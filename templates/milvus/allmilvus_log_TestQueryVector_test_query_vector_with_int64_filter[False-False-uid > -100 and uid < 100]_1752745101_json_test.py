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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752745101_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752745101.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid100AndUid1001752745101Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752745101.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752745101.json"
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
    'RequestId': 'bfc190cb-62f1-11f0-8702-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_38_08_225796uupywWcg',
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
    'RequestId': 'c2de2e35-62f1-11f0-989f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_38_08_225796uupywWcg',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Carol Pierce',
    'address': '1981 Edward Roads Suite 383\nNorth Philipview, MO 32632',
    'text': 'Stand she reduce prove movie leg. May with thought level stop. Collection surface tend item authority.',
    'email': 'twilliams@example.org',
    'phone_number': '001-498-822-9892x6798',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Laura Murphy',
    'Edward Donovan',
    'Joseph Roman',
    'Rachel Jones',
    'Nicole Novak',
    'Mr. Ethan Schneider Jr.',
    'Jesse Murray',
    'Lacey Shea',
],
    'json': {
    'name': 'Cheryl Santiago',
    'address': '4161 Jeffery Locks\nSouth Keithhaven, MI 56890',
},
    'key86566': 'value43457',
    'key23332': 'value65441',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Richard Ramos',
    'address': '8796 Stewart Street\nLake Michael, RI 15543',
    'text': 'Break since great bank education you. Their election already staff partner. Everybody only card check word. Network drive arm include off church right.',
    'email': 'mendozamarco@example.com',
    'phone_number': '448.592.7074',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Sosa',
    'Nancy Kirk',
    'Nicole Sanchez',
    'William Thomas',
    'Mark Reynolds',
],
    'json': {
    'name': 'Jessica Grimes',
    'address': '80547 Joel Curve\nEast Kristin, OK 24791',
},
    'key7805': 'value33926',
    'key59696': 'value27082',
    'key46707': 'value3664',
    'key32903': 'value96211',
    'key72583': 'value45050',
    'key97054': 'value42905',
    'key57662': 'value25897',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Cynthia Moreno',
    'address': '11032 Vanessa Lane\nJameshaven, KY 18499',
    'text': 'Total end southern word. Bit determine claim drug energy reality sometimes.\nDo strategy safe mind town over yet. Difference into story feeling second.\nHer will section explain.',
    'email': 'luis54@example.com',
    'phone_number': '(367)204-0826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mario Hopkins',
    'Olivia Choi',
    'Ronald Schroeder',
    'Russell Smith',
    'Jessica Carter',
    'Alejandra Douglas',
    'Christopher Logan',
],
    'json': {
    'name': 'Jerry Richardson',
    'address': 'PSC 1856, Box 3817\nAPO AP 52867',
},
    'key34730': 'value99223',
    'key54660': 'value4928',
    'key62208': 'value28291',
    'key48923': 'value92988',
    'key57614': 'value7760',
    'key94939': 'value38648',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Emily Bowman',
    'address': '229 Curry Flat Apt. 284\nJacksonberg, NH 87775',
    'text': 'Pm blue reality. Very side sea pressure.\nTown out through soon investment suffer.\nProtect full than them others good. Sound inside dinner television never. See simple future writer.',
    'email': 'lindseyian@example.net',
    'phone_number': '613-503-6106x42763',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Paula Ramirez',
    'Russell Ramirez',
    'Megan Benton',
],
    'json': {
    'name': 'Jordan Holmes',
    'address': '71790 Bobby Corner\nSouth Robert, AS 51387',
},
    'key3965': 'value24456',
    'key40484': 'value4385',
    'key54438': 'value39714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Caleb Boyd',
    'address': '979 Ruiz Inlet\nNorth Ryanside, IA 37851',
    'text': 'Loss claim maybe phone our simply. Realize work exist participant until. Remain back join dinner kitchen.',
    'email': 'wwilson@example.org',
    'phone_number': '561.940.4203x855',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Clarence Pruitt',
    'Dawn Payne',
    'Erica Harvey',
    'Timothy Stephens',
    'Sierra Moore',
    'Samuel Ramos',
    'Lauren Jackson',
],
    'json': {
    'name': 'Tammy Hendrix',
    'address': '78831 Diaz Shore\nNew Lisa, CA 14215',
},
    'key99913': 'value59014',
    'key34142': 'value37238',
    'key40911': 'value76430',
    'key28323': 'value31830',
    'key33027': 'value76667',
    'key21996': 'value36746',
    'key71475': 'value52112',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Shelly Hancock',
    'address': '009 Vega Islands\nWest Michelleville, GA 81505',
    'text': 'Continue treat vote how serious.\nAmong feel lay family him. Line price public not agree pay turn. Cold much order remain.',
    'email': 'steven58@example.com',
    'phone_number': '869.244.3878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kathy Vasquez',
    'Michael Schultz',
    'Sheila Jones',
    'Alexis Maxwell',
    'Jennifer Carlson',
    'Kathleen Burnett',
    'Nancy Kelly',
    'Laura Pacheco',
    'Kim Underwood',
    'Daniel Sanchez',
],
    'json': {
    'name': 'Edward Mata',
    'address': '67013 Michelle Keys\nNew Davidburgh, WI 44110',
},
    'key55429': 'value84527',
    'key71689': 'value78183',
    'key11209': 'value22034',
    'key54620': 'value48629',
    'key23750': 'value85520',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Sara Miller',
    'address': '2958 Gomez Station Suite 244\nStonemouth, LA 59184',
    'text': 'Success organization party response necessary. Sport option think sort. Protect what sense easy institution himself his take.\nGreat dark structure truth goal lead nice.',
    'email': 'omoreno@example.com',
    'phone_number': '729-803-5676',
    'array_int_dynamic': [
    17677,
],
    'array_varchar_dynamic': [
    'Kelly Ponce',
    'Katrina Ray',
    'Roy Foster',
    'Andrew Long',
    'Timothy Levine',
    'Nicole Baker',
    'Matthew Harvey',
    'Kristine Hoffman',
],
    'json': {
    'name': 'Brian Elliott',
    'address': '714 Hale Circle Suite 206\nCordovamouth, MN 07950',
},
    'key11662': 'value6191',
    'key24119': 'value79599',
    'key94966': 'value40205',
    'key3612': 'value23538',
    'key61996': 'value83160',
    'key12257': 'value40670',
    'key37674': 'value71371',
    'key80979': 'value15829',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Brian Lawrence',
    'address': '33693 Gregory Plains Suite 045\nBrandybury, PW 29526',
    'text': 'Able take third decide. Woman ready fill dog admit under. Sell always interesting. Hair challenge section season growth study.\nPiece fill pick affect about development. Kid work only until.',
    'email': 'zsantiago@example.com',
    'phone_number': '001-911-667-0116x4180',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robert Moon',
    'Stacey Molina',
    'Robert Ellis',
    'Tony Chaney',
    'Keith Salinas',
    'Shelby Durham',
    'Molly Nguyen',
],
    'json': {
    'name': 'Walter Walker',
    'address': '903 Holloway Wells Suite 957\nLake Erikstad, IL 16807',
},
    'key73211': 'value58833',
    'key32214': 'value27482',
    'key36303': 'value44161',
    'key38055': 'value60816',
    'key40757': 'value12973',
    'key75786': 'value85132',
    'key10945': 'value59178',
    'key28791': 'value53723',
    'key58580': 'value88995',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'John James',
    'address': '0177 Carlos Stravenue Apt. 493\nTimothyborough, WY 28826',
    'text': 'Series by help again newspaper capital. Keep book once rich represent same. Happy them kitchen early.\nRecord range kid right for southern. Course staff nature defense education stand record.',
    'email': 'blester@example.net',
    'phone_number': '(975)888-8213x2889',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tanya Chan',
    'Matthew Berg',
    'Sarah Foster',
    'Matthew Hernandez',
],
    'json': {
    'name': 'John Stewart',
    'address': '363 Kevin Forks\nLake Danielburgh, NE 51264',
},
    'key18182': 'value68179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Katie Smith',
    'address': '0670 Hall Ridges\nBradyshire, AS 62068',
    'text': 'Either prepare become total. Head news visit child image just product.',
    'email': 'aaron99@example.net',
    'phone_number': '001-743-980-5621x03686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Byrd',
    'Karen Ross',
],
    'json': {
    'name': 'Regina Mercer',
    'address': '58021 Thomas Loaf Suite 894\nGarrettchester, WI 73361',
},
    'key97234': 'value63594',
    'key86611': 'value27254',
    'key58231': 'value92069',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Alexandria Kim',
    'address': '760 Love Trail Suite 641\nBrittanyborough, CT 05667',
    'text': 'Language boy account data small happen usually matter. Window state shoulder particularly shoulder ok. Reach military performance president military two factor.',
    'email': 'owalker@example.net',
    'phone_number': '860-768-0443',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Hanson',
    'Erica Fox',
    'Jessica Lee',
    'William Kelly',
],
    'json': {
    'name': 'Sarah Meadows',
    'address': '917 Cruz Crest\nWebsterside, WI 42931',
},
    'key16432': 'value35072',
    'key23629': 'value70110',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Paul Adams',
    'address': '573 Chloe Drives\nKristinmouth, WV 26382',
    'text': 'Ground high woman race now today activity. Film finally itself.',
    'email': 'fmcdonald@example.org',
    'phone_number': '530.438.3320x463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Paul Brown',
    'Daniel Smith',
    'Steven Reese',
    'Matthew Valdez',
    'Erin Downs',
    'Eric Roberts',
    'Jessica King',
],
    'json': {
    'name': 'James Davis',
    'address': '366 Alicia Cliff\nJohnton, CA 64635',
},
    'key74469': 'value85047',
    'key3079': 'value50115',
    'key1133': 'value3445',
    'key41641': 'value8774',
    'key23930': 'value20704',
    'key30823': 'value21954',
    'key65768': 'value43561',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Gabriel Murphy',
    'address': '5175 Wallace Viaduct\nPennyview, WA 61741',
    'text': 'Account policy free nor enjoy common staff nice. Near successful reason such.\nGo everybody he sound store resource stay collection. Which cold blue politics.\nEvery level if player. Might miss be any.',
    'email': 'christophermendoza@example.org',
    'phone_number': '752-336-8153x35343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Abigail Gibson',
    'Breanna Chen',
    'Christopher Vaughn',
    'Tara Hood',
    'Michelle Miller',
    'Debra Glenn',
    'Andrea Monroe',
    'Richard Brock',
    'Charles Faulkner',
],
    'json': {
    'name': 'Brian Davis',
    'address': '6559 Alex Field\nCassandraland, TX 29327',
},
    'key6256': 'value33663',
    'key22214': 'value28004',
    'key13460': 'value90306',
    'key53757': 'value65698',
    'key27675': 'value5892',
    'key83465': 'value23570',
    'key2852': 'value25244',
    'key14213': 'value5358',
    'key28034': 'value14673',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Mitchell Hansen',
    'address': '461 Harper Turnpike\nNewmanfort, NE 79761',
    'text': 'Crime American test resource often.\nIssue north green moment loss reduce least. Recognize sign institution exactly democratic person. Mrs speech dinner.',
    'email': 'williamsamber@example.net',
    'phone_number': '001-446-485-1174x74495',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brett Turner',
    'Joe Combs',
    'Gregory Sparks',
],
    'json': {
    'name': 'Alicia Williams',
    'address': '50535 Taylor Track Suite 590\nEast Richardland, MD 41792',
},
    'key87942': 'value72771',
    'key69836': 'value17154',
    'key24083': 'value6884',
    'key60741': 'value16978',
    'key76864': 'value2891',
    'key4181': 'value73063',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Morgan Collins',
    'address': '56312 Craig Track Suite 643\nJamesmouth, HI 45127',
    'text': 'Still central leg face detail bank. Usually deep coach career.\nJob himself city inside statement each whatever. Return manager or area president reveal. Learn woman may ability later think should.',
    'email': 'john91@example.com',
    'phone_number': '(991)600-3621x69431',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lee Harrison',
    'Arthur Brown',
    'Shawn Crawford',
    'Jonathon Evans',
    'Travis Spencer',
    'Kyle Miller',
    'Mrs. Cynthia Wright',
    'Jennifer Moore',
],
    'json': {
    'name': 'Peter Buckley',
    'address': '393 Paul Knolls Apt. 225\nEast Marcoton, NC 19721',
},
    'key96915': 'value4648',
    'key22722': 'value34809',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'James Booth',
    'address': '4920 Matthew Lock\nGarciahaven, IA 55463',
    'text': 'Human use their hour thus. Perform get week season far. Movement beyond minute meet eye town.\nScientist stay stock thus now page include media.',
    'email': 'lisadixon@example.org',
    'phone_number': '(482)309-3193x163',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Hayley Lee',
],
    'json': {
    'name': 'Shelby Collins',
    'address': '49329 Dixon Views\nLake Victoriaside, DE 29211',
},
    'key79553': 'value21875',
    'key40305': 'value39721',
    'key38747': 'value50330',
    'key61747': 'value51867',
    'key38948': 'value37950',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Matthew Taylor',
    'address': '7448 Edwards Radial\nBrennanburgh, NV 85158',
    'text': 'Quality soon truth short eye few. Improve break maybe. Team spend heart them experience way city low.\nUs candidate interesting maintain. Wait shoulder administration eye.',
    'email': 'jonesseth@example.com',
    'phone_number': '923-557-9910x238',
    'array_int_dynamic': [
    43749,
],
    'array_varchar_dynamic': [
    'Dennis Moore',
    'David Rodriguez',
    'Richard Adams',
    'Justin Martinez',
    'Emily Boyd',
],
    'json': {
    'name': 'Nicole Cannon',
    'address': 'Unit 6813 Box 1642\nDPO AA 80937',
},
    'key49597': 'value74999',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Rhonda Wong',
    'address': '6262 Christopher Hills\nNew Thomas, AZ 92496',
    'text': 'Traditional responsibility bring church big some over even. Nor however paper seem. Gun political music instead read down music.',
    'email': 'brownchristine@example.net',
    'phone_number': '(727)944-9069x864',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jill Bullock',
    'Christopher Murillo',
    'Carol Matthews',
    'Dustin Bishop',
],
    'json': {
    'name': 'Samuel Perez',
    'address': '616 Andrew Freeway Apt. 497\nJamiechester, VA 97386',
},
    'key42052': 'value72527',
    'key88918': 'value60884',
    'key71902': 'value71869',
    'key53724': 'value52935',
    'key57486': 'value35793',
    'key96398': 'value89791',
    'key29896': 'value96557',
    'key11647': 'value1421',
    'key74126': 'value3929',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Albert Molina',
    'address': '3760 Karen Causeway\nSextonmouth, KS 81264',
    'text': 'Maybe born sister present. Record student professional should difficult open. Those share describe well audience.',
    'email': 'ruth05@example.net',
    'phone_number': '001-805-826-5213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jason Williams',
    'Haley Rodriguez',
    'Kayla Mata',
    'Craig Hill',
    'Amber Reed',
    'Rhonda Golden',
    'Jason Cooper',
],
    'json': {
    'name': 'David Anderson',
    'address': '35095 Clark Prairie Apt. 062\nPort Samantha, NE 12008',
},
    'key26192': 'value19557',
    'key27480': 'value26425',
    'key7883': 'value95933',
    'key34581': 'value37136',
    'key37715': 'value85462',
    'key49801': 'value40717',
    'key42358': 'value44863',
    'key89410': 'value3873',
    'key95170': 'value34607',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Dr. Cody Escobar',
    'address': '622 Curtis Lakes Suite 778\nNorth Nicolebury, NV 24968',
    'text': 'Town term establish source itself late occur tonight. Family base value make ever up.\nExactly age morning on. Say world feeling song explain character. Agent turn into focus people operation because.',
    'email': 'gabrielgraham@example.net',
    'phone_number': '237-451-2104',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Chandler',
    'Matthew Garcia',
    'Isabel Martin',
    'Megan Steele',
    'Charles Lin',
],
    'json': {
    'name': 'Todd Martinez',
    'address': 'PSC 3899, Box 4747\nAPO AE 13143',
},
    'key27148': 'value35192',
    'key54010': 'value21100',
    'key56186': 'value66176',
    'key14366': 'value90095',
    'key89907': 'value22160',
    'key78505': 'value30676',
    'key9382': 'value97761',
    'key58783': 'value39733',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Joseph Davis',
    'address': '530 Melanie View\nHarrisonborough, IA 19846',
    'text': 'Article base assume anything special read whether. Trade process plant property. Popular experience work develop.\nBlue around you a. Age less my ten. Third program hard care whom others.',
    'email': 'houstonjoseph@example.net',
    'phone_number': '(375)508-6471x39145',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jessica May',
    'Melissa Zimmerman',
    'Jean King',
    'Anna Garner',
],
    'json': {
    'name': 'Jamie Carr',
    'address': '64448 Garza Manors\nJosephfurt, FM 65051',
},
    'key48732': 'value40763',
    'key31125': 'value45026',
    'key45765': 'value36806',
    'key98374': 'value94330',
    'key9132': 'value9876',
    'key7498': 'value35585',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jordan Stewart',
    'address': '65234 Cook Burg\nBennettfort, GU 39167',
    'text': 'Matter into education street mother central. Medical cost how development character. Else third threat catch act late care. Ok want suffer consumer.',
    'email': 'brittany07@example.net',
    'phone_number': '732.744.0080x87248',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jack Pacheco',
    'Natasha Ramirez',
    'Amanda Baker',
    'Lindsay Baker',
    'Emily Mack',
],
    'json': {
    'name': 'Erik Webb',
    'address': '37306 Michael Mission\nLake Michael, WY 27593',
},
    'key8176': 'value46630',
    'key29237': 'value94662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Danielle Powell',
    'address': '14871 Jackson Springs\nEast Victoria, MT 62240',
    'text': 'Ahead training yeah reason find today toward.\nDescribe treat difference around. Whom green opportunity race guess. Start affect see hope.',
    'email': 'royroy@example.com',
    'phone_number': '001-977-877-0843',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Javier Guzman',
    'Joshua Stephens',
    'Rodney Nichols',
    'David Davis',
    'Dr. Anthony Smith',
    'Charles Flores',
    'Matthew Newton',
],
    'json': {
    'name': 'Jason Green',
    'address': '46942 Beck Knolls Apt. 372\nNew Vincentfurt, NH 84390',
},
    'key80180': 'value73376',
    'key56177': 'value58072',
    'key7780': 'value39626',
    'key34683': 'value82746',
    'key46951': 'value55021',
    'key16244': 'value54781',
    'key66743': 'value88954',
    'key29363': 'value14052',
    'key68005': 'value56035',
    'key56811': 'value83415',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Dr. Alexis Harris DDS',
    'address': '1454 Donna Corner Suite 020\nScottville, CO 14105',
    'text': 'Later thus white away evening. Fund once either serious how.\nBenefit the away guy. Before if work kind any camera. Himself risk claim reveal.\nAnyone guy hotel wide likely.',
    'email': 'simsdawn@example.net',
    'phone_number': '674.853.4989x01531',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ms. April Waller',
    'Christine Becker',
    'Pamela Diaz',
    'Bruce Chen',
    'Veronica Pierce',
    'Robert Watts',
    'Ernest Lester',
    'Steven Caldwell',
],
    'json': {
    'name': 'Tara Espinoza',
    'address': '9517 Duncan Pass Apt. 704\nErikstad, WI 13338',
},
    'key3609': 'value42866',
    'key66273': 'value80023',
    'key31764': 'value57966',
    'key14991': 'value18612',
    'key59750': 'value62042',
    'key9918': 'value80949',
    'key72246': 'value97966',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Vanessa Green',
    'address': '44688 Joseph Branch\nPort Kim, TX 37309',
    'text': 'Wish camera sure buy. Customer number ahead appear physical anyone. Kid job thank gun.\nTake usually child room hour. On card to occur decade. Character after democratic right.',
    'email': 'bpatel@example.com',
    'phone_number': '2432505155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Bryant',
    'Eric Howard',
    'Marcus Christian',
    'Jonathan Wilson',
    'Alexander Harper',
    'Kelly Davidson',
],
    'json': {
    'name': 'Brian Medina',
    'address': '434 Gomez Union\nCastroview, ME 68509',
},
    'key61355': 'value63197',
    'key2932': 'value52234',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Cynthia Harrison',
    'address': '664 Underwood Pike\nCarsonfurt, KY 42262',
    'text': 'Defense particular grow successful second career oil piece. Way article himself. Call guy brother.',
    'email': 'mpugh@example.com',
    'phone_number': '8203387923',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Boyd',
    'Katherine Gonzalez',
],
    'json': {
    'name': 'Crystal Davis',
    'address': '31986 Dawn Stream Suite 580\nBiancashire, CT 27238',
},
    'key60616': 'value25471',
    'key57605': 'value4521',
    'key63832': 'value56946',
    'key44646': 'value49455',
    'key25301': 'value14991',
    'key53722': 'value3646',
    'key20572': 'value87298',
    'key3563': 'value31914',
    'key23483': 'value15587',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Frank Horn',
    'address': '646 Delgado Stravenue Suite 283\nNorth Kylemouth, AK 46871',
    'text': 'Worry dark court yeah people card. Civil those decide she practice dream American couple. Spring rule performance.\nTrade beat catch single which. Break per point blood tree sit.',
    'email': 'jacqueline44@example.com',
    'phone_number': '7545446396',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Paige Anderson',
    'Holly Ramirez',
    'Michael Jimenez',
    'Kathryn Hughes',
],
    'json': {
    'name': 'Lori Green',
    'address': '1767 Williams Village\nEvansstad, WY 90057',
},
    'key20787': 'value26698',
    'key98304': 'value87842',
    'key41119': 'value40883',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Morgan Gonzales',
    'address': '890 Juan Plains Apt. 118\nDanaburgh, NV 71610',
    'text': 'General phone already child each scientist modern six. Return actually particularly stock into. Somebody the their either. Agree computer prepare test especially scientist another.',
    'email': 'madelinegonzales@example.com',
    'phone_number': '580.242.9219',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Powell',
    'Crystal Rojas',
    'Timothy Roberts',
],
    'json': {
    'name': 'Eric Conway',
    'address': '1755 Allison Throughway Suite 411\nPort Karina, CA 36694',
},
    'key7090': 'value99416',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Kimberly Davis',
    'address': '66575 Michael Walk\nNorth Shannontown, SD 41222',
    'text': 'Much win people partner eye. Because official camera whole arm attention common. Factor at friend dinner difficult goal. Young difference attorney.',
    'email': 'jenna50@example.org',
    'phone_number': '+1-882-428-9792x595',
    'array_int_dynamic': [
    25807,
],
    'array_varchar_dynamic': [
    'Samantha Waters',
    'Edward Dorsey',
    'John Valdez',
    'Robert Baker',
    'Deborah Thomas',
    'Austin Sanford',
    'Daniel Mullins',
    'Brian Ruiz',
    'Aimee Jones',
    'Cheryl Jenkins',
],
    'json': {
    'name': 'Raymond Rodriguez',
    'address': '3711 Hanson Brook Apt. 506\nPort Stephanie, FM 61741',
},
    'key57337': 'value33304',
    'key51229': 'value96257',
    'key69346': 'value42566',
    'key34397': 'value82358',
    'key2328': 'value35219',
    'key99812': 'value3428',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Deborah Neal',
    'address': '65712 Valdez Station Suite 992\nJacobberg, NJ 42533',
    'text': 'None number relationship job. North compare before peace above interest sea economy.\nThat reach world yes assume.',
    'email': 'gomezsteven@example.net',
    'phone_number': '959.926.4741x5964',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Ashley',
    'Jeremy King',
    'Barbara Nichols',
    'Stephanie Ingram',
    'Catherine Jones',
    'Melissa Smith',
    'Christopher Rodriguez',
    'Jeff Robinson',
    'Stephanie Hawkins',
],
    'json': {
    'name': 'John Harrington',
    'address': '10977 Castillo Springs Suite 642\nLake Ryan, MA 36140',
},
    'key28189': 'value40805',
    'key99794': 'value62337',
    'key94203': 'value32089',
    'key34955': 'value9880',
    'key64840': 'value80130',
    'key584': 'value30838',
    'key15928': 'value25436',
    'key81094': 'value79111',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Patricia Arnold',
    'address': '9772 Davis Turnpike Suite 489\nRaymondshire, GA 24111',
    'text': 'Campaign serve find police do site. Maintain method term factor rate several.\nDrive successful reduce. Among my anything various. Drop vote half traditional.',
    'email': 'travisbenson@example.org',
    'phone_number': '(913)672-4328x03956',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Marshall',
    'Joshua Clayton',
    'Stacey Zavala',
    'Willie Johnson',
    'Tiffany Dennis',
    'Adam Roberts',
    'Taylor Gutierrez',
    'Krystal Costa',
],
    'json': {
    'name': 'Michele Pitts',
    'address': 'PSC 2418, Box 6510\nAPO AE 56436',
},
    'key2231': 'value60871',
    'key92578': 'value22211',
    'key28311': 'value11128',
    'key84472': 'value30720',
    'key83427': 'value35504',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Robert Jordan',
    'address': '35097 Faith Track\nNorth Eric, OR 14740',
    'text': 'Knowledge increase model cold despite growth hundred. Late set fund pick collection. Choice minute half party sell.\nEvery feel husband bad current boy sign against. Surface drug social mean look.',
    'email': 'mfisher@example.com',
    'phone_number': '576-700-3404',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Chad Sanford',
    'Laura Schneider',
],
    'json': {
    'name': 'Sharon Dalton',
    'address': '9460 Barrett Landing Suite 080\nBrownbury, TX 85270',
},
    'key2520': 'value48748',
    'key10545': 'value57445',
    'key62568': 'value46530',
    'key81444': 'value82321',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Brian Williams',
    'address': '464 Charles Groves Apt. 390\nCrawfordborough, NV 97493',
    'text': 'Everything child next system worry.\nThan course Democrat smile cold investment economic open. Worker traditional interview according city feel.\nTry near create movie guy.\nDrive would usually offer.',
    'email': 'awebster@example.net',
    'phone_number': '5664509605',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Smith',
    'Erica Johnson',
    'Sean Barker',
    'Brandi Walker',
    'Renee Robinson',
    'Joel Mcdaniel',
    'Trevor Salazar',
    'Michael Moyer',
],
    'json': {
    'name': 'Maria Sandoval',
    'address': '3713 Jackson Rue\nLake Christine, ME 61966',
},
    'key32122': 'value99013',
    'key67794': 'value72533',
    'key17763': 'value42812',
    'key65411': 'value16258',
    'key3900': 'value63548',
    'key25850': 'value28294',
    'key133': 'value89130',
    'key31837': 'value50066',
    'key37697': 'value61153',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Nicole Sims',
    'address': '68634 Steven Causeway Suite 506\nWhitebury, AS 75780',
    'text': 'Something over commercial clearly movie free. Treat order body pretty three. Indicate involve simply station professional modern.',
    'email': 'stevenhart@example.org',
    'phone_number': '(615)736-6581x74928',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Robertson',
],
    'json': {
    'name': 'Joshua Doyle',
    'address': '4518 Michael Locks Apt. 875\nDominguezstad, KY 88282',
},
    'key93423': 'value78636',
    'key76108': 'value26432',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Kristi Vasquez',
    'address': '1101 Aaron Club\nNew Andrew, AZ 77935',
    'text': 'Resource black remember eat pattern. Red crime attack challenge wonder.\nWithout able sometimes sure art modern family. Maybe cost election choice add. Report writer moment should act.',
    'email': 'jeffreygalloway@example.org',
    'phone_number': '001-715-958-9863x98295',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Long',
    'Nathan Mack',
    'Tracy Butler',
    'Theresa Ferguson',
    'Robert Jones',
    'Jessica Lee',
    'Richard Ruiz',
    'Kevin Hinton',
],
    'json': {
    'name': 'Bryan Eaton',
    'address': '743 Allen Springs\nEast James, IL 45159',
},
    'key40528': 'value28260',
    'key27': 'value38561',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Megan Ramirez',
    'address': '34165 Kimberly Avenue\nCallahanside, CT 33409',
    'text': 'Or environment rock thought material cover weight. Run evidence something.',
    'email': 'wendywinters@example.com',
    'phone_number': '001-463-231-2215x8818',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Martinez',
    'Cindy Anderson MD',
    'Scott Obrien',
    'Laura Huynh DVM',
    'Carmen Thomas',
    'David Dillon',
    'Christopher Holt',
],
    'json': {
    'name': 'Kathleen Jackson',
    'address': '955 Williams Lake\nPort Marilynchester, VA 20985',
},
    'key47798': 'value29594',
    'key28226': 'value77851',
    'key50006': 'value255',
    'key19127': 'value31247',
    'key72237': 'value68395',
    'key16895': 'value25188',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Savannah Miller',
    'address': '92944 Thomas Extensions Suite 118\nLake Cynthiamouth, NY 96463',
    'text': 'Similar protect support drop make. In if value seem purpose only quickly. Environmental forget interview far organization.',
    'email': 'krista29@example.org',
    'phone_number': '001-751-853-1673',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Emily Hall',
    'Jamie King',
    'Joanna Nolan',
    'Jennifer Thornton',
    'Alexandra Watson',
    'Susan Nolan',
    'Marilyn Graves',
    'Steven Carter',
],
    'json': {
    'name': 'Nathan Smith',
    'address': '949 Thompson Pines\nSouth Elizabethmouth, OK 01830',
},
    'key7431': 'value17736',
    'key93360': 'value35750',
    'key85870': 'value54479',
    'key42146': 'value2795',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Kyle Holland',
    'address': '24286 Rachel Squares\nWest Charleneshire, HI 02654',
    'text': 'My activity song. Capital police add save simple prevent. Same management heart style value level dinner feeling. There eye beautiful best research.',
    'email': 'thomas67@example.com',
    'phone_number': '001-711-577-3622x173',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Anderson',
    'Christopher Smith',
    'Justin Estrada',
    'Peter Williams',
    'Jason Patel',
    'Matthew Jones',
    'Elizabeth Richardson',
],
    'json': {
    'name': 'Katherine Owens',
    'address': '0199 Kim Wall\nPort Christopherfort, MP 63100',
},
    'key63783': 'value83202',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Amanda Rios',
    'address': '89802 Colin Summit Apt. 033\nNorth Michael, TX 13234',
    'text': 'Thank strong account attack. Commercial economic development threat. Clear question wife beat great.\nInstitution out lay later. Goal real today still loss admit action.',
    'email': 'vhall@example.org',
    'phone_number': '001-582-275-8802x22792',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Miller',
    'Troy Parker',
    'Donna Bridges',
    'Donald Cunningham',
    'Ryan York',
    'Caroline Miller',
    'Stephen Pitts',
    'Diana Taylor',
],
    'json': {
    'name': 'Regina Valentine',
    'address': '0156 Richard Corners\nSwansonfort, DC 44715',
},
    'key63570': 'value71233',
    'key39190': 'value89036',
    'key36788': 'value40178',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Carlos Sherman',
    'address': '869 Aguilar Mission Suite 358\nNew Hannah, AS 55712',
    'text': 'Nearly brother nothing war result everyone capital. Meeting will gas best another nothing.',
    'email': 'chrisbauer@example.com',
    'phone_number': '623.753.7496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jason Reese',
    'Dawn Collins',
],
    'json': {
    'name': 'Derrick Hernandez',
    'address': '2065 Harper Pass\nPort Johnstad, NV 86824',
},
    'key27886': 'value56816',
    'key16728': 'value17793',
    'key75087': 'value88896',
    'key34361': 'value29305',
    'key60703': 'value95562',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Shannon Moore',
    'address': 'Unit 1980 Box 1058\nDPO AE 86228',
    'text': 'Likely receive population conference. Mean study now play member on politics. Bank let child when resource.',
    'email': 'nixonpatricia@example.org',
    'phone_number': '(696)845-7045x02415',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Stone',
],
    'json': {
    'name': 'Terry Ramirez',
    'address': '880 Bowman Route Suite 433\nGuzmanport, FL 08522',
},
    'key1929': 'value9390',
    'key52444': 'value94255',
    'key28885': 'value64441',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Hannah Flynn',
    'address': 'USS Rodriguez\nFPO AA 77380',
    'text': 'Free company western instead plan couple want. Civil language could. Which test well eight. Company cup know step consider even.',
    'email': 'roberto18@example.com',
    'phone_number': '964-884-8044x37202',
    'array_int_dynamic': [
    30239,
],
    'array_varchar_dynamic': [
    'David Smith',
    'Vanessa Fleming',
    'Amber Rhodes',
    'Ryan Donaldson',
    'Donna Medina',
    'Jonathan Garcia',
],
    'json': {
    'name': 'Terrance Pollard',
    'address': 'USNS Russo\nFPO AP 22541',
},
    'key94125': 'value11131',
    'key99548': 'value2356',
    'key25837': 'value69025',
    'key65103': 'value29190',
    'key87893': 'value37359',
    'key79513': 'value68827',
    'key49182': 'value86213',
    'key32374': 'value85378',
    'key23281': 'value27270',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Julie Norton',
    'address': '62444 Jennifer Run\nSouth William, MO 56314',
    'text': 'World nice these listen. Suggest book remember main million. Result tree red interest. Inside expert parent particularly.',
    'email': 'patrick00@example.com',
    'phone_number': '363.659.2705',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Zimmerman DDS',
    'Alex Hunt',
    'Misty Riley',
    'Donna Bryant',
    'Jeffrey Ho',
    'Michael Mathis',
    'Michael May',
],
    'json': {
    'name': 'Linda Nolan',
    'address': 'Unit 1458 Box 9384\nDPO AA 29243',
},
    'key25384': 'value97431',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Christine Levine',
    'address': '3531 Steven Lodge\nEast Sean, KS 51314',
    'text': 'Get now bill girl doctor improve condition debate. According from old no. War summer measure.',
    'email': 'michaelaobrien@example.net',
    'phone_number': '891.367.2911x0027',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Henry',
    'David Pace',
    'Lauren Bender',
    'Dawn Hunter',
    'Randy Byrd',
    'Jay Patton',
    'Anthony Fleming',
    'Shari Green',
    'Kevin Shelton',
],
    'json': {
    'name': 'Erin Winters',
    'address': '9055 Daniel Road\nRichardmouth, MP 06758',
},
    'key70976': 'value46287',
    'key3934': 'value2843',
    'key76049': 'value13665',
    'key73771': 'value95965',
    'key82228': 'value23669',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Kenneth Kerr',
    'address': '95687 Justin Shoals\nNew Bobbybury, NY 70446',
    'text': 'Be shoulder threat young onto treat owner indeed. Then hotel different with for happy.\nHow even run offer easy. Wear really arm another share hospital report.',
    'email': 'jeremyperry@example.com',
    'phone_number': '292-928-3715x33929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Walsh',
    'Scott Williams',
    'Chelsea Gibson',
    'Brenda Jackson',
    'Teresa Pearson',
    'Christopher Kerr',
    'Dr. David Arnold',
    'Cindy Morse',
    'Kelly Villanueva',
],
    'json': {
    'name': 'Mr. Scott Johnson',
    'address': '66779 Brittany Cliff Suite 387\nReedport, DC 43797',
},
    'key32821': 'value32038',
    'key3366': 'value58781',
    'key61642': 'value67680',
    'key9955': 'value66962',
    'key86812': 'value67790',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Michael Hudson',
    'address': '03489 Andrea Pines Suite 077\nCastilloport, IN 65701',
    'text': 'Art center mean land. Letter conference common carry finally. Statement poor whole teacher skill pay present and. Per beat strategy he job particular half wall.',
    'email': 'michelle94@example.com',
    'phone_number': '767.651.7373x3760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Lam',
    'Peter Hall',
],
    'json': {
    'name': 'Andre Crawford',
    'address': '1599 Olson Spring Apt. 216\nPort Meghanville, NM 84769',
},
    'key85627': 'value55428',
    'key38922': 'value13352',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Rebecca Hughes',
    'address': '93785 Dodson Pines\nLake Jason, MH 67429',
    'text': 'Enjoy hospital military authority level. Talk give offer. Interesting college else reflect again.\nLess see week now rich major. Letter key would they hair notice entire. Yet our material.',
    'email': 'lisavasquez@example.org',
    'phone_number': '001-281-327-8580x1531',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Miller',
    'James Melton',
    'Thomas Aguilar',
    'Katherine Hobbs',
    'Barry Hill',
    'Michael Foley',
    'Edgar Wilson',
    'Jessica Alvarez',
    'Ann Gay',
    'Robert Bruce',
],
    'json': {
    'name': 'Benjamin Robinson',
    'address': '881 Joshua Parkways Suite 527\nNew Lisafurt, AS 72030',
},
    'key70898': 'value39686',
    'key92126': 'value25474',
    'key17124': 'value13481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Amy Stone',
    'address': '3985 Kelly Throughway\nJohntown, TN 59716',
    'text': 'Necessary early rest assume decade sing affect. Like perhaps compare support wear ready suddenly. Practice though then series president prepare author.',
    'email': 'brittanyfisher@example.net',
    'phone_number': '7289806910',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michele Anderson',
    'Jesse Shields',
    'Sheila Thomas',
    'Michael Robinson',
],
    'json': {
    'name': 'Lindsey Klein',
    'address': '855 Lawrence Harbors Suite 390\nBryanhaven, MI 30667',
},
    'key93408': 'value11983',
    'key97974': 'value65162',
    'key28786': 'value72408',
    'key30563': 'value20915',
    'key95406': 'value56323',
    'key44001': 'value39343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Stephanie Wilkins',
    'address': '79461 Elaine Roads\nPerryborough, MS 92927',
    'text': 'Security young both enter avoid whether material. Police population address father paper let customer. Risk return subject.\nThem ten do capital type. Finish too others treat president.',
    'email': 'johnellis@example.com',
    'phone_number': '903-443-5142',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Frederick Phillips',
],
    'json': {
    'name': 'Austin Fleming',
    'address': '016 Jason Cape Suite 524\nWalkerview, WI 84332',
},
    'key83630': 'value41997',
    'key79398': 'value53146',
    'key86174': 'value27990',
    'key65640': 'value11576',
    'key31432': 'value90376',
    'key15477': 'value9578',
    'key49226': 'value36464',
    'key38960': 'value92736',
    'key81872': 'value26922',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Timothy Johnson',
    'address': '116 Ryan Cliff Suite 857\nWest Heather, MO 96854',
    'text': 'Decide school body choice. Dream series decade free.\nProbably modern hit professional food order. True instead model walk near against.',
    'email': 'jesse62@example.net',
    'phone_number': '(350)344-2653x635',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Webb',
],
    'json': {
    'name': 'Patrick Sullivan',
    'address': '14786 Scott Points Suite 522\nEast Sheilaside, IL 23377',
},
    'key95494': 'value52029',
    'key41990': 'value65144',
    'key34102': 'value35094',
    'key35112': 'value75036',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Tina Hunter',
    'address': '0747 Stacey Highway\nPort Ericland, NC 72115',
    'text': 'Whose car analysis build now him question. Door seek friend same black wife office.\nOf occur drop mean student she. Wear rate skill direction find. It far next least attention left surface.',
    'email': 'brandy24@example.net',
    'phone_number': '(699)283-5123x7267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Pacheco',
    'Sarah Thomas',
    'Lisa Diaz',
    'Kristine Glenn',
    'Richard Davis',
    'Alex Copeland',
    'Adriana Baker',
    'Andrea Fowler',
    'Roger Carson',
    'Melinda Wood',
],
    'json': {
    'name': 'Adam Cherry',
    'address': '23899 Robert Parks Suite 023\nAverymouth, SC 80698',
},
    'key23063': 'value38705',
    'key73109': 'value82328',
    'key69067': 'value24619',
    'key9728': 'value48096',
    'key29802': 'value77003',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Chris Ortega',
    'address': '6525 Veronica Prairie Suite 437\nNorth Kathryn, MS 91388',
    'text': 'Mouth begin possible person add catch. Discover continue focus wish while. Themselves war account than career sign indicate.\nMove song within event high bag. Scene ever few.',
    'email': 'uponce@example.com',
    'phone_number': '339-612-4173',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Mitchell',
    'Jessica Parker',
    'Adam Miller',
    'Joseph Wagner',
    'Courtney Lopez',
    'Joseph Lloyd',
    'Ryan Frederick',
],
    'json': {
    'name': 'Kimberly Gonzalez',
    'address': '4031 Logan Falls Apt. 158\nBrentfurt, MT 97855',
},
    'key81673': 'value80285',
    'key48966': 'value36666',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Justin Mahoney',
    'address': '3951 Acosta Roads\nJonesview, AL 66971',
    'text': 'Rise remain above team second image. Trial last call woman.\nStart threat do free police. Wish concern third defense production.',
    'email': 'lauren56@example.com',
    'phone_number': '(614)289-3713',
    'array_int_dynamic': [
    97710,
],
    'array_varchar_dynamic': [
    'Erica White',
    'Mrs. Pamela Moore',
    'Michael Norman',
    'Terry Brown',
],
    'json': {
    'name': 'Bryan Baker',
    'address': '724 Kathy Trace\nJacquelineburgh, ND 26772',
},
    'key58383': 'value28143',
    'key32114': 'value31002',
    'key44877': 'value56787',
    'key32253': 'value75075',
    'key9809': 'value16098',
    'key9959': 'value7667',
    'key71726': 'value3942',
    'key23005': 'value2067',
    'key96444': 'value65815',
    'key73799': 'value35755',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Zachary Hernandez',
    'address': '702 Smith Keys\nWaltonhaven, MP 68236',
    'text': 'Report same want entire you happen share. Sister process able alone course exist base. Long democratic seek throw quite.',
    'email': 'lisaramirez@example.com',
    'phone_number': '387.963.1135',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Justin Harris',
    'Sandra Murray',
    'Anthony Torres',
    'Heather White',
],
    'json': {
    'name': 'Vanessa Lynn',
    'address': '0482 Sabrina Point Apt. 390\nSouth Michelle, PR 86675',
},
    'key8741': 'value88482',
    'key35070': 'value84089',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Timothy Bruce',
    'address': '48238 Jared Crossroad Apt. 200\nJohnsonchester, CA 84054',
    'text': 'Social not approach west fly many prove. Politics meet month car citizen me.\nTeach at method despite oil night. Newspaper than center eight. Miss include too check.',
    'email': 'floreskendra@example.com',
    'phone_number': '(899)424-2435x0011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Campbell',
],
    'json': {
    'name': 'Lisa Miller',
    'address': 'PSC 9343, Box 9525\nAPO AP 95472',
},
    'key46507': 'value40080',
    'key46477': 'value5626',
    'key23836': 'value18330',
    'key7799': 'value649',
    'key12268': 'value65660',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Eric Washington',
    'address': '21526 Lucas Crossing\nReillymouth, NC 62159',
    'text': 'System production recently go staff reason call.\nSport whether trouble tend. Republican almost him plant.\nDebate final receive state. Heart get pull two service.',
    'email': 'james32@example.net',
    'phone_number': '(802)455-4769',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sheila Ramirez',
    'Stacy Sanders',
    'Justin Rodriguez',
    'Robert Bautista',
    'Matthew Berger',
],
    'json': {
    'name': 'Alexandria Mathews',
    'address': '86007 Higgins Fields\nPort Ianview, PW 93411',
},
    'key62895': 'value10955',
    'key3233': 'value35197',
    'key15589': 'value52418',
    'key85366': 'value76140',
    'key97250': 'value53860',
    'key85496': 'value4044',
    'key75393': 'value54867',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Dwayne Brown',
    'address': 'USNV Brown\nFPO AP 33671',
    'text': 'Very trouble eat cold. Treat pattern six white. Meet free believe. Data human sport know yes could probably.\nPerhaps establish court challenge east. Official nor box hot memory offer.',
    'email': 'charles28@example.org',
    'phone_number': '001-272-349-3351x7367',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Carrie Scott',
    'Isaiah Simpson',
    'Marcus Harper',
    'Donna Hughes',
    'Cynthia Arnold',
    'Timothy Fox',
    'Mr. Paul Swanson',
    'Denise Martinez',
    'Michelle Nielsen',
],
    'json': {
    'name': 'Abigail Andrews',
    'address': 'PSC 8612, Box 6197\nAPO AE 87772',
},
    'key15795': 'value31481',
    'key8769': 'value73237',
    'key75359': 'value84456',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'David Mitchell',
    'address': '00481 Mitchell Spur Apt. 392\nFaithstad, HI 42012',
    'text': 'Since word well matter whose speech manage federal. Federal five line anything serious color.',
    'email': 'jakestuart@example.org',
    'phone_number': '620-386-1529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Huerta',
],
    'json': {
    'name': 'Mark Jones',
    'address': '6903 Michael Viaduct\nPort Robertoville, DE 06333',
},
    'key27912': 'value4856',
    'key28463': 'value97916',
    'key22170': 'value31712',
    'key41189': 'value12919',
    'key97933': 'value8297',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Margaret Rivera',
    'address': '151 Aguilar Light Apt. 786\nLake Mariastad, KS 70276',
    'text': 'Read population TV work join fire that.\nParticular partner one over operation forget. Also ready these.\nEvery will money.',
    'email': 'samanthahall@example.net',
    'phone_number': '001-617-898-2656x035',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Blankenship',
    'Emily Knapp',
    'John Larson',
    'Amanda Gaines',
],
    'json': {
    'name': 'Anthony Hale',
    'address': '124 Dawn Locks Suite 018\nAntoniotown, MH 56149',
},
    'key8778': 'value26326',
    'key83215': 'value70548',
    'key22500': 'value82424',
    'key33878': 'value53886',
    'key39854': 'value56673',
    'key55338': 'value23036',
    'key40046': 'value94846',
    'key84443': 'value46113',
    'key51702': 'value99444',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Kyle Ochoa',
    'address': '619 Candace Viaduct Suite 059\nPort Brandon, FM 35407',
    'text': 'Scene idea full each clearly social morning. Name popular step thus research care. All shoulder describe score current.',
    'email': 'amy22@example.net',
    'phone_number': '+1-831-932-0168x64502',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Carrie Owen',
    'Mrs. Gloria Long',
    'Brad Moreno',
    'Sarah Dudley',
    'Kelly Rodriguez',
],
    'json': {
    'name': 'Jeffrey Gray',
    'address': '59351 Emily Trafficway\nNorth Margaretfurt, MN 58467',
},
    'key93381': 'value23541',
    'key51309': 'value24213',
    'key65838': 'value71921',
    'key99627': 'value21448',
    'key40208': 'value14532',
    'key1007': 'value26769',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jessica Henderson',
    'address': '7048 Pratt Turnpike Suite 812\nWest Dustinborough, DC 96998',
    'text': 'Recognize commercial establish hard main. Consumer break according add. Pull especially officer despite reality.\nOil condition admit. Director sea raise management.',
    'email': 'lmatthews@example.com',
    'phone_number': '590-476-7087x52482',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Randy Snyder',
    'Richard Rowe',
    'Michelle Ryan',
    'Margaret White',
    'Richard Foley',
    'Shawn Allen',
    'Patricia Smith',
    'Rebecca Phillips',
    'Justin Ross',
    'Seth Austin',
],
    'json': {
    'name': 'David Green',
    'address': '3179 Welch Fields Apt. 904\nKellyport, KY 60324',
},
    'key48981': 'value26527',
    'key32795': 'value76462',
    'key37681': 'value15743',
    'key38826': 'value9224',
    'key80616': 'value37542',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Glenda Kim',
    'address': '5802 Richardson Brook Apt. 570\nSouth Erinborough, PR 31973',
    'text': 'Color east shoulder hundred commercial. Decision choose keep catch. Watch employee product quite decade.\nBrother late customer manager cold evidence. Ok act drug make plant.',
    'email': 'sarah90@example.com',
    'phone_number': '316-520-9847x5376',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Glen Anderson',
    'Denise Gonzalez',
    'Joshua Wells',
    'Abigail Rodriguez',
    'Chad West',
    'Diana Oneill MD',
    'Jose Stevens',
    'Brenda Vargas',
    'Matthew Hardy',
],
    'json': {
    'name': 'Thomas Mendoza',
    'address': '67753 Reynolds Junction Apt. 521\nNew Miguelville, KS 94561',
},
    'key46889': 'value43049',
    'key37067': 'value75821',
    'key6559': 'value16774',
    'key26442': 'value42864',
    'key32931': 'value22624',
    'key71664': 'value539',
    'key23122': 'value72788',
    'key24376': 'value67464',
    'key66372': 'value96193',
    'key36465': 'value34594',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Gregory Underwood',
    'address': '6868 Benson Shoals\nPowellport, TX 57119',
    'text': 'Town start bill. Future property tonight statement follow. Season protect medical know establish behavior common.\nArtist prepare mission shoulder throw. Prepare head recognize region century rate.',
    'email': 'laurabowers@example.org',
    'phone_number': '(515)631-9519x7276',
    'array_int_dynamic': [
    73199,
],
    'array_varchar_dynamic': [
    'Monique Kelley',
    'Benjamin Hartman',
    'Brett Fisher',
    'Curtis Price',
    'Megan Gonzalez',
    'Nancy Lopez',
],
    'json': {
    'name': 'Donna Phelps',
    'address': '469 Simmons Loaf Apt. 212\nPort Meghanhaven, SD 41521',
},
    'key59376': 'value73898',
    'key36503': 'value18332',
    'key91312': 'value74390',
    'key14788': 'value78119',
    'key72238': 'value30905',
    'key74040': 'value96640',
    'key81481': 'value65454',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Dustin Jimenez',
    'address': '7429 Hernandez Creek\nEast Anneton, MS 74343',
    'text': 'Employee enough animal happen scientist.\nTwo for federal appear position magazine again. This son matter decision.\nHis hundred how particular fill bag. Agree build bad indeed.',
    'email': 'nealdavid@example.net',
    'phone_number': '(251)276-1915x370',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Sanchez',
],
    'json': {
    'name': 'Eric Stark MD',
    'address': '28252 Carroll Island\nNorth Sandraton, WY 02845',
},
    'key65373': 'value74671',
    'key23604': 'value16068',
    'key77123': 'value79161',
    'key3145': 'value71778',
    'key9762': 'value90024',
    'key72459': 'value65075',
    'key19524': 'value21672',
    'key54138': 'value2009',
    'key40410': 'value20339',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Amanda Smith',
    'address': '636 Kimberly Mews Apt. 431\nNew Barry, TX 30619',
    'text': 'Audience consider nice just upon money north. Police move Democrat operation simple. Establish hold organization back.\nTrouble include travel nice amount at. Tonight table hot find international.',
    'email': 'odomjared@example.org',
    'phone_number': '+1-814-465-6509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Robert Kelly',
    'Amy Fry',
    'Jeremy Robinson',
    'Holly Graham',
    'Tiffany Payne',
],
    'json': {
    'name': 'Robert Johnson',
    'address': '89419 Ware Ridge\nWilliamsfort, PR 80965',
},
    'key5625': 'value63183',
    'key18230': 'value43303',
    'key7158': 'value41960',
    'key8034': 'value40693',
    'key59021': 'value21101',
    'key46750': 'value49624',
    'key76249': 'value17975',
    'key71700': 'value16285',
    'key47864': 'value81677',
    'key33839': 'value18846',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Donald Dickerson',
    'address': '02708 Melton Circle Apt. 766\nCourtneytown, MH 28367',
    'text': 'Institution they when. Class foot answer but. Recognize war follow save police particular. National finally themselves reduce alone.',
    'email': 'ihenry@example.org',
    'phone_number': '775-947-2776',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Danielle King',
    'Kenneth Harvey',
    'Michael Jackson',
    'Michael Wallace',
    'Tracy Reyes',
    'Brittney Turner',
    'Justin Evans',
    'Allison White',
    'Rachel Anderson',
    'Nathan Avery',
],
    'json': {
    'name': 'Michelle Wyatt',
    'address': '2433 Smith Courts\nEast Jamie, MN 91588',
},
    'key96804': 'value35953',
    'key73482': 'value17531',
    'key94592': 'value56130',
    'key48320': 'value55890',
    'key62898': 'value32998',
    'key89437': 'value72976',
    'key22325': 'value36276',
    'key90713': 'value34608',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Mark Olson',
    'address': '937 Lee Junction\nSimmonsshire, CT 03435',
    'text': 'Thought answer add strategy share pattern media. Painting rule city pull pull top. Simply job example wife.\nLet one chair. Boy child her keep.',
    'email': 'xmorris@example.org',
    'phone_number': '261-504-8200x427',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Carpenter',
    'Jeffrey Lopez',
    'Jasmine Adams',
    'Connie Mckay',
],
    'json': {
    'name': 'Travis Mann',
    'address': '901 Williamson Knolls\nJesseside, NV 05482',
},
    'key79417': 'value93579',
    'key16540': 'value72496',
    'key47852': 'value9543',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jerry Huerta',
    'address': '9220 Chandler Radial\nDanielletown, IA 04308',
    'text': 'Quickly collection morning character. Hot big hospital president thus the identify movie. Term change nor tree choice.',
    'email': 'rclark@example.com',
    'phone_number': '(905)799-8643x72804',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Nelson',
    'Cathy Sellers',
    'Gavin Wyatt',
],
    'json': {
    'name': 'Mike Sullivan',
    'address': '5268 Garner Glens\nSamuelberg, DC 45075',
},
    'key76043': 'value63227',
    'key11496': 'value81136',
    'key21963': 'value29182',
    'key67428': 'value54017',
    'key47515': 'value33861',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Preston Roberts',
    'address': '758 Caldwell Wells Apt. 767\nPort Susan, ME 13257',
    'text': 'Arrive give accept appear difference probably quite. Teach blue law. Team news direction two religious nice guy.\nLot rock and its fire cell those.\nWord try player material. Huge yes firm push.',
    'email': 'randall56@example.org',
    'phone_number': '540.605.8782x558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Gomez',
    'Stephanie Booth',
    'Patricia Perkins',
    'Susan Harris',
    'Mr. David Thomas',
    'Charlotte Pierce',
    'Hayley Smith',
    'Donald Wilcox',
],
    'json': {
    'name': 'Nicholas Lin',
    'address': '366 Erin Wells\nHurleyfurt, MS 01352',
},
    'key2550': 'value73993',
    'key74629': 'value88588',
    'key16926': 'value14036',
    'key18423': 'value82723',
    'key7061': 'value28565',
    'key65955': 'value82431',
    'key64825': 'value40338',
    'key23604': 'value60721',
    'key67620': 'value39732',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Alexis Mcmahon',
    'address': '188 Samuel Lakes Apt. 884\nWest Tony, MS 11318',
    'text': 'Herself show mention best determine set. Cell box space lay worker.\nPainting south decade understand amount relate property. Fear message require note.',
    'email': 'kvalencia@example.com',
    'phone_number': '+1-493-310-4240x11314',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Brown',
    'Matthew Wilkerson',
    'Austin Gallagher',
    'William Evans',
    'Jessica Campbell',
    'Joseph Bowman',
    'Mr. Shawn Estrada',
    'Ryan Glover',
    'Richard Rios',
    'Jason Adams',
],
    'json': {
    'name': 'Timothy Peters',
    'address': '93094 Theodore Glens Suite 956\nAtkinsonland, VA 74166',
},
    'key94509': 'value13518',
    'key38704': 'value4102',
    'key84422': 'value21318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Corey Gonzalez',
    'address': '0059 Jason Loop\nRebeccaberg, MO 72894',
    'text': 'Art former relationship.\nRegion clear what. Part ten color sing technology child others.',
    'email': 'erica35@example.com',
    'phone_number': '(944)374-8157x53757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Santana',
    'Laura Jensen',
    'Jordan Oconnor',
    'Karen Jones',
    'Brooke Mitchell',
    'Leslie Thomas',
    'Mr. Steven Cantu',
],
    'json': {
    'name': 'Kristine Camacho',
    'address': '611 Robin Villages Suite 328\nWest Derek, NM 74671',
},
    'key66165': 'value76490',
    'key21567': 'value7064',
    'key97608': 'value46969',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Paula Green',
    'address': '682 Roy Lodge Suite 147\nNew Johntown, MS 85966',
    'text': 'Any room federal team unit follow. Grow and choose ground sometimes. Program about simple this collection.',
    'email': 'mackelizabeth@example.net',
    'phone_number': '556-893-0579x69628',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'James Jefferson',
    'Loretta Johnson',
    'Daniel Payne',
    'Amy Ayers',
    'Dominique Love',
    'Carol Arellano',
    'Brandon Mathis',
    'Rhonda Farley',
],
    'json': {
    'name': 'Miranda Conley',
    'address': '37928 Hogan Center\nWest Crystalshire, PR 91903',
},
    'key9085': 'value88538',
    'key32362': 'value81042',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Katie Johnson',
    'address': '9437 Tracey Drive\nPaulaborough, NY 71041',
    'text': 'Consider good parent your. Animal conference region seat score. Stop miss that this teach because.\nOnce notice morning relate or candidate participant.',
    'email': 'martinezmary@example.com',
    'phone_number': '001-621-617-1281x117',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Bailey',
    'Matthew Mccoy',
    'Brandon Reyes',
    'James Johnson',
    'John Craig',
],
    'json': {
    'name': 'Sandra Zuniga',
    'address': '974 Brewer Meadow\nSouth Nicholas, NJ 50101',
},
    'key97972': 'value8366',
    'key58992': 'value96777',
    'key12954': 'value80918',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jared Strickland',
    'address': '22545 George Throughway Suite 873\nNorth Dalton, MH 71743',
    'text': 'Piece recent once enough can.\nStatement main view always.\nEye billion short away but. Someone PM likely face major.',
    'email': 'fbanks@example.org',
    'phone_number': '4694435900',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Gonzalez',
],
    'json': {
    'name': 'Melissa Myers',
    'address': '103 Barnes Rapids\nLake Michaelfort, AL 41802',
},
    'key73715': 'value60365',
    'key60312': 'value60235',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'David Levy',
    'address': '41904 Monique Cliff\nOrtizberg, IA 50941',
    'text': 'Exist guess fall soldier their. Authority great structure style apply suddenly according. Window ever gun born while.\nYard sort southern fall arrive garden good. Threat federal community home from.',
    'email': 'andrea90@example.org',
    'phone_number': '001-422-233-3124x18229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mark Mullen',
    'Shawn Green',
    'Allison Hughes',
    'Shelley Brown',
],
    'json': {
    'name': 'Tonya Roberts',
    'address': '4030 Johnson Lights Suite 686\nWest Melissashire, NE 59429',
},
    'key79886': 'value48268',
    'key33829': 'value68271',
    'key87637': 'value57621',
    'key60828': 'value60628',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Charles Adams',
    'address': '893 Harris Estate\nWilliamsfort, FM 68818',
    'text': 'Institution person cause make may edge. Put power according today minute until.\nSister scene public pattern. Station card summer actually. Quality result recognize crime well stock phone happen.',
    'email': 'kristin82@example.com',
    'phone_number': '(278)667-2985x4335',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Peter Chaney',
    'Amber Bailey',
],
    'json': {
    'name': 'Robert Ramos',
    'address': '2872 Cheryl Plains Suite 428\nNorth Angela, CA 41316',
},
    'key11164': 'value65073',
    'key80444': 'value2225',
    'key95236': 'value81291',
    'key58525': 'value24147',
    'key43555': 'value87813',
    'key96487': 'value50357',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Tanya Allen',
    'address': '843 Christopher Islands Apt. 592\nNorth Elizabethton, FM 96402',
    'text': 'Student peace professor chance. Hold degree appear image act. Now speak the common tax.\nLetter brother news us field better do when. Those on process authority its order.',
    'email': 'rodriguezjoshua@example.com',
    'phone_number': '648.506.5870x631',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jose Johnson',
    'Lisa Vega',
    'Monica Sandoval',
    'Mr. Todd Pittman',
    'Jeff Rodriguez',
    'Jennifer Schneider',
    'Michael Sanchez',
    'Susan Williams',
    'Jennifer Herrera',
    'Jason Chen',
],
    'json': {
    'name': 'Robert Cook',
    'address': '21565 Baker Islands\nWest Ashley, MP 64844',
},
    'key6347': 'value95857',
    'key36943': 'value48803',
    'key69021': 'value3676',
    'key39531': 'value68203',
    'key75341': 'value49118',
    'key1145': 'value43168',
    'key15975': 'value55657',
    'key26923': 'value39974',
    'key62076': 'value62233',
    'key39302': 'value43394',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Rebecca Boyd',
    'address': '1225 Velez Fords\nSouth Seanfurt, PA 42763',
    'text': 'Project chair newspaper later. Practice not about. Five room rest sell.\nLike religious spring next. Box necessary eat report usually alone without fine. Adult science majority lead such book trade.',
    'email': 'pbrown@example.net',
    'phone_number': '(753)246-6944',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Todd Bowers',
    'Daniel Morgan',
    'Sergio Chambers',
    'Alyssa Hill',
    'John Wright DDS',
    'Claire Robles',
    'Natalie Armstrong',
    'Edward Carney',
],
    'json': {
    'name': 'Adam Jackson',
    'address': '086 Kent Pines\nNorth Jason, UT 77840',
},
    'key10739': 'value58683',
    'key2785': 'value59502',
    'key46681': 'value4122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Paul Rodriguez',
    'address': '15595 David Mountains Suite 077\nWalkerton, OH 63637',
    'text': 'Ago money never his data show lawyer nothing. Speech production theory decision.\nUnderstand local health miss up bad color still. Assume argue report.',
    'email': 'tguzman@example.net',
    'phone_number': '608.567.3924x92501',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Dwayne Butler',
    'Mr. Robert Jones',
    'Ashley Osborne',
    'Thomas Wilson',
],
    'json': {
    'name': 'James Roberts',
    'address': '658 Hoffman Locks\nPort Jameshaven, CA 96907',
},
    'key20569': 'value11055',
    'key20513': 'value12184',
    'key59929': 'value76274',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Peter Davis',
    'address': '88215 Johnson Brook Apt. 473\nEast Maryton, VI 09914',
    'text': 'Use enough customer career around worker. Decade watch true rest. Sense face poor much why while act hold. Laugh edge of forward investment film cell.',
    'email': 'jacqueline21@example.net',
    'phone_number': '349.398.8526x9270',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Guerra',
    'Mr. Jonathan Brady',
    'Logan Carney',
    'Heather Vargas',
    'Kelly Sloan',
    'Lucas Patel',
    'Nicole Cruz',
],
    'json': {
    'name': 'Craig Price',
    'address': '785 Anthony Well\nPort Daniel, CO 65901',
},
    'key35283': 'value3471',
    'key2450': 'value70661',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Timothy Hester',
    'address': 'PSC 4187, Box 4189\nAPO AP 47810',
    'text': 'So knowledge property. Star tell tonight southern. Arm seat paper culture best.\nChance right partner many industry shoulder personal. Piece wait finish be.',
    'email': 'michelepowers@example.org',
    'phone_number': '(277)259-6604x57248',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Reese',
    'Ricky Velazquez',
],
    'json': {
    'name': 'Chase Carrillo',
    'address': '1244 Green Locks\nLeeton, UT 48807',
},
    'key77182': 'value47329',
    'key87744': 'value70141',
    'key6144': 'value96383',
    'key34441': 'value12493',
    'key83249': 'value71249',
    'key40048': 'value90199',
    'key24924': 'value25044',
    'key99282': 'value17209',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Logan Ryan',
    'address': '6875 Shannon Point\nEast Michael, NV 39260',
    'text': 'Attention move finally night seat fine visit. Body accept effect house.\nNever cultural enjoy share. Production possible know seek well. Hand current style.',
    'email': 'tprice@example.net',
    'phone_number': '001-240-344-9132x334',
    'array_int_dynamic': [
    51436,
],
    'array_varchar_dynamic': [
    'Michael Cantrell',
    'Jennifer Smith',
    'Tracy Chaney',
    'Brandon Carroll',
    'Alexander Bauer',
],
    'json': {
    'name': 'William Gray',
    'address': '4060 Francis Groves Suite 803\nWest Johnshire, UT 91093',
},
    'key85595': 'value95772',
    'key47186': 'value71771',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Chad Santiago',
    'address': '7032 Coleman Lights Suite 312\nWilcoxbury, HI 45467',
    'text': 'Shoulder white dog choice door large. Family or audience per break build focus.\nEverybody on development team speech television attack.\nSee day way organization lot ok someone. Dream clear card.',
    'email': 'smithjesus@example.com',
    'phone_number': '+1-931-615-9598x89398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'James Davis',
    'Jason Johnson',
],
    'json': {
    'name': 'Stephanie Smith',
    'address': '55540 Williams Knolls Apt. 790\nJohnchester, AL 65988',
},
    'key80890': 'value1249',
    'key94946': 'value8198',
    'key20519': 'value63560',
    'key79066': 'value4829',
    'key82222': 'value96214',
    'key94513': 'value96702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Brooke Martin',
    'address': '4570 Oneal Shores\nSouth David, SC 78744',
    'text': 'Boy new nature everybody.\nExample do seven tree traditional. When paper task special.\nOption level take statement ok mention. Goal again natural history half. Decade sure exactly argue sort.',
    'email': 'kristy89@example.org',
    'phone_number': '(894)717-3792x81979',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Velazquez',
    'Johnny Mcneil',
    'Heather Tucker',
    'Katherine Buckley',
    'Suzanne Wilson',
    'Evelyn Haley',
],
    'json': {
    'name': 'Ashley Sheppard',
    'address': '489 Erin Spur\nSouth Jamieside, MP 22332',
},
    'key56546': 'value82423',
    'key29367': 'value97099',
    'key98682': 'value97970',
    'key96764': 'value97839',
    'key43552': 'value78641',
    'key35600': 'value13467',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Norma Martinez',
    'address': '696 Nelson Vista\nSteeleborough, OK 21798',
    'text': 'Organization institution increase woman friend exactly require. List establish at while.\nReceive art skill reality scientist. Operation central kitchen cost. Director ball evidence military page.',
    'email': 'josephchristine@example.com',
    'phone_number': '+1-511-835-7336x8456',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Howell',
    'Jeanette Armstrong',
    'Danielle Pratt',
    'Mark Sellers',
    'John Weaver',
    'Andre May',
    'Paul Hahn',
    'Darryl Jackson',
    'Charles Rodriguez',
    'Anthony Smith',
],
    'json': {
    'name': 'Jeffrey Velazquez',
    'address': '06199 Reeves Plains\nEast Jeremy, NM 99732',
},
    'key16202': 'value49458',
    'key86452': 'value6016',
    'key46682': 'value74121',
    'key53959': 'value89734',
    'key60988': 'value80936',
    'key61829': 'value55245',
    'key76752': 'value22938',
    'key85392': 'value84438',
    'key50672': 'value68703',
    'key54856': 'value99353',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'William White MD',
    'address': '6837 Amy Stravenue Suite 078\nEast Rachelland, GU 45225',
    'text': 'Risk statement sense read marriage religious.\nThere record law property lot. Light soon stage alone thought probably. Education herself mention fear attack.',
    'email': 'iesparza@example.org',
    'phone_number': '829-823-0541',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Chad Lewis',
    'Chad Mayo',
    'Kimberly Hamilton',
    'Logan Collins',
    'Terry Hess',
    'Cassandra Knox',
    'Linda Smith',
    'Alexander Stanley',
    'Michelle Brown',
    'Danielle Lopez',
],
    'json': {
    'name': 'Ashley Bell',
    'address': 'Unit 7958 Box 6406\nDPO AE 44927',
},
    'key1114': 'value8350',
    'key96076': 'value5151',
    'key41584': 'value46328',
    'key81699': 'value63132',
    'key9204': 'value52393',
    'key146': 'value25560',
    'key60719': 'value47764',
    'key48744': 'value49641',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Jaclyn Matthews',
    'address': '734 Craig Orchard\nNew Linda, KY 63517',
    'text': 'Indicate significant maintain leg help point east. Writer seven size defense simple great box. Increase my be dream as black.\nAlmost share set rule rest scene view. Clear left least return painting.',
    'email': 'vjones@example.net',
    'phone_number': '818-400-6018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Scott Rodriguez',
    'Daniel Jenkins',
    'William Castaneda',
    'Katie Ray',
    'Aaron Jackson',
    'Elizabeth Obrien',
    'Cindy Williams',
    'John Smith',
    'Christopher Clark',
    'Travis Howard',
],
    'json': {
    'name': 'Ryan Juarez',
    'address': '98830 Jared Haven\nMarkport, NE 58732',
},
    'key42218': 'value42399',
    'key59846': 'value67362',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Katelyn Boyd',
    'address': '70695 Amanda Vista Suite 264\nBrownmouth, MN 23096',
    'text': 'Student dog million board east less practice. Sell style home follow international animal.\nName card product admit. Board health hot indicate design.',
    'email': 'martinezaustin@example.net',
    'phone_number': '716.635.0440x50017',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Barber',
    'Lori Lambert',
    'Amanda Williams',
    'Stacie Brown',
    'Kaitlin Graham',
    'Elizabeth Allen',
],
    'json': {
    'name': 'Samantha Cannon',
    'address': '7754 James Forest\nJocelynfurt, MI 45996',
},
    'key39754': 'value34162',
    'key45855': 'value99043',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Steven Miller',
    'address': '66396 Marie Knoll Suite 760\nChristopherberg, ME 38321',
    'text': 'Relationship billion sometimes feel send community. Seat assume hear identify natural seem use. His serious early wrong.',
    'email': 'jessica00@example.net',
    'phone_number': '847.950.1532x8124',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Miller',
    'Stephanie Wright',
    'Danielle Carroll',
    'James Perkins',
],
    'json': {
    'name': 'Daniel Alvarado',
    'address': '49748 Luis Rest Suite 406\nHolmesborough, MP 95083',
},
    'key24038': 'value82354',
    'key37117': 'value98848',
    'key68707': 'value30350',
    'key73455': 'value56492',
    'key60781': 'value46146',
    'key93952': 'value18883',
    'key19625': 'value36446',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Scott Spencer',
    'address': '265 Matthews Lane Apt. 287\nNorth Kevin, MH 36078',
    'text': 'Exactly add owner religious Congress true. Painting property maybe live.\nAllow newspaper section policy crime network direction. Watch hold blood remain share ask throughout little.',
    'email': 'pgaines@example.org',
    'phone_number': '001-452-231-9365',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Floyd',
    'Michelle Martin',
    'Jenna Schmidt',
    'Randy Brady',
    'Jamie Villarreal',
    'William Roberts',
    'Lori Hudson',
],
    'json': {
    'name': 'Lauren Jackson',
    'address': '7124 Jackie Mountain Suite 744\nMichaelchester, DE 10675',
},
    'key94095': 'value13838',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Anna Martin',
    'address': '3682 Long Cliffs Apt. 979\nPort Susanburgh, MA 76753',
    'text': 'Business within trial audience person main. Of onto these marriage conference chance physical. Year all natural.\nReally several serve follow. Outside worry gun vote.',
    'email': 'steven67@example.com',
    'phone_number': '2805390763',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Hurley',
    'Kelly Mcfarland',
    'Michael Boyd',
    'Victor Collier',
    'James Buckley',
    'Daniel Romero',
    'Michael Gutierrez',
    'Laura Robinson',
    'Kellie Richmond',
],
    'json': {
    'name': 'Cindy Gonzalez',
    'address': '3947 Reyes Forks Suite 698\nLake Christopher, MI 72061',
},
    'key71295': 'value28642',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Troy Miller',
    'address': '1908 Yolanda Point\nNew Jeremy, WI 67732',
    'text': 'Assume bank close prove morning sure anything. Eight support happen week investment difference.',
    'email': 'fknight@example.org',
    'phone_number': '3244011954',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Johnson',
    'Dr. Jacob Carrillo',
    'Christopher Mueller',
],
    'json': {
    'name': 'Jacob Obrien',
    'address': '331 Hernandez Green\nNew Christopher, SC 24833',
},
    'key6795': 'value60711',
    'key99135': 'value50575',
    'key36002': 'value1855',
    'key83425': 'value7574',
    'key22531': 'value45801',
    'key61809': 'value11917',
    'key88684': 'value61192',
    'key57055': 'value93415',
    'key26193': 'value92302',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jennifer Gentry',
    'address': '84418 Williams Plains\nStacyburgh, MP 44650',
    'text': 'Agreement rock hotel bit market young. Stay hair science throughout change second however likely. Wall scientist figure than. Response once spend boy join large her.',
    'email': 'kelsey58@example.com',
    'phone_number': '+1-897-298-1125x56640',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Shane Ortiz',
    'Terry Thompson',
    'Gary Koch',
    'Felicia Carter',
    'Eric Davis',
],
    'json': {
    'name': 'Samuel Bush',
    'address': '119 Caitlyn Vista\nEast Anthony, CO 87706',
},
    'key14213': 'value65319',
    'key59359': 'value11033',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Mitchell Aguirre',
    'address': 'Unit 2145 Box 0826\nDPO AP 82122',
    'text': 'Interesting speak stage read practice page. Race daughter represent know. Either truth measure morning friend wonder several.',
    'email': 'vlarson@example.net',
    'phone_number': '+1-580-934-3140',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael White',
    'Marcia Jenkins',
    'Brittany Robbins',
    'Diana Martin',
    'Christina Henry',
],
    'json': {
    'name': 'Sharon Berg',
    'address': '9520 Timothy Greens\nChristopherberg, IN 29008',
},
    'key91093': 'value39318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jennifer Phillips',
    'address': '817 Watson Ways Apt. 226\nLozanoside, PW 95893',
    'text': 'Save near bar film thank nature language together. Knowledge art book sign nearly my left.\nGarden born program state show audience miss. Hard ground time article.',
    'email': 'jacquelinejones@example.org',
    'phone_number': '(810)684-0998x205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Rodgers',
    'Duane Jones',
    'Michael Bullock',
],
    'json': {
    'name': 'Brenda Glover',
    'address': 'PSC 4324, Box 1029\nAPO AA 69804',
},
    'key95430': 'value27584',
    'key82564': 'value17835',
    'key39183': 'value19801',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Joshua Elliott',
    'address': '85999 Stephanie Mission\nPort Aprilborough, NY 43797',
    'text': 'General position cup history put benefit.\nThink discover recently child we. Woman difficult do whatever right. Customer our attack system.',
    'email': 'millerdavid@example.org',
    'phone_number': '524-284-2103x03120',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Maria Nelson',
    'April Davis',
    'Stephen Morton',
    'Jamie Knight',
    'Derrick Marshall',
],
    'json': {
    'name': 'Shane Sanchez',
    'address': '961 Townsend Drives\nNorth Dianaland, OK 22399',
},
    'key36909': 'value69786',
    'key67808': 'value15550',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Martha Alexander',
    'address': '5724 Thompson Coves Suite 535\nWilliamside, UT 18952',
    'text': 'Health catch change sit. Treatment party which fine. According toward put.',
    'email': 'jason89@example.com',
    'phone_number': '804-748-0719',
    'array_int_dynamic': [
    46614,
],
    'array_varchar_dynamic': [
    'David Mueller',
    'Kristina Gonzalez',
    'Mark Mckinney',
    'Deanna Perez',
    'Kyle Clayton',
    'Brian Howard',
    'David Davis',
    'Angel Rios',
    'Gary Perez',
    'Rebecca Williams',
],
    'json': {
    'name': 'Ronnie Greer',
    'address': '1178 Mack Hill Apt. 314\nThomasview, IA 41161',
},
    'key14045': 'value10358',
    'key92890': 'value35542',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Lauren Johnson',
    'address': '225 Christina Wall\nEast Mindybury, CO 06959',
    'text': 'Number exist argue unit. Day how plan where new respond.\nEveryone can yard represent. Fish Mr represent do race evening. Send need career happy leader sort.',
    'email': 'david73@example.com',
    'phone_number': '2104840145',
    'array_int_dynamic': [
    26577,
],
    'array_varchar_dynamic': [
    'William Price',
    'Stacy Holmes',
],
    'json': {
    'name': 'Robert Carter',
    'address': 'USNV Martin\nFPO AE 17958',
},
    'key35002': 'value61132',
    'key70564': 'value23024',
    'key21382': 'value80428',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Joe Little',
    'address': '7088 Roberts Club\nPort Madisonstad, AR 62654',
    'text': 'Edge stock manage group gun watch. Very none can himself. Indicate well significant give here model.\nUp well probably southern which. North shoulder safe. Difference mean yourself treatment court.',
    'email': 'imatthews@example.com',
    'phone_number': '679.724.2668x306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kristine Miller',
    'Stephanie Barton',
    'Tiffany Barnett',
    'Eric Morris',
    'Sara Williams',
    'Taylor Moss',
],
    'json': {
    'name': 'Hannah Hoffman',
    'address': '226 Torres Track\nSerranoview, OR 88076',
},
    'key6845': 'value64604',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Kelly Stevens',
    'address': '645 Mccoy Streets\nLake Daniel, MS 71753',
    'text': 'Sea energy could watch. Age attorney mind effort character.',
    'email': 'perezdouglas@example.net',
    'phone_number': '4452532326',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James King',
    'Nathaniel Rodriguez',
    'Patricia Kennedy',
    'Michael Horne',
],
    'json': {
    'name': 'Stacy Fry',
    'address': 'Unit 9311 Box 9864\nDPO AP 70018',
},
    'key38012': 'value46988',
    'key31032': 'value84307',
    'key49527': 'value57725',
    'key25289': 'value86741',
    'key83212': 'value18448',
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
    'RequestId': 'c678034f-62f1-11f0-b79c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_38_08_225796uupywWcg',
    'filter': 'uid > -100 and uid < 100',
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
    'RequestId': 'c71bf1b9-62f1-11f0-b285-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_38_08_225796uupywWcg',
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
    'RequestId': 'bfc190cb-62f1-11f0-8702-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_38_08_225796uupywWcg',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > -100 and uid < 100]_1752745101.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid100AndUid1001752745101Json()
    test.run_tests()
