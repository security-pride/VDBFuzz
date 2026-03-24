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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-1]_1752744139_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-1]_1752744139.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId12810011752744139Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-1]_1752744139.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-1]_1752744139.json"
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
    'RequestId': '893c41dd-62ef-11f0-9b4b-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_17_761748DeZRSyjc',
    'dimension': 128,
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
    'RequestId': '89621914-62ef-11f0-b871-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_17_761748DeZRSyjc',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Derrick Hebert',
    'address': 'Unit 0601 Box 7016\nDPO AE 58736',
    'text': 'Hope city cost house. Reveal picture follow budget such such.\nEdge toward shoulder include account. Recognize tax people cell task employee reveal admit. Type statement age beyond measure.',
    'email': 'ggreen@example.com',
    'phone_number': '9004407268',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Robinson',
    'Rachel Harrell',
    'Ashley Jones',
    'Thomas Adams',
    'Patrick Mcdonald',
    'Jessica Lewis',
    'Jennifer Burnett',
],
    'json': {
    'name': 'Sheila Terry',
    'address': 'PSC 2691, Box 6939\nAPO AP 09342',
},
    'key97073': 'value22606',
    'key19890': 'value27344',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Gloria Gomez',
    'address': 'USCGC Walton\nFPO AA 24240',
    'text': 'Yard travel together right deep bed exactly happy. Never middle voice for wife. Bag appear media situation quality strong before.',
    'email': 'uodom@example.org',
    'phone_number': '001-422-241-7672x8426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Patton',
    'Kevin Taylor',
    'Julie Mayer',
    'Carol Walker',
    'James Thomas',
    'Jack Jennings',
    'Kelly Phillips',
    'Jeffrey Phillips',
    'Ana Cline',
],
    'json': {
    'name': 'John Williams',
    'address': '99107 Ross Flats\nEast Erika, GA 80265',
},
    'key64400': 'value93088',
    'key88884': 'value53071',
    'key64769': 'value8694',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jamie Bush',
    'address': '89497 Andrew Harbors\nNorth Travisland, PR 63108',
    'text': 'Same senior political that. Black score amount run make only. Green professional pay collection entire magazine example entire.',
    'email': 'jennifergraham@example.org',
    'phone_number': '4062606684',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tammie Evans',
    'Charles Maldonado',
    'John Frank',
    'Amanda Munoz',
    'Brian Harris',
],
    'json': {
    'name': 'Paul Green',
    'address': '5073 Tony Pike Apt. 723\nLake Jessicaville, KY 31882',
},
    'key51419': 'value48488',
    'key80508': 'value2178',
    'key47542': 'value53119',
    'key99272': 'value56680',
    'key1999': 'value37253',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Keith Fisher',
    'address': 'USCGC Turner\nFPO AP 87510',
    'text': 'Military design most PM by choose voice. Current raise outside peace life one bit. Through dark weight. Rest every story quickly.',
    'email': 'garrisonjessica@example.org',
    'phone_number': '547-942-3330x04192',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Foley',
    'Adam Jones',
    'Sharon Carrillo',
],
    'json': {
    'name': 'Judith Taylor',
    'address': '1720 Herrera Heights Apt. 065\nButlerborough, MA 81467',
},
    'key20588': 'value10516',
    'key81159': 'value49992',
    'key67555': 'value57670',
    'key7291': 'value65350',
    'key11357': 'value41142',
    'key1770': 'value38533',
    'key57817': 'value22782',
    'key65150': 'value20863',
    'key3115': 'value47486',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'William Bowman',
    'address': '132 Richard Lane\nWatsonshire, MO 43559',
    'text': 'Reality resource see sit. Everybody early chair loss notice success bank rest. Under argue candidate man my bad nice financial.',
    'email': 'sierramora@example.net',
    'phone_number': '369.265.5510',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Roberts',
    'Christopher Benson',
    'Joanna Kelly DDS',
],
    'json': {
    'name': 'Jennifer Alvarez',
    'address': '47119 William Stream Apt. 613\nWest Victor, SD 87341',
},
    'key53765': 'value64322',
    'key40348': 'value80516',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Heather Woodard',
    'address': '955 William Forks\nSouth Elizabethborough, IA 25392',
    'text': 'Those suddenly magazine adult. Difficult board own happen read spend range.\nRelationship lose involve quite central.',
    'email': 'james97@example.org',
    'phone_number': '001-655-888-6276x32124',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Martinez',
    'Phillip Greene',
    'Peter Bradley',
    'Jamie Walters',
    'Bethany Rodriguez',
    'Jacob Reid',
    'Malik Frazier',
    'Robert Lyons',
    'Vincent Campbell',
    'Jennifer Douglas',
],
    'json': {
    'name': 'Catherine Reid',
    'address': '0510 Michael Plains\nLake Daniel, FM 16829',
},
    'key36517': 'value49565',
    'key40612': 'value24582',
    'key95778': 'value22586',
    'key75542': 'value802',
    'key62328': 'value59685',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kiara Rodriguez',
    'address': '19919 Blake Land\nEast Chris, NM 50411',
    'text': 'Fear inside first while dark. Animal usually tend employee skill. Across center field amount feeling. Food treat hope north detail particular.',
    'email': 'stephensmatthew@example.org',
    'phone_number': '+1-438-387-5428',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jason Downs',
],
    'json': {
    'name': 'David Smith',
    'address': '32420 David Port\nHayesborough, NY 11631',
},
    'key83133': 'value16468',
    'key71835': 'value12736',
    'key39377': 'value49648',
    'key14953': 'value78473',
    'key61192': 'value5889',
    'key63796': 'value43381',
    'key62768': 'value66758',
    'key81154': 'value36186',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Kimberly Fuentes',
    'address': '87632 Stephenson Row\nSouth Tarabury, KS 80681',
    'text': 'Subject necessary approach evening visit necessary door simple. Call above long any change language must.',
    'email': 'halljeffrey@example.com',
    'phone_number': '001-698-278-7552x4955',
    'array_int_dynamic': [
    50229,
],
    'array_varchar_dynamic': [
    'Rachel Donovan',
    'Seth Ware',
],
    'json': {
    'name': 'Nathan Turner',
    'address': '67139 Anthony Mall\nLake Mariafurt, OH 13468',
},
    'key61958': 'value93051',
    'key31081': 'value12929',
    'key97965': 'value46022',
    'key49624': 'value90536',
    'key62251': 'value3222',
    'key2948': 'value78496',
    'key52867': 'value59752',
    'key87584': 'value27091',
    'key48008': 'value15581',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Karen Roberson',
    'address': '13572 Ramos Gardens\nWest Peterfurt, TN 17472',
    'text': 'Ready project deep there site break religious.\nScience relate thing. Ago age never practice current over.',
    'email': 'cody06@example.org',
    'phone_number': '001-383-378-8950x4688',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Robertson',
    'Brenda Jones',
    'Leslie Barber',
    'Anthony Chandler DVM',
    'Robert Livingston',
    'Steven Glover',
    'Laura Baker',
    'Maria Diaz',
],
    'json': {
    'name': 'Johnny Lopez',
    'address': '649 Thompson Forks\nSamuelville, PR 55709',
},
    'key87925': 'value36924',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Charles Donovan',
    'address': '963 Brady Underpass\nEast Kathrynfort, PR 60827',
    'text': 'Focus mother begin pressure stand. Short American politics standard treatment.\nGeneral ready case explain environment modern him. Its necessary hold civil gun four.',
    'email': 'ctucker@example.com',
    'phone_number': '435-247-2498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Jones',
    'Julie Brown',
    'John Yoder',
    'Gregory Spence',
],
    'json': {
    'name': 'Jason Sanders',
    'address': '04322 Mosley Throughway Apt. 690\nWest Craig, NY 72914',
},
    'key80300': 'value54536',
    'key32232': 'value11713',
    'key36191': 'value34930',
    'key51351': 'value86707',
    'key9400': 'value30593',
    'key67943': 'value84072',
    'key90200': 'value92956',
    'key88589': 'value76737',
    'key2243': 'value88605',
    'key85504': 'value4263',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Rebecca Nguyen',
    'address': '645 Owens Burgs Apt. 149\nKurtbury, IL 16433',
    'text': 'Yet beautiful outside case. Would for range life north such charge television.\nArrive also activity nice form. Decision cold here first suddenly believe explain. Something above customer style.',
    'email': 'parkerjoel@example.com',
    'phone_number': '+1-786-482-4707',
    'array_int_dynamic': [
    42374,
],
    'array_varchar_dynamic': [
    'Jennifer Thompson',
    'Jordan Henderson',
    'James Santos',
    'Nicole Rosario',
],
    'json': {
    'name': 'Diana Bartlett',
    'address': 'USCGC Hayes\nFPO AA 04178',
},
    'key63266': 'value92369',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Brenda Koch',
    'address': '2242 Mason Passage Suite 526\nEast Melanieton, NJ 75612',
    'text': 'Line but front health explain listen campaign laugh. Address sit growth argue theory. Morning whether so picture record.',
    'email': 'lloydsteven@example.com',
    'phone_number': '970.593.4595',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amy Ramirez',
],
    'json': {
    'name': 'Dr. Zachary Howell',
    'address': '3513 Ashley Square\nWeeksmouth, OH 21761',
},
    'key43695': 'value54332',
    'key96401': 'value56144',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Veronica Castaneda',
    'address': '31324 Judith Ville Apt. 184\nSouth Sarahstad, NV 06985',
    'text': 'Production national until compare onto pick. Dog meet somebody kid seven thing.\nAgree your door tax serve down fill. Or life each determine.',
    'email': 'matthew10@example.org',
    'phone_number': '3406835229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sandy Klein',
    'Ashley Owens',
    'Angela Hurley',
],
    'json': {
    'name': 'Pamela Humphrey',
    'address': 'PSC 2818, Box 5757\nAPO AP 63608',
},
    'key65669': 'value17664',
    'key7563': 'value30345',
    'key65614': 'value93413',
    'key42692': 'value78529',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Shannon Gordon',
    'address': '92405 Freeman Mill\nNorth Laurenville, GA 68719',
    'text': 'Impact drive could despite deep. Let leg present but possible person American.\nTeach save financial someone age boy. Generation power continue heavy suffer style clear recently.',
    'email': 'elliottkathy@example.com',
    'phone_number': '+1-984-776-9854x95812',
    'array_int_dynamic': [
    72034,
],
    'array_varchar_dynamic': [
    'Angela Washington',
    'Vanessa Parker',
    'Elaine Berg',
    'Tommy Jones',
    'Donald Daniels',
    'Alexander Henderson',
    'William Watson',
    'Jamie Howe',
    'Christine Hernandez',
    'Jennifer Castaneda',
],
    'json': {
    'name': 'David Haney',
    'address': '226 Joseph Plains\nKellyside, WI 84848',
},
    'key3167': 'value27371',
    'key36498': 'value75955',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Christopher Garza',
    'address': '909 Stephanie Land\nNew Mandy, FL 16573',
    'text': 'Piece show catch present various represent well. Community edge anything cover.\nEverybody vote present. Big eat call design whom section.',
    'email': 'kimberlyjohnson@example.net',
    'phone_number': '+1-967-427-1258x5946',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Taylor',
    'Richard Turner',
    'Jeffrey Mathis',
],
    'json': {
    'name': 'Charles Davis',
    'address': '0666 Lara Light\nLake Devinburgh, ND 01661',
},
    'key89326': 'value67621',
    'key18435': 'value66830',
    'key71680': 'value48623',
    'key87559': 'value17302',
    'key76872': 'value20754',
    'key74988': 'value2498',
    'key74527': 'value55100',
    'key85478': 'value54577',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Phillip Fuller',
    'address': '141 Acosta Cove Suite 214\nBurgessberg, DC 11200',
    'text': 'History throw oil almost firm current voice. Executive least wait article.\nUp else that rest age. Most look could north society.',
    'email': 'ryanchristopher@example.org',
    'phone_number': '+1-450-594-5799x801',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Wells',
    'Melissa Wilkinson',
    'Dr. Ricky Fitzgerald',
    'Zachary Jarvis',
],
    'json': {
    'name': 'Tony Wilson',
    'address': '6953 Frazier Islands\nNew Tracy, AS 48455',
},
    'key72429': 'value84183',
    'key34263': 'value78061',
    'key1846': 'value41593',
    'key18358': 'value41363',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Timothy Sullivan',
    'address': '278 Rogers Mill\nNorth Mauricetown, IL 92205',
    'text': 'Real learn might prepare meeting wish approach. Policy measure century. Spring position party program reality south.',
    'email': 'qramirez@example.com',
    'phone_number': '856.667.1125',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Bender',
    'Mary Moss',
    'Alyssa Cooper',
    'Darrell Perry',
],
    'json': {
    'name': 'Richard Hunter',
    'address': '218 Tonya Street\nSouth Annebury, VT 40516',
},
    'key32149': 'value93850',
    'key36013': 'value96983',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Joshua Mitchell',
    'address': '1634 Kelsey Expressway Apt. 535\nMichelleville, GA 01129',
    'text': 'Return contain because produce nice kid already. Conference finish half whose collection particular. Son stay central order.',
    'email': 'patriciawolfe@example.org',
    'phone_number': '(974)633-3098x417',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Castillo',
    'Sarah Sanchez',
    'James Kelly',
    'Stanley Johnson',
],
    'json': {
    'name': 'Chad Vasquez',
    'address': '7976 Howard Extensions\nJasonberg, TX 02486',
},
    'key51289': 'value95954',
    'key20242': 'value33615',
    'key3074': 'value367',
    'key82567': 'value95006',
    'key64527': 'value23061',
    'key19203': 'value54042',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Kimberly Page',
    'address': '38409 Leah Ridges Suite 172\nSpencerville, IA 29682',
    'text': 'Party require view technology even seem particular.\nThem for miss science writer Mr. Religious Mrs although lay blue least someone social. Treat each leader event hospital her quickly.',
    'email': 'sguzman@example.org',
    'phone_number': '747.449.4568x4632',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Dalton Thompson',
    'Victor Boyd',
    'Jessica Ortega',
    'Mark Sosa',
    'Tiffany Watkins',
    'David Carter',
    'James Williams',
    'Vanessa Murphy',
    'Robert Mckee',
    'James Perry',
],
    'json': {
    'name': 'Benjamin Nelson',
    'address': '329 Randy Park Apt. 224\nWest Ricardo, MD 79183',
},
    'key47682': 'value10907',
    'key65884': 'value4314',
    'key66222': 'value73131',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Natasha Smith',
    'address': '9474 Justin Mountains Suite 652\nFrederickmouth, MI 80051',
    'text': 'Great truth really participant eat mission. Collection happen marriage that. Could activity see American.',
    'email': 'guzmanandres@example.org',
    'phone_number': '683-790-2321x2917',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Laura Zimmerman',
    'Cody Snyder',
    'Paul Hunt',
    'Richard Chandler',
    'Bradley Wilson',
    'James Patterson',
    'Jody Simpson',
    'Curtis Clark',
    'Mark Henderson',
    'Veronica Rodriguez',
],
    'json': {
    'name': 'Jacob Ramirez',
    'address': '913 Jennifer Inlet Suite 923\nBakerberg, AZ 42906',
},
    'key27212': 'value44266',
    'key17254': 'value16492',
    'key88187': 'value49041',
    'key69667': 'value65782',
    'key83816': 'value11191',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Ryan Mason',
    'address': '78694 Baker Keys\nSouth Jamesfurt, AL 76101',
    'text': 'Population protect write.\nWithout appear suggest. He perform protect work cell. Whatever college follow child.\nCost story since worry. Turn play top out while arm. Near gun create environment.',
    'email': 'qcampbell@example.com',
    'phone_number': '(363)774-6522x677',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Emily Roberts',
    'Kathryn Smith',
    'William Pearson',
    'Jesus Harris',
    'Adam Jackson',
],
    'json': {
    'name': 'Monica Rodriguez',
    'address': '7696 Gregory Village Apt. 331\nFletcherchester, IL 81294',
},
    'key49541': 'value18753',
    'key18080': 'value54548',
    'key70903': 'value34642',
    'key91845': 'value69106',
    'key70873': 'value19596',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Elizabeth Velasquez',
    'address': '9305 Mendez Harbors Suite 696\nSouth Jessicafort, IA 30264',
    'text': 'High around economy step hour. Why actually look hold.\nPrevent why attention although. Far table factor once trip million however.',
    'email': 'burkejoanna@example.com',
    'phone_number': '552-928-0035',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Anna Lopez',
    'Denise Black',
    'Daniel Gonzales',
    'Amy Osborn',
],
    'json': {
    'name': 'Danielle Fleming',
    'address': 'Unit 4319 Box 0244\nDPO AE 40838',
},
    'key48976': 'value7860',
    'key79440': 'value48393',
    'key4686': 'value71593',
    'key15149': 'value33993',
    'key44479': 'value1686',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Peggy Edwards',
    'address': '5123 Michael Stream\nWendyshire, FM 66556',
    'text': 'Claim cause radio character point boy. Expect involve case reason. Build hair employee room stock audience what.\nDoor population bar yourself address. Its grow population into moment nation when.',
    'email': 'timothy56@example.org',
    'phone_number': '(458)892-4865x68481',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jesus Perez MD',
    'Shannon Allen',
    'Joe Cunningham',
    'Faith Ramirez',
    'Michael Moreno',
    'Kim Anderson',
    'Veronica Jackson',
    'Robert Campbell',
    'Michelle Kelly',
    'Harry Gibson',
],
    'json': {
    'name': 'Kevin Smith',
    'address': '667 Hayes Squares Apt. 022\nEast Jasonport, PR 72718',
},
    'key89475': 'value69996',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Adam Young',
    'address': '1274 Gutierrez Row\nDavidside, AR 73007',
    'text': 'Image and wall no black. Increase American whom animal yard life.\nSee break social worry create. Wish top change similar.\nFeeling report evidence ball audience. Shake prevent federal.',
    'email': 'sosarachel@example.net',
    'phone_number': '(587)213-9726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeffery Carter',
    'Anthony Mayo',
    'Miss Tracie Benson',
    'Ryan Ramos',
    'Samantha Gill',
    'Alexis White',
    'Anthony Weaver',
    'Audrey Hardy',
    'Thomas Lloyd',
    'Duane Clark',
],
    'json': {
    'name': 'Daniel Lang',
    'address': '8571 Kathleen Lakes\nLake Samuelshire, DC 40121',
},
    'key76104': 'value523',
    'key83196': 'value27020',
    'key87131': 'value39088',
    'key85809': 'value69141',
    'key72302': 'value53645',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'David Valenzuela',
    'address': '4432 Perry Locks Suite 219\nIsaiahchester, AK 14896',
    'text': 'Radio group indicate level music. Material others close. Collection talk music career.\nLarge reduce identify environmental.',
    'email': 'fcampbell@example.net',
    'phone_number': '423.903.4342x09515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mark Ramirez',
    'Sarah Carrillo',
    'Melanie Garcia',
    'Shannon Burton',
    'Zachary Williams',
],
    'json': {
    'name': 'Gary Jackson',
    'address': 'PSC 8694, Box 8966\nAPO AA 79405',
},
    'key14850': 'value77523',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Shannon Green',
    'address': '924 James Fort Apt. 808\nWest Davidfurt, FL 46872',
    'text': 'Happen art once painting culture teach early with. Reason consumer situation put determine. Professor three effort outside official language.',
    'email': 'pwalton@example.org',
    'phone_number': '(393)223-0057',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Erin Douglas',
    'Vincent Carter',
    'Amber Stevenson',
    'Jason Young',
    'Kevin Bailey',
    'Ashley Reynolds',
],
    'json': {
    'name': 'Mitchell Lee',
    'address': 'Unit 8919 Box 2817\nDPO AP 70918',
},
    'key1718': 'value8278',
    'key74221': 'value91314',
    'key94933': 'value39312',
    'key67639': 'value79825',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Mackenzie George',
    'address': '3903 Carlos Road\nChristianshire, TX 85068',
    'text': 'Third the plan director itself degree. Growth trip end region. Film provide few consumer best kitchen speak market.',
    'email': 'alyssabest@example.org',
    'phone_number': '288.254.4544x5076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Turner',
    'Rebecca Walsh',
    'Rachael Torres',
    'Rhonda Richards',
    'Cheryl Roberts',
    'Sarah Simmons',
    'Shawn Bennett',
    'Daniel Maldonado',
    'Michael Taylor',
    'Melissa Garcia',
],
    'json': {
    'name': 'Amy Cardenas',
    'address': '008 Snyder Gateway\nSouth Wendy, AZ 41046',
},
    'key51032': 'value24094',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Michael Lee',
    'address': '9874 Christopher Loop\nSmithton, MD 34787',
    'text': 'Show meeting cup especially. Brother place own candidate her answer green. Discussion beautiful deal hear success.',
    'email': 'vroy@example.org',
    'phone_number': '688.980.7046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Thomas',
    'Jessica Miranda',
    'Eric Cruz',
    'Rita Bowman',
    'Sarah Bell',
    'John Vargas',
    'Robin Miller',
    'Stephanie Padilla',
],
    'json': {
    'name': 'Brent Olson',
    'address': '32654 Flores Alley\nNorth Gregoryfurt, KY 14053',
},
    'key26998': 'value34326',
    'key73767': 'value49170',
    'key36715': 'value22481',
    'key28398': 'value15373',
    'key66576': 'value64180',
    'key48316': 'value20526',
    'key63575': 'value253',
    'key69545': 'value9749',
    'key56752': 'value59107',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Kyle Golden',
    'address': '190 French Ramp Suite 927\nPort Angelaburgh, MO 43605',
    'text': 'Item miss return big. Light person benefit will of today bank.\nOnce main take condition rise. Information drive high animal. True look than through floor.',
    'email': 'ureed@example.org',
    'phone_number': '(528)399-2752x04795',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lindsey Stephens',
    'Helen Roberts',
    'Rachel Mathis',
    'Eric Sims',
    'Sheri Ingram',
    'Samantha Powell',
    'Eric Clark',
    'Cynthia Holland',
],
    'json': {
    'name': 'Mary Christian',
    'address': '558 Casey Ramp\nStokesmouth, CO 99212',
},
    'key91076': 'value38895',
    'key85115': 'value69346',
    'key40957': 'value4141',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Dana Salazar',
    'address': '2781 Cooper Pass Apt. 843\nLoganberg, AS 73295',
    'text': 'These future every especially. Oil gas adult message. Last worry dog white official economy leave.',
    'email': 'stephenporter@example.com',
    'phone_number': '850-816-8160x94926',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Adams',
    'Amanda Harris',
],
    'json': {
    'name': 'Jorge Wolfe',
    'address': '464 Brittany Forge\nEast Amberfort, NV 28508',
},
    'key86980': 'value68614',
    'key41177': 'value11435',
    'key74512': 'value89092',
    'key66430': 'value45046',
    'key10560': 'value90346',
    'key51943': 'value21236',
    'key65': 'value44959',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Joseph Young',
    'address': '428 Charlene Flat Apt. 321\nSouth Elizabethfort, WY 26474',
    'text': 'Range summer baby form join.\nCulture few civil pull body. Scene right court stock ok dinner. Over trip there. American matter how plant some.',
    'email': 'weberdenise@example.net',
    'phone_number': '(434)910-1727x6550',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lori Wood',
    'Teresa Hernandez',
    'Jonathan Suarez',
    'Timothy Villa',
],
    'json': {
    'name': 'Dakota Raymond',
    'address': '7878 Eric Stravenue Suite 418\nJerometown, FM 16665',
},
    'key53966': 'value11708',
    'key23222': 'value64974',
    'key91927': 'value9632',
    'key77987': 'value82222',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Lisa Gates',
    'address': 'PSC 7688, Box 5080\nAPO AA 23235',
    'text': 'Any dream wear drive lead whole. Catch court themselves dinner nation international third. Matter matter describe land fly decade price law.',
    'email': 'tiffany44@example.org',
    'phone_number': '(853)530-9216',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Travis Henderson',
    'Taylor Kennedy',
    'Austin Reyes',
    'Sheila Mosley',
],
    'json': {
    'name': 'Jennifer Reid',
    'address': '836 Shawn Drive\nHunterfort, WA 76771',
},
    'key9551': 'value26553',
    'key51243': 'value81921',
    'key52869': 'value78475',
    'key73194': 'value62344',
    'key57746': 'value40319',
    'key38586': 'value83493',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Nicholas Williams',
    'address': '910 Christopher Drive Suite 787\nPort Cody, ME 78537',
    'text': 'Lose head development computer final. Project these owner between large strategy.\nCongress pressure my argue song. Six western remember point. About building more fear.',
    'email': 'dhamilton@example.org',
    'phone_number': '001-884-622-8699x5531',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Molly Ellis',
    'Sharon Sanchez',
],
    'json': {
    'name': 'Nicholas Torres',
    'address': '06501 Eric Drives Suite 383\nKelseytown, NJ 91033',
},
    'key17099': 'value56648',
    'key50615': 'value24160',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Justin Fuentes',
    'address': '08816 Howard Fords\nDavidfurt, KS 25863',
    'text': 'Word necessary Republican lead. Theory couple west wonder rock.\nPhysical board pass occur inside among. Recently laugh consumer film many.',
    'email': 'david52@example.net',
    'phone_number': '892.747.5043x236',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Carter',
    'Joshua Martinez',
],
    'json': {
    'name': 'Mr. Derek Ford',
    'address': '80227 Thomas Squares\nBridgesbury, NC 14903',
},
    'key86835': 'value59867',
    'key99625': 'value9128',
    'key59484': 'value91792',
    'key74242': 'value76163',
    'key41750': 'value98621',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Amanda Osborne',
    'address': '20533 Arthur Loaf Apt. 946\nZhangberg, AR 69876',
    'text': 'Republican nearly never begin ask floor. Man forward simply American but cultural probably.',
    'email': 'silvachristopher@example.org',
    'phone_number': '001-674-797-8015x7950',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Clark',
    'Michael Dickerson',
],
    'json': {
    'name': 'Carlos Cross',
    'address': '9016 Alvarado Haven\nEast Nicole, MN 46537',
},
    'key18997': 'value40104',
    'key4885': 'value79916',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jason Simmons',
    'address': '03598 Diana Plaza\nHawkinschester, LA 30716',
    'text': 'Whether within painting. Story reason power significant. Eight type fire poor head as language.\nSomebody occur growth agency. Identify man common image do fly.',
    'email': 'norma92@example.com',
    'phone_number': '001-823-454-6406',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Tate',
    'Jacqueline Gibson',
    'Tara Nunez',
    'Amanda Owens',
],
    'json': {
    'name': 'Fred Barnes',
    'address': '9294 Gonzalez Extension\nWest Sandraville, ME 89858',
},
    'key49669': 'value28903',
    'key1813': 'value54289',
    'key35094': 'value40229',
    'key9690': 'value36758',
    'key56402': 'value2799',
    'key96177': 'value94729',
    'key55905': 'value36059',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Karen Mcgee',
    'address': '706 Alvarez Mills\nNovakhaven, MH 74075',
    'text': 'Behind nearly remember present note. Ground over room order color health develop south.',
    'email': 'hmiller@example.net',
    'phone_number': '001-413-249-9577',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Erickson',
    'Jessica Chen',
    'Shannon Carlson',
    'Ashley Kim',
    'Andrew Lang',
    'David Zamora',
    'Steven Robinson',
    'Jaime Clark',
],
    'json': {
    'name': 'Michael Scott',
    'address': 'Unit 2749 Box 2671\nDPO AP 41594',
},
    'key75424': 'value31489',
    'key7867': 'value38828',
    'key75506': 'value72092',
    'key95162': 'value64164',
    'key17344': 'value38389',
    'key73640': 'value69245',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Edward Howard',
    'address': '55788 Knight Pine Apt. 519\nDylanberg, CT 94823',
    'text': 'Whose have research size.\nAlmost order sing cold cost art behind. Choice though tend similar.\nCandidate day every economic owner. Baby mention each us. Often board friend minute include.',
    'email': 'jose47@example.net',
    'phone_number': '001-651-615-3959',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Matthews',
    'Shane Crosby Jr.',
],
    'json': {
    'name': 'Donna Dudley',
    'address': '3385 Cameron Junction\nLake Jeremy, TN 14701',
},
    'key52131': 'value40399',
    'key35546': 'value60971',
    'key1341': 'value64402',
    'key52275': 'value32470',
    'key75483': 'value22883',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Katherine May',
    'address': 'USNS White\nFPO AE 67078',
    'text': 'Individual attack attention within them entire. Indicate scientist important challenge body. Service bit attorney something establish happy. Black wish various stand.',
    'email': 'dwhite@example.net',
    'phone_number': '8063071755',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alex Rios',
    'David Horton',
    'Crystal Mcgee',
],
    'json': {
    'name': 'Nathan Martin',
    'address': '707 Silva Ranch\nSouth Lucas, CT 20145',
},
    'key27805': 'value20794',
    'key78741': 'value46680',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Anna Rodriguez',
    'address': 'PSC 1071, Box 0288\nAPO AP 59713',
    'text': 'Strategy majority activity hotel past wall remain. Lawyer before follow life.\nProgram rock develop nice. To central step skin more official collection couple.',
    'email': 'iturner@example.com',
    'phone_number': '001-534-430-9411x796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Mccoy',
    'Kimberly Rivera',
    'Noah Carr',
    'Kiara Johnson',
],
    'json': {
    'name': 'Grant Ortiz',
    'address': '9361 William Lights\nHernandezside, RI 42773',
},
    'key33300': 'value3675',
    'key35130': 'value84661',
    'key68706': 'value20549',
    'key65349': 'value29508',
    'key59146': 'value76465',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Natalie Jones',
    'address': '63156 Maurice Burg\nWilliamsstad, VI 11689',
    'text': 'Somebody water suddenly interview respond bag lose need. It detail onto road return.\nWide around play official. Production within at lead owner soldier glass person.\nOrder draw science note our.',
    'email': 'matthewpatterson@example.net',
    'phone_number': '(874)911-3876',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Gilbert',
    'John Snyder',
    'Dana Brady',
    'Tammy David',
    'Kevin Stanley',
    'Gary Johnston',
],
    'json': {
    'name': 'Tom Burke',
    'address': '16429 Vasquez Park\nNorth Kevin, IN 49475',
},
    'key97598': 'value66132',
    'key52774': 'value12169',
    'key4120': 'value63277',
    'key83507': 'value98949',
    'key7531': 'value68273',
    'key28102': 'value75341',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Melissa Castillo',
    'address': '0557 Edward Lock\nPatrickberg, ND 98515',
    'text': 'To organization side.\nPrice dog clearly their learn drop dark there. Student change outside traditional home staff money.\nGirl message few you my until night. By east Republican law beat reveal.',
    'email': 'jeffrey28@example.com',
    'phone_number': '(516)932-7885',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Cannon',
],
    'json': {
    'name': 'Bryan Bender',
    'address': '04874 Barrett Stream Apt. 298\nLake Stevenport, PA 98908',
},
    'key98998': 'value22820',
    'key91942': 'value79867',
    'key34753': 'value91746',
    'key49117': 'value27938',
    'key77519': 'value76767',
    'key61677': 'value6637',
    'key21331': 'value9773',
    'key59176': 'value86946',
    'key98875': 'value71240',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Brianna Johnson',
    'address': 'Unit 7262 Box 1106\nDPO AP 29503',
    'text': 'Concern specific south partner. Price conference language north too.\nExpect protect want win part country. Pay bag mean least.',
    'email': 'tina33@example.com',
    'phone_number': '+1-785-266-4471x34417',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Gibson',
    'Brandi Rogers',
    'Daniel Jones',
    'Marisa Jones',
    'Kellie Smith MD',
    'Patricia Lynn',
    'Bonnie Robertson',
],
    'json': {
    'name': 'Veronica Smith',
    'address': '153 Garcia Curve Suite 357\nSouth Antonio, NH 65431',
},
    'key54425': 'value6165',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Angela Peterson',
    'address': '991 Christian Prairie\nReyesfort, PA 20811',
    'text': 'Contain card art although nice born many. Subject above agency add Democrat entire rich. Soldier tonight section three peace clearly than.',
    'email': 'alyssanelson@example.com',
    'phone_number': '383.421.1169x338',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Berry',
    'Jason Huff',
    'Cathy Ruiz',
    'Robert Gutierrez',
    'Pamela Jones MD',
    'Kelly Smith',
],
    'json': {
    'name': 'Isabel Hudson',
    'address': '20982 Reid Mall Apt. 551\nPort Danny, WV 02667',
},
    'key73044': 'value6575',
    'key62554': 'value15179',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Caitlin Friedman',
    'address': '52144 Matthew Passage Apt. 508\nLake Brian, MI 38378',
    'text': 'Push appear almost possible yard. Blood spring media mission call.\nRich television treatment up. Public read positive evening action. Join again store end listen candidate coach.',
    'email': 'xjacobs@example.org',
    'phone_number': '451.669.2309',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Johnson',
    'Anna Smith',
],
    'json': {
    'name': 'Kenneth Hopkins',
    'address': '4591 Mathis Squares Apt. 986\nEast Daltontown, NM 49165',
},
    'key38358': 'value26154',
    'key47140': 'value71941',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Emily Garcia',
    'address': '128 Collins Branch Apt. 746\nPort Tracyberg, ME 76841',
    'text': 'Until feel bar president bar door red. Single value radio difficult little face national. Rate possible tend your.',
    'email': 'stephanierios@example.net',
    'phone_number': '700-224-1854x35578',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Adam Ross',
    'Kenneth Stevens',
    'Breanna White',
],
    'json': {
    'name': 'Sylvia Shaw',
    'address': '876 Donna Bypass Apt. 160\nSouth Ryan, WY 56436',
},
    'key81625': 'value30978',
    'key2577': 'value50581',
    'key91713': 'value39225',
    'key47836': 'value16235',
    'key24542': 'value32422',
    'key44579': 'value74331',
    'key68767': 'value86380',
    'key84886': 'value30000',
    'key2374': 'value58219',
    'key82387': 'value82974',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Andrew Mcfarland',
    'address': '62537 Nicholas Oval Suite 701\nSouth Stephanieview, AS 45681',
    'text': 'Suffer step throw situation place administration who.\nUnder her than feeling call notice look. Would person lead community. Memory pick experience sister.',
    'email': 'robinsonheather@example.com',
    'phone_number': '341.656.9159x83002',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lindsay Keller',
],
    'json': {
    'name': 'Luis Smith',
    'address': '8905 Garcia Mill\nNew Kelly, VI 27155',
},
    'key89570': 'value33127',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Brandon Gibson',
    'address': 'Unit 6303 Box 2612\nDPO AA 13974',
    'text': 'Six school stay house hit she probably camera. Raise interesting wide allow hard.\nWrite order network because send.\nChair customer right. Over anyone already color inside.',
    'email': 'sharpelizabeth@example.net',
    'phone_number': '+1-990-322-7632',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Dunn',
    'Kevin Alvarez',
    'James Hamilton',
    'Rebecca Baker',
    'Jeremy Brown',
    'Christopher Moon',
    'Martha Mills',
    'Jessica Neal',
    'Daniel Underwood',
],
    'json': {
    'name': 'Stephen Phillips',
    'address': '585 Kathy Views Apt. 044\nBellland, PA 02114',
},
    'key80553': 'value21290',
    'key44057': 'value28059',
    'key6187': 'value2360',
    'key70924': 'value26062',
    'key73853': 'value25197',
    'key28373': 'value87624',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Anthony Mitchell',
    'address': 'PSC 4113, Box 5247\nAPO AP 65856',
    'text': 'Address popular fast for their.\nWonder high above effort in project employee. Face sort every peace check.\nHome chair all approach leave bad form into. Win bill food job seven view present.',
    'email': 'joannstewart@example.org',
    'phone_number': '326.687.0038',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Kelly',
    'Lauren Costa',
    'Angela Morrison',
    'Kelsey Ramirez',
    'Kimberly Martinez',
    'Adam Armstrong',
],
    'json': {
    'name': 'Chad Barry',
    'address': '40762 Reed Ranch Suite 860\nRiveraville, ME 76929',
},
    'key46442': 'value99840',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Anne Santiago',
    'address': '31460 Weaver Meadow Apt. 044\nWongtown, FM 92237',
    'text': 'Born young course social apply. Watch deep subject ten expect carry across left.\nDetail reduce few Mr then around. That approach state fly lay. Represent focus happy anyone traditional author.',
    'email': 'elliottcarolyn@example.org',
    'phone_number': '805.632.5966',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kathy Mcdowell',
    'Jerry Reyes',
],
    'json': {
    'name': 'Kelsey Golden',
    'address': '5690 Sherry Track\nStewartville, CA 64009',
},
    'key78128': 'value24613',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Lauren Shelton',
    'address': '958 Michelle Forges\nEast Kimberly, GU 51733',
    'text': 'Claim drive consider able teach. Quality film leg hear.',
    'email': 'castillojack@example.net',
    'phone_number': '(330)610-5612x2408',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Glass',
    'Timothy Brown',
    'Kyle Nguyen',
],
    'json': {
    'name': 'Mariah Walker',
    'address': '291 Jacob Park Suite 268\nAshleytown, IA 73779',
},
    'key42412': 'value22822',
    'key83466': 'value22735',
    'key27962': 'value6725',
    'key75926': 'value64742',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kathy Harris',
    'address': '845 Antonio Square\nToddfort, DE 12580',
    'text': 'Stop rise onto report successful already. Fast result human much.\nBall guess maybe. American tax main experience much.',
    'email': 'cynthiaware@example.org',
    'phone_number': '239-597-4753x059',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mike Fletcher',
    'Jerry Gould',
    'Rebecca Miller',
    'Brandi Williams',
    'Anthony Wilkerson',
    'April Baker',
],
    'json': {
    'name': 'Christopher Miller',
    'address': 'Unit 8324 Box 4281\nDPO AP 97455',
},
    'key31605': 'value65863',
    'key48042': 'value94908',
    'key21375': 'value83300',
    'key12517': 'value57110',
    'key3868': 'value93783',
    'key56539': 'value63990',
    'key53333': 'value53988',
    'key40757': 'value49809',
    'key64878': 'value30665',
    'key29050': 'value79015',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Nathan Mathis',
    'address': '1452 Ortiz Hill Apt. 415\nMeganshire, WI 19427',
    'text': 'Hair kind century organization option. Research south outside goal read attack. Finish job rise energy either message notice.',
    'email': 'hphillips@example.net',
    'phone_number': '(526)610-7135',
    'array_int_dynamic': [
    18735,
],
    'array_varchar_dynamic': [
    'Chad Mcmahon',
],
    'json': {
    'name': 'Miguel Patterson',
    'address': '106 Rodriguez Lights Suite 079\nAndersonland, FM 38717',
},
    'key31083': 'value65613',
    'key43607': 'value33721',
    'key72709': 'value99643',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Ana Cooper',
    'address': '9412 Sandra Meadows\nNorth Jamesbury, GU 32141',
    'text': 'Item son arm with collection group since. Change yes beat painting watch. Edge beyond significant successful expert or trip.',
    'email': 'jdecker@example.net',
    'phone_number': '+1-380-775-2089x546',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Perry',
    'Christie Gibson',
    'James Ramirez',
],
    'json': {
    'name': 'Colton Schultz',
    'address': 'PSC 5750, Box 5632\nAPO AP 27776',
},
    'key59579': 'value55225',
    'key8091': 'value8054',
    'key35299': 'value88101',
    'key98805': 'value25777',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Derrick Gutierrez MD',
    'address': 'Unit 6535 Box 4704\nDPO AA 94176',
    'text': 'Star member everybody trouble standard remember quite. Add still check other carry. Wrong could conference case find. Available practice recognize animal field baby wife.',
    'email': 'ucook@example.com',
    'phone_number': '+1-577-326-9498x265',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Scott',
    'Jeffrey Stephens',
    'Richard Reyes',
    'Krista Huynh',
    'Bryce Welch',
    'Xavier Garcia',
    'Rebecca Dixon',
    'Ryan Gibson',
],
    'json': {
    'name': 'Michael Martinez',
    'address': '38017 Perry Keys\nStaffordbury, GA 08691',
},
    'key87742': 'value35411',
    'key83378': 'value79608',
    'key70608': 'value43864',
    'key28728': 'value14291',
    'key22590': 'value97875',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Miss Sherry Kidd',
    'address': '197 Drake Brooks\nSethborough, MT 06140',
    'text': 'Arm music produce international receive. Measure describe its place represent.\nSo machine war church let road state. Continue recognize administration hot should.',
    'email': 'douglasdougherty@example.net',
    'phone_number': '369-271-3425',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Caleb Ford',
    'Jill Cantu',
    'Andrew Adams',
    'Jeff Poole',
    'Kevin Shepherd',
    'Matthew Briggs',
    'Joseph Grant',
    'Jeremy Ballard',
    'Nicole Williams',
],
    'json': {
    'name': 'Anthony Donovan',
    'address': '2033 Tran Inlet Apt. 605\nWest Joanstad, OH 77938',
},
    'key13067': 'value76217',
    'key25791': 'value4321',
    'key722': 'value61305',
    'key45879': 'value27821',
    'key34858': 'value72791',
    'key87332': 'value41738',
    'key1512': 'value39816',
    'key72400': 'value85804',
    'key49993': 'value27836',
    'key28802': 'value34709',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Mark Baldwin',
    'address': '1304 Hunt Meadow\nJeremyside, VI 43948',
    'text': 'Safe bad generation window son theory.\nCourt tonight off dog two soon anyone. Positive agency throughout near account bad. Condition also next cup black.',
    'email': 'thomasmiddleton@example.net',
    'phone_number': '(454)491-9733x2128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sheryl Peck',
    'Audrey Powell',
    'Courtney Brown',
    'Thomas Patton',
    'Ashley Jennings',
    'Christine Vega',
    'Samuel Kelley',
    'Angela Decker',
],
    'json': {
    'name': 'David Cook',
    'address': '79017 Alexander Rapids Apt. 755\nDiazview, TN 25023',
},
    'key92729': 'value99368',
    'key46916': 'value81284',
    'key89324': 'value96904',
    'key80250': 'value10981',
    'key4672': 'value27864',
    'key69136': 'value29201',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Andrew Valencia',
    'address': '34678 Corey Creek Apt. 748\nNorth Joseview, VI 97647',
    'text': 'Sell fire list experience call affect. Question conference author. Today everyone safe image compare owner.',
    'email': 'brian69@example.com',
    'phone_number': '+1-383-649-0349',
    'array_int_dynamic': [
    47450,
],
    'array_varchar_dynamic': [
    'Jennifer Morales',
    'Joe Clark',
    'Cassandra Whitaker',
    'Brenda Bush',
    'William Medina',
    'Kristin Wilson',
    'Lisa Palmer',
    'Preston Simon',
    'Suzanne Perez',
    'Kari Garcia',
],
    'json': {
    'name': 'Stephen Lopez',
    'address': '70490 Matthew Crest\nEast Lindafort, TN 59684',
},
    'key8846': 'value72713',
    'key86539': 'value88826',
    'key45716': 'value19858',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Tammy Shelton',
    'address': '9592 Prince Mews\nPort Katrinaport, WA 98288',
    'text': 'Candidate half force national. War role pull any machine air possible. Skill member population media run.',
    'email': 'phillip09@example.org',
    'phone_number': '309-418-6138',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Kelly',
    'Kenneth Duran',
    'Joseph Benjamin',
    'Sharon Hughes',
    'Kenneth Russell',
    'Chad Mclaughlin',
    'Mark Tucker',
    'Tammy Coleman',
],
    'json': {
    'name': 'Jennifer Vaughan',
    'address': '80878 Dawn Manors\nWest Lisa, NE 62006',
},
    'key26242': 'value36258',
    'key64356': 'value7318',
    'key31165': 'value38978',
    'key72948': 'value67143',
    'key73857': 'value89200',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Sean Lowery',
    'address': '9138 Welch Gardens\nNorth Alicia, NH 32777',
    'text': 'Few she entire exactly. Edge compare hit.\nCompany process because shoulder sell center million lawyer. Moment career still student least marriage. South rich get trial religious sing human.',
    'email': 'croberts@example.net',
    'phone_number': '436-757-5362x8591',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Justin Mccarty',
],
    'json': {
    'name': 'Rebecca Green',
    'address': '39545 Hill Villages\nChanmouth, IL 41258',
},
    'key39354': 'value44524',
    'key28835': 'value69033',
    'key30181': 'value79346',
    'key4070': 'value45367',
    'key45021': 'value29419',
    'key37679': 'value1600',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Julie Martinez',
    'address': '681 Kristin Islands\nClarkside, AS 91816',
    'text': 'Contain over speech outside because. Cover movie medical lawyer. Develop stage child car nothing process have.\nHuman simple affect. Commercial bed much go discover take base.',
    'email': 'ariana81@example.org',
    'phone_number': '+1-633-257-1626x814',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Nolan',
    'Julian Murphy',
    'Catherine Rivera',
    'Joseph Banks',
    'Kenneth Bowen',
    'Brittany Parker',
    'Terry Cooper',
    'Matthew Bray',
    'Cynthia Oneal',
    'Heidi Roberts',
],
    'json': {
    'name': 'Sarah Coleman',
    'address': '28335 Wheeler Village Suite 233\nNicoleland, WV 45270',
},
    'key87535': 'value87282',
    'key19320': 'value86885',
    'key88507': 'value53973',
    'key11643': 'value72794',
    'key83637': 'value75482',
    'key43455': 'value465',
    'key20635': 'value95291',
    'key79271': 'value5049',
    'key61199': 'value26700',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Timothy Garcia',
    'address': '91130 Decker Villages\nWest Alexanderbury, CO 51940',
    'text': 'Watch its offer might customer participant carry. Poor thing something.\nListen husband politics company. Technology history relationship somebody these we available.',
    'email': 'bsaunders@example.net',
    'phone_number': '+1-545-915-5199',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Evans',
    'Grace Mcintyre',
    'Eric Hughes',
    'Miguel Alexander',
    'Brittany Schroeder',
    'Mathew Perry',
    'Misty Marshall',
    'Elizabeth Turner',
],
    'json': {
    'name': 'Andrew Mccullough',
    'address': '62180 Johnson Cape\nDonaldborough, CT 84157',
},
    'key65341': 'value23815',
    'key68761': 'value40458',
    'key93835': 'value76542',
    'key32321': 'value90190',
    'key7524': 'value90824',
    'key59416': 'value17479',
    'key78715': 'value56463',
    'key40086': 'value60373',
    'key29487': 'value69379',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Joseph Kelly',
    'address': '18319 Martin Highway Suite 754\nBonnieton, NJ 78206',
    'text': 'Half machine deal wonder rate soon. As bit series high region off. Whose while thank number wife study.',
    'email': 'fharper@example.org',
    'phone_number': '001-717-444-2013',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Susan Delgado',
    'Derek Joseph',
    'Justin Saunders',
    'Shannon Flores',
    'Stephanie Payne',
    'Marc Garcia',
    'Ryan Phillips',
    'Jaclyn Hawkins',
],
    'json': {
    'name': 'Amanda Stephens',
    'address': 'Unit 7620 Box 5829\nDPO AE 31414',
},
    'key46111': 'value26228',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Rebecca Willis',
    'address': '12125 Wade Groves\nWest Sierra, NE 68195',
    'text': 'Develop stand hope strong. Focus identify five explain face dog but. Hope so different play fight watch two.',
    'email': 'villegasjacqueline@example.org',
    'phone_number': '914.424.7752x886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jody Jackson',
    'Shelley West',
    'Maria Price',
    'Scott Williams',
    'Wesley Bautista',
    'David Paul',
    'Leslie Ortiz',
    'James Young',
    'Patricia Wilson',
],
    'json': {
    'name': 'Justin Sanchez',
    'address': '979 Miller Neck Suite 287\nAndersonville, MP 40149',
},
    'key34916': 'value20007',
    'key56675': 'value31922',
    'key94925': 'value55544',
    'key44523': 'value81556',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Micheal Perry',
    'address': '931 Kenneth Walks Apt. 393\nDominguezshire, OK 57814',
    'text': 'Appear support from think. Child build miss good.\nTraditional serious reflect training road. Tell current else.',
    'email': 'bdean@example.com',
    'phone_number': '001-410-326-6323',
    'array_int_dynamic': [
    47151,
],
    'array_varchar_dynamic': [
    'Kelly Lane',
    'Ashley Johnson',
    'Samantha Banks',
    'Raymond Duran',
],
    'json': {
    'name': 'Stephanie Wood',
    'address': '8619 Deborah Junctions\nLake Douglasborough, TN 92581',
},
    'key97179': 'value18830',
    'key10950': 'value39685',
    'key48300': 'value19504',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Kathy Chen',
    'address': '00175 Mccann Springs Suite 571\nTinafurt, KS 56455',
    'text': 'Image teacher best charge government they or production. Side wind southern sure walk treat.',
    'email': 'ustafford@example.org',
    'phone_number': '731-478-4713x6685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Calderon',
    'Lindsey Price',
    'Zachary Knapp',
],
    'json': {
    'name': 'Tonya Hernandez',
    'address': '510 Julie Park Apt. 461\nHernandezhaven, CT 08027',
},
    'key83655': 'value81166',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kayla Hall',
    'address': '9117 Douglas Crest\nJenkinsside, CO 51744',
    'text': 'Seek feel movie. Daughter several exist television yard society.\nUnit air alone have yes piece difficult occur. Daughter mention contain tax above commercial.',
    'email': 'stephaniegriffin@example.org',
    'phone_number': '(369)552-9388x184',
    'array_int_dynamic': [
    32966,
],
    'array_varchar_dynamic': [
    'David Lang',
    'Justin Davis',
    'Kelly Sheppard',
    'Jeffrey Hamilton',
    'Lucas Moore',
    'Charlene Mckenzie',
    'Samuel Mason',
],
    'json': {
    'name': 'Courtney Dixon',
    'address': '498 Benjamin Union Suite 352\nNew Edward, KS 97616',
},
    'key42757': 'value99439',
    'key14918': 'value49492',
    'key56691': 'value9174',
    'key5758': 'value58362',
    'key87147': 'value93114',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Timothy Townsend',
    'address': '7664 Massey Brook Apt. 511\nWest Kimberly, FM 52486',
    'text': 'Could west time week data. Bed argue American manage offer human.\nUnder follow show board. Deep best quickly create national response. Statement current artist shake high leader statement sometimes.',
    'email': 'jeffrey85@example.net',
    'phone_number': '(817)701-5619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Fitzgerald',
    'Jason Wood',
    'Patricia Hill',
    'Jeanette Wright',
    'Katie Rogers',
    'Andrew Robbins',
    'Tonya Gordon',
    'Julie Scott',
    'Elizabeth Johns',
],
    'json': {
    'name': 'Lance Orr',
    'address': '2188 Christina Mills Suite 137\nEast Debraville, NM 64327',
},
    'key46555': 'value48964',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Joseph Griffith',
    'address': '2900 Murray Route\nLake Margaret, WI 16746',
    'text': 'Available history media smile. Behind set art particularly than forget.\nHear agent others drop. Pay lay party hold most later yes.\nProfessor traditional interest sound. Nice laugh question company.',
    'email': 'ltanner@example.net',
    'phone_number': '(613)950-0103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Katrina Phillips',
    'Laura Stout',
    'Ryan Kelly',
],
    'json': {
    'name': 'Logan Lopez',
    'address': '8912 Michelle Dam Apt. 076\nCummingschester, OR 24363',
},
    'key18009': 'value98787',
    'key27386': 'value64130',
    'key54619': 'value52094',
    'key73917': 'value68595',
    'key18976': 'value9886',
    'key35082': 'value64548',
    'key30638': 'value92229',
    'key21927': 'value71883',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Daniel Glover',
    'address': '9001 Wendy Road\nJacobmouth, GA 23061',
    'text': 'Thing such production relate movie though. Carry event body once nature door win. Drive modern whatever mention suddenly.',
    'email': 'vblack@example.com',
    'phone_number': '001-599-985-3379x4821',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Troy Allen',
    'Ryan Macdonald',
],
    'json': {
    'name': 'William Moore',
    'address': '903 Prince Radial Suite 692\nNorth Marcusburgh, PA 02677',
},
    'key84565': 'value10820',
    'key69519': 'value71499',
    'key24684': 'value98453',
    'key50624': 'value50457',
    'key55747': 'value61233',
    'key71315': 'value62152',
    'key92807': 'value36465',
    'key52075': 'value10375',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Matthew Stewart',
    'address': '9362 Rodriguez Overpass Apt. 661\nLake Pennyville, MN 62283',
    'text': 'Whatever piece carry international beat. Sure heavy evidence possible sort.',
    'email': 'daniel12@example.com',
    'phone_number': '001-630-481-9785x19886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Duane Maddox',
    'Charles Gray',
    'Keith Vasquez',
    'Leslie Fernandez',
    'Jennifer Hickman',
    'Brad Hopkins',
    'Mark Friedman',
    'Eric Hayden',
],
    'json': {
    'name': 'Charles Hansen',
    'address': '3109 Clark Place Apt. 615\nPort Ashleyberg, KY 25722',
},
    'key70956': 'value31781',
    'key45695': 'value96238',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Robert Morales',
    'address': '5996 Myers Via\nCodymouth, DC 25917',
    'text': 'Much yes trial.\nCompany conference catch activity. Lay there art both project center.\nHe strategy tree step parent leg. Accept old energy action. Single in today place.',
    'email': 'taylor86@example.com',
    'phone_number': '9866206923',
    'array_int_dynamic': [
    50290,
],
    'array_varchar_dynamic': [
    'Christian Maxwell',
    'Megan Perez',
    'Jonathan Miller',
    'Glenn Mcdonald',
    'Gabriel Hill',
],
    'json': {
    'name': 'James Palmer',
    'address': '97361 Maria Curve Suite 965\nNorth David, DC 24910',
},
    'key47666': 'value89992',
    'key49837': 'value78568',
    'key44474': 'value20646',
    'key37825': 'value4349',
    'key95070': 'value5423',
    'key35659': 'value72393',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Dustin Diaz',
    'address': '7169 Steven Extensions Apt. 685\nWilsonborough, SC 65890',
    'text': 'Executive discuss why general none purpose quickly. Window red politics attack sound almost of.\nStuff idea painting ready knowledge town. Benefit our federal TV. Because point to these police.',
    'email': 'cynthia32@example.org',
    'phone_number': '(996)879-7178',
    'array_int_dynamic': [
    72959,
],
    'array_varchar_dynamic': [
    'Michael Smith',
    'Juan Garcia',
    'Mark Armstrong',
    'Ronald Moore',
],
    'json': {
    'name': 'Kristina Reed',
    'address': '90619 Hull Lights\nNew Susanmouth, VI 60501',
},
    'key47466': 'value35762',
    'key79152': 'value18518',
    'key13087': 'value31806',
    'key28953': 'value68816',
    'key24795': 'value77322',
    'key38927': 'value21254',
    'key61860': 'value61053',
    'key51072': 'value91074',
    'key46788': 'value10235',
    'key78937': 'value30800',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Lisa Lucero',
    'address': '32820 Foster Via Apt. 480\nPort Shelley, OR 30036',
    'text': 'Significant fact point kid whatever weight write significant. Marriage concern inside make husband sound.',
    'email': 'hrogers@example.com',
    'phone_number': '001-224-835-1908',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Oliver',
    'Robert Underwood',
    'Cassandra Wheeler',
    'Michael Hays',
    'Heather Garner',
    'Gabriel Rodriguez',
    'Angel Rogers',
    'Joseph Griffin',
    'Brianna Beard',
    'Yvonne Stewart',
],
    'json': {
    'name': 'Jade Perkins',
    'address': '03005 Colleen Street Suite 773\nNicoleshire, AS 25304',
},
    'key99816': 'value83954',
    'key38981': 'value89487',
    'key4786': 'value15042',
    'key95520': 'value88212',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Julia Joseph',
    'address': '7236 Derek Harbors Apt. 519\nNew Joshuaview, NJ 32240',
    'text': 'Since keep bank kid. In new likely indeed.\nCut commercial television gun system building. Feel year number nothing take yes far. Rise information what today difficult.',
    'email': 'marywebb@example.com',
    'phone_number': '(983)721-3081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jeremiah Weeks',
    'Alex Castaneda',
    'Michael Ford',
    'Isaac Sanders',
    'Lee Jackson',
    'James Snyder',
    'Stacey Smith',
    'Kyle Thornton',
    'Amanda Flores',
],
    'json': {
    'name': 'Tim Young',
    'address': '14795 Sonya Dale Apt. 142\nOrtegaburgh, FL 48331',
},
    'key47167': 'value82938',
    'key87645': 'value5624',
    'key29048': 'value77164',
    'key99032': 'value76751',
    'key81691': 'value43352',
    'key89818': 'value73342',
    'key22396': 'value12224',
    'key4015': 'value1520',
    'key5291': 'value94371',
    'key27272': 'value96345',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Shawn Mendoza',
    'address': '954 Kyle Rest\nNorth Josephstad, NJ 05310',
    'text': 'Young popular want act green. Option allow boy paper arrive show. Career place number simply room program.',
    'email': 'cfranklin@example.com',
    'phone_number': '558.631.2597x5416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Jones',
    'Jason Thompson',
    'James Davis',
    'Theresa Howell',
    'Heather Roberson',
    'Miranda Stewart',
    'Rebecca Bowman',
    'Denise Wood',
    'Randall Hernandez',
],
    'json': {
    'name': 'Jessica Brandt',
    'address': '629 Hurst Wells\nSouth Christopherfurt, UT 32052',
},
    'key49715': 'value66616',
    'key62863': 'value20032',
    'key52383': 'value65929',
    'key57819': 'value19050',
    'key31218': 'value1409',
    'key85608': 'value29716',
    'key9203': 'value57737',
    'key51205': 'value65679',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Luis Hobbs',
    'address': '972 Vaughn Views\nJohnton, AL 80098',
    'text': 'Quality work commercial employee. Pay when occur cup. Traditional region draw eight.\nSkill add interest sign term. Practice arrive particularly.',
    'email': 'ronald51@example.com',
    'phone_number': '(733)660-6090x292',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeff Ochoa',
    'Christina Little',
    'Danielle Morales',
],
    'json': {
    'name': 'Jennifer Wright',
    'address': '4410 Jonathon Lane Apt. 233\nAshleymouth, MA 05380',
},
    'key27606': 'value45822',
    'key66420': 'value4227',
    'key65959': 'value57891',
    'key62093': 'value27054',
    'key45986': 'value94636',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Lindsey Graham',
    'address': '66367 Juan Fords Suite 965\nCookbury, SD 08633',
    'text': 'Nature kind blood visit so staff television. Property true girl it government four role. Time lead behind those population price.\nExist push per word real name keep community.',
    'email': 'parkerdavid@example.org',
    'phone_number': '4582845157',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Nolan',
    'Joshua Ford',
    'Sean Serrano',
    'Jesus Johnson',
    'Kathleen Webb',
],
    'json': {
    'name': 'Donna Sanchez DDS',
    'address': '0780 Stephens Spur Apt. 270\nAllisonbury, MA 31417',
},
    'key79043': 'value1723',
    'key7607': 'value68149',
    'key99388': 'value21250',
    'key8024': 'value51518',
    'key33430': 'value17831',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Shannon Lopez',
    'address': '01957 Roberts Route\nNew Javierbury, UT 81850',
    'text': 'Draw lead available interview forward. Then read executive general suffer yeah.\nForget especially stage mother financial our difficult. Morning whom major inside. Everyone voice statement which.',
    'email': 'robert63@example.net',
    'phone_number': '262-333-2166x6365',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Flynn',
    'Matthew Strickland',
    'Elizabeth Carter',
    'Rhonda Johnson',
    'Randy Robinson',
],
    'json': {
    'name': 'Mariah Bell',
    'address': '3791 Brent Spurs\nSouth Brent, HI 61710',
},
    'key75395': 'value16417',
    'key6493': 'value7439',
    'key63171': 'value3141',
    'key59725': 'value74270',
    'key97425': 'value54759',
    'key64239': 'value19185',
    'key77199': 'value79022',
    'key47204': 'value23794',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Julie Roman',
    'address': '35649 David Roads Suite 100\nWest Andrea, SD 03965',
    'text': 'Among student although environmental month. As mother involve face campaign.\nAnimal staff drop yeah suddenly TV south. Choose method develop pull as produce training. Success machine often his.',
    'email': 'montgomeryjoshua@example.org',
    'phone_number': '(989)749-0597',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Barrera',
    'George Davis',
    'Jennifer Salazar',
    'Whitney James',
    'David Miles',
],
    'json': {
    'name': 'Richard King',
    'address': '940 Steven Dam Apt. 057\nRonniefort, ID 03826',
},
    'key61968': 'value56177',
    'key77268': 'value79737',
    'key91623': 'value96029',
    'key56731': 'value53530',
    'key45948': 'value98563',
    'key19686': 'value77823',
    'key30336': 'value74667',
    'key77223': 'value26100',
    'key22931': 'value287',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Sharon Robinson',
    'address': '562 Nguyen Manor Apt. 077\nLake Wendymouth, TN 63558',
    'text': 'Name mind thank reality cover. Religious finally opportunity television its point.',
    'email': 'lrowland@example.org',
    'phone_number': '458-236-8320x202',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'William Martinez',
    'Erin Rojas',
    'Mr. Russell Wilson',
    'Kayla Reynolds',
    'Vanessa Weiss',
],
    'json': {
    'name': 'Kevin Byrd',
    'address': '32854 Brooke Squares Suite 343\nDavistown, IN 69068',
},
    'key45327': 'value98912',
    'key72126': 'value16564',
    'key85265': 'value2828',
    'key74598': 'value66095',
    'key11890': 'value63427',
    'key38025': 'value3763',
    'key40433': 'value59711',
    'key70438': 'value68043',
    'key64211': 'value92598',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Christopher Cordova',
    'address': '81367 Howe Field Suite 278\nAvilachester, TX 14126',
    'text': 'Choice factor clearly. Like news voice group near. Allow hand rule will.\nWork than human bank. Exist mission never course assume.',
    'email': 'gina99@example.com',
    'phone_number': '817-342-2290x284',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Gross',
    'Bradley Morgan',
    'Taylor Anthony',
],
    'json': {
    'name': 'Jessica Phelps',
    'address': 'USNV Campbell\nFPO AE 94980',
},
    'key4863': 'value90120',
    'key45912': 'value15848',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Thomas Choi',
    'address': '129 Alexander Divide\nEast Brandon, HI 77823',
    'text': 'Must page truth feel. Friend deal power attack audience give financial part. Week need effort behavior paper world evening.',
    'email': 'oharris@example.net',
    'phone_number': '001-642-576-3859x735',
    'array_int_dynamic': [
    33029,
],
    'array_varchar_dynamic': [
    'Kaitlin Williams',
    'Spencer Arnold',
],
    'json': {
    'name': 'Pamela Davis',
    'address': '28297 Ricky Mountain Suite 868\nLake Annettebury, MO 27189',
},
    'key85270': 'value80512',
    'key51793': 'value22144',
    'key15002': 'value4710',
    'key58325': 'value83918',
    'key49835': 'value9767',
    'key71824': 'value15996',
    'key33341': 'value76323',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Stacie Gaines',
    'address': '9339 Holmes Fords Suite 907\nChristinaberg, CT 05883',
    'text': 'Allow she weight of later. Language wrong the medical always.\nThird staff news measure issue speak. Statement until contain. Performance suffer right happen arrive fight. Talk big long safe.',
    'email': 'hardindonald@example.net',
    'phone_number': '201.613.1839x67751',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Murillo DDS',
    'Christina Harrington',
    'Kayla Garrett',
    'Austin Castro',
    'Hannah Todd',
    'Robert Smith',
    'Sara Suarez',
],
    'json': {
    'name': 'Christina Garrett',
    'address': '88455 Zachary Manor Suite 552\nRobinsonton, MS 12764',
},
    'key44435': 'value20679',
    'key20613': 'value14831',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Sherry Marquez',
    'address': '1331 Mason Well\nScottshire, NJ 61277',
    'text': 'Prove identify response final speech politics. Every reality option should individual. Sometimes realize power camera build.\nKey machine campaign size town. Day sound treat participant show final.',
    'email': 'jasonhebert@example.net',
    'phone_number': '+1-486-256-5897x5041',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Mason',
    'Jeffrey Sanders',
],
    'json': {
    'name': 'Julian Ortiz DVM',
    'address': '39928 Devin Roads Apt. 576\nPort Robertborough, ND 95780',
},
    'key93043': 'value30761',
    'key7109': 'value75782',
    'key53710': 'value73862',
    'key32617': 'value88176',
    'key93915': 'value94942',
    'key67583': 'value63892',
    'key79904': 'value6830',
    'key24200': 'value5326',
    'key58365': 'value51217',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Lisa Barnes',
    'address': '294 David Islands Suite 120\nSouth Jamiefurt, SC 50737',
    'text': 'Agree pay specific serve husband tend approach. Game film hot report soldier. Fund account own plant.',
    'email': 'munozphillip@example.com',
    'phone_number': '(472)392-2292x6464',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Jackson',
],
    'json': {
    'name': 'Jeffery Gordon',
    'address': 'USNV Rodriguez\nFPO AE 68557',
},
    'key71977': 'value61590',
    'key96646': 'value31966',
    'key59726': 'value56325',
    'key31996': 'value82911',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Thomas Harris',
    'address': '984 Santiago Pass Suite 952\nCookstad, WI 65774',
    'text': 'Bag bill recent top people. Understand body hand continue at one.\nUsually fall training value only edge together cultural. Every tonight statement.',
    'email': 'bradfordkelsey@example.org',
    'phone_number': '(428)370-2791',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Bush',
    'Debra Patel',
],
    'json': {
    'name': 'Amanda Howard',
    'address': '809 Foster Expressway\nWest Debra, ND 12550',
},
    'key82505': 'value35964',
    'key40670': 'value42808',
    'key44876': 'value47866',
    'key94833': 'value34083',
    'key24050': 'value38036',
    'key87309': 'value39698',
    'key81686': 'value68616',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Aaron Taylor',
    'address': 'PSC 7216, Box 2446\nAPO AE 41029',
    'text': 'Few draw writer especially or. Reveal discussion professor little sell I out.\nBreak fish see lay view order. How sound event recently. Pm rise perform station.',
    'email': 'sstewart@example.org',
    'phone_number': '001-833-927-8339x69878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'April Garner',
    'Tony Hudson',
    'Krystal Hernandez',
],
    'json': {
    'name': 'Jacob Burns',
    'address': '1531 Sanchez Path\nEast Chasehaven, MN 79399',
},
    'key52416': 'value44865',
    'key32734': 'value68435',
    'key77033': 'value71652',
    'key54436': 'value20199',
    'key88351': 'value16572',
    'key61795': 'value12521',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Brian Swanson',
    'address': '99823 Hart Cove\nSouth Davidside, MA 99332',
    'text': 'Maintain all career turn. Summer yet center finish.\nBall ago evidence religious available suggest well. Teach cost seven thus.',
    'email': 'guerrerorobert@example.org',
    'phone_number': '001-775-955-8411x558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Craig',
],
    'json': {
    'name': 'Anna Scott',
    'address': '9914 Zoe Locks Suite 444\nWest Angelatown, WI 25141',
},
    'key32353': 'value24812',
    'key34664': 'value17803',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Sean Young',
    'address': 'USS Guerra\nFPO AE 08681',
    'text': 'Fast whether he. Send three ball. Say rest old science whether case involve.\nSix trouble pick.\nHome carry visit lot gas figure. Try music space campaign ground.',
    'email': 'uallen@example.com',
    'phone_number': '215-224-4884x6757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Robert Simmons',
    'Scott Mckinney',
    'Timothy Mullins',
    'Isabella Hancock',
    'Barry Richmond',
    'Michelle Young',
    'Joy Holt',
    'Cheryl Ryan',
],
    'json': {
    'name': 'James Franco',
    'address': '933 Perez Wall Suite 159\nNew Victorialand, HI 63579',
},
    'key97304': 'value62584',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'David Washington',
    'address': '640 Kimberly Village Suite 020\nSouth Jesusburgh, FL 01879',
    'text': 'Simple detail drive there keep. Light purpose marriage oil. Pressure fund test student surface four very.',
    'email': 'ayalakevin@example.org',
    'phone_number': '(328)545-3259x5086',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Mclaughlin',
    'Jennifer Robinson',
    'Blake Tran',
    'Hannah Riggs',
    'Sonya Phillips',
],
    'json': {
    'name': 'Lindsey Davis',
    'address': '202 White Forest\nGuerreroport, WI 84318',
},
    'key50533': 'value6142',
    'key22467': 'value51647',
    'key90536': 'value18636',
    'key64754': 'value67112',
    'key25713': 'value16496',
    'key38495': 'value9858',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Nicholas Brown',
    'address': '0261 Martin Tunnel Suite 452\nNorth William, NM 88003',
    'text': 'Call charge recognize shoulder huge know possible. To make it site ten shake.\nParent expert perhaps expect economy already wife. Bring exist power section new act speak.',
    'email': 'cmaynard@example.net',
    'phone_number': '+1-443-950-7752x877',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Erica Long',
    'Kevin Rhodes',
    'Lisa Ellis',
    'Kimberly Jefferson',
    'Charles Herrera',
],
    'json': {
    'name': 'Nathan Thompson',
    'address': '97862 Gross Garden\nNew Stephen, PW 68530',
},
    'key4967': 'value52109',
    'key78201': 'value80299',
    'key4202': 'value47291',
    'key33135': 'value79598',
    'key74860': 'value33851',
    'key65827': 'value30349',
    'key16895': 'value67937',
    'key55433': 'value87267',
    'key15817': 'value63575',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Amanda Garza',
    'address': '4300 Alvarado Lodge Suite 179\nLewisshire, MO 32719',
    'text': 'Front medical amount. Fear friend participant control movement consider against.\nUnderstand law measure eight health save. Personal thank network next continue ready inside.',
    'email': 'hperkins@example.org',
    'phone_number': '(862)805-8295x03133',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Karla Davis',
    'Hector Nichols',
    'Zachary Castillo Jr.',
    'Lisa Reyes',
],
    'json': {
    'name': 'Andrea Hayes',
    'address': '44750 Chris Mall Apt. 537\nPhillipsbury, CA 63879',
},
    'key24341': 'value9691',
    'key97097': 'value8672',
    'key25944': 'value72884',
    'key11580': 'value81589',
    'key51775': 'value37986',
    'key88160': 'value49957',
    'key25538': 'value73157',
    'key24402': 'value27160',
    'key83607': 'value26499',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Trevor Black',
    'address': '7558 King Corners Apt. 342\nWalkertown, UT 27358',
    'text': 'Time everything artist price quickly purpose. Parent institution rest probably.\nCover why time top person mean. What support already speak within support.',
    'email': 'belllisa@example.org',
    'phone_number': '819-437-8156x175',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Donald Wright',
    'Jeffery Kelly',
    'Tiffany Ritter',
    'Kimberly Stone',
    'Steven Ferguson',
    'Evelyn Solis',
    'Renee Farley',
    'Joseph Raymond',
],
    'json': {
    'name': 'Carrie Smith',
    'address': 'USNS Medina\nFPO AE 23003',
},
    'key39065': 'value7112',
    'key77140': 'value85133',
    'key71963': 'value34115',
    'key96142': 'value66865',
    'key80565': 'value69346',
    'key60896': 'value48133',
    'key33237': 'value16398',
    'key20498': 'value21280',
    'key61870': 'value36761',
    'key13321': 'value76714',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Alexis Randall',
    'address': '861 Bradshaw Locks Apt. 946\nHaydenland, UT 40564',
    'text': 'During white conference scientist establish tonight oil clear. Still or while.\nGun radio place any turn. Cut Republican ground even. Stage spring nothing wish leave.',
    'email': 'davidhunt@example.org',
    'phone_number': '306-801-0451x6433',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Humphrey',
    'William Ross',
    'Jeremy Cooper',
    'Chad Rodriguez',
    'Andrew Watson',
    'Joseph Sutton',
    'Adam Dominguez',
    'William Hernandez',
    'Danielle Garcia',
    'Ricky Prince',
],
    'json': {
    'name': 'Amanda Townsend',
    'address': '210 Collier Pass\nEast Benjaminstad, NE 56192',
},
    'key78491': 'value15862',
    'key18880': 'value13179',
    'key80794': 'value9124',
    'key44476': 'value8980',
    'key95820': 'value36701',
    'key96303': 'value75697',
    'key30510': 'value87431',
    'key90477': 'value52247',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Donna Wells',
    'address': 'Unit 3340 Box 5667\nDPO AA 96545',
    'text': 'Memory relate store draw last suggest. Gas table what list.\nIdentify pull event billion may. Piece figure better information. Travel student bed news would scientist.',
    'email': 'pollardkristy@example.com',
    'phone_number': '(902)422-2338x1334',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Davidson',
    'Maria Oconnor',
    'Victoria Reid',
    'Zachary Hanson Jr.',
    'Jorge Dorsey',
],
    'json': {
    'name': 'Zachary Rivas',
    'address': '590 Hernandez Trafficway Suite 323\nNorth Amanda, ND 30227',
},
    'key36504': 'value419',
    'key35458': 'value76744',
    'key40206': 'value38076',
    'key53392': 'value1199',
    'key81280': 'value86011',
    'key43730': 'value55379',
    'key52444': 'value67532',
    'key45466': 'value14026',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Patrick Harvey',
    'address': '27039 Sherman Park Apt. 490\nEast Danielmouth, IA 98958',
    'text': 'Fact growth knowledge major again example training. Consider dream control face. Hotel wait bag perhaps enough general.\nOf clear employee say plant base recognize. Teacher day feel.',
    'email': 'tyronejordan@example.org',
    'phone_number': '+1-289-397-3997',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mallory Nelson',
    'Gabrielle Porter',
    'Adrian Thompson',
],
    'json': {
    'name': 'Kevin Collins',
    'address': '2822 Franklin Stream Suite 444\nNew William, WY 01577',
},
    'key77111': 'value24250',
    'key76167': 'value36001',
    'key11680': 'value30595',
    'key68165': 'value47504',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Kevin Gonzales',
    'address': '276 Anna Neck Apt. 394\nJosephport, NC 50428',
    'text': 'Loss sense in bank while. Until set analysis.\nRequire leave major better. Interest crime look anyone think dinner discuss.\nData prove never. Room picture animal admit test. Party hard these final by.',
    'email': 'mperkins@example.org',
    'phone_number': '+1-904-264-3185x9855',
    'array_int_dynamic': [
    30598,
],
    'array_varchar_dynamic': [
    'Latoya Rodriguez',
    'Michelle Gallegos',
    'Sherri Moss',
],
    'json': {
    'name': 'Lisa Ortiz',
    'address': '466 Stokes Fork Apt. 522\nWest Timothybury, VA 97078',
},
    'key37435': 'value35160',
    'key4639': 'value68808',
    'key37323': 'value228',
    'key8979': 'value1857',
    'key35269': 'value98412',
    'key99573': 'value14137',
    'key41219': 'value3009',
    'key99440': 'value88983',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Frederick Payne',
    'address': '44110 Harrison Port\nBaldwinborough, OK 53177',
    'text': 'Onto show trial morning reality. Open network indicate see room. Put officer really southern.\nPrevent bar yard accept.',
    'email': 'laurenhodge@example.net',
    'phone_number': '(205)759-4814',
    'array_int_dynamic': [
    58504,
],
    'array_varchar_dynamic': [
    'Mrs. Sabrina Velez DDS',
    'Pamela Mckinney',
    'George Saunders',
    'John Gray',
    'Jennifer Nguyen',
    'Donald Barrett',
],
    'json': {
    'name': 'Julie Jackson',
    'address': '11880 Miles Shoal Suite 432\nLake Timothy, SC 77216',
},
    'key9338': 'value39317',
    'key25661': 'value43743',
    'key16187': 'value27087',
    'key19728': 'value56983',
    'key65778': 'value64535',
    'key97880': 'value84004',
    'key89266': 'value11899',
    'key93953': 'value62715',
    'key43105': 'value7255',
    'key41580': 'value21641',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Ashley Pacheco',
    'address': '55713 Flores Tunnel Suite 611\nFrankside, DE 47073',
    'text': 'Rest authority environment. Natural lose on spring.\nStudy such doctor. Against theory strategy size four soon. Natural town if billion arm.',
    'email': 'tinagonzales@example.net',
    'phone_number': '928.873.0398x764',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Tracey Wilson',
    'Robert Bautista',
    'Kristin Rogers',
    'John Barnes',
    'Kimberly Patton',
    'Matthew Rollins',
    'Kim Richmond',
    'Jennifer Freeman',
    'Pamela Gonzalez',
],
    'json': {
    'name': 'Candice Schultz',
    'address': '233 Williams Corners Apt. 649\nHortonborough, MT 31189',
},
    'key14446': 'value38415',
    'key70304': 'value18870',
    'key93965': 'value48148',
    'key86924': 'value86417',
    'key50749': 'value36226',
    'key11707': 'value21996',
    'key40267': 'value91121',
    'key83534': 'value14865',
    'key82008': 'value3195',
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
    'RequestId': '893c41dd-62ef-11f0-9b4b-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_17_761748DeZRSyjc',
    'dimension': 128,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-1]_1752744139.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId12810011752744139Json()
    test.run_tests()
