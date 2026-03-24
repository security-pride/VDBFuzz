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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-2]_1752744130_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-2]_1752744130.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId3210021752744130Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-2]_1752744130.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-2]_1752744130.json"
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
    'RequestId': '840d03d3-62ef-11f0-b4ed-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_09_063550CNKIlFsX',
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
    'RequestId': '842e7e74-62ef-11f0-9af1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_09_063550CNKIlFsX',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Melissa Sandoval',
    'address': '46527 Allen Trail Suite 523\nPricebury, NV 33200',
    'text': 'Represent five catch require travel us which. Director leg audience threat store. Question college appear hear open push step allow.',
    'email': 'heather23@example.net',
    'phone_number': '290-479-4885x728',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'David Barrett',
    'Christopher Estrada',
    'James Nguyen',
    'Alexis Porter',
    'Jeffery Bush',
    'Jonathan Lee',
    'Jennifer Logan',
    'Joe Young',
    'Brandon Rivera',
    'Bryan Schroeder',
],
    'json': {
    'name': 'Jacqueline Moore',
    'address': '769 Holloway Orchard\nAndreashire, DE 13412',
},
    'key82620': 'value59803',
    'key42974': 'value33083',
    'key39001': 'value25182',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'William Hughes',
    'address': '56826 Lee River\nLake Lauratown, GA 88755',
    'text': 'Page president hot. Sign market defense challenge.\nBoth likely offer. Push agreement note again today year. Perform church friend whatever early then. Summer owner mean change.',
    'email': 'rwilliams@example.org',
    'phone_number': '+1-979-643-6126x28013',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Kramer',
    'Gregory Floyd',
    'Adam Butler',
    'Benjamin Griffin',
    'Donna Leonard',
    'James Nichols',
    'Kimberly Johnson',
    'Michele Davis',
    'Mrs. Heidi Weiss',
],
    'json': {
    'name': 'Darlene Russell',
    'address': '3912 Jeffrey Field Suite 363\nLake Barbaraton, IL 86045',
},
    'key12064': 'value791',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'James Lewis',
    'address': '9934 Tucker Court\nLake Samuelfurt, MD 69911',
    'text': 'Smile different seat sense source serve smile.\nFamily what learn have more determine good.\nSupport be suggest exist. Brother first including pretty friend word.',
    'email': 'rkelly@example.com',
    'phone_number': '001-850-615-5446x41630',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'David Allison',
    'Lisa Aguilar',
    'Mr. Roy Jones',
    'Hailey Flynn',
    'Jessica Hoffman',
    'Kenneth Hawkins',
    'Christopher Norman',
    'Whitney Logan',
    'Adam Erickson',
    'Ann Frederick',
],
    'json': {
    'name': 'Jenna Morris',
    'address': '57150 Amanda Spurs\nSouth Matthewport, KY 27797',
},
    'key37073': 'value67985',
    'key35114': 'value3351',
    'key43485': 'value27264',
    'key43180': 'value54875',
    'key36223': 'value60634',
    'key46574': 'value68744',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Katelyn Norman',
    'address': '6480 Morgan Glen Suite 128\nJosephton, GU 99409',
    'text': 'Approach benefit specific up always manager detail. Himself industry bad perhaps.\nDefense close allow mention. Attorney table service enter attack speak. Remain western draw require because movie.',
    'email': 'michael59@example.net',
    'phone_number': '(511)518-2202x1784',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Jordan',
    'Donna Walker',
    'Sharon Young',
    'Meagan Fisher',
    'Jennifer Davis',
    'Mrs. Maria Jones MD',
    'Vickie Garrett',
    'Gregory Bryant',
    'Andrea Davidson',
],
    'json': {
    'name': 'Robert Odonnell',
    'address': '70777 Carl Crossroad Apt. 687\nWest Kelseyview, CO 93572',
},
    'key92834': 'value22189',
    'key86576': 'value84670',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Mrs. Brittany Rodriguez',
    'address': '585 Dodson Vista\nJeffreyville, TN 43199',
    'text': 'Trouble who appear child break. Their response out free. Hit far lose later consumer arrive.\nCan let land process next. Everyone politics tough develop fight likely brother suggest.',
    'email': 'yorkbrandon@example.com',
    'phone_number': '(803)784-2772x7334',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Dana Chase',
    'Andre Conley',
    'Randall Lewis',
    'Thomas Hernandez',
    'Kimberly Mitchell',
    'George Sandoval',
    'Dale Butler',
    'Tyler Kennedy',
],
    'json': {
    'name': 'Lisa Jenkins',
    'address': '556 Smith Inlet Apt. 528\nPoncetown, NY 25150',
},
    'key15039': 'value27438',
    'key26011': 'value69762',
    'key28171': 'value57630',
    'key95715': 'value58543',
    'key28020': 'value40437',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Pamela Caldwell',
    'address': '74293 Stephanie Crescent\nWest Ashleybury, MO 66066',
    'text': 'Bill trial central after available reveal agree. Value join economic across word. Tonight performance effort serious the.',
    'email': 'pamela48@example.org',
    'phone_number': '7203345014',
    'array_int_dynamic': [
    93449,
],
    'array_varchar_dynamic': [
    'Lisa Phillips',
],
    'json': {
    'name': 'Michelle Cline',
    'address': '4474 Misty Light\nCynthiaview, NM 95139',
},
    'key75104': 'value7990',
    'key55461': 'value54378',
    'key74515': 'value27054',
    'key65736': 'value75549',
    'key14473': 'value71523',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Toni Williams',
    'address': '26252 Clark Points\nSouth Matthew, CT 86155',
    'text': 'Ten walk method east economic safe. Fish often interest also. Program quickly himself morning them identify weight.',
    'email': 'harrisomar@example.com',
    'phone_number': '001-548-651-5014x4511',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Williams',
    'Dr. Robert Carter',
    'Ashley Williams',
    'Sandra Wilson',
    'Benjamin Phillips',
    'Todd Chavez',
],
    'json': {
    'name': 'Andrew Castillo',
    'address': '3573 Murphy Courts Suite 908\nJennifertown, AS 69266',
},
    'key26153': 'value61838',
    'key66938': 'value86650',
    'key20593': 'value94282',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Kari Hammond',
    'address': '1937 Salinas Knolls Apt. 377\nFrazierhaven, IL 63613',
    'text': 'Base live really so beautiful five establish. Week style put player most. List almost gas affect hear.',
    'email': 'stephenmiller@example.com',
    'phone_number': '(962)569-4010x056',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Elliott',
    'Amy Simmons',
    'Elizabeth Morales',
    'Stephanie Lee',
    'Todd Rice',
    'Luke Roberts',
    'Jennifer Burke',
    'Richard Lopez',
    'Norman Hernandez',
    'Todd Santiago',
],
    'json': {
    'name': 'Brian Erickson',
    'address': '6339 Martinez Route\nVelasquezton, VT 15262',
},
    'key48570': 'value26330',
    'key71880': 'value49352',
    'key51423': 'value96515',
    'key37614': 'value88000',
    'key7996': 'value44292',
    'key51848': 'value38420',
    'key66694': 'value47523',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Tamara Johnson',
    'address': '3314 Kelli Burgs\nEast Brianland, MA 24029',
    'text': 'Lawyer resource design. Choose do major here entire half. Television single per short read nearly true.\nSeek hand national character base have. Trial look page mind special paper soon successful.',
    'email': 'bstone@example.com',
    'phone_number': '+1-411-819-2346x657',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Darius Orr',
],
    'json': {
    'name': 'Martin Brown',
    'address': '6663 Reyes Curve\nNew Bryan, WI 27789',
},
    'key44618': 'value6271',
    'key68735': 'value64126',
    'key35448': 'value74075',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Amy Sullivan',
    'address': 'PSC 2903, Box 3361\nAPO AE 66358',
    'text': 'Common life field race amount. No if movement beat meet. Son put several style goal Mrs if. Born step seek win your special hand food.\nBlue he along manage. Give another point point.',
    'email': 'vwood@example.org',
    'phone_number': '340.839.5369',
    'array_int_dynamic': [
    19978,
],
    'array_varchar_dynamic': [
    'Kenneth Richards',
    'Louis Spencer',
    'Kelly Gardner',
    'Lisa Graham',
    'Brittany Walker',
    'Aaron Hall',
    'Alexander Walker',
    'Erin Hanson',
    'Melissa Contreras',
],
    'json': {
    'name': 'Amanda Knapp',
    'address': '78119 Robinson Streets Apt. 517\nBrownstad, HI 31766',
},
    'key93574': 'value31022',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Mark Perkins',
    'address': '65555 James Bypass Suite 213\nNorth Cynthiachester, ID 16250',
    'text': 'My democratic far common. Practice floor analysis.\nCultural political price any thousand trade stand foot. Song song nice town. Couple last too debate.',
    'email': 'mmorris@example.com',
    'phone_number': '550.558.9899x8712',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Dale Miller',
    'Joshua Ponce',
    'Jacob Woodward',
    'Shane Ramsey',
    'Melissa Mcintosh',
    'Leah Miller',
    'Jason Morse',
    'Danielle Cook',
    'William Garza',
    'Tanner Medina',
],
    'json': {
    'name': 'Christy Booth',
    'address': '784 Donaldson Rapids Apt. 376\nKington, MN 41407',
},
    'key14481': 'value98464',
    'key38606': 'value45805',
    'key21815': 'value97648',
    'key91413': 'value90284',
    'key23655': 'value33181',
    'key18776': 'value28407',
    'key44240': 'value95913',
    'key2884': 'value58767',
    'key73776': 'value40157',
    'key43941': 'value72879',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Todd Bowers',
    'address': '8094 Dickson Park\nBrookefort, IN 41758',
    'text': 'Better experience social section explain. Finally head decide staff. Book late manager worker religious professional conference.',
    'email': 'christineaustin@example.com',
    'phone_number': '670-747-2280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jenna Kelly',
    'Sherri Sims',
    'Larry Poole',
    'Kathy Chen',
    'Sharon Ruiz',
],
    'json': {
    'name': 'Kyle Hale',
    'address': '8687 Moody Forks\nPort Stephenborough, MP 30499',
},
    'key38327': 'value83639',
    'key16242': 'value1119',
    'key14659': 'value24571',
    'key61706': 'value82607',
    'key42043': 'value19179',
    'key42154': 'value60609',
    'key29143': 'value41553',
    'key56141': 'value37839',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Dr. Julian Graham',
    'address': '02471 Humphrey Underpass Suite 592\nJonesview, GU 22132',
    'text': 'Lay rock country. Eat example attack so word. Indicate seek four entire black.',
    'email': 'nicholassullivan@example.com',
    'phone_number': '001-361-401-1424x48087',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kristy Wilson',
    'Jessica Gibbs',
    'Casey Duran',
    'Laura Johnson PhD',
    'Stephanie Mitchell',
    'John Larsen',
    'Scott Galloway',
    'Sherry Ortiz',
    'Mrs. Kaitlyn Reed',
],
    'json': {
    'name': 'Christina Richardson',
    'address': '54940 Ruth Shoals Apt. 759\nGloriahaven, HI 14451',
},
    'key30315': 'value21885',
    'key30411': 'value17719',
    'key78131': 'value57008',
    'key49910': 'value20971',
    'key73470': 'value63505',
    'key67135': 'value86084',
    'key18060': 'value38407',
    'key55762': 'value22874',
    'key46687': 'value37732',
    'key65307': 'value77318',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Leah Brown',
    'address': '95180 Davis Keys\nSouth Steven, MP 50388',
    'text': 'Trip level red question grow generation. Allow baby begin student lay provide.\nLeft leave that south beyond service. Pull thousand activity play outside any thought.',
    'email': 'jrangel@example.com',
    'phone_number': '+1-877-458-3019x03056',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin King',
    'Frank Smith',
],
    'json': {
    'name': 'Ronald Brown',
    'address': '9589 Burns Valleys\nSampsonland, AL 12295',
},
    'key12770': 'value65727',
    'key56779': 'value65207',
    'key83202': 'value13235',
    'key51747': 'value7712',
    'key29905': 'value9188',
    'key34607': 'value29751',
    'key44678': 'value21458',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Jessica Ward',
    'address': 'Unit 3303 Box 4002\nDPO AA 58557',
    'text': 'Commercial for actually interview. Next its continue hot hope. Reason watch call talk author to ever good.',
    'email': 'ericobrien@example.net',
    'phone_number': '(786)994-8262',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Hawkins',
],
    'json': {
    'name': 'Stacy Pruitt',
    'address': '633 Lucas Branch Apt. 123\nLake Samanthafort, NC 45228',
},
    'key53339': 'value23691',
    'key88594': 'value49070',
    'key73786': 'value78442',
    'key59907': 'value58121',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Peter Frye',
    'address': 'Unit 3936 Box 3633\nDPO AP 37251',
    'text': 'Firm well ball audience close million car. Hope cut impact city poor model much turn.\nStep part can drug fall. Same do bank chair cup.',
    'email': 'danielhouston@example.org',
    'phone_number': '914-329-8729x260',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mark Sanchez',
    'Lisa Mcconnell',
    'Christina Parker',
    'Jose Scott',
    'Robert Garza',
],
    'json': {
    'name': 'Sara Johnston',
    'address': '22604 Tracy Route\nPort Amyborough, VA 68005',
},
    'key32290': 'value33241',
    'key4729': 'value22418',
    'key6681': 'value11678',
    'key34553': 'value86010',
    'key59074': 'value49980',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Kim Watts',
    'address': '594 Melissa Field\nJohnbury, MD 30635',
    'text': 'Pressure sound store picture. Front thing it she. Series organization father risk.\nBed difficult because fact stop. Best form financial member. Last task nation where.',
    'email': 'harold44@example.net',
    'phone_number': '+1-338-269-8863x8825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Orozco',
    'Kevin Cantrell',
    'William Gould',
    'Michelle Scott',
    'Michael Johnson',
    'William Howard',
    'Elizabeth Johnson',
    'Nicholas Parks',
    'Rachel Osborne',
],
    'json': {
    'name': 'Suzanne Smith',
    'address': '35200 Molly Grove Apt. 396\nNorth Thomashaven, NY 28793',
},
    'key43463': 'value62663',
    'key64721': 'value67670',
    'key92318': 'value25143',
    'key92219': 'value47609',
    'key82456': 'value88834',
    'key47454': 'value62346',
    'key11': 'value33252',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'David Brown',
    'address': 'USCGC Miller\nFPO AA 80762',
    'text': 'Bring understand claim daughter even front night owner. Run nature everything race still put worker. Manager because small special ahead.\nDinner begin citizen cup personal. Check American age.',
    'email': 'thomasgonzales@example.net',
    'phone_number': '+1-723-949-4169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'April Haas',
    'Nicole Greer',
    'Sarah Williams',
    'Michael Hunt',
    'Kristin Barker',
    'Jillian Woods',
],
    'json': {
    'name': 'Steven Smith',
    'address': '401 Seth Turnpike Apt. 728\nEllisbury, DE 36917',
},
    'key23493': 'value27224',
    'key36428': 'value52380',
    'key69299': 'value67535',
    'key4535': 'value75144',
    'key57989': 'value58454',
    'key7045': 'value68487',
    'key81781': 'value1745',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Austin Jones',
    'address': 'USCGC Wilkinson\nFPO AA 94479',
    'text': 'Threat better conference. Writer analysis people. Yes there oil eye like health tend.\nArea soldier here behind explain. Never population team real month bed rich like.',
    'email': 'robert18@example.net',
    'phone_number': '+1-536-396-3389x9105',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mark Thomas',
    'Sherry Miller',
    'Sara Brooks',
    'Mrs. Jasmin Thomas',
    'Jillian Smith',
    'Christine Mcbride',
],
    'json': {
    'name': 'Katherine Hendricks',
    'address': '9130 Wendy Greens Suite 896\nWeavershire, RI 27115',
},
    'key94951': 'value58762',
    'key29742': 'value85799',
    'key14115': 'value89284',
    'key81340': 'value77603',
    'key70523': 'value77148',
    'key33596': 'value65867',
    'key66894': 'value75141',
    'key66766': 'value50693',
    'key24377': 'value84490',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Keith Jacobs',
    'address': '7975 Rojas Mountains Apt. 079\nSouth Heidi, PR 81376',
    'text': 'Need type lead water. Green stuff career conference bit. At movement early treat girl during. Final member glass society everything.',
    'email': 'robertaperez@example.org',
    'phone_number': '745.717.4389x9639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tina Miller',
    'Gina Dixon',
    'Renee Adams',
    'Jo James',
    'Morgan Moore',
    'Deborah Campbell',
    'Benjamin Compton',
    'Jose Erickson',
    'Mario Rivera',
    'Mark Hooper',
],
    'json': {
    'name': 'Brittany Brewer',
    'address': '165 Mary Summit\nJohnbury, MD 86293',
},
    'key71078': 'value76745',
    'key82538': 'value45419',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Joseph Welch',
    'address': '54568 James Village Suite 024\nSouth Michael, NH 54278',
    'text': 'Knowledge popular contain subject. Medical step sister bit act course analysis fill.\nLocal behind sea child allow. Compare after field international water another.',
    'email': 'xcampbell@example.com',
    'phone_number': '001-297-657-9813x53270',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Gina Hendrix',
    'Cody Frazier',
    'Tamara Burnett',
    'David Robinson',
    'Joshua Brown',
    'Adrienne Gonzalez',
],
    'json': {
    'name': 'Felicia Morris',
    'address': '7169 Pham Haven Apt. 843\nBarnetthaven, HI 59270',
},
    'key71768': 'value48417',
    'key30525': 'value79374',
    'key92821': 'value5860',
    'key13519': 'value39162',
    'key60315': 'value39136',
    'key56369': 'value92342',
    'key96940': 'value83088',
    'key60196': 'value6907',
    'key18217': 'value75386',
    'key12554': 'value5861',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Justin Mills',
    'address': '93571 Kimberly Square Suite 491\nWilliamshire, AZ 85570',
    'text': 'Bar assume major available. Best strong something sound member line.',
    'email': 'csimmons@example.com',
    'phone_number': '001-825-323-7787',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Carol Shaw',
    'Devin Olson',
    'Grace Brown',
    'Kristine White',
    'Benjamin Jimenez',
    'Kerry Good',
    'Melissa Smith',
],
    'json': {
    'name': 'Stephanie Fritz',
    'address': '323 Robinson Street Apt. 115\nWest Laurenfort, KS 12375',
},
    'key43143': 'value33623',
    'key90062': 'value9130',
    'key14780': 'value3099',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Walter Long',
    'address': '5636 George Motorway\nJuliechester, IA 93547',
    'text': 'Save fast program interesting place chair. Truth admit often option green group opportunity.',
    'email': 'santiagolaura@example.net',
    'phone_number': '(759)703-1985',
    'array_int_dynamic': [
    1199,
],
    'array_varchar_dynamic': [
    'John Hammond',
    'Victoria Brown',
],
    'json': {
    'name': 'Christopher Williams',
    'address': '496 Shirley Course\nValdezbury, FL 59232',
},
    'key68146': 'value83954',
    'key55712': 'value34784',
    'key65826': 'value97444',
    'key42581': 'value54742',
    'key57041': 'value41054',
    'key59022': 'value40533',
    'key63431': 'value82419',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Nathaniel Walker',
    'address': '61026 Hicks Turnpike Suite 215\nMarcoville, NH 45570',
    'text': 'Buy assume next wife like. Ok recently become. Give ago behavior maintain traditional citizen more.\nStructure where know almost season method that.',
    'email': 'lewillie@example.net',
    'phone_number': '001-629-340-2896x6372',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Herrera',
],
    'json': {
    'name': 'Kevin Cooper',
    'address': 'Unit 3653 Box 6634\nDPO AA 73253',
},
    'key53650': 'value88537',
    'key1794': 'value81959',
    'key26470': 'value57937',
    'key2562': 'value54656',
    'key67005': 'value92573',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Max Sanders',
    'address': '2884 Lisa Brook\nHardybury, NE 34604',
    'text': 'Born compare something century involve behind position. Material discover environmental bank. Story ten economic different pick.\nMillion know adult again. Bar base imagine agree.',
    'email': 'jennifershepherd@example.net',
    'phone_number': '9195311209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Murphy',
    'Danielle Martin',
    'Alice Watkins',
    'Savannah Lopez',
    'Sean Merritt',
    'William Wilson',
    'William Butler',
],
    'json': {
    'name': 'Seth Cunningham',
    'address': '535 Benjamin Lock Suite 429\nMariafort, DE 12174',
},
    'key70216': 'value4168',
    'key57885': 'value11418',
    'key36202': 'value13634',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Regina Jones',
    'address': '395 Evan Via\nNew Edward, PA 51746',
    'text': 'Little air stand agency. Avoid time task probably join different market.\nThough really away effort service.\nFrom or probably board. Reflect relationship those him high. Police beyond theory.',
    'email': 'woodsthomas@example.com',
    'phone_number': '528.221.3332x76391',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mary Knight',
    'Michele Yoder',
    'Mark Cardenas',
],
    'json': {
    'name': 'Margaret Gomez',
    'address': '23949 Mccullough Terrace Suite 664\nAlexanderland, MS 93543',
},
    'key41469': 'value24601',
    'key17516': 'value3321',
    'key31847': 'value78196',
    'key89892': 'value89124',
    'key40610': 'value27471',
    'key58587': 'value20210',
    'key24020': 'value52894',
    'key68651': 'value92721',
    'key84653': 'value77950',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Mr. Jose Morris',
    'address': '3619 Barnes Course Apt. 713\nPort Mark, CA 15455',
    'text': 'Property strong participant school seek. Process determine quickly create little. Science trade bag might according debate risk.',
    'email': 'rballard@example.com',
    'phone_number': '(921)361-0026x03695',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Taylor',
    'Matthew Rosales',
    'Trevor Barnes',
    'Matthew Aguilar',
    'Jessica Wade',
    'Nancy Boone',
    'Thomas Francis',
],
    'json': {
    'name': 'Jason Brown',
    'address': '515 Fernandez Unions\nBerryborough, OH 17880',
},
    'key93531': 'value11483',
    'key73571': 'value59306',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Madeline Cain',
    'address': '737 Cunningham Well\nNorth Elizabeth, AZ 81195',
    'text': 'Expect girl scientist accept might fall. Above herself difference tend environmental experience. Agent television country down score room.',
    'email': 'wsilva@example.org',
    'phone_number': '(751)859-5368',
    'array_int_dynamic': [
    25352,
],
    'array_varchar_dynamic': [
    'Christopher Richardson',
    'Brittany Fisher',
    'Miguel Gallagher',
    'Maria Koch',
    'Kirk Allen',
    'Jose Daniels',
],
    'json': {
    'name': 'Michelle Romero',
    'address': '317 Ryan Gardens Apt. 490\nLake Bethport, DC 15551',
},
    'key838': 'value34443',
    'key75293': 'value13166',
    'key99407': 'value22467',
    'key60450': 'value98843',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Robin Brown',
    'address': '321 Herrera Park Suite 621\nNew Martin, ND 90452',
    'text': 'Central with fall. Executive doctor control together hotel them property.\nRelate employee heart market author. Sea anyone long under bank staff hit. Husband line picture think would.',
    'email': 'dawnjordan@example.org',
    'phone_number': '5553976327',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Mcclain',
    'Jeffery Booth',
    'Russell Nelson',
    'Cynthia Wilcox',
    'Mary Huff DVM',
    'Robert Melton',
],
    'json': {
    'name': 'William Hall',
    'address': '34023 Allison Vista Suite 940\nJenkinsberg, PW 48947',
},
    'key60880': 'value30963',
    'key91002': 'value6364',
    'key26185': 'value62980',
    'key75497': 'value80988',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Felicia Wang',
    'address': '277 Martinez Meadow\nNorth Larry, PW 72987',
    'text': 'Spend better professor management sport identify some. Want difficult begin wish. Why provide be provide rule wait.',
    'email': 'tannernicole@example.com',
    'phone_number': '(717)201-1546',
    'array_int_dynamic': [
    77234,
],
    'array_varchar_dynamic': [
    'Christopher Hinton',
    'William Frost',
    'Shannon Lawson',
    'Allen Lewis',
    'Sarah Petty DDS',
],
    'json': {
    'name': 'Cheryl Mathis',
    'address': '76405 Ruth Circle Suite 146\nBarryland, IN 19602',
},
    'key19650': 'value86497',
    'key70063': 'value72341',
    'key74947': 'value7549',
    'key87654': 'value7140',
    'key92435': 'value99134',
    'key27112': 'value31026',
    'key13829': 'value92896',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Christopher Kaufman',
    'address': '33853 Denise Summit Apt. 983\nNorth Stevenport, CA 94559',
    'text': 'Section believe take town fire quickly. Identify shake morning other.\nDraw education travel task leave these everything lawyer. Relationship green unit arrive debate know.',
    'email': 'wendy41@example.com',
    'phone_number': '(270)357-3123x2245',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Hanson',
    'Tina Lawrence',
    'Rita Smith',
    'Laurie Grant',
    'Todd Fowler',
    'Luis Huff',
    'Helen Conner',
    'Curtis Brown',
    'David Ross',
],
    'json': {
    'name': 'Jacob Walker',
    'address': '5176 Brett Extensions\nEast Steven, KS 01221',
},
    'key21363': 'value51868',
    'key13289': 'value86495',
    'key84175': 'value9124',
    'key59406': 'value65787',
    'key90353': 'value14566',
    'key41186': 'value6745',
    'key26510': 'value67850',
    'key97896': 'value96864',
    'key71527': 'value61720',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'David Graves',
    'address': '977 Smith Plains Suite 048\nLake Brandi, AS 28972',
    'text': 'Agency social mother strategy guy.\nDecade enough dark dinner. Character behavior investment physical. Quality cell its woman purpose why teach ground.',
    'email': 'valenciasean@example.com',
    'phone_number': '001-429-899-6327x23734',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mary Sandoval',
    'Wendy Carroll MD',
],
    'json': {
    'name': 'Robin Jordan',
    'address': '133 Linda Extension\nNew Jessicaland, NE 58994',
},
    'key89331': 'value77218',
    'key8973': 'value45013',
    'key92992': 'value27340',
    'key29437': 'value8201',
    'key78298': 'value52509',
    'key93472': 'value18421',
    'key21851': 'value51078',
    'key26278': 'value29368',
    'key34352': 'value56050',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Amber West',
    'address': '9381 Walker Lodge\nAlexandrastad, ID 87166',
    'text': 'Rule industry nice sometimes. Later husband various animal forward poor around position.\nBetter scientist public recent.',
    'email': 'hbennett@example.org',
    'phone_number': '362.626.6813x011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Delgado',
    'Tammy Hernandez',
    'Todd Anderson',
    'Casey Green',
    'Edward Chang',
    'Monica Curry',
    'Craig Powell',
],
    'json': {
    'name': 'William Green',
    'address': '8843 Amy Hill\nNew Tammy, GA 96582',
},
    'key42821': 'value9951',
    'key11743': 'value33714',
    'key92069': 'value71687',
    'key27793': 'value29251',
    'key31440': 'value87443',
    'key45703': 'value78464',
    'key26591': 'value56747',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Erika Noble',
    'address': '795 Aaron Cove Suite 222\nShawnborough, MA 31864',
    'text': 'New side ago stock others time. Study miss research now concern network. Positive house yet fund large less ok.',
    'email': 'smithcassidy@example.org',
    'phone_number': '(831)839-4127x877',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'David Hunter',
    'Nicholas Martin',
    'Tyler Brown',
    'Monica Sullivan',
    'Sheila Boone',
    'Kelly Meyer',
    'Maureen Hayes',
    'Kristen Mills',
    'Adam Vasquez',
],
    'json': {
    'name': 'Ellen Thompson',
    'address': '3210 Michael Forge\nRoberttown, AS 75837',
},
    'key15580': 'value70125',
    'key54109': 'value7755',
    'key95963': 'value67515',
    'key13173': 'value55743',
    'key55384': 'value61548',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Nicholas Brown',
    'address': '68489 William Squares\nBoydfort, TN 59088',
    'text': 'Half world country use several large. Pull whether often stock agent role.\nYour off huge figure your. Spring hospital toward serve support something material family.',
    'email': 'gatesrachel@example.org',
    'phone_number': '001-637-906-0881x0511',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Austin Cervantes',
    'Jocelyn Smith',
    'Luis Myers',
    'Wesley Dixon',
    'Jesse Austin',
    'Brianna Mitchell',
    'Michele Chavez',
    'Diane Farrell',
    'Craig King',
],
    'json': {
    'name': 'Erik Hall',
    'address': '2393 Ford Mountains Suite 025\nTammybury, NE 83021',
},
    'key4747': 'value95863',
    'key52619': 'value1390',
    'key51509': 'value58127',
    'key82602': 'value64522',
    'key15085': 'value23477',
    'key15154': 'value70347',
    'key78971': 'value35197',
    'key81370': 'value15607',
    'key30211': 'value54432',
    'key67805': 'value51138',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Andrew Lewis',
    'address': '86769 Keith Union\nLake Calvin, GA 81602',
    'text': 'Account member which history later. Someone sell season. Record easy truth very worry scientist group.',
    'email': 'benjaminlisa@example.net',
    'phone_number': '001-603-726-6465',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Stuart',
    'Kimberly Burnett',
    'Michael Allen',
    'Kaitlin Johnson',
],
    'json': {
    'name': 'Robin Thomas',
    'address': 'USS Lambert\nFPO AP 89523',
},
    'key31107': 'value60990',
    'key59378': 'value25797',
    'key55979': 'value9776',
    'key15941': 'value59655',
    'key36574': 'value31805',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Frank Roberson',
    'address': '02046 Green Inlet Apt. 652\nRobertburgh, GU 38846',
    'text': 'Act hard time owner yes. Entire begin quite police teacher population his. Dinner girl national bad this.\nDrop there doctor. When protect doctor heavy others. Apply theory young a four.',
    'email': 'brittneysanchez@example.org',
    'phone_number': '485.413.6047',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Allison Salas',
    'Michael Frazier Jr.',
    'Michael Pena',
    'William Howard',
    'Mario Cook',
    'Gary Brown',
    'Charlene Hill',
],
    'json': {
    'name': 'Mr. Christopher Wilson',
    'address': '518 Barrera Isle Apt. 518\nPort Christopher, OR 69115',
},
    'key84241': 'value17411',
    'key76952': 'value48831',
    'key42837': 'value13502',
    'key80345': 'value43784',
    'key43708': 'value11779',
    'key15342': 'value85796',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Brianna Blankenship',
    'address': '52568 Jackson Hollow\nPort Adamhaven, AZ 07675',
    'text': 'Space class those type right blue involve. One case media military represent provide picture yeah. Process growth answer commercial.',
    'email': 'patrick04@example.org',
    'phone_number': '(784)644-3797x99298',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Nash',
    'Michael Lamb',
],
    'json': {
    'name': 'Jordan Hansen',
    'address': '94352 Maria Tunnel Apt. 447\nMillerfort, ID 70678',
},
    'key29302': 'value39995',
    'key35940': 'value62295',
    'key24227': 'value82936',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'David Lester',
    'address': '654 Michael Track Apt. 952\nRiveraport, OH 94282',
    'text': 'Address hand arrive under meet. Run discussion half late hospital administration better. Simple others blood house.\nThese only some strategy perhaps up. Factor suddenly media full reach other town.',
    'email': 'chase74@example.net',
    'phone_number': '506.805.2909x725',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'John Clements',
    'Kimberly Sanchez',
    'Jerry Nguyen',
],
    'json': {
    'name': 'Brittany Pineda',
    'address': '53993 Armstrong Well Suite 129\nHortonmouth, NH 60209',
},
    'key77231': 'value61566',
    'key94873': 'value38383',
    'key5134': 'value9068',
    'key457': 'value93710',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'George Haynes',
    'address': 'PSC 0215, Box 8910\nAPO AP 51392',
    'text': 'If answer give financial term fall. Production speak him personal.\nHimself manager pay mother.\nCommunity receive why opportunity when sort want. Vote enjoy boy maybe decide night without success.',
    'email': 'jason32@example.org',
    'phone_number': '(902)892-8351x5500',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Richard Green',
    'John Guerrero II',
    'Zachary Williams',
    'Evan Bauer',
    'Ronald Barr',
    'Kevin Lawrence',
    'Melissa Martinez',
    'Jordan Brown MD',
    'Tara Ward',
    'Tracy Hoffman',
],
    'json': {
    'name': 'Carrie Jones',
    'address': '2731 James Harbor Suite 758\nPaulaport, OK 87277',
},
    'key83522': 'value95396',
    'key81064': 'value97529',
    'key59362': 'value77780',
    'key38612': 'value8054',
    'key67317': 'value80234',
    'key28984': 'value12431',
    'key62453': 'value96421',
    'key64822': 'value4944',
    'key5258': 'value41577',
    'key99234': 'value81360',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Joel Booker',
    'address': '60038 Carol Alley\nNorth Kelli, TN 94630',
    'text': 'Finish baby edge fly real police. Can evening ready so career represent.\nTravel back material strong itself yeah. Purpose argue safe middle five dog understand.',
    'email': 'sharonweaver@example.com',
    'phone_number': '(225)513-0250x7108',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Julie Bush',
],
    'json': {
    'name': 'Mrs. Ashley Fisher DDS',
    'address': '1188 Michael Tunnel\nClinehaven, NH 69691',
},
    'key56453': 'value17546',
    'key23771': 'value53205',
    'key52911': 'value28077',
    'key25705': 'value58054',
    'key13040': 'value28422',
    'key69168': 'value69707',
    'key31625': 'value27410',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Mr. Joshua Williams',
    'address': '476 Kimberly Pines Suite 356\nRyanton, IN 98312',
    'text': 'Travel step draw other especially. Inside forward interview provide ever hundred. Everything executive oil foreign Mrs main federal.\nSo behind share cell main easy give. Reason conference action age.',
    'email': 'medinamichele@example.net',
    'phone_number': '001-786-614-0703x11364',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Walters',
    'Dean Rodriguez',
    'Laura Patton',
],
    'json': {
    'name': 'Nicholas Myers',
    'address': '627 Gomez Spring Apt. 305\nLucasmouth, WI 17907',
},
    'key91293': 'value20737',
    'key54647': 'value39341',
    'key26983': 'value9142',
    'key65136': 'value45217',
    'key28106': 'value50342',
    'key16683': 'value64076',
    'key62683': 'value79834',
    'key93453': 'value73778',
    'key60969': 'value71716',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Beth Ellis',
    'address': '30958 Curry Meadow Suite 086\nGreenfurt, DC 93374',
    'text': 'Same performance like food street skin activity. Arm song bank home bed pay me. Door expect wonder attack.\nFinally entire scientist. View show treat. Hot drop forget will red current.',
    'email': 'jeremyjohnson@example.org',
    'phone_number': '(284)999-7798x84841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Morris',
    'Jacob Green',
    'Ernest Morris',
    'Michael Williams',
    'Leslie Miller',
    'Amber Taylor',
    'Janice Middleton',
    'Adrienne Smith',
    'Jonathan Smith',
],
    'json': {
    'name': 'Steve Bailey',
    'address': '6607 Brian Plaza\nPort Shirley, PR 23769',
},
    'key80300': 'value36843',
    'key53023': 'value23780',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Danielle Brown',
    'address': '671 Lindsey Shore\nSouth Lydiaton, WI 46770',
    'text': 'Interesting bring organization woman approach vote. Front look wonder deal set fish. Even peace nor exist drug world.',
    'email': 'jasmine14@example.org',
    'phone_number': '532.964.3782',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Miss Terri Smith',
    'David Blake',
    'Scott Williams',
    'Carla Clark',
],
    'json': {
    'name': 'Mary Reid',
    'address': '20716 Noah Prairie Suite 236\nSouth Marcusview, CT 33645',
},
    'key81710': 'value85995',
    'key20423': 'value78791',
    'key99748': 'value37769',
    'key22784': 'value50667',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Alicia Powell',
    'address': '06262 John Plains\nWest Becky, AR 29349',
    'text': 'Sell coach successful. Least imagine visit happen property garden.\nScience garden court billion and executive receive. Several bit through piece allow college someone reduce. Thank case oil.',
    'email': 'rebecca72@example.com',
    'phone_number': '(846)486-2135',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gloria Allen',
    'Billy Daniels',
    'Christina Hernandez',
    'Mitchell Aguirre',
    'Jennifer Figueroa',
    'Barbara Blevins',
    'Casey Perez',
],
    'json': {
    'name': 'Eddie Powell',
    'address': '689 Ball Flat Apt. 174\nPort Amymouth, CA 96056',
},
    'key56908': 'value74456',
    'key56402': 'value74123',
    'key72413': 'value82152',
    'key54755': 'value98628',
    'key61007': 'value5002',
    'key14083': 'value29922',
    'key77101': 'value70994',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Jeffrey Bridges',
    'address': '34265 Anthony Viaduct\nEast Amy, NE 45472',
    'text': 'Cut admit experience use company arrive list. Design sister individual. Particularly professional candidate home bag.\nRight dog lose member simple significant. Risk may require do.',
    'email': 'anita49@example.org',
    'phone_number': '998-924-7879x729',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mark Bennett',
    'Lauren Sanchez',
    'Katie Fisher',
    'Jessica Brown',
    'Meagan Malone',
    'Scott Mata',
    'Eric Donovan',
    'Andrew Benton',
    'Maria Boyd',
],
    'json': {
    'name': 'Matthew Stokes',
    'address': '91474 Keith Lock\nPort Rachael, IL 79789',
},
    'key9700': 'value67599',
    'key27761': 'value38335',
    'key60902': 'value29203',
    'key22732': 'value84470',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Benjamin Torres',
    'address': '1811 Amber Squares\nLake Kimberlybury, CA 79049',
    'text': 'Whom him several important community. Suffer deal far through leave tree final.\nMinute letter along series. One citizen event popular play.',
    'email': 'howardian@example.com',
    'phone_number': '967-389-5987x18115',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Roberto Roberts',
    'Tiffany Cruz',
    'Debra Tyler',
    'Michael Miles',
    'Jordan Sosa',
    'Sandra Henderson',
    'Teresa Rubio',
],
    'json': {
    'name': 'Mr. Anthony Gill',
    'address': '0551 Lindsay Center Suite 820\nNew Emilyhaven, AR 48464',
},
    'key57705': 'value96597',
    'key99283': 'value19216',
    'key35786': 'value11712',
    'key69309': 'value28587',
    'key83356': 'value36942',
    'key43295': 'value57387',
    'key15603': 'value79645',
    'key78332': 'value15008',
    'key13780': 'value81293',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Christina Walton',
    'address': '37119 Perkins Flats Suite 108\nEast Angelshire, NJ 04395',
    'text': 'Figure accept style develop. Happy say probably general way player.',
    'email': 'corey16@example.org',
    'phone_number': '(999)398-6357',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Peterson',
    'John Miller',
    'Brandon Harris',
    'Kimberly Wilson',
    'Donna Bryan',
],
    'json': {
    'name': 'Joseph Sanchez',
    'address': '535 Johnson Extensions\nJosephville, CT 60580',
},
    'key41577': 'value69551',
    'key83918': 'value83315',
    'key48399': 'value83529',
    'key64431': 'value19821',
    'key55834': 'value75797',
    'key92305': 'value74285',
    'key7525': 'value91105',
    'key16322': 'value60209',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Luke Cole',
    'address': 'Unit 2487 Box 4908\nDPO AA 90343',
    'text': 'Generation number everyone character majority deal. Read yourself year.\nTell cut authority throughout. Event seek song agency second fact story.',
    'email': 'ymartin@example.com',
    'phone_number': '001-502-375-6450x4871',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Logan Wu',
    'Emily Oliver',
],
    'json': {
    'name': 'Christian Walker',
    'address': 'USS Murphy\nFPO AE 97339',
},
    'key67688': 'value24316',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Corey Roberson',
    'address': '507 Timothy Lodge\nSouth Mark, TN 36715',
    'text': 'White condition class lose risk. Agency notice almost office. Financial identify agreement PM exactly language camera lay.',
    'email': 'kathryn86@example.net',
    'phone_number': '001-263-865-7405x452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Misty Wise',
    'Kimberly Barnett',
],
    'json': {
    'name': 'Patrick Hicks',
    'address': '3679 Elizabeth Key Suite 939\nAdamsshire, IL 53215',
},
    'key34280': 'value35610',
    'key26477': 'value47622',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Victoria Torres',
    'address': 'PSC 7176, Box 9160\nAPO AP 96311',
    'text': 'Article enough activity beat month animal water. Election never certain case ever.\nImage politics recently you. Instead son thank.',
    'email': 'david26@example.com',
    'phone_number': '302-481-7059x7581',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Newman',
    'Ms. Meredith White',
    'Lisa Jones',
    'Catherine Mcconnell',
    'James Vaughn',
    'Joshua Luna',
    'Trevor Fox',
    'David Obrien',
    'Dana Cunningham',
],
    'json': {
    'name': 'Patricia Fernandez',
    'address': '39483 Jennifer Ports Apt. 502\nPughfort, NM 95623',
},
    'key17651': 'value88156',
    'key99438': 'value35106',
    'key2178': 'value69928',
    'key68764': 'value54108',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Dr. Adam Taylor',
    'address': '10113 Dean Row\nLeeton, AL 85194',
    'text': 'Foot whatever year phone author such involve three. Enjoy alone perhaps bit town training drug despite. Heart stop financial let car reality Republican.',
    'email': 'peter16@example.org',
    'phone_number': '001-338-776-6785x484',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Garcia',
    'James Young',
    'Sheila Lindsey',
    'Matthew Spears',
    'Chad Santiago',
    'Brandy Perry',
],
    'json': {
    'name': 'Suzanne Williams',
    'address': '183 Mary Knoll Suite 618\nHardychester, UT 63139',
},
    'key95577': 'value17456',
    'key28398': 'value72126',
    'key50735': 'value23649',
    'key3350': 'value66653',
    'key3079': 'value24057',
    'key70929': 'value54074',
    'key30943': 'value61329',
    'key12006': 'value96850',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Sean Roberts',
    'address': '995 Carlos Isle\nAmberfort, PA 81065',
    'text': 'Speech gas about air. Ball their eat operation instead.\nFar modern south agree mention myself open air. None later minute rock avoid often ability exist. Early may various different.',
    'email': 'whammond@example.com',
    'phone_number': '681.704.8921x641',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Jackson',
    'Lori Bell',
    'Sarah Patterson',
    'Hayley Russell',
    'Erika Allen',
    'Sheila Fitzpatrick',
    'Alec Mendoza',
    'Michael Nguyen',
    'James Smith Jr.',
],
    'json': {
    'name': 'Joshua Reed',
    'address': '55710 Nicholas Circles\nThomasmouth, NM 87959',
},
    'key42402': 'value74632',
    'key45788': 'value73915',
    'key37925': 'value66774',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Justin Davis',
    'address': 'USNS Reeves\nFPO AP 26909',
    'text': 'Edge majority city sell military customer nearly. Popular red last pay. By land cup bed somebody smile now.',
    'email': 'chad95@example.net',
    'phone_number': '2917401332',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Jones',
    'Gary Edwards',
    'Andrew Leonard',
    'Deborah Wright',
    'Rachel Fisher',
    'Robert Franco',
    'Dawn Lopez DDS',
    'Elizabeth Lewis',
],
    'json': {
    'name': 'Jeffrey Hill',
    'address': '8215 Bowman Springs Suite 991\nLake Katie, VT 99491',
},
    'key49767': 'value6346',
    'key8815': 'value53427',
    'key32381': 'value14053',
    'key10468': 'value60355',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Angelica Ramirez',
    'address': 'Unit 2565 Box 1701\nDPO AE 22027',
    'text': 'Tv your beat law from. Forget conference religious those election measure professional.\nMaybe sort realize recognize term couple fire.',
    'email': 'tiffanyvasquez@example.net',
    'phone_number': '(957)788-0660',
    'array_int_dynamic': [
    66669,
],
    'array_varchar_dynamic': [
    'Jeremy Mitchell',
    'Linda Shea',
    'Chad Lee',
    'Robert Hughes',
    'Christine Sanchez',
    'Bobby Smith',
    'Paul Hebert',
    'Kristi Wilson',
    'William Stone',
    'Tristan Collins',
],
    'json': {
    'name': 'Megan Nguyen',
    'address': '4925 Hernandez Burg Apt. 250\nLopezberg, LA 30163',
},
    'key21762': 'value25655',
    'key64405': 'value7845',
    'key41365': 'value94528',
    'key6799': 'value63017',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Alicia Chambers',
    'address': 'Unit 3515 Box 0850\nDPO AE 04570',
    'text': 'Nearly successful believe rock special knowledge plant her. Appear there industry future should better. Upon modern enough trip direction tree.',
    'email': 'eringordon@example.net',
    'phone_number': '7933777379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marissa Butler',
    'Cameron Casey',
    'Bradley Sweeney DDS',
],
    'json': {
    'name': 'Claire Harris',
    'address': '90711 Molina Isle\nKatieshire, RI 01664',
},
    'key19838': 'value92054',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Joshua Pierce',
    'address': '57909 Mary Underpass Suite 597\nNathantown, AR 08819',
    'text': 'Street box of Republican certainly family ok. Within anyone bad idea. Pick fire make control morning type.\nSmile cold kid wall more election. Defense green memory add. Community by five over.',
    'email': 'jill00@example.org',
    'phone_number': '+1-383-460-6180x5920',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dennis Barnett',
    'Dr. Tracy Mendoza',
    'David Ortiz',
    'Jennifer Perez',
],
    'json': {
    'name': 'Angela Walker',
    'address': '35216 Ray Extension\nVaughanmouth, CA 92831',
},
    'key28126': 'value3275',
    'key8505': 'value91578',
    'key22478': 'value24909',
    'key56192': 'value14972',
    'key74934': 'value83824',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Carlos Smith',
    'address': 'USNV Miller\nFPO AP 16785',
    'text': 'Have should seat state two. Man fact during game piece once color.\nFamily management since they teacher. From family strategy southern it red act.',
    'email': 'adamcarlson@example.org',
    'phone_number': '+1-534-673-3017x6088',
    'array_int_dynamic': [
    93311,
],
    'array_varchar_dynamic': [
    'Christopher Roberts',
    'Steven Wilson',
],
    'json': {
    'name': 'Ebony Valentine',
    'address': '6405 Elizabeth Plaza Suite 080\nChurchland, MH 53739',
},
    'key70947': 'value9771',
    'key9997': 'value66794',
    'key69458': 'value58320',
    'key39925': 'value145',
    'key19807': 'value87823',
    'key89114': 'value14796',
    'key571': 'value8007',
    'key9496': 'value83894',
    'key22260': 'value1556',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Catherine Adams',
    'address': '644 Matthew Pass Suite 961\nPenaborough, WV 46204',
    'text': 'Force structure study season stuff tell factor. Behavior factor film north north happy room.',
    'email': 'hammondlisa@example.com',
    'phone_number': '601-658-8039',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Russell Blackburn',
    'Christopher Brown',
    'Kristina Campbell',
],
    'json': {
    'name': 'Troy Stevens',
    'address': '92398 Schwartz Plain\nSouth Jack, FM 21081',
},
    'key65320': 'value68672',
    'key41256': 'value75160',
    'key45432': 'value95439',
    'key18719': 'value60225',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Katie Christensen',
    'address': '46488 Betty Pike Suite 756\nNorth Michael, WI 63078',
    'text': 'Nearly important chair relate. Mother child admit word matter hour blood.\nDirection worry decide fly degree player explain. Begin religious year either economic economic.',
    'email': 'brittanyclark@example.net',
    'phone_number': '490-500-7042',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Alisha Brown',
],
    'json': {
    'name': 'Kimberly Phillips',
    'address': '3658 Steven Mills Suite 615\nWest Michaelport, MN 32474',
},
    'key31609': 'value23162',
    'key97698': 'value20324',
    'key86846': 'value20720',
    'key61510': 'value4714',
    'key93115': 'value5535',
    'key12322': 'value42363',
    'key37972': 'value90347',
    'key66843': 'value10116',
    'key56745': 'value73299',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Anthony Webb',
    'address': '393 Brown Port\nPort Shannon, MI 10833',
    'text': 'Perform again late of. Administration realize type common. Strong create fill shoulder.',
    'email': 'ldean@example.org',
    'phone_number': '+1-811-936-5197x53542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Susan Welch',
    'Kayla Lucero',
    'Joshua Collins',
    'Brandon Allison',
    'Alyssa Jones',
],
    'json': {
    'name': 'Christopher Weaver',
    'address': '04974 Hester Summit\nNorth Elizabethfort, AS 91315',
},
    'key74337': 'value78854',
    'key13018': 'value17519',
    'key674': 'value87065',
    'key31231': 'value27283',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'John Martinez',
    'address': '806 Monique Meadow Suite 535\nCervanteston, ND 92359',
    'text': 'Run central open. Design the class daughter.\nLive nearly become certainly. Series a friend agree leader serious. Bring pick suddenly laugh herself off age.',
    'email': 'omartinez@example.org',
    'phone_number': '+1-770-643-3260x664',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Jackson',
    'Kyle White',
    'Alejandra Wallace',
    'Raymond Cochran',
    'Connie Roth',
    'Richard Santos',
    'Richard Scott',
    'John Kramer',
    'Amy Andrews',
],
    'json': {
    'name': 'Peter Jordan',
    'address': '499 Edwards Common\nNorth Elaine, TX 82511',
},
    'key2636': 'value50043',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Steven Bailey',
    'address': '116 Kenneth Lake Suite 934\nSouth Shane, PW 19526',
    'text': 'Join tonight certainly mission range.\nShare risk across individual book summer. Chair law nature item owner build staff.\nPlay lay image. Within friend trial no once.',
    'email': 'roblesemily@example.net',
    'phone_number': '+1-984-722-8477',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Medina',
    'Michael Moore',
    'Andrew Powers',
    'David Johnson',
    'Katherine Valdez',
    'Scott Aguilar',
],
    'json': {
    'name': 'Lisa Wu',
    'address': '82482 Johnson Creek\nChristianberg, WI 90010',
},
    'key85542': 'value22478',
    'key17666': 'value40021',
    'key45350': 'value79684',
    'key2780': 'value50339',
    'key59486': 'value24663',
    'key88359': 'value58379',
    'key70028': 'value95120',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Bradley Peters',
    'address': '21649 Stewart Brook Apt. 245\nTarastad, DC 76228',
    'text': 'Section rise age machine month break choice. Evidence production second probably with.\nFine serious hope dream. Recent letter wish partner about. Later move student sport she difference become.',
    'email': 'iwalter@example.net',
    'phone_number': '(377)531-8028x10496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Reed',
    'Randy Holland',
    'Valerie Palmer',
],
    'json': {
    'name': 'Anthony Sheppard',
    'address': '95995 Stewart Radial\nAnthonychester, SD 86553',
},
    'key43825': 'value62655',
    'key27443': 'value7040',
    'key92094': 'value17755',
    'key57650': 'value60564',
    'key95301': 'value65562',
    'key56863': 'value99954',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Kyle Vasquez',
    'address': '2794 Carolyn Forges\nRichardsborough, IN 63428',
    'text': 'Budget group southern necessary off staff term. Thing measure various begin traditional reflect. Theory number state just analysis high finish really.',
    'email': 'lowens@example.net',
    'phone_number': '8773974025',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Baker',
],
    'json': {
    'name': 'Hunter Morgan PhD',
    'address': '8595 Morgan Coves Apt. 646\nEast Steveshire, VA 42823',
},
    'key39208': 'value23016',
    'key69068': 'value74716',
    'key86692': 'value65526',
    'key4262': 'value31932',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Rebecca Ward',
    'address': '16010 Villarreal Inlet Apt. 341\nScottburgh, PA 54304',
    'text': 'State them live modern. Front wear left term feel strong person.\nShare music thing often security. This ground everything PM.',
    'email': 'nelsonrebecca@example.com',
    'phone_number': '654-497-4016x15755',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Katrina Johnson',
    'Kenneth Cross MD',
    'Kaylee Ruiz',
    'Katelyn Gibbs',
    'Kevin Gonzalez',
    'Kelsey Davis',
    'Renee Wu',
    'Mr. Tracy Smith Jr.',
    'Charles Glass',
],
    'json': {
    'name': 'Wendy Hopkins',
    'address': '1959 Kristin Inlet Suite 586\nWest Nicoleview, IL 54520',
},
    'key2953': 'value2985',
    'key43705': 'value35102',
    'key25381': 'value99669',
    'key21046': 'value10343',
    'key50548': 'value22310',
    'key82594': 'value5955',
    'key91394': 'value97669',
    'key85984': 'value6250',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Sharon Jordan',
    'address': '35491 Perry Forest Apt. 963\nLindsaybury, AS 47805',
    'text': 'Ago to seat room in others. Learn report into simple benefit stage safe. Nature reality figure including color.\nReligious reach series loss.',
    'email': 'haynescatherine@example.com',
    'phone_number': '+1-516-243-4675x3929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Charles Gonzalez',
    'Melissa Guerra',
    'Debbie Kennedy',
    'Brian Gonzalez',
    'Christopher Miranda',
    'Rebecca Mendoza',
    'Amy Patel',
    'Derek Kent',
    'Patrick Fernandez',
    'Bobby Jackson',
],
    'json': {
    'name': 'James Carlson',
    'address': '5207 Diana Plains\nWest John, AR 60436',
},
    'key46783': 'value85439',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Lisa Hawkins',
    'address': '674 Joel Branch Suite 996\nChristopherhaven, IL 82745',
    'text': 'Station night paper choice. Drop door mission.\nDegree base serve. Here run deal everything job ask. Computer moment prepare.',
    'email': 'ronaldrichards@example.com',
    'phone_number': '210-301-8178',
    'array_int_dynamic': [
    35021,
],
    'array_varchar_dynamic': [
    'Michael Park',
    'John Knox',
    'Eric Nicholson',
    'Amy Quinn',
    'Jeremy Larson',
],
    'json': {
    'name': 'Jennifer Gordon',
    'address': '092 Angela Mission Apt. 881\nNew Juan, OH 46887',
},
    'key74603': 'value70853',
    'key62197': 'value59442',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Marcia Adams',
    'address': '56227 Hale Path Apt. 178\nPort Williamview, MT 31247',
    'text': 'Kind section order. Occur price shake final.\nLittle respond song market trouble skin. Somebody than grow. Feel shake food worker remember idea employee.',
    'email': 'livingstonjohn@example.com',
    'phone_number': '(999)442-4539x58318',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jim Gardner Jr.',
    'Courtney Robertson',
    'Eric Harris',
    'Daniel Thompson',
    'Tanya Day',
    'Kaitlyn Beltran MD',
    'Kimberly Fuller',
    'Michael Macdonald',
    'Alexander Johns',
    'Amanda Wilson',
],
    'json': {
    'name': 'Michael Carter',
    'address': '570 John Brooks Apt. 982\nEast Robertmouth, CO 05799',
},
    'key14952': 'value51710',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Carol Sellers',
    'address': 'Unit 7665 Box 3429\nDPO AA 64622',
    'text': 'Painting move sort address stay west. Article medical mention.',
    'email': 'jamesmarquez@example.com',
    'phone_number': '(432)765-9624',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Lambert',
    'Anthony Smith',
    'Shannon Vargas',
    'Michelle Gilmore',
    'Suzanne Jones',
],
    'json': {
    'name': 'Ryan Chandler',
    'address': '88830 Erika Haven Apt. 239\nPort Jessica, MN 94124',
},
    'key76743': 'value11649',
    'key82038': 'value1131',
    'key14301': 'value13904',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Kelly Jordan',
    'address': 'USNS Price\nFPO AE 40072',
    'text': 'Feeling during something cover during difficult. Meet really particularly government.\nAddress research five throw shake game during. Leg school who.\nState great civil race. Natural nearly home there.',
    'email': 'stephen18@example.com',
    'phone_number': '535.356.0728x7800',
    'array_int_dynamic': [
    39139,
],
    'array_varchar_dynamic': [
    'Jeffrey Logan',
    'Rebekah Anderson',
    'Eric Thornton',
    'Nicole Lee',
    'Brandon Woods',
    'Vicki Wells',
    'Amy Reynolds',
    'Brian Powell',
],
    'json': {
    'name': 'Stephen Tate',
    'address': '605 Williams Fort Suite 659\nEast Jacquelinechester, MA 88901',
},
    'key85286': 'value43861',
    'key64989': 'value38501',
    'key1768': 'value19134',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Thomas Baker',
    'address': '65958 Kenneth Mountains\nBrittanyburgh, VI 97291',
    'text': 'Music low word same. Citizen worker once commercial realize. Hope ready stop bit anything section real. Especially point seem there.',
    'email': 'peterpowell@example.com',
    'phone_number': '350.836.6529x3553',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Walker',
    'Dan Leonard',
    'Alyssa Ramirez',
    'David Escobar',
    'Brenda Harmon',
    'Alicia Kaufman',
    'Kathryn Haynes',
],
    'json': {
    'name': 'Mr. Thomas Proctor',
    'address': '007 Matthew Square Suite 586\nSouth Melissashire, FM 25159',
},
    'key96697': 'value83830',
    'key81245': 'value28327',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Susan Smith',
    'address': '159 Kaiser Forest Suite 959\nSarahbury, MA 42712',
    'text': 'Event read song instead cold. Night reveal build.\nPiece fly nation maybe. Positive continue war. Conference seven will keep.',
    'email': 'saradurham@example.net',
    'phone_number': '275.672.7393x6852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tara Jones',
],
    'json': {
    'name': 'Douglas Newton',
    'address': 'Unit 0070 Box 9863\nDPO AP 08339',
},
    'key39937': 'value54207',
    'key33839': 'value67879',
    'key27578': 'value2699',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Charles Thompson',
    'address': '504 Greer Crest\nPattersonstad, IL 34398',
    'text': 'Political physical forward crime level.\nReality our whatever same structure. Or better game. Behavior eat allow them theory really perform race. Environment better claim add return heavy prevent PM.',
    'email': 'castilloalex@example.com',
    'phone_number': '7639799236',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Flores',
    'Jennifer Clark',
    'Nicolas Hunt',
    'Cynthia Christensen',
],
    'json': {
    'name': 'Samantha Davies',
    'address': '449 Amy Avenue\nPort Emilyhaven, MO 01902',
},
    'key32046': 'value80142',
    'key18305': 'value17944',
    'key52856': 'value92839',
    'key91533': 'value36443',
    'key66145': 'value69056',
    'key82449': 'value34887',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Tamara Lee',
    'address': '85699 Cook Club Apt. 159\nLopezborough, MI 82146',
    'text': 'Wait face democratic against wrong may article. Century word when leader record. Owner beat if owner article east need.\nStand involve fill even similar dark.',
    'email': 'parkerhector@example.org',
    'phone_number': '(302)675-1084',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Flores',
    'Shannon Lee',
    'Leah Ramirez',
    'Taylor Hernandez',
    'Madison Hernandez',
    'Margaret Becker',
    'Mark Thomas',
    'Jessica White',
    'Brandi Fleming',
    'Theresa Lee',
],
    'json': {
    'name': 'Charles Hernandez',
    'address': 'USCGC Watson\nFPO AP 32222',
},
    'key63822': 'value88996',
    'key51071': 'value49323',
    'key22314': 'value56138',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Blake Edwards',
    'address': '433 Stephanie Court Apt. 535\nRamirezhaven, IL 83979',
    'text': 'Class partner toward after so sound. Everything throw present or or long.',
    'email': 'ashley66@example.com',
    'phone_number': '268.730.6951x796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Joe Rodriguez',
    'Christopher Fletcher',
    'Mark Richardson',
],
    'json': {
    'name': 'Tonya Cruz',
    'address': '95067 Melinda Shoals Apt. 408\nCharlesberg, DE 97993',
},
    'key18444': 'value8658',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Joshua Kirby',
    'address': '01236 Andrew Locks\nNew Josephborough, ND 84139',
    'text': 'Building know stock born join. Research chance system store bring. Across young consumer prevent drug provide. Mr least million test.',
    'email': 'yhurley@example.org',
    'phone_number': '+1-277-593-5669x460',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Jones',
    'Nancy Hartman',
    'Dale Lee',
    'Johnathan Graves',
    'Jason Garner',
    'Tracy Blair',
    'Ann Jenkins',
    'Diana Smith',
    'Kelly James',
    'Clinton Gordon',
],
    'json': {
    'name': 'Amy Green',
    'address': '28620 Nguyen Neck\nNorth Charlestown, NY 73703',
},
    'key24806': 'value34141',
    'key97964': 'value18649',
    'key12507': 'value64546',
    'key50763': 'value28851',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Dale Nelson',
    'address': '2078 Anderson Station Apt. 780\nLake Diane, WI 71958',
    'text': 'Ask goal inside buy sound indeed. Soon indicate listen seven. Factor piece majority whom season brother also.\nGroup main late sometimes how friend. Lay how side imagine win.',
    'email': 'xperez@example.com',
    'phone_number': '001-850-375-0920x52621',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Gina Young',
    'Carlos Willis',
],
    'json': {
    'name': 'Jeffrey Harris',
    'address': '3527 Anna Dam\nPort Brandonmouth, WA 84864',
},
    'key21866': 'value72225',
    'key48319': 'value79556',
    'key7147': 'value65201',
    'key28299': 'value66262',
    'key27185': 'value79980',
    'key21257': 'value31940',
    'key80685': 'value25040',
    'key22413': 'value77903',
    'key78984': 'value25831',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Kevin Jackson',
    'address': '711 Kidd Trail\nNorth Kristin, NM 15746',
    'text': 'Economy bed three often certainly. Manage need real likely check. Increase nor care.\nStop college break or student. About name instead activity again.',
    'email': 'coxlauren@example.com',
    'phone_number': '(420)373-2375x8853',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Hawkins',
    'Hailey Lewis',
    'Leah Mcdonald',
    'Kathleen Martinez',
    'Elaine Wilson',
    'Mitchell Clark',
    'Ashlee Hansen',
    'Michelle Morris',
    'Christine Gray',
],
    'json': {
    'name': 'Pam Cardenas',
    'address': '0239 Lonnie Crest\nStevenmouth, MH 56064',
},
    'key21281': 'value81479',
    'key91561': 'value8876',
    'key81604': 'value47762',
    'key53124': 'value47501',
    'key26684': 'value59335',
    'key1706': 'value43374',
    'key66018': 'value40078',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Heather Johnson',
    'address': '1971 Wilson Dale Suite 363\nAveryshire, IN 77663',
    'text': 'Near investment quite religious before service. Many deep open seat others. Current then level class.\nOver mind system effect conference concern.',
    'email': 'michaelmaxwell@example.com',
    'phone_number': '705.701.0721x725',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Burton',
    'Randy Garrett',
],
    'json': {
    'name': 'Jason Andrews',
    'address': 'PSC 1817, Box 9129\nAPO AE 56012',
},
    'key37858': 'value13337',
    'key55434': 'value92684',
    'key31737': 'value22348',
    'key71104': 'value91613',
    'key18042': 'value70863',
    'key31708': 'value44135',
    'key6342': 'value77273',
    'key66850': 'value25417',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Cynthia Sanders',
    'address': '1908 Robbins Via Suite 862\nJosephmouth, CT 89097',
    'text': 'Economy reveal food low vote weight. Finally create remain sister word.\nCall compare behavior nation rather decade. Option really order responsibility. Line owner one feel idea tax.',
    'email': 'cole82@example.net',
    'phone_number': '(237)466-6969x975',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Walters',
    'Sheryl Martinez',
    'Jessica Smith',
    'Kelly Valdez',
    'Alison Young',
    'Michael Soto',
    'Patricia Thomas',
    'Andrea Johnson',
],
    'json': {
    'name': 'Martha Mann',
    'address': '5068 Bryce Shore Apt. 649\nLopezfort, AK 86592',
},
    'key5484': 'value15921',
    'key71615': 'value78963',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'David Lee',
    'address': '06426 Brandon Trace\nSouth Cindy, TN 82357',
    'text': 'Stand up day official responsibility nor. Research activity situation several with address.\nClass position another partner everybody gun. Kind small something two of. Tax process right behavior.',
    'email': 'hernandezmichael@example.com',
    'phone_number': '+1-300-312-9672x26639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Sims',
    'John Mitchell',
    'Andrew Morgan',
    'Zachary Harris',
    'Holly Brock',
],
    'json': {
    'name': 'Jade Horton',
    'address': '29804 White Shore Apt. 665\nLisatown, PR 85532',
},
    'key98324': 'value15190',
    'key2938': 'value53964',
    'key94267': 'value57775',
    'key45364': 'value75849',
    'key13313': 'value23741',
    'key48492': 'value26914',
    'key62648': 'value58003',
    'key77296': 'value75203',
    'key77106': 'value6726',
    'key27244': 'value57886',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Kaylee Nash',
    'address': '66114 Odonnell Brooks Apt. 664\nWest Jasonville, UT 35009',
    'text': 'Scientist drive Congress treat. Away of fish join blue soldier style.\nPm situation should rather. You science vote artist it performance. Want leg could party successful knowledge issue.',
    'email': 'johnthomas@example.org',
    'phone_number': '8465390838',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Daniel Kline DVM',
],
    'json': {
    'name': 'Albert Farmer',
    'address': '97629 Daniel Trace Suite 427\nJohnstonport, MN 99395',
},
    'key84027': 'value70267',
    'key95156': 'value55939',
    'key46798': 'value33063',
    'key41838': 'value43760',
    'key52261': 'value13487',
    'key83759': 'value60014',
    'key99388': 'value93804',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Luis Bruce',
    'address': '34068 Ricardo Parkway Suite 391\nNorth Molly, CA 48808',
    'text': 'Pass enjoy official company example evidence enter. Behind important whether rise suggest.',
    'email': 'nbrewer@example.org',
    'phone_number': '+1-908-913-5060x75683',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Lambert',
    'Hayley Martinez',
    'Mary Jones',
    'Lauren Roberts',
    'Heather Jackson',
    'Heidi Flowers',
    'Grace Benson',
],
    'json': {
    'name': 'Mary Jacobs',
    'address': 'PSC 6070, Box 2507\nAPO AA 88994',
},
    'key93689': 'value44176',
    'key5117': 'value81094',
    'key51043': 'value46695',
    'key20713': 'value56347',
    'key31696': 'value36357',
    'key56077': 'value44290',
    'key55189': 'value28567',
    'key49463': 'value71963',
    'key81366': 'value88558',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Sydney Cardenas',
    'address': '609 Peter Terrace\nLake Davidmouth, OR 05178',
    'text': 'Message impact writer official middle. Fast third bed others. Various mention pull allow but fact.\nLocal onto father control. Beat training pressure pay cold industry response.',
    'email': 'urivera@example.com',
    'phone_number': '541.647.3183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Young',
    'Heidi Horton',
    'Erin Kim',
    'Tammy Walker',
    'Valerie Cook',
    'Carrie Martinez',
    'Arthur Smith',
    'Cynthia Edwards',
],
    'json': {
    'name': 'Jennifer Lopez',
    'address': '242 Susan Isle Apt. 394\nMaxwellchester, IN 68957',
},
    'key39297': 'value29421',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'William Williams',
    'address': 'USCGC Townsend\nFPO AE 55775',
    'text': 'Dream national music market hospital kid modern. Financial image her own fire then candidate. I thing baby reveal attorney. Impact base end.',
    'email': 'michelle86@example.net',
    'phone_number': '001-827-771-2808x439',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Melinda Contreras',
    'Joseph Jenkins',
    'Nathan Gonzalez',
    'Jorge Chavez',
],
    'json': {
    'name': 'Wendy Smith',
    'address': '4783 Olivia Streets\nHensleyfort, NC 12955',
},
    'key85897': 'value88220',
    'key98961': 'value27464',
    'key18672': 'value13958',
    'key80040': 'value93994',
    'key81773': 'value74561',
    'key77276': 'value7890',
    'key16303': 'value4532',
    'key76167': 'value54285',
    'key6185': 'value82005',
    'key70259': 'value79962',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Katherine Walls',
    'address': '9891 Cole Lodge\nWarechester, PR 45180',
    'text': 'Environmental voice four above tree age. Little out team suffer take what road.\nHeart care teacher today whole choice then. Onto light arrive sister. Letter according or.',
    'email': 'kevinbeck@example.org',
    'phone_number': '961.450.8979x30834',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Dana Thompson',
    'Theresa Brown',
    'Frances Bautista',
    'George Johnston',
    'Janet Ramirez',
    'Kevin Lewis',
    'Jared Schmitt',
    'Alexis Cruz',
],
    'json': {
    'name': 'Gary White',
    'address': '54030 Stephanie Pike Suite 154\nWest Dorisshire, CT 69757',
},
    'key82296': 'value14709',
    'key84335': 'value97169',
    'key46655': 'value86740',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Sophia Burke',
    'address': '85382 Williams Walks\nWest Lisa, NC 88371',
    'text': 'Turn less heart cut. Image explain per fine. Space truth other mother item news this goal.\nExplain stop race generation rather message go. Try she list such care enter employee.',
    'email': 'tflores@example.org',
    'phone_number': '(564)261-9377x405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Howard',
    'Cathy Holland',
],
    'json': {
    'name': 'Katherine Daniel',
    'address': '04200 Jason Wall\nSouth Mariaburgh, PR 18791',
},
    'key70485': 'value61061',
    'key30183': 'value36024',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Michael Patterson',
    'address': '7929 Diana Court\nEast Sallyfurt, OH 62230',
    'text': 'Billion investment everyone direction I. Those with stuff more section hour with. You news exactly land talk technology. More consumer coach choice first anything trial west.',
    'email': 'jamesmontgomery@example.com',
    'phone_number': '001-310-988-5317x0059',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Mcneil',
    'Zachary Jackson',
    'Robert Henry',
    'Nicholas Horton',
    'Scott Bishop',
],
    'json': {
    'name': 'Kenneth Ramirez',
    'address': '413 Wheeler Burg\nEast Eric, FL 27687',
},
    'key50109': 'value11407',
    'key32156': 'value15262',
    'key29966': 'value10033',
    'key26831': 'value39577',
    'key76783': 'value21829',
    'key34904': 'value30188',
    'key95391': 'value89420',
    'key30011': 'value38331',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Danny Williamson',
    'address': '741 Jennifer Station Suite 586\nPort Scott, GA 53750',
    'text': 'Stand believe why draw clear together.\nWhat budget affect interview meet history meet. Environmental whatever occur anything last morning each. Hand station offer enjoy.',
    'email': 'richarddorsey@example.com',
    'phone_number': '832.940.0146',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Adam Dawson',
    'Wesley Jackson',
    'Brandy Brown',
    'Erin Dyer DVM',
    'Brenda Hayes',
    'Matthew Barnes',
    'Jay Gomez',
],
    'json': {
    'name': 'Matthew Baker',
    'address': '01139 David Fort Suite 805\nThompsonstad, FL 32509',
},
    'key67854': 'value41197',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Joshua Gallagher',
    'address': '029 Obrien Ports\nSouth Paul, GU 08202',
    'text': 'Strong student great blood prove. Not sister forget end fear guy act. Truth car church successful keep moment during.',
    'email': 'cassandra59@example.com',
    'phone_number': '732.836.1490x335',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dalton Rivera',
    'Samuel Howard',
    'Christina Salas',
    'Nancy Grimes',
],
    'json': {
    'name': 'Aaron Griffith',
    'address': '9902 Morgan Union Suite 266\nWest Joshuaville, MN 02878',
},
    'key26993': 'value59080',
    'key34503': 'value63800',
    'key57136': 'value76295',
    'key67685': 'value43224',
    'key61579': 'value2847',
    'key16079': 'value91821',
    'key26889': 'value37104',
    'key42457': 'value15362',
    'key99878': 'value33714',
    'key77529': 'value61655',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Logan Davis',
    'address': '87067 Lopez Brooks Apt. 104\nHermanside, KY 81767',
    'text': 'Half again test. Science throughout green available.\nOthers when become month entire. Write thought character road action require kitchen box. Key continue use garden low clear.',
    'email': 'fergusonmatthew@example.com',
    'phone_number': '418-696-1470',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Chad Johnson',
],
    'json': {
    'name': 'Julie Knox',
    'address': 'Unit 2276 Box 1220\nDPO AP 59572',
},
    'key66049': 'value74042',
    'key7161': 'value74262',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Tammy Murphy',
    'address': '94354 Sarah Well\nFergusonfort, CO 60387',
    'text': 'Get actually say note until good. Throughout why indeed seem check position must world.\nPlay chair war executive step still. Cold our for activity start against music remember.',
    'email': 'gregorybarrett@example.net',
    'phone_number': '001-679-604-9369x385',
    'array_int_dynamic': [
    98031,
],
    'array_varchar_dynamic': [
    'Paul Fisher',
    'Shaun Cannon',
    'John Thompson',
    'Andrew Leonard',
    'Christopher Ortiz',
    'Barbara Maldonado',
    'Crystal Miller',
],
    'json': {
    'name': 'Cynthia Alvarez',
    'address': '8179 Prince Rapids Suite 704\nRussellton, VI 22731',
},
    'key13881': 'value60450',
    'key88570': 'value34804',
    'key59356': 'value3554',
    'key3156': 'value21317',
    'key62895': 'value17538',
    'key4198': 'value55564',
    'key46740': 'value18645',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Colin Young',
    'address': '006 Kelly Skyway Apt. 415\nEast Christopher, VT 11771',
    'text': 'Long certainly house exist create friend present. Century also policy particular. Responsibility business guess manage free.',
    'email': 'tranmichelle@example.org',
    'phone_number': '001-435-212-0831',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Christopher Manning Jr.',
    'Peter Garza',
],
    'json': {
    'name': 'Joshua Fisher',
    'address': '157 Fox Street Suite 250\nAdamborough, FL 76389',
},
    'key3272': 'value25668',
    'key74396': 'value14517',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Jessica Neal',
    'address': '26778 Joshua Ports Apt. 961\nNorth Karen, OR 72350',
    'text': 'While Democrat page eye strong. Visit test study TV customer state whatever. Decide catch opportunity but participant ask health.',
    'email': 'justinhart@example.net',
    'phone_number': '4302740139',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Little',
    'Ana Mercado',
    'Michelle Kim',
    'Kimberly Oneill',
    'Deborah Washington',
    'Steve Le',
    'Tina Harding',
    'Megan Reilly',
    'Mark Gibson',
],
    'json': {
    'name': 'Robert Evans',
    'address': '0778 Gutierrez Street\nBenderview, AS 79500',
},
    'key97727': 'value12830',
    'key34435': 'value74730',
    'key6924': 'value4947',
    'key6113': 'value77095',
    'key45036': 'value93554',
    'key87273': 'value71819',
    'key17818': 'value67445',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Christy Herrera',
    'address': '444 Parker Brooks Apt. 078\nSouth Christopherbury, ID 42608',
    'text': 'Whom heart memory method knowledge. Ask movement employee.\nWhile reduce car drug fill yourself. Really summer include compare magazine Mr.',
    'email': 'hedwards@example.net',
    'phone_number': '001-837-695-0251x7989',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dominique Smith',
    'Mrs. Nicole Robbins MD',
    'Cody Romero',
    'Tara Dalton DDS',
    'Alexis Ramirez',
    'Jason Mullins',
    'Katherine Riley',
    'Christopher Jarvis',
    'Karen Jackson',
],
    'json': {
    'name': 'Justin Thompson',
    'address': '991 Jamie Garden Apt. 784\nPort Maryberg, AR 72449',
},
    'key84475': 'value223',
    'key17686': 'value52984',
    'key58241': 'value17032',
    'key82603': 'value79796',
    'key3464': 'value53391',
    'key87227': 'value25268',
    'key62950': 'value64975',
    'key45609': 'value82493',
    'key70277': 'value53203',
    'key64744': 'value99785',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Robin Hawkins',
    'address': '33679 Andrew Mall\nStephanieview, AL 47965',
    'text': 'For because soon understand truth enter. Pay car anyone federal remember perform action. Enough among reach wish stop social again.',
    'email': 'dennismiller@example.org',
    'phone_number': '001-250-802-1892x4781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Oneal',
    'Kimberly Vega DDS',
    'Jason Gonzalez',
    'Derrick Wilson',
    'Kayla Estrada',
],
    'json': {
    'name': 'Dennis Williams',
    'address': '7622 Martha Course\nNew Paigemouth, OR 96141',
},
    'key16176': 'value7171',
    'key39485': 'value11586',
    'key40091': 'value32371',
    'key58789': 'value53924',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Carolyn Johnson',
    'address': '8402 Yolanda Union Suite 988\nSmithburgh, DE 41801',
    'text': 'Way race study. Term natural perhaps land.\nHospital American wish reflect. Assume decade doctor offer.\nCreate from window follow run social authority. House local research image listen.',
    'email': 'isanchez@example.org',
    'phone_number': '001-214-453-3006x525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Raymond Holland',
    'Frederick Mitchell',
    'Deborah Hendricks',
    'Keith Sampson',
    'Karen Gross',
],
    'json': {
    'name': 'Katie Spears',
    'address': '46649 Ann Pines\nJonathanfurt, AR 13231',
},
    'key97407': 'value62935',
    'key97587': 'value24027',
    'key33496': 'value30311',
    'key1798': 'value81898',
    'key3940': 'value42866',
    'key34641': 'value48267',
    'key90342': 'value23108',
    'key10218': 'value83998',
    'key28629': 'value79773',
    'key18652': 'value7365',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Karen Rodriguez',
    'address': '595 Jaime Heights\nLake Patriciaton, AK 62093',
    'text': 'View history father top attention attention care another. Pattern keep hold than. Put product environmental.',
    'email': 'theodoredouglas@example.org',
    'phone_number': '(695)361-8129x824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Wilkinson',
    'Brian Brown',
],
    'json': {
    'name': 'Robin Ortiz',
    'address': '87735 Crystal Junctions Apt. 626\nNorth Johntown, PW 56714',
},
    'key37841': 'value92036',
    'key89551': 'value69721',
    'key59498': 'value30852',
    'key73005': 'value64929',
    'key99738': 'value54098',
    'key97476': 'value4067',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Carla Kim',
    'address': '74171 Linda Circle\nSouth Allisonside, MS 93779',
    'text': 'Town teacher light. Officer take ground day.\nThing why future bank. Candidate quickly letter. Leave general either pressure everything own from.',
    'email': 'pwhite@example.org',
    'phone_number': '936-492-2639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Huber',
    'Daniel Thomas',
    'Annette Johnson',
    'Edward Pollard',
    'David Nguyen',
    'Joel Freeman',
    'Jessica Thomas',
    'Stacey Harris',
    'Brenda Rosario',
],
    'json': {
    'name': 'Tracey Smith',
    'address': '419 Edwards Islands\nRachelfort, GA 80039',
},
    'key25797': 'value12542',
    'key39367': 'value85394',
    'key16048': 'value5476',
    'key44934': 'value59053',
    'key93404': 'value9942',
    'key60931': 'value30243',
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
    'RequestId': '840d03d3-62ef-11f0-b4ed-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_09_063550CNKIlFsX',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-100-2]_1752744130.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId3210021752744130Json()
    test.run_tests()
