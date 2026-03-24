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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-2]_1752744159_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-2]_1752744159.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId3210021752744159Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-2]_1752744159.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-2]_1752744159.json"
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
    'RequestId': '9598d621-62ef-11f0-8a6e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_38_501153ONZaZzUv',
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
    'RequestId': '95b98660-62ef-11f0-bd5f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_38_501153ONZaZzUv',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Hannah Farley',
    'address': '124 Jared Ferry\nLake Jamesland, NY 95160',
    'text': 'Myself expert move occur. Success hundred wall late game.\nParticularly plant become. Will about figure put per.',
    'email': 'walkertammy@example.org',
    'phone_number': '001-533-476-8128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'April Ellis',
    'Emma Wiggins',
    'Dr. Alyssa Sherman',
    'Kevin Martin',
    'Heather Oneill',
],
    'json': {
    'name': 'Nathaniel Taylor',
    'address': '19299 Larry Points Apt. 855\nScottbury, SD 03673',
},
    'key82250': 'value11775',
    'key22288': 'value66945',
    'key88154': 'value19328',
    'key48940': 'value49037',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Caitlyn Mcdonald',
    'address': '628 Harris Flat\nPort Ruth, TX 86888',
    'text': 'Phone money little community evidence. Card magazine baby husband story. While agree success whole office performance. Always million direction executive final.',
    'email': 'marycox@example.net',
    'phone_number': '(766)337-9128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Miguel Bryant',
    'Joseph Colon',
    'Sophia Benjamin',
    'Lindsay Patterson',
],
    'json': {
    'name': 'Helen Smith',
    'address': '7294 Black Drives\nNicoleburgh, WA 22466',
},
    'key2031': 'value29704',
    'key26545': 'value87238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Thomas Harrison',
    'address': '917 Carl Dale\nDonaldhaven, OH 83963',
    'text': 'Catch ask woman color message common entire stand. Like human wrong seek senior history.\nAvoid future week cell address far. Direction peace may the. Finally community effort he.',
    'email': 'usantos@example.net',
    'phone_number': '794-824-8225',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Megan Wise MD',
    'Anthony Scott',
    'Michele Patton',
    'Joshua Reese',
    'Morgan Johnson',
    'Bobby Davis',
    'William Grant',
    'Priscilla Padilla',
    'Billy Le',
],
    'json': {
    'name': 'Jennifer Hester',
    'address': '063 David Via\nEast Ashleyshire, MI 01066',
},
    'key14497': 'value42919',
    'key80004': 'value62055',
    'key16844': 'value26532',
    'key74442': 'value94526',
    'key1515': 'value77010',
    'key20933': 'value10265',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Nicholas Phillips',
    'address': 'PSC 1192, Box 0608\nAPO AE 91054',
    'text': 'Political run spring establish. Anyone their security poor middle. Support prevent quality goal.\nDescribe federal turn word worry. Hot success whom.\nPeople stuff vote realize business.',
    'email': 'claudia83@example.net',
    'phone_number': '508.843.5754x228',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jaime Phillips',
    'Anthony Ramsey',
    'Jonathan Dougherty',
],
    'json': {
    'name': 'Billy Hernandez',
    'address': '4091 Gregory Valleys Apt. 741\nGeorgemouth, OH 66445',
},
    'key44338': 'value28775',
    'key50426': 'value47959',
    'key79144': 'value11638',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Alexander Johnson',
    'address': '04449 William Drives\nLake Leslie, FL 27482',
    'text': 'Since worker everybody when.\nAllow side go firm focus. Him white maybe cultural.\nPolitical speak door. You try kind line.',
    'email': 'gonzalezdaniel@example.com',
    'phone_number': '675.662.9756x81578',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Frank Johnson',
    'Amanda Marshall',
    'Laura Moore',
    'Rachel Gentry',
    'Alexis Harris',
],
    'json': {
    'name': 'Brett Peterson',
    'address': '427 Anderson Well Suite 362\nLake Mary, UT 05154',
},
    'key18659': 'value9599',
    'key82122': 'value53785',
    'key33252': 'value24306',
    'key93690': 'value65548',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Aaron Carney',
    'address': '8636 Short Mission\nAlexisburgh, PR 48750',
    'text': 'Character new individual fall seem data teach. While report respond course remain news without.\nFamily sort street far up. Choice simple his left style security.\nQuickly half yes time run politics.',
    'email': 'shelleymcintyre@example.net',
    'phone_number': '(737)626-1563',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Bullock',
    'James Fuller',
    'Tara Cordova',
    'Jessica Cabrera',
    'Ryan Delacruz Jr.',
    'Stephanie Yates',
],
    'json': {
    'name': 'Justin Wilkerson',
    'address': '756 Alan Causeway Suite 320\nNorth Mark, FM 65519',
},
    'key19848': 'value25685',
    'key6337': 'value58463',
    'key3729': 'value85216',
    'key94665': 'value99719',
    'key75637': 'value1212',
    'key29313': 'value63878',
    'key37794': 'value50037',
    'key74797': 'value6200',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Taylor Weaver',
    'address': '449 David Port Apt. 281\nNew Marybury, AS 56160',
    'text': 'Likely standard expert get simply involve. A security weight water. City laugh new government respond join hand.\nListen camera century event property lot road. Treat end up push dinner least call.',
    'email': 'aaron77@example.org',
    'phone_number': '200.275.6374x6734',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'John Robinson',
    'Kelly Fitzgerald',
],
    'json': {
    'name': 'Jasmine Hogan',
    'address': '4182 Jerome Land Suite 706\nDonaldchester, RI 87798',
},
    'key47995': 'value38206',
    'key79552': 'value31563',
    'key47637': 'value63398',
    'key5265': 'value74334',
    'key32925': 'value25201',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'David Sutton',
    'address': '478 Castillo Village\nSouth Jennifer, AR 72119',
    'text': 'West physical time message enter attorney. Pay watch sure you husband animal effort. Far work land continue option.',
    'email': 'brownoscar@example.com',
    'phone_number': '518.478.4741',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Payne',
    'Connie Murphy',
    'Margaret Johnson',
    'Justin Green',
    'Heather Butler',
    'Nicholas Edwards',
],
    'json': {
    'name': 'Norman Hodges',
    'address': 'PSC 5688, Box 1992\nAPO AP 89388',
},
    'key16567': 'value25850',
    'key43884': 'value49983',
    'key56780': 'value60667',
    'key92118': 'value90094',
    'key70043': 'value77471',
    'key74418': 'value23852',
    'key36183': 'value41754',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Gabriel Ramirez',
    'address': '9449 Wyatt Ridge Apt. 096\nMatthewland, GU 51476',
    'text': 'Question spring sit.\nAdult teach determine situation. Camera my person his can ball of American. Significant court trouble.',
    'email': 'qmiller@example.org',
    'phone_number': '(459)463-8986',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Rivas',
],
    'json': {
    'name': 'Jerry Wade',
    'address': '13313 Moreno Common Apt. 747\nKennethville, OR 19304',
},
    'key41281': 'value53331',
    'key98829': 'value45844',
    'key59803': 'value87980',
    'key55358': 'value96907',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Donna Butler',
    'address': '9710 Jonathan Brooks Apt. 253\nEvanview, AL 82185',
    'text': 'Throw total serious color federal move these positive. Thus seat chance along history change stay.\nClaim room great know short plan record value. Your office above agreement reveal too main.',
    'email': 'kevinvalenzuela@example.net',
    'phone_number': '905.877.3329',
    'array_int_dynamic': [
    3337,
],
    'array_varchar_dynamic': [
    'Jonathan Silva',
    'Alexis Miranda',
    'Nicholas Robertson',
    'Samantha Baldwin',
],
    'json': {
    'name': 'Daniel Fleming',
    'address': '259 Simmons Isle\nRodriguezview, ME 74052',
},
    'key68705': 'value95676',
    'key56156': 'value44401',
    'key30972': 'value56110',
    'key82746': 'value67664',
    'key53519': 'value86982',
    'key96782': 'value81338',
    'key10190': 'value20076',
    'key9367': 'value30414',
    'key26665': 'value1985',
    'key18063': 'value2790',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Melissa Gardner',
    'address': '017 Weeks Canyon Apt. 412\nNorth Karenstad, FL 36069',
    'text': 'Race home offer against red outside official. Current cultural sure likely.\nMessage age remember also never feel ahead image. Sport level nothing term current pretty.',
    'email': 'yarmstrong@example.com',
    'phone_number': '(325)674-1306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Peterson',
    'Benjamin Willis',
    'Ms. Ashley Robertson',
    'Tina Lewis',
    'Autumn Rice',
    'Jessica Lopez',
    'Mrs. Jacqueline Cunningham',
    'William Nguyen',
],
    'json': {
    'name': 'Timothy Keller',
    'address': 'USS Baker\nFPO AA 94012',
},
    'key5084': 'value40206',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Courtney Ward',
    'address': '583 Christine Bypass\nEscobarburgh, PW 08134',
    'text': 'Director edge seek believe heart total serious. Who night parent set deep while. Good as explain wonder.',
    'email': 'lisamorgan@example.net',
    'phone_number': '(724)773-2740x1611',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Yang',
    'Kristine Martinez',
    'Samuel Bishop',
    'Brenda Burns',
    'Kimberly Warner',
    'Jesse Becker',
    'Yvonne Smith',
    'Mr. Mark Woods III',
    'Lisa Kane',
],
    'json': {
    'name': 'Whitney Green',
    'address': '3336 King Via Apt. 821\nNorth Maria, AL 09381',
},
    'key35850': 'value36707',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Mr. Donald Turner',
    'address': '39861 Robert Crossroad Suite 167\nWest Alex, NJ 20144',
    'text': 'So president hear production project hope behavior. Activity democratic throw since spend learn mother. Put step argue south especially option night.',
    'email': 'catherine09@example.org',
    'phone_number': '443.836.7192x17542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Mckay',
    'Mr. Tony Vasquez',
],
    'json': {
    'name': 'Joshua Ortega',
    'address': '5899 Joseph Ford Apt. 105\nNorth Nicolehaven, MA 06956',
},
    'key82470': 'value39531',
    'key19041': 'value33246',
    'key54072': 'value42492',
    'key97386': 'value16075',
    'key43716': 'value59486',
    'key77739': 'value72145',
    'key58294': 'value5556',
    'key40419': 'value55946',
    'key28966': 'value89486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Sandra Carney',
    'address': '85619 Troy Trace\nLarryton, VA 33686',
    'text': 'Get miss deal military national. I year thing drive keep could interest. Task whole sometimes establish little time increase major.',
    'email': 'tammyharvey@example.org',
    'phone_number': '8839062304',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stacey Campbell',
    'Joseph Howard',
    'Melinda Savage',
    'Kristie Butler',
    'John Potts',
    'Dawn Anderson',
    'Julie Marshall',
],
    'json': {
    'name': 'Maria Harris',
    'address': '82482 Baker Trace\nPettyburgh, NC 71709',
},
    'key32490': 'value15603',
    'key52459': 'value75294',
    'key2732': 'value68243',
    'key7286': 'value49385',
    'key76771': 'value57027',
    'key19109': 'value29044',
    'key22266': 'value80701',
    'key39860': 'value6156',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Lori Hall',
    'address': '6918 Michael Mountains Apt. 949\nNorth Arthurfurt, IN 28250',
    'text': 'Condition focus recent street approach. Tonight lead perform see spend remember. Get practice make dream two very.\nLevel man feeling visit leg activity total. Stuff else offer that large.',
    'email': 'stephanieramos@example.org',
    'phone_number': '+1-776-371-1486x0285',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Davenport',
    'Mark Irwin',
    'Tom Finley',
    'Amanda Flynn',
    'Paul Chaney',
    'Christina Alexander',
    'Cynthia Lee',
    'Courtney Kline',
    'Peter Stevens',
],
    'json': {
    'name': 'Shannon Matthews',
    'address': '45698 Brown Court Apt. 847\nLisamouth, NJ 36480',
},
    'key10017': 'value45006',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Mr. Scott Berger PhD',
    'address': '42060 Aaron Streets\nRaymondstad, OR 84646',
    'text': 'Media avoid traditional activity base tell. Sister first want concern so action. Young truth must develop word base.',
    'email': 'richardmann@example.com',
    'phone_number': '(996)230-2516',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Stevenson',
    'Jessica Robinson',
    'Benjamin Jackson',
    'Margaret Klein',
    'Stephanie English',
],
    'json': {
    'name': 'David Smith',
    'address': '54966 Martinez Ridges\nSarahchester, VT 24239',
},
    'key50363': 'value95102',
    'key69967': 'value60113',
    'key27932': 'value57322',
    'key12151': 'value65895',
    'key14638': 'value41525',
    'key11897': 'value16284',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Cynthia James',
    'address': '89436 Smith Roads Suite 684\nWest Richardmouth, IL 70526',
    'text': 'Would three cell much reveal. Person necessary image owner. Current I time you on product.\nProduct second old agent see. Capital off size past respond help since.',
    'email': 'schmidtrobert@example.com',
    'phone_number': '446.359.4807',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sara Williams',
    'Anna Potts',
    'Ryan Williams',
    'Jonathon Camacho',
    'Thomas Mack',
],
    'json': {
    'name': 'Christine Williams',
    'address': '61308 Graham Stravenue Suite 707\nMichaelhaven, MP 85181',
},
    'key16422': 'value61819',
    'key29239': 'value64618',
    'key59600': 'value967',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Nina Bryan',
    'address': '820 Chen Expressway Apt. 957\nPort Thomas, NE 40065',
    'text': 'Man answer business thank beautiful star field collection. Town behavior three cut either camera. Them phone station claim resource knowledge.',
    'email': 'churchmichael@example.net',
    'phone_number': '+1-253-624-8604',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Johnson',
    'Justin Decker',
    'Monica Stephens',
    'Tanya Fitzgerald',
],
    'json': {
    'name': 'Frances Lindsey',
    'address': '639 Molly Lake Suite 912\nRichardfurt, PA 30391',
},
    'key19923': 'value10536',
    'key25198': 'value92131',
    'key30169': 'value1029',
    'key9457': 'value46337',
    'key97246': 'value91709',
    'key54778': 'value20435',
    'key97426': 'value32339',
    'key30442': 'value75702',
    'key48557': 'value78693',
    'key84617': 'value93665',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Justin Avery',
    'address': '05625 Jenna Wells Suite 484\nNew Davidmouth, DE 44106',
    'text': 'Simple foreign position. Anything pay most research knowledge great crime throw. Organization possible at especially rest.',
    'email': 'marksdanielle@example.com',
    'phone_number': '+1-271-934-9503x96401',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Webb',
    'James Dickson',
    'Christina Harper',
],
    'json': {
    'name': 'Christine Smith',
    'address': '33550 Daniel Drive\nVincentberg, MA 20633',
},
    'key93767': 'value55775',
    'key57421': 'value49511',
    'key25353': 'value51648',
    'key6448': 'value45044',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Brittany May',
    'address': 'PSC 3107, Box 9223\nAPO AE 45892',
    'text': 'Fish question policy fire certain ok rise. Land three spend medical single offer. The know sing others yourself remember perform.',
    'email': 'sarahhensley@example.org',
    'phone_number': '836-835-4547x62249',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Hogan',
    'Maurice Flores',
    'Sandra Moss',
    'Cory Jenkins',
    'Michael Meadows',
    'Spencer Smith',
    'Patricia Moore',
    'Cheryl Moore',
],
    'json': {
    'name': 'James Jones',
    'address': '0655 Meyer Dale Apt. 528\nHarrisontown, ND 47463',
},
    'key91478': 'value66931',
    'key10019': 'value59612',
    'key73237': 'value28325',
    'key58383': 'value88400',
    'key57886': 'value71602',
    'key74338': 'value2637',
    'key58351': 'value22748',
    'key54041': 'value8181',
    'key4717': 'value36607',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Lauren Aguilar',
    'address': '562 Norman Inlet\nChelseaport, CO 60216',
    'text': 'Environmental life close cup school experience when position. Ago history sound yet create space. Last top follow get.\nTwo television sport effort relate. Eight anyone any to wide college theory.',
    'email': 'john05@example.net',
    'phone_number': '001-455-638-5848',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Scott Saunders',
    'Terry Hernandez',
],
    'json': {
    'name': 'Samuel Bennett',
    'address': '85263 Samuel Road Suite 107\nWest Elizabethville, AZ 94568',
},
    'key15719': 'value61673',
    'key55351': 'value8155',
    'key51213': 'value58554',
    'key37876': 'value88658',
    'key55147': 'value96903',
    'key44837': 'value79043',
    'key58358': 'value9465',
    'key55171': 'value88919',
    'key1983': 'value65541',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Karen Kim',
    'address': 'PSC 7166, Box 8556\nAPO AE 21643',
    'text': 'True material care which its force more whatever.\nChoose instead benefit television water south. Including movement market more age life remain.',
    'email': 'johnstoncarly@example.com',
    'phone_number': '324-268-8829',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'John Shepard',
],
    'json': {
    'name': 'Crystal Evans',
    'address': '1382 Lopez Route\nMichaelfurt, SC 39669',
},
    'key80437': 'value20290',
    'key81589': 'value80157',
    'key82591': 'value87221',
    'key7230': 'value67138',
    'key50268': 'value27757',
    'key33552': 'value86672',
    'key26004': 'value64801',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Jennifer Blankenship',
    'address': '1740 Hunt Stravenue\nNorth Richardstad, MO 85064',
    'text': 'Need industry skill whose. Question safe result candidate. Right business reveal although.',
    'email': 'melissaboone@example.org',
    'phone_number': '+1-235-778-4638x227',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Schneider',
    'Raymond Gibbs',
    'Crystal Torres MD',
    'Mr. Joseph Chambers',
    'David Perez',
    'Amber Yoder',
    'Toni Campbell',
    'Joshua Griffin',
    'Leonard Moore',
    'Craig Kim',
],
    'json': {
    'name': 'Jack Swanson',
    'address': '6423 Elizabeth Park\nAshleystad, GA 59785',
},
    'key3024': 'value96476',
    'key53933': 'value12603',
    'key5837': 'value12958',
    'key54847': 'value56856',
    'key1499': 'value4086',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Timothy Brown',
    'address': '7742 Meadows Street\nCarriefort, MO 32925',
    'text': 'Commercial away town three nice that history.\nExecutive first lot position decade wide loss. Camera sure tend according politics.',
    'email': 'gwendolyn53@example.com',
    'phone_number': '483-872-3551',
    'array_int_dynamic': [
    20970,
],
    'array_varchar_dynamic': [
    'Steven Allen',
    'Mary Moran',
    'Jeffrey Bender',
],
    'json': {
    'name': 'Erica Delgado',
    'address': '451 Carpenter Village\nBowmanchester, WA 21361',
},
    'key29486': 'value60772',
    'key87181': 'value77735',
    'key72335': 'value95100',
    'key55225': 'value70534',
    'key37588': 'value64645',
    'key95170': 'value84653',
    'key40898': 'value74052',
    'key80806': 'value34395',
    'key60786': 'value7943',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Andrea Martin',
    'address': 'PSC 7419, Box 5176\nAPO AP 88015',
    'text': 'Trade citizen item worker none. Part mission line she recognize possible age. Just factor bit cover record.\nAlong best human. Environmental explain question past leader figure.',
    'email': 'michelle87@example.org',
    'phone_number': '656-565-2864',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Campbell DVM',
    'Jose Molina PhD',
    'Kyle Huffman IV',
    'Tami Scott',
],
    'json': {
    'name': 'Nathaniel Bonilla',
    'address': 'Unit 5157 Box 1379\nDPO AP 25997',
},
    'key92851': 'value79476',
    'key68057': 'value44119',
    'key83289': 'value51190',
    'key53460': 'value29766',
    'key27224': 'value32308',
    'key2398': 'value1077',
    'key90253': 'value87193',
    'key3309': 'value43563',
    'key31852': 'value76210',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Erik Rodriguez',
    'address': '2326 Reeves View Apt. 704\nLake Christopherland, PW 87752',
    'text': 'Tonight oil respond color. Leg cell threat son consider blood general. Street both field high ability.\nLive data stage detail officer music new.',
    'email': 'nicholas89@example.net',
    'phone_number': '+1-897-397-5725x0102',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Esparza',
    'Gregory Wu',
    'Susan Harrison',
    'Charles Wright',
    'Stephanie Porter',
    'Jessica Wallace',
    'Bruce Moreno',
    'Michelle Monroe',
    'Eric Hancock',
],
    'json': {
    'name': 'Wesley Irwin',
    'address': '133 Julie Land Apt. 088\nBullockview, FM 62168',
},
    'key50762': 'value79506',
    'key42849': 'value46510',
    'key70370': 'value19855',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Brian Rowland',
    'address': '2658 Janice Corners\nHallchester, NH 95190',
    'text': 'Night herself campaign. Government offer modern after father theory plan. Receive simple this strategy happy than.',
    'email': 'codywiley@example.org',
    'phone_number': '(939)672-8550x92539',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Flores',
    'Ashley Rojas',
    'Katrina Young',
    'Jennifer Obrien',
    'Lisa Burke',
],
    'json': {
    'name': 'William Wells',
    'address': 'PSC 8785, Box 4932\nAPO AA 13744',
},
    'key10593': 'value82820',
    'key96863': 'value21171',
    'key51264': 'value10469',
    'key65690': 'value84551',
    'key32855': 'value30365',
    'key3372': 'value26178',
    'key2389': 'value33908',
    'key74244': 'value28272',
    'key93785': 'value76860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Ricky Price',
    'address': '502 Karina Mill\nHowefurt, GA 34341',
    'text': 'Seek black within statement sport. Course project cost student. Story may general although game fact prepare.',
    'email': 'vglass@example.net',
    'phone_number': '(717)684-4628x848',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Whitney Peters',
    'Mary Brown',
    'Kevin Terry',
    'Melissa Walker',
    'Linda Morris',
    'Johnny Petersen',
],
    'json': {
    'name': 'Chad Hughes',
    'address': '201 Harris Prairie Suite 441\nHoodville, WY 88545',
},
    'key91263': 'value40483',
    'key85334': 'value49528',
    'key36194': 'value45075',
    'key80147': 'value62548',
    'key27060': 'value48208',
    'key95446': 'value11478',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Joshua Harris',
    'address': '314 Henry Port Suite 413\nNewtonburgh, NE 50509',
    'text': 'Stock news prove sing floor church business. Between sit early everybody form commercial. Vote ten sit would you read.\nBase system nothing. Forget fight song treat smile front. Good likely yeah me.',
    'email': 'kim16@example.com',
    'phone_number': '(279)203-2345',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Medina',
    'Timothy Thornton',
    'Allison Yang',
    'Raymond Johnson',
    'Melanie White',
    'Kimberly Alvarez',
    'Julia Roberts',
    'Larry Stewart',
    'Mrs. Candace Friedman',
],
    'json': {
    'name': 'Alison Reynolds',
    'address': '8507 Joshua Haven Suite 790\nPort Brianna, NE 74259',
},
    'key35750': 'value43449',
    'key83995': 'value41001',
    'key91170': 'value97357',
    'key43918': 'value13800',
    'key282': 'value70542',
    'key57982': 'value61739',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'David Duffy',
    'address': 'USNS Walters\nFPO AE 11481',
    'text': 'Mention environmental near study purpose despite animal. Walk must that determine. I paper ready letter similar off.',
    'email': 'hellis@example.net',
    'phone_number': '+1-749-269-3333',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Bryan',
    'Edward Rose',
    'Norma Lawson',
    'Bradley Estrada',
    'Matthew Lawson',
],
    'json': {
    'name': 'Kevin Rogers',
    'address': '33895 Christy Summit\nLake Charles, FL 39864',
},
    'key30977': 'value8599',
    'key74516': 'value10991',
    'key54410': 'value26157',
    'key36062': 'value83183',
    'key54448': 'value39412',
    'key13189': 'value60799',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'George Hernandez',
    'address': '63529 Woods Junctions\nNorth Bradberg, CA 10327',
    'text': 'Pull because car speech others. Yet hospital this several line toward.\nCell dark phone person. Piece would provide family. View always dinner either.',
    'email': 'zcarter@example.net',
    'phone_number': '001-249-449-1456',
    'array_int_dynamic': [
    30368,
],
    'array_varchar_dynamic': [
    'Laura Fletcher',
    'Joseph Smith',
    'Keith Edwards',
],
    'json': {
    'name': 'David Nguyen',
    'address': '672 Shannon Locks Suite 420\nDillonstad, WA 43567',
},
    'key95608': 'value60071',
    'key76433': 'value80482',
    'key60862': 'value44881',
    'key94098': 'value47146',
    'key39301': 'value66055',
    'key8311': 'value64057',
    'key75864': 'value43942',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Michael Perez',
    'address': '874 Oconnell Lodge\nRobinsonburgh, LA 18200',
    'text': 'None class owner large week. Sit world protect pressure join pressure bed again. Realize beyond allow.',
    'email': 'vsmith@example.org',
    'phone_number': '231.312.5758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mark Walsh',
    'Alan Bryan',
    'Jenna Davis',
    'Terry Davis',
],
    'json': {
    'name': 'Carmen Haynes',
    'address': '558 Daniel Hills Suite 878\nRichardsonville, PW 80267',
},
    'key87785': 'value24514',
    'key60703': 'value63715',
    'key4487': 'value62372',
    'key71519': 'value63498',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Stephen Mills',
    'address': '1597 Gary Greens Apt. 786\nNew Thomas, FM 16442',
    'text': 'Black different go cover appear theory now. Federal scene finally wish doctor. Customer none action five box treat near next.\nUnder hope gun. Floor baby within contain. Teach teach production buy.',
    'email': 'matthew13@example.net',
    'phone_number': '7799594311',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Smith',
    'Pamela Jacobson',
    'Rebecca Mckenzie',
    'Blake Arnold',
    'Angela Young',
    'Christopher Duffy',
    'Mark Wilson',
    'Michael Hernandez',
],
    'json': {
    'name': 'Victor Fernandez',
    'address': '73109 Angela Turnpike\nHerrerafort, GU 13758',
},
    'key49994': 'value94297',
    'key54637': 'value63473',
    'key66500': 'value40761',
    'key5476': 'value27379',
    'key31909': 'value61495',
    'key10275': 'value80060',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Victoria Daniel',
    'address': '0322 Jonathan Mall\nReynoldsmouth, SC 81822',
    'text': 'Eye specific herself technology surface attack agency. Government expect under doctor market without. Small music try design medical large pass.',
    'email': 'jessica86@example.net',
    'phone_number': '576.507.5853x3789',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Larry Howell',
    'Joanna Guerrero',
    'Randall Singh',
    'Ashley Benton',
    'Janet Brewer',
    'Andrew May',
    'Jill Proctor',
    'Taylor Tyler',
    'Carolyn Lewis',
],
    'json': {
    'name': 'Carl Cobb MD',
    'address': '957 Elaine Park Apt. 695\nNorth Andrea, MI 55108',
},
    'key9871': 'value58287',
    'key54094': 'value10993',
    'key2274': 'value17617',
    'key72404': 'value30094',
    'key80987': 'value35260',
    'key10641': 'value35056',
    'key55524': 'value82112',
    'key32534': 'value77550',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Andrew Shah',
    'address': '125 Kevin Lights\nGeorgehaven, WV 92156',
    'text': 'Main treat field stuff.\nOk truth role leave organization product. Culture from bit camera. Understand boy structure. Goal decide design simple.',
    'email': 'ewilson@example.net',
    'phone_number': '842-540-3189',
    'array_int_dynamic': [
    48135,
],
    'array_varchar_dynamic': [
    'Jeffrey Ford',
    'Joseph Hansen',
    'Bryce Wolf',
    'Stephanie Rollins',
],
    'json': {
    'name': 'Brenda Hughes',
    'address': '55054 Laura Gateway Suite 264\nNorth Brian, SC 57819',
},
    'key95323': 'value89659',
    'key17663': 'value29493',
    'key62146': 'value74028',
    'key80241': 'value69105',
    'key39830': 'value29380',
    'key38592': 'value64680',
    'key98047': 'value75255',
    'key49820': 'value22151',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Christina Howell',
    'address': '456 William Lake\nVictoriachester, MS 56056',
    'text': 'Technology expect its answer perhaps activity onto. State later discussion strong but simply.\nDecide recently let parent on hit. Perhaps new probably rate baby wear.',
    'email': 'campbellnathaniel@example.net',
    'phone_number': '2753912035',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Bradley Richards',
    'Tiffany Hughes',
],
    'json': {
    'name': 'Jeremy Chen',
    'address': '2153 Sanchez Branch\nNew Michelleburgh, CA 65698',
},
    'key94721': 'value19954',
    'key92306': 'value36953',
    'key70414': 'value62995',
    'key94270': 'value20465',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Sarah Brown',
    'address': '6332 Krista Road Apt. 983\nPort Cassandraland, RI 41893',
    'text': 'Pass give make into I charge site. Focus give ever religious.\nBoth prove character project choose series. Out security what.\nStar there career this. Move recently positive popular.',
    'email': 'jacksonlinda@example.net',
    'phone_number': '(469)848-5354',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kendra Williams',
    'April Larson',
    'Leah Bennett',
],
    'json': {
    'name': 'Ian Lang',
    'address': '095 Sandra Trafficway\nAntoniohaven, PW 28604',
},
    'key98084': 'value78783',
    'key20827': 'value7035',
    'key79318': 'value27840',
    'key51491': 'value77519',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Maria Khan',
    'address': 'PSC 1087, Box 5097\nAPO AE 22480',
    'text': 'Pattern better indicate far own big help. Enter sport stage night.',
    'email': 'jreed@example.org',
    'phone_number': '926.792.0631',
    'array_int_dynamic': [
    28646,
],
    'array_varchar_dynamic': [
    'Barbara Flores',
    'Vincent White',
    'Roy Sutton',
    'Rhonda Lewis',
    'Chelsea Lozano',
    'Kelly Jacobs',
    'Dominique Luna',
    'Michelle Haynes',
    'Alexandra Gillespie',
    'Matthew Ramirez',
],
    'json': {
    'name': 'Jennifer Williams',
    'address': '37554 Angela Trail\nTimothyland, AS 92132',
},
    'key23219': 'value10798',
    'key78379': 'value95093',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Michael Brown',
    'address': '035 Karen Ranch Apt. 450\nNorth Holly, NV 06606',
    'text': 'Song anything choice court party soldier also. Catch source artist area baby forward.',
    'email': 'twilson@example.org',
    'phone_number': '736-352-4213x9590',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Mcgrath',
    'Kimberly Morton',
    'Andrea Moody',
    'Shannon Fowler',
    'Kelly Hamilton',
    'Zachary Powell',
    'Cristian Barton',
    'Bradley Weber',
    'Christopher Walker',
],
    'json': {
    'name': 'Christopher Blevins',
    'address': '055 Camacho Brooks\nShannonland, IL 55993',
},
    'key49309': 'value94534',
    'key77917': 'value51413',
    'key95290': 'value55313',
    'key55361': 'value55011',
    'key83317': 'value52080',
    'key12939': 'value49519',
    'key74527': 'value72621',
    'key72591': 'value62867',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Miguel Joseph',
    'address': '52999 Long Estate\nBradleyton, PA 51089',
    'text': 'Prevent difficult national all society thousand away.\nTeam course under practice hundred decide opportunity. Receive ready exactly. Sea that nearly learn.',
    'email': 'oestrada@example.org',
    'phone_number': '990-623-8033x2451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Renee Strickland',
    'Alejandro Peters',
    'Joshua Mejia',
    'Matthew Smith',
    'Joseph Duncan',
    'David Carter',
],
    'json': {
    'name': 'Brianna Duran',
    'address': '95168 Christian Divide Apt. 987\nNew John, FM 26992',
},
    'key91580': 'value11394',
    'key89270': 'value58862',
    'key46236': 'value88863',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Charles Hill',
    'address': 'Unit 1276 Box 2997\nDPO AE 26762',
    'text': 'Western realize lay public prevent. Stage civil think small. Teach result story through pressure. Certain return turn including new.',
    'email': 'sandersshawn@example.org',
    'phone_number': '698-993-4341x4507',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Laura Wilson',
    'Nicholas Good',
    'John Murphy',
],
    'json': {
    'name': 'Jessica Baker',
    'address': 'PSC 0713, Box 2346\nAPO AA 77833',
},
    'key54402': 'value62329',
    'key80592': 'value76213',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Jennifer Lee',
    'address': '34489 Jessica Summit Apt. 673\nLake Shaun, TN 04637',
    'text': 'When lay actually century method family. Occur still key add your create. Second both production manage small drive heavy. Each firm suddenly age him everybody administration.',
    'email': 'johnsonderek@example.com',
    'phone_number': '7586378363',
    'array_int_dynamic': [
    64228,
],
    'array_varchar_dynamic': [
    'Vanessa Espinoza',
    'Amber Gonzalez',
    'Jason Howell',
    'Parker Meza',
    'Amy Mitchell',
    'Tonya Graham',
    'Daniel Benjamin',
    'Hector Davis',
],
    'json': {
    'name': 'Robert Simmons',
    'address': '2481 Kennedy Ferry\nScottberg, PW 01585',
},
    'key98156': 'value5043',
    'key67009': 'value76103',
    'key80341': 'value49',
    'key42272': 'value78383',
    'key37184': 'value24667',
    'key319': 'value63481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Todd Glover',
    'address': '6533 Robert Curve\nNew Christiemouth, SD 06879',
    'text': 'Expect not various boy under tax.\nFew wear your explain quality. Again current star model.',
    'email': 'villaedward@example.org',
    'phone_number': '001-792-918-5317x33209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Allen Allen',
    'Paul Houston',
    'Daniel Hoffman',
    'Julia Diaz',
    'Christopher Ward',
    'Paige Reed',
    'Jenna Montoya',
    'Leah Fox',
    'Samuel Yang',
],
    'json': {
    'name': 'Lee Rivera',
    'address': '187 Candice Walk\nNorth Glennport, NC 58080',
},
    'key69414': 'value15631',
    'key59875': 'value99583',
    'key84494': 'value76771',
    'key85392': 'value59809',
    'key39324': 'value11259',
    'key77753': 'value90485',
    'key40710': 'value27230',
    'key79089': 'value63497',
    'key76177': 'value95559',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Theresa Kelly',
    'address': '1531 Nicholas Manor Apt. 363\nEast Moniqueland, MN 73077',
    'text': 'Clear American commercial its audience color full. Local teacher trade woman despite art Mr ever. Benefit down the cost it more.',
    'email': 'elliottmegan@example.org',
    'phone_number': '6525910267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Hannah Mann',
    'Dawn Chandler',
    'Sarah Allen',
    'David Khan',
    'Jared Beasley',
    'Betty Smith',
    'Nicole Dickerson',
    'Jennifer Miller',
    'Preston Hinton',
    'Allison Moore',
],
    'json': {
    'name': 'Douglas Rodriguez DVM',
    'address': '55698 Randall Turnpike\nPort Lisamouth, PA 77318',
},
    'key9013': 'value74008',
    'key14686': 'value47710',
    'key79102': 'value13768',
    'key227': 'value95030',
    'key46263': 'value73224',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Tiffany Garcia',
    'address': '72685 Powers Courts Suite 502\nGriffinshire, GA 58776',
    'text': 'Together first your long news. Prepare low agree.\nOccur head clear air institution. Design nice everything ok political company.',
    'email': 'russelljessica@example.net',
    'phone_number': '938-264-6451x0375',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tanya Huang',
    'Justin Stanley',
    'Danielle Soto',
    'Jason Thomas',
    'Vincent Ruiz',
    'Bruce Hines',
    'Ms. Sherri Morgan',
    'Lauren Hickman',
    'Alicia Hamilton',
],
    'json': {
    'name': 'Lori Scott',
    'address': 'PSC 6500, Box 5729\nAPO AP 17879',
},
    'key25385': 'value88698',
    'key79090': 'value48707',
    'key84494': 'value87784',
    'key48445': 'value91291',
    'key64778': 'value84774',
    'key4121': 'value85390',
    'key60043': 'value96197',
    'key47265': 'value55831',
    'key75635': 'value57076',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Cynthia Marshall',
    'address': '09382 Katherine Fall\nSouth Adrianbury, MT 52701',
    'text': 'Great father pretty maintain left American sign unit.\nPlant travel support daughter. Series probably itself window hear.',
    'email': 'stevenmcclain@example.com',
    'phone_number': '337-368-3942',
    'array_int_dynamic': [
    70753,
],
    'array_varchar_dynamic': [
    'Erica Woods',
    'Brittany Zimmerman',
    'Patricia Williams',
    'William Allen',
    'Chelsea Lawson',
    'Debra Miller',
],
    'json': {
    'name': 'Jordan Duncan',
    'address': '306 Judy Turnpike Apt. 820\nEast Mercedes, ME 13114',
},
    'key64911': 'value64036',
    'key34600': 'value15644',
    'key38621': 'value64811',
    'key64907': 'value19990',
    'key54742': 'value66196',
    'key14752': 'value15895',
    'key68807': 'value27097',
    'key69926': 'value66829',
    'key35434': 'value92241',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Holly Ritter',
    'address': '74475 Lee Port Apt. 588\nPort Edwin, PR 58257',
    'text': 'Investment sea pressure experience although rather after. Act population item maybe into together look. Amount share figure understand enter network point.',
    'email': 'nmyers@example.com',
    'phone_number': '+1-765-778-5675x7689',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Yesenia Parsons',
],
    'json': {
    'name': 'Sherry Freeman',
    'address': '04659 Joseph Street\nCarlastad, ME 52059',
},
    'key74554': 'value64801',
    'key64926': 'value69217',
    'key93537': 'value23615',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Aaron Watkins',
    'address': '6016 Steven Loaf\nKathleenport, AZ 03881',
    'text': 'Defense help strategy research. Partner stand establish certain half fine. Treat worry high tree service. Upon if we building.\nCarry true sense forward. Number billion arm behavior war.',
    'email': 'bsandoval@example.com',
    'phone_number': '001-795-819-7473x53595',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Mcdonald',
    'Jamie Tucker',
    'Melissa Love',
    'Brian Tate',
    'Desiree Rowe',
    'Thomas Kramer',
    'James Day',
    'Alison Moore',
],
    'json': {
    'name': 'Charles Briggs',
    'address': '0328 Coleman Knolls\nMichaelland, FL 65988',
},
    'key83822': 'value45944',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Leonard Wood',
    'address': '05701 John Mills\nToddberg, MP 63212',
    'text': 'Exist audience instead this safe approach.\nFeel enter necessary thank number key. Although understand system gun hundred air describe.',
    'email': 'amykane@example.net',
    'phone_number': '(280)900-2397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Walker',
    'Heidi Sanders',
    'Daniel Lucas',
    'Amanda Smith',
    'Francis Gardner',
    'Jay Jordan',
],
    'json': {
    'name': 'Dustin Morales',
    'address': '8696 Morgan Forge\nNorth Ryan, RI 43166',
},
    'key21910': 'value99835',
    'key72624': 'value47628',
    'key61669': 'value20447',
    'key50988': 'value98944',
    'key95000': 'value5335',
    'key36804': 'value90191',
    'key25923': 'value15509',
    'key933': 'value33011',
    'key89724': 'value24359',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Derek Carter',
    'address': '498 Nathan Plaza\nEast Austin, AR 33581',
    'text': 'Return sea agent music begin body prepare. Form such general expert focus rise. Sea yard thought test truth tree discover.\nBox out surface sit specific PM.',
    'email': 'tinajones@example.net',
    'phone_number': '+1-986-915-0351',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Floyd',
    'Mitchell Cabrera',
    'Steven Frazier',
],
    'json': {
    'name': 'Valerie Levine',
    'address': '248 Michael Dale\nWest Keith, ND 96554',
},
    'key43127': 'value18997',
    'key32212': 'value51244',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Jesse Ramos',
    'address': '975 Houston Overpass Suite 815\nEast Lauren, AL 74485',
    'text': 'Important commercial fear about. Recent protect be card recently language mean whether.',
    'email': 'greenerobert@example.net',
    'phone_number': '001-250-603-9558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Maldonado',
    'Cheryl Banks',
    'Dr. Jesus Sanders',
    'William Mitchell',
    'Christopher Watson',
],
    'json': {
    'name': 'Jeremy King',
    'address': 'USCGC Freeman\nFPO AE 08163',
},
    'key43052': 'value52211',
    'key61854': 'value51624',
    'key8897': 'value80786',
    'key84122': 'value4358',
    'key71911': 'value63500',
    'key18254': 'value22494',
    'key57504': 'value54966',
    'key48973': 'value73886',
    'key69416': 'value69415',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Jay Lewis',
    'address': '357 Kyle Mill Apt. 470\nNew Jennifer, NY 53365',
    'text': 'Project only Democrat life right. Song bag oil what chance bad past. Explain after economy within issue turn include claim.',
    'email': 'laurasullivan@example.com',
    'phone_number': '715-838-2800x286',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Odom',
    'Justin Robinson',
],
    'json': {
    'name': 'Michael Cooper',
    'address': '376 Andrea Center Apt. 455\nDavischester, MA 13563',
},
    'key68808': 'value43849',
    'key21539': 'value82014',
    'key42347': 'value61778',
    'key94954': 'value67251',
    'key12869': 'value50241',
    'key60575': 'value12017',
    'key44539': 'value40599',
    'key56253': 'value79586',
    'key5851': 'value67252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Deborah Livingston',
    'address': '5198 Aaron Fall Apt. 400\nHarrismouth, WV 20012',
    'text': 'Believe baby smile travel wait parent entire. Entire administration message approach.\nEvent bring great apply.\nCommercial morning use ago red. Data listen activity most figure.',
    'email': 'ldiaz@example.net',
    'phone_number': '(279)688-4721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lori Brown',
    'Phillip Lambert',
    'Audrey Barajas',
    'Cynthia Mathews',
    'Roger Spencer',
    'Sydney Johnson',
    'Zachary Walls',
    'Heather Allen',
    'Robert Velasquez',
    'Monica Watson',
],
    'json': {
    'name': 'Kathleen Hale',
    'address': '85343 Courtney Haven Suite 176\nEast Joseph, CA 12781',
},
    'key68632': 'value27023',
    'key69239': 'value16488',
    'key6155': 'value41385',
    'key88030': 'value56871',
    'key92336': 'value20184',
    'key14251': 'value58608',
    'key81420': 'value76849',
    'key17846': 'value12705',
    'key96018': 'value4456',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Kelly Sanchez',
    'address': '66476 Tasha Causeway Suite 716\nRichardshire, ME 89726',
    'text': 'While public itself bill certainly accept anything. Including news back under shake soon once. Year people concern left figure.',
    'email': 'turnercynthia@example.net',
    'phone_number': '6819802536',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Harvey',
    'Lee Hamilton',
    'Maria Rodriguez',
    'Carly Drake',
    'Corey Ayers',
    'Sandra Williams',
    'Robert Hill',
    'Samuel Garcia',
],
    'json': {
    'name': 'Jerome Cole',
    'address': '293 Ryan Underpass Suite 810\nPort Michael, NM 43195',
},
    'key8005': 'value89177',
    'key56275': 'value7677',
    'key8858': 'value4684',
    'key94159': 'value43562',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Michael Payne',
    'address': '56253 John Forge Suite 322\nNew Russell, NY 25150',
    'text': 'Yes yet own edge include artist. Quickly determine message over near dog choice. Light great piece chance.\nPositive southern edge run. If professor herself some whatever.',
    'email': 'williamskaren@example.net',
    'phone_number': '001-994-702-4102x42759',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Mathew Hammond MD',
    'Jonathan Johnson',
],
    'json': {
    'name': 'Curtis Gonzales',
    'address': 'USNS Chase\nFPO AP 23772',
},
    'key3446': 'value56692',
    'key71088': 'value21678',
    'key34784': 'value26879',
    'key16607': 'value5462',
    'key78754': 'value27357',
    'key2335': 'value20299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Tyler Santos',
    'address': 'PSC 3142, Box 5810\nAPO AA 66274',
    'text': 'Reality build actually debate.\nAllow friend standard stop police. Example test gun put development real. Pick go available billion that represent.\nLater another bed. Contain heart my series might.',
    'email': 'diana95@example.com',
    'phone_number': '(595)490-1004',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Adam Hill',
],
    'json': {
    'name': 'Eileen Olson',
    'address': '493 Leslie Springs\nPort Melissa, VT 45611',
},
    'key84984': 'value44499',
    'key60971': 'value21331',
    'key87596': 'value54244',
    'key65614': 'value67859',
    'key56197': 'value68257',
    'key11725': 'value37875',
    'key41664': 'value49048',
    'key28262': 'value91221',
    'key36774': 'value38787',
    'key18931': 'value22793',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Susan Jackson',
    'address': '28858 Vaughn Loop Suite 809\nLake Stephanieland, ME 24565',
    'text': 'Of out cell able set less. Different read close deal outside home sit growth.\nSimilar him one ask. None check notice. Leader lot knowledge example even rest.',
    'email': 'heatheranderson@example.com',
    'phone_number': '+1-671-371-1797x988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Katie Kim',
    'Sarah Meyer',
],
    'json': {
    'name': 'Connie Miller',
    'address': '18590 Thompson Knolls\nSouth Dennis, ME 93567',
},
    'key40795': 'value24579',
    'key25724': 'value18552',
    'key67779': 'value68727',
    'key62477': 'value15918',
    'key97272': 'value56453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Joshua Carter',
    'address': '080 Johnson Manor Suite 718\nPort Aprilview, ME 34145',
    'text': 'Tough part everybody civil street teach. As store end agree scientist trade edge. Drive common imagine kitchen senior.\nHerself phone anyone. Result your newspaper hit. Finally gun second history its.',
    'email': 'marvinsmith@example.com',
    'phone_number': '901-511-9479x866',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'April Howell',
    'Walter Hobbs',
    'Kiara Glover',
    'Rachel Johnson',
    'Karen Hunt',
    'Lisa Mack',
],
    'json': {
    'name': 'Danielle Lang',
    'address': '6383 Isabel Trail\nHodgeston, MO 59555',
},
    'key73191': 'value30369',
    'key88496': 'value26691',
    'key37795': 'value4282',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Kimberly Scott',
    'address': '799 Martin Track Suite 075\nAlanshire, FM 52662',
    'text': 'Role price alone land professor daughter. End act bank interesting. Conference what occur news next drop check.',
    'email': 'thatfield@example.net',
    'phone_number': '633.580.6945x2434',
    'array_int_dynamic': [
    19909,
],
    'array_varchar_dynamic': [
    'Brandi Hansen',
    'Nathan Johnston',
],
    'json': {
    'name': 'Zachary Shannon',
    'address': '466 Edwards Forge\nSouth Michelle, DE 97947',
},
    'key1544': 'value81886',
    'key70360': 'value1593',
    'key6832': 'value32603',
    'key53531': 'value83246',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Tanner Garcia',
    'address': '14746 Jill Mount Suite 074\nEast Susan, MD 50095',
    'text': 'Its building economy prove. Social hit amount on certain.\nStuff whatever energy. Serious theory else or serve piece generation.\nCampaign per bill important campaign possible.',
    'email': 'kmays@example.org',
    'phone_number': '001-864-501-1435',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christian Hensley',
    'Eric Martinez',
    'Mike Silva',
    'Dana Brown',
    'Thomas Wood',
],
    'json': {
    'name': 'Russell Arellano',
    'address': '7203 Thomas Hill\nNormaborough, GU 12960',
},
    'key76509': 'value62980',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Willie Houston',
    'address': '36304 Ross Centers Apt. 364\nPort Linda, IN 73989',
    'text': 'Per southern do available. Tonight character read hair. Dinner catch dream travel us nice boy.\nSimilar authority note poor participant might. Lead together others under look debate local soon.',
    'email': 'moralesdavid@example.net',
    'phone_number': '(861)775-3703x5955',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Krystal Gillespie',
    'Andrea Galloway',
    'Barbara Johnson',
    'Cindy Parker',
    'William Lawrence',
    'Thomas Jones',
],
    'json': {
    'name': 'Felicia Perez',
    'address': '8020 Perkins Unions Suite 119\nStephanieberg, AS 07733',
},
    'key96611': 'value91055',
    'key20936': 'value7717',
    'key37379': 'value78379',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Frank Brandt',
    'address': '25704 Fernandez Spurs\nEast Heather, NC 54152',
    'text': 'Factor yard site more answer ask. Former space long teach treat data.\nWalk laugh purpose all speech example part. Election second past future local.',
    'email': 'obanks@example.net',
    'phone_number': '497-405-0245x748',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Luis Clayton',
    'Dr. Maria Nguyen',
    'Theresa Wilkinson',
],
    'json': {
    'name': 'Kelly Garcia',
    'address': 'Unit 4056 Box 3876\nDPO AP 44761',
},
    'key7329': 'value49145',
    'key25310': 'value43699',
    'key49497': 'value3923',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Brittany Rivera',
    'address': '8647 Bailey Ways\nSteelebury, MS 61051',
    'text': 'Court relationship trouble policy natural style also foreign. Maybe blue must tell. Never edge west sure recently young.',
    'email': 'emills@example.net',
    'phone_number': '603-768-5999x423',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Davis',
],
    'json': {
    'name': 'Shannon Mann',
    'address': '3478 Nelson Forks\nNorth John, AR 94964',
},
    'key84502': 'value24178',
    'key18373': 'value96915',
    'key12045': 'value50356',
    'key16286': 'value26605',
    'key89066': 'value48670',
    'key12610': 'value12163',
    'key59540': 'value66572',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Connie Walton',
    'address': '4911 Richard Valleys\nNorth Stephanie, IN 69837',
    'text': 'Purpose turn need piece. Billion practice understand government example call cause break.\nKitchen wrong compare clearly organization open by. Reach unit camera probably company truth.',
    'email': 'lewismichael@example.net',
    'phone_number': '524.230.0474x1657',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brandy Smith',
    'Amy Dawson',
    'Michael Salinas',
    'Jacob Williams',
],
    'json': {
    'name': 'Judy Moody',
    'address': '16067 Benjamin Club Suite 907\nSheltonstad, ND 01172',
},
    'key43360': 'value98773',
    'key34072': 'value71069',
    'key31688': 'value54963',
    'key83386': 'value2443',
    'key24344': 'value88128',
    'key68828': 'value46586',
    'key70064': 'value67029',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Stephen Anderson',
    'address': '1466 Kathryn Ranch\nHebertburgh, FL 51326',
    'text': 'Me top eye. Growth century church kitchen practice. Artist ability floor manage.\nOffice professor Mr tax against range why. Top or film.\nLess another real watch. Per big real argue night.',
    'email': 'qyu@example.net',
    'phone_number': '6137395970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Eric Roth',
    'Amy Buchanan',
    'Erica Benson',
    'Dakota Rogers',
    'Joshua Kelley',
    'Michelle Sanchez',
    'Victor Baker',
    'Joel Ward',
    'Kevin Cunningham',
],
    'json': {
    'name': 'Crystal Foster',
    'address': '5250 Lopez Station Suite 253\nDiazshire, MD 68693',
},
    'key34424': 'value93576',
    'key98777': 'value70642',
    'key94254': 'value9727',
    'key94371': 'value13690',
    'key7428': 'value39774',
    'key49936': 'value80281',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'David Love',
    'address': '9213 Estrada Run\nPort Jeffreymouth, NE 57810',
    'text': 'Recent friend most five within guy edge. Though list movement cultural report science indeed. Whether its city. Song and drop word anything student into.',
    'email': 'swansonjustin@example.com',
    'phone_number': '+1-571-435-0436',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Richard Kennedy',
    'Tim Robinson',
    'Joe Sawyer',
],
    'json': {
    'name': 'Kimberly Harrison',
    'address': '008 Chase Rue\nJonesberg, MN 38221',
},
    'key26719': 'value56370',
    'key11132': 'value13165',
    'key81107': 'value94555',
    'key1721': 'value16363',
    'key32227': 'value85406',
    'key50357': 'value41074',
    'key6185': 'value17839',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Virginia Glover',
    'address': 'USCGC Anderson\nFPO AE 31182',
    'text': 'Just happy tend Mrs before firm time. Stage size interesting structure parent.\nCreate box deep despite day. Follow environment investment president course. Bar least detail unit carry learn.',
    'email': 'arthurknight@example.net',
    'phone_number': '+1-753-450-7504x13234',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Mcintosh',
    'Cody Bell',
    'Krista Vasquez',
    'Marc Stephenson',
    'Carla Alexander',
],
    'json': {
    'name': 'Sheila Gonzalez',
    'address': '2799 Kimberly Freeway\nTurnerfort, SD 83309',
},
    'key4070': 'value29275',
    'key57282': 'value37589',
    'key38629': 'value22474',
    'key52314': 'value93932',
    'key7415': 'value58026',
    'key71435': 'value34398',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Laura Scott',
    'address': '1309 Dougherty Summit\nMatthewside, PW 34725',
    'text': 'City garden once site station check call your. Blue middle memory watch south. Manager approach daughter impact sell recently. Continue PM some leader door.',
    'email': 'stephensdeborah@example.com',
    'phone_number': '001-639-857-4223x7956',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Peter Sutton',
    'Heidi Warner',
    'Joel Robbins',
    'Cassie Patterson',
    'David Harrison',
    'Anthony Jackson',
    'Shawn Ferguson',
    'Jason Williams',
    'Sandra Small',
    'Lawrence Mahoney',
],
    'json': {
    'name': 'Michael Willis',
    'address': '31333 Luis Shoal\nNorth Kathrynberg, FM 28597',
},
    'key1445': 'value55876',
    'key60605': 'value89533',
    'key94830': 'value91055',
    'key26641': 'value89481',
    'key7676': 'value75574',
    'key4384': 'value82402',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Teresa Hoffman',
    'address': 'USCGC Zamora\nFPO AA 58304',
    'text': 'East class seat total. Response even relationship into company half money.\nSociety marriage him improve nature. Stock finally information painting.',
    'email': 'fernandovasquez@example.com',
    'phone_number': '876-829-3878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Castro',
    'Aaron Hernandez',
    'Amber Armstrong',
    'Dawn Stewart',
    'Samantha Moran',
    'Elizabeth Chapman',
],
    'json': {
    'name': 'Tracy Kim',
    'address': 'Unit 9025 Box 2683\nDPO AE 43266',
},
    'key17476': 'value28795',
    'key45800': 'value98726',
    'key97802': 'value64178',
    'key19491': 'value62109',
    'key34484': 'value30751',
    'key3142': 'value85216',
    'key53377': 'value33620',
    'key80527': 'value70805',
    'key23284': 'value40890',
    'key13954': 'value61262',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Eric Bowman',
    'address': '6822 Garcia Forge Suite 906\nNelsonchester, CO 03038',
    'text': 'Buy car impact discussion.\nBeat thousand thing in successful. Attorney community institution enough beyond foot fight painting. Whether four century west.',
    'email': 'greenstacy@example.net',
    'phone_number': '627.415.7933x4509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jill Vega',
    'Michele Robertson',
    'Christopher Bryant',
    'Alexandra Robinson',
    'Zachary Lane',
    'Michael Robinson',
],
    'json': {
    'name': 'Jennifer Roberts',
    'address': '3996 Wilson Via\nNorth Angela, AL 50637',
},
    'key69504': 'value36981',
    'key31158': 'value69753',
    'key92607': 'value50679',
    'key24470': 'value8541',
    'key47657': 'value109',
    'key70276': 'value90',
    'key78181': 'value28628',
    'key18969': 'value40754',
    'key67219': 'value44331',
    'key88792': 'value61714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Kathleen Perez',
    'address': '635 Thomas Ridge Apt. 067\nTerriburgh, IA 90350',
    'text': 'Number civil go several. Catch reflect quality spend end drug foreign.\nFight outside theory data. Always job see would lawyer. Very shoulder appear image bar these.',
    'email': 'sarah66@example.com',
    'phone_number': '+1-922-795-8085x80266',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tina Turner',
    'Thomas Allen',
    'Tamara Jones',
],
    'json': {
    'name': 'Bill Elliott',
    'address': '974 Lisa Highway Apt. 837\nSouth Beckyland, ND 06572',
},
    'key40159': 'value65991',
    'key32183': 'value46400',
    'key85543': 'value8853',
    'key14978': 'value39588',
    'key82938': 'value48904',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Kimberly Holder',
    'address': 'Unit 2051 Box 8943\nDPO AE 70765',
    'text': 'Organization police computer fast. Public price data skill feeling six protect big.',
    'email': 'sherry37@example.net',
    'phone_number': '732-623-4772x5097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Curtis Velez',
    'Paul Smith',
    'Calvin Bell',
    'Ashley Lewis',
    'John Anderson',
    'John Green',
    'Samuel Camacho',
    'Amanda Stone',
],
    'json': {
    'name': 'Gregory Oconnor',
    'address': 'Unit 1051 Box 0438\nDPO AP 81002',
},
    'key91356': 'value65699',
    'key4236': 'value5301',
    'key66673': 'value67487',
    'key87932': 'value58039',
    'key29651': 'value12318',
    'key80436': 'value75716',
    'key31560': 'value30121',
    'key77516': 'value27833',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Kayla Dominguez',
    'address': '499 Deborah Fords\nMedinabury, CT 97947',
    'text': 'Approach foot soldier instead matter. Wait task religious newspaper stuff child. Article chair one throughout result many.\nDraw yourself citizen little staff Democrat list. Focus in who she movie.',
    'email': 'christian31@example.org',
    'phone_number': '2433327961',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Harry Day',
    'Terry Ross',
    'Connie Williams',
    'Richard Scott',
    'Bryan Rodriguez',
],
    'json': {
    'name': 'Jamie Riley',
    'address': '264 Donna Ports Suite 744\nLake Cameronburgh, WA 38635',
},
    'key75703': 'value74880',
    'key97332': 'value9981',
    'key1863': 'value57573',
    'key26409': 'value79728',
    'key23222': 'value5904',
    'key17847': 'value43739',
    'key70970': 'value8344',
    'key74437': 'value11988',
    'key34311': 'value78526',
    'key15568': 'value80215',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Ryan Stout',
    'address': '396 Christopher Brooks\nPort Danielville, TX 05316',
    'text': 'Back upon wife. Parent response one suddenly land you.\nHave issue election son threat cultural black. Hundred recognize wish pressure start.',
    'email': 'austinharris@example.net',
    'phone_number': '001-862-925-6829x136',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Meredith Nichols',
    'Mary Anderson',
    'Monica Duncan',
    'Linda Watts',
    'Kathleen Chan',
],
    'json': {
    'name': 'Michael Parrish',
    'address': '0919 Thomas Fords Suite 760\nLake Charles, TN 92025',
},
    'key77729': 'value90566',
    'key43869': 'value82470',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Jeffrey Price',
    'address': '7341 Taylor Ports\nEast Martin, RI 73713',
    'text': 'Sing friend bar cultural. Market before south several sometimes. Wait part scene career.\nTrouble suffer think growth. Article worry middle doctor. Perform upon option hand choose establish.',
    'email': 'iwhitehead@example.org',
    'phone_number': '878.325.0119x33568',
    'array_int_dynamic': [
    90486,
],
    'array_varchar_dynamic': [
    'Kevin Berg',
    'Joel Hernandez',
    'Ms. Veronica Cobb MD',
    'Elizabeth Thompson',
    'Kimberly Byrd',
],
    'json': {
    'name': 'Terry Kennedy',
    'address': '7580 Adams Plains\nEast Michael, VI 27318',
},
    'key60866': 'value36106',
    'key10936': 'value27982',
    'key16005': 'value16188',
    'key63303': 'value16631',
    'key95280': 'value36811',
    'key31936': 'value3551',
    'key96063': 'value27191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Adrian Pacheco',
    'address': '24624 Rhonda Brook Apt. 595\nPruittport, ME 17961',
    'text': 'Congress center cold worry art. Risk arm husband summer.\nHit attack system worker. Long rather for ever country.\nDevelopment hold space.',
    'email': 'bakerrobert@example.net',
    'phone_number': '396.315.9645x603',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jason Wagner',
    'Robert Martinez',
    'Christopher Thompson',
    'William Frost',
    'Troy Molina',
    'Heather Johnson',
    'Robert Gonzalez',
    'David Hernandez',
    'Nicholas White',
],
    'json': {
    'name': 'Anne Lawrence',
    'address': '03546 Ford Forge Suite 766\nLeahfort, FM 20006',
},
    'key80734': 'value76392',
    'key36630': 'value86703',
    'key47233': 'value80744',
    'key98729': 'value93000',
    'key46219': 'value75838',
    'key41879': 'value6803',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Justin Johnson',
    'address': '44830 Martinez Groves\nWest Andrew, WI 46669',
    'text': 'Smile dream not then assume think eat. Interest guy four memory record. Into their or small of garden price.\nPerson loss from together war. Other while couple he.',
    'email': 'nfranco@example.com',
    'phone_number': '630.634.1331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Walker',
    'Crystal Rubio',
    'John Perez',
    'Edward Vega',
    'Richard Ross',
    'Lisa Carroll',
    'Danielle Rios',
    'Priscilla Johnson',
    'Stephen Benjamin',
    'Mary Rodriguez',
],
    'json': {
    'name': 'Cory Velazquez',
    'address': '5828 Martin Drive\nGarciaberg, MN 25230',
},
    'key26730': 'value92668',
    'key70900': 'value90494',
    'key58319': 'value67534',
    'key61138': 'value98117',
    'key72174': 'value64924',
    'key6734': 'value40058',
    'key7075': 'value78030',
    'key33555': 'value39006',
    'key21819': 'value35083',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Mrs. Karen Chapman',
    'address': '302 Howard Knoll\nSouth Juliemouth, NH 53770',
    'text': 'Seven against according else industry after trade. Ask treat thing what career girl pattern. Receive other ever stuff value leg.',
    'email': 'dlong@example.org',
    'phone_number': '532.948.8253x07877',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Downs',
    'Victoria Nguyen',
    'Shaun Foster',
    'Megan Bowman',
    'Felicia Mclaughlin',
    'Edward Graves',
    'Amanda Taylor',
    'Steven Miller',
    'Johnny Clark',
    'Mark Anderson',
],
    'json': {
    'name': 'Melissa Cummings',
    'address': '777 Jody Station\nWaterstown, MT 08852',
},
    'key41406': 'value9367',
    'key17918': 'value59414',
    'key57585': 'value18852',
    'key35673': 'value91329',
    'key21929': 'value48896',
    'key67884': 'value34695',
    'key57532': 'value45355',
    'key17675': 'value10072',
    'key57415': 'value36691',
    'key4802': 'value72795',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Bill Hendricks',
    'address': '334 Turner Ramp Suite 930\nPaulmouth, RI 19119',
    'text': 'Day parent investment begin American western family. Your or offer tonight skill. Arm right who create most situation issue.\nSound forward election gun safe always special. Have character ask find.',
    'email': 'archerlori@example.org',
    'phone_number': '2457551670',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Katelyn Smith',
    'Ann Cameron',
    'Leah Blake',
    'Elizabeth Todd',
    'Abigail Cook',
    'Jackson Barker',
],
    'json': {
    'name': 'Thomas Cunningham',
    'address': '1292 Lynn Drive\nChenstad, IA 14119',
},
    'key79179': 'value46176',
    'key48159': 'value99263',
    'key4738': 'value62669',
    'key66642': 'value80832',
    'key86233': 'value49577',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Thomas Reyes',
    'address': '9918 Blackburn Ports Suite 518\nPort Ryan, CT 12112',
    'text': 'Safe bill down activity subject good success. Ask sometimes player night relate course. Brother just five beat.\nProtect his special while. Scene show purpose.\nCommon serious want per want.',
    'email': 'johnsullivan@example.com',
    'phone_number': '215.662.9010',
    'array_int_dynamic': [
    17297,
],
    'array_varchar_dynamic': [
    'James Garcia',
    'Allen Ewing',
    'Jennifer Turner',
    'Beverly Brennan',
    'Joseph Allen',
    'Malik Garcia',
    'Samuel Greer',
    'Kristine Lee',
    'Timothy Fischer',
],
    'json': {
    'name': 'Suzanne Black',
    'address': 'PSC 7799, Box 0555\nAPO AA 77458',
},
    'key93744': 'value18719',
    'key50986': 'value60009',
    'key30007': 'value26534',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Travis Mullins',
    'address': '6669 Becker Estate\nWest Amandaton, WI 26076',
    'text': 'Sport rest begin structure relationship force morning. Sell moment level provide. Morning situation may imagine admit dog author.',
    'email': 'hblackwell@example.org',
    'phone_number': '+1-610-648-2509x40304',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Hayley Mays',
    'Michelle Hicks',
],
    'json': {
    'name': 'Victoria Glover',
    'address': '47095 Charles Forge Suite 553\nStewartfort, NH 56707',
},
    'key7662': 'value82619',
    'key91829': 'value60660',
    'key11821': 'value92041',
    'key12244': 'value89582',
    'key926': 'value71592',
    'key96090': 'value20844',
    'key84952': 'value8337',
    'key26055': 'value58436',
    'key35675': 'value12196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Alexis Molina',
    'address': '80953 Lisa Falls\nAndrewport, ND 41392',
    'text': 'Task point wind low face too work and. There material chair officer every five. So her piece.\nRespond person southern ever common raise.',
    'email': 'william28@example.net',
    'phone_number': '513-914-2642x407',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Edwards',
],
    'json': {
    'name': 'Robin Henderson',
    'address': '8884 Christopher Curve Apt. 378\nNorth Teresabury, HI 38055',
},
    'key1461': 'value76159',
    'key17157': 'value91947',
    'key42854': 'value29692',
    'key3537': 'value85366',
    'key76874': 'value16413',
    'key51462': 'value98273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Joshua Moreno',
    'address': '244 Joseph Passage Suite 816\nDuranmouth, IN 91596',
    'text': 'Design hear around. Something live director admit play choose. Production increase phone could consumer investment husband.',
    'email': 'petersenkristen@example.com',
    'phone_number': '601.439.5851x0347',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Johnson',
    'Kelly Jordan',
    'Jessica Wong',
    'Katelyn Clarke',
    'Natalie Lewis',
],
    'json': {
    'name': 'Steven Reyes',
    'address': '53093 Molina Run Apt. 372\nWest Crystalfurt, HI 01216',
},
    'key52230': 'value55567',
    'key84406': 'value31520',
    'key21005': 'value21305',
    'key49185': 'value77663',
    'key50178': 'value99216',
    'key96335': 'value73951',
    'key85020': 'value36970',
    'key25811': 'value78614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Charles Jordan',
    'address': '87572 Jackson Ville Apt. 818\nNorth Carlosfurt, FL 11339',
    'text': 'Woman music effort home character security possible. Hospital collection question service.',
    'email': 'jeremy87@example.net',
    'phone_number': '(582)619-2038x718',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sara White',
    'David Wong',
    'Katherine Townsend',
],
    'json': {
    'name': 'Keith Chavez',
    'address': 'PSC 5924, Box 2763\nAPO AA 06337',
},
    'key70986': 'value30968',
    'key21592': 'value52060',
    'key82938': 'value85747',
    'key78484': 'value84669',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Matthew Smith',
    'address': '586 Alan Mountains\nLake Kellystad, NV 80381',
    'text': 'Billion standard create spend. Particularly case book create.\nSuffer government forward success wait week. Stage public like our argue network.',
    'email': 'gutierrezandrew@example.org',
    'phone_number': '986.478.5051',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Peter Ray',
],
    'json': {
    'name': 'Matthew Jones',
    'address': '3519 Ashley Centers Suite 641\nWest Kimberly, UT 94084',
},
    'key95444': 'value83118',
    'key87758': 'value60808',
    'key52725': 'value35701',
    'key23049': 'value39237',
    'key94594': 'value40165',
    'key84336': 'value94652',
    'key85794': 'value23492',
    'key45371': 'value71269',
    'key3290': 'value84605',
    'key44367': 'value75956',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'James Hill',
    'address': '92453 Jason Walk\nAndradehaven, OR 38369',
    'text': 'Change necessary look group. Cost know claim.\nYet behind season picture standard real campaign family. Other production early television beyond health believe.',
    'email': 'fmartinez@example.org',
    'phone_number': '520.412.8021x5095',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Keith White',
    'Ethan Cunningham',
    'James Carter',
    'Eric Calderon',
    'Spencer Hurley',
    'Ann Parker',
    'Linda Anderson',
],
    'json': {
    'name': 'Margaret Lee',
    'address': '98842 Santana Street\nSouth Ashleeborough, WA 94155',
},
    'key34463': 'value48907',
    'key2459': 'value63242',
    'key97499': 'value49285',
    'key10486': 'value19655',
    'key36375': 'value65307',
    'key97345': 'value3798',
    'key36959': 'value99754',
    'key87844': 'value90924',
    'key53950': 'value2294',
    'key54673': 'value46719',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Courtney Tyler',
    'address': '007 Kelly Harbor Apt. 088\nHernandezfurt, FL 02142',
    'text': 'Hard nature join garden center cover tell ahead. Improve born Mrs.\nWhole feel sound record blood work particularly laugh. Boy hit he thank ability chair should.',
    'email': 'amy06@example.com',
    'phone_number': '702.905.3280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Allen',
    'Joshua Hunter',
    'Mr. Taylor Sanders DVM',
    'Victoria Monroe',
    'Karen Garcia',
    'Rickey Lewis',
    'Annette Gonzalez',
],
    'json': {
    'name': 'Charles Mcbride',
    'address': '43984 Jackson Knoll Suite 399\nSouth Charlotteland, NY 07679',
},
    'key57142': 'value39330',
    'key93686': 'value6642',
    'key7829': 'value21095',
    'key72791': 'value24365',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Abigail Vazquez',
    'address': '5718 Weber Gardens Apt. 901\nBatesport, IA 79203',
    'text': 'Become claim personal fill. Seek theory effort note culture meeting avoid black. Attention develop support. Manage data car white second woman lay month.',
    'email': 'melissa11@example.org',
    'phone_number': '845-773-4937',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Carla Cervantes',
    'Jonathan Ward',
    'Mr. William Rodriguez PhD',
    'Brandon Powers',
    'Antonio Anderson',
],
    'json': {
    'name': 'Steven Reyes',
    'address': '1343 Teresa Lights Apt. 224\nPort Kennethview, NE 95703',
},
    'key63814': 'value88534',
    'key3890': 'value32177',
    'key56345': 'value50961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Jonathan Jones Jr.',
    'address': '160 Erickson Grove\nNorth Jamesbury, MP 07650',
    'text': 'Newspaper necessary bar big couple. What issue care entire remember position actually. Gun stay road here tough chair capital.',
    'email': 'uoliver@example.com',
    'phone_number': '988.900.0297x975',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Lee',
    'Julie Robinson',
    'Rebecca May',
    'Stuart Knight',
    'Katie Smith',
    'Jonathan Rodriguez',
    'Mark Hernandez',
    'Jimmy Stewart',
    'Tina Mullins',
    'Devin Johnson',
],
    'json': {
    'name': 'Mark Walsh',
    'address': '351 Gibson Forest\nNorth Ryanborough, GA 34936',
},
    'key56193': 'value19312',
    'key8220': 'value66134',
    'key68542': 'value45203',
    'key86129': 'value26074',
    'key612': 'value30180',
    'key66644': 'value94774',
    'key81211': 'value49474',
    'key55729': 'value22880',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Carolyn Murphy',
    'address': '69273 Karen Tunnel\nDavidshire, TX 81922',
    'text': 'Give since city table yes high. Congress believe notice mention really. Pm mouth themselves open.\nSing hundred bad cause support line call. Significant summer American purpose.',
    'email': 'lallen@example.org',
    'phone_number': '+1-210-280-4674',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tamara Wallace',
],
    'json': {
    'name': 'Amanda Vargas',
    'address': '617 Wright Gateway Suite 295\nCamposview, NH 91461',
},
    'key46003': 'value72054',
    'key30629': 'value61778',
    'key5811': 'value51554',
    'key97983': 'value48387',
    'key97022': 'value43997',
    'key53941': 'value62847',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Barbara Williams',
    'address': '473 James Station Suite 152\nSouth Michael, FM 48139',
    'text': 'Cut line your ok state hospital beautiful maybe. Themselves relate two song executive.\nTheir whole number sea.',
    'email': 'russelljessica@example.org',
    'phone_number': '+1-762-960-5702x86121',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Debra Coleman',
    'Benjamin Snyder',
    'Russell Hutchinson',
    'Jamie Anderson',
    'Jessica Hill',
    'Melissa Davis',
    'Laura Gonzalez',
    'Lauren Drake',
    'Eric Dyer',
],
    'json': {
    'name': 'Dana Clark',
    'address': '252 Delgado Flat\nNorth Cheryl, AK 89299',
},
    'key6993': 'value81970',
    'key61149': 'value72645',
    'key51326': 'value30513',
    'key42924': 'value59032',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Eric Johnson',
    'address': '7226 George Crossing Apt. 354\nEast Robyn, MS 18606',
    'text': 'Science either fund relate go should inside. Small wear seat rather everybody nearly plant. Piece any chance product hit.\nThird respond team present. Reality put expert push.',
    'email': 'rileytammy@example.org',
    'phone_number': '(886)455-0788x1502',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Hamilton',
    'Jeffrey Pham',
    'Timothy Frazier',
],
    'json': {
    'name': 'Lisa Johnson',
    'address': '5278 Clark Oval\nEmmaborough, VT 23996',
},
    'key96136': 'value57357',
    'key61537': 'value89610',
    'key51976': 'value96220',
    'key46447': 'value74037',
    'key68632': 'value93411',
    'key91304': 'value66090',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Kelly Silva',
    'address': '2920 Nicholas Springs\nDouglasshire, DE 81082',
    'text': 'Public federal need animal.\nWife politics eat exist behind. Difficult share policy station name.',
    'email': 'jillflowers@example.com',
    'phone_number': '376-963-0647',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Amber Jordan',
    'Jonathan Walton',
    'Dana Dean',
    'Timothy Espinoza',
    'Matthew Matthews',
    'Mr. James Diaz Jr.',
    'Jenna Stevens',
],
    'json': {
    'name': 'James James',
    'address': 'USS Fisher\nFPO AA 30432',
},
    'key25479': 'value81050',
    'key16246': 'value50514',
    'key23826': 'value78534',
    'key31364': 'value18238',
    'key76142': 'value28163',
    'key85430': 'value4982',
    'key52720': 'value12735',
    'key15169': 'value21143',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Allison Petersen',
    'address': '2819 Alvarez Highway\nPort Christinefurt, TX 04960',
    'text': 'History music between care gas southern run. Mission we until hard plan.\nStay affect bank they.',
    'email': 'ogreen@example.org',
    'phone_number': '001-921-202-1093x907',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Alexandra Hodges',
    'Alejandra Campbell',
    'Laura Casey',
],
    'json': {
    'name': 'Nicholas Brewer',
    'address': '36857 Mata Road\nWest Donnaborough, PA 72316',
},
    'key53802': 'value24359',
    'key33369': 'value93361',
    'key82418': 'value66485',
    'key26359': 'value98973',
    'key67160': 'value7803',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Ashley Lowe',
    'address': '3162 Johnson Camp Suite 352\nLake Rodney, CO 55556',
    'text': 'Field kitchen agree relationship best finish body opportunity. Go service health line.\nRepublican police article left. Thank agree common experience large. Three low special benefit me value ask.',
    'email': 'qlee@example.net',
    'phone_number': '(351)925-5242x51644',
    'array_int_dynamic': [
    18601,
],
    'array_varchar_dynamic': [
    'Suzanne Scott',
    'Kim Davis',
    'David Meyers',
    'Julie Taylor',
    'Marissa Hammond',
],
    'json': {
    'name': 'Brian Clark',
    'address': '4647 Erin Loop Apt. 886\nCaseystad, DE 78360',
},
    'key91778': 'value90987',
    'key84684': 'value71507',
    'key67610': 'value88109',
    'key10319': 'value75639',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Brittney Johnson',
    'address': 'PSC 6436, Box 4683\nAPO AA 25110',
    'text': 'Particularly difficult possible share activity kind. Sea day positive true relate current. Play similar image green.\nForward choose either idea measure store.',
    'email': 'karenramirez@example.net',
    'phone_number': '001-318-508-7599x1758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Martin',
    'Allison Schmidt',
    'Paula Marshall',
    'Kelly Wall',
    'Kathryn Hanson',
    'Christopher Hill',
    'Sandra Hill',
],
    'json': {
    'name': 'Sarah Ortiz',
    'address': '74133 Daniel Cliffs Apt. 618\nSouth Jenny, FM 31995',
},
    'key47770': 'value91141',
    'key89424': 'value43487',
    'key30850': 'value88222',
    'key18581': 'value8612',
    'key86016': 'value48701',
    'key49458': 'value3775',
    'key51345': 'value90808',
    'key31464': 'value93238',
    'key96036': 'value62166',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Gina Barrera',
    'address': '031 Chan Creek\nDanielleport, TX 65908',
    'text': 'Child type take appear. Who life hour.\nHand start girl girl kitchen. Short wear fire realize professor customer house large. Work skin respond maintain other line.',
    'email': 'srodriguez@example.com',
    'phone_number': '001-623-234-9866x0812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Scott Morton',
],
    'json': {
    'name': 'Daniel Johnson',
    'address': '77200 Young Trace Apt. 616\nPort Richardhaven, CA 21948',
},
    'key5501': 'value83771',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Denise Farmer',
    'address': '7282 Underwood Port Apt. 198\nSouth Denise, OR 67396',
    'text': 'Strategy important action million. Build product throughout region develop thing image.',
    'email': 'rlawson@example.org',
    'phone_number': '001-235-728-9714x86842',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jenny Berry',
],
    'json': {
    'name': 'Austin Mccormick',
    'address': '2875 Baldwin Inlet\nPort Jennifermouth, DE 38045',
},
    'key15402': 'value92164',
    'key70552': 'value48236',
    'key90769': 'value69433',
    'key98862': 'value70184',
    'key11200': 'value21112',
    'key61905': 'value18389',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Linda Sharp',
    'address': '990 Wright View\nPort Brandonside, KY 04679',
    'text': 'Purpose voice color of culture leader use. Democrat perform card institution statement.\nAbout hard forward play anything. Picture almost occur seek off difficult.',
    'email': 'codyschultz@example.net',
    'phone_number': '221.312.5221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Shirley Cantu',
    'Jennifer Floyd',
    'Alan Jones',
    'Karen Frank',
    'Michael Cunningham',
    'Ann Dunn',
    'Mark Martinez',
    'Mallory Huffman',
    'Jason Yu',
    'Frank Lloyd',
],
    'json': {
    'name': 'Tamara Lambert',
    'address': '477 Derek Plains\nStuartside, AR 10418',
},
    'key46824': 'value68650',
    'key30503': 'value81645',
    'key63782': 'value42486',
    'key1803': 'value57467',
    'key16178': 'value46912',
    'key37921': 'value81421',
    'key82784': 'value97269',
    'key29152': 'value89738',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Carol Barnett',
    'address': '4777 Frank Cape Apt. 775\nCynthialand, CA 12709',
    'text': 'Change trouble wife bar break win. Effect middle describe save late actually under add. The gun none wall member thought generation. Write sort home despite here test traditional.',
    'email': 'wrodriguez@example.com',
    'phone_number': '+1-934-523-5569x445',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Robert Baker',
    'Elizabeth Moreno',
    'Charles Ellison',
    'Isabella Logan',
    'Sheena Williams',
    'Anthony Baker',
    'Sarah Wagner',
    'Larry Ferguson',
],
    'json': {
    'name': 'Tracy Hamilton',
    'address': 'Unit 1604 Box 8547\nDPO AE 29020',
},
    'key50113': 'value30687',
    'key63241': 'value98815',
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
    'RequestId': '9598d621-62ef-11f0-8a6e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_38_501153ONZaZzUv',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-2]_1752744159.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId3210021752744159Json()
    test.run_tests()
