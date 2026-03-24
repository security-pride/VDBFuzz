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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-1]_1752744103_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-1]_1752744103.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId3210011752744103Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-1]_1752744103.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-1]_1752744103.json"
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
    'RequestId': '73e24648-62ef-11f0-8d68-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_41_939891UqpjKxwG',
    'dimension': 32,
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
    'RequestId': '7402af58-62ef-11f0-9932-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_41_939891UqpjKxwG',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Roberto Baird',
    'address': '311 Theresa Avenue Apt. 464\nMatthewbury, AS 80077',
    'text': 'Quality individual talk cell win floor sort together. Issue learn either glass hour she. Year hold crime pick into.\nAlone choose left. You direction share field nature. Step school agree activity.',
    'email': 'vhall@example.org',
    'phone_number': '7393825806',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Henry',
    'Sharon Robinson',
    'Christopher Taylor',
    'Jennifer Marshall',
    'Lauren Myers',
    'Jeffrey Costa DDS',
    'Amanda Neal',
    'James Gardner',
    'William Byrd',
    'Thomas Olsen',
],
    'json': {
    'name': 'Rhonda Dixon',
    'address': '63645 Michael Circle\nPort Jennifer, FL 59278',
},
    'key85931': 'value94273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Virginia Young',
    'address': '474 Kathleen Pine\nNorth Joyton, OH 26737',
    'text': 'Political which page number sometimes move. Surface they year.\nHistory civil answer sense attack area night table. Spring individual across Mrs.',
    'email': 'uhartman@example.org',
    'phone_number': '+1-400-704-8032x58670',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Rhodes',
    'Sarah Perez',
],
    'json': {
    'name': 'Mr. Luis Barnett',
    'address': '322 Cameron Ridge Suite 438\nVictoriaview, VT 77382',
},
    'key5606': 'value95259',
    'key4800': 'value68299',
    'key46693': 'value53113',
    'key13469': 'value30731',
    'key91289': 'value73988',
    'key24752': 'value95129',
    'key1230': 'value88286',
    'key57785': 'value80432',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Omar Duke',
    'address': 'Unit 0783 Box 6296\nDPO AA 57248',
    'text': 'Own any author too.\nLook by meet story hand per strategy. Local enjoy agreement forget. Mean blue activity game water must.',
    'email': 'molinajason@example.com',
    'phone_number': '+1-330-676-8467x64328',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christina Moore',
    'Jay Phillips',
    'Michelle Mcmillan',
    'Amy Ramirez',
    'Leslie Davila',
    'Kelly Powell',
    'Todd Wilson',
    'Marco Scott',
    'Stephanie Davis',
    'Adam Sloan',
],
    'json': {
    'name': 'Bradley Friedman',
    'address': '931 Kevin Squares\nGrahamshire, NC 95275',
},
    'key59962': 'value3513',
    'key62661': 'value28946',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'David Burns',
    'address': '844 Joshua Field\nWest Brian, TX 36763',
    'text': 'Single west southern item hear sometimes hair. Learn eat may organization race particular hit. Few involve happy study information identify push image.',
    'email': 'bgolden@example.org',
    'phone_number': '+1-237-219-6125x9309',
    'array_int_dynamic': [
    77483,
],
    'array_varchar_dynamic': [
    'William Sanford',
    'Donna Wilson',
    'Stephen Horn',
],
    'json': {
    'name': 'Jeffrey Jacobs',
    'address': '2157 Marsh Well Suite 227\nNew Audreyberg, PW 28314',
},
    'key66381': 'value98002',
    'key78691': 'value89919',
    'key73088': 'value72463',
    'key57217': 'value35491',
    'key56550': 'value43213',
    'key15271': 'value80469',
    'key14341': 'value4398',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Katie Stewart MD',
    'address': '7032 Washington Gardens\nRogerstad, MI 20018',
    'text': 'Senior room opportunity economy. Own then computer.\nI he car. Themselves institution matter only what.',
    'email': 'fmiller@example.net',
    'phone_number': '414.254.6820x22358',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Brianna Tyler',
    'Tracy Chavez',
    'Michelle Allen',
],
    'json': {
    'name': 'Vickie Porter DDS',
    'address': '162 Mary Locks Suite 329\nLake Dennisfort, NV 89429',
},
    'key81743': 'value36667',
    'key7620': 'value26361',
    'key57113': 'value42531',
    'key94435': 'value90813',
    'key18355': 'value37969',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Luke Patterson',
    'address': '94970 Freeman Divide Suite 613\nWest Erika, NE 87894',
    'text': 'Cold whether relate work concern. Eat TV among eight.\nBall land edge front wish. Feeling avoid memory truth.',
    'email': 'jerry57@example.com',
    'phone_number': '589-616-1600',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amy Booker',
    'Alex Miller',
    'Lisa Morrow',
    'Brittany Brown',
    'Samantha Miller',
    'David Lopez',
    'James Smith',
],
    'json': {
    'name': 'Christian Thomas',
    'address': '8702 Richard Pass\nLake Brianstad, UT 85624',
},
    'key63961': 'value96511',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Adam Webb',
    'address': '57601 Morgan Rapid\nRonaldhaven, RI 67980',
    'text': 'Black blue serious radio job. Easy interview news fall sure. Likely lead your commercial person bar last represent. Campaign toward hotel choose yet.',
    'email': 'baileypaul@example.com',
    'phone_number': '408.688.8922x0721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Dr. John Davis',
    'Wayne Smith',
    'Shannon Brown',
],
    'json': {
    'name': 'Kelly Nelson',
    'address': '9879 Stephanie Rapid\nNorth Tony, NM 39753',
},
    'key94197': 'value5828',
    'key71856': 'value41745',
    'key76558': 'value18237',
    'key50792': 'value48897',
    'key99647': 'value36508',
    'key20116': 'value77725',
    'key12367': 'value50435',
    'key707': 'value50023',
    'key7078': 'value54319',
    'key26081': 'value53294',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Michael George',
    'address': '602 Chris Mountain\nCollinsport, TX 94082',
    'text': 'Last century daughter right pressure artist property. To result single in organization. Science case yet.',
    'email': 'christopher28@example.org',
    'phone_number': '350.949.2032',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Miss Rebecca Andrews MD',
],
    'json': {
    'name': 'Jeffrey Stephens',
    'address': '69456 Daniel Mountain Suite 012\nWhiteview, GA 34060',
},
    'key26988': 'value85049',
    'key16378': 'value91595',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Christopher Matthews',
    'address': '676 Jennifer Garden\nLake Bethfurt, MT 16325',
    'text': 'Career new father article choose per relate. Available sign avoid take. Night alone fly laugh.\nDecide must compare short. Word employee election.',
    'email': 'kimberly86@example.net',
    'phone_number': '724.654.2463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Bartlett',
    'Margaret Marshall',
    'Jenna Robinson',
    'Timothy Williams',
    'Wanda Huang',
    'Cynthia Grant',
],
    'json': {
    'name': 'Thomas Mcgee',
    'address': '6002 Daugherty Street\nSouth Michael, VA 98861',
},
    'key88286': 'value39105',
    'key95149': 'value54676',
    'key98519': 'value36715',
    'key8525': 'value87822',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Sarah Gray',
    'address': '323 King Crest\nShawnfort, KS 11549',
    'text': 'Shoulder mean head peace think then. First detail lay admit source. Staff significant picture.',
    'email': 'blopez@example.org',
    'phone_number': '824-252-5623x35560',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Harris',
    'Christine Hamilton',
    'Jonathan Mack',
    'Michael Murray',
    'Jillian Moon',
    'Christian Perez',
    'Amy Curtis',
    'Teresa Williams',
    'Roy Freeman',
    'Lisa Snyder',
],
    'json': {
    'name': 'James Thomas',
    'address': 'USCGC Rodriguez\nFPO AP 59116',
},
    'key70504': 'value45560',
    'key30563': 'value1298',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Michelle Cook',
    'address': '512 Simmons Club\nRomeroberg, CO 65260',
    'text': 'Community group heart industry view bag. Unit tonight surface always few skin material respond.\nMay my positive very tend participant raise. Senior red no size black many factor.',
    'email': 'andrew31@example.org',
    'phone_number': '417-660-3707x112',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Payne',
    'Sarah Reynolds',
],
    'json': {
    'name': 'Shawn Brooks',
    'address': '346 Raymond Freeway\nHillberg, DC 65607',
},
    'key61440': 'value26348',
    'key4299': 'value600',
    'key53006': 'value5717',
    'key92522': 'value40273',
    'key8828': 'value54362',
    'key26097': 'value66902',
    'key51984': 'value9881',
    'key24220': 'value73530',
    'key38061': 'value38417',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Luke Edwards',
    'address': '683 Mooney Highway Suite 263\nKaylafort, OH 56599',
    'text': 'Drive available majority voice career style. Break cold citizen stage pick source deep.\nMachine site add father. Style concern nation heart.',
    'email': 'harrislisa@example.com',
    'phone_number': '(652)858-9955x509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeremiah Allen',
    'Kyle Hampton',
    'Keith Rollins',
    'Timothy Martinez',
    'Jon Fernandez',
],
    'json': {
    'name': 'Patty Johnson',
    'address': '653 Shannon Haven Suite 279\nSouth Courtneyview, IA 74316',
},
    'key36536': 'value50612',
    'key7262': 'value43878',
    'key96198': 'value40776',
    'key90088': 'value54290',
    'key38719': 'value41163',
    'key16563': 'value62956',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Carrie Hill',
    'address': '17734 Goodwin Lights Apt. 902\nJeremystad, NY 41245',
    'text': 'Level foreign physical choice. Marriage hope sometimes draw various four citizen right.\nAdmit have future drive course gun. Born report hospital along.',
    'email': 'clarkamanda@example.org',
    'phone_number': '637-996-6334x8297',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Mclaughlin',
    'Daniel West',
    'Michael Nguyen',
    'Marcus Roman',
    'Christopher Black',
    'Vickie Watson',
    'William Adams',
    'Amanda Cox',
    'Cynthia Perez',
],
    'json': {
    'name': 'Paula Haynes',
    'address': 'PSC 8612, Box 0853\nAPO AE 74629',
},
    'key47494': 'value42607',
    'key40329': 'value6877',
    'key50415': 'value64566',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'John Higgins',
    'address': '135 Jennifer Groves Suite 872\nAnthonymouth, OR 64884',
    'text': 'Little wish manager. Glass four hit environment ground. Western condition environment head natural spring.\nEast development on. Become respond later range.',
    'email': 'emily87@example.org',
    'phone_number': '+1-653-868-0118x269',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Chelsey Spears',
    'Bobby Rodriguez',
],
    'json': {
    'name': 'Kimberly Young',
    'address': '0971 David Creek\nSaraburgh, AL 83583',
},
    'key19757': 'value76724',
    'key33771': 'value49812',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Dana Alvarez',
    'address': 'USS Rodriguez\nFPO AP 77228',
    'text': 'Newspaper guess chance huge Republican beat. Production door cold anyone read rise.\nDo many society process drop field.',
    'email': 'thebert@example.org',
    'phone_number': '(920)316-1263x5115',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Francisco Mahoney',
    'Robert Ballard',
    'Katie Jones',
    'Melissa Newman',
    'William Duncan',
    'Carlos Russell',
    'Christopher Brown',
    'Christopher Dickson',
    'Teresa Henderson',
],
    'json': {
    'name': 'Kelly Holmes',
    'address': '051 Jennifer Mills Suite 659\nNorth Lisamouth, WA 21023',
},
    'key28262': 'value21522',
    'key35694': 'value58123',
    'key50523': 'value48551',
    'key66011': 'value33820',
    'key35218': 'value8545',
    'key3803': 'value22571',
    'key2997': 'value96911',
    'key61582': 'value35743',
    'key50860': 'value69962',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Jennifer Hill',
    'address': '1772 Savannah Expressway\nAnnaland, MH 72635',
    'text': 'Car thing impact big maybe figure end. Scientist impact usually great hundred.',
    'email': 'fhernandez@example.net',
    'phone_number': '613.331.9814x544',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Bruce Williams',
    'Stephen Ross',
    'Melissa Hansen',
    'Karen Flowers',
    'Sara Smith',
    'Jennifer Mcconnell',
    'Laura James',
    'Christopher Cobb',
    'Christopher Cowan',
],
    'json': {
    'name': 'Kathy Frey',
    'address': 'Unit 0774 Box 6563\nDPO AE 18942',
},
    'key93764': 'value96114',
    'key51392': 'value24304',
    'key7167': 'value27046',
    'key26356': 'value61470',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Roberto Berg',
    'address': '138 Felicia Centers Apt. 384\nNorth Kelsey, OK 11602',
    'text': 'Official still pass. Theory policy million inside management set. Three young whose already environment third.\nFly ten morning send big activity. Democrat recent spring nation score minute few the.',
    'email': 'bauerdawn@example.org',
    'phone_number': '(228)503-5643x970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Dennis',
    'Robert Mendoza',
    'Sarah Frye',
    'Patrick Walker',
    'Sonya Hall',
    'Shaun Massey',
    'Omar Cook',
    'Jay Clarke',
],
    'json': {
    'name': 'Joann Reynolds',
    'address': '1359 Solomon Manor Suite 056\nAnthonyshire, MT 81922',
},
    'key4423': 'value830',
    'key81641': 'value39343',
    'key62465': 'value50032',
    'key577': 'value79371',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Carol Love',
    'address': 'Unit 7718 Box 9014\nDPO AP 87598',
    'text': 'Nation president appear about research per well.\nEffect TV author go represent lead.\nRange line forward likely majority old. Pretty issue respond resource town century.',
    'email': 'christopher98@example.org',
    'phone_number': '468-269-8092x224',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Hayes',
    'Francisco Henderson',
    'Jennifer Lopez',
    'Misty Hall',
    'Justin Collins',
    'Carl Martinez',
    'Jesus Gregory',
    'Krystal Griffin',
    'Steven Carter',
    'William Sharp',
],
    'json': {
    'name': 'Mary Harper',
    'address': '6983 Miller Island\nGomezmouth, MD 65860',
},
    'key50033': 'value4789',
    'key7642': 'value55270',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Cindy Cannon',
    'address': 'PSC 5366, Box 5052\nAPO AA 77884',
    'text': 'Sign sister store compare. Own majority create fish sure stage usually easy. Budget head find child buy show onto.',
    'email': 'ogillespie@example.com',
    'phone_number': '(490)799-8589x34169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Roy Brown',
    'Kenneth Mendoza',
    'Nathan Wolf',
    'Evelyn Mayo',
    'Emily Mooney',
],
    'json': {
    'name': 'James Mooney',
    'address': '2879 Jones Radial Apt. 978\nBenitezview, MH 56804',
},
    'key64921': 'value18082',
    'key17223': 'value33704',
    'key62430': 'value268',
    'key62505': 'value23469',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Trevor Francis',
    'address': '96124 Rhodes Mall\nJonathanton, DC 93018',
    'text': 'Room rest do section. Friend just performance his adult.',
    'email': 'kyliealvarez@example.net',
    'phone_number': '(527)873-3134x8502',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Clark',
],
    'json': {
    'name': 'Michael Marshall',
    'address': '324 Gregory Course\nJustinhaven, NY 94454',
},
    'key90480': 'value25456',
    'key95823': 'value28033',
    'key28703': 'value66306',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Tammy Kaiser',
    'address': '22517 Anna Alley\nNew Patriciaborough, AS 64937',
    'text': 'Treat group practice modern bad treat pick. Interview dream notice social term.\nChair system test but out. See worker consider west. Fall natural notice game.',
    'email': 'alexandria40@example.org',
    'phone_number': '+1-693-214-0748x236',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Robert Torres',
    'Jesse Gardner',
    'Christina White',
],
    'json': {
    'name': 'Jacob Miller',
    'address': '448 Barker Green\nEast Joseph, NE 67334',
},
    'key4369': 'value96173',
    'key50922': 'value89250',
    'key96723': 'value45365',
    'key35377': 'value70847',
    'key30604': 'value87338',
    'key17230': 'value37524',
    'key23416': 'value73119',
    'key75008': 'value1106',
    'key31606': 'value70556',
    'key80557': 'value73416',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Natalie Hicks',
    'address': '73655 Brenda Views\nJohnview, TN 32067',
    'text': 'Suggest contain control special clearly. Bar agree build deal school need. Strategy popular feel instead church.\nTwo fear remember find then later story. Represent TV might so through.',
    'email': 'wyattkathleen@example.org',
    'phone_number': '(795)578-1721x7107',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Briana Carrillo',
    'Ashley Spencer',
],
    'json': {
    'name': 'Vanessa Lopez',
    'address': '6228 Small Shore\nLarsonmouth, GU 10739',
},
    'key92353': 'value52377',
    'key51280': 'value75184',
    'key12904': 'value22554',
    'key38722': 'value84962',
    'key29341': 'value1898',
    'key31886': 'value66046',
    'key80920': 'value22615',
    'key11788': 'value129',
    'key20743': 'value58653',
    'key92689': 'value52388',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Molly Warren',
    'address': '8697 Johnson Squares Apt. 198\nPort Reneeport, OR 26633',
    'text': 'Scientist three skin approach eye. Difference Congress ten everybody instead. Station listen record sign season.\nPersonal add occur. Or heavy fish system.',
    'email': 'gwilliams@example.org',
    'phone_number': '561.721.4699',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Williams',
    'Beverly Austin',
    'Michelle Hughes',
    'David Lamb',
    'Cheryl Bryant',
],
    'json': {
    'name': 'Jennifer Herrera',
    'address': '6693 Atkins Estate\nBakerhaven, AR 39214',
},
    'key70122': 'value65872',
    'key65823': 'value65432',
    'key27653': 'value4657',
    'key60173': 'value63674',
    'key29290': 'value41036',
    'key58755': 'value23234',
    'key74755': 'value62899',
    'key1528': 'value76681',
    'key50715': 'value89122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Monica Shepard',
    'address': '71858 Stanley Locks\nWilliamchester, KS 10398',
    'text': 'Respond deep election simple eye film. Want party if player. His different program consumer section.',
    'email': 'vazquezjacqueline@example.com',
    'phone_number': '(743)589-8875x9474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Kennedy',
    'Sean Powell',
    'Edward Rodriguez',
    'Clayton Stanley',
    'Lisa Lewis',
    'David Fischer',
],
    'json': {
    'name': 'Ronald Gibson',
    'address': 'USS Holt\nFPO AP 54899',
},
    'key44480': 'value49262',
    'key41155': 'value9709',
    'key2971': 'value41015',
    'key32486': 'value69810',
    'key77399': 'value82264',
    'key88943': 'value56320',
    'key2044': 'value20005',
    'key85422': 'value3741',
    'key24364': 'value28913',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Brianna Miller',
    'address': '222 Alyssa Mews\nKristafort, VI 10159',
    'text': 'Friend interesting likely Mr house discover prove myself. Interview cost although voice risk score value.\nSenior million draw Mr as central own. Teacher site item material yeah keep deal.',
    'email': 'wilsontimothy@example.com',
    'phone_number': '+1-721-863-9435x476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Snyder',
    'Patricia Watson',
    'Jennifer Parsons',
    'Susan Rice',
    'Robert Ortiz',
],
    'json': {
    'name': 'Mackenzie Williams',
    'address': '42123 Jason Pass Suite 017\nPaulmouth, ME 42819',
},
    'key62690': 'value5380',
    'key38696': 'value80460',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Angela Moore',
    'address': 'PSC 8529, Box 3681\nAPO AE 12138',
    'text': 'Whom factor fish hospital his father. Away decade million camera fast. Realize fight buy part tend stop.\nParticular necessary democratic its I major season.',
    'email': 'sanchezjared@example.com',
    'phone_number': '+1-236-439-8334x289',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kristin Johnson',
    'Whitney Navarro',
    'Cassandra Young',
    'John Jones',
    'Diana Berger',
    'Daniel Burton',
],
    'json': {
    'name': 'Harry Hahn',
    'address': '926 Flowers Mountains\nHillville, CA 30019',
},
    'key62909': 'value82613',
    'key10048': 'value88238',
    'key85995': 'value31876',
    'key76298': 'value20522',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Cameron Wise',
    'address': '788 Hartman Parkways\nMillerport, DC 36735',
    'text': 'Charge reason wonder. Thought in show truth and deal serious store.\nWeek upon weight behind education throughout ten.\nGreat serious put line there fill language.',
    'email': 'jennifer09@example.com',
    'phone_number': '747-289-5903x0306',
    'array_int_dynamic': [
    37307,
],
    'array_varchar_dynamic': [
    'Angela Ford',
    'Anthony Sanchez',
    'Jeffrey Diaz',
    'Mark Ortiz',
    'Kathleen Bennett',
    'Chase Pierce',
    'Jason York',
    'Corey Conway',
],
    'json': {
    'name': 'Mindy Parker',
    'address': '109 Richmond Freeway\nBriannaton, WV 24177',
},
    'key79933': 'value66432',
    'key14729': 'value63753',
    'key53874': 'value53044',
    'key51026': 'value96405',
    'key86859': 'value87957',
    'key43958': 'value45386',
    'key70857': 'value14766',
    'key29007': 'value7438',
    'key16365': 'value85920',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Christian Cardenas',
    'address': '281 Douglas Orchard Apt. 651\nSherrimouth, MS 17202',
    'text': 'Animal despite each certainly under. Image use stuff head.\nTheory hand southern physical remain science away. Common something road if.',
    'email': 'ddavis@example.com',
    'phone_number': '345.432.3850',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Carol Brown',
    'Richard Smith',
    'Frank Walton',
    'Kelly Nelson',
    'Rhonda Gutierrez',
    'Jonathan Quinn',
    'Nicholas Johnson',
    'Brittney Alexander',
],
    'json': {
    'name': 'William Guzman',
    'address': '35542 John Falls\nWeeksview, ID 45056',
},
    'key21804': 'value56129',
    'key57362': 'value34241',
    'key11945': 'value24783',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Tammy Lopez',
    'address': '216 Sandra Trafficway\nPort Michaelstad, NH 54674',
    'text': 'Want these someone movement police significant. Chance green peace general economy agent sense. Back hope early city read floor.',
    'email': 'pcollins@example.com',
    'phone_number': '(426)800-8819',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Singh',
    'James Silva',
    'Rebecca Williams',
],
    'json': {
    'name': 'Tony Mays',
    'address': 'PSC 7139, Box 9857\nAPO AE 88243',
},
    'key87083': 'value88895',
    'key52159': 'value17714',
    'key31285': 'value32885',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Alvin Ferguson',
    'address': 'Unit 5572 Box 1010\nDPO AA 80173',
    'text': 'Phone begin treatment wonder cut. Really between people suffer. Painting nation certainly into.\nHear strategy full despite might. Strong decision society fish nice cost.',
    'email': 'ashley98@example.org',
    'phone_number': '509-625-9892',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Fletcher',
    'Michael Martinez',
    'Cody Jones',
    'Margaret Blackwell',
    'William Shaw',
    'Megan Scott',
    'Jordan Johns',
    'Thomas Finley',
    'Amanda Sullivan',
],
    'json': {
    'name': 'James Hall',
    'address': '2761 Kimberly Lights Apt. 368\nPatriciaside, ID 19048',
},
    'key10273': 'value73456',
    'key57079': 'value53280',
    'key9165': 'value19332',
    'key26672': 'value66137',
    'key64049': 'value75129',
    'key30463': 'value202',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Carl Guzman',
    'address': '038 Padilla Neck\nCohentown, ID 06766',
    'text': 'Big newspaper most receive official.\nElection industry key out TV. Body prevent party spend.\nExpert like rather who weight. Idea church factor final street hot.',
    'email': 'jacobenglish@example.org',
    'phone_number': '+1-957-570-7045',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Brown',
    'Allison Anderson',
    'Darryl Allen',
    'James Diaz',
    'Jennifer Garza',
],
    'json': {
    'name': 'Jessica Brown',
    'address': '8121 Reynolds Gardens\nNorth Seanville, NE 14052',
},
    'key51444': 'value91653',
    'key13945': 'value23686',
    'key41877': 'value4673',
    'key64324': 'value81220',
    'key1939': 'value30053',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'James Bryant',
    'address': '5673 Rodriguez Station Apt. 659\nTammychester, GA 81922',
    'text': 'Like be require partner. This explain huge.\nMethod among energy call into hope operation. Throw the traditional research story itself. Glass page little increase small live production for.',
    'email': 'justinbaker@example.com',
    'phone_number': '+1-474-448-7041x21443',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura House',
    'Ms. Bianca Olson',
    'Jason Gibbs',
],
    'json': {
    'name': 'Kimberly Mathews',
    'address': '6882 Griffin Villages Suite 310\nLopezshire, PR 34120',
},
    'key93643': 'value57483',
    'key70291': 'value17639',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Sandra Young',
    'address': '9706 Buck Village\nLake Dawn, TN 65950',
    'text': 'May word wind single soldier. Tough remember themselves total she.\nGarden eight growth focus relate but.\nResponse there glass. His college natural. Near southern year rise capital amount population.',
    'email': 'heatherpoole@example.net',
    'phone_number': '001-685-808-1890x52620',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Chase',
    'Kevin Stark',
    'Sharon Arnold',
    'Joshua Salazar',
    'Brittany Rosario',
    'Christian Jackson',
    'Kevin Patton',
    'Brittany Simon',
],
    'json': {
    'name': 'Ashley Hood',
    'address': '85539 Melanie Creek\nWest Michaelview, FL 26522',
},
    'key73092': 'value99743',
    'key93625': 'value34861',
    'key42479': 'value30534',
    'key40881': 'value31473',
    'key58772': 'value83201',
    'key12076': 'value10522',
    'key53631': 'value74194',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Gregory Peterson',
    'address': '03360 Ricardo Rest\nPort Cynthiahaven, VA 27858',
    'text': 'Either green of account. Whatever employee science brother begin hour happen card. Rate matter stay you.',
    'email': 'ujimenez@example.net',
    'phone_number': '001-307-537-6840',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Sandoval',
    'Christine Mendoza',
    'Ashley Carroll',
    'Charles Ibarra DDS',
    'Rachel Lopez',
],
    'json': {
    'name': 'Amy Jordan',
    'address': '6717 Patricia Path\nNew Daisystad, NJ 69764',
},
    'key51597': 'value95560',
    'key56033': 'value88605',
    'key77312': 'value74944',
    'key27663': 'value38591',
    'key76107': 'value41585',
    'key69693': 'value85062',
    'key29477': 'value53147',
    'key25666': 'value65146',
    'key93546': 'value58182',
    'key97939': 'value65450',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Nicole Romero',
    'address': '833 Davis Loop Suite 362\nNorth Amandamouth, DE 11207',
    'text': 'Whatever inside try support card. Economic stage run seat.\nOne study offer real turn as certain season. First left fast anyone federal and. Dream grow choose language each.',
    'email': 'johnsonbradley@example.net',
    'phone_number': '(766)442-6726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amber Guzman',
    'Rhonda Perry',
    'Brianna Lucas',
],
    'json': {
    'name': 'Kara Flores',
    'address': '209 Burke Loaf\nBrendaberg, IN 60593',
},
    'key4052': 'value64514',
    'key1499': 'value14896',
    'key52739': 'value9592',
    'key34090': 'value19394',
    'key7804': 'value27526',
    'key6345': 'value14024',
    'key94701': 'value54159',
    'key68336': 'value24673',
    'key53374': 'value35155',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Mr. Jon Mcgrath',
    'address': '420 Tyler Inlet Suite 007\nSouth Robert, ID 54200',
    'text': 'Medical finish reveal culture. Clear carry physical official success somebody hundred.',
    'email': 'jessicamcintyre@example.org',
    'phone_number': '(741)364-0226',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Amanda Cameron',
    'Richard Hill',
],
    'json': {
    'name': 'Brooke Oliver',
    'address': '76250 Marie Summit Apt. 517\nNew Ryan, IN 42830',
},
    'key79964': 'value77856',
    'key35175': 'value50317',
    'key47023': 'value77162',
    'key94615': 'value70895',
    'key53426': 'value96175',
    'key97407': 'value7640',
    'key60778': 'value75234',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Michael Thomas',
    'address': '761 Fox Plains Suite 107\nStevenbury, IL 50822',
    'text': 'Cause east around force. Pull central carry health.\nCompare six fly some detail follow amount. Brother among look goal best film.',
    'email': 'robertnewman@example.net',
    'phone_number': '2357988510',
    'array_int_dynamic': [
    47989,
],
    'array_varchar_dynamic': [
    'Angel West',
    'Elizabeth Perez',
],
    'json': {
    'name': 'Amy Thompson',
    'address': '8996 Shaw Ferry\nSouth Emmaville, MP 87872',
},
    'key23017': 'value1183',
    'key12587': 'value22850',
    'key58278': 'value37349',
    'key61579': 'value28842',
    'key42923': 'value23740',
    'key71899': 'value5734',
    'key78667': 'value77623',
    'key95639': 'value19326',
    'key15000': 'value25659',
    'key39734': 'value91856',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Brian Hogan',
    'address': '31967 Mcdowell Courts Apt. 227\nLake William, NY 27264',
    'text': 'Character gas fire member. Response culture appear lawyer affect want for. Town program baby address range town. Area answer suffer.',
    'email': 'lwells@example.org',
    'phone_number': '001-719-577-1834x06253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Larry Jackson',
    'Lynn Davis',
],
    'json': {
    'name': 'Andrew Ball',
    'address': 'USNV Moore\nFPO AP 88857',
},
    'key64621': 'value93312',
    'key5493': 'value92995',
    'key52760': 'value96777',
    'key31755': 'value5822',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Grant Black',
    'address': '240 Lisa Light\nJoshuaborough, HI 01263',
    'text': 'Statement rate room maintain catch site stand. Even look write someone. Want left since before.\nRadio air this exist firm listen magazine. Power choose story hard theory seek claim adult.',
    'email': 'james88@example.net',
    'phone_number': '001-328-354-5609x09223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joel Miller',
    'Crystal Hurley',
    'Diane Mccann',
    'Charles Brewer',
    'Felicia Randall',
    'Julia Wallace',
    'Brian Rogers',
    'Brenda Hill',
    'Christina Smith',
],
    'json': {
    'name': 'Douglas Carpenter',
    'address': '3714 Reeves Parkways Suite 717\nNorth Tiffanyburgh, PW 18978',
},
    'key68010': 'value54909',
    'key88703': 'value79358',
    'key51919': 'value22028',
    'key14138': 'value75731',
    'key2076': 'value530',
    'key94257': 'value97121',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Tracey Whitney',
    'address': '40245 Taylor Bridge\nEast Jamesside, MN 62044',
    'text': 'Shoulder part glass ball rest forget. Idea never scene paper air. Discover behavior majority let recently.\nShake line simply. Network politics onto might and degree.',
    'email': 'cmccullough@example.org',
    'phone_number': '757.661.0369x776',
    'array_int_dynamic': [
    7780,
],
    'array_varchar_dynamic': [
    'Kevin Young',
    'Thomas Blair',
    'Megan Jones',
    'Dawn Fox',
    'Jennifer Robinson',
    'Katie Griffin',
],
    'json': {
    'name': 'Thomas Owens',
    'address': '151 Christopher Crescent\nThomasview, WA 58197',
},
    'key20087': 'value92747',
    'key16162': 'value56097',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Mary Gomez',
    'address': '8085 Jennings Extensions\nEricfurt, NJ 41786',
    'text': 'Trip to blue. Wrong kid gas social. Want measure glass identify.\nHappen truth real. Other Democrat operation morning. Raise specific skill thank.\nAgain skill mind. Poor operation customer physical.',
    'email': 'joshua50@example.com',
    'phone_number': '5952260161',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Gonzales',
    'Heather Cox',
    'Michael Smith',
    'Chris Morgan',
    'Rebecca Mckee',
],
    'json': {
    'name': 'Gabriel Lee',
    'address': '4911 Poole Hill\nNorth Renee, CT 19536',
},
    'key50122': 'value88742',
    'key70743': 'value45112',
    'key96859': 'value34517',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Jennifer Watts',
    'address': '442 Cole Flat\nStoneberg, FM 27991',
    'text': 'Reveal alone gas. Manage every statement show anyone.\nThere computer difference leader knowledge candidate pick.\nDemocrat fire almost out road forget cause.',
    'email': 'emily66@example.com',
    'phone_number': '954-429-3222x81757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Nelson',
    'Joshua Andersen',
    'James Sanders',
    'Laura Garcia',
    'James Collins',
    'Lee Johnson',
    'Tammy Nguyen',
    'Larry Nelson',
],
    'json': {
    'name': 'Melissa Barnes',
    'address': '153 Randall Fords Suite 599\nNorth Allisonborough, AS 18821',
},
    'key57397': 'value32721',
    'key80594': 'value99608',
    'key35197': 'value31023',
    'key45762': 'value42797',
    'key23495': 'value59435',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Jamie Stanley',
    'address': '904 Julie Crest\nLake Lance, IA 70687',
    'text': 'Fly make former medical floor particularly. Recently great option artist.\nCover pattern far later her. Interview leave child break. Interesting right rate throw.',
    'email': 'sarahwarner@example.com',
    'phone_number': '+1-470-329-4944x4222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Lucero',
    'Maria Romero',
    'Darlene Andrews',
    'Christopher Smith',
    'Denise Roman',
    'Andrea Barajas',
],
    'json': {
    'name': 'Debbie Smith',
    'address': 'USNV Barry\nFPO AE 46483',
},
    'key72391': 'value20761',
    'key78333': 'value8957',
    'key45330': 'value84456',
    'key57645': 'value75101',
    'key31735': 'value30836',
    'key4042': 'value47805',
    'key15928': 'value65260',
    'key12469': 'value72472',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Maria Torres',
    'address': '01229 Brandon Ville Suite 257\nLake Jacob, CT 04458',
    'text': 'Picture practice service. End certain draw recognize pattern year.\nYeah must open then before animal maybe this. Learn full imagine force wish ahead employee.',
    'email': 'kporter@example.org',
    'phone_number': '(843)886-8425x486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Williams',
    'Luke Long',
    'Joseph Jenkins',
    'Kevin Smith',
    'Jason Guerra',
    'Elizabeth Williams',
    'Jason Wright',
    'Joseph Jones MD',
],
    'json': {
    'name': 'Fernando Jones',
    'address': '404 Jennifer Pine\nNorth Nicholastown, VT 19239',
},
    'key92957': 'value91637',
    'key25341': 'value97852',
    'key5885': 'value63040',
    'key33874': 'value36304',
    'key25536': 'value88679',
    'key34883': 'value79432',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Antonio Porter',
    'address': '9268 Barnes Trail Apt. 946\nPort Danny, NM 39629',
    'text': 'Summer bar ask purpose. Color or our worry back front past.\nEvening wear feeling establish old end. Marriage close determine line art wind budget.',
    'email': 'mstevenson@example.org',
    'phone_number': '001-532-716-4380x39471',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amber Shelton',
    'David Beck',
    'Tammy Sanchez',
    'Ryan Valencia',
    'Kelly Keller',
    'Marcus Smith',
],
    'json': {
    'name': 'Keith Rodriguez',
    'address': '756 Browning Extension Apt. 533\nPort Kimberly, DE 53717',
},
    'key24435': 'value31977',
    'key52035': 'value49487',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'David Fernandez',
    'address': '354 Matthew Causeway Apt. 062\nHeidiburgh, NH 56815',
    'text': 'Write lot view put free herself.\nStay it region test option woman. Any similar follow tax discuss.\nCandidate available voice paper. Cultural finish million wall. National light artist other.',
    'email': 'acardenas@example.com',
    'phone_number': '001-591-558-6389x58918',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joe Hanna',
    'Kimberly Warren',
    'Beth Robertson',
    'Steven Wilson',
],
    'json': {
    'name': 'Theresa Evans MD',
    'address': 'PSC 0256, Box 2246\nAPO AE 63776',
},
    'key72569': 'value589',
    'key97563': 'value34708',
    'key59326': 'value14290',
    'key2180': 'value78660',
    'key33215': 'value87046',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Michael Gonzalez',
    'address': '29548 Delacruz Course\nJasonfurt, VI 32329',
    'text': 'Per school budget argue condition inside. Five important quite religious response career number its.\nResearch establish those country price. Clear continue consumer plant.',
    'email': 'taylorkristin@example.net',
    'phone_number': '001-613-341-8919x7719',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Heather Coffey',
    'Julie Galloway',
    'Christopher Williamson',
    'Nathan Crawford',
    'Jessica Stein',
    'Adrian Clark',
    'Emily English DVM',
],
    'json': {
    'name': 'Stacy Johnson',
    'address': '5607 Devin Port\nGeorgeshire, LA 32689',
},
    'key65974': 'value83304',
    'key33815': 'value49554',
    'key87835': 'value75892',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Brittney Rodriguez',
    'address': '2956 John Centers\nFigueroachester, SC 67349',
    'text': 'Mrs factor after political magazine. Around moment plan one often look skill.\nFine you health meeting dream. Say yes vote deal PM future.\nSong step check. Point third shake hospital.',
    'email': 'michelle83@example.com',
    'phone_number': '3422056596',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lindsay Lee',
    'Richard Moore',
    'Jessica Charles',
    'Matthew Sweeney',
    'Allison Crane',
    'Robert Barton',
    'Brent Maldonado',
    'Deborah Fields',
    'Brian Johnson',
    'Thomas Rodriguez',
],
    'json': {
    'name': 'Ruth Smith',
    'address': '7218 Zachary Hollow Suite 855\nJosephfurt, KY 80002',
},
    'key51387': 'value95719',
    'key54639': 'value96226',
    'key50983': 'value77342',
    'key76923': 'value49367',
    'key46992': 'value85835',
    'key47440': 'value57687',
    'key24953': 'value15791',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Kayla Hayden',
    'address': '5528 Lorraine Harbors Apt. 066\nBatesfurt, PW 98932',
    'text': 'True west grow hour cover meet look. Fish deal half item cell under region especially. Dream stock become street. Culture how yourself simple treatment worry style.',
    'email': 'monicaruiz@example.org',
    'phone_number': '001-709-311-8518x883',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Jones',
],
    'json': {
    'name': 'Daniel Anderson',
    'address': '600 Elizabeth Prairie\nWest Philip, PR 55550',
},
    'key34173': 'value16746',
    'key64831': 'value38485',
    'key96055': 'value78064',
    'key34396': 'value25294',
    'key5906': 'value64210',
    'key60633': 'value49035',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Amber Mclaughlin',
    'address': '55638 Theresa Stream Suite 463\nBrendatown, AL 50485',
    'text': 'Movement herself or set central just raise former. West industry model program morning evening successful friend. Benefit quickly discover once.\nMust back teach. Also religious police three.',
    'email': 'carloshall@example.net',
    'phone_number': '557-211-2244x04205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Moses',
    'Peter Parks',
    'Scott Turner',
    'Jordan Elliott',
],
    'json': {
    'name': 'Tina Foster',
    'address': '50246 Michael Fields Suite 116\nRosschester, ME 15328',
},
    'key52958': 'value56805',
    'key55899': 'value96426',
    'key11457': 'value43979',
    'key29266': 'value33814',
    'key80609': 'value58753',
    'key99738': 'value539',
    'key610': 'value32820',
    'key96580': 'value12936',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Mark Duncan',
    'address': '6206 Paula Route\nNorth Brianbury, MT 99692',
    'text': 'Various rate dark now. Heart including little film. Anything baby newspaper natural ok.\nAlong three area. Project approach may maybe table.',
    'email': 'bwillis@example.org',
    'phone_number': '939-853-9981',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Jones',
    'Destiny Smith',
    'Barry Mullins',
    'Sarah Schultz',
    'Christopher Khan',
    'Justin Johnson',
    'Olivia Meyer',
    'Julie Stephens',
    'Judy Knapp',
    'Courtney Molina',
],
    'json': {
    'name': 'Mary Miller',
    'address': 'Unit 3660 Box 2495\nDPO AE 05445',
},
    'key72431': 'value99728',
    'key79940': 'value75873',
    'key29923': 'value51432',
    'key19475': 'value40781',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Adrienne Moore',
    'address': '7054 Rush Way\nNorth Jon, MD 41295',
    'text': 'Fight attorney receive represent hard center production fill. Total opportunity news seem land.\nJob test single own fight near. Street tend throughout star. Well whole though property rather.',
    'email': 'melissamoore@example.org',
    'phone_number': '+1-203-785-8310x61704',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Clark',
],
    'json': {
    'name': 'Patrick Foster',
    'address': '3467 Wendy Junctions Apt. 326\nGarrettberg, FM 41232',
},
    'key44727': 'value22602',
    'key7458': 'value69891',
    'key97381': 'value53915',
    'key71626': 'value95071',
    'key41733': 'value59175',
    'key81860': 'value11008',
    'key79179': 'value26322',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Julie Hall',
    'address': '488 Summers Island\nMorganview, MP 41826',
    'text': 'Discussion happy from see air actually upon. Teacher always author mention Mr go. Clear inside thank. City available evening future moment realize parent seven.',
    'email': 'rushmichael@example.net',
    'phone_number': '(220)403-0947x9086',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Stephens',
    'Laura Vega',
    'Antonio Cannon',
    'Benjamin Williams',
    'David Soto',
    'Shelby Love',
    'Marc Molina',
],
    'json': {
    'name': 'Patrick Peterson',
    'address': '713 Thompson Passage\nNew Jason, VT 88551',
},
    'key50348': 'value71808',
    'key81138': 'value68486',
    'key15545': 'value96170',
    'key44182': 'value67674',
    'key38446': 'value68010',
    'key4678': 'value94956',
    'key13867': 'value61188',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Tracy Dunn',
    'address': '4598 Kelly Brook\nNew Monica, MN 33802',
    'text': 'Soon person win agree recent perhaps. Per leg out use within there end. Although often bank remain see situation.',
    'email': 'matthew97@example.net',
    'phone_number': '(959)775-8600x1222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Debra Lucero',
    'Melissa Perez',
    'Peter Moyer',
    'Brandon King',
    'Melanie Wilson',
    'Timothy Fuller',
    'Erin Duncan',
    'Robert Yu',
    'Mark Gomez',
],
    'json': {
    'name': 'Mark Khan',
    'address': '4026 Valentine Overpass Apt. 325\nNew Lisaport, OH 06917',
},
    'key35719': 'value4434',
    'key98660': 'value37080',
    'key77016': 'value42354',
    'key63946': 'value5588',
    'key54468': 'value78523',
    'key8145': 'value10389',
    'key4090': 'value97813',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Vanessa Vargas',
    'address': 'PSC 5442, Box 8480\nAPO AA 75013',
    'text': 'Event develop between between chair ever meeting last. Law wait relate suggest game meeting firm.',
    'email': 'lindsaylee@example.org',
    'phone_number': '572.534.9910x0964',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Hawkins',
    'Gregory Aguilar',
    'Courtney Duran',
    'Lisa Smith',
    'Rebecca Garcia',
    'April Moss',
    'Sarah Kelley',
],
    'json': {
    'name': 'Dominique Simpson',
    'address': '949 Rebecca Gardens Apt. 681\nLake Shelby, NC 61859',
},
    'key85394': 'value88997',
    'key53068': 'value97246',
    'key16017': 'value38754',
    'key57723': 'value59211',
    'key55058': 'value62395',
    'key74438': 'value32352',
    'key57215': 'value53762',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'David Rodriguez',
    'address': '784 Potter Union\nLake Julie, NC 48567',
    'text': 'Candidate expect coach development plant. Bar book such garden write just war.\nDebate suggest tend herself such per. While better special realize.',
    'email': 'thomas98@example.com',
    'phone_number': '(914)903-1314x6150',
    'array_int_dynamic': [
    94430,
],
    'array_varchar_dynamic': [
    'Randall Phillips',
    'Beverly Williams',
    'Donald Chapman',
    'Savannah Thornton',
    'Jasmine Wood',
    'Joseph Kelley',
    'Jason Merritt',
],
    'json': {
    'name': 'Brenda Lee',
    'address': '7530 Matthews Spur\nNew Juliestad, OR 74341',
},
    'key45860': 'value18353',
    'key20870': 'value18251',
    'key74747': 'value1849',
    'key4968': 'value94995',
    'key81649': 'value16898',
    'key29314': 'value86979',
    'key8864': 'value84204',
    'key51537': 'value79067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Mark Hill',
    'address': '98349 Ramirez Hollow\nCatherineshire, PR 67618',
    'text': 'Trade red drive seek him coach. Relationship strong Republican include.',
    'email': 'jesusbaker@example.com',
    'phone_number': '(533)593-5566x936',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Becker',
    'Amanda Phillips',
    'Scott Lowe',
    'Jason Diaz',
    'Patrick Ramirez',
    'Terri Carter',
    'Wendy Lopez',
    'Douglas Holt',
],
    'json': {
    'name': 'Sara Montgomery',
    'address': '375 Moran Mission Suite 435\nDarlenebury, WA 65025',
},
    'key217': 'value71046',
    'key26129': 'value50171',
    'key43134': 'value97700',
    'key31122': 'value76422',
    'key33341': 'value36020',
    'key51547': 'value99060',
    'key72254': 'value29085',
    'key17723': 'value98959',
    'key95309': 'value97713',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Scott Strickland',
    'address': '856 Alexander Row\nNew Devin, DE 08811',
    'text': 'Know environment newspaper sister letter international. Success might number executive key rather meeting president. Thought only start wish maintain.',
    'email': 'david45@example.org',
    'phone_number': '+1-984-342-4585',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Ross',
],
    'json': {
    'name': 'Sonya Ray',
    'address': '0543 Rachel Summit\nPort Anthony, GU 08714',
},
    'key84289': 'value75391',
    'key74850': 'value63951',
    'key56592': 'value38534',
    'key74551': 'value49566',
    'key58920': 'value64763',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Robert Adams',
    'address': '529 Suzanne Corner\nNormanmouth, NJ 68178',
    'text': 'Quite affect state entire board. Federal security world side budget PM.',
    'email': 'yfranklin@example.com',
    'phone_number': '+1-410-587-0566x106',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Santiago',
    'Steve Jones',
    'Shannon Weaver',
],
    'json': {
    'name': 'Megan Johnson',
    'address': '1257 Villa Stravenue\nMartinezview, NE 46261',
},
    'key69146': 'value78144',
    'key66382': 'value41934',
    'key91782': 'value13262',
    'key79371': 'value28428',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Cindy Dawson',
    'address': '0256 Reed Tunnel\nLake Nicholas, GU 40410',
    'text': 'East still room decide wind consider gun. Century itself firm reduce. Front hour involve just new should.\nSignificant hand Mrs plant. Fast economic culture director.',
    'email': 'sjohnson@example.net',
    'phone_number': '(861)381-5002',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stacy Diaz',
    'Christopher Snyder',
],
    'json': {
    'name': 'Gary Francis',
    'address': '5696 Mclean Land\nHollowaymouth, CO 90501',
},
    'key3606': 'value8089',
    'key68730': 'value65985',
    'key8322': 'value25673',
    'key62401': 'value40790',
    'key28985': 'value87493',
    'key97001': 'value63249',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Katie Lindsey',
    'address': '9657 Steven Isle Apt. 140\nNew Michaelaburgh, MA 88260',
    'text': 'Charge character also mention notice. Military lose he material how.\nBorn international girl bit arrive. Community meeting arm. Million and teacher upon you become there.',
    'email': 'jacksonnicholas@example.org',
    'phone_number': '248-711-6190x68745',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Denise Kelly',
    'Zachary Gregory Jr.',
],
    'json': {
    'name': 'Monica Brown',
    'address': '15345 Tanner Trail\nMichaelhaven, TX 06760',
},
    'key56342': 'value97586',
    'key21797': 'value53395',
    'key32939': 'value50890',
    'key14151': 'value40210',
    'key12302': 'value84600',
    'key3827': 'value16230',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Candice Clark',
    'address': '2927 Oliver Divide\nPort Raymond, MT 61104',
    'text': 'Receive science method watch doctor significant often. Human put often right difference.\nSell nation work rise not goal. Smile Democrat consumer ok wife camera.',
    'email': 'dillon14@example.com',
    'phone_number': '+1-760-731-5142x926',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Jimenez',
    'Brittany Daniel',
    'Blake Brown',
    'Peter Moody',
],
    'json': {
    'name': 'Edward Stevens',
    'address': '694 Massey Valley Suite 119\nEast Michael, GA 32800',
},
    'key99184': 'value32980',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Joshua Lopez',
    'address': '04112 Kathryn Track\nWest Larryshire, DE 07045',
    'text': 'Despite pressure guess boy similar product. Daughter decision director instead bill.\nBoy agreement international focus he bank. Local back tax surface watch.',
    'email': 'uhuerta@example.org',
    'phone_number': '001-818-690-1276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Gray',
    'Paul White',
    'Andrea Carlson',
    'Helen David',
    'Mary Ruiz',
    'Dawn Stewart',
    'Stephanie Estrada',
    'Brenda Duncan',
    'Samantha Cook',
],
    'json': {
    'name': 'Monica Brown',
    'address': '137 Barnes Trail Apt. 743\nNew Johnburgh, VI 94583',
},
    'key22359': 'value42555',
    'key77666': 'value43690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Edwin Cain',
    'address': '9547 Jackson Stravenue Suite 164\nCourtneyfort, MS 09079',
    'text': 'Hotel person rule thank staff. Four represent our continue green nearly require.\nPerformance laugh actually with north well ago laugh. Establish charge help though coach policy everyone.',
    'email': 'watkinsveronica@example.org',
    'phone_number': '5697889009',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Rodriguez',
    'Kristen Fry',
    'Corey Alvarez',
    'Tina Moran',
    'John Flores',
    'Mary Hart',
    'Lori Coleman',
],
    'json': {
    'name': 'Michele George',
    'address': '50960 Rachael Ports\nDavidside, MP 31817',
},
    'key97548': 'value99160',
    'key27105': 'value50453',
    'key90951': 'value35094',
    'key59524': 'value37820',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Elizabeth Allen',
    'address': '63862 Nathaniel Trace\nMarystad, TX 94654',
    'text': 'Food long check performance Republican. Both organization onto hope policy.\nWhile who woman agreement report wait. Read a give change always around by.',
    'email': 'faulknerrodney@example.net',
    'phone_number': '229-958-7393',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'William Smith',
    'Ashlee White',
    'Kevin Kennedy',
],
    'json': {
    'name': 'Melissa Butler',
    'address': '555 Alexander Harbor\nCarrilloton, NE 57855',
},
    'key8655': 'value22899',
    'key16642': 'value31961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Ms. Shannon Zavala DDS',
    'address': 'PSC 2475, Box 4067\nAPO AA 27852',
    'text': 'Foreign majority similar different finally. Generation more until skill. Best picture reflect town reach public throughout.\nFast yes large leg. Garden deep at physical catch avoid morning.',
    'email': 'jamesanderson@example.net',
    'phone_number': '739-255-6063x1058',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Davis',
    'Dennis Mills',
],
    'json': {
    'name': 'Lori Robinson',
    'address': '99203 Middleton Divide\nTannermouth, MT 05266',
},
    'key44138': 'value33537',
    'key68215': 'value44970',
    'key55197': 'value43722',
    'key3666': 'value8009',
    'key69290': 'value40326',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Erin Zuniga',
    'address': '1964 Estes Hill\nLake Caleb, MT 99946',
    'text': 'Method window campaign. Pretty style catch responsibility such father property someone.\nPick away travel effort. Soldier himself every majority serve national. Country message want listen.',
    'email': 'molly38@example.com',
    'phone_number': '483-453-0367',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Key',
    'Eric Lopez MD',
    'Lucas Turner',
    'John Gilmore',
    'John Harmon',
    'Rachael Flowers',
],
    'json': {
    'name': 'Erica Glenn',
    'address': '082 Molina Mount\nDeniseborough, MS 18695',
},
    'key18859': 'value50179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Charles Miller',
    'address': '6544 Suzanne Springs\nBrandonside, TN 73413',
    'text': 'Chance mother red example though. Professional key they growth international. Body art huge tree together in how.\nFactor themselves force good. Trouble large rate close should sport.',
    'email': 'xferguson@example.org',
    'phone_number': '001-239-918-9676x168',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Eric Collins',
    'Dana Jenkins',
    'Jerome Fowler',
    'Victoria Collins',
    'Erin Schultz',
    'Edgar Olson',
],
    'json': {
    'name': 'Cynthia Myers',
    'address': '7350 Alexa Corners\nSouth Allenhaven, CT 18040',
},
    'key91071': 'value69717',
    'key85502': 'value34512',
    'key93099': 'value63947',
    'key27147': 'value3049',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Daniel Stone',
    'address': '6331 Brandon Ports Apt. 881\nRobinsonside, AS 99196',
    'text': 'Middle agree deal mother discussion usually.\nStyle skill since young will card over. Then friend worker compare. Response letter hope heavy fast number employee.',
    'email': 'simmonscharles@example.org',
    'phone_number': '+1-263-349-0421',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Jordan',
    'Mr. Calvin Evans',
    'Brenda Baker',
    'Victoria Foster',
],
    'json': {
    'name': 'Kayla Smith DDS',
    'address': 'Unit 9458 Box 7929\nDPO AE 41469',
},
    'key91546': 'value20625',
    'key99173': 'value28763',
    'key46895': 'value48324',
    'key76025': 'value41395',
    'key30286': 'value85904',
    'key34681': 'value49655',
    'key28014': 'value9545',
    'key62323': 'value69301',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Caitlyn Cook',
    'address': '8587 Christina Courts\nGonzalezchester, KS 73233',
    'text': 'Guess watch newspaper statement. Important when role idea.\nCollege walk whole college together maybe. Message including blue conference road character professional.',
    'email': 'callahanelizabeth@example.com',
    'phone_number': '582.370.4569x165',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Ball PhD',
    'Alexander Wilson',
    'Austin Castillo',
    'Emily Guerrero',
    'Rebecca Marshall',
    'Shannon Graham',
    'Michael Clark',
    'Stacy Meyer',
    'Devin Ortega',
    'Selena Potts',
],
    'json': {
    'name': 'Carmen Morgan',
    'address': '7691 Anne Inlet\nWest Johnshire, GA 47672',
},
    'key31795': 'value58348',
    'key95668': 'value198',
    'key51864': 'value25501',
    'key49483': 'value22609',
    'key91488': 'value11525',
    'key4581': 'value25095',
    'key93046': 'value37240',
    'key74160': 'value26791',
    'key17505': 'value97040',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'James Huber',
    'address': '224 Guzman Mountains Suite 448\nSouth Candace, NE 05844',
    'text': 'Hope human him in pressure read.\nTravel sure team suggest while. Agreement interesting soldier happy whose most. Kid sing determine seem dinner prove. Plan accept against use back such.',
    'email': 'carolrivera@example.net',
    'phone_number': '+1-468-450-0438x1771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mary Murray',
],
    'json': {
    'name': 'Janet Smith',
    'address': '171 Jason Inlet Apt. 737\nPort Brittany, CA 27926',
},
    'key99598': 'value18244',
    'key63943': 'value20582',
    'key10966': 'value82399',
    'key34383': 'value81049',
    'key96644': 'value70728',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Donald Torres',
    'address': '448 Rivers Coves Suite 257\nNorth Jeffreyshire, MN 38793',
    'text': 'Amount water people picture country last include budget. Campaign onto big Democrat sit view they mother. Imagine agent always onto environment.',
    'email': 'spearskayla@example.com',
    'phone_number': '510.754.9034',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Brown',
],
    'json': {
    'name': 'Joshua Flowers',
    'address': '7339 Timothy Island Apt. 732\nLittlefort, IN 01828',
},
    'key55568': 'value18884',
    'key13462': 'value92216',
    'key473': 'value83616',
    'key12026': 'value26961',
    'key57822': 'value1529',
    'key90479': 'value12277',
    'key3175': 'value32291',
    'key30901': 'value7824',
    'key48579': 'value96600',
    'key51906': 'value8446',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Michael Duke',
    'address': '824 Ashley Glens Apt. 856\nWest Brendaburgh, NM 00795',
    'text': 'Impact hope under reality. Development account building shake political religious. White grow toward candidate.',
    'email': 'wking@example.org',
    'phone_number': '567.661.4660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Adams',
    'Claudia Parks',
    'David Arnold',
],
    'json': {
    'name': 'Dr. Mark Harris',
    'address': 'Unit 9621 Box 9532\nDPO AP 73846',
},
    'key69391': 'value12967',
    'key27233': 'value56413',
    'key57665': 'value40493',
    'key86043': 'value71976',
    'key56819': 'value3826',
    'key25126': 'value59560',
    'key72282': 'value39368',
    'key31695': 'value82408',
    'key49559': 'value58373',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Vincent Edwards',
    'address': '16680 Maynard Key\nEast Scott, KS 83343',
    'text': 'Reveal woman site federal true bag other. Theory natural meet pressure with.\nWord face show store. Operation cover professor gun hospital allow. Debate option Mrs better information clearly that of.',
    'email': 'pricemichael@example.org',
    'phone_number': '+1-441-721-6727x156',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kari Houston',
    'Matthew Barber',
    'Robert Sanchez',
],
    'json': {
    'name': 'Travis Smith',
    'address': '2724 Sara Wells\nJuliemouth, ME 58379',
},
    'key38128': 'value74334',
    'key31188': 'value60773',
    'key99891': 'value66708',
    'key57414': 'value41179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Joshua Lee',
    'address': '92024 Rivas Lock Apt. 257\nBrianview, AZ 24253',
    'text': 'Watch present wait.\nIndustry many general improve beat. Participant computer institution. Tough man interesting quickly cold.',
    'email': 'mflores@example.org',
    'phone_number': '652-868-6388x7072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Gabriel Smith',
    'Mr. Scott Young',
    'Andrew Hayes',
    'Brenda Oneill',
    'Tiffany Byrd',
    'Jessica Castillo',
    'Robert Griffin',
    'Denise Sanchez',
    'Catherine Perez',
],
    'json': {
    'name': 'Ashley Warner',
    'address': '008 Aaron Crescent Suite 102\nEast Cory, NM 30876',
},
    'key56649': 'value95800',
    'key66000': 'value35305',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Dennis Reeves',
    'address': '3585 Jordan Trace\nCaldwellton, DE 62817',
    'text': 'Arrive believe list record. Break cost newspaper common employee way staff actually.',
    'email': 'wcarr@example.net',
    'phone_number': '001-503-473-4805',
    'array_int_dynamic': [
    25201,
],
    'array_varchar_dynamic': [
    'Mark Gardner',
    'Joshua Grant',
    'Catherine Barker',
    'Jimmy Little',
    'Victor Kline',
],
    'json': {
    'name': 'Timothy Kelley',
    'address': '071 Rogers Heights\nMckenzieville, OH 97350',
},
    'key6428': 'value38258',
    'key68958': 'value99737',
    'key3205': 'value78311',
    'key23680': 'value71476',
    'key6876': 'value33592',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Jordan Green',
    'address': '438 Carter Stream\nJohnbury, MA 91780',
    'text': 'Yard cause product explain whose page player thought. Education marriage material culture able system.',
    'email': 'pricenicholas@example.net',
    'phone_number': '001-832-918-9927x6318',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Montgomery',
    'Isaac Smith',
    'Brittany Taylor',
],
    'json': {
    'name': 'Joshua Moon',
    'address': '13458 Acevedo Grove Apt. 093\nFigueroastad, ND 11327',
},
    'key986': 'value52212',
    'key56459': 'value25381',
    'key9756': 'value7085',
    'key75003': 'value94250',
    'key55629': 'value69116',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Erica Briggs',
    'address': '175 Ortiz Glens\nNorth Jodi, ME 18255',
    'text': 'Fear list save. Modern rest list author compare test. Save each lot specific car include significant.',
    'email': 'stephanie19@example.com',
    'phone_number': '(875)207-0503x29074',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Russell',
    'Sarah Woodard',
    'Edwin Wall',
    'Aaron Carter',
    'Sara Nelson',
    'Kurt Molina',
],
    'json': {
    'name': 'Scott Robinson',
    'address': '7092 Ernest Junction\nMichaelfort, AK 89617',
},
    'key58468': 'value44815',
    'key4174': 'value51849',
    'key47618': 'value3043',
    'key84184': 'value88901',
    'key7824': 'value33298',
    'key10695': 'value72873',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Bradley Allen',
    'address': '4488 Gray Shoals Suite 705\nDavidland, PW 75488',
    'text': 'Relationship question still important give. Sort account catch agent.\nRate everything discover development machine. Us born gun reach. Growth shake consumer win life describe.',
    'email': 'marcus67@example.com',
    'phone_number': '746.345.8280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Marissa Figueroa',
    'Nicole Miller',
    'Jenna Garcia',
    'Erin Porter',
    'Julia Lynn',
    'Destiny Clark',
    'Mark Hess',
    'Melissa Hernandez',
    'April Clark',
],
    'json': {
    'name': 'Courtney Rodriguez',
    'address': '20954 Molina Tunnel\nPort Katherinemouth, VA 40684',
},
    'key33415': 'value32101',
    'key41762': 'value71891',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'April Jones',
    'address': '90538 Norris Points\nChanchester, FL 91384',
    'text': 'Consider increase lay increase.\nPlay soon rock some detail also. Out matter any five baby.\nWorker then citizen interesting. Laugh teacher up hand water.',
    'email': 'tracysimpson@example.com',
    'phone_number': '(569)298-1093x30305',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Wayne Wheeler',
    'Anthony Decker',
    'Jason Anderson',
    'Jacob Villegas',
    'Jeffrey Meyer',
    'Craig Martin',
    'Connie Brooks',
    'Sabrina Miller',
    'Stephanie Short',
    'Rebecca Davis',
],
    'json': {
    'name': 'Christy Brown',
    'address': '24396 Whitaker Motorway Apt. 818\nDouglasside, AR 92699',
},
    'key29141': 'value30330',
    'key42297': 'value2134',
    'key82440': 'value71583',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Elizabeth Howard DVM',
    'address': '3839 Gregory Square\nPaulborough, VI 42923',
    'text': 'Wrong process machine spring ground. Audience light as direction. Image yes kid.\nCar near remain perhaps despite best. Who describe suffer lead apply choose subject.',
    'email': 'jenniferbailey@example.com',
    'phone_number': '(535)531-8152x0215',
    'array_int_dynamic': [
    91843,
],
    'array_varchar_dynamic': [
    'Mason Martin',
],
    'json': {
    'name': 'Paul Melton',
    'address': 'USS Page\nFPO AE 27621',
},
    'key55494': 'value22456',
    'key55426': 'value7204',
    'key742': 'value72888',
    'key55403': 'value12175',
    'key82902': 'value78496',
    'key77371': 'value24335',
    'key96097': 'value48458',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Anthony Nelson',
    'address': '8135 Vasquez Pass\nCollinsstad, NE 45468',
    'text': 'Through section character director indicate unit. Wait tough within what role art allow. Decade career build item seem fly face.\nOf catch talk level.',
    'email': 'gfields@example.net',
    'phone_number': '213.215.8483',
    'array_int_dynamic': [
    73243,
],
    'array_varchar_dynamic': [
    'Robin White',
    'Teresa Murphy',
    'Mary Moon',
    'Jessica Morrison',
    'Jessica Allen',
    'Richard Thomas',
    'William Ramirez',
    'Tracy Oconnell',
    'Joel Wiggins',
],
    'json': {
    'name': 'Heather Smith',
    'address': '0394 Mullen Circle\nLake Elizabethfort, CO 58886',
},
    'key17085': 'value2512',
    'key71506': 'value42209',
    'key66582': 'value43420',
    'key17973': 'value41016',
    'key5246': 'value94120',
    'key36641': 'value29876',
    'key14508': 'value10704',
    'key48723': 'value80350',
    'key36684': 'value11803',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Elaine Alvarez',
    'address': '765 Kendra Ferry\nGonzalezbury, GA 83883',
    'text': 'Same senior star. Expert trial drug improve. Service degree to loss work culture father.',
    'email': 'villanathan@example.com',
    'phone_number': '+1-928-371-9180x34658',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Diana Lewis',
    'Adam Riddle',
    'Lynn Haney',
    'Krista Benitez',
    'Ashley Thomas',
    'Arthur Sims',
    'Raymond Coleman',
    'Karl Edwards',
    'Gabriel Thompson',
],
    'json': {
    'name': 'Brandon Ellis',
    'address': '036 Aaron Ramp Suite 271\nWest Daniel, NH 64091',
},
    'key11587': 'value17544',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Daniel Hicks',
    'address': '1997 Moore Circle Apt. 575\nBlankenshipbury, RI 92540',
    'text': 'Attorney smile support discuss boy these. Follow Republican career science.',
    'email': 'arogers@example.net',
    'phone_number': '001-697-538-6928x39283',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Gina Knapp',
    'Darren Choi',
    'Danielle Downs MD',
    'Janice Brown',
    'Nicole Garza',
    'Randy Marshall',
    'Dawn Duke',
    'Ethan Boyle',
    'Monica Kelly',
    'Logan Fuentes',
],
    'json': {
    'name': 'Sabrina Jones',
    'address': '96231 Houston Street\nPerkinstown, NC 94094',
},
    'key3418': 'value73303',
    'key50195': 'value47038',
    'key9093': 'value59828',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Kimberly Villarreal',
    'address': '8685 Angela Well Suite 086\nFrankfurt, CO 75667',
    'text': 'Fine reflect reason yard new deal. Day ball quality PM customer than customer force.\nView more little role. Too about company experience here.',
    'email': 'wilsonapril@example.net',
    'phone_number': '(494)230-0455x0515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Sanders',
    'Megan Nichols',
    'Brooke Terry',
    'Cameron Hahn',
    'Brian Nunez',
    'Andrew Ward',
    'Stephen Hansen',
    'Phillip Young',
    'Richard Brown',
    'Madison Lawson',
],
    'json': {
    'name': 'Connie White',
    'address': '5766 Jones Estates Apt. 675\nGabrielport, FM 98042',
},
    'key54804': 'value96376',
    'key7409': 'value15447',
    'key448': 'value53617',
    'key81095': 'value57587',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Kristin Mullen',
    'address': '2409 Chavez Land Suite 060\nParsonsmouth, AS 96834',
    'text': 'Against knowledge book five while pull. Hour us offer game floor leg officer use. Respond their us which low.\nSea along win off party. Risk study computer. Yes international prevent produce interest.',
    'email': 'jimmyburke@example.org',
    'phone_number': '589.908.2533',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Craig Bennett',
    'Shelby Walker',
    'Daniel Bentley',
],
    'json': {
    'name': 'Karen Miller',
    'address': '616 Walker Views Apt. 128\nRodriguezstad, SD 16854',
},
    'key38571': 'value80208',
    'key66818': 'value72277',
    'key98133': 'value68243',
    'key85329': 'value28259',
    'key97279': 'value63959',
    'key20417': 'value8930',
    'key39127': 'value55084',
    'key16689': 'value29338',
    'key56838': 'value21150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'David Clark',
    'address': '2379 Jennings Branch\nKristenmouth, IL 73809',
    'text': 'Analysis most entire fall over. Claim machine current whether investment. Respond wonder station. Audience with drive visit office single note.',
    'email': 'brandondavis@example.net',
    'phone_number': '001-994-722-3044x548',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Stanton',
    'Jeffrey Adams',
    'Nicole Pittman',
    'Michael Morris',
    'Anne Chang',
    'Jessica Hawkins',
    'Sherry Miller',
],
    'json': {
    'name': 'Victor Wilkerson',
    'address': '6389 Ernest Lane\nThompsonstad, UT 73209',
},
    'key67131': 'value61239',
    'key19978': 'value23379',
    'key76876': 'value53532',
    'key23954': 'value79507',
    'key62904': 'value78415',
    'key40408': 'value5458',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'April Conner',
    'address': '5457 Kara Springs Suite 605\nSouth Sheilafurt, AZ 85578',
    'text': 'Able answer rise clearly. Already exactly set. Heavy since letter some take red.',
    'email': 'adrian60@example.com',
    'phone_number': '393-804-9048',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Cory Lawrence',
    'Wesley Norman',
],
    'json': {
    'name': 'Angela Ramos',
    'address': 'Unit 8999 Box 6032\nDPO AA 01790',
},
    'key16064': 'value39079',
    'key36836': 'value19920',
    'key2411': 'value17013',
    'key40177': 'value43453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Edward Harper',
    'address': '363 Soto Union\nSouth Trevorfurt, AZ 98154',
    'text': 'Partner window single. Development tell price sea catch memory none. Fight serve plant plan.',
    'email': 'carmstrong@example.com',
    'phone_number': '(714)319-6123x0867',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brenda Whitney',
    'Michael Moore',
    'Miguel Lewis',
    'Brian Simpson',
    'James Hernandez',
    'Lucas Lee',
    'Jeremy Adams',
    'Andrew Medina',
    'April Bird',
],
    'json': {
    'name': 'Jennifer Skinner',
    'address': '70332 Felicia Underpass Suite 945\nNorth Brian, IA 54965',
},
    'key87369': 'value32434',
    'key81137': 'value79039',
    'key577': 'value88561',
    'key5095': 'value35807',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Samuel Espinoza',
    'address': '506 Jennifer Prairie\nEast Mitchellton, MI 66335',
    'text': 'Food good support model. Performance process think buy four use while. Leave for enjoy everyone car focus. Sing just surface research ready might.',
    'email': 'krodriguez@example.net',
    'phone_number': '389.697.9805x7770',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Yang',
    'Kevin Miller',
    'Erica Freeman',
],
    'json': {
    'name': 'Christopher Miller',
    'address': 'Unit 6390 Box 8549\nDPO AP 60328',
},
    'key6008': 'value79539',
    'key11594': 'value88939',
    'key38582': 'value74358',
    'key49008': 'value89252',
    'key27493': 'value76602',
    'key52498': 'value71263',
    'key92997': 'value20490',
    'key89861': 'value15655',
    'key79015': 'value41176',
    'key27583': 'value28469',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Janice George',
    'address': '8347 Woodward Greens Suite 340\nNorth Jason, NC 67173',
    'text': 'Check someone than crime smile.\nHuman space eight rate. Factor specific apply allow carry about. Watch dinner last traditional system somebody husband.',
    'email': 'bryantdavid@example.com',
    'phone_number': '937-707-5818x487',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Padilla',
    'Barbara Byrd',
    'Barbara Moreno',
    'Sherry Oconnor',
    'Mallory Nunez',
    'Carrie Sims',
    'Aaron Hernandez',
    'Mario Noble',
],
    'json': {
    'name': 'Rebecca Williamson',
    'address': 'USNV Allen\nFPO AE 26629',
},
    'key69680': 'value80211',
    'key48542': 'value86750',
    'key5511': 'value38215',
    'key4657': 'value68560',
    'key3725': 'value85598',
    'key11836': 'value83799',
    'key75550': 'value4469',
    'key69754': 'value25075',
    'key25952': 'value78126',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Edward Brennan',
    'address': '315 Jackson Locks Apt. 862\nTrevorport, SC 16677',
    'text': 'Generation feel risk. Blood window from oil not list performance.\nEight writer thus recent. Determine understand happy option cultural. Expert note without tough nothing reality.',
    'email': 'qrodriguez@example.net',
    'phone_number': '001-516-616-5913',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Ross',
    'Richard King',
    'Heather Ramsey',
    'Donna Brown',
],
    'json': {
    'name': 'Christopher Robles',
    'address': '46832 Mathews Forest Apt. 326\nNorth Larryhaven, GA 79178',
},
    'key35070': 'value21066',
    'key87966': 'value6809',
    'key34348': 'value967',
    'key78526': 'value41853',
    'key50875': 'value1254',
    'key11753': 'value15724',
    'key43830': 'value96944',
    'key16045': 'value14023',
    'key39602': 'value81868',
    'key85109': 'value19',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'William Kirk',
    'address': '0971 Juan Oval\nNorth Donnastad, MT 97588',
    'text': 'Mean piece language pattern support memory most. Later movie return serve order account top challenge.',
    'email': 'debraharrison@example.net',
    'phone_number': '001-619-683-8147x720',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Johnson',
    'Crystal Chavez',
    'Crystal Clay',
],
    'json': {
    'name': 'Jeremy Moore III',
    'address': '9970 Justin Tunnel\nKramerville, TN 67698',
},
    'key67031': 'value48932',
    'key78620': 'value98776',
    'key27636': 'value21778',
    'key24025': 'value842',
    'key22809': 'value43906',
    'key21983': 'value94789',
    'key91139': 'value57331',
    'key8548': 'value7533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Evelyn Williams',
    'address': 'USNS Moore\nFPO AE 59204',
    'text': 'House former positive food probably. According others him have born mind. His modern decide local late.\nAccount everything whether democratic by national. Individual pull boy.',
    'email': 'henrymichael@example.com',
    'phone_number': '2232885731',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Serrano',
    'Mrs. Felicia Harrington',
    'Michael Wells',
    'David Knox',
    'Andrea Santiago',
],
    'json': {
    'name': 'Sarah Mann',
    'address': '74495 Petty Trail\nDianaport, FL 92628',
},
    'key90145': 'value37231',
    'key15124': 'value38347',
    'key90297': 'value89088',
    'key78532': 'value30793',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Richard Wallace',
    'address': '56389 Wood Cliffs\nCynthiamouth, UT 69633',
    'text': 'Hundred born enough give. Turn worker answer practice.\nExperience trade by yes report focus stage. Teach dream ability campaign town meeting continue their. Factor contain water think.',
    'email': 'nguyenkaren@example.net',
    'phone_number': '972-543-6037x6112',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Frank Gonzalez',
    'Joseph Williams',
    'Kimberly Raymond',
    'Wayne Phillips',
    'Stefanie Butler',
    'Ronald Stout',
    'James Livingston',
    'Michael Ellison',
    'James Williams',
],
    'json': {
    'name': 'Jennifer Schneider',
    'address': '96964 Spencer Knolls Apt. 287\nNorth Amy, MI 75335',
},
    'key59': 'value12601',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Eric Adams',
    'address': '761 Thomas Villages\nJenniferfurt, NH 54745',
    'text': 'Along technology brother factor do. These guess kitchen court president official within class.',
    'email': 'georgekari@example.net',
    'phone_number': '486-656-7123',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Scott Neal',
    'Catherine Byrd',
    'Jesse Ward',
    'Gregory Baker',
    'Johnny Sanchez',
    'Denise Rogers',
    'Linda Salazar',
    'Connie Lowe',
    'Patricia Foster',
    'Daniel Kent',
],
    'json': {
    'name': 'Joseph Massey',
    'address': '72349 Moody Bridge Apt. 275\nJesseview, MI 46814',
},
    'key34679': 'value37155',
    'key85693': 'value557',
    'key38379': 'value53397',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Daniel Robles',
    'address': '40083 Bryant Greens Apt. 591\nMarquezport, GA 75419',
    'text': 'Wife imagine network one agent buy. Simply fund operation than.\nSomebody anything page model politics weight. Country degree quickly everything note never sure.',
    'email': 'griffithdenise@example.com',
    'phone_number': '(719)278-5287x5149',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Pearson',
    'Joshua Butler',
    'Brittany Buchanan',
    'Tamara Wilson',
    'Jennifer Allen',
    'Sara James',
],
    'json': {
    'name': 'Mrs. Rachel Welch',
    'address': '401 Erin Gardens Apt. 771\nEast Cynthiaburgh, OH 36090',
},
    'key7401': 'value95746',
    'key67413': 'value33271',
    'key91250': 'value58356',
    'key49268': 'value31008',
    'key27295': 'value29550',
    'key70278': 'value47111',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'David Sanchez',
    'address': 'USNS Cunningham\nFPO AA 55371',
    'text': 'Mind about score game. Between recent travel maintain official where mother government. Tell maintain stay this.\nOthers total song light interesting claim why. Ten everybody budget set public return.',
    'email': 'bclay@example.net',
    'phone_number': '4713337090',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Price',
    'James Shea',
    'Monica Booth',
    'Amy Stevens',
],
    'json': {
    'name': 'Donald Wagner',
    'address': '0704 Smith Landing\nNorth Jessicashire, MT 38313',
},
    'key87593': 'value30572',
    'key96765': 'value33083',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'James Baker',
    'address': '78410 Miller Extension Apt. 470\nGeorgeview, AL 94967',
    'text': 'Want sometimes believe position. Piece star shoulder establish give Mr. Factor too difference open anything artist.',
    'email': 'mcphersonbenjamin@example.com',
    'phone_number': '+1-738-443-0731x081',
    'array_int_dynamic': [
    51360,
],
    'array_varchar_dynamic': [
    'Aimee Ramirez',
    'Joseph Miranda',
],
    'json': {
    'name': 'Clinton Smith',
    'address': '6535 John Brook\nNorth Madisonside, AL 80230',
},
    'key15527': 'value11493',
    'key46629': 'value59983',
    'key97110': 'value35914',
    'key94590': 'value92310',
    'key70536': 'value31536',
    'key68807': 'value52202',
    'key46902': 'value22335',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Nathaniel Rodriguez',
    'address': '662 Koch Extensions Suite 408\nSouth Miguel, KS 35016',
    'text': 'Their eat four stop tell respond. Shake sport sometimes identify person share difficult fine. Fast determine admit someone yeah.\nRelationship indicate executive hold.',
    'email': 'rebeccaalexander@example.org',
    'phone_number': '001-338-207-9938',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Chung',
    'Eric Thompson',
    'Shelby Johnson',
    'Christina Campbell',
    'Kathleen Ramos',
    'Sandra Ruiz',
    'Jennifer Martin',
    'Michelle Jimenez',
    'Micheal Lee',
],
    'json': {
    'name': 'Krista Hamilton',
    'address': '5113 Kelsey Manor\nChapmanstad, LA 05988',
},
    'key90440': 'value46525',
    'key3035': 'value20239',
    'key71305': 'value1277',
    'key11378': 'value86263',
    'key63094': 'value28515',
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
    'RequestId': '73e24648-62ef-11f0-8d68-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_41_939891UqpjKxwG',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-1]_1752744103.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId3210011752744103Json()
    test.run_tests()
