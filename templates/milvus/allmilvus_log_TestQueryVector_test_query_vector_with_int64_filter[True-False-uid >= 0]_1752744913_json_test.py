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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752744913_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752744913.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid01752744913Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752744913.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752744913.json"
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
    'RequestId': '4fea9afb-62f1-11f0-b206-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_00_589964GrwlycPl',
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
    'RequestId': '53083cde-62f1-11f0-871f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_00_589964GrwlycPl',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Justin Tucker',
    'address': '271 Jennifer Knoll\nHoganhaven, SC 80990',
    'text': 'Save call finally moment win place play.\nFirst adult painting case forward imagine admit.\nPractice relate common by true under.\nGrow newspaper job miss across hear. Offer to range most girl pressure.',
    'email': 'kellybryan@example.com',
    'phone_number': '+1-359-549-2449x535',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Robert Mccullough',
    'Vanessa Miller',
    'Mrs. Diane Clay',
    'James Day',
],
    'json': {
    'name': 'Debbie Lozano',
    'address': '7517 Allen Brooks\nChristinaside, GA 87737',
},
    'key41239': 'value84250',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Mr. William Roberts',
    'address': '91646 Carlos Falls\nEast Peter, MP 76167',
    'text': 'Job everyone wrong finish goal whole happy player. Easy center part institution analysis education plan.',
    'email': 'qperry@example.net',
    'phone_number': '272-632-9139',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Susan Conley',
    'Michael Brown',
    'Tamara Hurley',
    'Kathleen Garcia',
],
    'json': {
    'name': 'Brian Bennett',
    'address': '070 Pamela Harbors\nJenniferton, NE 63562',
},
    'key46581': 'value29639',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Benjamin Adams',
    'address': '3035 Sarah Plain Apt. 227\nGarciaburgh, CT 48253',
    'text': 'Center your hour fine. Receive clearly team town member series station. Instead option arrive majority keep surface.\nSuccessful another listen surface. Rise lot population only box.',
    'email': 'tina54@example.org',
    'phone_number': '001-752-487-5641x33416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brian Juarez Jr.',
    'Michael Miller',
    'Brittany Smith',
    'Amber Mcneil',
    'Gary Williams',
    'Karen Gomez',
    'Jonathan Mitchell',
    'Lisa Ortega',
    'Leah Baird',
],
    'json': {
    'name': 'Gregory Garcia',
    'address': 'Unit 1748 Box 0354\nDPO AP 22343',
},
    'key22108': 'value95188',
    'key92788': 'value87488',
    'key63943': 'value93968',
    'key48570': 'value72187',
    'key50606': 'value30017',
    'key62681': 'value28647',
    'key18456': 'value78270',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Holly Spears',
    'address': 'Unit 6071 Box 4131\nDPO AP 70386',
    'text': 'Environment good capital evening message detail. Forget agreement election reason teach us.\nApproach method religious before stop into I piece. Thought avoid night.',
    'email': 'zacharyfarley@example.com',
    'phone_number': '961.618.3729x650',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alicia Sosa',
    'Ashley Stevenson',
    'Bryan Wood',
    'Dalton Abbott',
    'Stephen Armstrong',
    'Michael Hernandez',
],
    'json': {
    'name': 'Eric Gomez',
    'address': '40717 Cynthia Trail Apt. 871\nLake Stephen, OK 11778',
},
    'key80894': 'value22151',
    'key32113': 'value93735',
    'key79665': 'value42979',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Christopher Malone',
    'address': '670 Martinez Overpass\nJonesbury, PA 39640',
    'text': 'When involve determine together teacher throw. Keep west knowledge example. Pattern more free.\nSpecific determine late able. Very wonder remain federal drop.',
    'email': 'xcortez@example.com',
    'phone_number': '628.410.9558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Scott Higgins',
    'Teresa Henderson',
    'Henry Sheppard',
    'Regina Spence',
    'Jason Porter',
],
    'json': {
    'name': 'Ralph Wiley',
    'address': '8208 Mcdonald Loop Apt. 577\nPort Kristi, OK 92719',
},
    'key50383': 'value25844',
    'key14615': 'value76562',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Matthew Moreno',
    'address': '226 Joanne Drive\nWest Christopherville, GU 04020',
    'text': 'Compare position stay industry kid wall. Realize data painting ten note nor physical. Minute authority party shake support court deep.',
    'email': 'thomasandrew@example.net',
    'phone_number': '+1-885-841-2323x492',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Howard Petersen',
    'Tina Miller',
    'Cynthia Weaver',
    'Melissa Gill',
    'Douglas Robinson',
    'Aaron Mcfarland',
    'Deborah Jackson',
],
    'json': {
    'name': 'Lisa White',
    'address': '4957 Brown Springs Suite 497\nNorth Ronald, OH 78670',
},
    'key88521': 'value43457',
    'key89458': 'value92598',
    'key86325': 'value80622',
    'key65869': 'value65044',
    'key40907': 'value1214',
    'key99205': 'value75949',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Douglas Thomas',
    'address': '78083 Joseph Village Apt. 519\nScottmouth, AS 65618',
    'text': 'Believe right per high risk main class. Production significant garden resource reach. Turn possible likely second grow bag mean.',
    'email': 'angela71@example.net',
    'phone_number': '251.560.9474x1919',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Robin Anderson',
    'Jeffery Hall',
    'Alexis Rodriguez',
    'Matthew Davenport MD',
    'James Page',
    'Doris Rubio',
    'Jessica Beasley PhD',
    'Curtis Carlson',
    'Aaron Patterson',
    'Kristy Garza',
],
    'json': {
    'name': 'Caleb Holland',
    'address': '889 Melissa Unions\nSouth Ricardoland, AR 97810',
},
    'key88198': 'value55619',
    'key98004': 'value14992',
    'key38122': 'value40000',
    'key156': 'value43737',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Joseph Turner',
    'address': '4985 Miller Courts\nPort Katherineland, DC 13476',
    'text': 'Show operation attention crime. Yes past north.\nProgram admit control notice when. Important card but figure stock. Line perhaps control want fill might eye.',
    'email': 'ericadavis@example.com',
    'phone_number': '(895)796-6324x29187',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Denise Briggs',
    'Tricia Horne',
    'Justin Banks',
    'Kirk Spencer',
],
    'json': {
    'name': 'Adam Wallace',
    'address': '2981 Saunders Harbor Apt. 588\nHickmanshire, AK 90073',
},
    'key82605': 'value81787',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Angela Santos',
    'address': '82830 Gonzales Underpass Suite 068\nSusanberg, MS 52141',
    'text': 'Agree culture across right dinner or show. Fly design develop establish type character wish. Citizen western image spring but.',
    'email': 'kyle10@example.com',
    'phone_number': '(582)619-9016x66740',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Garcia',
    'Dylan Blair',
    'Corey Manning',
    'James Bowman',
    'Adam White',
],
    'json': {
    'name': 'Brittany Warner',
    'address': '3250 Danielle Valley\nWest Allison, OK 72734',
},
    'key48032': 'value82416',
    'key36396': 'value47663',
    'key69932': 'value27406',
    'key86175': 'value69244',
    'key45860': 'value20346',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Benjamin Austin',
    'address': '194 Howard Trace Suite 371\nJonesbury, ID 90544',
    'text': 'Or garden prevent part magazine. Step prevent detail build else himself join.\nBlue wife main. Only population nation laugh catch imagine you. Design performance direction easy.',
    'email': 'lramsey@example.org',
    'phone_number': '605-732-6551',
    'array_int_dynamic': [
    63344,
],
    'array_varchar_dynamic': [
    'Linda Farrell',
    'Douglas Dixon',
    'William Nichols',
    'Cynthia Novak',
    'Cameron Clay',
    'Marcus Mendez',
],
    'json': {
    'name': 'Zachary Ballard',
    'address': '1964 Aguilar Heights Apt. 375\nDanielside, WA 20859',
},
    'key94453': 'value15813',
    'key30993': 'value68814',
    'key23946': 'value20297',
    'key97119': 'value45927',
    'key11122': 'value56942',
    'key36301': 'value37999',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Stephanie King',
    'address': 'Unit 4902 Box 5204\nDPO AE 35841',
    'text': 'Write degree force cold. Reduce although data student.\nPressure financial it economy system. Minute light suggest red American. Popular record thing feel relate quality.',
    'email': 'vincentirwin@example.com',
    'phone_number': '255-388-6410x4083',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Thomas',
    'Edwin Leach',
    'Matthew Sullivan',
    'Michael Zimmerman',
    'Eric Fields',
    'Jeffery Mcbride',
    'Victor Brown',
    'Kimberly Long',
    'Lisa Gordon',
    'Ellen Sanchez',
],
    'json': {
    'name': 'Susan Pearson',
    'address': '576 Brooke Points\nLake Monique, OK 91810',
},
    'key45092': 'value3974',
    'key85930': 'value76925',
    'key27603': 'value72520',
    'key78979': 'value43726',
    'key66714': 'value25091',
    'key67557': 'value78319',
    'key23217': 'value45134',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Morgan Vance',
    'address': '4660 Tamara Path Suite 759\nHughesbury, CA 43129',
    'text': 'Necessary hard concern than enough eat.\nIf throw nothing buy. Reflect turn rule effort after show director. Fall continue take think fill another.',
    'email': 'angela54@example.com',
    'phone_number': '(374)688-9404x989',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Darius Hernandez',
    'Jordan Thompson',
    'Katherine Russo MD',
    'Kenneth Rocha',
    'Larry Jackson',
    'Darlene Atkinson',
],
    'json': {
    'name': 'Bruce Ochoa',
    'address': 'Unit 6034 Box 2922\nDPO AA 02954',
},
    'key2904': 'value72531',
    'key98218': 'value60742',
    'key34948': 'value67469',
    'key34513': 'value40690',
    'key30792': 'value93924',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Richard Newman',
    'address': '05984 Bryan Vista\nSouth Jesus, MI 79886',
    'text': 'Project focus north write memory. Including gun owner once economy tree successful. Television idea increase travel.',
    'email': 'blankenshipmark@example.org',
    'phone_number': '974-584-4347x177',
    'array_int_dynamic': [
    35427,
],
    'array_varchar_dynamic': [
    'Jeffrey Young',
    'April Dyer',
    'Matthew Luna',
    'Susan Mcknight',
    'Megan Wilkinson',
    'Beverly Singleton',
],
    'json': {
    'name': 'Melissa King',
    'address': '24524 Natasha Station Apt. 630\nNew Sharon, GA 82248',
},
    'key61483': 'value20029',
    'key75490': 'value55241',
    'key93203': 'value12768',
    'key56103': 'value82504',
    'key93922': 'value67262',
    'key6581': 'value49353',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Timothy Juarez',
    'address': '1499 Scott Summit Apt. 802\nJasontown, WA 65077',
    'text': 'Few development scene indicate three. Down start idea raise attention pretty home. Much medical clear carry term mind customer majority.',
    'email': 'christopher36@example.org',
    'phone_number': '001-931-933-0729x24208',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Paul Dalton',
    'Jeffrey Tate',
    'Jason Reeves',
    'Ashley Gordon',
    'Heather Conley',
    'Ann Johnson',
    'Nicole Parker',
],
    'json': {
    'name': 'David Roach',
    'address': '6594 Laura Brooks Apt. 753\nMccarthychester, IL 43304',
},
    'key92547': 'value99006',
    'key23605': 'value2857',
    'key80484': 'value61358',
    'key25889': 'value99677',
    'key78339': 'value68174',
    'key46787': 'value59192',
    'key95820': 'value18110',
    'key52993': 'value35470',
    'key4352': 'value75701',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Benjamin Cole',
    'address': '517 Mary Estate\nMaryborough, LA 35297',
    'text': 'Early member no surface. Subject data wind. Religious shoulder effect represent.\nLeg win international could goal a stage. Month along program could sing paper middle.',
    'email': 'wbrown@example.com',
    'phone_number': '001-688-251-7044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Charles Rivera',
    'Miguel Arnold',
    'Lauren Barajas',
    'Katherine Jackson',
    'Charles Hicks',
],
    'json': {
    'name': 'Joel Thomas',
    'address': '9553 Medina Islands Suite 088\nNew Paulborough, FM 15598',
},
    'key24957': 'value96712',
    'key71839': 'value12048',
    'key96635': 'value45531',
    'key77107': 'value39387',
    'key14037': 'value24565',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jaime Walsh',
    'address': '7529 Benjamin Brooks\nElizabethland, AR 62275',
    'text': 'North investment best floor. Less purpose according seem return let current. Figure church happy performance certainly country. The discussion financial point.\nHusband first nation community wonder.',
    'email': 'jdavis@example.com',
    'phone_number': '8876578710',
    'array_int_dynamic': [
    64319,
],
    'array_varchar_dynamic': [
    'Veronica Oliver',
    'Edward Griffith',
],
    'json': {
    'name': 'Devin Martin',
    'address': '982 Barr Summit Suite 997\nEast Danielle, CA 48308',
},
    'key64592': 'value88337',
    'key35461': 'value34137',
    'key54438': 'value31141',
    'key45132': 'value21972',
    'key98164': 'value43191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Zachary Robinson',
    'address': '0558 Vargas Well\nEast Tara, MI 12546',
    'text': 'Husband religious modern image phone write tonight about. Type weight finish.',
    'email': 'larry24@example.com',
    'phone_number': '001-489-900-3144x240',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kim Taylor',
    'Adam Randall',
    'Erin Landry',
    'Brittney Flores',
    'Ralph Nicholson',
],
    'json': {
    'name': 'Steven Jones',
    'address': '574 Gordon Creek Apt. 742\nNorth Phillip, LA 41302',
},
    'key68346': 'value68909',
    'key34215': 'value76018',
    'key89115': 'value80649',
    'key63242': 'value85204',
    'key31552': 'value47953',
    'key31663': 'value15058',
    'key89387': 'value2422',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Anthony Morrow',
    'address': '43195 Rick Crescent Apt. 000\nNew Tracy, WA 23531',
    'text': 'Task drop seat yet. Go radio activity point main health high.\nHeart hair reflect between by eight raise. Second assume election affect head production.',
    'email': 'elucero@example.org',
    'phone_number': '462.223.3670',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Gibson',
    'Gregory Weber',
    'Sarah Tran',
    'Alexander Cox',
],
    'json': {
    'name': 'Kent Rhodes',
    'address': 'PSC 3435, Box 0727\nAPO AA 09238',
},
    'key56167': 'value15365',
    'key44577': 'value64682',
    'key92450': 'value86989',
    'key4268': 'value44260',
    'key16731': 'value59888',
    'key31647': 'value54629',
    'key38699': 'value61829',
    'key77078': 'value40455',
    'key3008': 'value89379',
    'key50972': 'value31654',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Jessica Stephens',
    'address': '97822 Jones Greens Suite 259\nEast Tracey, WA 82812',
    'text': 'Child find major chance international around not. Mother book now there prepare remember beautiful mention.\nSo discuss factor. North because improve technology. Difficult blood budget as.',
    'email': 'vpatel@example.com',
    'phone_number': '359-281-7890',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Karen Clarke',
    'Clifford Ramos',
    'Shannon Smith',
    'Eric White',
    'Joshua Smith',
],
    'json': {
    'name': 'Natasha Craig',
    'address': '1470 Alice Courts Suite 212\nWebbmouth, RI 20130',
},
    'key1653': 'value75695',
    'key74825': 'value97509',
    'key97385': 'value85874',
    'key8899': 'value11629',
    'key39936': 'value64361',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Timothy Sellers',
    'address': '45876 Anthony Fords Apt. 292\nNorth Samantha, TX 82407',
    'text': 'Care value though each why important coach return. Bar leader my few hear result news.\nDiscuss make issue boy stage. Reach try happen four weight.',
    'email': 'claire76@example.org',
    'phone_number': '841.903.6995x722',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Francis Ortiz',
    'Jose Green',
    'Charles Tran',
    'Mr. Jon Contreras',
    'Melissa West',
],
    'json': {
    'name': 'Holly Martin',
    'address': 'PSC 8744, Box 5899\nAPO AA 55606',
},
    'key79042': 'value97804',
    'key25285': 'value4416',
    'key96287': 'value19612',
    'key60858': 'value52584',
    'key42360': 'value55828',
    'key41300': 'value56524',
    'key28874': 'value59991',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Rose Bright',
    'address': '4320 Nicholas Manors Suite 749\nLaurenburgh, MT 35437',
    'text': 'A again should arm beat yes also. Relate speech might yard coach.\nCulture the will sister. Shake agent check particular. A former give ten.',
    'email': 'jason50@example.com',
    'phone_number': '001-293-592-3345',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Susan Barnes',
    'Holly Reid',
    'Ryan Velez',
    'Michael Bowers',
    'Eric Smith',
    'Gabriella Miller',
    'Kevin Ray',
    'Rebecca Gonzales',
    'Luke Chen',
    'Richard Dickson',
],
    'json': {
    'name': 'Andrew Mcfarland',
    'address': '254 Christine Lock\nBernardmouth, UT 32914',
},
    'key70111': 'value33189',
    'key51162': 'value39062',
    'key65265': 'value19782',
    'key52056': 'value59370',
    'key53356': 'value82188',
    'key87966': 'value15747',
    'key37325': 'value42696',
    'key15247': 'value58683',
    'key25486': 'value72904',
    'key27358': 'value40451',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Amanda Mcdonald',
    'address': '18193 Beth Locks Suite 153\nRandallside, WV 24011',
    'text': 'Behavior born Republican. Heavy produce article many term.\nLast available item item model.',
    'email': 'ihodges@example.org',
    'phone_number': '001-718-598-8692x3331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Bruce',
    'Michael Nicholson',
    'Jaime Richards',
    'Briana Bauer',
    'Kimberly Miles',
    'Michael Jones',
    'Ronald Bonilla',
    'James Ramirez',
    'Jason Mitchell',
],
    'json': {
    'name': 'Karen Aguirre',
    'address': '47698 Aaron Pike\nHannafurt, VT 56662',
},
    'key30858': 'value46870',
    'key63416': 'value7094',
    'key74710': 'value17579',
    'key58310': 'value61980',
    'key98468': 'value23637',
    'key11477': 'value81259',
    'key25834': 'value71977',
    'key181': 'value13069',
    'key56498': 'value14187',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Albert Price',
    'address': '481 Maddox Drives\nNew Eugeneland, MT 30151',
    'text': 'National information benefit. Citizen allow attorney memory. General director father way way thing.',
    'email': 'kevinmayo@example.org',
    'phone_number': '+1-710-319-8518x574',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sherry Young',
    'Roger Porter',
    'Lisa Hubbard',
    'Diana Bradley',
    'Kyle Pugh',
],
    'json': {
    'name': 'Nicole Webb',
    'address': '9669 Lucas Heights Suite 238\nPort Austin, NC 18269',
},
    'key57462': 'value31938',
    'key47765': 'value84086',
    'key50046': 'value34244',
    'key11747': 'value90987',
    'key650': 'value4230',
    'key56461': 'value49035',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jason Harris',
    'address': '038 Thompson Villages Apt. 732\nWest Stephanietown, AZ 94604',
    'text': 'Activity prevent radio her rule manage. Stay wish physical between wait.\nLeast international information somebody control tax sell. Hard interview box customer international color expert hit.',
    'email': 'kburgess@example.org',
    'phone_number': '8386746720',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Leah Bennett',
    'Jennifer Barton',
],
    'json': {
    'name': 'Emily Rodriguez',
    'address': '61719 Gardner Circle\nLake Lydiaborough, NH 05905',
},
    'key41022': 'value88527',
    'key12678': 'value21236',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Allison Parks',
    'address': '77022 Kathleen Mews\nTabithaburgh, PA 73419',
    'text': 'Most break prevent after through. Car around raise simply hot defense. Music way body school author.\nFederal sing up. Beat difference force evening.',
    'email': 'wwilson@example.net',
    'phone_number': '+1-925-659-5516x363',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Reyes',
    'Luke Boyd',
],
    'json': {
    'name': 'Alexandria Brown',
    'address': '64652 Cheyenne Plain Apt. 584\nChanfurt, IN 50705',
},
    'key72668': 'value57568',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Robin Rivera',
    'address': '4623 Beth Extension Apt. 016\nElizabethfurt, AR 98049',
    'text': 'Her enough field. Expect relationship never news recently. Party him social artist have behavior.\nBuild have challenge down value. Speak ball up four officer.',
    'email': 'mitchellmichael@example.org',
    'phone_number': '799-781-0100',
    'array_int_dynamic': [
    4340,
],
    'array_varchar_dynamic': [
    'Steven Martinez',
    'Megan Mcconnell',
    'Nathaniel Love',
],
    'json': {
    'name': 'Crystal Turner',
    'address': 'Unit 5893 Box 7575\nDPO AE 35092',
},
    'key9113': 'value50521',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jennifer Daugherty',
    'address': '38916 Clark Rue Apt. 699\nNew Saramouth, AR 80535',
    'text': 'Thought general whose fact reach. Relationship growth explain speech. Behavior quality pretty remain.',
    'email': 'katiethomas@example.com',
    'phone_number': '001-764-717-1765x52760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Cunningham',
    'Mikayla Alvarez',
    'Christine Simpson',
    'Michael Lewis',
],
    'json': {
    'name': 'Crystal Holmes',
    'address': '335 Boyer Walks Apt. 380\nSouth Eileenberg, SC 29441',
},
    'key98534': 'value63502',
    'key3063': 'value64308',
    'key61217': 'value60475',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Stacey Simon',
    'address': '666 Carla Valley\nNorth Todd, SD 91992',
    'text': 'Shake together care. Her rest discuss face. Third interesting alone discussion receive resource scientist.\nSix several general. Current fill able region sea appear occur.',
    'email': 'pamela03@example.org',
    'phone_number': '992.506.5564',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Livingston',
    'Kelly Williams',
    'Monique Lane',
],
    'json': {
    'name': 'Mrs. Angela Howard',
    'address': 'USNS King\nFPO AP 27765',
},
    'key78258': 'value90081',
    'key19801': 'value2095',
    'key74164': 'value6314',
    'key64429': 'value52467',
    'key50961': 'value92029',
    'key71408': 'value75899',
    'key21455': 'value12016',
    'key30901': 'value95646',
    'key11315': 'value79590',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jeffrey Cobb',
    'address': '5841 Costa Turnpike\nJackfort, MS 60928',
    'text': 'Such occur two major. Mission minute resource. Right course rule great movie memory area few.\nMission threat fall here put hard professor everything. Car account always which evidence.',
    'email': 'orangel@example.net',
    'phone_number': '241.789.4599',
    'array_int_dynamic': [
    4972,
],
    'array_varchar_dynamic': [
    'Joyce Osborne',
],
    'json': {
    'name': 'Jon Orozco',
    'address': '93155 Nichols Skyway Suite 310\nManuelfurt, MT 60686',
},
    'key2923': 'value4766',
    'key83429': 'value91927',
    'key12157': 'value44611',
    'key5401': 'value65967',
    'key5065': 'value23841',
    'key45380': 'value21329',
    'key87099': 'value52259',
    'key30407': 'value64258',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Austin Meyer',
    'address': '872 Butler Shore Suite 058\nPort Dianeview, IN 68583',
    'text': 'Movement imagine letter. Require order around play never.',
    'email': 'joannacastaneda@example.net',
    'phone_number': '(802)622-3591',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jon Kelly',
    'Anthony White',
    'James Day',
    'Dana Jenkins',
    'Jennifer Campbell',
    'Suzanne Guzman',
    'Monique Martinez',
],
    'json': {
    'name': 'Cynthia Terry',
    'address': '6164 West Locks\nNew Stephen, WY 24023',
},
    'key5778': 'value19226',
    'key70957': 'value42410',
    'key8298': 'value15789',
    'key76431': 'value7048',
    'key51723': 'value83604',
    'key71260': 'value55929',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Jenny Harvey',
    'address': '03668 Alex Locks Apt. 992\nSouth Williamburgh, IN 58562',
    'text': 'Although boy rather board police. Half wish lose with TV special benefit.\nLike term American marriage bad product. With entire run executive. Stage evening method pattern air choose.',
    'email': 'andreathomas@example.org',
    'phone_number': '520-876-5779x785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Paula Curry',
    'Robert Williams',
    'Michelle Hill',
    'Joseph James',
],
    'json': {
    'name': 'Lori Johnson',
    'address': '05628 Holmes Centers Suite 332\nNew Jose, MP 30360',
},
    'key36202': 'value48187',
    'key77795': 'value99260',
    'key28838': 'value57066',
    'key91175': 'value98253',
    'key38891': 'value48627',
    'key23677': 'value52467',
    'key34593': 'value60639',
    'key39744': 'value64678',
    'key21245': 'value32360',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'James Shaw',
    'address': '66983 Hopkins Centers Apt. 195\nWest Lawrencestad, ID 35562',
    'text': 'These listen card meeting.\nFilm mother other task machine.\nBar big position become skill range. Special until pretty student center cultural.',
    'email': 'pamela31@example.com',
    'phone_number': '001-587-870-1047x80633',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jill Oneill',
    'Carly Snyder',
    'Nichole Ramirez',
    'Cindy Hines',
],
    'json': {
    'name': 'Bruce Woods',
    'address': '840 Mendoza Street\nNew Sandyville, AS 93530',
},
    'key43217': 'value56079',
    'key98230': 'value11102',
    'key80024': 'value56389',
    'key30218': 'value43787',
    'key52920': 'value37829',
    'key83345': 'value77283',
    'key87855': 'value48757',
    'key14995': 'value80442',
    'key1847': 'value99064',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Michael Dunlap',
    'address': 'PSC 8827, Box 5264\nAPO AE 28089',
    'text': 'Tough entire others about life anything catch. Radio tend call bill paper best hold. Population population miss. Writer late doctor country everybody.',
    'email': 'edward15@example.com',
    'phone_number': '(774)780-8637x209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Henry Nelson',
    'Kyle Richardson',
    'Paula Pham',
    'Jimmy Smith',
    'William Ward',
],
    'json': {
    'name': 'Christopher Evans',
    'address': '6463 Miller Roads\nEast Georgemouth, MH 19202',
},
    'key44068': 'value97931',
    'key52309': 'value74658',
    'key60566': 'value77120',
    'key56421': 'value65803',
    'key25736': 'value21944',
    'key80081': 'value95610',
    'key74934': 'value46850',
    'key33700': 'value10101',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'David Williams',
    'address': '28208 Roberson Motorway Suite 702\nNew Elizabethhaven, HI 22899',
    'text': 'Feel you might bad. Music town fact push increase second space without.\nUnder theory business pick finish. Add direction series brother along. Side standard raise like make.',
    'email': 'lawrence53@example.net',
    'phone_number': '549-726-7894x87922',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brent Richmond',
    'Yvette Cox',
    'Deanna Simmons',
    'Edward James',
],
    'json': {
    'name': 'Michelle Ellison MD',
    'address': '790 Katherine Streets\nNorth Derekview, MP 17686',
},
    'key1049': 'value54137',
    'key2274': 'value9057',
    'key29234': 'value33007',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Susan Ward',
    'address': 'PSC 2504, Box 1117\nAPO AE 49008',
    'text': 'Apply war national college necessary. Day food in important the ball rise. School open director those cut fast simply.\nMagazine loss third. By do hot huge key choose item bed.',
    'email': 'wwood@example.com',
    'phone_number': '791-433-8835x99949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Jackson',
    'Heather Adams',
],
    'json': {
    'name': 'Brittany Thornton',
    'address': '721 Amanda Shore\nNorth Anthony, WV 90387',
},
    'key52920': 'value28065',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'David Reyes',
    'address': '9347 Michelle Branch\nWest Daniel, NV 65054',
    'text': 'Analysis agent recently social. Not best cut few despite.\nThree arm draw instead too left black. Alone including allow dark hand. Present box call east call all.',
    'email': 'woodjoshua@example.org',
    'phone_number': '+1-799-495-9825x602',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Cory Booth',
    'Sara Hernandez',
    'Andrea Davis',
    'Kimberly Roberts',
],
    'json': {
    'name': 'David Yoder',
    'address': '975 Mary Plaza Suite 370\nMillerchester, WA 64507',
},
    'key97167': 'value3269',
    'key39539': 'value10389',
    'key2736': 'value3551',
    'key69314': 'value12352',
    'key1841': 'value64718',
    'key39495': 'value52678',
    'key67068': 'value92522',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Jessica Johnson',
    'address': '23551 Tyler Meadow\nSouth Kimberly, IN 31580',
    'text': 'Kind also later work organization mouth. By suggest raise away your lose person. Over four north think conference child.',
    'email': 'dmurphy@example.org',
    'phone_number': '(268)324-2482x9605',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lindsay Coleman',
    'Jaclyn Brown',
],
    'json': {
    'name': 'Henry Chen',
    'address': '2916 Gray Ways Apt. 488\nArthurview, MP 37881',
},
    'key48043': 'value38226',
    'key83773': 'value82674',
    'key50874': 'value60355',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Aaron Griffin',
    'address': '536 Le Points Suite 924\nChaseville, AS 17760',
    'text': 'Stay believe picture likely. Lawyer thousand development.\nTeacher pay remain land serve myself one. Material commercial source there. Vote only should argue.\nSituation ability former tell interview.',
    'email': 'sydney27@example.org',
    'phone_number': '+1-279-228-2578x008',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Hunt',
    'Kimberly Cole',
    'Jacob Richardson',
    'James Smith',
    'Nicholas Andrade',
],
    'json': {
    'name': 'Emily Hopkins',
    'address': '2750 Herrera Harbors\nWest Jasmine, RI 80250',
},
    'key37945': 'value8567',
    'key3247': 'value58309',
    'key79592': 'value16517',
    'key8246': 'value32608',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Debbie Martin',
    'address': 'PSC 5255, Box 2415\nAPO AE 49866',
    'text': 'Treat material east entire statement industry site. Order what value financial American book. Sister so night.',
    'email': 'michaelpowers@example.org',
    'phone_number': '001-387-903-7911x96559',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Robert Robertson',
    'Lisa Miller',
    'Jonathan Nguyen',
    'Haley Williams',
    'Scott Obrien',
],
    'json': {
    'name': 'Ethan Thompson',
    'address': '16465 Jordan Springs\nAcostastad, MN 45517',
},
    'key29149': 'value98451',
    'key13046': 'value30891',
    'key34910': 'value47485',
    'key28339': 'value30785',
    'key95925': 'value95498',
    'key31971': 'value88626',
    'key31277': 'value83267',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Anna Rodriguez',
    'address': '4646 Weaver Divide Apt. 612\nMiashire, TX 31585',
    'text': 'Yard minute agreement manage exist even board arrive. Piece operation herself fact thousand my young.',
    'email': 'marcdyer@example.com',
    'phone_number': '+1-797-939-3799x1239',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Rush',
    'Dennis Ward',
    'Jack Smith',
    'Gary Fernandez',
    'Gabriela Davis',
    'Taylor Rodriguez',
    'Gina Sanchez',
    'Jacob Rhodes',
    'Ronald Patterson',
    'Catherine Dominguez',
],
    'json': {
    'name': 'Stephanie Petty',
    'address': '69794 Edwin Parkway Suite 895\nDominguezbury, ND 95878',
},
    'key7685': 'value79090',
    'key56611': 'value42454',
    'key2436': 'value77006',
    'key65452': 'value84408',
    'key88603': 'value20782',
    'key33902': 'value22693',
    'key63757': 'value85909',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Joseph Ward',
    'address': '62339 Christian Road Apt. 328\nJimenezchester, ND 76325',
    'text': 'Wrong ok black check finish dream. International various real put shoulder fact. Small place go especially only. Economic hair test.',
    'email': 'goodsarah@example.net',
    'phone_number': '756.314.4062x3377',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Moore',
    'Mary Huerta',
    'Alexis Sexton MD',
    'Heather Rhodes',
    'Christopher Stephenson',
    'Laura West',
],
    'json': {
    'name': 'Jessica Gomez',
    'address': '324 Adam Island\nNew Rebeccaland, NE 67955',
},
    'key45785': 'value56560',
    'key10152': 'value57269',
    'key826': 'value58513',
    'key44897': 'value36319',
    'key5714': 'value97180',
    'key66865': 'value42307',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Andrew Wade',
    'address': '890 Hahn Roads Suite 241\nEast Karen, NE 99473',
    'text': 'Team also treatment husband civil.\nReturn student kitchen late appear eight. Bad why page when though wear see per.',
    'email': 'melindastark@example.net',
    'phone_number': '573-837-2461x80827',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robin Lee',
    'Spencer Patton',
    'Kelly Stark',
    'Sara Spencer',
    'Brian Richardson',
    'Taylor Kaiser',
],
    'json': {
    'name': 'Christopher Potter',
    'address': '937 Green Green\nEast Kelsey, NC 09355',
},
    'key83057': 'value26072',
    'key48691': 'value56638',
    'key89519': 'value73148',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Kristi Barajas',
    'address': '40112 Navarro Mountains\nDonnaburgh, MD 18018',
    'text': 'Forget single actually summer suddenly stuff smile. Feel million ground offer. Put reflect financial.',
    'email': 'otownsend@example.com',
    'phone_number': '900-243-5749',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Williams',
    'Tracy Turner',
    'Scott Lee',
    'Benjamin Bailey',
    'Jeff Coleman',
    'Sara Morrison',
    'Ryan Glenn',
    'Olivia Estrada',
    'Timothy Green',
    'Benjamin Williams',
],
    'json': {
    'name': 'Greg Johnson',
    'address': '046 Price Fords\nScottside, RI 14364',
},
    'key76277': 'value35827',
    'key62459': 'value12216',
    'key11609': 'value1799',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Michele Contreras',
    'address': '11272 Nicholas Key Suite 722\nFitzgeraldport, AK 78651',
    'text': 'I prove particular dog. Second wife meeting skin push. His blue woman war source social upon. Wear street or.',
    'email': 'denniskayla@example.net',
    'phone_number': '001-450-479-6773',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Adrian Ayala',
    'Gregory Miles',
    'Melinda Alvarado',
    'Trevor Cooper',
    'Robin Torres',
],
    'json': {
    'name': 'David Maddox DVM',
    'address': '93024 Davila Spurs\nWilsonville, NH 53311',
},
    'key28972': 'value36311',
    'key28520': 'value73910',
    'key6952': 'value39091',
    'key29145': 'value70607',
    'key86499': 'value68726',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Cody Mcintyre',
    'address': '9213 Lee Avenue\nWest Bobby, AS 66247',
    'text': 'Could herself side something whole may.\nOk able yet nature war change education. Head Democrat we investment until crime down.',
    'email': 'rhonda79@example.org',
    'phone_number': '001-583-735-4340x2529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Hamilton',
    'Michael Smith',
    'Michele Davis',
    'Dustin Henderson',
    'Kyle Hunt',
    'Christopher Smith',
    'Julie Rice',
],
    'json': {
    'name': 'Helen Davis',
    'address': '33285 Hannah Square\nKellyfort, ND 87777',
},
    'key83418': 'value86935',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Grace Wilson',
    'address': '133 Le Unions Apt. 233\nNorth Megan, SD 41332',
    'text': 'Everything toward cost center writer between at picture. Drive remember science site exactly. Recognize want physical likely read.',
    'email': 'petersullivan@example.org',
    'phone_number': '(375)551-2709x2887',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Hines',
],
    'json': {
    'name': 'Patrick Cooper',
    'address': '585 Berg Underpass Apt. 302\nEast Lauren, NV 26119',
},
    'key50503': 'value46556',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Melissa Ayala',
    'address': '2958 Brooke Dam Suite 920\nNew Emily, ND 36246',
    'text': 'Save rate six against. Rise among region control.\nAppear may produce military style. Receive him institution each concern. Country then protect likely performance ever herself agree.',
    'email': 'clarkmaurice@example.net',
    'phone_number': '+1-951-741-7845x114',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Fitzpatrick',
    'Ruth Wagner',
    'Becky Frost',
    'Julian Mason',
    'Jeffrey Saunders',
    'Jesse Frederick',
    'Gary Johnson',
    'Frank Graham',
    'Daniel Friedman',
    'Kara Huang',
],
    'json': {
    'name': 'Jessica Moreno',
    'address': '86798 Hannah Bypass\nOrtizfurt, OR 55639',
},
    'key21924': 'value4528',
    'key45601': 'value40868',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'David Love',
    'address': '466 Jeff Mission Apt. 842\nWest Ashley, WI 31230',
    'text': 'Send true successful suffer house admit scientist. Talk it anything performance peace stop her adult. Another movie surface commercial myself whether guy.',
    'email': 'steven38@example.org',
    'phone_number': '(968)452-6942',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Fowler',
    'Joan Wagner',
    'Thomas Harmon',
    'Jacob Hill',
    'Jamie Young',
],
    'json': {
    'name': 'Mrs. Elizabeth Lawrence',
    'address': '4546 Carter Stream Suite 135\nDannybury, GU 95943',
},
    'key75029': 'value18726',
    'key55982': 'value49545',
    'key32378': 'value20486',
    'key11261': 'value28495',
    'key54649': 'value23725',
    'key32096': 'value53757',
    'key30246': 'value94078',
    'key69008': 'value44823',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Carrie Daniels',
    'address': '4870 Amy Springs Apt. 208\nMitchellstad, MO 29363',
    'text': 'Name environmental represent parent sure find agree grow. Every pick interesting. Perform call TV wall do American. Rise last find happy truth memory part.',
    'email': 'angela03@example.org',
    'phone_number': '(893)403-6384',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Sharp',
    'John Benson',
    'Christina Mata',
    'Victoria Miller',
    'Russell Wilson',
],
    'json': {
    'name': 'Caroline Sanchez',
    'address': '852 Jillian Rue Apt. 216\nSarahberg, VI 95616',
},
    'key18258': 'value10620',
    'key69228': 'value77227',
    'key86298': 'value62828',
    'key21489': 'value49467',
    'key48722': 'value70452',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Lauren Smith',
    'address': '260 Stewart Island\nNorth Andrewberg, MO 67658',
    'text': 'List social increase somebody toward right oil.\nMilitary success important. Would perhaps term. Forward husband listen mouth military someone happen.',
    'email': 'wesley83@example.net',
    'phone_number': '431.460.5868x100',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Justin Owens',
    'Joanne Garcia',
    'James Anderson',
    'Scott Clements II',
    'Daniel Ortiz',
    'Jocelyn Brown',
    'David Cole',
    'Tara Gilbert DDS',
],
    'json': {
    'name': 'Robert Trujillo',
    'address': '83384 Michael Cape Apt. 019\nNorth Marytown, NY 32711',
},
    'key15491': 'value64967',
    'key13115': 'value93177',
    'key16098': 'value74592',
    'key11737': 'value41922',
    'key72865': 'value75897',
    'key71463': 'value95166',
    'key12821': 'value92149',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Matthew Carter',
    'address': '3292 Charles Trace\nHooverhaven, NV 50946',
    'text': 'Interesting most again campaign. Line take adult culture mean war. Reality economy simply data buy dog.',
    'email': 'awolf@example.org',
    'phone_number': '897.441.2324x100',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Amber Taylor',
],
    'json': {
    'name': 'Douglas Graham',
    'address': '0453 Gray Flats\nMitchellborough, KS 30506',
},
    'key67491': 'value87404',
    'key69941': 'value13951',
    'key31656': 'value44249',
    'key11131': 'value803',
    'key17057': 'value94376',
    'key22295': 'value40979',
    'key41405': 'value33983',
    'key96301': 'value21240',
    'key85049': 'value17313',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Emily Camacho',
    'address': '886 Tammy Haven\nWest Steve, GU 59196',
    'text': 'Line picture including wait night. Put scientist effort music stay. Reduce type local others sit.\nTime we police serious. Table one star everything.',
    'email': 'lunanicholas@example.com',
    'phone_number': '331.871.8530',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lawrence Miller',
    'Justin Welch',
    'Matthew King',
    'Mr. James Daniels',
    'Michael Grant',
    'Jeffery Lowery',
    'Sandra Hamilton',
    'Alexis Martin',
],
    'json': {
    'name': 'Daniel Gilbert',
    'address': '5683 Buck Point\nFrymouth, WI 98302',
},
    'key19648': 'value96654',
    'key74401': 'value81897',
    'key77074': 'value87536',
    'key76048': 'value77518',
    'key92868': 'value10297',
    'key69942': 'value82039',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Mrs. Jasmine Wilson',
    'address': '187 Julia Creek Apt. 928\nSouth Alvin, AK 79157',
    'text': 'Life your often personal detail look indeed. Newspaper per lot answer effect over.\nHow even involve whose stay participant seat. Price agent beyond design go few capital him. Subject old almost the.',
    'email': 'christophersmall@example.org',
    'phone_number': '(552)320-1877x32392',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Carter',
    'Mark Obrien',
    'Martha Barron',
],
    'json': {
    'name': 'Robert Santiago',
    'address': '56278 Antonio Hollow\nWatsonburgh, UT 05598',
},
    'key80998': 'value62543',
    'key2277': 'value2058',
    'key24071': 'value60729',
    'key69343': 'value30466',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Michael Joyce',
    'address': '549 Hernandez Turnpike\nEast Andrew, PA 34999',
    'text': 'Maybe international traditional throw lay. Among be education expert ball career prove.\nEnjoy effort development note. Strong relate ability. Piece hard executive close.',
    'email': 'williamsedward@example.org',
    'phone_number': '483.372.9368x8196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Casey Carlson',
],
    'json': {
    'name': 'Shelby Martin',
    'address': '891 Craig Mission Apt. 153\nEast Sherrybury, IN 95088',
},
    'key68899': 'value21751',
    'key18626': 'value87623',
    'key15867': 'value21817',
    'key99627': 'value97631',
    'key15994': 'value66554',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Mrs. Gloria Bryant MD',
    'address': '069 Martin Drive\nRichardview, DE 43898',
    'text': 'Foot dark put represent get Mr. Authority reduce figure hair if data image.\nMorning three all near five region. Meet stock Mr should possible.\nThemselves media age compare why.',
    'email': 'elizabethjuarez@example.org',
    'phone_number': '+1-501-971-2601x138',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Rebecca Mata DVM',
    'Sandra Nichols',
    'Joshua Hall',
    'David Nguyen',
    'Amanda Perez',
    'Angela Fowler',
    'Pamela Neal',
    'Nicholas Hernandez',
],
    'json': {
    'name': 'Jerry Jones',
    'address': '4698 Erica Islands\nMcleanchester, MO 02963',
},
    'key92108': 'value24336',
    'key81866': 'value77007',
    'key86756': 'value73476',
    'key72336': 'value62744',
    'key64100': 'value73906',
    'key94452': 'value36045',
    'key52304': 'value8022',
    'key85869': 'value46906',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'John Cooper',
    'address': '1180 Harris Squares Apt. 611\nEast Kevin, VA 95951',
    'text': 'Structure guess information. Rise attorney identify get. Manage race miss lose.\nOnce my religious feeling it. Prove speak leg despite.',
    'email': 'gabbott@example.net',
    'phone_number': '(529)881-1753x07366',
    'array_int_dynamic': [
    86622,
],
    'array_varchar_dynamic': [
    'Brian Bruce',
    'Savannah Phelps',
    'Beth White',
    'Jerry Greene',
    'Sean Roberts',
    'Catherine Stevens',
    'Roy Miller',
],
    'json': {
    'name': 'Danielle Macdonald',
    'address': '1571 Green Circles\nWest Susantown, LA 32882',
},
    'key85877': 'value6279',
    'key37247': 'value29933',
    'key17343': 'value57963',
    'key59866': 'value29643',
    'key74873': 'value95560',
    'key40526': 'value72003',
    'key59272': 'value62444',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Dr. Michelle Oliver',
    'address': '98107 Beasley Track Suite 911\nLeslieton, TX 37912',
    'text': 'Sure various old almost some media. Happen technology agree. Guy cultural skin property west. Talk bag reveal charge.',
    'email': 'ajackson@example.org',
    'phone_number': '+1-414-350-5108',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Emily Ayala',
    'Jacqueline Rodriguez',
    'Mario Smith',
    'Sharon Beard',
    'Lisa Peters MD',
    'Ashley Copeland',
    'Cynthia Ryan',
],
    'json': {
    'name': 'John Rose',
    'address': '8440 Mary Ferry Suite 784\nMichaelton, MA 29096',
},
    'key85596': 'value4839',
    'key6592': 'value76235',
    'key40179': 'value47801',
    'key83577': 'value93690',
    'key71240': 'value69978',
    'key63029': 'value95256',
    'key29627': 'value77050',
    'key1025': 'value39333',
    'key1571': 'value71945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Robert Rogers',
    'address': 'USS Morales\nFPO AP 02799',
    'text': 'Child environmental power subject. Event describe view order authority show radio.\nSmile student who friend floor.',
    'email': 'lisa56@example.com',
    'phone_number': '650.794.8579x7814',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jorge Nguyen',
    'Sean Lane',
],
    'json': {
    'name': 'David Martinez',
    'address': '68054 Melanie Pines Apt. 337\nJoelside, NH 72147',
},
    'key95217': 'value29158',
    'key18841': 'value22403',
    'key91110': 'value53782',
    'key5090': 'value88050',
    'key66335': 'value89555',
    'key93490': 'value31029',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'David Sexton',
    'address': 'USNV Sweeney\nFPO AA 95044',
    'text': 'Consumer itself leader. Billion respond college mother north girl action. Quality phone industry indicate western director.\nList never world scene significant magazine.\nProgram new professor.',
    'email': 'richardlyons@example.com',
    'phone_number': '210-374-6878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Autumn Flores',
    'Michael Martinez',
    'Jeffrey Roman',
    'Dr. Bryan Adams',
    'Kimberly Davenport',
    'Alan Gray',
    'Rachel Hickman',
    'Erin Nguyen',
],
    'json': {
    'name': 'Victoria Hayes',
    'address': '5739 Brian Branch Suite 012\nNorth Johnmouth, NC 26597',
},
    'key89613': 'value22682',
    'key65320': 'value50852',
    'key60367': 'value26322',
    'key57125': 'value86939',
    'key28763': 'value48119',
    'key1306': 'value94404',
    'key80985': 'value35009',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Kevin Powers',
    'address': '276 Rangel Wells\nCartershire, ID 57445',
    'text': 'Discuss pattern fact sell few world she. Heavy difference resource theory reason develop write though.\nSimple response indicate high rock American. Mouth visit first myself minute wind.',
    'email': 'yvasquez@example.org',
    'phone_number': '(272)252-2781x23065',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Maria Johnson',
    'Michael Oneill',
    'Jane Hood',
    'Robin Murphy',
    'Lauren Martinez',
    'Gabriel Anthony',
    'Stephen Campos',
    'Yvonne Herrera',
    'Ellen Poole',
    'Kyle Jones',
],
    'json': {
    'name': 'Garrett Garza',
    'address': '675 Williams Turnpike Suite 034\nSouth Ericaberg, GU 60695',
},
    'key9220': 'value56701',
    'key50913': 'value15772',
    'key44017': 'value459',
    'key49332': 'value85469',
    'key98227': 'value66408',
    'key30448': 'value59175',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Richard Harrison',
    'address': '5114 Gardner Run\nLunaberg, MO 36507',
    'text': 'Relate central peace hundred front cell scene. Trial surface owner.\nOption network woman road. Perform expert hand. Billion offer back like. Get stop nothing give factor without little thought.',
    'email': 'millerandrew@example.net',
    'phone_number': '8013931760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Melanie Harris',
    'Jennifer Phillips',
    'Stephanie Fox',
    'Natasha Pierce',
],
    'json': {
    'name': 'Russell Burgess',
    'address': '56287 Merritt Harbor Apt. 248\nWilliamsberg, LA 28812',
},
    'key51227': 'value23343',
    'key4911': 'value47088',
    'key36774': 'value95802',
    'key55951': 'value55956',
    'key17846': 'value82792',
    'key94139': 'value89719',
    'key42383': 'value97117',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Paul Rodriguez',
    'address': '6018 Hays Springs Suite 489\nDouglasport, FL 33429',
    'text': 'Last Mr push there. Get weight stay goal until worry read.\nFish nice message trip. One head finally business.\nAccording rule it dream. What to stop how identify investment.',
    'email': 'gilbertisaac@example.org',
    'phone_number': '+1-272-688-1404',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Foster',
    'Rachel Jordan',
    'Vincent Black',
    'Elizabeth Torres',
    'Yvonne Daugherty',
    'Kimberly Garner',
    'Michael Crawford',
],
    'json': {
    'name': 'Angela Bishop',
    'address': '4646 Garrett Harbor\nNew Crystal, MT 06645',
},
    'key97843': 'value59343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Mark Riddle',
    'address': '18568 Jacob Groves\nSouth Jodi, MI 63440',
    'text': 'Must seven scene eight discuss fire shoulder. Require price toward amount kind. Region activity of home from worry event.',
    'email': 'tjohnson@example.com',
    'phone_number': '279.382.6047x0846',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Reed',
],
    'json': {
    'name': 'Christopher Thompson MD',
    'address': 'USCGC Craig\nFPO AA 29874',
},
    'key87364': 'value54282',
    'key17013': 'value51996',
    'key3572': 'value20739',
    'key38419': 'value16978',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Stephanie Adams',
    'address': '9441 Romero Track Apt. 896\nJacobberg, SD 47596',
    'text': 'Local management social deep score. Government third anyone above order issue two. Production interview easy national appear. Daughter after price fill doctor.',
    'email': 'linda45@example.net',
    'phone_number': '(245)789-5662x1484',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Brown',
    'Allison Griffith',
    'Jeffrey Rose',
    'Tasha Morse',
    'Robert Moore',
    'Abigail Walker',
],
    'json': {
    'name': 'Donna Yu',
    'address': '829 James Plains\nKellystad, WI 09482',
},
    'key78779': 'value16210',
    'key16713': 'value70345',
    'key23448': 'value16322',
    'key63588': 'value65042',
    'key24997': 'value10547',
    'key26127': 'value30263',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Mr. Samuel Holt III',
    'address': '011 Perry Pine Suite 732\nSmithmouth, DC 59355',
    'text': 'Stuff trial after however really lot control month. Establish certainly sometimes become. Catch sell agency fire central team. Center nature among moment training special.',
    'email': 'jonnewton@example.com',
    'phone_number': '266.683.9762x5459',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Richardson',
    'Linda Jones',
    'Barbara Ellis',
    'Alexandra Rice',
],
    'json': {
    'name': 'Connie David',
    'address': '51466 John Shoals Suite 872\nWest Christine, RI 27759',
},
    'key99254': 'value83555',
    'key32517': 'value6564',
    'key3072': 'value25522',
    'key30939': 'value37671',
    'key19869': 'value47264',
    'key72371': 'value44612',
    'key21431': 'value34385',
    'key24916': 'value73592',
    'key51882': 'value54673',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jason Hale',
    'address': '40209 Justin Square\nAmyville, MI 48263',
    'text': 'Including suddenly reach country.\nMy color if happy treatment same senior. Traditional student here physical investment.',
    'email': 'troy99@example.com',
    'phone_number': '919.255.4615x80619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jeffery Becker',
    'Richard Gibson',
    'Mary Jones',
    'Denise Williams',
    'Dillon Benitez',
],
    'json': {
    'name': 'Omar Johnson',
    'address': '9155 Meyer Courts Suite 581\nNew Barry, GA 28865',
},
    'key83714': 'value80702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Thomas Perez',
    'address': '03217 Jennifer Burgs Apt. 896\nBurtonmouth, VI 65543',
    'text': 'This brother sea behavior material light TV. Left discussion machine bit. Cut strategy leader.\nForeign book future number hotel reflect agent. Young owner some general similar glass.',
    'email': 'belliott@example.com',
    'phone_number': '700.727.8401x32799',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jane Webster',
    'James Rivera',
    'Steven Cline',
    'Ethan Campbell',
    'Helen Waller',
    'Brandi Copeland',
    'Heather Welch',
    'Robert Miles',
    'Lisa Barber',
    'Julia Robinson',
],
    'json': {
    'name': 'Megan Hopkins',
    'address': '454 Franklin Hollow\nSouth Wandahaven, FL 56273',
},
    'key8561': 'value70167',
    'key76347': 'value69558',
    'key601': 'value97593',
    'key96591': 'value73358',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Misty Davis',
    'address': '518 Hunt Court Suite 059\nWallacechester, IA 61224',
    'text': 'Good home want bed also spring almost. Laugh consider reason movie happen more.\nYes outside available upon out series prevent. Result style generation way.',
    'email': 'johnsonronald@example.org',
    'phone_number': '001-975-283-0325',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Roberts',
    'Kathryn Smith',
    'Joan Shaw',
    'Richard Mcdowell',
    'Anita Johnson',
],
    'json': {
    'name': 'Sarah Myers',
    'address': '689 Edwards Mall Suite 726\nBarryfurt, WV 50915',
},
    'key94346': 'value55480',
    'key30273': 'value81234',
    'key93752': 'value40224',
    'key97385': 'value67440',
    'key10812': 'value51528',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Vanessa Poole',
    'address': '561 Burton Isle\nEast Katherine, AL 49745',
    'text': 'Much drop model personal take. Idea at affect entire occur pay strategy look.\nFeel guess involve. Million report number property. Major race others born peace might page would.',
    'email': 'joshua45@example.org',
    'phone_number': '894-538-6446',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mikayla Meyers',
    'Melissa Wilson',
    'Nicholas Donovan',
],
    'json': {
    'name': 'Victoria Mills',
    'address': '812 Black Falls Apt. 104\nEast Amandamouth, WA 24916',
},
    'key27596': 'value51455',
    'key77916': 'value41870',
    'key38531': 'value78401',
    'key7390': 'value99675',
    'key25999': 'value98983',
    'key46105': 'value40594',
    'key24915': 'value3753',
    'key18761': 'value93271',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Brad Garcia',
    'address': '926 Teresa Corner Suite 055\nSouth Anthonyborough, NC 69819',
    'text': 'Around music nor machine million what sing. Third would glass mission reason he natural. Sea arrive page against.',
    'email': 'smithchris@example.org',
    'phone_number': '212-302-9903',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amy Mayo',
    'Ashley Black',
    'Matthew Flores',
    'Steven White',
    'Jordan Werner',
    'Deborah Tran',
    'Meredith Fisher',
],
    'json': {
    'name': 'Thomas Perez',
    'address': '096 Tiffany Harbor Apt. 773\nLake Andrew, AK 71050',
},
    'key38963': 'value77618',
    'key89647': 'value69586',
    'key83244': 'value83867',
    'key91197': 'value86543',
    'key63470': 'value37591',
    'key41596': 'value73306',
    'key2244': 'value59138',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Samantha Myers',
    'address': '4918 Reed Mission\nSouth Jenniferchester, SC 89851',
    'text': 'Degree personal community not war bill matter. Ball owner generation skin economic out seat. Image body official eat chair camera consider past. Music still enjoy board early sister.',
    'email': 'thomas85@example.org',
    'phone_number': '+1-607-494-2167',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Peters',
    'Brandon Potter',
],
    'json': {
    'name': 'Nicole Johnson',
    'address': '60257 Andrew Cliff Apt. 142\nPort Evanville, AZ 58505',
},
    'key58269': 'value14227',
    'key2056': 'value8427',
    'key53227': 'value5685',
    'key95948': 'value67906',
    'key8038': 'value26654',
    'key1851': 'value50539',
    'key36174': 'value51752',
    'key26877': 'value12852',
    'key75503': 'value59197',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Mary Ellis',
    'address': '4222 Todd Common Apt. 356\nWest Laura, DC 37040',
    'text': 'Than save data defense both safe. Near fear anyone final find.\nRespond nice conference sign worry. Protect sort official admit state wife.',
    'email': 'aaronjohnson@example.org',
    'phone_number': '(456)980-6829x41889',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Huerta',
    'Shelley Yoder',
    'Shaun Jones',
    'Brian Bailey',
],
    'json': {
    'name': 'Robert Beasley',
    'address': '17410 Mark Course Suite 103\nLeeshire, VA 76963',
},
    'key10644': 'value41057',
    'key71805': 'value54996',
    'key26721': 'value8002',
    'key56314': 'value48660',
    'key2108': 'value6467',
    'key41347': 'value56422',
    'key65993': 'value80506',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Margaret Mclaughlin',
    'address': '407 Christian Islands\nBrianmouth, SD 12051',
    'text': 'Hot chance fund always door. Produce during election check.\nPage make fear culture. Prevent kid brother race clearly southern sort owner.\nBaby strategy change. Job relate kind.',
    'email': 'pwilliams@example.net',
    'phone_number': '001-458-441-8779x1301',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robin Wall',
],
    'json': {
    'name': 'Nicole Ellis',
    'address': '579 Jessica Courts Apt. 693\nRobertburgh, KY 15253',
},
    'key11238': 'value47225',
    'key76227': 'value3704',
    'key12926': 'value18411',
    'key18526': 'value71504',
    'key57052': 'value23659',
    'key51876': 'value8210',
    'key76291': 'value66476',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Kevin Diaz',
    'address': '192 Alvin Cove Suite 369\nReeseland, IL 13991',
    'text': 'Why car month couple indicate race high. Special another above blood.\nCar by receive research clearly before director. Wonder economy hospital person.',
    'email': 'sabrinacraig@example.org',
    'phone_number': '001-359-264-9805x81058',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Mann',
    'Amy Cooper',
    'Charles Davis',
    'Robert Wilson',
    'Mrs. Crystal Padilla',
    'Megan Willis',
    'Erik Hood',
    'Clayton Camacho',
],
    'json': {
    'name': 'Katherine Stafford',
    'address': 'PSC 5382, Box 6382\nAPO AE 43304',
},
    'key85355': 'value58554',
    'key29949': 'value89854',
    'key36890': 'value27978',
    'key56695': 'value72648',
    'key35848': 'value91242',
    'key11270': 'value72220',
    'key74397': 'value42959',
    'key46439': 'value86144',
    'key89450': 'value78530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jason Hicks',
    'address': '0038 Johnson View\nSouth Robert, WV 84668',
    'text': 'We professor order trouble. Activity individual although million total surface compare campaign.\nSince perform present point gas five hear center.',
    'email': 'michael18@example.net',
    'phone_number': '713.721.6327x362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jody Washington',
    'Rachel Goodwin',
],
    'json': {
    'name': 'Beth Butler',
    'address': '830 Vaughn Flats\nKellytown, CA 52863',
},
    'key54772': 'value44369',
    'key33475': 'value42058',
    'key75989': 'value71812',
    'key3880': 'value47659',
    'key62782': 'value20655',
    'key66767': 'value85534',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Vincent Hall',
    'address': '903 Jessica Port Apt. 043\nWest Lauraside, NV 61655',
    'text': 'Least early ten hour around. Never figure give smile social turn.',
    'email': 'georgecynthia@example.net',
    'phone_number': '+1-841-473-2042',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Johnson',
    'Michelle Osborne',
],
    'json': {
    'name': 'Kirsten Greene',
    'address': '780 Rivera Ville Suite 690\nLake Kevin, KY 68982',
},
    'key24952': 'value28076',
    'key82767': 'value50182',
    'key92847': 'value83535',
    'key13604': 'value73503',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Peggy Duncan',
    'address': '5297 Krueger Turnpike Suite 475\nLake William, ID 71771',
    'text': 'Congress significant firm. Simple end operation growth fight take single.\nPicture look cover also number wind. International pull provide.',
    'email': 'griffinlindsay@example.com',
    'phone_number': '(840)935-0360x92760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Don Dunn',
    'Stephen Clarke',
    'Rachel Baker',
    'Phyllis Chen',
    'Jennifer Booth',
    'Daniel Jones',
    'Shawn Green',
    'Christina Scott',
    'Christopher Brown',
],
    'json': {
    'name': 'Aaron Webb',
    'address': '228 Moran Camp Apt. 925\nLucasstad, OK 83482',
},
    'key34354': 'value80140',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Dylan Hernandez',
    'address': '776 Jackson Forges Suite 030\nNew Victorside, VT 14216',
    'text': 'Available clear ahead address in people know. Garden indicate become would bank. Wear collection artist prove shoulder not walk.',
    'email': 'pagebridget@example.net',
    'phone_number': '577.518.4435',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Campbell',
    'Kayla Guerrero',
    'Samantha Robinson',
    'Peggy Hernandez',
    'Ryan Jefferson',
    'Christopher Shannon',
    'Sarah Andrews',
    'Brandon Landry',
],
    'json': {
    'name': 'Steven Johnson',
    'address': '249 Meyer Freeway Suite 927\nSouth Kevinton, SD 39877',
},
    'key11850': 'value73374',
    'key75351': 'value61485',
    'key57535': 'value84618',
    'key70769': 'value38924',
    'key30035': 'value19732',
    'key59847': 'value47815',
    'key27842': 'value8554',
    'key67698': 'value9105',
    'key17159': 'value70544',
    'key75115': 'value33326',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Jennifer Ramsey',
    'address': '25988 Cassie Village\nWest Amanda, DC 16120',
    'text': 'Show thank news between bad. Require she four real camera ten join. Seat service impact myself. Not scene hour foot.\nLevel meet author Mrs meeting guess. Couple whole defense issue southern.',
    'email': 'anthonycruz@example.com',
    'phone_number': '258-862-2868',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jose Patterson',
],
    'json': {
    'name': 'Jade Marsh',
    'address': '6701 Charles Lake\nDannyfurt, VA 33705',
},
    'key19410': 'value6611',
    'key80831': 'value78269',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'James Scott',
    'address': '203 Chad Mill Suite 239\nCarlville, TN 73745',
    'text': 'Forward change child nearly. Knowledge artist radio dark. Happy believe economic behavior worker stock support.',
    'email': 'brendawood@example.com',
    'phone_number': '418.363.4581x3001',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Smith',
    'Timothy Hall',
],
    'json': {
    'name': 'Miguel Glass',
    'address': '208 Wilson Extensions\nEast Philip, NM 41882',
},
    'key7312': 'value14894',
    'key34984': 'value99043',
    'key35776': 'value50630',
    'key39706': 'value60114',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Zachary Jackson',
    'address': '596 Robinson Points\nEdwardsfort, PR 26213',
    'text': 'Remember party respond although. Draw base stand begin mention field. Still life forward form what.',
    'email': 'joshua46@example.net',
    'phone_number': '001-314-382-2853x0464',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David Bowman DDS',
    'Michael Richardson',
    'Mary Johnson',
    'Juan Johnson',
    'Nancy Lee MD',
    'Deborah Carey',
    'Jason Ingram',
],
    'json': {
    'name': 'Colleen Knox',
    'address': 'Unit 9087 Box 7181\nDPO AP 62769',
},
    'key82947': 'value57591',
    'key89059': 'value80824',
    'key77018': 'value49371',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Karla Lee',
    'address': 'PSC 8699, Box 8488\nAPO AE 39848',
    'text': 'Store fill imagine. Responsibility source feel open leave. Event vote matter theory too.',
    'email': 'josephwallace@example.com',
    'phone_number': '+1-429-571-3102',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Burnett',
    'Richard Rogers',
    'Nicole Garcia',
    'Nathaniel Jones',
],
    'json': {
    'name': 'Hannah Williams',
    'address': '539 Brown Flats\nMatthewside, VT 83420',
},
    'key71745': 'value45347',
    'key19852': 'value97366',
    'key48588': 'value42834',
    'key93336': 'value37286',
    'key78297': 'value20943',
    'key49298': 'value73277',
    'key10822': 'value38738',
    'key62105': 'value67724',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Kara Black',
    'address': 'Unit 1187 Box 9482\nDPO AP 66615',
    'text': 'Even turn within white town say treatment. Various right only.\nCouple his training design those price despite never. Democrat new certain control business.',
    'email': 'dixoncolleen@example.net',
    'phone_number': '001-940-542-1505x0279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Huynh',
    'April Martin',
    'Casey Brock',
    'Emily Hernandez',
    'Carol Miller',
],
    'json': {
    'name': 'Carla Rogers',
    'address': '74401 Amanda Stream\nNorth Heather, NH 57327',
},
    'key36070': 'value2484',
    'key57563': 'value67069',
    'key73902': 'value85165',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Emily Moss',
    'address': '4185 Thomas Parkways Suite 830\nSouth Sarah, MO 90347',
    'text': 'Sort teacher wrong she. Discuss leave statement campaign magazine do information provide. Break family become open store energy figure.',
    'email': 'ernestwillis@example.com',
    'phone_number': '7586807250',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sean Lee',
    'Kristin Ward',
    'Brendan Garcia',
    'Michael Garcia',
    'Caleb Blair',
    'Crystal Walker',
    'Calvin Harris',
],
    'json': {
    'name': 'Michael Riley',
    'address': '692 Dickerson Rapid Suite 979\nScottton, MI 06891',
},
    'key53891': 'value23511',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Ms. Chloe Baird DVM',
    'address': '25988 Joshua Dam Apt. 461\nHunterland, CO 30478',
    'text': 'Religious protect beyond since identify explain usually. Teacher magazine law style already reach garden include. Leg address institution attorney.',
    'email': 'erikgilbert@example.org',
    'phone_number': '5644920499',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alexandra Pope',
    'Megan Ford',
    'Craig Evans',
],
    'json': {
    'name': 'Thomas David',
    'address': '5677 Cunningham Hollow\nNorth Jillchester, NY 12446',
},
    'key81063': 'value19794',
    'key37275': 'value34216',
    'key78103': 'value88749',
    'key53979': 'value14708',
    'key11917': 'value55785',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Tracy Garcia',
    'address': '87496 George Ville\nSouth Stevenburgh, NC 30643',
    'text': 'Compare drive now address large. Treat stock star next fill yourself. Commercial compare experience up.',
    'email': 'garciaedward@example.net',
    'phone_number': '(309)995-9193',
    'array_int_dynamic': [
    24726,
],
    'array_varchar_dynamic': [
    'Veronica Ross',
    'Jacob Hunt',
],
    'json': {
    'name': 'Lauren Kidd',
    'address': '8147 Wagner Branch\nMollyfurt, IN 91561',
},
    'key95495': 'value55879',
    'key25590': 'value44507',
    'key96996': 'value88494',
    'key18209': 'value25631',
    'key9927': 'value42722',
    'key35717': 'value70796',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Kiara Norris',
    'address': '281 Eric Gateway\nLake Monica, NH 22894',
    'text': 'Ground seven prevent identify three attorney. Outside it TV affect model ok.\nSouth party conference lay those spring. Issue foot head natural author prevent price.',
    'email': 'bsnyder@example.com',
    'phone_number': '(527)724-7017',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Powers',
    'Tara Flores',
    'Ian Gill',
],
    'json': {
    'name': 'Molly Blake',
    'address': '25249 Lynn Turnpike\nFergusonside, HI 62609',
},
    'key53114': 'value54086',
    'key10694': 'value71858',
    'key65734': 'value2529',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'David Wilson',
    'address': '776 Caleb Pines Apt. 127\nSouth Christopher, SD 80406',
    'text': 'Feeling meeting candidate decision daughter always prove up. Them meet development size best large cover break.\nComputer side spend. President which perform film win. Letter help drive miss.',
    'email': 'annettecox@example.net',
    'phone_number': '748-882-5975x0985',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Preston White',
    'Angela Harrison',
    'Erin Hernandez',
    'Walter Chen',
    'Andrew Stephens',
    'Timothy Jackson',
    'Dana Lopez',
    'Robert Clark',
],
    'json': {
    'name': 'Natalie Jones',
    'address': '396 Courtney Points Suite 290\nNorth Albert, CA 90363',
},
    'key48209': 'value64007',
    'key58891': 'value65366',
    'key49330': 'value86794',
    'key93839': 'value88692',
    'key53984': 'value93178',
    'key46924': 'value75741',
    'key83309': 'value75891',
    'key64322': 'value31322',
    'key56395': 'value82886',
    'key65155': 'value12461',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Brandon Rogers Jr.',
    'address': '2659 Samantha Square\nPort John, FM 43650',
    'text': 'Hundred sea hair wait up. Arrive benefit seek field throw.',
    'email': 'wallacetiffany@example.org',
    'phone_number': '001-522-404-4623x579',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Martinez',
    'Paula Delacruz',
    'Jessica Washington',
    'Duane Gibson',
],
    'json': {
    'name': 'Jill Crawford',
    'address': '7260 Mcdaniel Meadow\nVargasstad, NH 22018',
},
    'key47626': 'value17117',
    'key17936': 'value87258',
    'key25731': 'value99642',
    'key8848': 'value24898',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Marcus Moses',
    'address': '46968 Johnson Track\nNorth Laurenfurt, NM 68241',
    'text': 'Employee even laugh. Appear shoulder age. Carry letter action use.\nMarket position prepare piece anything.\nBehavior office serious mission individual across. Accept PM leg close indicate outside.',
    'email': 'xho@example.com',
    'phone_number': '001-755-406-2147',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Baker',
    'Rebecca Deleon',
    'Christy Roberts',
    'Emily Dodson MD',
],
    'json': {
    'name': 'Sarah Marks',
    'address': '851 Brown Canyon Apt. 651\nNew Stephen, AL 40696',
},
    'key55863': 'value99802',
    'key24903': 'value36313',
    'key86170': 'value87564',
    'key94462': 'value71553',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Dawn Hudson',
    'address': 'USS Lewis\nFPO AA 96485',
    'text': 'Rate mind evening woman. Store serve room still minute force.\nAdmit hair economic control gun more laugh.',
    'email': 'lorimartinez@example.net',
    'phone_number': '+1-379-269-1220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Delacruz',
    'David Fisher',
    'Regina Taylor',
    'Stanley Ramirez',
    'Megan Martin',
    'John Jimenez',
    'Daisy Lane',
    'Timothy Pope',
    'John Thompson',
],
    'json': {
    'name': 'Amy Fischer',
    'address': '660 Tonya Valleys Apt. 299\nSouth Robert, WV 81380',
},
    'key2469': 'value10088',
    'key30010': 'value81601',
    'key18286': 'value11058',
    'key42192': 'value21217',
    'key91061': 'value17783',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Jill Rodriguez',
    'address': '7586 Sanchez Avenue Suite 108\nMichaelfort, TX 25849',
    'text': 'Item tend certain when center. I whom detail. Happy kid seek debate.\nLand set foreign agency magazine yard. Difficult establish must focus pretty part. Best rise skill star only dark.',
    'email': 'jorge57@example.org',
    'phone_number': '(525)827-9328',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Santana',
    'James Figueroa',
    'Rachel Duarte',
    'Nicholas Guerrero MD',
    'Jared Soto',
],
    'json': {
    'name': 'Madeline Chavez',
    'address': '7444 Torres Hills\nKaylashire, MP 78750',
},
    'key79103': 'value602',
    'key22586': 'value78836',
    'key32651': 'value28412',
    'key846': 'value93407',
    'key83717': 'value6521',
    'key31700': 'value54753',
    'key68033': 'value42438',
    'key80787': 'value58846',
    'key3177': 'value60859',
    'key28462': 'value86013',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Ronald Parker',
    'address': '35457 Johnson Vista Suite 799\nDavidview, MT 08404',
    'text': 'Share successful continue question. Yes loss available go community. Around health door often discussion.\nAgainst buy impact usually fine fear go artist. Write whole main either along help right.',
    'email': 'mortonronnie@example.com',
    'phone_number': '001-596-363-4540x313',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Howard Yoder',
    'Michele Ramos',
    'Jared Kelly',
    'Devon Ward',
],
    'json': {
    'name': 'Stephanie Jones',
    'address': '250 Hartman Islands\nNew Robert, DE 32295',
},
    'key85468': 'value8793',
    'key15463': 'value98630',
    'key55794': 'value80088',
    'key90513': 'value95539',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kristina Brown',
    'address': '83311 Norris Circles\nAshleyside, NE 72032',
    'text': 'Role stand dog join much field use. Environment participant occur sing. Shake charge a from media argue until present.\nName discuss wall piece truth study themselves none. Grow next seek enjoy.',
    'email': 'amycurtis@example.com',
    'phone_number': '+1-801-369-6193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Julie Holloway',
    'Nicole Navarro',
    'Michael Vance',
    'Julia Lewis',
    'Sandra Smith',
    'Sarah Kelly',
    'Michael Johnson',
    'Wayne Schwartz',
    'Tracy Ruiz',
],
    'json': {
    'name': 'Heather Joseph',
    'address': '442 Mann Wall Suite 223\nNew Brian, WI 53835',
},
    'key31819': 'value46407',
    'key86180': 'value51845',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Sara Duran',
    'address': '3682 King Route\nSouth Deborahberg, CT 76242',
    'text': 'Inside wait perform. Table sit building happen boy. Against campaign property employee.\nThan west party concern. Establish blue high bring together smile.',
    'email': 'angelicachase@example.org',
    'phone_number': '001-739-859-2690x216',
    'array_int_dynamic': [
    65623,
],
    'array_varchar_dynamic': [
    'Caitlin Hill',
    'Grant Stewart',
    'Justin Johnson',
    'Jerry Duncan',
    'Brian Leon Jr.',
    'Dr. Charles Hale',
],
    'json': {
    'name': 'Jennifer Thompson',
    'address': '408 Pratt Glen Apt. 182\nChangport, MP 44307',
},
    'key84991': 'value66066',
    'key10655': 'value27716',
    'key52006': 'value95921',
    'key46715': 'value51397',
    'key23688': 'value80367',
    'key58268': 'value403',
    'key8557': 'value58479',
    'key81297': 'value5150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Charles Vasquez',
    'address': '55963 Rodriguez Island\nMcclurebury, KS 78611',
    'text': 'Understand both single discover purpose fish. Bill tend see institution.',
    'email': 'jeremywashington@example.net',
    'phone_number': '001-756-719-3973x16169',
    'array_int_dynamic': [
    45555,
],
    'array_varchar_dynamic': [
    'Kelly Weaver',
    'Jordan Martin',
    'Michael Estes',
    'Matthew Shaffer',
    'Tiffany Patterson',
    'Jose Galvan',
    'Jennifer Miller',
    'Edward Hunt',
],
    'json': {
    'name': 'Darren Daniels',
    'address': '6716 Carol Corner\nJosephfort, SC 36295',
},
    'key84554': 'value30561',
    'key5420': 'value20266',
    'key53493': 'value25906',
    'key38497': 'value55303',
    'key88072': 'value85074',
    'key43321': 'value36150',
    'key52572': 'value14746',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Jean Ferrell',
    'address': '828 Karen Course Apt. 219\nSouth Kimberlyside, AS 27281',
    'text': 'Best game director. Add turn management.\nIf everyone mouth assume. Choice war step bill thank.',
    'email': 'halllaurie@example.com',
    'phone_number': '6739986376',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Buck',
    'Ashley Barnett',
    'David Smith',
    'Nicole Lewis',
    'Adam Morrison',
    'Laura Walter',
    'Cynthia Johnson',
],
    'json': {
    'name': 'Nicholas Smith',
    'address': '9929 Robert Radial Suite 096\nCarterborough, IA 39539',
},
    'key43779': 'value41383',
    'key67902': 'value71415',
    'key31517': 'value2456',
    'key35463': 'value58400',
    'key90401': 'value27670',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Russell Weeks',
    'address': '384 Wilson Pike\nPort Jennifer, MP 26399',
    'text': 'Nature kind position very rather pressure poor.\nAround paper rest. Mean study law concern personal miss.',
    'email': 'christina67@example.com',
    'phone_number': '933-479-0880x824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Golden',
    'Mark Johnson',
    'Bradley Hale',
    'Mr. Derrick Porter DVM',
    'Tracy Gomez',
],
    'json': {
    'name': 'Sophia Boone',
    'address': 'PSC 1260, Box 8104\nAPO AP 26132',
},
    'key70543': 'value49968',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Micheal Mcdonald',
    'address': '578 James Wells\nWoodfort, WA 22926',
    'text': 'Operation dinner election. Foreign industry understand agency arrive ball election.',
    'email': 'fmorales@example.com',
    'phone_number': '752.228.9068x134',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Connie Rogers MD',
    'Terry Smith',
    'Matthew Moreno',
    'Amber Nelson',
    'Joshua Callahan',
    'Calvin Spencer',
],
    'json': {
    'name': 'Nicholas Galvan',
    'address': '783 Paul Ramp Apt. 910\nSouth Brettbury, MP 19013',
},
    'key53154': 'value59742',
    'key837': 'value13063',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Karen Kaiser',
    'address': '11030 Alexis Mountain Suite 989\nEast Kerri, RI 89636',
    'text': 'Both major nice catch. Table charge only thing really clearly direction. Ability ago prepare sound myself hit father left.\nStation those trade reveal. Us family price write.',
    'email': 'ronnie10@example.net',
    'phone_number': '(413)639-8515x9247',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Monica Jackson',
    'Adrian Herring',
    'Carrie Mendoza',
    'Erin Munoz',
    'Anthony Dalton',
],
    'json': {
    'name': 'Jeffrey Lyons',
    'address': '083 Christopher Mountain Suite 476\nWest Brianmouth, GA 64831',
},
    'key43092': 'value8902',
    'key73203': 'value86053',
    'key78126': 'value36649',
    'key73883': 'value9298',
    'key13477': 'value70316',
    'key18110': 'value79812',
    'key19731': 'value70949',
    'key32785': 'value81391',
    'key38243': 'value47889',
    'key58391': 'value12554',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v1/vector/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '56a23745-62f1-11f0-9519-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_00_589964GrwlycPl',
    'filter': 'uid >= 0',
    'limit': 100,
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
    'RequestId': '5745aaa3-62f1-11f0-aedb-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_00_589964GrwlycPl',
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
    'RequestId': '4fea9afb-62f1-11f0-b206-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_00_589964GrwlycPl',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752744913.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid01752744913Json()
    test.run_tests()
