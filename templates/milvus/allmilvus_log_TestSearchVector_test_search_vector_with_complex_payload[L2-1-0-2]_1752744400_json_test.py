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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_complex_payload[L2-1-0-2]_1752744400_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[L2-1-0-2]_1752744400.json"
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithComplexPayloadL21021752744400Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[L2-1-0-2]_1752744400.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[L2-1-0-2]_1752744400.json"
        self.test_count = 5  # 测试方法数量
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
    'RequestId': '20b85dc9-62f0-11f0-854e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_26_31_911081WxZdlCvJ',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
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
    'RequestId': '23d9328a-62f0-11f0-b5ef-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_26_31_911081WxZdlCvJ',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jackie Bradford',
    'address': '867 Watkins Pass\nHillside, SD 63073',
    'text': 'Teacher produce prove ability high information floor. School technology man although poor alone cell. Certainly personal without pull important without.',
    'email': 'eric76@example.com',
    'phone_number': '7153340875',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Cruz',
    'Toni Blair',
    'Caitlin Pitts',
    'Mary Dyer',
    'Kevin Price',
    'Carl Lopez',
    'Christopher Jones',
],
    'json': {
    'name': 'Neil Moreno',
    'address': '70604 Kevin Crossing Suite 967\nMichaeltown, MA 19116',
},
    'key94355': 'value54538',
    'key8707': 'value25998',
    'key90596': 'value63940',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sarah Cummings',
    'address': '613 Nicholas Cliffs\nTanyahaven, PA 20503',
    'text': 'Economy end will door civil across. Glass whether challenge side speak focus score.\nEvent give them why order. Point college late people.',
    'email': 'lesterjulia@example.net',
    'phone_number': '660.859.7155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stacy Andersen',
    'Andrew Lane',
    'Clinton Harrison',
    'Gary Stewart',
    'Martin Murphy',
],
    'json': {
    'name': 'Michael Wright',
    'address': 'Unit 8310 Box 3705\nDPO AP 18086',
},
    'key27566': 'value75300',
    'key10458': 'value52002',
    'key42546': 'value82426',
    'key28059': 'value67976',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jessica Coleman',
    'address': 'Unit 1587 Box 7080\nDPO AE 76463',
    'text': 'Team they with shoulder why firm maintain low. I heart cut candidate consumer win security.',
    'email': 'martinezmiguel@example.org',
    'phone_number': '(691)812-8382x179',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Debra Ali',
    'Katherine Huffman',
    'Zachary Garcia',
],
    'json': {
    'name': 'Cindy Smith',
    'address': '1014 Beck Ridge\nPollardburgh, NY 02472',
},
    'key64328': 'value38545',
    'key73748': 'value39956',
    'key17353': 'value87837',
    'key72623': 'value2774',
    'key66178': 'value47451',
    'key55889': 'value92288',
    'key31731': 'value79107',
    'key78437': 'value2907',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'William Ramirez',
    'address': '8050 Rodgers Common Apt. 287\nPort Angelaberg, VI 27569',
    'text': 'Me physical professional gun quickly case. Stop community company institution until. Under car light could which.',
    'email': 'marcusfuentes@example.net',
    'phone_number': '001-400-820-5295x13223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brittney Terry',
    'Bernard Terry',
    'Amber White',
    'Tiffany Cohen',
    'Stephanie Hayes',
    'James Smith',
    'Jessica Ferrell',
    'Nicholas Small',
    'David Cox',
],
    'json': {
    'name': 'Matthew Turner',
    'address': '11823 Cynthia Fort\nMichaelstad, GA 07700',
},
    'key99948': 'value64072',
    'key87974': 'value9754',
    'key27649': 'value54653',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Eric Jones',
    'address': '758 Patricia Turnpike Suite 901\nNew Diane, MI 22813',
    'text': 'Standard half record natural get college executive. Near yeah minute feeling participant. Successful better foreign official.\nModel crime style produce ask.',
    'email': 'benjamin97@example.net',
    'phone_number': '001-693-380-4102x705',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Turner',
    'Collin Williams',
    'Jonathan Murphy',
    'Mike Rivera',
    'Michele Leon',
    'Corey Williams',
    'Brandon Thomas',
],
    'json': {
    'name': 'Adam Cooper',
    'address': 'Unit 8402 Box 9982\nDPO AA 94959',
},
    'key84916': 'value17833',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jimmy Aguilar',
    'address': 'Unit 1156 Box 0817\nDPO AE 77568',
    'text': 'Through dog serve measure situation. Attention ever while traditional respond company fight number.\nWord suddenly citizen. Head miss somebody. Wide history break than.',
    'email': 'samanthacarr@example.org',
    'phone_number': '+1-674-638-8506x74686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Charles',
    'Laurie Taylor',
    'Lauren Anderson',
    'Stephanie Doyle',
],
    'json': {
    'name': 'Katrina Johnson',
    'address': '6052 Zimmerman Trail Suite 691\nSouth Joshuaburgh, WI 43620',
},
    'key53708': 'value59550',
    'key43579': 'value80276',
    'key85392': 'value7031',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Julie Gomez',
    'address': '953 Charles Walks Apt. 157\nGarciaburgh, PW 98267',
    'text': 'Rock summer discussion bank. Rate institution number loss.',
    'email': 'teresa50@example.net',
    'phone_number': '001-288-907-1378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Anderson',
    'Michael Gordon',
    'Kyle Mcgee',
    'Jordan Jones',
    'Adam Clark',
    'Krista Chen',
    'Stacy Jones',
],
    'json': {
    'name': 'Jeffery Huffman',
    'address': '201 Victor Inlet\nPattersonchester, WA 99771',
},
    'key788': 'value85175',
    'key42429': 'value40259',
    'key14025': 'value34311',
    'key2112': 'value93939',
    'key44667': 'value91438',
    'key49843': 'value63124',
    'key48452': 'value23658',
    'key40318': 'value29918',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Linda Parker PhD',
    'address': '825 Amy Dale\nSouth Devin, IA 86808',
    'text': 'Attack strong office cause cultural.\nLoss pick police project. Perform environment true increase yard day within community.',
    'email': 'cvincent@example.org',
    'phone_number': '859.664.8853',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Mcmillan',
    'Richard Berry',
    'Theodore Barnes',
    'Jackson Wallace',
    'Katie Hughes',
    'Zachary Rivera',
    'Rebecca Holden',
    'David Vaughn',
    'Tommy Jenkins',
],
    'json': {
    'name': 'Tyler Hogan',
    'address': '001 Osborn Plaza Suite 695\nWest Christopherchester, SC 88091',
},
    'key82561': 'value61986',
    'key46113': 'value7380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Wayne Castro',
    'address': '013 Debbie Circles Apt. 897\nKeybury, IA 30126',
    'text': 'Carry decade follow bit. Effect carry explain walk.\nDirection small quality large worker me per among. Low side material reflect pay line material.',
    'email': 'ricky75@example.org',
    'phone_number': '779.755.6612x21412',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Adam Long',
    'Glen Hughes',
    'Amanda Horton',
    'Danny Moore',
    'Cindy Dawson',
    'Julie Hines',
    'Michael Hinton',
    'Gary Cardenas',
    'Jennifer Abbott',
    'Diana Clay',
],
    'json': {
    'name': 'Christian Carpenter',
    'address': '955 Sanders Green\nSouth Nichole, FM 01178',
},
    'key64453': 'value77340',
    'key56473': 'value31590',
    'key90732': 'value34019',
    'key16966': 'value65061',
    'key68156': 'value33745',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Amy Green',
    'address': '010 Amber Spurs Apt. 656\nWilsonhaven, PW 00762',
    'text': 'Commercial provide expect entire. Prepare present finish all.\nFour ok institution. Run hospital southern list thus. Early according forward reach painting.',
    'email': 'alarsen@example.org',
    'phone_number': '+1-575-913-3316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Donald Klein',
    'Anthony Chan',
    'Barbara Haley',
    'Mark Johnson',
],
    'json': {
    'name': 'Rachel Griffin',
    'address': '01799 Dillon Greens Suite 510\nLake Lorrainechester, MA 17684',
},
    'key77465': 'value26841',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Geoffrey Keith',
    'address': '80183 Campbell Common\nLindseybury, FM 63467',
    'text': 'Sell tough establish answer guess. Participant agency fear require. Particular special democratic teacher region dark something consider.',
    'email': 'scottrobert@example.net',
    'phone_number': '(885)473-0629x70205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sonya Scott',
    'Alec Morrow',
    'Amanda Walker',
    'Justin Gilmore',
    'Benjamin Brooks',
],
    'json': {
    'name': 'Brenda Woodward',
    'address': 'USS Martin\nFPO AE 91232',
},
    'key7215': 'value87232',
    'key1759': 'value23577',
    'key89675': 'value95785',
    'key68391': 'value11646',
    'key33377': 'value46465',
    'key67303': 'value75421',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Angela Nash',
    'address': '86884 Rachael Wells\nEast Leonardchester, CA 21696',
    'text': 'Good movement occur threat. Recent check tax. Pay he and specific expert yeah.\nPattern west trade only agency near. Southern individual business foreign save.',
    'email': 'taylorbrad@example.net',
    'phone_number': '001-457-572-5266x4894',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Koch',
    'Lindsey Howell',
    'David Anderson',
],
    'json': {
    'name': 'Danielle Mueller',
    'address': '309 Lewis Mall Suite 999\nJasonside, CA 42513',
},
    'key90369': 'value46560',
    'key13857': 'value44509',
    'key9337': 'value54504',
    'key49611': 'value55121',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Crystal Webb MD',
    'address': 'Unit 4999 Box 8045\nDPO AE 72900',
    'text': 'Leader condition spend activity. Very type as home from knowledge sell. Goal ability stock whatever.',
    'email': 'valeriehughes@example.org',
    'phone_number': '001-967-590-7981',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Lopez',
    'Isabella Preston',
    'Tracy Hernandez',
    'Stephanie Greene',
    'Robert Murphy',
    'Anthony Martin',
    'Carlos Santiago',
],
    'json': {
    'name': 'Carol Williams',
    'address': '33605 Ryan Pike Suite 654\nEast Michael, MP 85422',
},
    'key82952': 'value66973',
    'key87903': 'value40902',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Nicholas Mills',
    'address': '1936 Jonathan Avenue Suite 675\nGomezstad, MN 12560',
    'text': 'Amount provide population son fish picture. Future foreign do join rather challenge close red. Serious include section investment.',
    'email': 'xturner@example.net',
    'phone_number': '277.813.2547x610',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Rush',
    'Robert Duke',
],
    'json': {
    'name': 'Jessica Castillo',
    'address': '743 Joe Trail\nPort Patrickstad, ME 52348',
},
    'key96141': 'value21120',
    'key29878': 'value65429',
    'key87992': 'value88206',
    'key97855': 'value88345',
    'key26316': 'value13049',
    'key99725': 'value43273',
    'key34237': 'value90424',
    'key23840': 'value98133',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Pamela Scott',
    'address': '19208 Brian Rapid\nLake Eric, MN 43024',
    'text': 'Modern effort southern growth such end serve. Not almost real since detail paper bring.\nPrice yourself politics but high.\nHere sport area if area. Early base election spend.',
    'email': 'dukechad@example.org',
    'phone_number': '001-784-960-5634',
    'array_int_dynamic': [
    50290,
],
    'array_varchar_dynamic': [
    'Phillip Mckenzie',
    'Megan Solis',
    'Dr. Jonathon Smith DDS',
    'Randy Reyes',
    'Randy Mccoy',
    'Brian Holt',
    'Lindsey Manning',
    'Jerry Price',
],
    'json': {
    'name': 'Carl Wheeler',
    'address': '36222 Parker Trace Apt. 741\nMonicaburgh, AK 31649',
},
    'key57494': 'value60925',
    'key64083': 'value4354',
    'key37626': 'value42797',
    'key73231': 'value13961',
    'key35485': 'value24489',
    'key95522': 'value41507',
    'key51583': 'value37006',
    'key31027': 'value93082',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jennifer West',
    'address': 'USNV Jones\nFPO AP 76888',
    'text': 'Pm long position beautiful watch relationship. Could require another your book that. Weight red end write table grow.\nLand scientist responsibility idea painting past. Win that spring.',
    'email': 'fordalexandra@example.net',
    'phone_number': '(926)713-6263x231',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Vazquez',
    'Mary Bowen',
    'Donna Allen',
    'Ashley Howell',
    'Amanda Sullivan',
],
    'json': {
    'name': 'Valerie Santiago',
    'address': '64338 Watson Wells Suite 239\nNorth Cherylberg, WA 35014',
},
    'key55572': 'value74744',
    'key11111': 'value36789',
    'key36063': 'value27837',
    'key57128': 'value26748',
    'key94797': 'value20893',
    'key7127': 'value99501',
    'key75484': 'value55470',
    'key59029': 'value55174',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'David Dickerson',
    'address': '18782 Robert Causeway\nStephensfurt, MN 18491',
    'text': 'Use could if hot.\nThrough should even win camera. Imagine son past up chair majority.\nConsider order current. Beyond area most minute.',
    'email': 'omoreno@example.net',
    'phone_number': '(356)240-3143',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Griffith',
    'Nathan Yang',
],
    'json': {
    'name': 'Hannah Robinson',
    'address': '102 Amber Road Apt. 906\nEast Abigailborough, KS 83218',
},
    'key89190': 'value19572',
    'key53': 'value13260',
    'key89160': 'value49148',
    'key22971': 'value99407',
    'key51945': 'value85579',
    'key27663': 'value47451',
    'key59249': 'value61742',
    'key88972': 'value83825',
    'key7456': 'value28198',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Madeline Guerrero',
    'address': '3396 Richard Stream Suite 327\nSingletonstad, NV 44307',
    'text': 'Man mention car true I. Into that suggest item situation kid interview. Hundred effort bar father.',
    'email': 'paulshaffer@example.net',
    'phone_number': '2492389197',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amy Lee',
    'Christine Hansen DVM',
    'Roger Robertson',
    'Jeffrey West',
    'Kayla Davidson',
    'Wesley White',
    'Christopher Kidd',
    'April Jensen',
    'Miguel Wright',
],
    'json': {
    'name': 'Cynthia Stewart',
    'address': '082 Holloway Lodge\nNew Teresa, GU 84735',
},
    'key98853': 'value65133',
    'key7769': 'value80598',
    'key9534': 'value8904',
    'key80578': 'value78902',
    'key48780': 'value25299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Stephanie Ford',
    'address': '94737 Eric Gardens\nEast Amandaville, CT 15851',
    'text': 'Central difficult travel too them computer fact quality. Chair land billion over. Environmental especially as young represent realize walk. Chair could I gun power nation.',
    'email': 'eweeks@example.org',
    'phone_number': '263-689-8522x708',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Miranda',
    'Donna Dickerson',
    'Robert Davis',
    'Linda Jacobs',
    'John Ortega',
    'Alyssa Thompson',
    'Mr. Alexis Campbell Jr.',
    'Stacy Page',
    'Sarah Santiago',
],
    'json': {
    'name': 'Vanessa Jones',
    'address': '6339 Heather Extension\nWest Regina, ME 27423',
},
    'key86466': 'value92991',
    'key91990': 'value1250',
    'key94512': 'value61044',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'David Nguyen',
    'address': '2862 Brent Loop\nWilliamside, AL 07572',
    'text': 'Item performance become forget. However term kind beat nice.\nGuy cause simply. Station raise alone now bed act. Support themselves realize career other.',
    'email': 'brooksjohn@example.org',
    'phone_number': '879-291-2365x37029',
    'array_int_dynamic': [
    67264,
],
    'array_varchar_dynamic': [
    'Cathy Long',
    'Michael Harrison',
    'Christopher Carr',
    'Shaun Miller',
    'Kathryn Chapman',
    'Marc Arnold',
    'Robin Dalton',
    'Stephanie Sampson',
],
    'json': {
    'name': 'Larry Walker',
    'address': '511 Catherine Plain Suite 935\nScottport, NY 09333',
},
    'key50960': 'value85419',
    'key95816': 'value28574',
    'key66754': 'value33153',
    'key94980': 'value27733',
    'key6433': 'value6754',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Rebecca White',
    'address': 'USNS Acevedo\nFPO AE 91794',
    'text': 'Wish low manager many what go operation. Report read town out six American trip. Usually require safe act. Election because wife outside power wear.',
    'email': 'ericlowe@example.com',
    'phone_number': '484-800-5205x85501',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Justin Hunter',
    'Sarah Peters',
],
    'json': {
    'name': 'Steven Brown',
    'address': '9933 Pham Unions\nPort Jordanstad, AZ 94824',
},
    'key30601': 'value18977',
    'key38877': 'value97266',
    'key23652': 'value47343',
    'key62571': 'value87534',
    'key74343': 'value53495',
    'key51693': 'value46500',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Shawn Krause',
    'address': '2630 Kimberly Heights Suite 770\nNorth Amanda, FL 70714',
    'text': 'People save challenge later every. Mean stand civil animal easy. Opportunity skill professor.\nWhat trouble contain explain. Before forget some. Spring me my sign add.',
    'email': 'christina80@example.com',
    'phone_number': '001-858-652-9804x4540',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Allison Gibson',
],
    'json': {
    'name': 'Gina Martin',
    'address': '7080 Taylor Grove Suite 772\nStacyfort, NC 85750',
},
    'key91270': 'value96634',
    'key46853': 'value17136',
    'key73997': 'value88045',
    'key43313': 'value18945',
    'key21038': 'value40210',
    'key51195': 'value38568',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Adam Mcmahon',
    'address': '0288 Susan Coves Suite 431\nAmyberg, OR 03209',
    'text': 'Prevent cover week too speech significant performance. Local consumer record lawyer. Foot return to audience close always sport.',
    'email': 'jesuscarrillo@example.org',
    'phone_number': '874.541.1917x72781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Roger Brown',
    'Gary Bates',
    'Alyssa Patel',
    'Erin Brown',
    'Anthony Austin',
    'Jerry Wagner',
    'Edward Taylor',
    'Stacey Williams',
    'Patrick Davis',
],
    'json': {
    'name': 'Misty Rollins',
    'address': '797 Linda Neck\nDarrenfurt, AR 32844',
},
    'key98012': 'value18794',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Julie Hill',
    'address': '6026 Vanessa Manors\nPort Stacyshire, TN 24258',
    'text': 'Question than single. Daughter between especially always model point risk. Animal allow age coach.',
    'email': 'robert89@example.org',
    'phone_number': '676-684-3836',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Edwards',
    'Gina Olsen',
    'Sheryl Gray',
],
    'json': {
    'name': 'Elizabeth Zhang',
    'address': '34434 Douglas Vista\nNew John, MP 13730',
},
    'key31948': 'value10977',
    'key87011': 'value90499',
    'key51213': 'value53815',
    'key37712': 'value79759',
    'key34854': 'value66810',
    'key69409': 'value53886',
    'key43370': 'value15667',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Christine Meyers',
    'address': '6245 Reginald Orchard Apt. 169\nContrerastown, DC 50875',
    'text': 'Live while debate modern cause should. Vote detail peace usually stage.',
    'email': 'bassbrian@example.org',
    'phone_number': '001-638-383-9679x8784',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Valenzuela',
    'Heather Carney',
    'Benjamin Morgan',
    'Joseph Edwards',
    'Ronald Serrano',
],
    'json': {
    'name': 'Kimberly Mckinney',
    'address': '5694 Mendez Motorway\nSouth Marcus, WY 38025',
},
    'key15956': 'value57212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Amanda Perez',
    'address': '00134 Amy Village Apt. 034\nMitchellhaven, UT 57649',
    'text': 'Music clear ground claim opportunity great must. Sell today one safe boy financial. Ten exactly mother mean sister than. Money expect wall pretty safe.',
    'email': 'travisaguilar@example.com',
    'phone_number': '+1-320-801-8543x6035',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Ramirez',
    'Christopher Andrews',
    'Cheyenne Holland',
    'Tammy Stevens',
    'Erin Munoz',
    'Lance Rogers',
    'Melissa Miller',
    'Lauren Jones',
    'Kayla Martin',
    'Jeffrey Lynch',
],
    'json': {
    'name': 'Anna Davis',
    'address': 'Unit 2406 Box 4027\nDPO AE 28020',
},
    'key86420': 'value16024',
    'key86799': 'value56549',
    'key55253': 'value71505',
    'key23548': 'value95202',
    'key47156': 'value34483',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'David Phelps',
    'address': 'Unit 1694 Box 1470\nDPO AA 47422',
    'text': 'Off laugh seat cultural. Although population young yard offer response hold. Prepare wish environmental today sound of.\nSummer yet successful six very hard. Future policy first often couple chair.',
    'email': 'samanthavargas@example.net',
    'phone_number': '703.319.8295x03617',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Murphy',
    'Jeffery Morris',
    'Emily Combs',
],
    'json': {
    'name': 'Donald Wilkins',
    'address': '59678 Hill Station\nWest Anthonyville, LA 99839',
},
    'key59821': 'value96125',
    'key62472': 'value83602',
    'key48305': 'value39234',
    'key28361': 'value86947',
    'key68445': 'value28693',
    'key70334': 'value39934',
    'key12060': 'value93032',
    'key15809': 'value77562',
    'key64713': 'value21122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Marc Roman',
    'address': '6093 Mclaughlin Land Apt. 772\nJenniferstad, MD 46077',
    'text': 'Down effort professional camera particularly audience serious. Himself which plan only animal rock. Investment green eye phone store attack manage.',
    'email': 'jackhenry@example.com',
    'phone_number': '5303622026',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Caldwell',
    'Randall Villarreal',
    'Jonathan Williams',
    'Joseph Fernandez',
],
    'json': {
    'name': 'Jonathan Robbins',
    'address': '25588 Collins Flat\nJohnsonshire, SD 91862',
},
    'key4074': 'value80044',
    'key54602': 'value70261',
    'key398': 'value88332',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jason Neal',
    'address': '6944 Christine Coves\nPort Annfort, PR 41904',
    'text': 'At sort little among outside. Become project now citizen hear campaign.\nRock rule last city data. Find entire easy record project set.\nAgainst plan heavy be read.',
    'email': 'gbullock@example.net',
    'phone_number': '+1-440-288-7049',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Sullivan',
    'Alyssa Jones',
    'John Nguyen',
    'Dale Shaw',
    'Megan Allen',
],
    'json': {
    'name': 'Joshua Hawkins',
    'address': '059 Jon Meadow Apt. 601\nNew John, OK 58057',
},
    'key49808': 'value84887',
    'key1946': 'value8275',
    'key62104': 'value6926',
    'key77509': 'value93145',
    'key13041': 'value50854',
    'key32802': 'value27185',
    'key32547': 'value89317',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Christopher Spears',
    'address': '9444 Kevin Ports Suite 824\nNorth Emily, MD 48028',
    'text': 'Arm charge type local something bad resource. Billion president decide per fight.',
    'email': 'williamsmelissa@example.org',
    'phone_number': '(558)331-4796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Robinson',
    'Kyle Chen',
],
    'json': {
    'name': 'Christopher Montoya',
    'address': '286 Danny Shoal Apt. 035\nGrahamchester, NE 79602',
},
    'key25667': 'value72975',
    'key24845': 'value81712',
    'key97634': 'value18189',
    'key7974': 'value94214',
    'key8047': 'value4431',
    'key30735': 'value81267',
    'key40602': 'value12977',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Bethany Rodriguez',
    'address': '178 Susan Islands\nMartinborough, VA 98162',
    'text': 'Open among year shoulder he. Trial reach rather yes through grow several. This society anyone.',
    'email': 'willislaura@example.net',
    'phone_number': '001-871-545-5772x632',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Charles Wyatt',
    'Miguel Miller',
    'Jennifer Hawkins',
    'Richard Long',
    'David Glenn',
    'Dylan Mueller',
    'Michelle James',
    'Charles Long',
    'Stephanie James',
    'Michael Bell',
],
    'json': {
    'name': 'Sabrina Reyes',
    'address': '6109 Melody Crescent Suite 097\nDennistown, ID 53952',
},
    'key4891': 'value61522',
    'key41146': 'value61363',
    'key32169': 'value77139',
    'key47600': 'value71232',
    'key93880': 'value40782',
    'key47594': 'value53252',
    'key781': 'value1321',
    'key83823': 'value31338',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Christine Miller',
    'address': '5590 Debra Fords Suite 903\nLake Jennifer, NJ 72148',
    'text': 'Fill head wind choose go.\nChair college operation school improve physical shake. Accept father operation industry memory cultural these.',
    'email': 'omiller@example.net',
    'phone_number': '001-609-276-7230x942',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Charles Bradshaw',
    'Charles Garcia',
    'Teresa Goodman',
    'Megan Hunt',
    'Rebecca Stephens',
    'Benjamin Garza',
    'Adam Ramirez',
],
    'json': {
    'name': 'Timothy Jones',
    'address': 'PSC 7240, Box 1241\nAPO AA 04008',
},
    'key27592': 'value76206',
    'key72401': 'value73340',
    'key42276': 'value76506',
    'key77836': 'value59660',
    'key31199': 'value762',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Jo Sexton',
    'address': '21597 Deanna Courts Suite 038\nCarsonberg, OK 34512',
    'text': 'Town everybody just whose. Today idea vote health hot question during all. Blue hundred cup his. Business key buy mention policy message write party.',
    'email': 'antonio87@example.com',
    'phone_number': '641-820-9157x12280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Erik Williams',
    'James Evans',
    'Jordan Robinson',
    'Douglas Burke',
    'Michael Diaz',
    'Kimberly Mccarthy',
    'Sean Stewart',
    'Tiffany Alvarado',
    'Steven Mitchell',
    'Troy Thomas',
],
    'json': {
    'name': 'Claudia Campos',
    'address': '87701 Christopher Lakes Apt. 794\nKathleenfurt, NC 23398',
},
    'key37452': 'value94227',
    'key47015': 'value15498',
    'key81945': 'value63794',
    'key19914': 'value62197',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Darlene Wallace',
    'address': '50845 Michael Points\nNorth Monica, WV 87477',
    'text': 'Six first certainly might difference keep food. Situation play painting make.',
    'email': 'castrolaura@example.org',
    'phone_number': '+1-882-233-1382x148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Poole',
    'John Matthews',
    'Amy Freeman',
],
    'json': {
    'name': 'Tiffany Collins',
    'address': '74010 Burns Freeway Suite 760\nLawrencemouth, TN 09049',
},
    'key6237': 'value70700',
    'key26192': 'value5184',
    'key7464': 'value59579',
    'key165': 'value6841',
    'key43129': 'value89189',
    'key91769': 'value43303',
    'key57700': 'value81013',
    'key64999': 'value28744',
    'key89572': 'value76938',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Kimberly Callahan',
    'address': 'Unit 5016 Box 5667\nDPO AA 53167',
    'text': 'Source actually yard none certainly today. Me glass so way stage.\nAfter say paper art body floor his hair. Speak arrive join activity look door.\nMonth agency site.',
    'email': 'ortegataylor@example.net',
    'phone_number': '001-674-929-7562x5870',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tami Hunt',
    'Richard Hart',
    'Luis Henderson',
    'Erika Williams',
    'David Turner',
],
    'json': {
    'name': 'Denise Morris',
    'address': '20999 Haynes Mill Apt. 491\nGillburgh, KS 73785',
},
    'key53370': 'value5425',
    'key44697': 'value76719',
    'key80766': 'value37750',
    'key36010': 'value65439',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Joel Sherman',
    'address': '1456 Heather Camp Suite 968\nAlexborough, DC 27807',
    'text': 'Follow city society those. Your be catch. From area gun inside guy magazine remain.',
    'email': 'zcontreras@example.net',
    'phone_number': '001-206-574-6837x9680',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Ortiz',
],
    'json': {
    'name': 'Natalie Brown',
    'address': '203 Daniel Trail\nBarnettview, PA 44797',
},
    'key26076': 'value14993',
    'key49829': 'value70091',
    'key39418': 'value46511',
    'key90648': 'value35361',
    'key82347': 'value34312',
    'key92851': 'value98261',
    'key60725': 'value65076',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Charles Carlson',
    'address': '2214 Emily Station\nPort Michaelview, NY 03088',
    'text': 'Rule them well agreement thought. Few hold end radio now man minute black.\nToward decade agree benefit population. Film foreign physical green pick force resource since. Over ball management them.',
    'email': 'nlee@example.net',
    'phone_number': '5582943961',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stacey Ochoa',
    'Melissa Smith',
    'Rachel Williams',
    'Kathleen Scott',
    'Bradley Harris',
    'Angela Morris',
],
    'json': {
    'name': 'Dr. Danielle Johnson',
    'address': '3259 Buck Stream\nWest Tommy, MT 58129',
},
    'key38996': 'value53582',
    'key30747': 'value81814',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'April Church',
    'address': '978 Robinson Mission Apt. 591\nEast Juan, DE 46586',
    'text': 'Until speech order explain to financial wrong. Sport term national career check could. Building focus war half.',
    'email': 'hessgregory@example.com',
    'phone_number': '2357133783',
    'array_int_dynamic': [
    28062,
],
    'array_varchar_dynamic': [
    'James Cordova',
    'Linda Harrington',
    'Curtis Ingram',
    'Christy Robinson',
    'Tanya Richard',
    'Jacob Jones',
    'Rick Smith',
    'Shelly Obrien',
    'Veronica Mitchell',
    'Janet Cruz',
],
    'json': {
    'name': 'Angel Hall',
    'address': 'PSC 9194, Box 9871\nAPO AA 69654',
},
    'key73585': 'value6666',
    'key26049': 'value59821',
    'key61860': 'value27332',
    'key79420': 'value95628',
    'key3721': 'value43828',
    'key64075': 'value54900',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Kristin Mullins',
    'address': '1598 Sweeney Roads Apt. 238\nGalvanshire, IA 50633',
    'text': 'Like town article represent. Upon brother region whom. Money imagine look bed.\nElse name and government suffer. Expert these big million bag treat point oil. Natural difference measure couple.',
    'email': 'joel94@example.com',
    'phone_number': '626-384-4464x1233',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Charles Yates',
    'Jonathan Perez',
    'Katie Roth DVM',
    'William Kline',
    'Erika Hayes',
    'Kimberly Hayes',
    'Phillip Chen',
],
    'json': {
    'name': 'Larry Prince',
    'address': 'Unit 3495 Box 4423\nDPO AP 06262',
},
    'key86425': 'value64964',
    'key61598': 'value16519',
    'key84277': 'value40766',
    'key73896': 'value40912',
    'key37293': 'value78486',
    'key88647': 'value86354',
    'key95032': 'value21139',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jeffrey Jackson',
    'address': '96456 Jill Harbors\nBrendafort, TX 34740',
    'text': 'Hotel season beyond radio seven write former. Every song various kid.\nNo ahead of field. Draw talk month unit pay.',
    'email': 'fredwalls@example.org',
    'phone_number': '6668109170',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Benjamin',
    'Alyssa Long',
    'Joshua Estes',
    'Matthew Harmon',
    'Nathan Flowers',
    'Anthony Hickman',
    'Keith Bowen',
    'Julie Barnett',
],
    'json': {
    'name': 'Roger Garcia',
    'address': '0508 Darin Villages\nAmandafort, MA 12010',
},
    'key78646': 'value18206',
    'key55641': 'value9866',
    'key90806': 'value56657',
    'key63888': 'value36614',
    'key50763': 'value51637',
    'key25643': 'value81354',
    'key68825': 'value95240',
    'key38300': 'value50500',
    'key67057': 'value29017',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Holly Lopez',
    'address': '0105 Michelle Locks\nMichaelport, GU 46954',
    'text': 'Woman miss somebody. Election five year design blue build loss prevent.\nAccount figure at. Ahead his garden close yet.',
    'email': 'erik05@example.net',
    'phone_number': '001-473-329-9897x005',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Caitlin Flores',
    'Joseph Griffin',
    'James Campbell',
    'Eric Delacruz',
    'Mark Palmer',
],
    'json': {
    'name': 'Christopher Wright',
    'address': '739 Kari Isle\nNorth Nicole, AZ 68650',
},
    'key81525': 'value93007',
    'key89920': 'value70959',
    'key55319': 'value30583',
    'key58983': 'value83483',
    'key18058': 'value491',
    'key94574': 'value28050',
    'key78105': 'value6204',
    'key69092': 'value6789',
    'key87506': 'value95068',
    'key48850': 'value48965',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Preston Carter',
    'address': '41036 Jordan Lodge\nLake Sara, ND 21905',
    'text': 'Middle care else thus gas attorney. Court business even woman pattern a stuff.\nTown country different development hundred station program.',
    'email': 'wriley@example.org',
    'phone_number': '8206387060',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Taylor',
    'Jerome Cooke',
    'Alexander Sandoval',
    'Stephanie Walsh',
    'Katherine Miller',
    'Katherine Norris',
    'Jeffery Romero',
    'Anthony Moore',
    'Jennifer Byrd',
    'Kevin Sosa',
],
    'json': {
    'name': 'Joshua Lopez',
    'address': '8303 Angela Ridges Apt. 167\nJosephside, AL 89244',
},
    'key69215': 'value69297',
    'key2037': 'value57868',
    'key15093': 'value92307',
    'key5661': 'value11564',
    'key51612': 'value92059',
    'key43446': 'value48365',
    'key33992': 'value62602',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Lisa Shaw',
    'address': '774 Joseph Center\nNew Stevenside, WY 46486',
    'text': 'National exactly cover plan. Could national relationship hour record benefit.\nSmall claim keep mind point develop edge. Success account teacher couple. My size drop foreign.',
    'email': 'william85@example.org',
    'phone_number': '925-670-4132',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Webster',
    'Christina Miller',
    'Chad Sparks',
    'Tiffany Jackson MD',
    'Donald Perez',
],
    'json': {
    'name': 'Michael Watson',
    'address': '440 Castro Forge Suite 760\nWest Tanya, ID 99226',
},
    'key81468': 'value14927',
    'key26150': 'value76508',
    'key15316': 'value7315',
    'key35740': 'value59976',
    'key91937': 'value73928',
    'key75163': 'value64334',
    'key80641': 'value38819',
    'key85548': 'value20193',
    'key78430': 'value19211',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Andrew Buchanan',
    'address': '1620 Perkins Run\nJaniceborough, WY 55557',
    'text': 'Career consider family involve spend common. Action material page case better from. Worker knowledge art position above anything tell.',
    'email': 'qgraves@example.net',
    'phone_number': '+1-952-968-1176',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mindy Parker',
    'Jamie Stevenson',
    'Loretta Williams DDS',
    'Danielle Miller',
    'Maria Abbott',
],
    'json': {
    'name': 'Ellen Welch',
    'address': '22233 Jacqueline Flat\nMatabury, NV 21719',
},
    'key64324': 'value74968',
    'key95213': 'value37940',
    'key13831': 'value38923',
    'key97446': 'value43450',
    'key62040': 'value28085',
    'key74737': 'value73213',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Marie Rodriguez',
    'address': '77379 Jonathan Lock Apt. 485\nLake Annebury, VT 19112',
    'text': 'Section suddenly civil deep perform whether sell inside.',
    'email': 'davismeghan@example.org',
    'phone_number': '001-204-725-7321x0042',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Smith',
    'Amanda Phelps',
    'Karen Benitez',
    'Clifford Reed',
],
    'json': {
    'name': 'Deanna Smith',
    'address': '562 Rebecca Freeway Apt. 742\nSouth Michaelside, HI 92544',
},
    'key63824': 'value30451',
    'key49205': 'value99531',
    'key46283': 'value67299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Steven Mata',
    'address': 'PSC 1043, Box 6580\nAPO AP 22276',
    'text': 'Bad soon certainly become. Federal suggest raise source easy total.\nQuality sure soon cut modern.\nUsually really staff source without. Model listen career. Kitchen score president leave.',
    'email': 'stewartleonard@example.com',
    'phone_number': '3773665967',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Miller',
    'James Boyd',
],
    'json': {
    'name': 'Melissa Ortiz',
    'address': '07445 William Brook Apt. 312\nCatherinemouth, MO 25619',
},
    'key80219': 'value58545',
    'key95095': 'value54969',
    'key9899': 'value60920',
    'key37829': 'value48896',
    'key66710': 'value75058',
    'key84605': 'value16338',
    'key82532': 'value32366',
    'key587': 'value79733',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Karina Bridges',
    'address': '695 Arroyo Turnpike\nBrownshire, VI 88082',
    'text': 'Investment hot process admit public. Heart recognize ready that.\nCase red red trip interesting. Next bad weight option section boy sure somebody. Explain organization somebody scientist much.',
    'email': 'julia10@example.org',
    'phone_number': '985.699.2823x353',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Chad Faulkner',
    'Yvonne Simpson',
    'Tony Medina',
    'Melanie Davis',
    'Kimberly Mclaughlin',
    'Jordan Martinez',
],
    'json': {
    'name': 'Jeremy Nolan',
    'address': '91010 Sierra Extension\nSouth Patrickton, VA 46200',
},
    'key4246': 'value28094',
    'key56599': 'value74940',
    'key68615': 'value63630',
    'key67254': 'value15510',
    'key90798': 'value90731',
    'key66190': 'value32223',
    'key91617': 'value31193',
    'key95956': 'value38201',
    'key4621': 'value27705',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Sandra Smith',
    'address': '1601 Dominic Points Apt. 063\nAmberchester, WA 31979',
    'text': 'Early fast democratic factor morning. Pick address man system another series. Issue program dark she gas effect provide.\nProduct human story. Part total beat arrive water let.',
    'email': 'ztaylor@example.net',
    'phone_number': '863-541-5871x7223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Andre Henderson',
    'Benjamin Holt',
    'Elizabeth Christensen',
    'Chelsey Esparza',
    'Mark Washington',
    'Thomas Howard',
    'Amanda Craig',
    'Jeffery Scott',
    'Peggy Macdonald',
    'Kevin Robinson',
],
    'json': {
    'name': 'Timothy Phillips',
    'address': '56105 Katie Grove\nLake Blake, FM 32914',
},
    'key39544': 'value39773',
    'key91060': 'value7881',
    'key51276': 'value11031',
    'key96179': 'value69335',
    'key44274': 'value54643',
    'key98731': 'value35228',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Rachel Dalton',
    'address': '45795 John Terrace Apt. 720\nCherylborough, AL 56764',
    'text': 'Walk lot trial. Hospital exist reach customer. Fill usually region four stay happy happen.',
    'email': 'dyerrachel@example.net',
    'phone_number': '001-842-700-1031x64416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Hopkins',
    'Darryl Booth',
    'Brett Chambers',
    'Taylor Watkins',
    'Donald Garcia',
    'Rhonda Collins',
    'Eric James',
    'Christine Benson',
    'Teresa Thompson',
],
    'json': {
    'name': 'Scott Kelley',
    'address': '942 Henry Parks Suite 696\nNew Julia, GA 30111',
},
    'key10798': 'value36693',
    'key89185': 'value50567',
    'key25901': 'value1205',
    'key87906': 'value8600',
    'key57993': 'value399',
    'key76065': 'value53526',
    'key88522': 'value52707',
    'key762': 'value46960',
    'key80667': 'value41034',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Willie Ballard',
    'address': '477 Ellis Glen Apt. 863\nBurtonbury, NM 30584',
    'text': 'Themselves forget news compare ago positive race. Hear successful kid movie network others. Either network next box build stock.\nWhom writer your pretty body.',
    'email': 'amanda21@example.com',
    'phone_number': '607-894-1667',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Newton',
    'John Stone',
    'James Bell',
    'Brian Lee',
    'Ryan Peterson',
    'Johnny Hernandez',
    'Ricardo Miller',
    'Kathy Simpson',
    'Samantha Barnes',
    'Daniel Wilson MD',
],
    'json': {
    'name': 'Dean Mathis',
    'address': '3901 Reed Mountain\nStevensshire, NV 37791',
},
    'key41945': 'value96104',
    'key70016': 'value28438',
    'key30573': 'value33444',
    'key65787': 'value39201',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Brenda Clarke',
    'address': '030 James Lake Suite 230\nEast Ariana, NE 03325',
    'text': 'Career tough fund go because.\nSecurity determine majority prepare. High oil stock too painting.\nBecome minute commercial list best. Speech seem another win education.',
    'email': 'gilesariana@example.org',
    'phone_number': '900-413-1800x1647',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Moore',
    'Joann Stephenson',
    'Susan Carter',
    'Jonathan Olsen',
],
    'json': {
    'name': 'Christopher Dickerson',
    'address': '171 Thomas Island Suite 918\nSouth Scott, DE 48186',
},
    'key17269': 'value22646',
    'key22396': 'value70187',
    'key58442': 'value89010',
    'key17091': 'value80587',
    'key8893': 'value4495',
    'key69373': 'value5381',
    'key82254': 'value31481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Brian Carrillo',
    'address': '838 Robin Island\nNew Brandonshire, MP 72880',
    'text': 'Certainly remember court begin player walk respond. If very baby.',
    'email': 'oliverrobert@example.net',
    'phone_number': '(668)290-5444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Angela Perry',
],
    'json': {
    'name': 'Stacey Smith',
    'address': '36941 Walker Road Apt. 934\nSouth Jennifer, PW 73197',
},
    'key95341': 'value89915',
    'key85883': 'value79404',
    'key60546': 'value70950',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Jean Sanchez',
    'address': '16050 Jeffrey Lights\nLake William, FM 89313',
    'text': 'Set week air southern life sea response.\nMove official party statement. Condition risk move create that its pull political.',
    'email': 'johnrodriguez@example.org',
    'phone_number': '(485)913-5258x277',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Sparks',
    'Julie Bailey',
    'Justin Hanson',
],
    'json': {
    'name': 'Travis Long',
    'address': '45075 Thomas Mill\nNorth Bradleychester, ID 71688',
},
    'key21360': 'value52445',
    'key54728': 'value89837',
    'key74300': 'value17064',
    'key38763': 'value51981',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Julie Savage',
    'address': '7913 Brown Mission Apt. 084\nWest Brandonstad, MS 37771',
    'text': 'Teach ready two. Goal sing indeed smile figure. Real miss unit serious beautiful improve serve theory.\nBuilding scene sport. Position player last.',
    'email': 'jenniferkirk@example.org',
    'phone_number': '599.615.4535x619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Mccullough',
    'Dr. Cynthia Smith',
    'John Davis',
    'Todd Delgado',
    'Kimberly Walker',
    'Kristen Perry',
    'Faith Mccullough',
],
    'json': {
    'name': 'Amanda Bowers',
    'address': '77724 Tracey Throughway Apt. 427\nSouth Bradhaven, AZ 74320',
},
    'key63661': 'value90568',
    'key88800': 'value18487',
    'key55605': 'value48775',
    'key94143': 'value89437',
    'key93041': 'value17768',
    'key32956': 'value28540',
    'key2742': 'value61524',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Raymond Juarez',
    'address': '54749 Dunn Gardens\nEast Jason, MP 50177',
    'text': 'Before summer green capital. Pressure own month investment sure.\nWhatever past everybody entire treat machine. Down paper mean hot vote peace threat.',
    'email': 'martinezmax@example.com',
    'phone_number': '489.360.2563',
    'array_int_dynamic': [
    90123,
],
    'array_varchar_dynamic': [
    'Haley Bell',
    'Kayla Avila',
    'Andrew Garcia',
    'James Clements PhD',
    'Patrick Patrick',
    'Charles Matthews',
    'John Waters',
],
    'json': {
    'name': 'Heather Young',
    'address': '25193 Sampson Flat Apt. 301\nGonzalezborough, GU 26811',
},
    'key98388': 'value23635',
    'key73733': 'value34586',
    'key20520': 'value12788',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'George Ortiz',
    'address': '7648 Taylor Way\nNorth Kristopher, NC 51419',
    'text': 'His professional interview form concern. Organization wife record born hand far.\nRadio position himself system appear mention I. Your line need sound really. Quite page create.',
    'email': 'boothjames@example.com',
    'phone_number': '985.895.2607',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Caroline Johnson',
    'Stephanie Flores',
],
    'json': {
    'name': 'Jodi Goodman',
    'address': '18596 Tonya Lodge Suite 672\nEast Kimmouth, UT 79033',
},
    'key70281': 'value12613',
    'key89444': 'value20800',
    'key11329': 'value56753',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Russell Miller',
    'address': '943 Keith Land\nSouth Nicholas, MD 91158',
    'text': 'Garden sound red create anything question whether. Box song prove heart.\nLet table tree inside system method itself. Present more foreign.',
    'email': 'daughertypamela@example.org',
    'phone_number': '849-363-1952x253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Arnold',
    'Robert Juarez',
    'Ana Hill',
    'Jennifer Miller',
    'Scott Patterson',
    'Dr. Tiffany Lewis DDS',
    'Kelsey Gonzalez',
    'Emily Williams',
    'Adriana Duke',
],
    'json': {
    'name': 'Rebecca Allen',
    'address': '188 Amanda Valley\nSouth Donaldfort, FL 44786',
},
    'key38077': 'value61830',
    'key22456': 'value72432',
    'key96893': 'value60637',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jillian Turner',
    'address': '506 Archer Cove\nNew Jamieborough, OK 53914',
    'text': 'Note history against issue room detail both sister. Value when put number central. Little blood early affect thus easy fear.',
    'email': 'amberturner@example.com',
    'phone_number': '(425)386-4724x2056',
    'array_int_dynamic': [
    23250,
],
    'array_varchar_dynamic': [
    'Mary Rosales',
    'Mitchell Burke',
    'Michelle Moreno',
    'James Mejia',
    'Deborah Henderson',
],
    'json': {
    'name': 'Melissa Lawrence',
    'address': '2936 Victor Ports Apt. 565\nNew Williamstad, AZ 10650',
},
    'key17868': 'value44921',
    'key33165': 'value95630',
    'key38710': 'value42193',
    'key4650': 'value80540',
    'key22147': 'value54565',
    'key22980': 'value94585',
    'key46602': 'value21318',
    'key3726': 'value56333',
    'key56536': 'value67321',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Laurie Day',
    'address': 'PSC 1542, Box 6756\nAPO AA 76014',
    'text': 'Understand hold base where suggest. Doctor card catch such training realize.\nSuffer suffer really book month woman wait suggest.\nCut tax own region. Sound second garden.',
    'email': 'karen78@example.org',
    'phone_number': '(962)769-3180',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Green DDS',
    'Alyssa Jackson',
    'Christopher Clark',
    'Deborah Thomas',
    'Stephen Johnson',
    'Dana Campbell',
    'John Anderson',
],
    'json': {
    'name': 'Charles Adams',
    'address': '30932 Wilkins Points\nWest Donald, WY 76044',
},
    'key2584': 'value49511',
    'key87889': 'value25349',
    'key2966': 'value47901',
    'key22548': 'value24523',
    'key54920': 'value18014',
    'key76535': 'value48272',
    'key85189': 'value7797',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Kim Williams',
    'address': '6780 Sarah Views\nGarnerville, CA 67867',
    'text': 'Cell include newspaper affect. Remember drug whole major agree. South cut through staff pull down information.',
    'email': 'smithamber@example.net',
    'phone_number': '218.451.7476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Scott Hood',
    'Lori Davis',
],
    'json': {
    'name': 'Miguel Johnston',
    'address': '842 Shane Shoal Suite 445\nNew Nicole, MT 07753',
},
    'key62308': 'value60',
    'key92088': 'value11578',
    'key16324': 'value26574',
    'key60690': 'value43967',
    'key74281': 'value45461',
    'key73558': 'value116',
    'key38882': 'value15387',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Kelsey Phillips',
    'address': '7255 Joshua Manor Apt. 373\nNorth Michealberg, UT 67185',
    'text': 'Base Congress that it loss magazine. Some occur hour population minute above including.\nSite look continue. Investment such yeah improve about others. Hot job cell suffer determine only voice four.',
    'email': 'thomasschneider@example.org',
    'phone_number': '324.576.0221x4186',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Philip Frye',
    'Mariah Thomas',
    'Anna Glover',
    'Todd Young',
    'Bryan Bennett',
    'Colleen Silva',
],
    'json': {
    'name': 'Kevin Rogers',
    'address': '58129 Davis Stream Suite 474\nPort Christopherchester, AK 52981',
},
    'key41460': 'value46572',
    'key70252': 'value60388',
    'key8245': 'value87815',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Amy Perkins',
    'address': '770 Curry Via Suite 165\nSouth Melindaburgh, SC 92927',
    'text': 'Woman morning month community. Where million focus country cost film.\nHead pressure necessary other then city green. Each still better pressure. Section commercial easy others side security remember.',
    'email': 'scott08@example.com',
    'phone_number': '4457677958',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kristina Rice',
    'Jessica Campbell',
    'Valerie Phillips',
    'Brandy Perez',
    'Carly Obrien',
    'Mr. Michael Ross MD',
    'Amanda Wallace',
    'William Dawson',
    'Daniel Smith',
],
    'json': {
    'name': 'Gary Dean',
    'address': '67334 Reed Roads\nEast Shane, IL 50609',
},
    'key78290': 'value34022',
    'key76810': 'value12885',
    'key83946': 'value11437',
    'key59800': 'value62267',
    'key40598': 'value47211',
    'key55317': 'value93953',
    'key6413': 'value50188',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Amanda Davies',
    'address': '5632 Smith Plaza\nWhitestad, PW 78754',
    'text': 'Bring get bag side home. At bill training personal record sound.\nPay language those entire coach hit moment.\nLive coach most tough tax group. Himself remember attorney important.',
    'email': 'donna79@example.net',
    'phone_number': '(448)771-7881x3081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Rhonda Hernandez',
],
    'json': {
    'name': 'Seth Hill',
    'address': 'PSC 9449, Box 8635\nAPO AA 72063',
},
    'key63459': 'value18007',
    'key49074': 'value58518',
    'key72504': 'value60003',
    'key210': 'value27467',
    'key68256': 'value19280',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Kurt Black',
    'address': '835 Anderson Manors Apt. 651\nDarrenland, NE 97268',
    'text': 'Affect before stand environment establish send federal information. Main down should section professional anyone idea. Human life list but central.',
    'email': 'brian56@example.com',
    'phone_number': '(799)804-6902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brian Rose',
    'Jesse Thompson',
    'Willie Price',
    'Sabrina Lucero',
    'Robert Lee',
],
    'json': {
    'name': 'George Roberson',
    'address': '295 Samuel Spurs\nLawsonhaven, WI 69906',
},
    'key20029': 'value69825',
    'key2573': 'value23142',
    'key89602': 'value10516',
    'key39421': 'value98772',
    'key37576': 'value65991',
    'key40653': 'value85454',
    'key24272': 'value2922',
    'key54196': 'value10962',
    'key89214': 'value94672',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Alison Johnson',
    'address': '732 Jennifer Locks Suite 833\nNew Elizabethland, WI 43077',
    'text': 'Appear religious such style sign fall rule. Owner tree particularly girl could herself region impact. Say with in quality.',
    'email': 'rgonzalez@example.org',
    'phone_number': '001-717-637-1054x23885',
    'array_int_dynamic': [
    18469,
],
    'array_varchar_dynamic': [
    'Carlos Williams',
    'Brian Mercado',
    'William Simmons',
    'Eileen Knapp',
    'Monica Ibarra',
    'Alicia Oliver',
    'Jon Howard',
],
    'json': {
    'name': 'Robert Berg',
    'address': '165 John Loaf\nSouth Lawrence, TN 87105',
},
    'key80895': 'value60313',
    'key41926': 'value64048',
    'key52170': 'value25563',
    'key27154': 'value11732',
    'key49846': 'value70956',
    'key37809': 'value52223',
    'key55285': 'value74884',
    'key5040': 'value60675',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Michele Thomas',
    'address': '0905 Patty Extension\nNew Abigailview, SC 25238',
    'text': 'Production already threat employee politics significant yard. Fear hair hope agree manager reach deal. Others impact sometimes within play answer that seat.',
    'email': 'patrick53@example.net',
    'phone_number': '802.754.2063',
    'array_int_dynamic': [
    36744,
],
    'array_varchar_dynamic': [
    'Joshua Patterson',
    'Peter Rios',
    'John Smith',
],
    'json': {
    'name': 'Curtis Scott',
    'address': '359 Tara Point Suite 444\nNew Martinmouth, MD 83790',
},
    'key78048': 'value88993',
    'key75797': 'value91483',
    'key63184': 'value46407',
    'key96454': 'value9714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Mrs. Veronica Oneal MD',
    'address': '61375 Walter Mills\nNorth Travisshire, SC 50963',
    'text': 'Customer change huge. Writer each subject. Reach to nor national property arrive vote.\nOr writer throw.\nShe alone lead level forget ok truth. Laugh front none property.',
    'email': 'harrygarcia@example.org',
    'phone_number': '636.392.7282',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brian Buckley',
    'Stephen Murphy',
    'Cristina Stewart',
    'Derrick Allen',
    'Joseph Reese',
    'Crystal Ingram',
],
    'json': {
    'name': 'Diane Jones',
    'address': '16276 Hurley Brooks\nNew Mckenzieview, GA 01399',
},
    'key99674': 'value29743',
    'key41977': 'value8477',
    'key40803': 'value2025',
    'key82549': 'value8341',
    'key1511': 'value97049',
    'key91251': 'value93401',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jeffrey Brown',
    'address': '6122 David Estate Apt. 512\nPort Sarah, KS 10833',
    'text': 'Condition wish but six generation science. Loss condition up road give. Worker skin poor news method agreement.',
    'email': 'kristenjackson@example.com',
    'phone_number': '001-706-628-4104x85961',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Oscar Downs',
    'Dana Finley',
    'Michelle Thompson',
    'Paul Martinez',
    'Michael Fernandez',
    'Tracy Gonzalez MD',
],
    'json': {
    'name': 'Dennis Christian',
    'address': '713 Lamb Landing Apt. 296\nNew Bryanville, IN 70486',
},
    'key41865': 'value71712',
    'key49213': 'value90060',
    'key28483': 'value27835',
    'key4322': 'value17750',
    'key34256': 'value87330',
    'key22090': 'value5185',
    'key24207': 'value25404',
    'key49171': 'value54063',
    'key64916': 'value56830',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'William Jones',
    'address': '96002 King Unions Apt. 135\nHodgeberg, AS 18541',
    'text': 'Discussion list like management wonder upon lose whose. Spring consider magazine less.\nPull something model again artist. Good build run attorney. Imagine last attorney decade.',
    'email': 'daniellemorgan@example.net',
    'phone_number': '2047539261',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Molly Kelley',
    'Terri Williams',
    'Brianna Sloan',
    'Julie Ramos',
    'Henry Donovan',
    'Douglas Miller',
],
    'json': {
    'name': 'Rachel Nichols',
    'address': '46243 Brian Creek Apt. 973\nBuckview, KS 00973',
},
    'key51512': 'value92581',
    'key32639': 'value43091',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Brian Richardson',
    'address': '542 Alexander Camp\nNew Kristenville, OH 25442',
    'text': 'Source campaign eight here resource. Laugh issue argue since professor security myself. Similar call morning crime.',
    'email': 'tammycarter@example.com',
    'phone_number': '202-406-2033',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Garza',
    'Yolanda Stokes',
    'Theresa Bennett',
    'Jason Koch',
    'Daniel Campbell',
    'Joseph Richards',
    'Zoe Roberts',
    'Amanda Gibson',
    'Eric Garcia',
],
    'json': {
    'name': 'Hayley Mcmillan',
    'address': '144 John Spur\nLake Gabriel, VA 32669',
},
    'key6801': 'value70409',
    'key17984': 'value24643',
    'key77904': 'value35144',
    'key9292': 'value5544',
    'key79001': 'value66603',
    'key53212': 'value79568',
    'key6216': 'value72937',
    'key46395': 'value18863',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Miss Erica Jarvis',
    'address': '51093 Patrick Drives Apt. 070\nMichaelport, OH 92980',
    'text': 'Project before including. Must like while.\nArticle happy chance. Yard themselves my.',
    'email': 'lambertemily@example.org',
    'phone_number': '+1-771-656-8029x089',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sierra Smith',
    'Joshua Smith',
    'Jennifer Bryant',
    'David Garcia',
],
    'json': {
    'name': 'Bianca Jones',
    'address': '3904 Justin Forks\nBrownberg, VA 93134',
},
    'key8165': 'value51149',
    'key20572': 'value60590',
    'key63419': 'value92925',
    'key2949': 'value92202',
    'key48291': 'value3764',
    'key48006': 'value6608',
    'key54833': 'value90779',
    'key94955': 'value63693',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Traci Brown',
    'address': '96820 Browning Vista Suite 481\nTranfort, TN 84782',
    'text': 'East then region other policy employee personal. Model meeting piece bad certain paper man send.\nChance mother threat lead address hard before. Admit several it television good thousand sit.',
    'email': 'kayla56@example.com',
    'phone_number': '4658200117',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Vargas',
    'Stacey Stephens',
    'Sarah Lawson',
],
    'json': {
    'name': 'Tyler Lee',
    'address': '43904 Stanton Shoals\nMercadohaven, AK 71245',
},
    'key54833': 'value25498',
    'key54277': 'value23424',
    'key13104': 'value97378',
    'key1701': 'value5006',
    'key54595': 'value15500',
    'key57691': 'value84552',
    'key66421': 'value29342',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Brittney Reyes',
    'address': '17196 Sarah Park Suite 865\nEast Jimmy, KS 32458',
    'text': 'Cell exist Mrs quality owner. Raise toward yard still. Friend herself my heavy. Available level situation.',
    'email': 'haynesmichael@example.net',
    'phone_number': '+1-681-419-0126x7552',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jason Brown',
],
    'json': {
    'name': 'Michael Morris',
    'address': '1240 Anne Highway\nNorrisfurt, KY 82727',
},
    'key64704': 'value6598',
    'key37273': 'value76278',
    'key39892': 'value69543',
    'key35733': 'value8136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Amy Russell',
    'address': '59559 Moore Centers Suite 307\nLake Keithmouth, PA 92540',
    'text': 'Individual work civil near everybody. Record road star.\nWhom society write leader group. Travel scientist moment hand north.\nEducation above trade everyone cost suggest arrive. Industry window court.',
    'email': 'stephen34@example.net',
    'phone_number': '+1-819-489-2161x57822',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Anderson',
    'Lawrence Perry',
    'William Collier',
    'Jenny Andrade',
    'Tammy Lewis',
],
    'json': {
    'name': 'David Cook',
    'address': '673 Waters Burgs\nCollinsside, WA 12254',
},
    'key76865': 'value4236',
    'key1715': 'value98980',
    'key64481': 'value88610',
    'key34622': 'value86246',
    'key77867': 'value4071',
    'key83856': 'value56271',
    'key2471': 'value30846',
    'key71756': 'value64212',
    'key19675': 'value31068',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Heather Hall',
    'address': '1824 Gonzalez Mill Suite 133\nProctorton, DC 50819',
    'text': 'Note add but. Never style manager deal either.\nCard we treatment street recognize prepare both. Heart power deep. Rest if attack or condition day land agency.',
    'email': 'jrodriguez@example.org',
    'phone_number': '319-948-3669',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Rosales',
    'Robert Sosa',
    'Carrie Hernandez',
    'Anthony Kennedy',
    'Scott Evans',
    'Richard Townsend',
    'Julia Garza',
    'Margaret Williams',
    'Ashley Howard',
    'Sean Wilson',
],
    'json': {
    'name': 'Michael Gross',
    'address': '54790 Shields Springs\nNorth John, NJ 31025',
},
    'key64066': 'value65558',
    'key50138': 'value74902',
    'key47378': 'value87310',
    'key36449': 'value11775',
    'key91861': 'value29566',
    'key15844': 'value94674',
    'key70739': 'value85949',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Cindy Clark',
    'address': '390 Gould Inlet Suite 150\nPort Alexisland, CA 11948',
    'text': 'Hospital child main. People individual claim huge soldier general. Likely discuss trouble among happy no vote.',
    'email': 'ericacortez@example.com',
    'phone_number': '491-481-4859',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mike Coleman',
    'Andrew Waters',
    'Peter Herrera',
    'Cynthia Little',
    'Tiffany Anderson',
    'William Mills',
    'David Garner',
    'Tracy Turner',
],
    'json': {
    'name': 'Sarah Clark',
    'address': '2263 Rocha Crest Apt. 063\nSouth Warren, WY 36320',
},
    'key7539': 'value78842',
    'key75485': 'value65362',
    'key24402': 'value52991',
    'key89991': 'value94069',
    'key69248': 'value22955',
    'key29528': 'value50932',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Kevin Knapp',
    'address': '179 Bryan Pine Suite 054\nGarciamouth, IA 67235',
    'text': 'Dark gun significant finally ready. Various true me within his mouth white.\nAll cost send hear late. Her daughter my hundred throw. Must now fish.',
    'email': 'ujohnson@example.com',
    'phone_number': '854-271-5716',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Linda Brown',
    'Melissa Coleman',
    'Terri Clark',
    'Linda Harvey',
    'Emily Avila',
],
    'json': {
    'name': 'Brittany Lopez',
    'address': 'USNV Berry\nFPO AA 57081',
},
    'key14626': 'value10522',
    'key58345': 'value22815',
    'key29580': 'value93341',
    'key41276': 'value22419',
    'key65374': 'value89820',
    'key94171': 'value9008',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Michael Williams',
    'address': 'PSC 0895, Box 5554\nAPO AE 51365',
    'text': 'Color baby west better. Follow site security must.\nVisit man stuff in between society. News around house third quality as.\nDescribe have everybody actually.',
    'email': 'rogersjohn@example.net',
    'phone_number': '(716)767-0921x41591',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Diane Davis',
    'Rebecca Fox',
    'Kimberly Wilson',
    'Lori Wilson',
    'Yolanda Warren',
    'Daniel Charles',
    'Sheryl Santos',
    'Emily Wilson',
],
    'json': {
    'name': 'Whitney Owens',
    'address': 'USNV Rivera\nFPO AA 11162',
},
    'key84970': 'value2840',
    'key12842': 'value97287',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Heather Thompson',
    'address': '44207 Doyle Keys\nSouth Harold, NM 24936',
    'text': 'Base project create produce floor. Every into affect debate number. Head although serious.',
    'email': 'mjennings@example.net',
    'phone_number': '493.513.1146x79027',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brianna Lewis',
    'Paige Hill',
    'Kyle Patrick',
    'Ryan Ramirez',
    'Dawn Morgan',
    'Stephanie Oliver',
    'Jacob Dillon',
],
    'json': {
    'name': 'Sean Hill',
    'address': '8083 Ferguson Spurs Apt. 434\nEast Tony, NE 42435',
},
    'key70956': 'value6838',
    'key6388': 'value89699',
    'key33441': 'value32615',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Michael Kelly',
    'address': '95739 Samuel Shores Suite 496\nEast Maria, WA 26843',
    'text': 'Consider must imagine fact like. Congress system party fast. Back behind think action character.\nGuess yeah live ever. Much much follow which budget off.',
    'email': 'jenningsjohn@example.net',
    'phone_number': '237.787.1998x046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tricia Hoover',
    'Nicholas Whitaker',
    'Diane Ward',
],
    'json': {
    'name': 'Stephen Newman',
    'address': '5387 Martinez Cliff\nColinmouth, CT 34458',
},
    'key50452': 'value55543',
    'key32161': 'value16747',
    'key9038': 'value71169',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Katie Davis',
    'address': '9618 Fernandez Views\nPort Kathleenbury, MD 85289',
    'text': 'Four whatever most involve property. Out item home rule result rich. Treatment story energy national offer on near believe.',
    'email': 'kgarza@example.org',
    'phone_number': '(472)995-1845',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Bailey',
    'Marissa Gonzalez',
    'Jessica Norton',
    'Gina Mcmahon',
    'Monica Bright',
    'Cynthia Moore',
    'Holly Hodges',
    'Shannon Potter',
    'Holly Graham',
    'Kevin Morris',
],
    'json': {
    'name': 'Leslie Riley',
    'address': '3081 Tammy Stream\nEast Christopher, NJ 25700',
},
    'key15681': 'value38616',
    'key27113': 'value92',
    'key80604': 'value2637',
    'key53701': 'value1977',
    'key45888': 'value94169',
    'key53451': 'value81669',
    'key19643': 'value38561',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Karen Hoffman',
    'address': 'Unit 8515 Box 5288\nDPO AE 19411',
    'text': 'Such race should admit another need. Teach cause arm.\nEvening effect major. Activity without suddenly radio.',
    'email': 'kirsten17@example.net',
    'phone_number': '+1-765-686-3604x016',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Orozco',
],
    'json': {
    'name': 'Julie Soto',
    'address': '99516 Richmond Springs Apt. 251\nWest Lucas, HI 97639',
},
    'key35596': 'value33285',
    'key1119': 'value54984',
    'key8657': 'value91995',
    'key25392': 'value22419',
    'key33234': 'value67739',
    'key65099': 'value46390',
    'key89670': 'value91929',
    'key48086': 'value39042',
    'key24537': 'value65472',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Lindsay Glenn',
    'address': '124 Bell Pine Suite 244\nSamanthaside, MS 03766',
    'text': 'Easy analysis but race Mrs note sea. Time public your receive.\nCondition financial law turn quite security. Maybe ago parent range. Pay drug simple can.',
    'email': 'gilmoreanthony@example.com',
    'phone_number': '655-649-7826x608',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marcia Rosario',
],
    'json': {
    'name': 'David Hendrix',
    'address': '658 Haynes Village\nRobinport, HI 32971',
},
    'key77108': 'value49993',
    'key35164': 'value56592',
    'key91429': 'value36626',
    'key93201': 'value27013',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Sarah Singh',
    'address': '1727 Amy Parks Apt. 035\nJenniferside, KY 07596',
    'text': 'Health each yet future cause statement. During value return low draw notice indicate. Born prepare themselves learn.',
    'email': 'seanthompson@example.com',
    'phone_number': '+1-808-364-1912x62720',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Zimmerman',
    'Andrea Gordon',
    'Anthony Foster',
    'Stacey Davis',
],
    'json': {
    'name': 'Eugene Johnson',
    'address': '346 Samantha Glen Suite 937\nChelseashire, FM 45012',
},
    'key45622': 'value38915',
    'key8084': 'value15780',
    'key82330': 'value68668',
    'key73927': 'value16837',
    'key13700': 'value7707',
    'key7052': 'value27819',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jeffrey Wu',
    'address': '924 Wendy Points\nDiazburgh, LA 90117',
    'text': 'Billion from six sound. Fact possible best take may stand.\nUpon exist material control. Court beyond speak practice drug inside security. Reach able maybe scene also.',
    'email': 'yeseniafisher@example.net',
    'phone_number': '001-527-687-9853x27874',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Kelly',
    'Melissa Gibson',
],
    'json': {
    'name': 'Felicia Campbell',
    'address': '43196 Melody Springs\nMichaelside, NM 09907',
},
    'key74729': 'value35108',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Stephanie Simon',
    'address': '1167 Bradley Track\nPort Sarahchester, IA 82832',
    'text': 'Sound coach I to. Whom art table raise father he discussion.\nView since control threat attorney. Suffer price single game office do spring.',
    'email': 'fodonnell@example.com',
    'phone_number': '001-995-543-5162x3775',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sophia Henson',
    'Tina Malone',
    'Tina Wolfe',
    'Jason Fitzgerald',
    'Billy Delgado',
    'Dillon Roberts',
    'Maria Lee',
    'Timothy Thompson',
    'Laura Lewis',
],
    'json': {
    'name': 'Sandra Donaldson',
    'address': '29642 John Row\nEast Rogerberg, WI 25296',
},
    'key85220': 'value17502',
    'key71144': 'value60440',
    'key71076': 'value50620',
    'key69875': 'value28972',
    'key41496': 'value37182',
    'key5787': 'value4144',
    'key72304': 'value71395',
    'key99526': 'value95884',
    'key24604': 'value57160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Wendy Marquez',
    'address': 'USNS Bush\nFPO AP 37996',
    'text': 'Suddenly ahead west ready evidence practice lawyer.\nMoment letter western rule customer. Keep also firm serious.\nConsumer seem cultural reach reduce beat speech.',
    'email': 'rebeccaferguson@example.com',
    'phone_number': '001-324-409-4691x02452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Oconnor',
    'Nicole Dougherty',
    'Courtney Vazquez',
    'David Thomas',
    'David Wilson',
    'Mary Garcia',
    'Crystal Henderson',
    'Kevin Tran',
],
    'json': {
    'name': 'Nathan Garrett',
    'address': '593 Christopher Ridges Suite 388\nSouth Douglas, NM 21464',
},
    'key1007': 'value29190',
    'key40273': 'value62153',
    'key40343': 'value35129',
    'key35269': 'value43905',
    'key12801': 'value49337',
    'key8722': 'value65756',
    'key35068': 'value15752',
    'key50682': 'value58916',
    'key47310': 'value3154',
    'key26760': 'value27614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Anthony Parker',
    'address': '3992 Joshua Key\nLake Matthew, KY 55299',
    'text': 'None picture audience marriage property organization. Include decade everybody white region. Moment manage notice him. Fly population space fear else.',
    'email': 'elizabethharding@example.net',
    'phone_number': '(666)565-0379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Diana Walters',
    'Christopher Gonzales',
    'Kristina Cooley',
    'Andrew Oconnell',
    'Autumn Peters',
    'Ronald Smith',
    'Deanna Beck',
    'Amber Gonzalez',
    'Anna Hughes',
    'Zachary Trujillo',
],
    'json': {
    'name': 'Eric Pierce',
    'address': '2312 Baker Flats Suite 475\nNicolebury, VI 91648',
},
    'key17633': 'value7283',
    'key58376': 'value91347',
    'key99289': 'value13154',
    'key42110': 'value5297',
    'key85747': 'value41714',
    'key51681': 'value55025',
    'key78421': 'value4537',
    'key42320': 'value2491',
    'key6186': 'value55537',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Elizabeth Ortiz',
    'address': '472 Jacqueline Crest\nCameronbury, PR 21124',
    'text': 'Middle toward possible each. Themselves my note foot art only human. Avoid especially Congress this.\nCommunity get draw national stage. Sea better reason mean weight. Dark buy which call.',
    'email': 'patricia74@example.com',
    'phone_number': '361.667.2089x9529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Richard Lee',
    'Louis Baker',
    'Jonathan Thompson',
    'Austin Bonilla',
    'Roger Kaufman',
],
    'json': {
    'name': 'Kara Woods',
    'address': '18184 Deanna Cliffs Suite 629\nPenningtonland, TX 18536',
},
    'key69232': 'value24711',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Patrick Duarte',
    'address': '68997 Young Fields\nJoshualand, VI 22665',
    'text': 'Interest family throughout not music. Forward not skin data answer. Eat page seem.',
    'email': 'wilkinsjacob@example.org',
    'phone_number': '998.828.5606x47934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Steve White',
    'Katie Jackson',
    'Renee Watson',
    'Nicole Williams',
    'Anthony Thompson',
    'Meredith Jones',
    'Terri Richardson',
],
    'json': {
    'name': 'Jennifer Lowery',
    'address': '065 Victoria Brooks Apt. 570\nLaurenport, TX 58792',
},
    'key75535': 'value16768',
    'key38116': 'value38626',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Michael Russell',
    'address': '01577 Michael Oval\nEast Lynn, OK 53928',
    'text': 'Machine control wait. Data court tell message physical tax.\nMuch record student approach.\nPhone approach age artist far. Shoulder include final huge sure. Democratic son loss list dark.',
    'email': 'johncarter@example.net',
    'phone_number': '(956)757-3389',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brian Perez',
    'Jessica Miller',
    'Patricia Rocha',
    'Brianna Daniels',
    'Anthony Scott',
    'Tiffany Luna',
    'Richard Martinez',
],
    'json': {
    'name': 'Alexander Griffin',
    'address': '23822 Taylor Manor\nSantanahaven, NH 64740',
},
    'key76320': 'value49584',
    'key67533': 'value58776',
    'key43995': 'value67695',
    'key39053': 'value27299',
    'key26718': 'value38731',
    'key81834': 'value32677',
    'key87147': 'value47108',
    'key74954': 'value73567',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Amanda Fritz',
    'address': '152 Joseph Isle Apt. 252\nBraunberg, NJ 97731',
    'text': 'Attention main large shake can rise beat wind. Evidence site another image. Box agreement toward fish.\nReturn special blue trouble. Almost blue how involve fast career. Light onto Mr specific.',
    'email': 'wendy55@example.org',
    'phone_number': '872-737-3750',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Cameron',
    'Steven Christensen',
    'Sharon Rodriguez',
    'Shannon Clark',
    'Kimberly White',
    'Denise Williams',
    'Jeffrey Tate',
],
    'json': {
    'name': 'Keith Wood',
    'address': '24232 Amanda Plain\nLake Sandrafurt, KS 72513',
},
    'key22285': 'value1921',
    'key88501': 'value49388',
    'key79741': 'value64146',
    'key97907': 'value5272',
    'key70012': 'value29698',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Meghan Brewer',
    'address': '9799 Zachary Glens\nWest Andrewside, MT 60642',
    'text': 'Better position fall college book response. Send money live special.\nBenefit bit state popular meet. Choose ability wonder fly.\nMost group drop lot onto if.',
    'email': 'bethanysmith@example.com',
    'phone_number': '369.306.9425x3738',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Williams',
    'Mark Nguyen',
    'Ana Allison',
    'Kenneth Archer',
    'Clayton Waters',
],
    'json': {
    'name': 'Garrett Griffin',
    'address': '4558 Moore Oval\nBakermouth, MD 18486',
},
    'key92393': 'value56612',
    'key68640': 'value56798',
    'key22561': 'value89097',
    'key50091': 'value45208',
    'key82878': 'value25279',
    'key75950': 'value76769',
    'key75185': 'value67636',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Rebecca Webb',
    'address': '6007 Kim Stravenue\nEdwardfurt, GA 07851',
    'text': 'State try level some small consumer table perform. Never cell resource. Sign wife between state network.',
    'email': 'douglaskristin@example.net',
    'phone_number': '982.921.4651x6220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Miguel Edwards',
    'Bonnie Ray',
    'Brandon James',
    'Edward Snow',
    'Courtney Dennis',
    'Natalie Wagner',
    'Hector Jones',
    'Michelle Stafford',
    'Jacob Espinoza',
],
    'json': {
    'name': 'Cameron Mcintyre',
    'address': '257 Riley Field\nPort Kylie, OH 92201',
},
    'key31858': 'value73679',
    'key62432': 'value58747',
    'key51786': 'value21103',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Nicole Ramirez',
    'address': '8208 Laura Divide\nSouth Angela, AK 46775',
    'text': 'Great statement prove wind. Down again yet picture thank success interview. It other create when nature point increase red.\nAway ball analysis. Total thought my radio try realize.',
    'email': 'ztrevino@example.org',
    'phone_number': '903.251.5877x30919',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Hughes',
    'Wesley Roth',
],
    'json': {
    'name': 'Carol Wong',
    'address': '008 Jackson Valleys Apt. 277\nNew Mary, WI 29163',
},
    'key70705': 'value55638',
    'key73871': 'value79032',
    'key70303': 'value57496',
    'key45977': 'value40156',
    'key68755': 'value3380',
    'key40796': 'value78869',
    'key45337': 'value41368',
    'key78931': 'value74801',
    'key44603': 'value42595',
    'key15536': 'value45064',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Cory Dawson',
    'address': '3740 Daniel Expressway Apt. 883\nWest Jamesborough, SC 88199',
    'text': 'Heart side heart fire. Develop organization throughout method ground fill use. Over bag last deal like loss.',
    'email': 'jamesruiz@example.org',
    'phone_number': '600-940-7899',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Taylor',
    'Cheryl Obrien',
    'Brandon Murphy',
    'Jennifer Cook',
    'Jason Chavez',
],
    'json': {
    'name': 'Nicole Tyler',
    'address': '9976 Angela Isle\nNew Danahaven, MA 76571',
},
    'key57644': 'value85922',
    'key83601': 'value15598',
    'key95445': 'value10652',
    'key33351': 'value80894',
    'key29045': 'value71088',
    'key92814': 'value54343',
    'key6949': 'value69055',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Michael Jones',
    'address': '09105 Karen Trail\nLake Paul, NJ 01395',
    'text': 'Under fly indeed gun clear war. Federal enough bank street information believe form.\nHundred protect hold treat. Thank despite light agree beautiful first tell.',
    'email': 'michellehanson@example.com',
    'phone_number': '+1-612-976-1013x542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Jackson',
    'Tony Heath',
    'Dawn Lawson',
    'Denise Garcia',
    'Adam Bernard',
],
    'json': {
    'name': 'Michael Ellis',
    'address': '2408 Jonathan Neck Suite 979\nLake John, CO 16240',
},
    'key25874': 'value80027',
    'key87701': 'value85326',
    'key90171': 'value86906',
    'key15430': 'value44430',
    'key5358': 'value32453',
    'key73744': 'value24612',
    'key41796': 'value51269',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'David Montgomery',
    'address': '090 Wood Shoals\nPort Mariastad, MP 13792',
    'text': 'Less near chair star. Similar exist country recent onto.\nYeah whole house. Key your song hope any. Call particular determine according democratic clearly model remember.',
    'email': 'ycannon@example.net',
    'phone_number': '946.732.5686x806',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Rowe',
    'Brian Hobbs',
    'Ronald Rivers',
    'Michael Salas',
    'Darlene Barton',
    'Anne Osborn',
],
    'json': {
    'name': 'Robert Perez',
    'address': '00791 Sarah Prairie\nSouth Isaiah, GU 24535',
},
    'key1350': 'value18772',
    'key10010': 'value37026',
    'key55199': 'value18278',
    'key82572': 'value26889',
    'key56142': 'value64222',
    'key17915': 'value52684',
    'key30334': 'value1882',
    'key73661': 'value29759',
    'key54142': 'value66137',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Oscar Martinez DDS',
    'address': '9008 Wright Viaduct\nNorth Joshuaborough, NY 58307',
    'text': 'Future surface section herself indeed industry side. Unit human money check eight along.\nOrder understand hot eat. Boy might sometimes should. Feeling themselves thus effort thank single his.',
    'email': 'norrissarah@example.org',
    'phone_number': '+1-668-424-5092x341',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Michael Miller',
],
    'json': {
    'name': 'Theresa Stewart',
    'address': '6675 Gray Trail Suite 231\nEast Raymondville, MA 92047',
},
    'key5359': 'value70017',
    'key49352': 'value71974',
    'key23399': 'value94883',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Samuel Parker',
    'address': '7560 Victor Mountains Apt. 980\nKruegerport, VA 36652',
    'text': 'Around industry continue agency. Provide who continue song sort. Drug natural pretty prepare popular be whatever. Financial memory doctor training appear attack any.',
    'email': 'qsmith@example.org',
    'phone_number': '549-616-9600x1145',
    'array_int_dynamic': [
    383,
],
    'array_varchar_dynamic': [
    'Samuel Alvarado',
    'Joseph Davis',
    'Brian Adams',
    'Laura Chang',
    'Debbie Powell',
],
    'json': {
    'name': 'Denise Kelly',
    'address': '764 Brown Manors Apt. 175\nSouth Michael, PR 85478',
},
    'key7920': 'value67466',
    'key51424': 'value72829',
    'key20338': 'value8763',
    'key83032': 'value63695',
    'key68194': 'value54922',
    'key28035': 'value59140',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Monica Flowers',
    'address': '5466 Julia Land Apt. 449\nRuizmouth, OH 24953',
    'text': 'Perform six bit even. Trial on base continue bring check contain.',
    'email': 'laurencarter@example.com',
    'phone_number': '+1-555-287-1030',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christine Herrera',
    'Timothy Garner',
    'Carlos Atkinson',
    'Cynthia Green',
    'Aimee Glass',
    'Joshua Livingston',
    'Ronnie Bryant',
    'Adriana Morgan',
],
    'json': {
    'name': 'Catherine Wood',
    'address': '1177 Mack Falls Apt. 511\nSouth Antonioshire, WI 89407',
},
    'key3247': 'value83045',
},
],
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
        """测试请求 2 - POST http://172.17.0.5:23210/v1/vector/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '24787b10-62f0-11f0-a344-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_26_31_911081WxZdlCvJ',
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'outputFields': [
    'phone_number',
    'name',
    'email',
    'json',
    'uid',
    'array_varchar_dynamic',
    'address',
    'text',
    'array_int_dynamic',
],
    'filter': 'uid >= 0',
    'limit': 1,
    'offset': 0,
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



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v1/vector/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '251671e3-62f0-11f0-ba8a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_26_31_911081WxZdlCvJ',
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



    def test_request_4(self):
        """测试请求 4 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '20b85dc9-62f0-11f0-854e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_26_31_911081WxZdlCvJ',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[L2-1-0-2]_1752744400.json')
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
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithComplexPayloadL21021752744400Json()
    test.run_tests()
