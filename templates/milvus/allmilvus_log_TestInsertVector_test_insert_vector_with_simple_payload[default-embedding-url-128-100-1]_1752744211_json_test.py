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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-1]_1752744211_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-1]_1752744211.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl12810011752744211Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-1]_1752744211.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-1]_1752744211.json"
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
    'RequestId': 'b45615fd-62ef-11f0-bfce-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_30_073061wOpNnPKz',
    'dimension': 128,
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
    'RequestId': 'b4764e3c-62ef-11f0-a008-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_30_073061wOpNnPKz',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Alan Miller',
    'address': '862 Michele Prairie Apt. 355\nSouth Joseton, WV 90149',
    'text': 'Cell pattern on draw audience Republican foot. Nation others health how whole various. Less direction action commercial find important.',
    'email': 'marshalljohn@example.org',
    'phone_number': '+1-611-675-3563x603',
    'array_int_dynamic': [
    34611,
],
    'array_varchar_dynamic': [
    'Timothy Romero',
    'Joseph Gray',
    'Kerri Kirby',
    'Tracy Morris',
    'Christina Cooper',
    'Zachary Fisher',
    'Adam Luna',
    'Tammy Perez',
],
    'json': {
    'name': 'Patrick Hudson',
    'address': '0720 Amanda Drive Apt. 592\nNorth Lindaland, NJ 92584',
},
    'key46126': 'value10366',
    'key78061': 'value38836',
    'key57927': 'value15740',
    'key2925': 'value56319',
    'key41184': 'value55685',
    'key67175': 'value35968',
    'key22404': 'value58899',
    'key5242': 'value4689',
    'key6': 'value27096',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Angela Smith',
    'address': '873 Debra Crest Suite 626\nFredhaven, VI 86852',
    'text': 'Focus him include game. Cause bank interview per. Mention poor news way go.\nFind because newspaper activity many wide three. Eat together stand energy.',
    'email': 'sanchezkelsey@example.org',
    'phone_number': '306.795.8042x057',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Shaw',
    'Kelly Blevins',
    'Jack Gould',
    'Andrea Lopez',
    'Timothy Hill',
    'Kendra Warren',
    'Nicole Snyder',
    'Amanda Miller',
    'Samantha Nunez',
    'Peter Garcia',
],
    'json': {
    'name': 'Jonathan Campbell',
    'address': '9507 Tiffany Green Apt. 130\nSouth Hailey, NC 11505',
},
    'key68916': 'value75941',
    'key15997': 'value27902',
    'key97362': 'value21469',
    'key64976': 'value48092',
    'key75832': 'value16372',
    'key88259': 'value53575',
    'key60997': 'value5688',
    'key89766': 'value39844',
    'key79871': 'value23649',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Troy Mcclain',
    'address': '96615 Heather Knoll Suite 646\nEast Kylieport, HI 55014',
    'text': 'Truth turn could. Pick test consider defense professional important wife same.\nMaintain wonder me. Others cup growth same more.',
    'email': 'ofigueroa@example.com',
    'phone_number': '646-315-2788',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Megan Mahoney',
    'Teresa Rasmussen',
    'Lori Chavez',
    'Tammy Terrell',
    'Susan Proctor',
    'Amanda Robbins',
    'Kimberly Herrera',
    'Joseph Smith',
    'Sarah Perez',
    'Elizabeth Webb',
],
    'json': {
    'name': 'Megan Fernandez',
    'address': '2926 Williams Trail\nEast Robertburgh, ID 02287',
},
    'key15446': 'value45191',
    'key77138': 'value43343',
    'key88520': 'value55643',
    'key19514': 'value805',
    'key62348': 'value9844',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Brian Farrell',
    'address': '09045 Jodi Expressway\nKeithland, MI 05122',
    'text': 'Without color again sort yeah. Southern heavy truth box tell most consider. Economic approach reveal option else. Full role ready police easy article where stand.',
    'email': 'cheryl05@example.org',
    'phone_number': '719.593.8020x5234',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Desiree Williams',
    'Natalie Johnson',
],
    'json': {
    'name': 'Crystal Cherry',
    'address': '0002 Benjamin Highway\nBrookstown, FM 80941',
},
    'key21668': 'value14521',
    'key99196': 'value54464',
    'key40602': 'value45352',
    'key92916': 'value4167',
    'key82662': 'value59981',
    'key25815': 'value45690',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Christopher Snyder',
    'address': '255 Heather Knolls Apt. 961\nEast Taramouth, VI 39525',
    'text': 'Allow current behind call collection ability. Individual success successful red our guess center. Reality director skill concern interest move hour threat.',
    'email': 'turnerpamela@example.com',
    'phone_number': '+1-949-391-7030x3310',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Phillips',
    'Jordan Jefferson',
    'Jared Welch',
    'Cynthia Wilson',
    'Sarah Hernandez',
],
    'json': {
    'name': 'Tammy Davis',
    'address': '049 Michael Point\nIsabellaborough, DE 03898',
},
    'key83202': 'value21455',
    'key86996': 'value69868',
    'key68621': 'value38923',
    'key12500': 'value64519',
    'key26683': 'value76627',
    'key56195': 'value30963',
    'key86066': 'value39565',
    'key3038': 'value96089',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Logan Goodwin',
    'address': '7802 Stephanie Creek\nNorth Debbie, MT 75277',
    'text': 'Political western government top.\nPublic so TV into maybe foot page believe. Look fly accept option wind how.',
    'email': 'xsmith@example.org',
    'phone_number': '632-645-3028x0336',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Julie Scott',
    'Mark Howard',
    'Deborah Howard',
    'Mrs. Melissa Mcdonald',
    'Dr. Kyle Brown',
    'John Flores',
],
    'json': {
    'name': 'Whitney Padilla',
    'address': '193 Bailey Shoal Suite 436\nOlsonstad, TN 32370',
},
    'key26294': 'value85725',
    'key78466': 'value84021',
    'key62598': 'value61475',
    'key82486': 'value11296',
    'key558': 'value58562',
    'key16868': 'value89876',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Jessica Stanley',
    'address': 'Unit 1877 Box 7783\nDPO AE 80033',
    'text': 'Fall myself very fine subject well. Design answer suddenly attack parent marriage.\nEconomy heart mouth represent than role foreign base. Successful tax sound part bring what.',
    'email': 'ocole@example.com',
    'phone_number': '001-728-347-2458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Diana Cardenas',
    'Gregory Perez',
],
    'json': {
    'name': 'Melissa Fisher',
    'address': '68999 Harris Mount\nAngelaland, VT 38129',
},
    'key82439': 'value82790',
    'key14492': 'value80879',
    'key14059': 'value36498',
    'key24541': 'value28765',
    'key83455': 'value15403',
    'key47056': 'value26197',
    'key77970': 'value9557',
    'key79762': 'value48474',
    'key56858': 'value11224',
    'key55980': 'value14181',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Shannon Hood',
    'address': '778 Edward Track Apt. 157\nWilsontown, NM 95613',
    'text': 'Attorney significant court grow throw involve responsibility. Car practice law size training learn. Little company performance individual soon tend attorney.',
    'email': 'judith84@example.net',
    'phone_number': '498.980.4143x957',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Paul Cowan',
    'Steven Wolf',
],
    'json': {
    'name': 'Mr. Scott Lee Jr.',
    'address': '3561 Jennifer Highway Suite 866\nKathyton, ME 47288',
},
    'key10110': 'value55256',
    'key65880': 'value7806',
    'key49929': 'value10369',
    'key59278': 'value88769',
    'key6309': 'value72198',
    'key60895': 'value50421',
    'key73959': 'value36076',
    'key37201': 'value66120',
    'key81141': 'value10713',
    'key71680': 'value72065',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Kimberly Jenkins',
    'address': '41377 Heather Junctions\nLake Jenniferville, NE 12079',
    'text': 'Door reach oil project live. Know national travel step sing which.\nLook experience listen southern real. Score skill hear nor. Method party report according but.',
    'email': 'millertracy@example.com',
    'phone_number': '962-818-1032x21535',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Jacobs',
    'Brian Orozco',
    'Joseph Burke',
    'Tammy Wallace',
    'Hector Boyd',
    'James Mills',
    'Justin Hernandez',
    'Tyler Hall',
],
    'json': {
    'name': 'Eric Parsons',
    'address': '8983 Gray Stream\nEmilybury, NV 95244',
},
    'key61390': 'value49871',
    'key70388': 'value60218',
    'key86908': 'value43804',
    'key73865': 'value30785',
    'key41337': 'value7624',
    'key35544': 'value98295',
    'key58131': 'value23710',
    'key58010': 'value70937',
    'key58608': 'value95748',
    'key62249': 'value93700',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Kathryn Rojas',
    'address': '2412 Todd Coves\nAshleychester, MH 50832',
    'text': 'Suggest film someone attorney fire task become billion. Understand number movement top tend stuff tonight.',
    'email': 'stephenmeyer@example.org',
    'phone_number': '(269)294-2199',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robert Rodriguez',
    'Diana Smith',
    'Steven Martin',
    'Barbara Wells',
    'Daniel Gonzalez',
    'Nicole Wilson',
    'Jessica Barnett',
    'Rodney Jordan',
    'Michael Jarvis',
    'Susan Hudson',
],
    'json': {
    'name': 'Michelle Nguyen',
    'address': '3184 Harris Well\nNew Brittany, FM 53314',
},
    'key6779': 'value2762',
    'key12028': 'value15346',
    'key250': 'value52626',
    'key39914': 'value10748',
    'key81687': 'value50279',
    'key58358': 'value71858',
    'key21240': 'value20041',
    'key75154': 'value73326',
    'key9197': 'value46843',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Levi Elliott',
    'address': '6738 Hamilton Branch\nNew Beth, CO 29685',
    'text': 'Town law floor third family. Approach tree son bit rest try wide.\nEvent many yet ever page. Black them kitchen hour away. Deal husband key.',
    'email': 'shawn07@example.net',
    'phone_number': '422.548.7141x95508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Janet Vasquez',
    'Tammy Gilbert',
    'Rachel Farley',
    'Lisa Shelton',
    'Jessica Adkins',
    'Connie Dalton',
    'Dr. Vanessa Williams DDS',
],
    'json': {
    'name': 'Matthew Cruz',
    'address': '3126 Ward Gateway Suite 916\nFernandeztown, SD 47403',
},
    'key22894': 'value7676',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Beth Gay',
    'address': '1139 Samantha Stream Suite 207\nEricstad, WY 94960',
    'text': 'Ask protect prove language energy end. Civil feeling money house radio property west. Take off gas line. Door technology right first.',
    'email': 'krussell@example.com',
    'phone_number': '671-597-9115',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Seth Lee',
],
    'json': {
    'name': 'Kiara Huerta',
    'address': '46320 Robinson Spring\nEast Justinville, HI 08713',
},
    'key13445': 'value90240',
    'key50409': 'value66368',
    'key67322': 'value39679',
    'key19181': 'value16173',
    'key24478': 'value33856',
    'key73247': 'value53363',
    'key18555': 'value21609',
    'key92842': 'value69482',
    'key44335': 'value85703',
    'key47505': 'value10289',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Jermaine Dawson DDS',
    'address': '239 Thomas Underpass Apt. 416\nPerezmouth, MH 08785',
    'text': 'Recent become ago sell but table team person. Improve play field walk by. Wind source just live outside. For trouble rule old same.',
    'email': 'hensleyjennifer@example.net',
    'phone_number': '5909720852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shane Morton',
    'Jennifer Sheppard',
],
    'json': {
    'name': 'Bruce Hunter',
    'address': '561 Robin Mountain\nMichaelmouth, NJ 66171',
},
    'key17002': 'value89469',
    'key64688': 'value24574',
    'key3443': 'value64525',
    'key23816': 'value29055',
    'key1951': 'value35600',
    'key61544': 'value43541',
    'key57400': 'value42260',
    'key39082': 'value14520',
    'key88611': 'value3612',
    'key32529': 'value7237',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Christopher Brown',
    'address': '14618 Oscar Bridge Suite 879\nBarryland, SC 05644',
    'text': 'Buy less public realize always yeah. Magazine both heart economy.\nKitchen certainly standard open inside real. Five reduce eight.',
    'email': 'kellyaudrey@example.com',
    'phone_number': '(750)576-9779x480',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Keith Hernandez',
    'Victoria Mann',
],
    'json': {
    'name': 'Sheila Ho',
    'address': '05908 Vanessa Shoal\nHarrisside, SC 08527',
},
    'key68551': 'value53320',
    'key12146': 'value87010',
    'key75008': 'value33931',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Marie Chavez',
    'address': '57235 Stephenson Highway\nPort Amber, SD 03030',
    'text': 'Outside tell structure he long bring run. Truth quite Republican accept forget. Morning loss current claim.\nWould glass person Democrat soldier. Research us crime admit other.',
    'email': 'willisrobert@example.org',
    'phone_number': '001-670-928-2498x2690',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Savannah Sawyer',
    'Erica Wright',
    'Daniel Hendrix',
    'Heather Trevino',
    'Denise Duarte',
    'Joshua Daniels',
    'Jose Chandler',
    'Aaron Owens',
    'Deborah Griffin',
    'Robert Scott',
],
    'json': {
    'name': 'Kiara Durham',
    'address': '11132 Cooper Center Suite 673\nNorth Peggy, NC 80636',
},
    'key33284': 'value3944',
    'key77073': 'value48806',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jesse Rich',
    'address': 'Unit 2202 Box 7445\nDPO AP 06732',
    'text': 'Purpose test century civil.\nMrs one today thus bag strategy moment.\nMrs entire dinner black. Less same treat method data western idea. Maintain positive throw.',
    'email': 'boltonlindsey@example.com',
    'phone_number': '+1-572-237-2018x30676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Allison James MD',
    'Michele Spears',
    'Aaron Alvarado',
    'Rachel Baird',
],
    'json': {
    'name': 'Julie Christensen',
    'address': '003 James Hills Suite 704\nNew Bryanmouth, ND 17026',
},
    'key72959': 'value35235',
    'key90282': 'value26834',
    'key55989': 'value40399',
    'key88202': 'value74993',
    'key52973': 'value27846',
    'key59339': 'value36113',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Karen Patel',
    'address': '852 Burns Expressway\nEast Jeffmouth, UT 36367',
    'text': 'Similar most foot add.\nAffect television yet develop. Increase follow feel. Course responsibility charge relate training.',
    'email': 'browneric@example.com',
    'phone_number': '(810)430-1094x3777',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Walker',
],
    'json': {
    'name': 'Andrea Williams',
    'address': '1882 Ramos Hollow\nNew Angela, MS 33106',
},
    'key56295': 'value69362',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Philip Taylor',
    'address': '5765 Jeffrey Park Apt. 328\nStevenborough, KY 48974',
    'text': 'Smile hold involve road appear method.\nNecessary produce quickly every.\nLook road administration back picture six kid. Accept central feel back concern town including.',
    'email': 'smithmary@example.org',
    'phone_number': '+1-473-767-8869x676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Hill',
    'Devin Johnson',
    'Michael Tyler',
],
    'json': {
    'name': 'David Sexton',
    'address': '92320 Sullivan Estates Apt. 578\nNorth Jacobville, OR 57431',
},
    'key3037': 'value91536',
    'key55164': 'value35535',
    'key56035': 'value30832',
    'key58002': 'value25478',
    'key88811': 'value53011',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Rachel Brown',
    'address': '165 Russell Plain Suite 218\nPort Suzannemouth, LA 12960',
    'text': 'Reality surface mission happy. Discuss last day deep small task.\nBreak message teacher responsibility old. Question growth quickly scientist tough himself.',
    'email': 'mcgeejennifer@example.com',
    'phone_number': '798-323-5716',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Justin Lopez',
    'Jordan Ford',
],
    'json': {
    'name': 'Catherine Rodgers',
    'address': '9980 Byrd Spur Apt. 828\nJayport, MS 43311',
},
    'key33922': 'value92499',
    'key85216': 'value55160',
    'key76824': 'value66592',
    'key18304': 'value41452',
    'key59736': 'value97751',
    'key39444': 'value322',
    'key70040': 'value85565',
    'key48000': 'value95532',
    'key8582': 'value30573',
    'key62374': 'value5935',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Dylan Jones',
    'address': '521 Richard Port\nWest Wendy, WA 28479',
    'text': 'Apply way budget organization. Send strategy speak manager. Who board stop born kitchen.\nMagazine push garden we several hot understand. Space participant loss say charge.',
    'email': 'sarahlyons@example.com',
    'phone_number': '998.570.3129',
    'array_int_dynamic': [
    78058,
],
    'array_varchar_dynamic': [
    'Carl Gregory',
    'Gail Jackson',
    'Charles Pruitt',
],
    'json': {
    'name': 'Katelyn Green',
    'address': '183 Cole Flats Suite 135\nNathanielfurt, NV 68810',
},
    'key76773': 'value72677',
    'key75784': 'value95871',
    'key75757': 'value85341',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Brenda Reed',
    'address': '241 Walker Passage\nWoodstad, VT 05375',
    'text': 'Physical join item realize. Stand entire write indicate character. Option commercial both ten.',
    'email': 'heidi60@example.net',
    'phone_number': '+1-629-674-1507x9029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jeffery Rivera',
    'Cynthia Walton',
    'Renee Curtis',
    'Heidi Rose',
],
    'json': {
    'name': 'Daniel Hanson',
    'address': '860 Henderson Drive Apt. 138\nWest Charleschester, WY 51366',
},
    'key58607': 'value91927',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jonathan Copeland',
    'address': 'USCGC Hernandez\nFPO AE 06099',
    'text': 'Author under common similar. Success some education provide seem stand debate. Table kitchen Republican sport spend. Think power authority from appear.',
    'email': 'mark96@example.com',
    'phone_number': '310.241.2013x714',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Bruce Mendoza',
    'James Green MD',
    'Christine Reyes',
    'Jesse Osborne',
    'Mr. Jesus Mccarthy',
    'Kevin Dean',
],
    'json': {
    'name': 'Melissa Wagner',
    'address': '7961 Amber Valley Apt. 168\nWest Latoyaberg, NE 08674',
},
    'key84624': 'value58360',
    'key16348': 'value98438',
    'key74225': 'value96717',
    'key28873': 'value32399',
    'key64733': 'value70254',
    'key37000': 'value30393',
    'key93056': 'value67216',
    'key59048': 'value69051',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jack Rodgers',
    'address': '5545 Allen Drive Apt. 379\nBrownfurt, DE 76771',
    'text': 'Join great rock story ok. Help discuss color work before. Pretty story result white.\nGeneration care pick around fish race. Friend future network.',
    'email': 'diana62@example.net',
    'phone_number': '(496)344-1075x379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Parker',
    'Brandon Turner',
    'Pamela Lawrence',
    'Nicholas Brown',
    'Veronica Nolan',
    'Laura Thomas',
    'William Reynolds',
    'Samantha Clark',
],
    'json': {
    'name': 'Douglas Ferguson',
    'address': '159 Johnson Estates Suite 003\nErintown, SC 01649',
},
    'key42126': 'value56543',
    'key82736': 'value7350',
    'key62776': 'value95265',
    'key29916': 'value98771',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Luis Le',
    'address': 'PSC 8760, Box 8441\nAPO AE 64059',
    'text': 'Budget six represent money attorney. Hospital current laugh difference. Worry I start sell. Answer service much magazine expert.',
    'email': 'amber68@example.com',
    'phone_number': '447-450-0589x33286',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Montoya',
    'James Ali',
    'Dana Simmons',
    'Lori Holt',
    'Mary Moore',
    'Andrew Jones',
    'Diana Donovan',
    'Mathew Smith',
    'Marvin Patel',
    'Cody Silva',
],
    'json': {
    'name': 'Samuel Macdonald',
    'address': '6228 Teresa Ridges Suite 483\nAriasmouth, MA 66838',
},
    'key90423': 'value69962',
    'key20360': 'value20277',
    'key1132': 'value26118',
    'key28967': 'value46515',
    'key19665': 'value34578',
    'key32749': 'value95053',
    'key47202': 'value7303',
    'key10083': 'value80391',
    'key22824': 'value7490',
    'key61527': 'value30192',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Ronald Lowe',
    'address': 'PSC 3970, Box 6992\nAPO AP 63786',
    'text': 'Soon poor before everyone team. Ground turn a talk. Away choice star wind answer range.\nApply audience beyond those carry. Activity rule certainly chance me.',
    'email': 'millerangela@example.com',
    'phone_number': '346-641-6017x7118',
    'array_int_dynamic': [
    12645,
],
    'array_varchar_dynamic': [
    'Jason Allen',
    'Jackson King',
    'Daniel Combs',
    'Donald Watson',
    'Destiny Wilson',
    'Christopher Gordon',
    'Krista Taylor',
    'Gerald Hernandez',
    'Danielle Gibson',
],
    'json': {
    'name': 'Curtis Hoover',
    'address': '5717 Kathleen Tunnel\nSouth Nathanberg, CA 74897',
},
    'key49761': 'value40211',
    'key4778': 'value69151',
    'key63659': 'value8200',
    'key75643': 'value2298',
    'key81219': 'value3177',
    'key69507': 'value84172',
    'key51061': 'value17937',
    'key8352': 'value16293',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Rebecca Bauer',
    'address': 'Unit 5005 Box 0289\nDPO AP 63419',
    'text': 'Cup need matter science TV some system. Wish say main once.\nIdentify indicate a consider win. Impact think major show. Low decade almost citizen clear school.',
    'email': 'nmartin@example.com',
    'phone_number': '001-762-911-6608',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Kim',
    'Jennifer Poole',
],
    'json': {
    'name': 'Kimberly Ray',
    'address': '0658 Clark Plains Apt. 495\nPhelpsville, VT 58106',
},
    'key19382': 'value5575',
    'key4644': 'value36359',
    'key53940': 'value35761',
    'key37196': 'value42243',
    'key45622': 'value57288',
    'key66900': 'value27370',
    'key58180': 'value43317',
    'key48100': 'value63205',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Tyler Shaffer',
    'address': '6929 Patricia Inlet Suite 208\nEast Christopher, IL 86172',
    'text': 'Finish administration evening nation. Save soldier new center.\nCourt kind exactly star factor.\nFeel rich significant father analysis it.',
    'email': 'santiagomichael@example.org',
    'phone_number': '226.252.6019x2159',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Nelson',
    'Randy Riley',
    'Lucas Cox',
    'Michael Johnson',
],
    'json': {
    'name': 'Mason Pratt',
    'address': '7622 Craig Drive Suite 255\nBrowntown, DE 53205',
},
    'key70271': 'value63072',
    'key31704': 'value2521',
    'key79760': 'value31256',
    'key30625': 'value28202',
    'key86424': 'value4587',
    'key84614': 'value43240',
    'key39942': 'value37521',
    'key71399': 'value4533',
    'key99353': 'value32932',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Denise Fisher',
    'address': 'USCGC Hernandez\nFPO AA 69667',
    'text': 'Tax open financial near provide adult direction wall. Support former expect. Traditional without size especially.\nSignificant set under item public. Common how close talk.\nAgree feel trade seven.',
    'email': 'marcusrivera@example.com',
    'phone_number': '2306961546',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Taylor',
    'Alexis Dennis',
    'Jennifer Price',
    'Raven Ayala',
    'Robert Reyes',
    'Deborah Jackson',
    'Heather George',
],
    'json': {
    'name': 'Jack Benitez',
    'address': '12342 Yang Canyon\nLake Luis, WA 83268',
},
    'key43395': 'value64574',
    'key56121': 'value32645',
    'key35705': 'value44506',
    'key33178': 'value75437',
    'key67348': 'value28808',
    'key84822': 'value62474',
    'key20326': 'value48101',
    'key93295': 'value63600',
    'key99171': 'value68545',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Martin Smith',
    'address': '430 Jones Common\nHarmonland, NJ 02992',
    'text': 'Away care watch bag. Smile several student model out beautiful ago society.\nAuthority quickly process wind apply better coach. White network wife local where leave protect.',
    'email': 'annacampbell@example.org',
    'phone_number': '(885)796-0148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Wiley',
    'Jason Salinas',
    'Shawn Ortiz',
    'Anna Wheeler',
    'Kimberly Elliott',
],
    'json': {
    'name': 'Casey Higgins',
    'address': '8094 Poole Highway Suite 027\nPort Tiffany, ID 16920',
},
    'key43355': 'value47226',
    'key10513': 'value98514',
    'key66010': 'value98500',
    'key62993': 'value59824',
    'key61973': 'value49328',
    'key68845': 'value57727',
    'key99178': 'value9269',
    'key33793': 'value73442',
    'key50298': 'value35599',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Andrew Wallace',
    'address': 'USCGC Mendoza\nFPO AP 42903',
    'text': 'Thing difference include sea commercial imagine charge. Mind better collection example. Explain direction impact born we wall mention.',
    'email': 'brownleslie@example.com',
    'phone_number': '878.769.0261',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Colleen Ramos',
    'William Warren',
    'David Wells',
    'Jeanette Neal',
    'Dr. Jordan Jones',
    'Jennifer Blake',
    'Jennifer Martin',
],
    'json': {
    'name': 'Jennifer Hayes',
    'address': '054 White Square Suite 422\nNew Shellyborough, GA 64581',
},
    'key65434': 'value71193',
    'key87363': 'value5693',
    'key52682': 'value82121',
    'key41606': 'value48521',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Karen Barajas',
    'address': '602 Dylan Ports Apt. 402\nNorth Johnstad, TN 94874',
    'text': 'Determine thus early dinner. Lead type carry agreement. Control federal white.\nAction attention former anyone to. My specific course among reduce discussion good rate.',
    'email': 'johnduncan@example.com',
    'phone_number': '491-929-3963x4119',
    'array_int_dynamic': [
    46892,
],
    'array_varchar_dynamic': [
    'Robin Lopez',
    'Daniel Buchanan',
],
    'json': {
    'name': 'Thomas Lewis',
    'address': '77342 Keith Street\nNew Markhaven, MA 06224',
},
    'key8526': 'value80133',
    'key109': 'value10389',
    'key60306': 'value39037',
    'key72307': 'value7747',
    'key24552': 'value55609',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Holly Luna DDS',
    'address': '703 Thompson Bridge\nPort Marcus, KS 70877',
    'text': 'Person about enter yeah like thus field professional. Grow produce growth student word weight thousand. Painting middle process process allow hot hear.',
    'email': 'jeremy84@example.com',
    'phone_number': '296-745-9326x307',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Mcbride',
    'Nancy Wong',
    'Adam Scott',
    'Michael Lopez',
    'Sara Thornton',
    'Deborah White',
    'Elizabeth Odonnell',
    'Carrie Rodriguez',
    'Melissa Chen',
    'Janet James',
],
    'json': {
    'name': 'David Cooper',
    'address': 'Unit 2497 Box 3072\nDPO AA 74739',
},
    'key93819': 'value23314',
    'key57884': 'value12289',
    'key82301': 'value27138',
    'key8562': 'value57843',
    'key85310': 'value68971',
    'key99140': 'value32317',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Sheryl Castro',
    'address': '289 Craig Ferry\nKimberlyland, NV 94814',
    'text': 'Recognize month small carry activity man. Treatment enough particularly adult produce. Dog event both paper Mrs future ability.\nCurrent avoid specific in stand bank.',
    'email': 'ronald30@example.net',
    'phone_number': '922.691.8831x87169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Fisher',
    'Michelle Esparza',
    'Briana Smith',
    'Christopher Johnson',
    'Katrina Salazar',
],
    'json': {
    'name': 'Brandy Morris',
    'address': '67120 Corey Neck Suite 730\nLake Andrew, WV 41312',
},
    'key29135': 'value52535',
    'key30219': 'value62482',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Aaron Wilson',
    'address': '6141 Harmon Ways\nPaulton, KY 30451',
    'text': 'So too field. Street onto themselves light pattern trade gun. Green size step data language life model.',
    'email': 'nmaynard@example.com',
    'phone_number': '001-710-600-9986x674',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tamara Bender',
    'Angela Turner',
    'Jennifer Coleman',
    'William Pierce',
    'Tonya Berry',
    'Mary Chavez',
    'Kristen Michael',
    'Amber Casey',
    'Beth Sanchez',
    'Meghan Smith',
],
    'json': {
    'name': 'Tony Campos',
    'address': '412 Rojas Fords Apt. 133\nEast Morganmouth, KY 54367',
},
    'key60533': 'value96019',
    'key91476': 'value46491',
    'key67594': 'value43473',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Stephen Bennett',
    'address': '739 Elliott Trace\nSarahshire, TX 13888',
    'text': 'Strategy eight chance body article. During bad doctor dinner almost fish. Six number western use wind safe many let. Possible item best tend until election foreign third.',
    'email': 'pricelynn@example.org',
    'phone_number': '728-775-8642',
    'array_int_dynamic': [
    77460,
],
    'array_varchar_dynamic': [
    'Raymond Kelly',
    'Bryan Logan',
    'Grace Black',
    'Christopher Mccullough',
],
    'json': {
    'name': 'Martin Lewis',
    'address': 'PSC 1591, Box 8876\nAPO AP 40503',
},
    'key47490': 'value17210',
    'key8408': 'value47778',
    'key8518': 'value37543',
    'key98616': 'value16787',
    'key28528': 'value88155',
    'key81394': 'value77005',
    'key18642': 'value57118',
    'key40390': 'value20848',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Madison Lam DDS',
    'address': '45411 Joshua Coves Apt. 146\nLake Kathyville, MP 71000',
    'text': 'End whatever build current act build lose. Enough rise process when save tend despite.',
    'email': 'thomasbauer@example.net',
    'phone_number': '(365)374-5462x33781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Pennington',
    'Mary Bowers',
    'Elizabeth Hunter',
    'Jessica Rosales',
    'Robert Meyer',
],
    'json': {
    'name': 'Martin Gonzales',
    'address': '091 Lisa Isle\nJustinmouth, IA 82630',
},
    'key56005': 'value5213',
    'key41108': 'value82106',
    'key64107': 'value29631',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Ryan Sparks',
    'address': '18289 Holmes Gardens\nJenkinsburgh, NE 99057',
    'text': 'Serious no eat material worker who against act. Return increase yeah want.\nMaterial Democrat myself third. Note may Mrs. Central adult hear human than.',
    'email': 'tonyellis@example.org',
    'phone_number': '6517900397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'William Ware',
    'Nicole Mason',
    'Holly Jones',
    'Jennifer Smith',
    'Sydney Mason',
    'Kimberly White',
    'Ronald Kennedy',
    'Tabitha Paul',
    'Bruce Armstrong',
    'Vanessa Hicks',
],
    'json': {
    'name': 'Dennis Tucker',
    'address': 'USNV Hogan\nFPO AE 44141',
},
    'key74979': 'value28402',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Kristi Booth',
    'address': '973 Robin Highway Suite 247\nNorth Brenda, MT 48342',
    'text': 'Form onto establish hotel. Reveal site everybody himself teacher middle gun forward. Heavy left PM her blood federal begin meeting.\nFish mean face decide.',
    'email': 'fcox@example.com',
    'phone_number': '745-576-2366x1168',
    'array_int_dynamic': [
    28366,
],
    'array_varchar_dynamic': [
    'Colleen Higgins',
    'Lisa Stafford',
    'Jonathan Alvarado',
    'Valerie Ho',
    'Jeff Stone',
],
    'json': {
    'name': 'Kimberly Marshall',
    'address': 'PSC 5736, Box 4112\nAPO AE 25470',
},
    'key97712': 'value42022',
    'key36412': 'value46144',
    'key34099': 'value11304',
    'key73055': 'value36898',
    'key9102': 'value26784',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Brenda Beard',
    'address': '93960 Gregory Springs Suite 773\nNew Michael, KY 72781',
    'text': 'Together office example cup red show.\nMight close knowledge where performance phone much. Decision game behind in. Tonight national mean much.',
    'email': 'brandydowns@example.org',
    'phone_number': '001-886-479-1856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Luna',
    'Kimberly Luna',
    'Christopher Yates',
],
    'json': {
    'name': 'Rachel Wise MD',
    'address': 'USCGC Barnett\nFPO AP 08006',
},
    'key51338': 'value78226',
    'key69074': 'value53004',
    'key27740': 'value87796',
    'key84945': 'value16771',
    'key57613': 'value96965',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Justin Santiago',
    'address': '26519 Woods Forge\nSouth Curtiston, MH 85439',
    'text': 'Staff there break piece skill whose.\nParticipant all risk us where. Individual activity feeling them physical speech road.\nSerious gas audience his picture candidate weight.',
    'email': 'blakekathryn@example.net',
    'phone_number': '(330)587-7606x488',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Thompson',
],
    'json': {
    'name': 'Matthew Morgan',
    'address': '96902 Eric Walk Apt. 187\nCollinsbury, HI 38673',
},
    'key59070': 'value77924',
    'key93273': 'value83672',
    'key93347': 'value36343',
    'key1824': 'value93555',
    'key71083': 'value28389',
    'key26072': 'value80008',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Ashley Acevedo',
    'address': '484 Scott Ramp\nEast Marciaport, WI 05578',
    'text': 'She rise class use. Detail want despite range rich who southern.\nStay among rock people reveal mission. Like Congress production material raise professional.',
    'email': 'monique26@example.com',
    'phone_number': '582.576.8973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Rhonda Davis',
    'Deborah Martin',
    'Vickie Vega',
    'Tiffany Hayes',
    'Jessica Wilson MD',
    'Emily Dickson',
    'Mary Rice',
    'Jon Hopkins',
    'Amy Davis',
],
    'json': {
    'name': 'Joe Keith',
    'address': '0227 Cole Curve\nLindseyburgh, NH 11046',
},
    'key64139': 'value65355',
    'key43728': 'value93179',
    'key56789': 'value55541',
    'key75539': 'value33636',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Kevin Bennett',
    'address': '254 Rice Vista\nTimothyton, WA 99562',
    'text': 'Process information artist business. Important program why strong. Later late by meeting.',
    'email': 'rebecca67@example.org',
    'phone_number': '923-296-2491x44104',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mary Glass',
    'Jerry Ross',
    'Jennifer Lewis',
    'William Harrison',
    'Elizabeth Bentley',
    'Carl Tran',
    'Amanda Cook',
    'Alex Stevens',
],
    'json': {
    'name': 'Cheryl Bradley',
    'address': '0843 Michael Knoll\nScottmouth, MA 40549',
},
    'key28785': 'value722',
    'key40706': 'value77888',
    'key72216': 'value64789',
    'key46155': 'value62902',
    'key69649': 'value22984',
    'key82520': 'value77806',
    'key99651': 'value53925',
    'key78380': 'value98493',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Danielle Morton',
    'address': '96677 Garcia Curve Suite 212\nEast Frank, MN 82561',
    'text': 'Media seek thank mission employee newspaper method must. Order education or.\nMoney home perhaps process. Work ever medical wear manager room.',
    'email': 'ysullivan@example.com',
    'phone_number': '001-898-868-6340x30606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Susan Peters',
    'Lori Jordan',
    'Michelle Campbell',
    'Jeanette Cooper',
    'Jordan Jones',
    'Anthony Holmes',
    'Melissa Hall',
    'Michael Torres',
],
    'json': {
    'name': 'Robert Jordan',
    'address': '9171 Harris Ridge\nPort Natalieburgh, NE 05912',
},
    'key88785': 'value93068',
    'key79381': 'value96615',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Andrew Strong',
    'address': '2160 Mullins Light\nWest Megan, TX 22759',
    'text': 'Gas Mr interesting film alone store process. Determine could its writer community degree sort.\nLearn onto with voice return finally. Expect his body time property.',
    'email': 'chambersscott@example.com',
    'phone_number': '+1-517-688-2242x472',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michele Lee',
    'Taylor Orr',
    'Joseph Nguyen',
    'Kelly White',
    'Eric Clark PhD',
    'Patrick Jones III',
    'Tiffany Villegas',
    'Laurie Bell',
],
    'json': {
    'name': 'Christian Espinoza',
    'address': '278 Smith Bypass Suite 513\nBrownborough, FL 41156',
},
    'key99899': 'value88252',
    'key17852': 'value4100',
    'key49333': 'value88764',
    'key83787': 'value76520',
    'key51562': 'value44559',
    'key57021': 'value2001',
    'key93669': 'value20727',
    'key16081': 'value59146',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Justin Edwards',
    'address': '147 Page Forge\nLake Chelseahaven, VI 12813',
    'text': 'Various child eight. Movement certain source task travel key mother nothing. Who help check small staff why bar.',
    'email': 'moorerenee@example.net',
    'phone_number': '+1-811-349-9103x01322',
    'array_int_dynamic': [
    83660,
],
    'array_varchar_dynamic': [
    'Aaron Kaiser',
    'Wendy Olson',
    'Christopher Rowe',
    'Frances Roberts',
    'Edwin Smith',
    'Tammie Chang',
],
    'json': {
    'name': 'Steve Ward',
    'address': '5158 Stefanie Well\nEast Kelsey, NE 10096',
},
    'key20688': 'value69856',
    'key26453': 'value1136',
    'key95047': 'value11798',
    'key87885': 'value71191',
    'key62549': 'value12779',
    'key54905': 'value80267',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Erica Mueller',
    'address': '5823 Allison Burgs\nWest Jessica, FL 18037',
    'text': 'Treat issue get black minute. Threat another sit wind anything car. Sing although memory his could enough.',
    'email': 'gonzalezlisa@example.com',
    'phone_number': '+1-571-948-7140x67896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Frank Kelly',
    'Mr. Johnny Harper',
    'Edward Day',
    'Eric Ramos',
    'Megan Johnson',
    'Robert Grimes',
    'Danielle Thomas DVM',
    'Phyllis Washington',
],
    'json': {
    'name': 'Stacy Tran',
    'address': '20473 Thomas Land Apt. 105\nSouth David, OK 89709',
},
    'key72417': 'value33039',
    'key3983': 'value41158',
    'key61839': 'value99991',
    'key33263': 'value97595',
    'key38412': 'value96014',
    'key23324': 'value74357',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Dorothy Smith',
    'address': '942 Osborne Views Suite 220\nBlairchester, MT 58913',
    'text': 'Leg deep service you half start physical future. Still rich thus control.\nSince them country. Sea others fact those positive.\nEnter out sister prevent discussion.',
    'email': 'martinezlisa@example.org',
    'phone_number': '+1-596-609-4922',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Jordan',
    'Lindsay Miller',
    'Felicia Holloway',
    'James White',
    'Shawn Griffin',
    'Christine Raymond',
    'Emily Diaz',
    'Jerry Adams',
    'Larry Saunders',
    'Scott Bender',
],
    'json': {
    'name': 'Angela Williams',
    'address': '613 Michael Land\nWest Brandon, FL 01163',
},
    'key54515': 'value10230',
    'key95852': 'value33489',
    'key21922': 'value8072',
    'key90712': 'value93501',
    'key31983': 'value7981',
    'key92035': 'value18037',
    'key48099': 'value1055',
    'key83203': 'value63498',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Michael Salas',
    'address': '6170 Allen Valley\nLake James, NV 72695',
    'text': 'Central good happy itself goal factor many team. Agent on item main action. Fly society study quite claim treat.\nSave interview real according. Money know job argue large.',
    'email': 'tosborn@example.com',
    'phone_number': '607.367.7265x06794',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Weber',
    'Rachel Hester',
    'Joshua Green',
],
    'json': {
    'name': 'John Ruiz',
    'address': '6206 Anna Square Suite 514\nPort Alisonhaven, AS 29954',
},
    'key24896': 'value91402',
    'key7383': 'value61246',
    'key41767': 'value81827',
    'key81327': 'value92989',
    'key72933': 'value75999',
    'key26798': 'value80699',
    'key57692': 'value79569',
    'key62198': 'value40986',
    'key41642': 'value41542',
    'key25662': 'value87873',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Cory Ryan',
    'address': '969 Moreno Lodge\nNew Amanda, SC 18320',
    'text': 'White girl turn charge. Development artist home writer upon size it.\nTreatment daughter authority probably young share. Just consider nearly might. Hot he something produce race mind.',
    'email': 'andrewlambert@example.com',
    'phone_number': '(435)402-8012',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'April Walker',
    'Scott Williams',
    'Lisa Garrett',
    'Laura Crawford',
],
    'json': {
    'name': 'Whitney Olson',
    'address': '866 Chandler Squares Apt. 774\nKyleborough, OR 20367',
},
    'key77618': 'value89780',
    'key46073': 'value94722',
    'key99934': 'value6013',
    'key25080': 'value60486',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Christine Cruz',
    'address': '81494 Brandon Corners\nSouth Kimberlyland, NH 89890',
    'text': 'Peace investment dinner speak can detail. Star free bring forget here administration huge.\nBy easy population first century.',
    'email': 'amanda39@example.net',
    'phone_number': '001-592-658-6108x2682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marissa Clark',
],
    'json': {
    'name': 'Jessica Henderson',
    'address': 'Unit 0043 Box 3467\nDPO AP 69938',
},
    'key30962': 'value8207',
    'key37707': 'value95469',
    'key81596': 'value22168',
    'key3657': 'value81777',
    'key7036': 'value20300',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Kimberly Carlson',
    'address': 'Unit 7223 Box 4195\nDPO AP 19809',
    'text': 'State that treat sell high inside better. Fall office can right.\nSingle religious everything teacher food. Lawyer wide specific. Return you culture face huge lawyer. Town change game if some.',
    'email': 'dhanna@example.net',
    'phone_number': '+1-788-799-1683x9140',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kellie Garcia',
    'Angela Curtis',
    'Robin Johnson',
    'James Bullock',
    'Veronica Carr',
    'Craig Flores',
    'Jeffrey Atkins',
],
    'json': {
    'name': 'Steve Martin',
    'address': '026 Thompson Coves\nPhillipsfort, MS 60459',
},
    'key44562': 'value96211',
    'key80338': 'value92130',
    'key90569': 'value90552',
    'key69659': 'value55754',
    'key23365': 'value15511',
    'key92603': 'value67589',
    'key30025': 'value96363',
    'key78129': 'value28646',
    'key51677': 'value64195',
    'key67397': 'value44802',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Jason Stuart',
    'address': '309 Alexander Station Apt. 272\nNorth Sherryport, MI 33035',
    'text': 'Game entire mother positive.\nPeople star share product kind. Can per practice change measure out.',
    'email': 'tamarabennett@example.com',
    'phone_number': '7795267175',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kevin White',
],
    'json': {
    'name': 'Andrew Jordan',
    'address': '2086 Crystal Trafficway Suite 107\nLake Crystaltown, NJ 32848',
},
    'key73151': 'value58131',
    'key82081': 'value48817',
    'key55562': 'value19628',
    'key82669': 'value85596',
    'key26163': 'value75803',
    'key19578': 'value76913',
    'key94268': 'value67237',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'David Tran',
    'address': '96434 Davis Passage\nJohnshire, VI 93994',
    'text': 'Perform movement out explain reach test. Many natural summer point town. American water our expert him.',
    'email': 'qgriffin@example.org',
    'phone_number': '811.799.0604x3081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Chad Williams DDS',
    'Neil Costa',
    'Joseph Lucas',
    'James Page',
    'Brenda Schultz',
    'Michael Kelly',
    'Cynthia Norman',
    'Jeremy Reeves',
    'Adrian Elliott',
    'Kristen Ortiz',
],
    'json': {
    'name': 'Mandy Ward',
    'address': '8521 Jeffrey Extension Apt. 103\nNew James, AS 54667',
},
    'key38571': 'value65141',
    'key42007': 'value32551',
    'key71183': 'value65471',
    'key56743': 'value65876',
    'key30410': 'value41594',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Aaron Harvey',
    'address': '284 Mcguire Bridge\nPageburgh, MH 35624',
    'text': 'Position yard item true push day. Especially every option.\nHappen respond effort. Book agreement across child their. Law vote leave painting kind.',
    'email': 'shorton@example.org',
    'phone_number': '890-931-2804x4279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Welch',
    'Joshua Johnson',
    'Katherine Rowe',
    'Jay Lewis',
    'Sean Bailey',
    'Joshua Cole',
    'Donald Lee',
    'Oscar Campbell',
],
    'json': {
    'name': 'Michelle Walsh',
    'address': '9011 Katie Meadows\nPollardstad, MA 31644',
},
    'key45371': 'value97948',
    'key28547': 'value31065',
    'key80042': 'value35916',
    'key73062': 'value7237',
    'key67818': 'value31182',
    'key6269': 'value60507',
    'key48121': 'value44603',
    'key62818': 'value20787',
    'key76319': 'value65045',
    'key77067': 'value44515',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Stacey Hayes',
    'address': '0968 Ronnie Locks Apt. 195\nJasonmouth, NM 31008',
    'text': 'Into notice seek market choose. Successful my culture matter often boy.',
    'email': 'pateljulie@example.com',
    'phone_number': '873-637-2308x381',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Herrera',
    'Clifford Lopez',
],
    'json': {
    'name': 'Theresa Meza',
    'address': '939 Teresa Forge Apt. 205\nWest Vanessaberg, VT 03887',
},
    'key47635': 'value40290',
    'key71261': 'value42346',
    'key86867': 'value29770',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Lisa Dillon',
    'address': '97759 Melissa Walk\nNorth Tracy, CT 13712',
    'text': 'Require treatment receive another. Likely buy just participant hope.',
    'email': 'pbarnes@example.org',
    'phone_number': '(327)550-1596',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Molina',
    'Aaron Wood',
    'Shirley Kelly',
    'Jeffrey Hunt',
    'Amanda Henry',
    'Kathryn Richards',
    'Stephanie Garcia',
],
    'json': {
    'name': 'Bridget Crane',
    'address': '443 Zachary Plains\nRamirezfort, MA 09956',
},
    'key73252': 'value85173',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Stephanie Turner',
    'address': '45895 May Points\nNorth Anna, SC 83317',
    'text': 'Determine type before among threat grow. Rich agency race morning sure. Computer pattern civil measure series his.',
    'email': 'ghumphrey@example.com',
    'phone_number': '001-732-501-5968x9252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Mitchell Becker',
    'Brooke Leonard',
    'Lisa Taylor',
],
    'json': {
    'name': 'Bobby Salazar',
    'address': 'PSC 5371, Box 3624\nAPO AE 58978',
},
    'key77371': 'value92643',
    'key52051': 'value93702',
    'key9574': 'value50272',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Terry Morris',
    'address': '0428 Jennifer Tunnel\nAllenchester, IA 03908',
    'text': 'Spring discussion old allow point.\nAgreement experience cold cause season employee. Than part pass key. Local on century want.\nBest foreign know feeling inside. Effort after threat often.',
    'email': 'lunderwood@example.org',
    'phone_number': '848.506.2053',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Erika Jones',
    'Michael Chapman',
    'James Ward',
    'Jeff Wilcox',
],
    'json': {
    'name': 'Nicole Obrien',
    'address': '3864 Rodriguez Greens\nNew Jessicaborough, VT 66366',
},
    'key92799': 'value13665',
    'key17653': 'value8141',
    'key49631': 'value72776',
    'key47038': 'value49682',
    'key8694': 'value79115',
    'key53158': 'value24811',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Rachel Vega',
    'address': '53587 Danielle Street\nFlemingburgh, NJ 94731',
    'text': 'Against subject military cell lose. Though hospital reason southern. Method age event near. Data boy century call plant herself.\nPaper something suggest Congress not. And catch young then.',
    'email': 'anthony76@example.org',
    'phone_number': '661.963.1683',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Harris',
    'Angelica Humphrey',
    'Lisa Smith',
    'Alexander Scott',
],
    'json': {
    'name': 'Dennis Ryan',
    'address': '6148 Wilkinson Pines Suite 584\nWalkerstad, VI 34865',
},
    'key32935': 'value48016',
    'key60599': 'value61244',
    'key52137': 'value55880',
    'key53005': 'value78039',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Terry Thomas',
    'address': '21494 Snyder Fort\nPenningtonfurt, FL 38289',
    'text': 'Start wrong value training. Relate stop Democrat. Set modern foot less.',
    'email': 'bauermonica@example.com',
    'phone_number': '693-402-3000',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Smith',
    'William Gates',
    'Christine Rodriguez',
    'Teresa Walters',
],
    'json': {
    'name': 'Kristy Gill',
    'address': '94825 Dawn Lock Suite 597\nSarafort, VI 30568',
},
    'key1406': 'value30701',
    'key59218': 'value68747',
    'key37885': 'value22548',
    'key77101': 'value42716',
    'key20443': 'value47600',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Reginald Thornton',
    'address': '44566 Melanie Shoal\nAnthonychester, KY 24968',
    'text': 'Ball TV let message hear career. I in bill participant.\nAuthor home alone practice discover dinner.',
    'email': 'tanyataylor@example.net',
    'phone_number': '+1-890-372-2083x11504',
    'array_int_dynamic': [
    15557,
],
    'array_varchar_dynamic': [
    'Mr. Brian Johnson',
    'Andrew Mayer',
    'Robert Ochoa',
    'William Spence',
],
    'json': {
    'name': 'Breanna Phillips',
    'address': '11438 Nichole Haven\nBrownburgh, CT 60459',
},
    'key86513': 'value61122',
    'key15272': 'value47967',
    'key43372': 'value66128',
    'key34188': 'value86616',
    'key8952': 'value64755',
    'key7007': 'value10749',
    'key85810': 'value27641',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Matthew Chavez',
    'address': '436 Nielsen Lodge Apt. 815\nSouth Amandaside, AK 52162',
    'text': 'Some wear contain season authority note east produce. Watch answer forward land purpose age federal.',
    'email': 'joseph61@example.org',
    'phone_number': '350-768-1960',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ricky Sanchez',
    'Joanna James',
],
    'json': {
    'name': 'David Reeves',
    'address': '01780 Gibbs Walks Apt. 291\nEast Miguelchester, FL 73494',
},
    'key27362': 'value27915',
    'key217': 'value69280',
    'key61837': 'value7762',
    'key18003': 'value9835',
    'key35903': 'value21074',
    'key74343': 'value71756',
    'key97147': 'value8093',
    'key37134': 'value11372',
    'key48502': 'value31124',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Michael Brown',
    'address': '45936 Timothy Lodge\nDianamouth, MD 85181',
    'text': 'Statement tend common nation evening moment here. Indeed wind leader someone modern.\nPrevent point clearly law page. Stay might big establish. Quite say event value evening. Make pass full exist.',
    'email': 'fitzgeraldlisa@example.com',
    'phone_number': '780-510-0220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mary Gallagher',
    'Jack Parrish',
    'Brianna Pace',
],
    'json': {
    'name': 'Douglas Murray',
    'address': '391 Steve Glen Suite 540\nPaulfort, AZ 93859',
},
    'key74405': 'value67240',
    'key491': 'value19338',
    'key89770': 'value60515',
    'key56238': 'value48815',
    'key11624': 'value42424',
    'key19651': 'value31758',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Rachael Fisher',
    'address': '3082 Duarte Path\nProctorbury, MP 28996',
    'text': 'Capital feeling particular evidence office note. Set tough design father image eight. Us college available year.\nIndividual star several why. Poor say area big these.',
    'email': 'francislinda@example.net',
    'phone_number': '001-294-422-8191x1194',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Antonio Williams',
    'Stephanie Collins DVM',
],
    'json': {
    'name': 'Karen Gray',
    'address': '539 Jonathan Loop\nSouth Donna, ND 80651',
},
    'key1740': 'value349',
    'key22076': 'value79287',
    'key55271': 'value86989',
    'key82348': 'value41192',
    'key53661': 'value74257',
    'key40536': 'value65682',
    'key68887': 'value83474',
    'key89428': 'value25412',
    'key37112': 'value76308',
    'key14371': 'value35445',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Cynthia Parker',
    'address': '5722 Maria Skyway\nErinberg, DC 32798',
    'text': 'Assume stock against memory set. Consumer commercial not before information six.\nUnderstand win generation majority. Sister local hair bit seem bar. Marriage reveal song beat consumer wait send.',
    'email': 'michaelpruitt@example.net',
    'phone_number': '001-620-295-0589',
    'array_int_dynamic': [
    45391,
],
    'array_varchar_dynamic': [
    'Drew Blair',
    'Ashley Harrison',
    'Bradley Valdez',
    'Barbara Richmond',
    'Kevin Baird',
],
    'json': {
    'name': 'Adam Robinson',
    'address': '1403 Juan Rue Apt. 073\nWest Megan, IA 23958',
},
    'key7566': 'value34835',
    'key803': 'value44009',
    'key30260': 'value37681',
    'key19235': 'value33863',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Kathleen Cabrera',
    'address': 'Unit 5379 Box 2265\nDPO AP 45284',
    'text': 'And partner reach more very. Allow social middle.\nCertainly wonder skin enough citizen green billion. Though word heavy as next loss give.',
    'email': 'lduncan@example.com',
    'phone_number': '+1-483-739-8201x672',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Scott Jones',
    'Casey Page',
],
    'json': {
    'name': 'Lindsay Rodriguez',
    'address': '77544 Anthony Tunnel\nPort Jon, GA 24252',
},
    'key20851': 'value8371',
    'key57721': 'value72771',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Lisa Harrell',
    'address': '05699 Wendy Common Apt. 711\nDaviston, TX 69109',
    'text': 'Key like mission away weight issue. Summer risk against choose issue.\nSense institution treat south miss police option. Church exactly turn.',
    'email': 'achen@example.net',
    'phone_number': '582.596.9190',
    'array_int_dynamic': [
    76410,
],
    'array_varchar_dynamic': [
    'Andrea Rivera',
    'Ronald Smith',
    'Sandra Joseph',
    'Bryan Jones',
    'Shirley Briggs',
    'Mrs. Maria Santos',
    'Kyle Myers',
    'Heather Mitchell',
    'Jacqueline Small',
    'William Goodwin',
],
    'json': {
    'name': 'Kevin Clark',
    'address': '44921 Davis Meadow Suite 259\nJonesstad, MO 93397',
},
    'key94695': 'value37249',
    'key93198': 'value78812',
    'key70407': 'value90471',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Richard Johnson',
    'address': '773 Amy Landing Apt. 167\nRobinsonshire, IL 35284',
    'text': 'About method cup care cultural fight behavior. Then project thousand player put while. Risk visit member.',
    'email': 'abigail40@example.com',
    'phone_number': '646.713.5016x37938',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Thompson',
],
    'json': {
    'name': 'Christopher Shaw',
    'address': 'PSC 3562, Box 2886\nAPO AE 51339',
},
    'key26263': 'value3943',
    'key98046': 'value77686',
    'key87003': 'value45238',
    'key34374': 'value70603',
    'key49020': 'value59057',
    'key83717': 'value77446',
    'key12198': 'value15880',
    'key48180': 'value72374',
    'key42090': 'value19382',
    'key71681': 'value60272',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Cassie Wright DDS',
    'address': '54929 Warren Plaza\nJohnfurt, VA 73780',
    'text': 'Evening very plan letter activity phone leg how. Specific eat nor chair go chance action. She its dream difference western skill area.',
    'email': 'gbuck@example.net',
    'phone_number': '001-847-518-0235',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Peter Wagner',
    'Mary Vega',
    'Miguel Gonzalez',
    'Michael Hoover',
    'Dr. Nancy Brown',
    'Jordan Anderson',
    'Patricia Ferguson',
    'James Barnes',
    'Paul Schaefer',
    'Desiree Jones',
],
    'json': {
    'name': 'Christopher Lopez',
    'address': '7999 Garcia Tunnel\nNew Stephanie, PW 99826',
},
    'key58395': 'value77600',
    'key94453': 'value38201',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Taylor Hughes',
    'address': '846 Hawkins Hill\nSaramouth, PW 69618',
    'text': 'Take class into voice. Important woman school party.\nCommunity skill think off determine hot drop. Charge reveal hour type thousand second continue page.',
    'email': 'schneiderbrian@example.net',
    'phone_number': '436-285-0832x506',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffery Lopez',
    'Jimmy Freeman',
    'Rebecca Daniels',
    'John Brown',
    'Natalie Mitchell',
    'Steven Jones',
],
    'json': {
    'name': 'Mitchell Fernandez',
    'address': '386 Keith Crest Apt. 089\nTracyland, MO 17089',
},
    'key34389': 'value69426',
    'key95634': 'value35185',
    'key79083': 'value4282',
    'key47354': 'value6752',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Christine Anderson',
    'address': '45303 Anthony Summit\nGainesberg, ME 24829',
    'text': 'Attack property thus appear physical interview wait. Reality life speak difficult film story.',
    'email': 'caseycook@example.net',
    'phone_number': '001-331-566-9892x812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Lee',
    'Amy Tran',
    'Alyssa Baird',
    'Kayla Wagner',
    'Tyler Klein',
    'Michael Adkins',
    'James Williams',
    'Alicia Warner',
    'Yolanda Rice',
],
    'json': {
    'name': 'Joseph Walker',
    'address': '268 Ann Crescent Apt. 530\nLake Jonathanside, NC 39480',
},
    'key46923': 'value597',
    'key42942': 'value84392',
    'key2075': 'value64573',
    'key25473': 'value95913',
    'key22861': 'value41575',
    'key62917': 'value40123',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Timothy Johnson',
    'address': '25998 Mckenzie Ridge Suite 232\nSouth Tyler, NY 90878',
    'text': 'Figure try size against. Group probably question floor day ask ball task. High kitchen trouble toward who person.\nActivity change cost voice.',
    'email': 'mark76@example.com',
    'phone_number': '001-702-573-5908x342',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Armstrong',
    'Ashley Chase',
    'Steven Estes DDS',
    'Trevor Wright',
    'Paige Lane',
    'Corey Rivera',
    'Kevin Stanton',
    'Ronald Rogers',
],
    'json': {
    'name': 'Deanna Harrington',
    'address': '2181 Black Squares\nEast Joshua, CO 85882',
},
    'key74998': 'value10993',
    'key49888': 'value11191',
    'key48173': 'value48437',
    'key25622': 'value10290',
    'key54853': 'value10813',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Denise Jenkins',
    'address': '46081 Edward Pass\nWardshire, NM 84226',
    'text': 'On outside their business allow born receive. Tax on down entire message hour PM. Recognize walk follow film.\nStyle board now remain close mission. Wish nation feeling rate day.',
    'email': 'ffrost@example.com',
    'phone_number': '+1-965-327-1399',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Payne',
    'Heather Blake',
    'Kayla Morton',
    'Samuel Hobbs',
    'Heather Arnold',
    'Nicole Walsh',
    'Michael Murphy',
],
    'json': {
    'name': 'Heather Thompson',
    'address': '5349 Rodney Unions\nSouth Rachelland, WV 78128',
},
    'key95070': 'value27002',
    'key17613': 'value98007',
    'key96506': 'value64350',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Rebecca Burns',
    'address': '403 Webb Parkways\nEast Kristin, NM 79506',
    'text': 'Than end television parent. Soon yard vote election western process whole.\nImportant major season inside door. Year want growth statement well letter. Leg future exactly star one into.',
    'email': 'kendra52@example.net',
    'phone_number': '333.943.0934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Brooks',
    'Karen Villa',
    'Lee Burns',
],
    'json': {
    'name': 'Victoria Garner',
    'address': '21967 Donald Summit Apt. 980\nGuzmanbury, NM 83748',
},
    'key41290': 'value97474',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Mr. Arthur Green',
    'address': '3688 Parker Drive\nAtkinsport, WI 87151',
    'text': 'Side tell lose with. Whose stock perhaps behind. Defense serious sure population minute.\nAttack main deal society. Recently minute light break.',
    'email': 'jamesmclean@example.org',
    'phone_number': '+1-371-392-5708x990',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sonia Smith',
    'Scott Newton',
    'Luis Thomas IV',
    'Kimberly Marshall',
    'Alexander Johnson',
    'Shane Castillo',
],
    'json': {
    'name': 'Anthony Lewis',
    'address': '060 Walter Gardens Apt. 698\nNicoleport, PW 74130',
},
    'key14553': 'value91136',
    'key52641': 'value34226',
    'key70946': 'value97320',
    'key58025': 'value97556',
    'key88712': 'value65209',
    'key98138': 'value19120',
    'key13526': 'value78135',
    'key28123': 'value11603',
    'key77050': 'value20731',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Steven Parks',
    'address': '43951 Amy Greens Suite 958\nCarterview, MS 41366',
    'text': 'Similar more rule enough. Box thousand bring smile high we. Southern defense phone meet.',
    'email': 'emilyprice@example.net',
    'phone_number': '+1-224-401-1678x039',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Carter',
    'Matthew Bennett',
    'Jonathon Webb',
    'Paul Spencer',
    'Maria Juarez',
    'Christopher Perkins',
    'Cheryl Coffey',
    'Laurie Walker',
    'Angela Spence',
    'Rachael Jackson',
],
    'json': {
    'name': 'James Miller',
    'address': '49027 Hernandez Square\nEast Marissaton, MA 22768',
},
    'key79507': 'value16592',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Natasha Mccall',
    'address': '4215 Melanie Port\nSouth Casey, VI 33239',
    'text': 'Church four near nation process speech. Time age admit money food life visit. Movement know opportunity him.',
    'email': 'heather93@example.net',
    'phone_number': '621-411-2396x29537',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Miller',
    'Amy Vasquez',
    'Keith Mcmillan',
    'Ryan Meyer DVM',
],
    'json': {
    'name': 'Nicolas Bradford',
    'address': '8773 Billy Road\nWest Juan, CO 94452',
},
    'key4283': 'value79613',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'John Sexton',
    'address': '77379 Sean Street Apt. 807\nWillieland, HI 54131',
    'text': 'Cell better coach thus add black. Design half born side during high.\nProfessor important scene describe score agreement more. Girl manage also institution play. Truth economy wind food.',
    'email': 'scarter@example.net',
    'phone_number': '+1-634-980-7192x6704',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stefanie Landry',
    'Joseph Clayton',
    'Troy West',
    'Gregory Hurst',
],
    'json': {
    'name': 'Christine Morrison',
    'address': '66170 Jody Heights\nDanielborough, DC 40419',
},
    'key92232': 'value75605',
    'key8293': 'value40014',
    'key59874': 'value21792',
    'key13943': 'value77676',
    'key44173': 'value44626',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Joanna Castillo',
    'address': 'PSC 0693, Box 3265\nAPO AE 19826',
    'text': 'Teacher book address education forward. Plant begin garden necessary.',
    'email': 'jennifer04@example.net',
    'phone_number': '(550)738-7407x726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Stanley',
],
    'json': {
    'name': 'Rebecca Hall',
    'address': 'PSC 4658, Box 9396\nAPO AA 65195',
},
    'key49709': 'value2821',
    'key14607': 'value55352',
    'key91995': 'value92342',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Leah Chan',
    'address': '3029 Fernandez Mountain\nMarcmouth, UT 34673',
    'text': 'Sister hotel any industry back. Future choose onto sit join. Despite risk true water imagine service.',
    'email': 'codymendoza@example.org',
    'phone_number': '898-385-0190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Guerra',
],
    'json': {
    'name': 'Kristine Wood',
    'address': '705 Ball Center\nWest Katrina, DC 43673',
},
    'key43665': 'value23931',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Savannah Hodges',
    'address': '704 Jamie Trail Suite 930\nPort Katherineview, AR 62154',
    'text': 'In policy this free old after much. Wall show would community top final another.\nScience company through. Defense station easy despite dinner lead. Amount catch month travel rather east sell girl.',
    'email': 'william58@example.com',
    'phone_number': '473.778.8885x371',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Manning',
    'John Richards',
    'Charles Smith',
    'Mrs. Lydia Hayes',
    'Pamela Lee',
    'Nicole Gonzalez',
    'John Meyer',
    'Evelyn Rivera',
],
    'json': {
    'name': 'Stephanie Williams',
    'address': '115 Brian Loaf\nLake Evanport, UT 68610',
},
    'key73315': 'value43563',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Judith Ortega',
    'address': '672 Chavez Knolls\nEast Juan, MS 90904',
    'text': 'Summer know particularly natural role man. Blood sport line Republican. Such executive administration rather development.',
    'email': 'qgibson@example.com',
    'phone_number': '001-507-267-3557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Chad Ibarra',
    'Paul Cook',
    'Mr. Christopher Delacruz',
    'Jason Williams',
    'Julie Wood',
    'Renee Lewis',
    'Jack Lewis',
    'Timothy Taylor',
],
    'json': {
    'name': 'Jasmine Walker',
    'address': '85168 Bennett Cliff Apt. 547\nLake Lindsay, MH 34349',
},
    'key66150': 'value78173',
    'key48550': 'value53802',
    'key10877': 'value53102',
    'key52599': 'value29181',
    'key46983': 'value30307',
    'key24130': 'value21840',
    'key58318': 'value15491',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Cory Shannon',
    'address': '491 Heidi Unions\nJohnsonville, PR 36760',
    'text': 'According word approach center be degree type. Item meeting site best rather executive important.\nConsider land visit they attention government anything job. Section most culture firm group his.',
    'email': 'lmcdonald@example.org',
    'phone_number': '+1-280-723-9986',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jason Jensen',
    'Edward Long',
    'Alfred Joseph',
    'Kristie Kelley',
    'Corey Medina',
],
    'json': {
    'name': 'Martin Lopez',
    'address': '963 Erin Harbors\nHerringmouth, AZ 38945',
},
    'key56460': 'value64789',
    'key54582': 'value83574',
    'key84887': 'value94394',
    'key32605': 'value66770',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Sharon Ramirez',
    'address': 'PSC 4483, Box 5051\nAPO AE 63537',
    'text': 'Option have citizen final possible age west. Able music leave enjoy act possible involve. Nation real easy tough hot miss purpose part.',
    'email': 'wwright@example.com',
    'phone_number': '(717)387-2752x538',
    'array_int_dynamic': [
    53717,
],
    'array_varchar_dynamic': [
    'Stephanie Miller',
    'Misty Sullivan',
    'Tyler Daugherty',
    'Justin Moody',
    'Gina Andrade',
    'Jacob Daugherty',
    'Brian Herrera',
    'Bryce Parker',
],
    'json': {
    'name': 'Wesley Watkins',
    'address': 'USS Farley\nFPO AP 90391',
},
    'key66642': 'value73606',
    'key1772': 'value58988',
    'key96608': 'value77905',
    'key62522': 'value79877',
    'key17333': 'value21612',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Maurice Edwards',
    'address': '11903 Rodriguez Pines Apt. 953\nCharlesberg, SD 55457',
    'text': 'This difference beat career later so. Test again site.\nMovement protect strong traditional peace key nothing. Hair serve player today.',
    'email': 'ujackson@example.com',
    'phone_number': '001-739-322-4420',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Sherman',
    'Stacey Scott',
    'Taylor Hernandez',
    'Joseph Campos',
    'Roy Church',
    'William Crosby',
],
    'json': {
    'name': 'Joanna Miller',
    'address': '53184 Shane Mission Apt. 441\nNew Kristina, OK 45312',
},
    'key91691': 'value88641',
    'key82860': 'value68495',
    'key68186': 'value82733',
    'key78432': 'value17822',
    'key1676': 'value9193',
    'key37135': 'value70519',
    'key12183': 'value84562',
    'key3345': 'value54532',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Brad King',
    'address': '54131 Kevin River\nAmbermouth, KY 38422',
    'text': 'Build event every job.\nStage write defense west check. Perform leg technology experience tend mission.\nOften customer position tough draw health nation.',
    'email': 'dhoward@example.net',
    'phone_number': '+1-303-645-1047',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amber Walton',
],
    'json': {
    'name': 'Natalie Bartlett',
    'address': '05518 Tiffany Street\nWest Stevenmouth, NJ 45177',
},
    'key21848': 'value65683',
    'key50511': 'value43510',
    'key82894': 'value69106',
    'key78926': 'value65831',
    'key16348': 'value95064',
    'key76820': 'value48088',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Bruce Mcconnell',
    'address': '666 Miller Circle Suite 642\nLake Jasonstad, NH 07415',
    'text': 'Sister together mean exactly fill if. Season either believe still provide.\nResearch real visit place answer drug time. Picture family letter.',
    'email': 'bryanrichardson@example.net',
    'phone_number': '001-715-485-5254x0985',
    'array_int_dynamic': [
    59120,
],
    'array_varchar_dynamic': [
    'Jonathan Black',
    'Ricky Smith',
    'Jessica Olson',
    'Whitney Stewart',
    'Jeffrey Chambers',
],
    'json': {
    'name': 'Charles Gray',
    'address': '70219 Nelson Cove Suite 975\nPort Cameron, NM 61647',
},
    'key6570': 'value87287',
    'key45507': 'value99214',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Kristen Hart',
    'address': 'Unit 8613 Box 3036\nDPO AP 04315',
    'text': 'Along this three century great fast station.\nLong him traditional training work protect consumer. Cut training especially senior hold improve.',
    'email': 'emartin@example.org',
    'phone_number': '001-522-769-5261x9226',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Todd Lopez',
    'Edward Diaz',
    'Barbara Parker',
    'Benjamin Austin',
    'Deborah Levine',
    'Elizabeth Mcneil',
],
    'json': {
    'name': 'Mary Freeman',
    'address': 'PSC 9766, Box 3507\nAPO AE 66975',
},
    'key3507': 'value96239',
    'key21461': 'value57607',
    'key87765': 'value58556',
    'key47275': 'value8357',
    'key14926': 'value2921',
    'key81436': 'value38128',
    'key1179': 'value49786',
    'key21359': 'value70351',
    'key42949': 'value96162',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Michael Vega',
    'address': '7886 Kenneth Isle\nJenniferberg, AS 68524',
    'text': 'Boy rich finally institution modern. With mission east job writer whom. Discussion big middle those natural.\nFire across song five similar benefit.\nCup hand media change he bring window.',
    'email': 'dwayne56@example.net',
    'phone_number': '302-976-9945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Velasquez',
    'Ronald Day',
    'Stacey Poole',
],
    'json': {
    'name': 'Cassandra Dean',
    'address': '238 Miller Points Suite 935\nSouth Timothy, DC 48356',
},
    'key44639': 'value47003',
    'key56903': 'value82745',
    'key5748': 'value30616',
    'key7719': 'value47304',
    'key87944': 'value66275',
    'key84929': 'value74788',
    'key18911': 'value7641',
    'key78985': 'value22451',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Eric Swanson',
    'address': '9096 Ronald Square\nEast Ashley, SC 74160',
    'text': 'Forget study factor issue also skin. Say sister also would investment follow local newspaper.\nAppear cell drop save. Since condition whose mouth. Since themselves culture politics off.',
    'email': 'ryan53@example.org',
    'phone_number': '573.447.7265',
    'array_int_dynamic': [
    51843,
],
    'array_varchar_dynamic': [
    'Crystal Salazar',
    'Derrick Smith',
    'Christopher Aguirre',
    'Angela Hawkins',
    'Heather Henderson',
    'Mr. John Nicholson',
    'Melissa Rose',
    'Nicole Henderson',
],
    'json': {
    'name': 'Melissa Mcgee',
    'address': '9429 Christopher Knoll\nPadillaberg, NV 51447',
},
    'key60863': 'value43694',
    'key29160': 'value36702',
    'key97380': 'value156',
    'key3223': 'value8428',
    'key85351': 'value13551',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Megan Stewart',
    'address': 'PSC 3159, Box 8050\nAPO AP 22405',
    'text': 'Particular along run item. Carry others maintain light floor point. Most language board few. While off industry civil painting.\nFear tax grow than less time. Serve few will event.',
    'email': 'parkergabriel@example.com',
    'phone_number': '459.510.6455',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Rowland',
    'Sarah Dunlap',
    'Laurie Howard',
    'Brandy Hurley',
],
    'json': {
    'name': 'Sara Johnson',
    'address': '175 Douglas Lakes Apt. 304\nAshleymouth, AZ 37520',
},
    'key11986': 'value39633',
    'key9211': 'value60055',
    'key88466': 'value91795',
    'key8729': 'value50636',
    'key30548': 'value375',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Scott Collins',
    'address': '799 Williams Road\nLoganborough, TN 35431',
    'text': 'One dark glass political the certain full. Mother actually involve we mind since.\nChild evidence me evidence. Move early part structure need floor hair set.',
    'email': 'yhenry@example.org',
    'phone_number': '+1-463-628-6140x522',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kristi George',
    'Vicki Williams',
    'Lawrence Lee',
    'Jennifer Santiago',
    'Sherry Brandt',
    'Patrick Richmond',
],
    'json': {
    'name': 'Jessica Price',
    'address': '434 Murray Park\nPort Amberside, NY 06797',
},
    'key49409': 'value29495',
    'key1639': 'value43757',
    'key3273': 'value63570',
    'key23353': 'value84418',
    'key95646': 'value87079',
    'key47864': 'value27180',
    'key49394': 'value98042',
    'key80132': 'value18702',
    'key13282': 'value93432',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Katrina Flores',
    'address': '2537 Graham Mountain\nPetersonberg, WV 90703',
    'text': 'Future north lay condition bring camera nearly. Hand lay southern time machine product.\nBar fear kitchen take space word even. Opportunity sign side itself nearly shoulder.',
    'email': 'staylor@example.net',
    'phone_number': '6143987784',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Matthews',
    'Sarah Gonzalez',
    'Beverly Rosario',
    'Robert Juarez',
    'Eric Green',
],
    'json': {
    'name': 'Michele Walker',
    'address': '89046 Zachary Port Suite 390\nSouth Lori, CO 77737',
},
    'key25033': 'value39731',
    'key91325': 'value95288',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Monica Mejia',
    'address': '37209 Rivera Garden Suite 468\nNorth Alyssa, KY 76544',
    'text': 'Near thought state test. Inside military media behavior. Push run group high but before.',
    'email': 'kristenjohnston@example.net',
    'phone_number': '+1-725-885-7336x211',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amy Walker',
    'Michael Lopez',
    'Matthew Gill',
    'Kyle Adams',
    'Bryan Jones',
    'Jose Ballard',
    'Stacey Perry',
    'Lisa Smith',
    'Frank Lopez',
],
    'json': {
    'name': 'Sean Lopez',
    'address': '61480 Teresa Extension Apt. 328\nThomasland, NY 08272',
},
    'key57939': 'value22203',
    'key22607': 'value31237',
    'key26920': 'value18525',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Lauren Newton DDS',
    'address': 'USNV Fisher\nFPO AP 65529',
    'text': 'Your nation group meeting. Attorney score material real experience yeah.\nFriend change condition suggest agree. Political under food new official its.',
    'email': 'lchapman@example.net',
    'phone_number': '(635)985-7285',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Donna Douglas',
    'Susan Whitney',
    'Bridget Freeman',
    'Brandon Thompson',
    'Karen Kline',
    'Jason Bradley',
    'Anita Evans',
    'Michele Taylor',
    'Sarah Collier',
    'Troy Hamilton',
],
    'json': {
    'name': 'Krystal Flowers',
    'address': '458 Davis Island\nEast Janestad, DC 16653',
},
    'key17521': 'value36545',
    'key96593': 'value40305',
    'key12217': 'value55260',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Crystal Bates',
    'address': '13534 Johnson Canyon Apt. 261\nLake Kent, PR 91590',
    'text': 'Serious trouble society full. Next effort inside thousand.\nTrip indicate about stock. Herself war yourself rest bit.\nSome wish realize operation fast art affect young. Minute play up.',
    'email': 'greenkristen@example.net',
    'phone_number': '579.271.7852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Smith',
    'Denise French',
    'Aaron Thomas',
],
    'json': {
    'name': 'Amy Hood',
    'address': 'USNS Berger\nFPO AA 60380',
},
    'key78387': 'value85444',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Thomas Hamilton',
    'address': '90756 Flores Extensions\nEast Courtney, PW 46511',
    'text': 'Third that determine prepare paper. Light employee like manage class same interesting value. Majority eat local hour.\nGrowth music worry single. Like bad score while imagine.',
    'email': 'aaguirre@example.net',
    'phone_number': '475.736.7787x87473',
    'array_int_dynamic': [
    55606,
],
    'array_varchar_dynamic': [
    'Timothy Gomez MD',
],
    'json': {
    'name': 'Eric Cox',
    'address': '21978 Raymond Road\nEast Michaelmouth, MN 97245',
},
    'key66407': 'value10143',
    'key46287': 'value76780',
    'key98788': 'value74949',
    'key82613': 'value70294',
    'key81060': 'value94888',
    'key65872': 'value39954',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Robert Jackson',
    'address': '295 Louis Freeway Suite 303\nEast Rachelburgh, AZ 89489',
    'text': 'New election boy safe. Likely still method society science. Positive enough list such action form both model. Environmental about less test drug.\nAny system face book. Leg author consider.',
    'email': 'williamnoble@example.org',
    'phone_number': '001-448-746-4472x522',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Diaz',
    'Roberta Mayer',
    'Claudia Gomez',
    'Taylor Leonard',
    'Carol Phillips',
    'Dana Kaufman',
    'Katherine Hall',
    'Denise Pham',
    'Jeremy Hawkins',
    'Adam Smith',
],
    'json': {
    'name': 'Ann Harrison',
    'address': '5840 Carlson Rapid\nChristopherville, CA 21266',
},
    'key84268': 'value54569',
    'key7137': 'value59358',
    'key62867': 'value89017',
    'key75804': 'value30689',
    'key57818': 'value77073',
    'key84725': 'value37777',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Mitchell Washington',
    'address': '714 Steve Dale\nNorth Sydneychester, DE 13045',
    'text': 'Instead have save compare. Question story pull her then center. Participant after sometimes two trade between.\nUpon notice often front or sound. Difference artist itself pretty. Face agent ago body.',
    'email': 'danielpayne@example.com',
    'phone_number': '606-776-6859x98364',
    'array_int_dynamic': [
    87898,
],
    'array_varchar_dynamic': [
    'Andrew Fisher',
    'Ryan Sullivan',
    'Douglas Anderson',
],
    'json': {
    'name': 'Kaylee Bishop',
    'address': '3764 Chung Plains\nStephanieland, TN 72093',
},
    'key5737': 'value76668',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Justin Norton',
    'address': '097 Kyle Squares\nPort Robertmouth, ND 44023',
    'text': 'Find American bag alone garden heavy claim thank.\nRest between tend run goal week growth. Item phone just party art than summer. Second base blue policy than democratic born.',
    'email': 'cathyschroeder@example.net',
    'phone_number': '001-310-367-5927',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Harris',
],
    'json': {
    'name': 'Justin Vazquez',
    'address': 'USS Jackson\nFPO AA 63420',
},
    'key63679': 'value41380',
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
    'RequestId': 'b45615fd-62ef-11f0-bfce-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_30_073061wOpNnPKz',
    'dimension': 128,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-1]_1752744211.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl12810011752744211Json()
    test.run_tests()
