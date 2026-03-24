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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-1]_1752744110_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-1]_1752744110.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId12810011752744110Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-1]_1752744110.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-1]_1752744110.json"
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
    'RequestId': '782e3dda-62ef-11f0-847a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_49_148637CwNhFTqn',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
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
    'RequestId': '784d29f6-62ef-11f0-a1ab-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_49_148637CwNhFTqn',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Pam Clark',
    'address': '7238 Andrew Rue\nWest Valerie, MI 38942',
    'text': 'Company enjoy same among research nothing. Anyone television law arm.\nMaybe range executive bag language its.',
    'email': 'ttaylor@example.com',
    'phone_number': '+1-599-413-8113x0950',
    'array_int_dynamic': [
    4823,
],
    'array_varchar_dynamic': [
    'Cassandra Austin',
    'Dwayne Edwards',
    'Sara Smith',
    'Robyn Giles',
    'Lisa Romero',
    'James Brown',
    'Anthony Perkins',
    'Laura Kim',
    'Mary Lang',
],
    'json': {
    'name': 'Veronica Reid',
    'address': '7904 Robinson Parkway\nNorth Sandra, FL 34414',
},
    'key65295': 'value11086',
    'key20352': 'value9662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Natasha Brown',
    'address': '11199 Alexa Station Suite 334\nPort Caleb, MA 14906',
    'text': 'Military everything own experience technology see. Just agent minute finish agent affect easy.\nOutside sometimes benefit. Focus send challenge free animal expert yourself.',
    'email': 'christopher95@example.com',
    'phone_number': '001-949-994-7401x2049',
    'array_int_dynamic': [
    2079,
],
    'array_varchar_dynamic': [
    'Ashley Shepherd',
    'Kristie Payne',
    'Leonard Hicks',
    'James Clark',
    'Brandon White',
    'Matthew Simpson',
],
    'json': {
    'name': 'Mark Williams',
    'address': '258 Cooper Court Apt. 302\nSouth Stephanie, SD 45076',
},
    'key8985': 'value9215',
    'key37730': 'value62056',
    'key70961': 'value38923',
    'key70651': 'value32570',
    'key93965': 'value69119',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Renee Goodwin',
    'address': '374 Erik Mountains Apt. 195\nSmithberg, WY 86099',
    'text': 'Feel join company officer mission attack. Late trade green where then which.\nPhysical raise gas federal difference ok. Local option claim southern safe factor.',
    'email': 'orivera@example.net',
    'phone_number': '(875)207-8291x951',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Michael',
    'Tammy Howell',
    'Rebecca Nguyen',
    'Larry Jones',
],
    'json': {
    'name': 'John Koch',
    'address': 'PSC 9176, Box 2871\nAPO AP 86571',
},
    'key68143': 'value61452',
    'key35363': 'value65023',
    'key57832': 'value28583',
    'key95257': 'value74790',
    'key18767': 'value49538',
    'key79320': 'value58461',
    'key29753': 'value49206',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Javier Zavala',
    'address': '596 Christopher Roads Apt. 104\nAlexton, GA 69810',
    'text': 'Sign us inside cut off source share. Receive law record represent structure.\nSport interest suddenly house service. Company debate parent rise perform use since. Available place decide.',
    'email': 'torresrebecca@example.com',
    'phone_number': '+1-257-563-2982',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Hall',
],
    'json': {
    'name': 'Gloria Parker',
    'address': '1503 Kenneth Haven\nNorth Ginaborough, LA 10177',
},
    'key19775': 'value27491',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Sheri Stephens DDS',
    'address': '95275 Griffin Divide Suite 560\nSouth Seanview, AZ 56997',
    'text': 'Artist daughter suddenly candidate. Sister themselves couple force me recognize. Behind set increase kid whether page situation.',
    'email': 'shannon56@example.com',
    'phone_number': '579-651-7311x9373',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Garcia',
    'William Blake',
    'Stephanie Middleton',
    'Brandy Cook',
    'Stacey Best',
],
    'json': {
    'name': 'Jorge Owens',
    'address': '23245 Suzanne Walks Apt. 810\nEast Jaredside, RI 17763',
},
    'key935': 'value63784',
    'key57022': 'value40855',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Timothy Green',
    'address': '59537 Brown Trace Apt. 708\nNorth Johnview, AK 15741',
    'text': 'To call agree increase case suggest may. System discuss discussion.\nSame fish training pattern. Interesting party dream turn option year model. Value sure near various magazine.',
    'email': 'christinamunoz@example.com',
    'phone_number': '899.914.5344x7086',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Salazar',
    'Karen Warren',
    'David Miller',
    'Cameron Jackson',
    'Mr. Joseph Smith',
    'Jacob Price MD',
],
    'json': {
    'name': 'Noah Hill',
    'address': 'USNV Mercer\nFPO AA 04129',
},
    'key83491': 'value45046',
    'key17885': 'value87245',
    'key75402': 'value71360',
    'key59946': 'value22329',
    'key70783': 'value11203',
    'key69038': 'value32950',
    'key44001': 'value17933',
    'key69925': 'value34750',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Todd Frank',
    'address': '76828 Gabriel Groves Suite 303\nWest Shane, WA 42847',
    'text': 'Human activity people recently station give different. Movie itself charge nation technology stay. Other final much approach town food.',
    'email': 'bruce37@example.net',
    'phone_number': '+1-304-953-1224x6502',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Kane',
    'Stephen Thompson',
    'Lance Anderson',
    'Frederick Murphy',
    'Stephanie Gonzalez',
    'Cameron Gonzales',
],
    'json': {
    'name': 'Brittany Smith',
    'address': '4645 Bobby Circle Suite 040\nRebeccamouth, ME 75977',
},
    'key30523': 'value58518',
    'key45607': 'value33019',
    'key59616': 'value89788',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jacob Davis',
    'address': '81625 Travis Common\nSouth Michaelfort, PR 06126',
    'text': 'Quickly writer task mention never though book. Film reason reach director enjoy.\nWater purpose suggest nice show. Your practice Republican media check.',
    'email': 'scott16@example.com',
    'phone_number': '944.947.2649x573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brian Thompson',
    'Kimberly Frazier',
    'Martin Hicks',
    'Samantha Cole',
],
    'json': {
    'name': 'Tracey Higgins',
    'address': '38098 Jacqueline Course\nWilliamsburgh, ND 05021',
},
    'key55217': 'value63963',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Angel Jackson',
    'address': '00672 Christine Crossing Apt. 750\nPort Josephside, NY 19397',
    'text': 'Wall language inside because success. If little build also theory garden owner.\nBreak majority result effect especially describe finish.',
    'email': 'andreagriffin@example.com',
    'phone_number': '967-296-6031',
    'array_int_dynamic': [
    54769,
],
    'array_varchar_dynamic': [
    'Jessica Robinson',
    'Daniel Moran',
    'Joseph Delgado',
    'Christine Garcia',
    'Lori Garcia',
    'Megan Osborne',
    'Sarah Garcia',
    'Gregory Turner',
    'Sarah Dixon',
    'Wanda Gross',
],
    'json': {
    'name': 'Cynthia Powers',
    'address': 'PSC 7286, Box 3078\nAPO AE 52169',
},
    'key69456': 'value53050',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Carolyn Spencer',
    'address': 'USCGC Ferguson\nFPO AA 23229',
    'text': 'Sea show state network mouth of. Real site our back stand.\nNote majority shake take. Democratic medical later wait live anyone radio.',
    'email': 'zreyes@example.net',
    'phone_number': '602.404.5079x44906',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Mitchell',
    'Lisa Smith',
],
    'json': {
    'name': 'Amanda Gonzalez',
    'address': '786 Powell Dale Suite 520\nCynthiaton, FM 99355',
},
    'key13362': 'value14291',
    'key57560': 'value31722',
    'key10846': 'value78002',
    'key27602': 'value71945',
    'key6429': 'value98460',
    'key8658': 'value23889',
    'key64854': 'value5073',
    'key98679': 'value80627',
    'key59042': 'value36880',
    'key57545': 'value75525',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Lindsey Mitchell',
    'address': 'USS Hernandez\nFPO AE 61077',
    'text': 'Be enter top manager short. Stuff charge entire market.\nNature help again view. Ever that guy wrong.\nPay fine cut ago.',
    'email': 'owensemily@example.org',
    'phone_number': '282.639.2036x76522',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Beth Thompson',
    'James Anderson',
    'Erica Patrick',
    'Vicki Rios',
    'Austin Phillips',
    'James Ramsey',
    'Peter Oconnell',
],
    'json': {
    'name': 'Steven Davis',
    'address': '15633 Jared Extensions\nSouth Fred, FL 78766',
},
    'key78575': 'value76892',
    'key34521': 'value89811',
    'key22416': 'value76005',
    'key76699': 'value89417',
    'key39950': 'value12373',
    'key30109': 'value87901',
    'key72714': 'value91383',
    'key67872': 'value88111',
    'key8541': 'value44486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Pamela Frank',
    'address': '7388 Burgess Centers\nEast Vickiview, RI 28876',
    'text': 'Despite not offer see certain. Short heart go indicate.\nFull that leg area particular carry me. Explain store officer cold situation.',
    'email': 'amberjackson@example.org',
    'phone_number': '383.613.5831x1045',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Laurie Murphy',
    'Rebecca Zhang',
    'Monica Peters',
],
    'json': {
    'name': 'Todd Lawson',
    'address': '8243 Roger Ferry Apt. 909\nEast Sarahstad, KY 44828',
},
    'key98223': 'value59',
    'key80685': 'value99338',
    'key42851': 'value48667',
    'key80538': 'value21974',
    'key93847': 'value40900',
    'key41666': 'value45230',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Christopher Alvarez',
    'address': '992 Sullivan Pass Apt. 450\nRebeccaside, MT 33570',
    'text': 'Behind everything husband. Structure off pay kitchen. Seek over middle generation behind visit visit note.\nEarly interesting on herself. Condition series analysis score. Drop allow one exist data.',
    'email': 'morenorobin@example.net',
    'phone_number': '999-404-5799x452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amy Bailey',
    'Hailey Wilson',
    'Gary Evans',
    'Jennifer Sampson',
    'Wendy Rodriguez',
    'Heather Becker',
    'Dr. Adam Jenkins',
    'Edward Smith',
    'Mark Jordan',
],
    'json': {
    'name': 'Randall Martin',
    'address': 'PSC 7826, Box 3711\nAPO AP 59218',
},
    'key90330': 'value41851',
    'key59757': 'value49235',
    'key52830': 'value59202',
    'key82574': 'value71494',
    'key90721': 'value64391',
    'key33964': 'value25513',
    'key89653': 'value79681',
    'key80245': 'value65527',
    'key46049': 'value70663',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'David Trevino',
    'address': '7886 Diane Dale\nEast Donnaton, RI 31246',
    'text': 'Collection tend billion section. Create south financial raise school. Hotel glass fear. Game represent bad.',
    'email': 'jhancock@example.com',
    'phone_number': '+1-749-845-1145x854',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Curtis Jackson',
],
    'json': {
    'name': 'Mr. Mark Jenkins',
    'address': 'USNV Marquez\nFPO AA 75936',
},
    'key22314': 'value37609',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Bianca Hill',
    'address': '033 Anthony Vista\nPort Jasonville, GA 87900',
    'text': 'Who factor director occur current responsibility study shake. Level memory interesting station.\nCarry single news whose add. Rock eight two year appear. Among grow three sound.',
    'email': 'uwilliams@example.net',
    'phone_number': '(910)926-9082x190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Schultz',
    'Renee Bender',
    'Janet Flynn',
    'Andrew Booth',
    'Robert Mendoza',
    'Sandra Park',
    'John Wilson',
    'Richard Smith',
    'Annette Russo',
],
    'json': {
    'name': 'Samuel Washington',
    'address': '09248 Jaime Forks\nNewtonfurt, IA 34465',
},
    'key55815': 'value31650',
    'key64743': 'value76718',
    'key72825': 'value46505',
    'key13717': 'value63154',
    'key44236': 'value58455',
    'key32306': 'value91944',
    'key45850': 'value2213',
    'key55844': 'value63982',
    'key58436': 'value87634',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Deborah Juarez',
    'address': '565 Larry Bridge\nJillside, ME 99222',
    'text': 'Different hot provide anyone Congress interview. All movement station. Drop church what all.',
    'email': 'tracy40@example.net',
    'phone_number': '(689)440-9948',
    'array_int_dynamic': [
    73593,
],
    'array_varchar_dynamic': [
    'Daniel Mercado',
    'Marie Adams',
    'Grace Huff',
    'Jeffrey Mcgrath',
    'Madeline Rodriguez',
],
    'json': {
    'name': 'Tiffany Krause',
    'address': '21019 Moss Freeway\nNew Davidland, MO 79347',
},
    'key47106': 'value40340',
    'key84526': 'value47927',
    'key44784': 'value77449',
    'key29637': 'value37209',
    'key11325': 'value36721',
    'key95928': 'value64532',
    'key74271': 'value7046',
    'key63856': 'value88100',
    'key24391': 'value80352',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Kristin Gregory',
    'address': '68458 Campbell Mews Suite 563\nKaylamouth, NH 96021',
    'text': 'Home box accept military. Minute really or foot face.',
    'email': 'whitecarla@example.net',
    'phone_number': '449-491-0076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Howell',
    'Joseph Welch',
],
    'json': {
    'name': 'Timothy Castro',
    'address': '7800 Vazquez Unions\nLake Tiffany, PA 87763',
},
    'key32068': 'value9037',
    'key89339': 'value22366',
    'key21768': 'value5141',
    'key11725': 'value85027',
    'key94805': 'value5318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Timothy Mcgee',
    'address': 'PSC 4510, Box 2659\nAPO AA 69503',
    'text': 'Enjoy baby then want seem president white. Establish ready much beat force shake go. Available rule rather will.',
    'email': 'matthewjohnson@example.org',
    'phone_number': '001-459-495-1274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sheila Brown',
    'Christopher Wade',
],
    'json': {
    'name': 'Lisa Stone',
    'address': '3115 Shannon Port\nWelchberg, IL 36339',
},
    'key58917': 'value51606',
    'key3789': 'value50875',
    'key80090': 'value37972',
    'key46753': 'value69640',
    'key59971': 'value13037',
    'key67701': 'value85757',
    'key59428': 'value64250',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Desiree Valdez',
    'address': '5431 Avery Islands\nNew Timtown, MD 74561',
    'text': 'Amount manage myself cover return three common. Work tax only.\nThreat hot hear role.\nCampaign floor source. Act growth from economic to participant real. Him drop establish.',
    'email': 'fgregory@example.net',
    'phone_number': '001-562-556-3873x018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Curtis',
    'John Booth',
    'Brittany Ramsey',
    'Jason Velasquez',
],
    'json': {
    'name': 'Keith King',
    'address': 'PSC 6082, Box 2532\nAPO AA 19123',
},
    'key32756': 'value97297',
    'key77710': 'value86417',
    'key65946': 'value61009',
    'key6041': 'value20213',
    'key93001': 'value93739',
    'key40309': 'value98015',
    'key13712': 'value37806',
    'key93644': 'value23088',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Alan Perez',
    'address': '76113 Moore Causeway Apt. 521\nNorth Stephanieshire, WV 45544',
    'text': 'Generation energy suggest whatever everything energy. Close us task ago only miss trade trouble. Call than industry recognize simple goal war.',
    'email': 'randrews@example.org',
    'phone_number': '218.478.2394x4801',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Martinez',
],
    'json': {
    'name': 'Danielle Wood',
    'address': '0014 Alvarez Turnpike Apt. 662\nNorth Maria, NH 73861',
},
    'key98632': 'value48790',
    'key39755': 'value83647',
    'key10531': 'value16838',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Paul Lucas',
    'address': '00987 Sharon Ports Apt. 963\nEast Eduardoburgh, AL 16981',
    'text': 'Service imagine serve. Property level land particularly else bed term. Moment section return summer Mr treatment later.',
    'email': 'william06@example.com',
    'phone_number': '364-444-6043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Judy Crawford',
    'Jennifer Hodge',
    'Kristine Mays',
    'Kelly Floyd',
],
    'json': {
    'name': 'Julie Bradley',
    'address': '0957 Harris Hollow Suite 149\nWilliamston, KY 68581',
},
    'key30153': 'value14577',
    'key27131': 'value58564',
    'key72293': 'value10140',
    'key22012': 'value8647',
    'key59692': 'value88445',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Maurice Huang',
    'address': '895 Tina Spur Apt. 638\nKathleenland, CT 81416',
    'text': 'Fund sort according society start strategy. Blood note hour. Old especially everyone reality woman.\nLead nor several structure character beyond line. Person authority purpose cost. Full feeling now.',
    'email': 'zcunningham@example.com',
    'phone_number': '+1-671-372-0571x51122',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Anderson',
    'Leonard Martin',
    'Kevin Kent',
    'Angel Martinez',
    'Tony Jones',
    'Matthew Hart',
],
    'json': {
    'name': 'Chris Short',
    'address': '950 Valenzuela Overpass Apt. 918\nWalkerside, KY 68738',
},
    'key23872': 'value14538',
    'key21405': 'value49289',
    'key69848': 'value1765',
    'key86510': 'value15083',
    'key9639': 'value68765',
    'key85469': 'value51050',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Charles Brown',
    'address': '3781 Saunders Pines Apt. 941\nBlairburgh, DE 46557',
    'text': 'Sure after leader size. Dinner air add away company model. Eight front apply place scientist southern.\nCivil card memory lay administration direction site bad.\nAffect happy movement long compare.',
    'email': 'wolfeallen@example.net',
    'phone_number': '655-880-1174x794',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Sanders',
    'Jennifer Kaiser',
    'David Sanchez',
    'Ryan Cortez',
    'Jacqueline Fleming',
    'Matthew Carson',
    'Rhonda Mitchell',
    'Emily Beck',
    'Andrew Wall',
    'Donald Castillo',
],
    'json': {
    'name': 'Cynthia Houston',
    'address': '452 Martin Cliff Apt. 852\nLake Williamville, DC 63226',
},
    'key13835': 'value48289',
    'key55178': 'value66402',
    'key34414': 'value27839',
    'key80280': 'value76625',
    'key95999': 'value88095',
    'key23295': 'value94576',
    'key2567': 'value66464',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Carlos Sandoval',
    'address': '90942 Jessica Forge Suite 243\nEast Williamberg, DC 68683',
    'text': 'Stock treatment we. Send me indicate know view animal mission. Dinner difference sign skill.\nSure me town central music. Present phone house partner our sure.',
    'email': 'dennismorgan@example.com',
    'phone_number': '338-317-0577x82458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Anderson',
    'Julia Miller',
    'Tara Mcgee',
    'Amy Davis',
],
    'json': {
    'name': 'Katherine Young',
    'address': '917 Christopher Forest Suite 346\nPort William, NM 77277',
},
    'key11949': 'value90942',
    'key68464': 'value87825',
    'key5177': 'value89266',
    'key53166': 'value48248',
    'key82909': 'value64633',
    'key43477': 'value66934',
    'key98880': 'value99386',
    'key11644': 'value63586',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Amy Kelley',
    'address': '0002 James Stravenue\nRebeccaside, PW 34003',
    'text': 'Door their act public successful quality relate. Many herself and food along in.\nStandard site Mrs or southern true move. Also wall hope once catch far time yourself.',
    'email': 'jeremy65@example.org',
    'phone_number': '5145943868',
    'array_int_dynamic': [
    88475,
],
    'array_varchar_dynamic': [
    'David Riley',
    'Kara Atkins',
    'Daniel James',
    'Susan Stevens',
    'Dr. Scott Guzman',
    'Michael Graham',
    'Scott Marks',
    'Tamara Owens',
    'Allen Taylor',
    'Amy Campbell',
],
    'json': {
    'name': 'Todd Gonzalez',
    'address': '90788 Swanson Village\nEast Elizabeth, WY 15975',
},
    'key48355': 'value40075',
    'key2632': 'value73574',
    'key67366': 'value91271',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Anthony Brown',
    'address': '8488 Cruz Prairie\nNorth Nicholas, MA 93629',
    'text': 'Billion beautiful list meeting. Piece population play decade reveal star. Factor manage with travel apply bad painting federal. Close cup claim upon question authority science.',
    'email': 'vdominguez@example.net',
    'phone_number': '246-403-0504x65380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Destiny Choi',
    'Angela Cunningham',
    'Sean Freeman',
    'Christopher Wilson',
],
    'json': {
    'name': 'Roberto Ochoa',
    'address': '489 Morrow Roads\nLake Amandastad, NJ 76200',
},
    'key91328': 'value53392',
    'key71702': 'value37736',
    'key4072': 'value49024',
    'key80217': 'value35394',
    'key86145': 'value7387',
    'key70199': 'value92506',
    'key86860': 'value45219',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Vincent Molina',
    'address': '868 Matthew Springs Apt. 388\nCathybury, PA 11314',
    'text': 'Wish their win way forget act. Like capital last effect deep appear end. Notice carry over style bit story.\nPush impact those protect than never later. Reduce another law offer baby dog.',
    'email': 'hmann@example.org',
    'phone_number': '001-228-567-9994x71222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Moore',
    'Mark Carlson',
    'Wesley Quinn',
    'Anthony Thompson',
    'Robin Chang',
    'Gary Castro',
    'Jeffrey Gomez',
    'Cheryl Nixon',
    'Daniel Francis',
],
    'json': {
    'name': 'Brandon Compton',
    'address': '6784 Amber Gateway\nGaryton, AK 14325',
},
    'key5581': 'value68547',
    'key60994': 'value53671',
    'key60637': 'value12678',
    'key67188': 'value15231',
    'key23998': 'value76717',
    'key63305': 'value95161',
    'key7450': 'value17791',
    'key50475': 'value63060',
    'key56122': 'value1817',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jennifer Fuller',
    'address': '05470 Matthew Forges\nSouth Sarahport, VT 38880',
    'text': 'Issue personal wear throw. Court enjoy rich now sea.\nRest share edge. Trade start dinner pattern. Bad doctor player size series me toward.',
    'email': 'carolyn95@example.com',
    'phone_number': '(842)986-9401x52946',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Bethany Ross',
    'Alexandra Evans',
    'John Johnson',
    'Michael Ross',
    'Tina Barker',
    'Linda Kelley',
],
    'json': {
    'name': 'Phillip Thompson',
    'address': '01660 Kenneth Throughway Suite 777\nLake Albert, MI 45451',
},
    'key86053': 'value8031',
    'key84794': 'value98690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Tyler Taylor',
    'address': '869 Scott Bypass Suite 770\nNew Geoffreyberg, VT 09794',
    'text': 'Number ok instead woman. Believe its option recent choice. Create through result debate base remember black.',
    'email': 'rebeccasantana@example.org',
    'phone_number': '541.766.2346x710',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Peter Collins MD',
    'Jason Hernandez',
    'Douglas Miller',
    'Kelli Williams',
    'Erik Morris',
    'Robert Moody',
    'Brian Anderson',
],
    'json': {
    'name': 'Matthew Saunders',
    'address': '41601 Robert Park Suite 470\nJoseport, MP 98676',
},
    'key33802': 'value32797',
    'key81950': 'value89171',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Jeffrey Orr',
    'address': '309 Grimes Trace\nEast Evelynhaven, DE 19440',
    'text': 'Less successful where yet meet goal. Happy his sort threat draw.\nQuality realize next free. Allow radio nature thought step section benefit. Light shoulder process military.',
    'email': 'rbush@example.org',
    'phone_number': '001-952-497-8833',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Hawkins',
    'Jason Olson',
    'Mr. Anthony Murray',
    'Nicholas Smith',
],
    'json': {
    'name': 'Jill Roberts',
    'address': '7053 Eaton Garden\nSinghmouth, IA 54358',
},
    'key3938': 'value76969',
    'key33290': 'value26457',
    'key24832': 'value92241',
    'key97297': 'value49701',
    'key12936': 'value76884',
    'key47513': 'value36553',
    'key44247': 'value98118',
    'key66213': 'value20174',
    'key48011': 'value78524',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Andrew Mcconnell',
    'address': '7830 Moon Groves Suite 353\nCarrilloton, CT 98426',
    'text': 'Must authority matter. Resource study yet take view. Win agreement everybody interesting last offer.',
    'email': 'kathleengutierrez@example.com',
    'phone_number': '307-815-8324x1423',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jermaine Graham',
    'Shane Mckay',
    'Danielle Bryant',
    'Matthew Spencer',
    'John Davis',
    'Hailey Green',
    'Jerome Navarro',
    'Scott Gomez',
],
    'json': {
    'name': 'Nicole Gonzales',
    'address': 'PSC 5187, Box 8228\nAPO AP 07471',
},
    'key21873': 'value17667',
    'key78970': 'value33240',
    'key75888': 'value62268',
    'key25720': 'value47008',
    'key48706': 'value12495',
    'key87626': 'value6979',
    'key89456': 'value34254',
    'key96358': 'value49120',
    'key59437': 'value28784',
    'key84411': 'value15778',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Tina White',
    'address': '7043 Alexis Walk Apt. 621\nSouth Jasmineshire, MT 55002',
    'text': 'Reality rock measure property trade. Run assume we out identify.',
    'email': 'samanthadelgado@example.org',
    'phone_number': '4585457756',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Craig Olson',
    'Peter Travis',
    'Michael Jordan',
    'Timothy Ford',
    'Carol Kelley',
],
    'json': {
    'name': 'Patricia Mcintosh',
    'address': 'Unit 0470 Box 7364\nDPO AA 54226',
},
    'key70550': 'value72123',
    'key11415': 'value33527',
    'key86577': 'value45657',
    'key93817': 'value72725',
    'key86442': 'value46801',
    'key90067': 'value49969',
    'key45598': 'value62993',
    'key96563': 'value2166',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kimberly Lane',
    'address': '61057 James Highway Suite 482\nEast Jonview, OK 15095',
    'text': 'True three loss mouth fact challenge. Development keep shake too wall own indicate rise.\nWife democratic find assume worry. Take ground fall film.',
    'email': 'vsmith@example.net',
    'phone_number': '(559)655-8349x614',
    'array_int_dynamic': [
    43482,
],
    'array_varchar_dynamic': [
    'Cheryl Scott',
    'William Fry',
],
    'json': {
    'name': 'Jill Ward',
    'address': 'PSC 9217, Box 6602\nAPO AE 90397',
},
    'key86516': 'value47861',
    'key10243': 'value29501',
    'key55066': 'value28597',
    'key29766': 'value11647',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jared Hernandez',
    'address': '098 Virginia Trace Suite 079\nBrendamouth, KY 70545',
    'text': 'Home identify thank return necessary lead medical. Nature total watch member age black management.\nCompany dream mean hair charge add between. Rock guy purpose world process wife religious.',
    'email': 'erin14@example.org',
    'phone_number': '849.644.5908x6115',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Frank',
    'Mrs. Jill Walker',
    'Christian Green',
    'Susan Herrera',
    'Joel Booth',
    'Heidi Flores',
    'Michelle Palmer',
],
    'json': {
    'name': 'Charles Brown',
    'address': '845 Robert Pass\nClementsville, NH 79815',
},
    'key68453': 'value42791',
    'key17342': 'value36219',
    'key14661': 'value21443',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Tracy Hill',
    'address': '7829 Kimberly Flats\nEast Michaelmouth, MA 45188',
    'text': 'Minute face generation safe party spring. Apply move eye company. Among personal place Democrat common minute something. Cultural analysis wind teach tend author.',
    'email': 'wbradley@example.org',
    'phone_number': '213.998.2883x44780',
    'array_int_dynamic': [
    62092,
],
    'array_varchar_dynamic': [
    'Denise Lynn MD',
    'Tiffany Martinez',
    'Michael Anderson',
    'Gerald Fox',
],
    'json': {
    'name': 'Abigail Gardner',
    'address': '77775 Jessica Club\nSouth April, AS 59798',
},
    'key59472': 'value56325',
    'key18312': 'value76495',
    'key6480': 'value13237',
    'key33918': 'value88010',
    'key12479': 'value29636',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Ashley Myers',
    'address': '069 Leblanc Ranch\nJamesfurt, NV 08403',
    'text': 'Hospital growth house consider television difficult. Skin will help finish I. She audience break interesting deal.',
    'email': 'duffyjason@example.net',
    'phone_number': '570.311.6441',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Barr',
],
    'json': {
    'name': 'Megan Pacheco',
    'address': '74435 Jimenez Rapid Suite 504\nNorth Sandra, WI 05357',
},
    'key22570': 'value10941',
    'key93581': 'value44760',
    'key56926': 'value76720',
    'key73035': 'value80669',
    'key91139': 'value76611',
    'key65003': 'value16940',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Kim Gill',
    'address': 'USCGC Sullivan\nFPO AE 90270',
    'text': 'Among me purpose. Especially station year determine indicate school. Popular speak rich fact care understand.',
    'email': 'lisarobinson@example.org',
    'phone_number': '557-415-9993x5045',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Mcconnell',
    'Clinton Scott',
    'Dylan Evans',
    'Diana Harmon',
    'Jessica Ashley',
],
    'json': {
    'name': 'Michelle Braun',
    'address': '87627 Brock Circle\nJohnsonstad, OK 81593',
},
    'key59135': 'value540',
    'key11109': 'value78846',
    'key86844': 'value74764',
    'key21290': 'value8593',
    'key77563': 'value30330',
    'key54818': 'value24159',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Joel Sullivan',
    'address': '3695 Johnny Mountain Suite 574\nCharlesstad, GU 70196',
    'text': 'Sure market single good suffer character less.\nHeavy year scientist new bill increase own. Phone probably cold phone.\nIts tonight upon size. Daughter without tree community once church face sea.',
    'email': 'wallison@example.net',
    'phone_number': '361.390.9511',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jose Crawford',
    'Timothy Lawson',
    'Joshua Paul',
    'Jeffrey Gutierrez',
    'Mr. Adam Rose MD',
    'Charles Bates DVM',
    'Mary Thompson',
],
    'json': {
    'name': 'Sara Johnson',
    'address': '2393 Matthew Estate Suite 799\nNew Timothy, AL 30174',
},
    'key19866': 'value70126',
    'key26257': 'value13275',
    'key36348': 'value66733',
    'key54523': 'value14751',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Monica Mccoy',
    'address': '254 Joseph Street Suite 126\nMatthewshire, GA 34154',
    'text': 'Notice interview apply language former. Down themselves mind.\nLay drop table cut contain smile light. Ability central option people season.\nEarly feeling region four marriage.',
    'email': 'josephware@example.net',
    'phone_number': '939-285-1004x0196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Adams',
    'Ethan Ramsey',
    'Tanya Bradley',
    'Destiny Anderson',
    'Stephanie Carter',
    'Tara Miller',
    'Jason Mitchell',
],
    'json': {
    'name': 'Courtney Rodgers',
    'address': '00567 Green Avenue Apt. 325\nLake Stephenburgh, NJ 01378',
},
    'key7193': 'value18603',
    'key84840': 'value42205',
    'key89871': 'value11936',
    'key94574': 'value61239',
    'key75136': 'value44412',
    'key23022': 'value6233',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Laura Rodriguez',
    'address': '001 Stephanie Loaf Suite 917\nAngelafort, IL 05336',
    'text': 'Tough health community fact. Color business somebody able decision phone. Mother test young plan.\nAccept walk political plan north relationship break. Reality key firm language information gun Mrs.',
    'email': 'yfarmer@example.net',
    'phone_number': '(863)323-9442x1708',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Erickson',
    'Michael Lewis',
],
    'json': {
    'name': 'Chad Love',
    'address': '920 Foster Knolls Apt. 495\nNew Michaelfort, FM 79237',
},
    'key19201': 'value33134',
    'key57404': 'value90859',
    'key66123': 'value2737',
    'key89113': 'value71407',
    'key69088': 'value29643',
    'key37849': 'value38448',
    'key20322': 'value99898',
    'key96481': 'value41391',
    'key33934': 'value8595',
    'key79017': 'value49574',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jonathan Dominguez',
    'address': '4064 Michael Fork Suite 287\nWest Davidport, RI 19556',
    'text': 'Culture today stuff I. Assume per child media hand a ever.\nHeavy economic capital against ability himself. Discover career night leader meet. Drop health heavy compare while beautiful last in.',
    'email': 'browncolin@example.com',
    'phone_number': '285-779-7148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Laurie White',
    'Alexis Schmidt Jr.',
    'Stephen Hall',
    'Matthew Romero',
    'Cindy Cantu',
    'Jason Mitchell',
    'Richard Payne',
    'Christie Benson',
    'Morgan Davis',
    'Philip Rodriguez',
],
    'json': {
    'name': 'Sandra Carlson',
    'address': '9872 Wallace Street Apt. 058\nNew Jon, AK 24046',
},
    'key33423': 'value82444',
    'key21558': 'value79934',
    'key87695': 'value22328',
    'key81473': 'value87407',
    'key78573': 'value40841',
    'key85035': 'value58108',
    'key59108': 'value41772',
    'key83797': 'value84801',
    'key44355': 'value360',
    'key50396': 'value74427',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Michael Floyd',
    'address': '69184 Matthew Radial Apt. 140\nMercerburgh, OK 43502',
    'text': 'Change response treatment science. Lot church little compare friend resource. Future fill process human central opportunity toward.',
    'email': 'stephanie77@example.net',
    'phone_number': '001-592-940-8789x5629',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Stewart',
    'Bryan Dominguez Jr.',
    'Angela Hudson',
],
    'json': {
    'name': 'Shelley Brown',
    'address': '393 Hernandez Key\nPort Jerry, OR 02749',
},
    'key50485': 'value95330',
    'key17284': 'value10608',
    'key54363': 'value57021',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Barbara Arnold',
    'address': 'PSC 6669, Box 6495\nAPO AE 74946',
    'text': 'These but think cell image we. Section old seat sort hard. Decide bit pattern them.\nStory fire red street. Value media free require race walk develop Mr.',
    'email': 'james81@example.net',
    'phone_number': '543.953.7549',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Raymond Davis',
    'Victoria Thomas',
],
    'json': {
    'name': 'Mrs. Lori Moore PhD',
    'address': '342 Nichole Hills Apt. 777\nPort Roberto, GU 16044',
},
    'key81927': 'value22291',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Paul Mason',
    'address': '54732 Andrea Canyon\nLeburgh, WV 32826',
    'text': 'Finish loss official measure. Water member or tax deal.\nUnder easy avoid list. Plan hair figure until list.\nTechnology class must property brother hard try. Car speech language direction.',
    'email': 'jeffrey41@example.org',
    'phone_number': '816.443.9938x7213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Ramirez',
    'Benjamin Valdez',
    'Sherri Harris',
],
    'json': {
    'name': 'Kirk Rodriguez',
    'address': '8684 Collier Fort Apt. 168\nOrtegaside, AZ 97386',
},
    'key57507': 'value17104',
    'key99677': 'value82146',
    'key80552': 'value50913',
    'key69599': 'value68652',
    'key8546': 'value11556',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Dr. Ann Anderson',
    'address': '06545 Myers Mission Apt. 240\nBrittneyfort, LA 15862',
    'text': 'Him between throughout in great. Alone though doctor international.\nAccording start consumer never indicate. Cover describe similar social that.',
    'email': 'amandabrown@example.net',
    'phone_number': '819.767.6043x133',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Reyes',
    'Mark Morales',
    'Jesse Flynn',
    'Brittany Erickson',
    'Daniel Hahn',
    'Caleb Hall',
    'Tara Stewart',
    'Randy Schmidt',
    'Kenneth Vasquez',
],
    'json': {
    'name': 'Norman Wallace DDS',
    'address': '47586 Lopez Divide Apt. 270\nKyleborough, IL 56428',
},
    'key93047': 'value68237',
    'key80316': 'value34948',
    'key78593': 'value38130',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Lisa Gamble',
    'address': '9033 Butler Prairie Apt. 175\nWest James, MA 63705',
    'text': 'Option operation wide agent. Republican generation wear ball nature size. Event alone here very clearly cover white.\nWall community travel environmental professor. Wide meet effort red.',
    'email': 'mmartinez@example.net',
    'phone_number': '(604)612-4146x23739',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mary Johnson MD',
    'Eric Vasquez',
    'Jacqueline Cook',
    'Allison Dougherty',
    'Joanne Watson',
    'Aaron Smith',
    'Angela Arias',
    'Kevin Benson',
],
    'json': {
    'name': 'Anthony Parker',
    'address': '68288 Cunningham Rest\nPort Jennifer, VT 35855',
},
    'key25064': 'value53454',
    'key27136': 'value43318',
    'key92389': 'value45498',
    'key31349': 'value74556',
    'key97480': 'value79713',
    'key97973': 'value57471',
    'key78901': 'value85594',
    'key45431': 'value60471',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Patrick Ellis',
    'address': '1336 Christina Lodge\nNew Stevenhaven, LA 16709',
    'text': 'Keep wife pull main chair responsibility bit. Degree great indeed walk beautiful board girl technology.\nEast authority somebody meet blood. Over management stuff say.',
    'email': 'theresapage@example.com',
    'phone_number': '801-851-4072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lance Perez',
    'Leslie Carter',
    'Patrick Thomas',
],
    'json': {
    'name': 'Ricardo Norman',
    'address': '45159 Thomas Square Suite 451\nEast Davidborough, NH 70569',
},
    'key76065': 'value35536',
    'key71009': 'value83573',
    'key4298': 'value3240',
    'key84009': 'value43501',
    'key14622': 'value4817',
    'key32539': 'value57542',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Noah Scott',
    'address': '238 Joe Canyon\nWilliamfurt, MN 29888',
    'text': 'Actually star player air. Significant price no reveal apply start when.\nExperience travel American training kitchen without. Letter mind realize create often oil concern.',
    'email': 'nashholly@example.com',
    'phone_number': '600.979.3404x3798',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Salazar',
    'Cheryl Stevens',
],
    'json': {
    'name': 'Mariah Wells',
    'address': '066 Lawrence Manor Suite 328\nClaytonburgh, DC 63292',
},
    'key38340': 'value49686',
    'key9024': 'value38799',
    'key92500': 'value8910',
    'key46568': 'value79817',
    'key76099': 'value98705',
    'key23947': 'value1136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Mary Carrillo',
    'address': '4531 Alicia Island Suite 146\nBriannafurt, NV 09227',
    'text': 'Physical join century identify wait evidence require thought. Fill gas dream check part low film. Risk court also window edge.\nDark suddenly focus lead the. Me know help later why seven.',
    'email': 'yjones@example.com',
    'phone_number': '770.963.6954',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Rodgers',
    'Tina Melendez',
    'Andrea Haney',
    'Brandi Ayala',
    'Andrew Hall',
    'Caleb Sloan',
],
    'json': {
    'name': 'Dustin Robinson',
    'address': '2200 David Station Suite 260\nWest Erik, OH 00607',
},
    'key78672': 'value99074',
    'key16974': 'value36442',
    'key30936': 'value86421',
    'key32722': 'value73537',
    'key3997': 'value11111',
    'key58737': 'value68139',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Tammy Simpson',
    'address': '1690 Andrea Court\nPort Brandi, NV 03671',
    'text': 'Center southern themselves never area travel ask how. Story book low relate when present social.',
    'email': 'thompsontimothy@example.com',
    'phone_number': '5393667416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Shaw',
    'Steven Bowen',
    'Theresa King',
    'Bobby Mitchell',
    'Sabrina Poole',
    'Carrie Harris',
    'Mr. Anthony Mcmahon Jr.',
    'Lisa Brown',
    'April Chavez',
    'Michelle White',
],
    'json': {
    'name': 'Brittany Boyd',
    'address': '730 Jennings Extension Apt. 963\nWest Randystad, FM 97144',
},
    'key27931': 'value39615',
    'key53228': 'value43785',
    'key74685': 'value59669',
    'key58656': 'value44824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Charles Smith',
    'address': '336 Gardner Rest\nPort Jamesville, VT 39829',
    'text': 'College door college walk hope. Question sure writer fly law TV interesting.\nStrong important his. Increase watch serve before second.',
    'email': 'baldwintiffany@example.net',
    'phone_number': '001-720-402-1701x852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Corey Rangel DDS',
],
    'json': {
    'name': 'Yolanda Evans',
    'address': '55517 Ramirez Unions\nCaitlinshire, VI 72438',
},
    'key74329': 'value43637',
    'key73064': 'value64212',
    'key66540': 'value34435',
    'key1339': 'value26926',
    'key37264': 'value44495',
    'key42660': 'value35766',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Martha Herring',
    'address': '212 Brown Track Suite 604\nBrandonchester, AZ 90654',
    'text': 'Notice clearly sell above likely plan best much. Involve sense sister consider throw upon must. Level do bill safe. Per call one special debate laugh somebody.',
    'email': 'gregorypatel@example.net',
    'phone_number': '001-533-719-2273',
    'array_int_dynamic': [
    58275,
],
    'array_varchar_dynamic': [
    'Timothy Fisher',
    'Lisa Anderson',
    'Elizabeth Lee',
    'Shannon Jones',
    'Donald Butler',
],
    'json': {
    'name': 'Jim Douglas',
    'address': '291 Holloway Crescent\nMillerberg, AL 19514',
},
    'key64013': 'value90051',
    'key67565': 'value94575',
    'key23782': 'value32744',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Vincent Ross',
    'address': '361 Cook Fort Suite 116\nHaynestown, DE 40694',
    'text': 'Material range school Mrs stay go test. Series end both why the no paper.\nForeign break happen capital lead. Sell set fact agent other interview. Loss task you former hold.',
    'email': 'jakeeverett@example.org',
    'phone_number': '001-845-396-1242x86562',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Kirk',
    'Jonathan Ryan',
    'Jennifer Rodriguez',
],
    'json': {
    'name': 'Paul Mejia',
    'address': '03666 Daniel Lane Apt. 111\nWest Timothytown, VA 42881',
},
    'key87891': 'value82951',
    'key60359': 'value88526',
    'key23649': 'value93598',
    'key48260': 'value3257',
    'key2973': 'value17785',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Cynthia Ruiz',
    'address': 'Unit 0896 Box 0443\nDPO AA 75094',
    'text': 'Partner according news our order Mrs shake song. Politics him husband fish option.\nGuess why establish goal citizen collection across. Cold wall more oil item floor long.\nThan that way factor.',
    'email': 'hpollard@example.net',
    'phone_number': '387-403-4651x477',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Collier',
    'Sandra Butler',
    'Amanda Best',
    'Phillip Bowman',
],
    'json': {
    'name': 'Todd Zimmerman',
    'address': 'USCGC Page\nFPO AE 47353',
},
    'key71054': 'value38988',
    'key74581': 'value61126',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Karen Oconnell',
    'address': '55647 Pamela Streets\nNorth Aaron, ND 39806',
    'text': 'Over into sing above change. Store it everything store. Various field vote site fly suffer. Describe nearly culture.',
    'email': 'zoe21@example.org',
    'phone_number': '001-624-755-9407x474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Peter Hale',
    'Robert Wang',
    'Stacey Robinson',
    'Bradley Campbell',
    'Valerie Fischer',
    'Gregory Flores PhD',
    'Robert Griffin',
    'Christopher Gutierrez',
    'Denise Daniels',
],
    'json': {
    'name': 'Diane Brewer',
    'address': '4854 Sarah Street Apt. 190\nWest Michael, AR 29684',
},
    'key54969': 'value93929',
    'key59533': 'value83871',
    'key95416': 'value91181',
    'key3234': 'value89797',
    'key82460': 'value19674',
    'key22553': 'value62736',
    'key52914': 'value62927',
    'key85969': 'value48259',
    'key47001': 'value98353',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Bobby Raymond',
    'address': '8931 Stacy Inlet Suite 270\nNorth Joelborough, MA 52598',
    'text': 'Dog speak scene nearly bag. Cup last usually course nice baby. They practice before glass wall see.',
    'email': 'hillmary@example.org',
    'phone_number': '287.499.1689x13043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Russell Miller',
    'Randy Johnson',
    'Karen Olson',
    'Gilbert Phillips',
    'Angela House',
    'Joshua Buckley',
    'David Day',
    'Kaylee Ramirez',
    'Ronald Davis',
    'Sean Keith',
],
    'json': {
    'name': 'Nichole Hunt',
    'address': '259 Baker Burg\nAaronport, VI 88465',
},
    'key16664': 'value27050',
    'key33687': 'value824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Barbara Bennett',
    'address': '645 Mcdonald Circle Apt. 877\nLake Pamela, WV 10413',
    'text': 'Analysis board respond amount. Candidate fish think Democrat your information watch. Oil hear upon bag subject cut. Week fight land party east let.',
    'email': 'nicholewhite@example.com',
    'phone_number': '4159020420',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tara Russell',
    'Marie Gibson',
    'Wanda Clements',
    'Rick Baker',
    'Ryan Allen',
],
    'json': {
    'name': 'Alexandria Walker',
    'address': '31702 Johnson Mountains\nPort Carlos, GU 95257',
},
    'key45596': 'value44479',
    'key8775': 'value10716',
    'key31203': 'value42623',
    'key45181': 'value25419',
    'key36529': 'value85554',
    'key82500': 'value51695',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Anthony Delgado',
    'address': 'Unit 9307 Box 7202\nDPO AP 95900',
    'text': 'Stop alone might star candidate trial. Mouth kind center someone across skill full. Lawyer red box voice learn series perhaps poor.',
    'email': 'claytonlittle@example.org',
    'phone_number': '(788)686-1463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Emily Ramirez',
    'Crystal Wagner',
    'Matthew Miller',
    'Leah Alvarez',
    'Heather Perry',
    'Joshua Hernandez',
],
    'json': {
    'name': 'Stacy Warren',
    'address': '8052 Nguyen Cliff\nWest Katherineland, OK 08997',
},
    'key6133': 'value19251',
    'key83670': 'value36609',
    'key22561': 'value2594',
    'key80644': 'value15478',
    'key28936': 'value61115',
    'key21555': 'value95763',
    'key51486': 'value51719',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Mrs. Monica Walters DDS',
    'address': '26804 Michael Divide Suite 200\nChristinafurt, CT 51848',
    'text': 'Data future huge act officer child my.\nShake idea material realize next trial. Analysis quickly list sport staff.',
    'email': 'leechristopher@example.com',
    'phone_number': '(797)712-8007x05906',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Fisher',
    'Roy Turner',
    'Jaclyn Williams',
],
    'json': {
    'name': 'Jack Archer',
    'address': '72125 Hernandez Stravenue\nLake Lauren, SC 64075',
},
    'key6631': 'value96958',
    'key44886': 'value30277',
    'key5025': 'value52763',
    'key22884': 'value30797',
    'key4692': 'value35563',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'James Arnold',
    'address': '38036 Christopher Valley Apt. 850\nPort Mikechester, AK 73170',
    'text': 'Citizen word difference stop century evidence free final. Measure alone around card board magazine.',
    'email': 'stephanie48@example.com',
    'phone_number': '001-365-302-6103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brian Burns',
    'Andre Casey',
    'Mark Oneill',
    'Edward Bell',
    'David Rangel',
    'Nancy Schmidt',
    'Daniel Santos',
    'Mary Harper',
    'Kent Adams',
    'Paige Matthews',
],
    'json': {
    'name': 'Stephanie Glass',
    'address': '201 Joshua Oval Apt. 820\nDavidside, LA 63747',
},
    'key97897': 'value94165',
    'key30348': 'value38962',
    'key61843': 'value3122',
    'key63809': 'value71762',
    'key40197': 'value61649',
    'key71867': 'value74699',
    'key47065': 'value44248',
    'key11150': 'value66902',
    'key87236': 'value85969',
    'key72595': 'value81287',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Kenneth Lindsey',
    'address': '799 Tracy Knoll Suite 637\nPort Alyssaport, AK 90336',
    'text': 'Manager resource company everyone. Late nearly tax.\nScene crime interest stop factor throw. Vote example a foreign expert amount nothing realize. Leave site second and east guy.',
    'email': 'doughertynicholas@example.net',
    'phone_number': '(389)872-6008',
    'array_int_dynamic': [
    7878,
],
    'array_varchar_dynamic': [
    'Marie Jackson',
    'James Chambers',
    'Julia Johnson',
    'Joseph Turner',
    'Sharon Mason DDS',
    'Jocelyn Long',
    'Robert Singh',
    'Jennifer Porter',
],
    'json': {
    'name': 'Vincent Guerrero',
    'address': '120 Stefanie Summit Suite 900\nSouth Joshuaville, OK 27849',
},
    'key51528': 'value66677',
    'key92537': 'value26309',
    'key25670': 'value74641',
    'key25774': 'value39611',
    'key35927': 'value63544',
    'key38158': 'value98538',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Mr. Louis Williams',
    'address': '1759 Karla Brook\nKaufmanbury, MO 71921',
    'text': 'Huge or color like. Case face together design special authority chance generation.',
    'email': 'hannahcooper@example.com',
    'phone_number': '001-359-295-1000x433',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Ortega',
    'Bryan Mclean',
    'Julie Hamilton',
    'Lisa Moran',
    'Sandra Chandler',
    'Victor Rowe',
    'Jennifer Morse',
    'Christopher Roth',
],
    'json': {
    'name': 'Michael Powers',
    'address': '625 Patterson Loaf Suite 237\nMeghanburgh, MO 57905',
},
    'key30041': 'value3441',
    'key2254': 'value79157',
    'key67727': 'value77484',
    'key10254': 'value60555',
    'key47842': 'value926',
    'key72250': 'value16867',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Eric Mayo',
    'address': 'PSC 3966, Box 6904\nAPO AP 73534',
    'text': 'Note develop animal before inside suggest human the. Push discuss minute now school apply hair. Rest any central. Piece prevent success.',
    'email': 'allenthomas@example.net',
    'phone_number': '574-946-8605x62796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Bobby Smith',
],
    'json': {
    'name': 'Brittany Cabrera',
    'address': 'Unit 1351 Box 1164\nDPO AA 87291',
},
    'key9252': 'value1794',
    'key93863': 'value64652',
    'key69791': 'value94914',
    'key69199': 'value75418',
    'key70442': 'value4018',
    'key63736': 'value68703',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Terry Garcia',
    'address': '708 Victor Gardens Suite 354\nBarbaratown, VT 60001',
    'text': 'Its order situation good. By especially really practice within wife agent article. Believe build site participant may.\nWay general modern sound take.',
    'email': 'kellysanchez@example.org',
    'phone_number': '001-417-644-6151',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Wells',
    'Wendy Warren',
    'Melissa Kim',
    'James Torres',
    'Nicole Haynes',
    'Nicole Hensley',
    'Sarah Foster',
    'Cassandra Weber',
],
    'json': {
    'name': 'Ashley Pham',
    'address': '40469 Jacobs Isle Suite 395\nNew Sarahbury, UT 34036',
},
    'key92327': 'value71084',
    'key81755': 'value20682',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Victoria Franklin',
    'address': '1182 Campbell Village Apt. 716\nNorth Jennifer, PR 52751',
    'text': 'Brother later able read public eye blood. Site tonight write. Officer true trial see.',
    'email': 'heather98@example.net',
    'phone_number': '538-962-7554x372',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Richard Mason',
    'Sean Romero',
    'Alex Gould',
    'Christina Booth',
    'Darren Mcdonald',
    'Elizabeth Hernandez',
    'Robert Ramirez',
    'Lance Watson',
    'Vicki Hernandez',
    'Robert Booker',
],
    'json': {
    'name': 'Steven Jimenez',
    'address': '9321 Wheeler Spur Suite 890\nWest Joel, ID 66334',
},
    'key75021': 'value8464',
    'key72595': 'value1855',
    'key46485': 'value47520',
    'key10989': 'value46007',
    'key89053': 'value56932',
    'key51740': 'value39293',
    'key13841': 'value11569',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Timothy Johnson',
    'address': '7499 Franklin Village\nEast Madeline, SD 88042',
    'text': 'Particular respond nothing nearly these yet. Sure cost treat work report. Nothing north city easy east.\nAmount back study agreement news carry. Four professor husband property.',
    'email': 'jennifer91@example.org',
    'phone_number': '699-781-7449x02355',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Thornton',
],
    'json': {
    'name': 'Jason Nichols',
    'address': '5481 Joseph Stravenue Apt. 060\nWest Douglasview, IL 63453',
},
    'key39557': 'value67477',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Franklin Mcmahon',
    'address': '201 Dylan Motorway Apt. 574\nSouth Adam, ND 38557',
    'text': 'National tax purpose computer. Box tree four church. Example long accept various positive design agent.\nBoard clear church share investment room garden. Agent surface nature whatever offer trial.',
    'email': 'onealtracy@example.com',
    'phone_number': '001-858-231-3224x5996',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Krista White',
    'Adam Young',
    'Kathryn Bass',
    'Jimmy Krause',
    'Wanda Bailey',
    'Elizabeth Vazquez',
],
    'json': {
    'name': 'Joshua Parrish',
    'address': '1537 Barbara Well Apt. 768\nEast Rachel, OR 12531',
},
    'key42398': 'value39347',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Angela Smith',
    'address': '1980 Steven Pike\nNew Vanessa, MD 87126',
    'text': 'Pm model lose ahead much laugh dinner. System could bill move each Democrat surface manager.\nSuch wonder use Congress. Bed enough final scene bank avoid.',
    'email': 'marksmith@example.net',
    'phone_number': '911.265.0515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Jones',
    'Melanie Lam',
    'James Jones',
],
    'json': {
    'name': 'Joseph Cobb',
    'address': 'Unit 8336 Box 8965\nDPO AP 50772',
},
    'key12531': 'value45939',
    'key361': 'value26181',
    'key87548': 'value81842',
    'key13883': 'value82832',
    'key67774': 'value65317',
    'key26623': 'value35477',
    'key10356': 'value22513',
    'key75976': 'value86635',
    'key45494': 'value29948',
    'key6099': 'value40656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Jasmine Martin',
    'address': '267 Ortiz Bypass Suite 207\nCartermouth, AK 23120',
    'text': 'Describe mind election manage everyone. Require offer development son idea kind record wife.',
    'email': 'haileywilliams@example.org',
    'phone_number': '2857671361',
    'array_int_dynamic': [
    26568,
],
    'array_varchar_dynamic': [
    'Ryan Mcconnell',
],
    'json': {
    'name': 'Bryan Hansen',
    'address': '04924 Johnson Plaza\nPort Andreashire, PA 57010',
},
    'key83917': 'value90108',
    'key85813': 'value18456',
    'key60251': 'value11352',
    'key1467': 'value57130',
    'key3373': 'value55299',
    'key8584': 'value14630',
    'key84359': 'value16669',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Pamela Williams',
    'address': '190 Joseph Valleys Suite 945\nHaleymouth, OH 49488',
    'text': 'Another small likely situation away million space. Stuff fund although win street ground power. Nearly drop various low receive. Training north including everybody letter myself story.',
    'email': 'yjones@example.org',
    'phone_number': '+1-735-542-8535x1571',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Hanson',
    'Robert Mcguire',
    'Meagan Mendoza',
    'Jason Johnson',
    'Adrian Thomas',
    'Mr. Daniel Gross',
    'Jane Nichols',
],
    'json': {
    'name': 'Carly Garcia',
    'address': '0946 Davis Center\nEast Nicholasshire, CT 82623',
},
    'key52460': 'value90496',
    'key54401': 'value98805',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Debbie Lambert',
    'address': '31589 James Square Apt. 351\nGonzalezhaven, IA 21783',
    'text': 'Wish care east great age rest model. Successful body big item. Film main maybe budget.',
    'email': 'smithderek@example.com',
    'phone_number': '(295)751-0709x52311',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lori Benton',
    'Andrew Pierce',
    'Jennifer Good',
    'Xavier Elliott',
    'Lawrence Jackson',
    'Joseph Douglas',
    'Jason Guzman',
],
    'json': {
    'name': 'Kevin Young',
    'address': '51617 Mariah Square Apt. 571\nKarenshire, AR 71129',
},
    'key44910': 'value47777',
    'key36890': 'value63287',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Cory Johnson',
    'address': '1226 Bentley Forge Apt. 082\nNew Matthewside, SC 74854',
    'text': 'Wear fast whole before. Change but rate religious that.\nHalf suggest long no she. Deep bring into thought industry fact.',
    'email': 'phillipsnancy@example.com',
    'phone_number': '+1-477-542-9056x389',
    'array_int_dynamic': [
    10184,
],
    'array_varchar_dynamic': [
    'Michael Phillips',
],
    'json': {
    'name': 'John Henderson',
    'address': '73064 Nicholas Throughway\nLake Sandra, NJ 06181',
},
    'key30000': 'value80732',
    'key97332': 'value60080',
    'key27024': 'value90988',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Rebecca Cabrera',
    'address': '0345 Michael Stream Suite 536\nSandramouth, AZ 60561',
    'text': 'Cultural pressure card decide most appear sea speech. Trade try camera way. School parent audience.',
    'email': 'pwolfe@example.com',
    'phone_number': '970.446.6893',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Suarez',
    'Thomas Mcdonald',
    'Martha Short',
    'Ryan Rose',
    'Megan Martinez',
    'David Pierce',
    'Julie Gould',
    'Judith Mcmillan',
    'Cassandra Strickland',
    'Stephanie Roberts',
],
    'json': {
    'name': 'Karen Oneill',
    'address': '5290 Paul Meadows Apt. 464\nPort Wayneville, DC 65331',
},
    'key70994': 'value18777',
    'key34689': 'value93409',
    'key23035': 'value74890',
    'key35773': 'value50646',
    'key35688': 'value28744',
    'key14250': 'value53427',
    'key50721': 'value28835',
    'key63046': 'value60165',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Derrick Santos',
    'address': '835 Williams Passage Suite 981\nEast Randy, NY 72771',
    'text': 'Happy unit sport official about.\nBar little town. Account ground tree. Realize real development him enter director.\nOwn drive tree behavior. Suffer avoid benefit stand even admit.',
    'email': 'brownzachary@example.org',
    'phone_number': '001-277-820-0605x1492',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Holder',
],
    'json': {
    'name': 'Nicholas Zimmerman',
    'address': '8600 Daniel Tunnel Apt. 868\nJosephshire, MP 50394',
},
    'key82249': 'value145',
    'key47829': 'value36093',
    'key79559': 'value21239',
    'key82198': 'value62097',
    'key96609': 'value73363',
    'key88090': 'value43239',
    'key19477': 'value92396',
    'key12632': 'value26809',
    'key6625': 'value54399',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Leonard Tucker',
    'address': '0774 Garza Ville Apt. 680\nEast Ronald, NH 45825',
    'text': 'National imagine line rather hard. Amount join as risk Mr her. Same likely Democrat easy model site fight home.',
    'email': 'johnsonlogan@example.org',
    'phone_number': '715-927-6299',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Barajas',
    'Dr. Bradley Miller',
    'David Howell',
],
    'json': {
    'name': 'Matthew Richardson',
    'address': '2204 Laura Creek Apt. 761\nWest Brian, DE 73087',
},
    'key78315': 'value35476',
    'key52561': 'value95191',
    'key57906': 'value79868',
    'key78021': 'value20607',
    'key43981': 'value93836',
    'key60444': 'value96854',
    'key92199': 'value82600',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Jeffrey Dalton',
    'address': '2007 Jennifer Manors\nLake Natasha, MH 54686',
    'text': 'Take author important industry bag former report final. What try establish section. Friend big when tell worry sit she woman.',
    'email': 'tina30@example.net',
    'phone_number': '+1-909-811-4861x1874',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Knight',
    'David Guerra',
    'Ashley Flores',
    'Heather Willis',
    'Scott Webb',
    'Kimberly Valdez',
    'Benjamin White',
    'Eric Coleman',
    'Scott Robbins',
    'Christina Alvarado',
],
    'json': {
    'name': 'Jonathan Moore',
    'address': '277 Frederick Lights Apt. 663\nSouth Benjaminfort, MP 33717',
},
    'key30480': 'value43042',
    'key34808': 'value66444',
    'key51708': 'value7653',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Kimberly Johnson',
    'address': '40067 Smith Highway\nKelleyland, MA 23675',
    'text': 'Friend involve bed any war believe. Another close old difficult institution. Drop chance raise chance gas determine out.\nMy apply bill education throughout money me.',
    'email': 'luke23@example.org',
    'phone_number': '914-743-1303x85331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Ramos',
    'Christopher Cox',
    'Shane Shaw',
    'Jessica Johnson',
],
    'json': {
    'name': 'Kathryn Brock',
    'address': '065 Douglas Circle Suite 376\nBishopland, WV 22006',
},
    'key80851': 'value16514',
    'key74024': 'value21055',
    'key8306': 'value56196',
    'key36390': 'value81771',
    'key44978': 'value91829',
    'key72243': 'value31318',
    'key22361': 'value90691',
    'key41571': 'value95687',
    'key61952': 'value51870',
    'key88611': 'value368',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'John Rodriguez',
    'address': '85334 Paul Port\nPort Davidland, KS 65045',
    'text': 'Building difficult factor.\nTonight feel marriage knowledge available audience. Develop all situation spring police.',
    'email': 'mcasey@example.com',
    'phone_number': '001-349-251-6568x185',
    'array_int_dynamic': [
    41365,
],
    'array_varchar_dynamic': [
    'Laurie Moreno',
    'Rhonda Parker',
    'Raymond Baker',
    'Luis Webb',
    'Robert Rodriguez',
    'Candice Becker',
],
    'json': {
    'name': 'Danielle Kelly',
    'address': '04409 Janice Estate Apt. 572\nNorth Erin, NV 19875',
},
    'key15713': 'value79323',
    'key95019': 'value81009',
    'key8747': 'value69257',
    'key92495': 'value44385',
    'key81490': 'value37700',
    'key11061': 'value76383',
    'key65292': 'value48515',
    'key26817': 'value47268',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Heidi Lewis',
    'address': '2700 Scott Crossing\nHillbury, AK 06112',
    'text': 'Threat poor tax trip media. Civil fear yes for history however. Cup series surface particularly example baby.\nLate lead by bad position threat value. Field more suggest whom inside series.',
    'email': 'wiseana@example.org',
    'phone_number': '+1-689-257-7565x6499',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Martin',
    'Cheryl Obrien',
    'Ricky Clark',
    'Kathleen Lopez',
    'Cynthia Griffith',
    'Alex Flores',
],
    'json': {
    'name': 'Rachel Kelley',
    'address': '199 Kristin Turnpike Suite 607\nNorth Pamela, MD 88888',
},
    'key37899': 'value57197',
    'key44630': 'value29356',
    'key92012': 'value85595',
    'key93644': 'value84159',
    'key34789': 'value6757',
    'key53673': 'value23595',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Aaron Brown',
    'address': '9486 Elizabeth Plaza\nWest Yvonne, SD 12329',
    'text': 'Condition firm ahead green few thousand. Information trip discussion to lead edge character.\nCatch special than he cut interview space.',
    'email': 'ywebb@example.org',
    'phone_number': '(615)403-8900x7101',
    'array_int_dynamic': [
    66077,
],
    'array_varchar_dynamic': [
    'Victoria Duffy',
    'James King',
    'Brandon Schmidt',
    'Karen Reynolds',
    'Holly Henry',
],
    'json': {
    'name': 'Austin Jones',
    'address': '439 Holder Mill Suite 942\nValenciabury, AR 74498',
},
    'key23824': 'value87663',
    'key81685': 'value82952',
    'key58044': 'value53604',
    'key63350': 'value18386',
    'key79905': 'value52036',
    'key50247': 'value36052',
    'key61207': 'value37816',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Michael Bautista',
    'address': '40215 Brenda Lodge Apt. 478\nNew Ryan, MO 46981',
    'text': 'Single rise reach scientist own meeting alone. Better doctor party describe treat small coach business.\nPretty nation strategy operation cold nice wonder several. Low better movie effect walk charge.',
    'email': 'cynthiachase@example.org',
    'phone_number': '+1-662-311-7303x27806',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Peters',
    'Joseph Wood',
    'Harry Bowers',
    'Jacob Smith',
    'Mary Sherman',
    'Sherry Mcintosh',
    'Sean Wright',
    'Maria Griffin',
],
    'json': {
    'name': 'Emily Smith',
    'address': '530 Kimberly Ports\nEast Stephanie, PR 45337',
},
    'key62505': 'value90018',
    'key20785': 'value9106',
    'key99065': 'value89501',
    'key11082': 'value37506',
    'key62148': 'value40804',
    'key62864': 'value55790',
    'key11072': 'value75644',
    'key90518': 'value71410',
    'key40672': 'value61465',
    'key34104': 'value95658',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Mrs. Sharon Ali',
    'address': '65737 Lauren Meadows Apt. 048\nMichaelbury, ND 19468',
    'text': 'Husband church like down son.\nPiece development fact boy shoulder let. Country record three this heavy accept.',
    'email': 'sharon10@example.org',
    'phone_number': '(766)453-6900',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Clark',
    'Pamela Meza',
    'Mrs. Cynthia Kent MD',
    'Phillip Johnson',
    'Judy Adams',
    'David Herrera',
    'Erik Berry',
    'Sheri Shaw',
    'Dominique Duarte',
    'Lonnie Bernard',
],
    'json': {
    'name': 'William Wiggins',
    'address': '981 Bentley River Apt. 202\nSheltonville, VI 51159',
},
    'key42965': 'value20292',
    'key18108': 'value62806',
    'key28594': 'value17213',
    'key66617': 'value75603',
    'key5194': 'value47956',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Gina Schneider DVM',
    'address': '3658 Dawn Mill\nGallagherport, MA 22007',
    'text': 'Challenge section worry fact follow total. Major hotel maintain. And out often personal offer different.\nMachine life minute.\nDoctor rather paper example risk me.',
    'email': 'thompsonamber@example.org',
    'phone_number': '001-871-886-8452x3832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Mcpherson',
    'Marie Wood',
    'Melanie Smith',
    'Christine Costa',
    'Michelle Walker',
    'Tamara Davidson',
    'Ashley Beasley',
    'Sabrina Carter',
    'Stacy Randolph',
],
    'json': {
    'name': 'Richard Watson',
    'address': '30203 John Islands Apt. 655\nNorth Devon, NV 92510',
},
    'key72237': 'value26642',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Kayla Grant',
    'address': '27474 Joseph Green Apt. 503\nNorth Samantha, MH 81169',
    'text': 'Better radio high west. Song get follow everything. Ago create listen national TV we.\nBed western light figure until.',
    'email': 'eschwartz@example.net',
    'phone_number': '723.537.3953',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Frederick Banks',
],
    'json': {
    'name': 'Daniel Cardenas',
    'address': '793 Gay Forge\nPort Cindy, UT 26319',
},
    'key18991': 'value48915',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'David Morgan',
    'address': '01411 Ward Shore\nStevenstad, UT 71679',
    'text': 'Writer fast gun notice.\nPressure effect measure hit strategy. Present machine scene spend who offer else carry. Range develop Democrat force meeting think.\nWhen member few table court would tonight.',
    'email': 'merrittkevin@example.net',
    'phone_number': '001-965-742-6908x6573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Johnson',
    'Rebecca Sandoval',
],
    'json': {
    'name': 'Molly Dixon DVM',
    'address': '830 Donovan Points Suite 912\nPayneville, MD 85129',
},
    'key21011': 'value55136',
    'key58399': 'value53061',
    'key31933': 'value14491',
    'key86282': 'value53536',
    'key79673': 'value98590',
    'key1506': 'value16393',
    'key46458': 'value18101',
    'key30795': 'value83799',
    'key15678': 'value48353',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Anne Garcia',
    'address': '737 Allen Run\nSpencerville, WY 37156',
    'text': 'Sea toward coach power might. Policy position prevent maybe finally plant. Window there finish good develop.\nGood two place medical people arrive. Prove along score among risk.',
    'email': 'henryscott@example.com',
    'phone_number': '444-469-4437x078',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Johnson',
    'Gregory Mendez',
    'Nicholas Garcia',
    'Ms. Martha Moran',
    'Aaron Wolf',
    'Mario Taylor',
    'Tina Callahan',
    'Shane Brown',
    'Matthew Becker Jr.',
    'Gregory Cherry',
],
    'json': {
    'name': 'Mr. Christopher Cooper',
    'address': '69681 Jones Inlet Apt. 588\nEast Marvin, ID 19589',
},
    'key40468': 'value6546',
    'key28339': 'value85383',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Walter Brown',
    'address': '8779 Hutchinson Prairie Apt. 217\nWest Elizabeth, IA 01557',
    'text': 'Rock huge product fear history job. Owner government become realize sea.\nBelieve example between past. Chair worker use happy surface politics.',
    'email': 'april10@example.net',
    'phone_number': '(431)566-9720',
    'array_int_dynamic': [
    13537,
],
    'array_varchar_dynamic': [
    'Ariel Torres',
    'Victor Carter',
    'Rachel Henderson',
    'Donald Carr',
],
    'json': {
    'name': 'Dr. Ashley Calderon',
    'address': 'Unit 4503 Box 4138\nDPO AP 98311',
},
    'key45939': 'value29491',
    'key8605': 'value23471',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Darrell Roberts',
    'address': '75122 Lewis Key\nNorth Jamesbury, NV 99831',
    'text': 'Have traditional you. Visit admit good so even smile move. Do campaign partner.',
    'email': 'isutton@example.org',
    'phone_number': '001-986-566-5664x8843',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Douglas',
    'Cynthia Wilson',
    'Tricia Jordan',
],
    'json': {
    'name': 'Stephen Ho',
    'address': '5227 Lucas Fork\nEast Christy, WA 83309',
},
    'key33039': 'value16758',
    'key68751': 'value8803',
    'key77261': 'value46082',
    'key89051': 'value63960',
    'key30262': 'value8601',
    'key54607': 'value64893',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Tyler Brown',
    'address': '311 Keith Junctions Apt. 466\nLake Tammyhaven, MS 45925',
    'text': 'Economy near film involve both law last student. House option newspaper main color charge.',
    'email': 'francisbrandon@example.net',
    'phone_number': '001-245-553-0501x460',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gina Mccullough',
    'Edward Gonzales',
    'Gabriel Jackson',
    'Jody Rodriguez',
    'Lauren Bryant',
],
    'json': {
    'name': 'Patricia Jones',
    'address': '2356 Buckley Inlet Suite 463\nRobertmouth, LA 01625',
},
    'key37268': 'value86218',
    'key37880': 'value77640',
    'key67262': 'value84913',
    'key65970': 'value76720',
    'key58739': 'value22913',
    'key71737': 'value35840',
    'key89764': 'value95013',
    'key6365': 'value78895',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Shelly Wallace',
    'address': '5865 Glenn Haven Apt. 011\nPort Mark, NY 71593',
    'text': 'Individual more window still thousand war. Explain computer huge product serious. Office free thus whose growth four politics.\nWith the myself prevent away couple rock.',
    'email': 'rgarcia@example.net',
    'phone_number': '(831)630-4484x290',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Williams',
    'Samuel Delgado',
    'Erik Williams',
    'Dr. Kim Lee',
    'Caitlyn Rodriguez',
    'Virginia Crosby',
    'Harold Mclean',
    'Sheila Garcia',
    'Grant Rivera',
    'John Martinez',
],
    'json': {
    'name': 'Kristina Taylor',
    'address': '45463 Diaz Drives Suite 250\nWest Lesliestad, PR 10456',
},
    'key56152': 'value15146',
    'key35658': 'value99873',
    'key33374': 'value20756',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Aaron Richard',
    'address': '56672 Joseph Radial\nWebsterview, GU 08976',
    'text': 'Question three wrong around one toward. Condition less draw manager growth.',
    'email': 'vmejia@example.com',
    'phone_number': '(850)493-7788',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lacey Montoya',
    'James Perez',
    'Alicia Torres',
    'Crystal Dunn',
    'Danny Ramirez',
    'Taylor Herrera',
    'Jose Velasquez',
    'Karen Ballard',
    'Steven Griffin',
],
    'json': {
    'name': 'Jennifer Andrews',
    'address': '09241 Rose Station\nNorth Joshua, HI 94544',
},
    'key53556': 'value39812',
    'key61473': 'value76447',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Maria Arnold',
    'address': '20568 Johnson Rapid Suite 617\nNew Erinhaven, IL 17323',
    'text': 'Training physical step current. Time deal tend president threat company. Current both financial street.\nSet development various wrong education deep. Order clear discuss kid into environment.',
    'email': 'cassandra07@example.org',
    'phone_number': '881-996-0216x03003',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Heather Davidson',
    'Jesse Mason',
    'Christopher Oneill',
    'Ann Rice',
    'Jonathan Thomas',
    'Gregory Flynn',
    'Bradley Mcdonald',
    'James Hansen',
],
    'json': {
    'name': 'Brian Goodman',
    'address': '755 Kathleen Fall Suite 464\nColleenfort, LA 26466',
},
    'key86055': 'value230',
    'key71429': 'value84597',
    'key85290': 'value15990',
    'key49109': 'value73301',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Rebecca Castro',
    'address': '618 Justin Flat Apt. 563\nSouth Stephanieville, NM 18258',
    'text': 'Keep firm agree heavy. Husband often especially soon make. Democratic watch stand offer social crime others scientist.',
    'email': 'krystalpierce@example.net',
    'phone_number': '441.299.6625',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Wallace',
    'Dawn Murray',
    'Jennifer Joyce',
    'Martin Long',
    'Brent Wang',
    'Felicia Hughes',
    'Lisa Bowers',
],
    'json': {
    'name': 'Rachel Martinez',
    'address': '34399 Moore Ramp\nWest Stephen, VI 55826',
},
    'key15806': 'value66062',
    'key49042': 'value65997',
    'key91753': 'value74391',
    'key1831': 'value80829',
    'key15434': 'value49905',
    'key38507': 'value28285',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Mrs. Elizabeth Henderson MD',
    'address': '444 Zachary Corner\nRalphton, FL 29119',
    'text': 'Good follow Mr run.\nTax fill good usually respond house. Guess sit figure establish. Hard price new hit probably pattern. Dark site put whole upon.',
    'email': 'tylertaylor@example.org',
    'phone_number': '001-734-620-0601x08444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Anna Roy',
    'Rachel Walton',
    'Elizabeth Roberts',
    'Alexander Harrison',
],
    'json': {
    'name': 'Matthew Austin',
    'address': '23720 Jefferson Junctions\nSuttonfort, AK 54186',
},
    'key73551': 'value72690',
    'key70318': 'value58162',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Dr. Denise Phillips',
    'address': 'PSC 8996, Box 0836\nAPO AA 33543',
    'text': 'Director mission language high newspaper skin. This prove majority low should.\nAhead black nice assume speak else. Recently lawyer bar technology.',
    'email': 'eknox@example.com',
    'phone_number': '001-458-695-3877x2993',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Susan Roberts',
    'Bobby May',
    'Ian Salazar',
    'Cynthia Williams',
    'Eric Baker',
    'Nathan Wallace',
],
    'json': {
    'name': 'Jeffrey Mccarty',
    'address': '3170 Emily Mall\nJonesview, MH 35636',
},
    'key73165': 'value52837',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Stephen Miller',
    'address': '4285 Jasmine Square\nPort Thomas, IN 09018',
    'text': 'Less prepare out. Center enjoy way issue.\nBase those simply laugh. Work somebody box without treat citizen three important. Piece performance pressure idea such loss color.',
    'email': 'gspencer@example.org',
    'phone_number': '754.621.3847',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kelsey Harper',
    'Michelle Green',
    'Alison Orozco',
    'William Evans',
    'Rebecca Vargas',
    'Nicole Maynard',
    'Carol Coleman',
],
    'json': {
    'name': 'Tyler Watson',
    'address': '22092 Lopez Mill\nEast James, HI 65963',
},
    'key28253': 'value3144',
    'key73999': 'value21015',
    'key16112': 'value80865',
    'key35858': 'value97035',
    'key77221': 'value87124',
    'key88423': 'value59959',
    'key82188': 'value31254',
    'key72992': 'value29327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Melissa Stephens',
    'address': '736 Cassandra Mountain Apt. 215\nNew Brandymouth, OR 53492',
    'text': 'Human practice point field poor environmental development.\nOpen phone statement best. According question young red campaign add.\nBase you least foreign win. Eat road current little drug.',
    'email': 'jgutierrez@example.com',
    'phone_number': '(927)595-5893x99354',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Heather Jenkins',
    'Miss Lisa Young',
    'Edward Cox',
    'Alyssa Trujillo',
    'Larry Rose',
    'Michaela Wong',
    'Stefanie Fischer',
    'Nicholas Solomon',
],
    'json': {
    'name': 'Amy Leonard',
    'address': '72530 Lloyd Circle Apt. 649\nLatashaville, NC 97444',
},
    'key40222': 'value4792',
    'key84612': 'value76269',
    'key11371': 'value14823',
    'key34237': 'value13472',
    'key30731': 'value7800',
    'key76679': 'value16652',
    'key95017': 'value80247',
    'key52943': 'value49639',
    'key75724': 'value69853',
    'key66018': 'value9123',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Erica Owens',
    'address': '4797 Stewart Islands\nNew Shaunport, PR 53594',
    'text': 'Finally explain sense star. Then future clearly film change sure. Tax few hair old reason control player.\nMay room human believe bank way. Child anyone western.',
    'email': 'joseph86@example.com',
    'phone_number': '333.296.0651',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Natasha Ramirez',
    'Edward Pacheco',
    'Cassandra Simpson',
],
    'json': {
    'name': 'Ashley Harris',
    'address': '688 Schultz Knoll\nEast Melvin, PW 96139',
},
    'key55641': 'value61503',
    'key26741': 'value89537',
    'key60731': 'value88209',
    'key95840': 'value8909',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Michael Wade',
    'address': '20296 Erin Island Suite 693\nNorth Jasmine, AS 73740',
    'text': 'Someone for question station future store. Television get oil probably cause past person dream. Before future open.',
    'email': 'amandawang@example.com',
    'phone_number': '001-850-889-4293x8181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Megan Walls',
    'Ashley Malone',
    'Daniel Bentley',
    'Christian Coleman',
    'Lauren Evans DDS',
    'Cassandra Grant',
    'Amy Shelton',
    'Tristan Farmer',
],
    'json': {
    'name': 'Jason Mccall',
    'address': '7858 David Ports Suite 442\nFordstad, CT 97698',
},
    'key24490': 'value32488',
    'key8559': 'value43493',
    'key88523': 'value58337',
    'key55885': 'value46094',
    'key3393': 'value48279',
    'key34007': 'value37552',
    'key48858': 'value67945',
    'key32544': 'value65998',
    'key37854': 'value94165',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Dr. Ronald Campbell',
    'address': '770 Felicia Manors\nSamanthaberg, CO 20209',
    'text': 'Along entire catch case. Deal peace he half. Home card middle matter agency civil mission.\nPull society ball change. Garden size study including natural son condition. Fight toward here.',
    'email': 'starkwilliam@example.net',
    'phone_number': '764.357.0668',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Martinez',
    'Jason Hill',
    'Amanda Hutchinson',
    'Olivia Smith',
    'Sharon Lynn',
],
    'json': {
    'name': 'Jeffrey Garcia',
    'address': 'Unit 2756 Box 5000\nDPO AP 18314',
},
    'key18184': 'value72415',
    'key33460': 'value2056',
    'key14619': 'value55145',
    'key27577': 'value46997',
    'key20491': 'value37240',
    'key52432': 'value5854',
    'key29648': 'value13690',
    'key7371': 'value97053',
    'key37375': 'value88660',
},
],
    'dbName': 'prod',
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
    'RequestId': '782e3dda-62ef-11f0-847a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_49_148637CwNhFTqn',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-100-1]_1752744110.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId12810011752744110Json()
    test.run_tests()
