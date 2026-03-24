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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-1]_1752744131_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-1]_1752744131.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId3210011752744131Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-1]_1752744131.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-1]_1752744131.json"
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
    'RequestId': '84f44e15-62ef-11f0-ad1e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_10_579318yeZNyuJH',
    'dimension': 32,
    'primaryField': 'id',
    'vectorField': 'embedding',
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
    'RequestId': '8519d2e4-62ef-11f0-a33c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_10_579318yeZNyuJH',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Shelby Willis',
    'address': '35027 Jacob Bypass\nStanleychester, TN 05584',
    'text': 'Ball smile crime college cultural building design sense. Ever to better whom.\nAnyone wife make glass matter card time know. Family just until travel. Respond treatment page society may what too.',
    'email': 'sergio76@example.net',
    'phone_number': '+1-434-514-6878x28439',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Nichols',
    'Amanda Cook',
    'Peter Smith',
    'Kristine Adams',
    'Rebecca Martin',
    'Thomas Allen',
    'Diana Floyd',
    'Nicole Jones',
    'Thomas Scott',
    'Dylan Dean',
],
    'json': {
    'name': 'Samuel Tucker',
    'address': 'USCGC Lee\nFPO AA 16011',
},
    'key29400': 'value30204',
    'key35436': 'value10729',
    'key80441': 'value39334',
    'key93666': 'value22719',
    'key10026': 'value32539',
    'key76882': 'value52854',
    'key17402': 'value29351',
    'key10627': 'value11964',
    'key75959': 'value42085',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Gerald Fitzgerald',
    'address': '19899 Kim Cliffs\nSchaeferton, NM 62011',
    'text': 'Section bar without herself candidate floor process wait. Better wide image opportunity personal. Early suddenly even wish win.',
    'email': 'brianna23@example.org',
    'phone_number': '831-642-5224x490',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Herman',
    'Andrew Turner',
    'Scott Snyder',
    'Katie Riley',
    'Elizabeth Hall',
],
    'json': {
    'name': 'Karen Evans',
    'address': '1109 John Fall Suite 421\nHeatherview, WY 73666',
},
    'key36382': 'value5218',
    'key30384': 'value59094',
    'key74870': 'value83743',
    'key2432': 'value10681',
    'key88662': 'value80624',
    'key43181': 'value13467',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Jacob Sanchez',
    'address': '0766 Mora Gardens Apt. 949\nEast Gregoryton, MT 15028',
    'text': 'Camera never old staff forget.\nYou movement oil. Article argue Republican.',
    'email': 'sean32@example.net',
    'phone_number': '9689849682',
    'array_int_dynamic': [
    68082,
],
    'array_varchar_dynamic': [
    'Kenneth Burnett',
    'Joseph Hall',
    'Donald Martinez',
    'Daniel Garcia',
    'Dennis Wilson',
    'Stacey Harris',
    'Joshua Clark',
    'Eric Blake',
    'Kimberly Burgess',
],
    'json': {
    'name': 'Brandi Hamilton',
    'address': '5437 Tammy Pine\nPort Thomas, SD 41701',
},
    'key34185': 'value74923',
    'key3023': 'value4481',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Mary Bryant',
    'address': '22482 Thomas Via Suite 808\nNew Kennethside, NJ 01734',
    'text': 'Purpose Democrat policy. Data house somebody. International food since material full town current.',
    'email': 'kurt53@example.com',
    'phone_number': '(988)233-3104',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alison Elliott',
    'Anita Miller',
],
    'json': {
    'name': 'Samuel Stewart',
    'address': '152 Stephenson Drives Apt. 303\nWilliammouth, WV 13232',
},
    'key45189': 'value6326',
    'key19163': 'value51018',
    'key20843': 'value4773',
    'key56868': 'value52044',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Ashley Nelson',
    'address': '27817 Ritter Forest\nEast Elaineborough, TN 55733',
    'text': 'Set toward enjoy on Democrat other operation weight. Leave arrive son ago would most spend foreign.\nMovie season itself power. Recently day us.',
    'email': 'youngjoe@example.org',
    'phone_number': '(718)986-4363x557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Miller',
    'Nicholas Livingston',
    'Brittney Collins',
],
    'json': {
    'name': 'Chelsea Howard',
    'address': '1567 Veronica Cove\nSouth Sarah, AZ 83265',
},
    'key98680': 'value42833',
    'key62487': 'value39379',
    'key12757': 'value47569',
    'key81069': 'value52692',
    'key92587': 'value36994',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Charles Underwood',
    'address': '6832 Lisa Mission Apt. 814\nPort Seanborough, OR 19947',
    'text': 'Require federal hot relationship.\nSix board remember guy particular firm. Weight put remember to write smile.\nSell assume direction score price central across rich.',
    'email': 'andersonkristin@example.com',
    'phone_number': '264-742-2693',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Aaron Kim',
    'Mr. Ian Blair',
    'Cheryl Wallace',
    'Christian Dickson',
    'Christine Good',
    'Mr. Jeremy Hudson MD',
    'Hailey Wilkinson',
    'Thomas Scott',
    'Timothy Henderson',
],
    'json': {
    'name': 'Lauren Shaw',
    'address': '527 Beth Islands\nGarzaburgh, MT 33262',
},
    'key46858': 'value97600',
    'key29002': 'value76755',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Robert Sutton',
    'address': '93979 Lopez Brooks Suite 930\nEast Jeff, KS 25451',
    'text': 'Style go positive build high high standard. Level positive trouble mission myself Republican. Action couple thing option debate you recently.\nScene week majority ability protect morning.',
    'email': 'damoncarlson@example.org',
    'phone_number': '863-586-3153x2488',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Angela Johnson',
    'Robert Ortega',
    'Judith Mason',
    'Melissa Wallace',
    'Marco Weber',
],
    'json': {
    'name': 'Nathaniel Hanna',
    'address': '126 Kelly Valley Suite 872\nEast Sarah, PR 57679',
},
    'key5410': 'value5210',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Bryan Solomon',
    'address': '348 Haley Fields\nArellanobury, IN 05513',
    'text': 'Marriage country street easy.\nBecome lot along I. Best city also crime.\nSense data thus share project necessary. Range top local course detail yard understand. Best ground example catch of plant per.',
    'email': 'jpayne@example.com',
    'phone_number': '(786)952-4561',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Karina Adams PhD',
    'Thomas Clay',
    'Richard Mendez',
    'Jessica White',
],
    'json': {
    'name': 'Jeffrey Flores',
    'address': 'USNV Johnston\nFPO AE 12866',
},
    'key23160': 'value65050',
    'key77486': 'value13553',
    'key45040': 'value15235',
    'key47715': 'value73679',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Thomas Cannon',
    'address': 'PSC 6439, Box 6606\nAPO AE 84329',
    'text': 'Conference stock forward agree argue. National including store keep. Cause attorney accept painting.\nRate race detail reflect picture. Fight fear education your myself suggest sense.',
    'email': 'brian89@example.net',
    'phone_number': '+1-944-694-4510x29190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Livingston',
    'Vanessa Blackburn',
    'Tammy Hansen',
    'Larry Byrd',
    'Charles Smith',
],
    'json': {
    'name': 'Zachary Smith',
    'address': '395 Jones Mills Suite 421\nKimberlyfurt, AL 04285',
},
    'key43282': 'value18721',
    'key14888': 'value33326',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Gary Griffith',
    'address': '8273 Mullins Forks\nGregoryborough, MO 51310',
    'text': 'Arm reduce figure culture individual feel choose. Sit eye arm. Mr school parent physical wife human.\nEvening second common specific. None left half sit sister. Morning partner side buy nature.',
    'email': 'omyers@example.net',
    'phone_number': '629.902.8992',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Rogers',
    'Karen Padilla',
    'Rebecca Pierce',
    'Gordon Ferguson',
    'Gabriel Murphy',
],
    'json': {
    'name': 'Nicholas Yang',
    'address': '876 Seth Drives\nAriasfort, NV 02446',
},
    'key4738': 'value57127',
    'key49374': 'value31756',
    'key33721': 'value32548',
    'key34660': 'value79973',
    'key6221': 'value18721',
    'key71052': 'value58900',
    'key60157': 'value59860',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'David Reed',
    'address': '01245 Sandoval Walks\nBarbaraberg, AL 76490',
    'text': 'Red stuff same. Specific trial grow require street voice event.\nCourse there American attention fear.\nCan expect eight sound deal drive. Use full send maintain through.',
    'email': 'katelyn26@example.com',
    'phone_number': '600.264.7956',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dominique Gray',
    'Bruce Molina',
    'Nathan Meadows',
    'Michael Elliott',
],
    'json': {
    'name': 'James Patterson',
    'address': '6590 Tyler Falls Suite 701\nGarciamouth, IL 14872',
},
    'key89633': 'value10072',
    'key32846': 'value38895',
    'key996': 'value80818',
    'key72660': 'value79987',
    'key97071': 'value35796',
    'key49446': 'value80188',
    'key83936': 'value84124',
    'key28652': 'value35646',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Michael Fleming',
    'address': '0374 Wesley Junction Suite 651\nLake Stephen, WI 79582',
    'text': 'Forget response picture quite. Rise finish under sometimes.\nDegree public hear reveal lawyer. Us officer outside draw woman successful. Year cultural always second.',
    'email': 'kryan@example.org',
    'phone_number': '+1-384-421-4387x8116',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Bobby Reilly',
    'Michael Johnston',
    'Gloria Solomon',
],
    'json': {
    'name': 'Emily Clark',
    'address': '037 Murray Drive\nTerrifurt, NM 89325',
},
    'key33559': 'value62232',
    'key4586': 'value16156',
    'key62314': 'value43438',
    'key38742': 'value38972',
    'key61548': 'value32187',
    'key30826': 'value94390',
    'key53762': 'value61622',
    'key4356': 'value32251',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Paul Morgan',
    'address': '4790 Amber Spur Apt. 497\nEast Troyshire, LA 83680',
    'text': 'We anyone phone page rich. Between good record reason model.\nPiece notice Mrs hit third operation. Company risk site court discuss.\nLevel gun market. Into time along view last very music fear.',
    'email': 'yross@example.com',
    'phone_number': '(647)564-9050x640',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Huang',
    'Shannon Stone',
    'Caitlin Brown',
    'Ashley Maddox',
],
    'json': {
    'name': 'Erika Robinson',
    'address': 'USNV Jennings\nFPO AA 34043',
},
    'key47972': 'value29081',
    'key70054': 'value8620',
    'key16177': 'value93467',
    'key87874': 'value43278',
    'key57065': 'value50911',
    'key3008': 'value40941',
    'key67033': 'value12909',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Bailey Manning',
    'address': '4210 Amy Ridges\nNelsonville, NM 39873',
    'text': 'No appear provide them together development leave. Cup daughter industry eye.',
    'email': 'sara90@example.com',
    'phone_number': '361-949-6705',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Priscilla Wilkerson',
    'Curtis Turner',
    'Erica Ruiz',
    'Courtney Wood',
    'Courtney Holt',
    'Deborah Brooks',
    'Nicholas Wilson',
    'Travis Riddle',
],
    'json': {
    'name': 'Sean White',
    'address': '36845 Nunez Rest Suite 726\nMooreburgh, AZ 33101',
},
    'key83667': 'value99665',
    'key80940': 'value70055',
    'key71775': 'value81259',
    'key73948': 'value61660',
    'key58865': 'value59114',
    'key39832': 'value51437',
    'key24371': 'value37912',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Jimmy Jones',
    'address': '3662 Haas Shore Apt. 893\nSouth Richardville, IL 43868',
    'text': 'Fear like certain according why grow what manage. Fly federal report.\nValue imagine training agent. Team road difficult although prepare rate. Heavy industry agree sing.',
    'email': 'ashley09@example.com',
    'phone_number': '778-812-3968x650',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Brewer',
    'Christopher Martin',
    'Sarah Gillespie',
],
    'json': {
    'name': 'Laura Newman',
    'address': '13181 Jeanette Fort\nPort Chelseastad, RI 31275',
},
    'key37285': 'value68630',
    'key1832': 'value44176',
    'key30221': 'value59014',
    'key37753': 'value49854',
    'key15597': 'value31488',
    'key88864': 'value59630',
    'key39968': 'value37488',
    'key21763': 'value818',
    'key33770': 'value60604',
    'key76623': 'value12435',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Patrick Hahn',
    'address': '149 Jose Island\nTimothyville, IN 50931',
    'text': 'Probably set blood major pressure practice. Want everyone thousand western government next concern action. Seem know sell cost kitchen.\nMovie that fill heavy big must community.',
    'email': 'daniel51@example.net',
    'phone_number': '001-602-624-1309x492',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Cunningham',
    'Kenneth Ortega',
],
    'json': {
    'name': 'Antonio Smith',
    'address': '510 Brown Station Apt. 013\nLake Meganstad, PW 61785',
},
    'key45291': 'value89148',
    'key79539': 'value94198',
    'key59787': 'value92327',
    'key47423': 'value87228',
    'key50605': 'value42450',
    'key64110': 'value29349',
    'key9592': 'value27205',
    'key3516': 'value71666',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Brooke Moore',
    'address': '4926 Pace Extension Suite 889\nBanksbury, MI 32290',
    'text': 'Above age church walk offer air. Job note kid law reduce less some off. Huge yes game year.\nLow area if idea we peace.',
    'email': 'kvaughn@example.net',
    'phone_number': '001-462-802-1630x3794',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Johnson',
],
    'json': {
    'name': 'Erin Love',
    'address': '04288 Jeremy Brook\nSouth Shawn, VI 57394',
},
    'key30177': 'value85920',
    'key20293': 'value52884',
    'key71753': 'value38221',
    'key86133': 'value68622',
    'key24281': 'value57521',
    'key15100': 'value28186',
    'key21577': 'value92556',
    'key90149': 'value37435',
    'key3174': 'value29006',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Amanda Hendricks',
    'address': '907 James Pines\nEileenborough, IA 22438',
    'text': 'Doctor away but bag.\nInstitution before clearly size pick treat. Government fill commercial type order candidate.\nFish a appear agree. Morning house glass majority cost.\nPolicy paper this push.',
    'email': 'wesley42@example.net',
    'phone_number': '001-215-502-9988x6967',
    'array_int_dynamic': [
    68505,
],
    'array_varchar_dynamic': [
    'Robin Irwin',
    'Linda Jackson',
    'Patrick Lawrence Jr.',
    'Matthew Chapman',
    'Michael Ellis',
],
    'json': {
    'name': 'Emily Smith',
    'address': '684 Nelson Via\nPort Paulland, OH 54637',
},
    'key27854': 'value2731',
    'key98223': 'value16651',
    'key66064': 'value16500',
    'key48827': 'value3540',
    'key90123': 'value82752',
    'key31773': 'value89332',
    'key8991': 'value32318',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Barbara White',
    'address': '7032 Angela Harbor Suite 937\nRobertport, VA 83578',
    'text': 'Industry property only act. While smile old task perhaps. Article player word.\nStudent far tree capital. Side movie how west become.\nOver rather official human as.',
    'email': 'ptaylor@example.net',
    'phone_number': '001-201-379-5838x60656',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Munoz',
    'David Lopez',
    'Mike Lee',
    'Miranda Leach',
    'Teresa Adams',
],
    'json': {
    'name': 'Daniel Murphy',
    'address': '38918 Payne Unions\nGarciaville, AS 48554',
},
    'key81744': 'value76956',
    'key87370': 'value44120',
    'key89612': 'value12050',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Carolyn Fischer',
    'address': '0444 Smith Island\nPamelaton, NC 90876',
    'text': 'Set new image least and phone. Heart top bit leg save wife.\nStation success artist way often general big. Coach one itself drive physical gas part. On simply which write.',
    'email': 'sanchezpaul@example.org',
    'phone_number': '(571)335-2862',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Phillips',
    'Anthony Williams',
    'Denise Stanley',
    'Paul Munoz',
],
    'json': {
    'name': 'Jason Henderson',
    'address': 'PSC 6629, Box 8187\nAPO AP 27964',
},
    'key74865': 'value12873',
    'key55320': 'value45536',
    'key46527': 'value53322',
    'key80910': 'value32461',
    'key76846': 'value31452',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Kevin Chang',
    'address': 'USCGC Wright\nFPO AA 24534',
    'text': 'Important born pull happen trip game. Able hear know painting. Meeting what off policy.\nHour again police. Follow all many seek. Will after wear compare.',
    'email': 'savannah01@example.org',
    'phone_number': '001-654-857-0288',
    'array_int_dynamic': [
    30487,
],
    'array_varchar_dynamic': [
    'Jonathan Dougherty',
    'Jason Allen',
    'Laura Hernandez',
    'Jerome Cox',
],
    'json': {
    'name': 'Marcus Gray',
    'address': 'Unit 7379 Box 8940\nDPO AA 06769',
},
    'key89903': 'value32173',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Sarah Rodriguez',
    'address': '747 Dennis Forge\nEast Annaview, WI 79304',
    'text': 'Fear form first focus. Personal worker difference.\nSeason near catch old middle despite. Fight our anyone.',
    'email': 'andrea00@example.org',
    'phone_number': '229.931.0039',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Carol Martin',
    'Julie Jenkins',
],
    'json': {
    'name': 'Bryan Hamilton',
    'address': '79960 Pam Streets\nBeckerfurt, NV 15004',
},
    'key94082': 'value2829',
    'key85019': 'value32845',
    'key35328': 'value81194',
    'key50150': 'value75721',
    'key96779': 'value81687',
    'key67487': 'value43891',
    'key20105': 'value56619',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Tanya Myers',
    'address': '7954 Rhonda Ville\nJordanmouth, CA 65013',
    'text': 'Positive computer area reason voice. Sense stop individual own base. Surface idea physical fill page table inside.',
    'email': 'harrisonkendra@example.com',
    'phone_number': '001-479-523-2826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'James Mullen',
    'Mary Nguyen',
    'Billy Mcdonald',
    'Connie Roth',
    'John Lamb',
],
    'json': {
    'name': 'Stephen Knight DVM',
    'address': '164 Booth Shores Apt. 618\nWest Bethberg, MO 83090',
},
    'key67332': 'value37474',
    'key18486': 'value93487',
    'key41921': 'value28476',
    'key84383': 'value85859',
    'key50': 'value95450',
    'key10438': 'value20127',
    'key63445': 'value3236',
    'key85448': 'value12494',
    'key15374': 'value2257',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Ms. Victoria Estes MD',
    'address': '14970 Melissa Lodge Suite 861\nEast Laura, ME 07402',
    'text': 'Sign sound term consumer. Focus choose hand sometimes father region individual guy. Agency really during drop defense arrive.',
    'email': 'markferguson@example.net',
    'phone_number': '001-934-617-2020',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joshua White',
    'Brandon Palmer',
    'Theresa Becker',
    'Julie Cruz',
    'Mary Fritz',
    'Matthew Gordon',
    'Erika Robles',
    'Laura Moore',
],
    'json': {
    'name': 'Brandon Davis',
    'address': '76248 Emily View\nSouth Angela, SC 81688',
},
    'key60076': 'value83772',
    'key90385': 'value54064',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Terry Marks',
    'address': '401 Craig Track Suite 733\nNew Alan, WA 47370',
    'text': 'Stop author read strategy. Force hair a soon increase particularly off.\nTough save loss morning. Minute view range hit both first.\nBegin something TV boy.',
    'email': 'julie22@example.org',
    'phone_number': '(743)777-1775x585',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Johnson',
    'Donald Johnson',
    'Regina Richards',
],
    'json': {
    'name': 'Thomas Ortega',
    'address': 'Unit 1329 Box 6117\nDPO AA 60159',
},
    'key59208': 'value8421',
    'key50308': 'value57817',
    'key1091': 'value81964',
    'key96135': 'value17311',
    'key17089': 'value65429',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Danielle Stark MD',
    'address': '691 Nguyen Isle Apt. 238\nTheresaside, LA 91595',
    'text': 'Concern billion speech a tough agree happen.\nFollow science seek music lay side. Wait society person end so dinner write. Job expect born reflect letter.',
    'email': 'brandycook@example.org',
    'phone_number': '001-306-663-4451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Frank Haas',
    'Kyle Mckenzie',
    'Christina Hawkins',
],
    'json': {
    'name': 'Tracy Klein',
    'address': 'USNS Davis\nFPO AE 78669',
},
    'key67250': 'value48262',
    'key79350': 'value94730',
    'key85348': 'value83720',
    'key74673': 'value68034',
    'key31499': 'value87814',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Sherry Reed',
    'address': '803 Martinez Ridges\nSmithmouth, MN 56442',
    'text': 'Truth close during way might bank. Like positive traditional authority yourself surface. After the dog main weight.',
    'email': 'obowen@example.org',
    'phone_number': '415.662.9665x3327',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Eric Brooks',
    'Amanda Armstrong',
],
    'json': {
    'name': 'John Pratt',
    'address': '2978 Benjamin Prairie\nRobertshire, KS 12476',
},
    'key74882': 'value99137',
    'key95768': 'value76524',
    'key65163': 'value75337',
    'key31005': 'value78210',
    'key95908': 'value29866',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Margaret Stevens',
    'address': '857 Alexis Plain Suite 764\nJessicatown, ME 44191',
    'text': 'Board represent clear memory someone only agreement. Modern program particularly.\nStreet space similar war situation five. Purpose investment thus piece.',
    'email': 'coopereric@example.org',
    'phone_number': '(545)693-0061',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Dylan Frey',
    'Jessica Wong',
    'Nancy Smith',
    'Jacqueline Dunn',
    'Ricardo Suarez',
    'Theresa Golden',
    'Bryce Velazquez',
    'Tiffany Mejia',
],
    'json': {
    'name': 'Tammy Patel',
    'address': '5399 Smith Wall Suite 536\nChristyborough, IN 62786',
},
    'key50753': 'value54189',
    'key97787': 'value79486',
    'key9349': 'value99256',
    'key10259': 'value64512',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Sean Hill',
    'address': '5987 Young Underpass\nNicoleport, WA 78967',
    'text': 'Too outside cell. Age process spring. Whether firm class believe unit good race attention.\nOperation they everyone sister so money north. These of can car mouth six to.',
    'email': 'ghernandez@example.net',
    'phone_number': '+1-235-487-4867x031',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Bates',
    'Stephen Knight',
    'Melvin Galvan',
    'Charles Jimenez',
    'Kevin Hart',
    'Wendy Miller',
    'Jessica Williams',
],
    'json': {
    'name': 'Patricia Mckenzie',
    'address': 'USNV Morton\nFPO AA 96020',
},
    'key46353': 'value40955',
    'key90816': 'value15437',
    'key89099': 'value10615',
    'key65920': 'value95544',
    'key85593': 'value47362',
    'key86121': 'value34353',
    'key32400': 'value34189',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Anthony Young',
    'address': '28720 Williams Burg Suite 966\nPort Joseph, NJ 50614',
    'text': 'Out charge reflect herself note. Whole less people need bar allow.\nAvoid pressure stop manage place result. List themselves thus or film stand institution. Take notice improve else.',
    'email': 'sryan@example.com',
    'phone_number': '9736809373',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Charlene Torres',
    'Michelle Lee',
    'Paul Keller',
    'Brittany Gray',
    'Cameron Silva',
    'Gary White',
    'Mitchell Curtis',
    'Taylor Dean',
],
    'json': {
    'name': 'Lauren Fischer',
    'address': '9638 Laura Park\nNorth Sylviaside, NM 67428',
},
    'key75624': 'value7187',
    'key56528': 'value90902',
    'key63361': 'value49372',
    'key93966': 'value26287',
    'key52007': 'value19448',
    'key81627': 'value56465',
    'key62549': 'value89046',
    'key42943': 'value79962',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'James Weber',
    'address': 'USNS Harrison\nFPO AA 57086',
    'text': 'Table summer really particular same top house. Number decide wonder season. Front age direction between present.',
    'email': 'wnewton@example.com',
    'phone_number': '001-500-291-3345',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Howard',
    'Michael Martin',
    'Maria Reynolds',
    'Lauren Anderson',
    'Tina Jackson',
    'Sharon Schmidt',
],
    'json': {
    'name': 'Timothy Brown',
    'address': '6283 Ashley Center Suite 241\nWest Jacqueline, PW 59709',
},
    'key30515': 'value36186',
    'key1859': 'value15276',
    'key38226': 'value81704',
    'key45080': 'value27670',
    'key78240': 'value32975',
    'key51552': 'value43341',
    'key65964': 'value64356',
    'key88742': 'value18841',
    'key40498': 'value44369',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Ashley Davis',
    'address': '7311 Rogers Village Apt. 686\nGuerramouth, OK 51603',
    'text': 'Ahead mean doctor nor sport street. Above interesting foreign sign.\nThousand close offer once those. Eight could tend order nor small song. Account save system magazine center government during.',
    'email': 'bettychan@example.net',
    'phone_number': '001-640-399-2261x569',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Carl Robbins',
    'Mary Young',
],
    'json': {
    'name': 'Amanda Vasquez',
    'address': '47128 Michael Corners\nNathantown, VT 16194',
},
    'key59459': 'value79269',
    'key43867': 'value26352',
    'key80945': 'value39114',
    'key32315': 'value23097',
    'key58135': 'value14738',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Karen Paul',
    'address': '051 Dawn Hollow\nSouth Patricia, VT 33304',
    'text': 'Education collection consumer top he agency although. Outside much long once. Rest less although hear keep.\nDebate four set enough bar popular. Indicate doctor military goal.',
    'email': 'shuff@example.org',
    'phone_number': '547-737-8008',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Emily Mcfarland',
    'Robert Ellis',
    'Ashley Leonard',
    'Michael Wiley',
    'Lisa Mccarthy',
    'Tamara Nguyen',
],
    'json': {
    'name': 'Lee Hart',
    'address': '685 Jason Mews\nClaytonside, RI 68577',
},
    'key99385': 'value93715',
    'key16164': 'value75899',
    'key39089': 'value90678',
    'key12836': 'value68137',
    'key35400': 'value89028',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Jimmy Brown',
    'address': '4216 Mandy Cove\nLake Vanessa, ME 72750',
    'text': 'Lot clear debate player. Raise resource late start attorney. Occur writer deep local beat. Federal walk us.',
    'email': 'dhernandez@example.net',
    'phone_number': '447-327-7895',
    'array_int_dynamic': [
    97403,
],
    'array_varchar_dynamic': [
    'Kimberly Huff',
    'Sharon Gutierrez',
    'Beth Gomez',
    'Monica James',
    'Thomas Goodwin',
],
    'json': {
    'name': 'Jennifer Reynolds',
    'address': '8869 Adrian Loaf\nWest Lisaton, MI 26479',
},
    'key56572': 'value70246',
    'key30035': 'value21880',
    'key6429': 'value9640',
    'key11523': 'value5553',
    'key35169': 'value15120',
    'key73867': 'value74597',
    'key65734': 'value94118',
    'key51356': 'value81915',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Carlos Ramirez',
    'address': '09558 Sonya Field Suite 884\nSouth Paulaville, FL 62178',
    'text': 'Recent take world form we. Mention Mrs follow enough.\nService stop ever. Explain administration month record. Rise different responsibility something game.\nPrepare situation move.',
    'email': 'sdouglas@example.net',
    'phone_number': '+1-326-487-3816x020',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Angela Carroll',
    'Mitchell Wells',
    'Carol Chavez',
    'Troy Cross',
    'Amy Ramos',
    'Curtis Pierce',
    'Brittany Martin',
    'Heather Cherry',
    'Richard Parsons',
],
    'json': {
    'name': 'Logan Anderson',
    'address': '8994 Davis Brooks\nPort Arielberg, CA 74172',
},
    'key85653': 'value22666',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Kevin Ruiz',
    'address': 'Unit 0309 Box 6296\nDPO AP 88547',
    'text': 'Attorney writer message little up dream worry. Student top board wonder paper poor. Make let live machine message while soldier.',
    'email': 'renee13@example.com',
    'phone_number': '739-865-3339x281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Rodney Smith',
    'David Cunningham',
    'Christine Harris',
    'Ryan Miller',
],
    'json': {
    'name': 'Christian Cohen',
    'address': '702 James Corners Suite 659\nNorth Sharon, TX 23569',
},
    'key70804': 'value54788',
    'key91773': 'value60882',
    'key68266': 'value9184',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Chad Mclaughlin',
    'address': '79470 Wells View\nWagnerfort, IA 57787',
    'text': 'Able reach get participant.\nCitizen play growth it shake so near. Wife trial age late. Sing increase although hold to. Thing teach gun sit.',
    'email': 'psanchez@example.com',
    'phone_number': '(988)346-7088',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Scott',
    'Katherine Clarke',
    'Brian Wood',
    'Vincent Ortiz',
    'Thomas Mcguire',
    'Morgan Russell',
],
    'json': {
    'name': 'Felicia Small',
    'address': '28270 Peck Mountain\nWest Whitneyfurt, MH 24106',
},
    'key91994': 'value14967',
    'key47308': 'value3370',
    'key36072': 'value90815',
    'key83035': 'value60243',
    'key92007': 'value86681',
    'key19448': 'value59768',
    'key20597': 'value19794',
    'key73951': 'value66049',
    'key80331': 'value28170',
    'key46680': 'value40078',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Kayla Jones',
    'address': '376 Jones Freeway\nJessefurt, LA 59814',
    'text': 'Know green reality book. Response still somebody region old.\nProfessor author receive expert store admit still. School eye show miss. Specific unit somebody item.',
    'email': 'stephenchen@example.net',
    'phone_number': '001-598-350-0431',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Russell',
    'Benjamin Clark',
    'Jordan Stanley',
    'Jennifer Scott',
    'Peter Cole',
    'Andrea Mckinney',
    'Richard Flores',
],
    'json': {
    'name': 'Amy Davis',
    'address': '2574 Hernandez Via\nEast Matthew, VI 80928',
},
    'key5963': 'value14919',
    'key6694': 'value12603',
    'key17513': 'value97074',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Robert Cantrell',
    'address': '02567 Gilbert Circles\nPort Ericshire, AS 31148',
    'text': 'Create someone my point model individual. Himself dark wide price life similar once.\nPerhaps magazine dark practice task go treatment. Somebody smile likely interest before.',
    'email': 'halldaniel@example.net',
    'phone_number': '9979215676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Davis',
    'Darrell Perez',
    'Tracy Valencia',
    'Annette Williams',
    'Mr. Ryan Mercer',
],
    'json': {
    'name': 'Victor Wright',
    'address': '5781 Ellen Locks Apt. 896\nPort Jacqueline, MO 71137',
},
    'key73582': 'value42043',
    'key97117': 'value51394',
    'key42614': 'value1385',
    'key68585': 'value106',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Charles Roach',
    'address': '380 Miranda Isle\nKennethton, AR 35968',
    'text': 'Television billion quality continue main black night. Sort training drug business food. Firm responsibility nature painting.',
    'email': 'kellykimberly@example.net',
    'phone_number': '001-832-507-9839x31290',
    'array_int_dynamic': [
    38719,
],
    'array_varchar_dynamic': [
    'Paul Miller',
    'Chelsea Williamson',
    'Carmen Byrd',
    'James Kelley',
    'Mario Alvarado',
    'Alexander Lee MD',
    'David Perry',
    'Jeff Buckley',
],
    'json': {
    'name': 'Anthony Peters',
    'address': '48177 Tina Hills\nEricafort, ID 75762',
},
    'key38171': 'value53720',
    'key16930': 'value22022',
    'key51676': 'value46427',
    'key47396': 'value49319',
    'key6112': 'value18630',
    'key87680': 'value51623',
    'key67883': 'value39929',
    'key20260': 'value50846',
    'key83261': 'value35205',
    'key16214': 'value82904',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'David Peterson',
    'address': '78151 Erik Ferry\nLake Katherine, OH 15880',
    'text': 'Rock central who water. Every where common claim number institution. There another service management.\nSmile security oil after. Live your whether use speak various phone through.',
    'email': 'mhancock@example.com',
    'phone_number': '001-464-528-6860',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Heather Dunn',
    'Terry Mcdonald',
    'Douglas Bell',
    'Jennifer Boone',
    'Curtis Harrell',
    'Donna Gray',
],
    'json': {
    'name': 'Jennifer Scott',
    'address': '4735 Taylor Fords\nStevenshaven, MA 60133',
},
    'key22576': 'value43275',
    'key93354': 'value87414',
    'key2556': 'value9960',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Bryan Davis',
    'address': 'Unit 1027 Box 9532\nDPO AE 14480',
    'text': 'Enjoy first usually.\nGeneration military anyone head. Soon second sell study. Feel language image Democrat green.\nFund agree these owner every. Enter rise production I. Teacher film instead expert.',
    'email': 'jeffrey30@example.org',
    'phone_number': '001-384-652-7372x391',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Lopez',
    'David Robinson',
    'Kimberly Marshall',
    'Ricky Ford',
    'Julie James',
],
    'json': {
    'name': 'Mason Garcia',
    'address': '49663 Justin Islands\nWest Stacychester, GU 53345',
},
    'key11418': 'value44929',
    'key18417': 'value7609',
    'key86001': 'value69973',
    'key80222': 'value53031',
    'key59506': 'value31905',
    'key37127': 'value85746',
    'key16164': 'value97946',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Marissa Martinez',
    'address': '1863 Miranda Gateway\nFlemington, NY 44920',
    'text': 'Month information research candidate. Manager former financial employee. Field field need activity minute federal true.\nCold central result child person blood.\nDecision official main support plan.',
    'email': 'popewilliam@example.org',
    'phone_number': '440-799-6275',
    'array_int_dynamic': [
    5419,
],
    'array_varchar_dynamic': [
    'Michelle Berry',
    'Christine Marshall',
    'Stephanie Cruz',
    'Frank Reeves',
    'Nancy Knox',
],
    'json': {
    'name': 'Belinda Brown',
    'address': '81312 Jack Tunnel\nSouth Lauren, CO 25430',
},
    'key99693': 'value88557',
    'key49665': 'value82802',
    'key14724': 'value13750',
    'key9479': 'value63571',
    'key6797': 'value76832',
    'key53980': 'value51222',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Joseph Lewis',
    'address': '48076 Wilkerson Camp Suite 095\nFaulknerview, IL 85741',
    'text': 'Institution for quickly especially case want star. Speak condition help herself. One key letter everybody generation night military yet.\nStop decade whatever cover machine.',
    'email': 'nburns@example.net',
    'phone_number': '824.502.6739x912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Cooper',
    'Alejandra Randolph',
    'Danny Avila',
    'Raymond King',
    'Todd Mendoza',
    'Joseph Cain',
],
    'json': {
    'name': 'Christopher Morton',
    'address': '025 Roberto Villages\nNorth Kristinefort, MH 25734',
},
    'key60576': 'value73877',
    'key33434': 'value14535',
    'key6728': 'value33966',
    'key32855': 'value8663',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'April Duncan',
    'address': '2584 Barton Inlet Apt. 667\nSanchezfurt, AR 86761',
    'text': 'Until son her coach capital save. Require politics story note once.\nYard owner phone trade light run best choose. Source left thus.',
    'email': 'brandon31@example.org',
    'phone_number': '+1-980-229-6841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ricky Hays',
    'Allison Carr',
    'Mark Morrow',
    'Billy Cole',
    'Glenn Lewis',
    'Amber Patterson',
    'Susan Romero',
    'Melissa Phillips',
],
    'json': {
    'name': 'Bailey Hammond',
    'address': '012 Smith Manor\nLisaborough, PR 88676',
},
    'key9885': 'value49249',
    'key46147': 'value3947',
    'key43429': 'value11485',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Edward Caldwell',
    'address': '9575 Strong Forge Apt. 545\nTamiside, ID 09734',
    'text': 'Chance record meet produce very seem nation. Easy owner sign couple six pressure. Our Mr pick southern hand young improve.\nBook benefit news star. Blue guy yard we interview benefit eye.',
    'email': 'alicia73@example.com',
    'phone_number': '001-867-500-1894x548',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Daniel Morgan',
    'Todd King',
    'Nathan Murray',
    'Carla Jones',
    'Gwendolyn Cabrera',
    'Danielle Barry',
    'Robert Powell',
    'Terry Lucas',
],
    'json': {
    'name': 'Marissa Watts',
    'address': '6406 Kerri Creek\nKirbymouth, PA 05816',
},
    'key13113': 'value514',
    'key95806': 'value81919',
    'key7466': 'value11872',
    'key57570': 'value85168',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Valerie Fox',
    'address': '595 Kenneth Ferry Suite 781\nJonathanburgh, TX 03273',
    'text': 'Somebody along work control medical. Training class information hospital. Away specific pressure perform give.\nOr writer financial man. Weight wall southern blue.',
    'email': 'brandonanderson@example.org',
    'phone_number': '+1-992-677-4907x07334',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Strickland',
    'Frank Gray',
    'Tammy Lewis',
    'Erin White',
    'Kevin Hall',
    'Aimee Mclean',
    'Mary Bean',
],
    'json': {
    'name': 'James Guerrero',
    'address': '950 Williams Cliff\nRachelland, AL 87603',
},
    'key85234': 'value52147',
    'key19160': 'value52944',
    'key85857': 'value67395',
    'key85312': 'value93315',
    'key89813': 'value96899',
    'key65396': 'value29144',
    'key50809': 'value4911',
    'key19921': 'value23988',
    'key55021': 'value13282',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Sylvia Scott',
    'address': '52734 Ross Terrace\nLesliehaven, RI 11151',
    'text': 'Have budget issue campaign response actually.\nDegree side coach decide three high. Southern know herself region health assume exactly.\nWhole effect while occur happy play activity.',
    'email': 'patricia83@example.com',
    'phone_number': '001-991-705-0447x63933',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ms. Amy Todd',
    'Megan Oliver',
    'Amber Lester',
    'Richard Pacheco',
    'Brian Powell',
    'Courtney Scott',
    'Bonnie Jones',
    'Andrea Cordova',
    'Sherri Diaz',
],
    'json': {
    'name': 'Barbara Meza',
    'address': '445 Williams Shoal\nWest Gregory, CO 54768',
},
    'key40714': 'value28002',
    'key90107': 'value15260',
    'key90304': 'value11855',
    'key74461': 'value51968',
    'key13': 'value84003',
    'key87199': 'value7398',
    'key24932': 'value88427',
    'key31902': 'value14202',
    'key14124': 'value81503',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Daniel Price',
    'address': '15714 Lauren Brooks\nWest Adrian, KS 28832',
    'text': 'Quality direction economy appear. So pay hit trial.\nAction together evening east. Reduce minute team house item. Far rate natural crime determine professor.',
    'email': 'qhernandez@example.com',
    'phone_number': '(265)338-9405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christina Solomon',
    'Joseph Douglas',
    'Lance Lewis',
    'Robert Wells',
    'David Austin',
],
    'json': {
    'name': 'Kendra Williams',
    'address': 'PSC 4243, Box 7645\nAPO AP 20882',
},
    'key88471': 'value80937',
    'key25936': 'value38916',
    'key50176': 'value15362',
    'key64045': 'value9576',
    'key16974': 'value19749',
    'key51468': 'value39010',
    'key32076': 'value58165',
    'key44425': 'value2308',
    'key11412': 'value87766',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Christopher Gonzalez',
    'address': '96059 Leah Courts Apt. 303\nWest Diane, WV 58939',
    'text': 'May young safe newspaper threat day bring so. Issue pick visit world assume campaign statement.\nMaterial avoid top together product increase.',
    'email': 'gcollins@example.org',
    'phone_number': '(450)843-3118',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Paul Rogers',
    'Dale Harrington',
    'Rachel Elliott',
    'Christopher Weaver',
    'Andrew Smith',
    'Daniel Smith',
    'Carla Adams',
    'Stephanie Avery',
    'Kenneth Estrada',
    'Beth Little',
],
    'json': {
    'name': 'Amanda Moore',
    'address': '960 John Locks\nNew Paige, UT 50526',
},
    'key71141': 'value14105',
    'key11387': 'value11355',
    'key8919': 'value303',
    'key36702': 'value70667',
    'key14459': 'value43269',
    'key63454': 'value65045',
    'key552': 'value17571',
    'key48640': 'value24951',
    'key73014': 'value95690',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Erica Williams',
    'address': '46843 Tara Lights\nEast Terrencestad, NV 94236',
    'text': 'Some window strategy this recent thousand. Country past upon their exist.\nEnter fast law product table style. Purpose goal while cultural season.',
    'email': 'emily19@example.org',
    'phone_number': '621.722.1703x31772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Cameron Griffin',
    'Cynthia Powers',
    'Dr. Mathew Gould',
    'William Allen',
    'Tommy Wilkinson',
],
    'json': {
    'name': 'Cynthia Johnston',
    'address': '48457 Robert Key\nRichardside, MS 68819',
},
    'key25509': 'value54946',
    'key64721': 'value2632',
    'key50682': 'value77469',
    'key13157': 'value87912',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Melanie Williamson',
    'address': '9996 Stephanie Glens Suite 602\nLake Christinemouth, MH 26537',
    'text': 'Future season ready TV nation common yes. Attention TV beat main back outside.\nKnowledge along smile series. Myself speech piece sound. Page set reach right full.',
    'email': 'aandrews@example.com',
    'phone_number': '+1-870-213-2648x0250',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Krista Smith',
],
    'json': {
    'name': 'Caitlin Spencer',
    'address': 'PSC 4070, Box 0106\nAPO AP 26396',
},
    'key46707': 'value12391',
    'key81578': 'value69656',
    'key67138': 'value95109',
    'key19296': 'value38802',
    'key99996': 'value25854',
    'key49221': 'value54677',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Carmen Herman',
    'address': '7459 Allison Motorway\nRobertbury, TX 02958',
    'text': 'Listen mouth support week. Physical interview successful skill contain guy act. Style main skin child down national kitchen.',
    'email': 'sherry74@example.org',
    'phone_number': '3257285090',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Samuel Herring',
    'Philip Duncan',
    'Shannon Rodriguez',
    'Crystal Patton',
    'Ashley Nielsen',
    'Stephanie Hansen',
    'Amanda Obrien',
],
    'json': {
    'name': 'Thomas Henderson',
    'address': '23549 Herrera Square\nLake Annettefort, MI 54574',
},
    'key4406': 'value39663',
    'key98358': 'value52569',
    'key44002': 'value8077',
    'key65209': 'value32876',
    'key58242': 'value60724',
    'key36959': 'value73046',
    'key15891': 'value33279',
    'key41795': 'value67590',
    'key32365': 'value34932',
    'key93173': 'value4806',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Kathryn Hall',
    'address': '76370 Salazar Overpass Apt. 222\nSouth Jacob, TN 14949',
    'text': 'Hotel attorney production. Kitchen federal argue dark. Buy by something expect.\nArtist black behind area pattern positive news. Before color mission measure cold art within official.',
    'email': 'brianklein@example.org',
    'phone_number': '897-635-9007',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Alexander',
    'Taylor Fox',
    'Alejandra Jenkins',
    'Angela Davis',
    'Timothy Patrick',
    'Sandra Coleman',
    'David Sullivan',
    'Paige Harmon',
],
    'json': {
    'name': 'Andrea Duarte',
    'address': '17999 Norton Alley Suite 236\nLambertland, NE 88191',
},
    'key7110': 'value27804',
    'key13099': 'value99220',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Charles Pierce',
    'address': '80742 David Forge Suite 430\nKevinborough, LA 13400',
    'text': 'Interest note piece quickly best. Other wait again lay leg either color include.',
    'email': 'williamsalicia@example.com',
    'phone_number': '+1-604-919-0120x22476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Monica Bradley',
    'Stephanie Mayer',
    'Cody Tran',
    'Aaron Hunter',
    'Christian Flores',
    'David Sharp',
    'Scott Moore',
    'Jennifer Ward',
    'Sara Watson',
    'David Hall',
],
    'json': {
    'name': 'Krista Robinson',
    'address': '48794 Erin Lights\nMcknightbury, ID 10171',
},
    'key95334': 'value90182',
    'key51704': 'value95541',
    'key53982': 'value78632',
    'key54425': 'value6184',
    'key4995': 'value1089',
    'key36860': 'value90036',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Jason Russell',
    'address': '299 Grant Lodge Apt. 931\nNormashire, WA 23944',
    'text': 'Sense reach woman from key goal. Worry role argue realize quality political admit.',
    'email': 'raymondcarl@example.org',
    'phone_number': '481.875.2354',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Anderson',
    'Tammy Stewart',
    'Michelle Lang',
    'Elizabeth Carney',
    'Tricia Maldonado',
    'Christina Massey',
    'Steven Carroll',
    'Stephanie Reynolds',
    'Sonia Ward',
    'Rebecca King',
],
    'json': {
    'name': 'Daniel Ross',
    'address': '774 Austin Curve\nPort Joshuaside, ND 91100',
},
    'key93698': 'value45257',
    'key69637': 'value27002',
    'key16971': 'value41154',
    'key42495': 'value42244',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Jennifer Castro',
    'address': '6923 Elizabeth Rue\nNew Colleenstad, WY 56064',
    'text': 'Sign industry hard student. Then with charge area no I few.\nMedical senior fill gas both leg. Professional new general fight. Fast course few.\nSpring mind national often focus. Forget enter allow.',
    'email': 'charlesvaughn@example.net',
    'phone_number': '672.685.4474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Kaufman',
    'Jessica Clark',
],
    'json': {
    'name': 'Philip Coffey',
    'address': '051 Tracy Fall\nReevesburgh, NM 54145',
},
    'key16182': 'value15349',
    'key54074': 'value13088',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Matthew Price',
    'address': '219 David Lock\nJeffreyside, OR 51858',
    'text': 'Part together little decide sea where different. Set ball product mean big. Type someone reduce build drop people.',
    'email': 'leonard19@example.org',
    'phone_number': '+1-934-749-2322x46276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Solis',
    'Mr. Brandon Rogers',
    'Ashley Dawson',
],
    'json': {
    'name': 'Victoria Bailey',
    'address': '3876 Riley Bypass Suite 886\nRicebury, KY 28820',
},
    'key56587': 'value56144',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Edwin Burgess',
    'address': '2095 Cheyenne Plaza\nHerreramouth, DC 30209',
    'text': 'Ever military yes about knowledge. Pattern local continue next.\nMorning fight before class. Couple everything he although service woman kind. Notice these through tend since.',
    'email': 'carrie04@example.org',
    'phone_number': '(644)600-8260x14478',
    'array_int_dynamic': [
    51538,
],
    'array_varchar_dynamic': [
    'Donna Hays',
    'Karen Collins',
    'Brian Chambers',
    'Brian Flores',
    'Lauren Waters',
    'Keith Lewis',
    'Melissa Mendez',
],
    'json': {
    'name': 'Bryan Dixon',
    'address': '79480 Katherine Causeway Suite 069\nWest Victoriaview, SC 43000',
},
    'key80076': 'value93723',
    'key16987': 'value84060',
    'key92810': 'value3345',
    'key4005': 'value37109',
    'key23034': 'value98754',
    'key91769': 'value98353',
    'key91464': 'value5086',
    'key30633': 'value57368',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Jennifer Moran',
    'address': '9950 Ferguson Alley Suite 897\nAdamton, WY 94390',
    'text': 'Gun report physical despite take finally. Phone customer second mean understand election subject budget. Agreement form friend wait.',
    'email': 'yguzman@example.com',
    'phone_number': '704.715.9886x6278',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jim Burke',
    'Craig Simmons',
    'John Butler',
],
    'json': {
    'name': 'William Hernandez',
    'address': '166 Smith Drive\nSouth Bobby, SC 37953',
},
    'key36886': 'value98931',
    'key52201': 'value62511',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Aaron Rubio Jr.',
    'address': '697 Olivia Drive\nLake Denisefurt, VA 39978',
    'text': 'We serious wrong. Behavior note young unit become particularly leg writer. Year region major learn. Page choose then sister spend age activity.',
    'email': 'xgallagher@example.net',
    'phone_number': '(837)335-1940x43143',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tara Myers',
    'Bryan Reese',
],
    'json': {
    'name': 'April Salazar',
    'address': '51789 Patrick Islands\nYoungburgh, AK 90917',
},
    'key12709': 'value84009',
    'key32005': 'value59619',
    'key74226': 'value84090',
    'key93603': 'value22259',
    'key14610': 'value17992',
    'key48183': 'value87238',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Dr. Sharon Lee',
    'address': '2756 Eric Points Suite 192\nBrownville, SC 04929',
    'text': 'Respond central already TV current. Go TV executive cut three none never. Social rich now hundred eight suffer.',
    'email': 'rachel81@example.org',
    'phone_number': '515.558.1678x7552',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Laura White DDS',
],
    'json': {
    'name': 'Jeffrey Williams',
    'address': '2656 Cruz Hill Suite 744\nNew Tiffany, NC 07601',
},
    'key86750': 'value88913',
    'key8288': 'value13843',
    'key32001': 'value69367',
    'key26191': 'value48241',
    'key99753': 'value90340',
    'key93158': 'value51002',
    'key51024': 'value32832',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Amanda Hall',
    'address': '266 Dominic Streets\nGriffinburgh, WY 14846',
    'text': 'Ok catch support lawyer.\nValue claim bad late. Interest particular by throughout. Particular color beyond care. Central investment focus have hotel now prepare.',
    'email': 'april18@example.org',
    'phone_number': '(866)888-4652x19740',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Kelly Patel',
],
    'json': {
    'name': 'Matthew Mitchell',
    'address': '72852 Sarah Heights\nWest Jessica, WV 57234',
},
    'key44716': 'value58332',
    'key11419': 'value24087',
    'key22619': 'value50402',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Rachel Shannon',
    'address': '414 Salas Mountain Suite 581\nRussofort, VI 21629',
    'text': 'Art note world but place.\nLate employee on and modern step avoid. Nearly person choice chance force. Table just behavior speak reason wind. Myself student never almost quality.',
    'email': 'swolf@example.com',
    'phone_number': '+1-654-575-4772x93677',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Williams',
    'George Young',
],
    'json': {
    'name': 'Michael Duarte',
    'address': '6990 Katherine Turnpike Apt. 331\nNew Robertton, KY 65074',
},
    'key74023': 'value71579',
    'key63296': 'value1392',
    'key32588': 'value30758',
    'key38657': 'value44184',
    'key23349': 'value21394',
    'key8990': 'value35255',
    'key89041': 'value69302',
    'key76532': 'value37916',
    'key8744': 'value28598',
    'key98597': 'value53277',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Karen Cortez',
    'address': '68548 Natasha Isle\nPort Briannaborough, OH 78344',
    'text': 'She child beautiful too effect remain such. Adult street personal often by. Kind staff event trial employee cost important add.',
    'email': 'alyssa10@example.com',
    'phone_number': '001-270-413-0251x16649',
    'array_int_dynamic': [
    29133,
],
    'array_varchar_dynamic': [
    'Michael Lewis',
    'Joseph Martin',
    'Donna Zavala',
    'Kimberly Long',
],
    'json': {
    'name': 'Sean Hernandez',
    'address': 'USNV Reed\nFPO AA 67949',
},
    'key37958': 'value74730',
    'key13953': 'value5905',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Sandy Meza',
    'address': '98615 Kaitlin Port\nEast Amanda, NH 75961',
    'text': 'Follow hour and. Ever sister author exactly a national.\nProcess bad ago. Matter always head opportunity from. Rest attack specific idea today beyond pattern.',
    'email': 'xmiller@example.net',
    'phone_number': '001-345-535-0264x4353',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Cole Miranda',
    'Joan Brown DDS',
    'Robert Ellis',
    'Tyler White',
    'Mary Wilson',
],
    'json': {
    'name': 'Ashley Hester',
    'address': 'Unit 4451 Box 7210\nDPO AA 65298',
},
    'key1361': 'value32372',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Walter Brown',
    'address': '55949 Heather Bypass\nGaryside, WA 29867',
    'text': 'Where girl her similar however. Difference world nearly head player system.\nKind yeah image draw standard artist. Tv school guess.\nAhead assume skin environmental born.',
    'email': 'samantha25@example.org',
    'phone_number': '001-496-589-2176x783',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Laura Gibbs',
    'Jennifer Long',
    'Amanda Boyd',
    'Theresa Fletcher',
    'Michael Hernandez',
],
    'json': {
    'name': 'Phyllis Marshall',
    'address': '92514 Mackenzie Cape\nLesliemouth, FL 09103',
},
    'key53975': 'value10456',
    'key99858': 'value53080',
    'key73443': 'value54358',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Matthew Rodriguez',
    'address': '34521 Christopher Mill\nSouth Rebekahshire, MO 27669',
    'text': 'Whole a training speak hair whole. Station age hot. Member agreement professional.',
    'email': 'johndeleon@example.com',
    'phone_number': '(514)652-1924x79461',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Nichols',
    'Adam Smith',
],
    'json': {
    'name': 'Audrey Mclean',
    'address': '091 Hill Forks Suite 422\nElizabethburgh, HI 57102',
},
    'key67178': 'value52609',
    'key14633': 'value53288',
    'key77651': 'value86247',
    'key86300': 'value53158',
    'key77302': 'value58687',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Michael Willis',
    'address': 'PSC 9861, Box 7174\nAPO AE 28708',
    'text': 'Bar husband group strong notice within every there. Trade cover I century within lot space. Interest chance because statement fall.',
    'email': 'ronniejohnson@example.org',
    'phone_number': '(699)640-5786',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Hamilton',
    'Evan Short',
],
    'json': {
    'name': 'David Lucas',
    'address': '20618 Dana Via\nNorth Christineland, CA 06605',
},
    'key70554': 'value94703',
    'key30495': 'value88082',
    'key92208': 'value32224',
    'key28838': 'value76880',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Jeffrey Wood',
    'address': '680 Hansen Lodge\nRyanhaven, WV 15978',
    'text': 'Answer again when serious feel. Amount card common less whole skill best.\nAnyone arrive raise figure. Keep sometimes poor go plan guess.',
    'email': 'phaney@example.org',
    'phone_number': '(910)223-8070x71063',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jason Rodriguez',
    'Nathan Ball',
    'Kenneth Nguyen',
    'William Johnson',
    'Tiffany Reid',
    'Karen Schneider',
    'Kimberly Rios',
],
    'json': {
    'name': 'Teresa Holland',
    'address': '967 Craig Mountain Suite 046\nKellyton, MA 76369',
},
    'key27548': 'value83160',
    'key75437': 'value22660',
    'key89792': 'value56922',
    'key48527': 'value29830',
    'key21468': 'value69815',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Christopher Rice',
    'address': '75469 Matthew Bridge Apt. 033\nNelsonfurt, NY 76579',
    'text': 'Girl shoulder industry allow exist protect little voice. Young theory fight trade wonder method.\nRich Republican down election fact price. Boy up follow son.',
    'email': 'kaneantonio@example.net',
    'phone_number': '827-502-5530',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Cameron DVM',
    'Tracey Roberts',
    'Kenneth Bennett',
    'Debbie Smith',
    'Edward Benjamin',
    'Henry Bender',
    'Allison Roberts',
    'Linda David',
    'Michelle Thomas',
    'Bridget Evans',
],
    'json': {
    'name': 'Elaine Dominguez',
    'address': '53651 Eric Ways Suite 493\nLevyfort, SD 46000',
},
    'key58703': 'value52926',
    'key43075': 'value6450',
    'key43201': 'value6179',
    'key89768': 'value61790',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Howard Zimmerman',
    'address': '16632 Cody Curve Suite 391\nNew Jo, CO 63730',
    'text': 'American even author mother successful class become. Certainly Mr sound report teach you training.\nBlood admit draw beyond sound trade. Environmental student light she.',
    'email': 'robingonzalez@example.net',
    'phone_number': '907-743-1116x316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Kirby',
    'Wendy Steele',
    'Joe Garcia',
],
    'json': {
    'name': 'Scott Martinez',
    'address': '21311 Todd Mall Suite 212\nValdeztown, NY 20269',
},
    'key60413': 'value60382',
    'key87381': 'value17383',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Sharon Morales',
    'address': '61737 Christopher Lodge\nEast Larrytown, MA 20991',
    'text': 'Along real certain word player. Political ten however live traditional whom act.\nBoy ball movie look later federal. Rule be standard.',
    'email': 'kelleydiane@example.org',
    'phone_number': '(463)238-3912x6484',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Davis',
    'Ann Patterson',
    'Paul Morrow',
],
    'json': {
    'name': 'Christopher Mosley',
    'address': '41821 Kelly Roads Suite 112\nMarcusside, OR 40676',
},
    'key16583': 'value10936',
    'key54440': 'value83393',
    'key13307': 'value55165',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Kenneth Adams',
    'address': 'USCGC Patterson\nFPO AE 67629',
    'text': 'White understand high floor. Green computer turn popular. Participant get team very his specific quickly.',
    'email': 'clintoncunningham@example.net',
    'phone_number': '(830)978-9112x48586',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Brown',
    'Lisa Thomas',
],
    'json': {
    'name': 'Robin Anderson',
    'address': 'PSC 3938, Box 4701\nAPO AP 71258',
},
    'key22897': 'value20459',
    'key29637': 'value50191',
    'key98532': 'value38470',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Robert Thomas',
    'address': '84060 Davis Shoal Apt. 202\nSalazarville, MS 92188',
    'text': 'Enjoy our short health success about may. Face back it cost attention concern.\nSingle expert sister bag pretty foot seek.',
    'email': 'simmonskristen@example.net',
    'phone_number': '+1-598-258-3531x155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Silva',
    'Natasha Butler',
],
    'json': {
    'name': 'Brittney Padilla',
    'address': '2440 Margaret Field Apt. 069\nSouth Joshuaview, ID 88944',
},
    'key55413': 'value86501',
    'key20616': 'value70045',
    'key21213': 'value49573',
    'key92099': 'value78924',
    'key84425': 'value36984',
    'key80347': 'value34261',
    'key71983': 'value78812',
    'key49408': 'value38854',
    'key1687': 'value82814',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Miss Megan Thompson',
    'address': '06617 Montgomery Village\nStevenview, PR 20218',
    'text': 'Forward mention Democrat policy. Class treat actually different.\nDifferent tax owner week. Share floor camera player need Mr.',
    'email': 'kbaker@example.net',
    'phone_number': '338-398-8884',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Scott Cruz',
    'Victor Miller',
    'Megan Hill',
    'Sarah Cole',
    'Gabrielle Palmer',
    'Evan Stevens',
    'Phillip Hill',
    'Jacob Jones',
    'Joshua Bautista',
],
    'json': {
    'name': 'Lawrence Green',
    'address': '428 Albert Harbor\nWest Maryshire, UT 14610',
},
    'key83196': 'value8902',
    'key25465': 'value15679',
    'key9994': 'value27898',
    'key36704': 'value98989',
    'key55630': 'value48655',
    'key50573': 'value83961',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Raymond Black',
    'address': '7906 Andrew Lock Apt. 698\nWest Madisonfurt, IL 28215',
    'text': 'Provide easy for test. Reason talk how garden upon.\nForget senior red pick. School able else. Quality often view blood glass perhaps evening. East economy none half available inside daughter.',
    'email': 'kwatson@example.net',
    'phone_number': '709-978-0539',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Ferguson',
    'Rachel Lopez',
    'Paul Liu',
],
    'json': {
    'name': 'Michael Nolan',
    'address': 'PSC 9612, Box 7486\nAPO AA 82779',
},
    'key66717': 'value4551',
    'key8880': 'value50530',
    'key17573': 'value48923',
    'key4150': 'value72892',
    'key60916': 'value39498',
    'key40868': 'value88728',
    'key787': 'value92754',
    'key38399': 'value47568',
    'key36800': 'value14364',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Alyssa Campbell',
    'address': '9670 Stephanie Fork Apt. 199\nRoberthaven, MA 98702',
    'text': 'Manager live form two rich. Choose method media husband message nothing finally.\nConsider travel officer they foreign. Beat leader occur really. Name treat pass possible less.',
    'email': 'amelton@example.com',
    'phone_number': '(501)527-3205x548',
    'array_int_dynamic': [
    65343,
],
    'array_varchar_dynamic': [
    'Danny Reed',
    'Clinton Gibson',
    'Miss Carol Farley',
],
    'json': {
    'name': 'Kathleen Sparks',
    'address': '5625 Hanson Green\nFishermouth, MP 22712',
},
    'key19673': 'value27062',
    'key30689': 'value22503',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Bryan Smith',
    'address': 'USNV Hendrix\nFPO AE 67252',
    'text': 'Job help during east mind will. First painting enough accept. And fight spring wonder although.\nHour know career. Book game couple eight prepare indicate. Million range six newspaper he.',
    'email': 'karenbrown@example.net',
    'phone_number': '(647)685-9066',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Frost',
    'Gloria Young',
],
    'json': {
    'name': 'Alan Hunter',
    'address': '635 James Square\nWest Brittanybury, OH 59437',
},
    'key63961': 'value46652',
    'key68495': 'value83581',
    'key2220': 'value51145',
    'key84191': 'value70821',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Michelle Kane',
    'address': '80315 Gordon Village\nNew Brittanyberg, ME 94639',
    'text': 'Interview threat effect themselves out attack history. Investment heavy amount century single anyone.\nSomeone conference bill then five pattern. Lose opportunity accept sort fish information social.',
    'email': 'maryramos@example.com',
    'phone_number': '+1-802-363-0162x53094',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Bailey',
    'Dylan Taylor',
],
    'json': {
    'name': 'James Donaldson',
    'address': '8910 Jennings Valley Suite 118\nLake Marilynton, GA 07572',
},
    'key11339': 'value24846',
    'key36927': 'value7329',
    'key63028': 'value65288',
    'key16973': 'value21560',
    'key68997': 'value83192',
    'key69278': 'value15540',
    'key28864': 'value3508',
    'key56493': 'value50216',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'David Johnson',
    'address': '3746 Tim Falls Apt. 267\nRodriguezburgh, MA 95773',
    'text': 'Yourself change computer often. Black scientist drop home turn medical either. Improve would later everybody decade shake save.\nReady once subject difficult life.',
    'email': 'loriclark@example.net',
    'phone_number': '731-221-1909x1899',
    'array_int_dynamic': [
    31041,
],
    'array_varchar_dynamic': [
    'Bryan Stein',
    'Gabrielle Williams',
    'Darlene Humphrey',
],
    'json': {
    'name': 'Valerie Carter',
    'address': '667 Richard Shoals Apt. 002\nPhillipsberg, CA 24039',
},
    'key87195': 'value42863',
    'key41214': 'value92866',
    'key28829': 'value84062',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Anthony Hart',
    'address': '4711 Payne Ville Apt. 059\nChadborough, FL 84948',
    'text': 'Rate whether learn staff.\nKeep fly industry possible final difference. Skill year happy. Painting focus day nor town enjoy east.',
    'email': 'jake87@example.net',
    'phone_number': '531.964.2220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Derrick Brooks',
    'Aaron Smith',
    'Joseph Edwards',
],
    'json': {
    'name': 'Daniel Robinson',
    'address': '411 Alfred Circle\nJacobmouth, IA 14663',
},
    'key46086': 'value32348',
    'key12473': 'value73963',
    'key46740': 'value12736',
    'key99558': 'value32104',
    'key84751': 'value1796',
    'key44046': 'value68544',
    'key26666': 'value43125',
    'key62242': 'value23769',
    'key94333': 'value70208',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Curtis Welch',
    'address': '20869 Craig Ranch Suite 551\nEast Katrina, NH 64756',
    'text': 'Green perhaps field light because head land. Manage off policy development.\nMaybe capital by program particularly. Consider natural before. Source recently economic bring purpose break.',
    'email': 'kevin04@example.org',
    'phone_number': '001-680-482-5304',
    'array_int_dynamic': [
    72248,
],
    'array_varchar_dynamic': [
    'Jerry Fletcher',
    'Brandy Arroyo',
    'Alexander Blevins',
    'Lisa Miller',
    'Michael Scott',
    'Philip Flowers',
    'Mrs. Regina Price',
],
    'json': {
    'name': 'Deborah Adkins',
    'address': '9600 Hawkins Pass\nCrystalville, MT 95552',
},
    'key10095': 'value45798',
    'key52141': 'value24399',
    'key35661': 'value56783',
    'key59848': 'value22209',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Helen Salinas',
    'address': '59646 Kelly Mill\nTammystad, TX 25381',
    'text': 'Half cost sing nature. Place government turn under energy during.\nSide environmental state clearly usually high. Wish local benefit.',
    'email': 'shawn55@example.org',
    'phone_number': '+1-475-589-9269',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Sellers',
    'Aaron Bailey',
    'Charles Powell',
    'Joseph Vasquez',
    'Troy Spencer',
    'Carolyn Hodges',
],
    'json': {
    'name': 'Leah Lewis',
    'address': '7741 Pamela Circles\nPort Williamside, MN 04366',
},
    'key39996': 'value60474',
    'key26363': 'value27889',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Nicholas Quinn',
    'address': '2698 Stephanie Fork\nDonnaborough, FM 57846',
    'text': 'Study activity or talk lot.\nActivity back your finish suggest base game. Group particularly how letter go long.\nThemselves also world we bit ground build. No employee apply peace why picture.',
    'email': 'davidkrueger@example.com',
    'phone_number': '233.991.6024',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Watson',
    'Sarah Cook',
    'David Marks',
    'Carolyn Perry',
    'Daniel Maddox',
    'Brendan Schwartz',
    'Robin Sanchez',
    'Crystal Estrada',
    'James Blake',
],
    'json': {
    'name': 'Renee Torres',
    'address': '94052 Lopez Hollow\nPort Matthew, PA 04706',
},
    'key59816': 'value3156',
    'key59914': 'value31837',
    'key6993': 'value45315',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Stephanie Colon',
    'address': '6736 Gallagher Heights Suite 497\nWest Jonathanview, MP 49361',
    'text': 'For reflect game us child. Whatever while glass might.\nBoy agree second hospital section there concern.',
    'email': 'meyermichael@example.net',
    'phone_number': '+1-888-550-3121x0941',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mary Powers',
    'Destiny Thomas',
],
    'json': {
    'name': 'Christina Barr',
    'address': '01228 Michelle Gateway Suite 713\nWilliamschester, OH 73209',
},
    'key85827': 'value91343',
    'key83970': 'value5319',
    'key719': 'value6586',
    'key12248': 'value12505',
    'key37620': 'value3809',
    'key60976': 'value91861',
    'key17493': 'value70636',
    'key89517': 'value31403',
    'key30348': 'value40581',
    'key38893': 'value9036',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'April Villanueva',
    'address': '85403 Daniel Court Suite 933\nJamesmouth, ME 90358',
    'text': 'Maybe simple final. Letter whether season can. Power bad myself cell. Board explain usually safe doctor give start TV.\nAlone center music strategy. Serve third former. Beat any always image store.',
    'email': 'juliereynolds@example.org',
    'phone_number': '9939667600',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Freeman',
    'Larry Cervantes',
    'Jill Yates',
    'Mr. Jacob Jones',
    'Keith Bates',
    'Brian Mccormick',
    'Sara Reynolds',
    'Vanessa Edwards',
    'Diana Ellis',
    'Dustin Murphy',
],
    'json': {
    'name': 'Anthony Mann',
    'address': '6755 Shannon Knolls Suite 779\nJacksonberg, NJ 74504',
},
    'key22121': 'value48457',
    'key920': 'value23136',
    'key77291': 'value21839',
    'key13516': 'value84148',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Danielle Peters',
    'address': '403 Matthew Coves Apt. 182\nNorth Tyronemouth, VI 39954',
    'text': 'About trade for center south us. Close relate something receive sing act type.',
    'email': 'awilliams@example.com',
    'phone_number': '990.661.8229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Lopez',
    'Patricia Osborn',
    'Samantha Lam',
    'Sarah Franklin',
    'Shelly Harris',
    'David Hall',
    'Miss Lori Cole',
    'Michael Reynolds',
],
    'json': {
    'name': 'David Smith',
    'address': '04058 April Divide Suite 224\nNorth Katrina, WA 24222',
},
    'key31455': 'value78694',
    'key65639': 'value70755',
    'key21555': 'value2148',
    'key38261': 'value25413',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Roy Hunter DDS',
    'address': '98213 Randall Plains\nAlyssamouth, NY 64326',
    'text': 'Raise perhaps current later between like out. Choose laugh these hotel. Get mean seven eat especially.\nSuggest for claim tree data thing low. Sport check require fight call.',
    'email': 'tony92@example.org',
    'phone_number': '464.367.0558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Carl Shields',
    'Richard Sanders',
    'Bobby Long',
    'Benjamin Gonzales',
    'Kyle Wallace',
    'Karen Silva',
],
    'json': {
    'name': 'Stefanie Johnson',
    'address': '4375 Vincent Lodge\nLake Courtneyside, VT 51579',
},
    'key17278': 'value91254',
    'key57480': 'value90024',
    'key8144': 'value24145',
    'key75795': 'value83691',
    'key687': 'value2027',
    'key57726': 'value69033',
    'key71471': 'value53438',
    'key57806': 'value64303',
    'key29936': 'value39697',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Billy Macias',
    'address': '334 White Spring Suite 473\nPaulaville, VA 68740',
    'text': 'Stop later view finally reach compare later begin. American human star more wall actually.',
    'email': 'thomasjohn@example.org',
    'phone_number': '001-498-456-6141x6232',
    'array_int_dynamic': [
    56800,
],
    'array_varchar_dynamic': [
    'Jeremy Dixon',
    'Todd Murray',
    'William Stanley',
],
    'json': {
    'name': 'Jennifer Hughes',
    'address': 'PSC 7456, Box 7037\nAPO AP 05621',
},
    'key34134': 'value13897',
    'key78467': 'value13042',
    'key82470': 'value96966',
    'key60413': 'value73189',
    'key74600': 'value71773',
    'key61104': 'value97199',
    'key65366': 'value73229',
    'key40664': 'value86373',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Dustin Jackson',
    'address': '2403 Smith Neck\nNorth Larry, AS 24904',
    'text': 'American indeed animal me service. Simple blood democratic politics weight.\nIndicate worker color safe. Second reach talk marriage. Under I oil end attack heart.',
    'email': 'ryan86@example.com',
    'phone_number': '224.405.9886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Huff',
    'Jerry Thompson',
    'Todd Steele',
    'Jennifer Brown',
    'Dale Trujillo',
    'Patricia Lucas',
    'Janet Kelly',
    'Joe Simpson',
    'Alice Roberts',
    'Lori York',
],
    'json': {
    'name': 'George Burke',
    'address': '29473 Jeremy Haven Suite 921\nSonyafort, AZ 54881',
},
    'key58162': 'value92135',
    'key91335': 'value60709',
    'key81299': 'value65198',
    'key29329': 'value43027',
    'key74801': 'value99174',
    'key43283': 'value80253',
    'key74517': 'value55285',
    'key8043': 'value48551',
    'key30943': 'value76284',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Sandra Burgess',
    'address': '01250 Aguilar Light\nCervantesmouth, NM 79524',
    'text': 'Nearly somebody finally ground different. Science place year door. Religious not quality international tax be suggest. Color similar suddenly.',
    'email': 'jameswilson@example.net',
    'phone_number': '(559)579-0615x281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Wayne Brock',
    'Cynthia Reed',
],
    'json': {
    'name': 'Richard Obrien',
    'address': 'PSC 8271, Box 5528\nAPO AE 28312',
},
    'key1184': 'value78070',
    'key40626': 'value70936',
    'key61181': 'value14595',
    'key92223': 'value25453',
    'key89740': 'value61813',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'David Garcia',
    'address': '73806 Richard Knoll\nSouth Angela, AS 48387',
    'text': 'But easy live result million piece. What field lot population top.\nBag whatever success human us enough. Bag tonight final risk our owner sister.',
    'email': 'matthewfreeman@example.org',
    'phone_number': '850-628-7479',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Hunter',
    'Nathan Holmes',
    'Dr. Rachel Williams',
    'Keith Acosta',
    'Michael Davis',
    'Tina Gordon',
    'Joseph Johnson',
    'Gary Freeman DDS',
],
    'json': {
    'name': 'Tyler Bowen',
    'address': '30621 Gibson Groves\nAmyfort, IN 74159',
},
    'key3621': 'value30921',
    'key97907': 'value68895',
    'key30422': 'value25135',
    'key72171': 'value26753',
    'key59456': 'value75237',
    'key99043': 'value15327',
    'key98103': 'value43956',
    'key20320': 'value21158',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Kristie Mccoy',
    'address': '49196 Jordan Forest Suite 864\nNorth Joshuaport, AL 38889',
    'text': 'Open major main family hair treatment opportunity vote. Back born father game seek approach. Our second add two yes.',
    'email': 'stephen56@example.net',
    'phone_number': '(383)914-3141x38751',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David White',
    'Nicholas Hughes',
],
    'json': {
    'name': 'Andrew Salas',
    'address': '12648 Thomas Underpass Suite 055\nWest Williamshire, MS 05666',
},
    'key81065': 'value99606',
    'key15988': 'value36495',
    'key8713': 'value3561',
    'key79023': 'value49095',
    'key23690': 'value21984',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Christopher Martin',
    'address': '64469 Carla Shoals Suite 198\nHuynhshire, SD 67404',
    'text': 'Remember green shake research. Than about past several.\nOld about whatever modern surface glass. Skin necessary live ball one son. Better then protect total open.',
    'email': 'ojoseph@example.org',
    'phone_number': '001-995-616-7020x871',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Garrett Stephens',
    'Jason Taylor',
    'Brett Shields',
    'David Smith',
    'Roger Smith',
    'Mike Kim',
    'Jeffrey George',
    'Molly Ross',
    'Jacqueline Johnson',
    'Joshua Brandt',
],
    'json': {
    'name': 'Chad Moon',
    'address': '3348 Andrew Center\nEast Scott, ID 71839',
},
    'key70424': 'value77768',
    'key81046': 'value42604',
    'key48384': 'value23331',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Matthew Burgess',
    'address': '2930 Greene Station\nPort Donaldview, PA 50241',
    'text': 'World responsibility summer expect right. Exactly garden every present to tree.\nSummer admit worker.\nMuch international manager skill could where. Agree church bill yard inside.',
    'email': 'hahnkaren@example.net',
    'phone_number': '(799)689-1815',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Hannah Osborn',
    'Melissa Hill',
    'Scott Gibson',
    'Charles Jones',
    'Tracy Munoz',
    'Laura Thompson',
],
    'json': {
    'name': 'Vanessa Miller',
    'address': '1806 Karen Wall Suite 217\nSarachester, MO 28798',
},
    'key75488': 'value15793',
    'key64136': 'value38119',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Veronica Montgomery',
    'address': 'USS Stevens\nFPO AP 86764',
    'text': 'Training address ball can finally next. Whose key break trial above notice on performance.\nDegree statement industry sea. Crime minute inside court particular hair.',
    'email': 'tbenson@example.com',
    'phone_number': '+1-361-992-8614x21085',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Wiley',
    'Maria Carr',
],
    'json': {
    'name': 'Henry Roberts',
    'address': '3856 Sanders Squares\nTonyview, ME 78837',
},
    'key69684': 'value39532',
    'key71089': 'value15865',
    'key79645': 'value98944',
    'key90867': 'value50525',
    'key76030': 'value66055',
    'key91771': 'value2217',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'William Cherry',
    'address': '0676 Anthony Vista Suite 447\nNew Austin, CA 03087',
    'text': 'Sell so clearly fall stuff hope present. Study audience edge station. Eight choose chair industry improve.',
    'email': 'rachel13@example.net',
    'phone_number': '503.638.4933x639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Hall Jr.',
    'Kevin Nunez',
    'Jennifer Smith',
    'William Thornton',
    'Patricia Wright',
    'Lisa Burke',
    'Stephen Morris',
],
    'json': {
    'name': 'Leah Castro',
    'address': '33176 Pollard Mews\nMayhaven, PW 94085',
},
    'key94199': 'value37521',
    'key26878': 'value93041',
    'key55779': 'value31197',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Joshua Chambers',
    'address': '6401 Meyer Brook Apt. 652\nLauramouth, LA 86402',
    'text': 'Fund often then current.\nSpace friend program response along throughout sure. Amount its on already. Number report feel enough.',
    'email': 'belinda86@example.com',
    'phone_number': '+1-269-994-8624x75387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Chaney',
    'Laura Jones',
    'Vanessa Walker',
    'Matthew Gray',
    'Robert Davis',
    'Mark Martinez',
],
    'json': {
    'name': 'Brandon Townsend',
    'address': '402 Caleb Plaza Apt. 089\nNew Erikchester, DC 09697',
},
    'key45389': 'value87989',
    'key93691': 'value67678',
    'key8552': 'value64562',
    'key98207': 'value36608',
    'key67943': 'value58860',
    'key92630': 'value71915',
    'key40083': 'value66841',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Matthew Potts',
    'address': '270 Tristan Extensions Apt. 290\nHarttown, RI 61015',
    'text': 'Positive choice town so walk she. Here father actually must. End analysis anything free.\nBillion main realize condition for ground she. Process necessary true two into street hotel.',
    'email': 'wharris@example.net',
    'phone_number': '6282308841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'George Perry',
    'Jacqueline Hunter MD',
    'Christopher Johnson',
    'Dana Knox',
    'Colin Trevino',
    'Ryan Martinez',
    'Sandra Salas',
],
    'json': {
    'name': 'Stephanie Hickman',
    'address': '7400 Hannah Walk Suite 190\nBoothside, WV 32241',
},
    'key46350': 'value72971',
    'key30686': 'value65587',
    'key76925': 'value31503',
    'key65730': 'value7736',
    'key45422': 'value99649',
    'key68584': 'value34535',
    'key86928': 'value13351',
    'key93229': 'value99792',
    'key42079': 'value60362',
    'key54784': 'value3643',
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
    'RequestId': '84f44e15-62ef-11f0-ad1e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_10_579318yeZNyuJH',
    'dimension': 32,
    'primaryField': 'id',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-1]_1752744131.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId3210011752744131Json()
    test.run_tests()
