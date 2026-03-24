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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752744859_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752744859.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid100AndUid1001752744859Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752744859.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752744859.json"
        self.test_count = 4  # 测试方法数量
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
    'RequestId': '3004dfa5-62f1-11f0-9a87-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_07_075029jckqIvMd',
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
    'RequestId': '3322e0f0-62f1-11f0-8bcb-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_07_075029jckqIvMd',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Charlotte Baker',
    'address': '106 Adrian Cape\nLake Patriciachester, AK 15905',
    'text': 'Interview energy sense.\nAvailable husband effect thank more small. Think far message in perhaps.\nCover law share say political push. Enough industry foot rule early name simple. Leg night year from.',
    'email': 'raguilar@example.com',
    'phone_number': '8196864050',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Calderon',
],
    'json': {
    'name': 'Clifford Perez',
    'address': '6621 Craig Tunnel Suite 679\nJordanville, RI 63464',
},
    'key60080': 'value77406',
    'key5617': 'value12165',
    'key19127': 'value51304',
    'key67022': 'value61334',
    'key48281': 'value9920',
    'key52224': 'value33138',
    'key57616': 'value88796',
    'key28373': 'value7370',
    'key67991': 'value87546',
    'key24587': 'value67600',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Dr. Stephanie Ferguson',
    'address': '2043 Michael Mill Suite 026\nOsbornview, PR 83022',
    'text': 'Less oil along guess rate direction ability conference. Safe policy paper property employee item boy community.',
    'email': 'kbradford@example.org',
    'phone_number': '460.225.6992x999',
    'array_int_dynamic': [
    47007,
],
    'array_varchar_dynamic': [
    'Carlos Petersen',
    'Caitlin Griffin',
    'Eric Schwartz',
],
    'json': {
    'name': 'Marcus Reyes',
    'address': 'USCGC Jacobs\nFPO AP 33829',
},
    'key2699': 'value97467',
    'key83763': 'value78978',
    'key51738': 'value37288',
    'key92410': 'value31989',
    'key158': 'value62079',
    'key97329': 'value25067',
    'key84523': 'value13582',
    'key50123': 'value84681',
    'key41824': 'value12974',
    'key69671': 'value75582',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Matthew Goodman',
    'address': '14526 Mays Orchard\nPort Kimberlyburgh, AL 14833',
    'text': 'Against their response TV remember always billion. Recently capital eight effect project the.\nTen glass back scene decision thus to. Response coach almost successful interest.',
    'email': 'dale12@example.com',
    'phone_number': '6165832961',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Alvarado',
    'Derek Case',
    'Tyrone Braun',
    'James Taylor',
    'Matthew Bryant',
    'Anna Chapman PhD',
    'William Williams',
],
    'json': {
    'name': 'Laura Webb',
    'address': '371 Bennett Station\nNew Kimberlyfurt, WV 68538',
},
    'key30462': 'value66892',
    'key9229': 'value81937',
    'key31496': 'value74496',
    'key39182': 'value30979',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jennifer Lang',
    'address': '57735 Kenneth Plaza Suite 272\nJohnsonstad, AL 16680',
    'text': 'Prevent them strategy interview so maybe she. Effort laugh just agreement entire think. Although item also according become short his.\nHave information any. Space rise run. Weight someone product.',
    'email': 'bradshawluke@example.com',
    'phone_number': '482.379.2822',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Cathy Pearson',
    'Angela Gamble',
    'Eric Thomas',
],
    'json': {
    'name': 'Jennifer Sanchez',
    'address': 'USNV Freeman\nFPO AA 43227',
},
    'key89428': 'value20405',
    'key56982': 'value71451',
    'key17327': 'value27289',
    'key31537': 'value47493',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Hector Bishop',
    'address': '472 Aaron Spurs\nGarciamouth, RI 11534',
    'text': 'There actually team huge us game throw. Action space general technology. Traditional music teach role really best realize.\nWith management if during bit year.',
    'email': 'jordanbrendan@example.com',
    'phone_number': '(464)275-1268x15799',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Randy Fuller',
    'Ronald Sanders',
    'Darryl Edwards',
    'Melissa Myers',
    'Gregory Webster',
    'Dana Salas',
    'Richard Guerra',
    'Charles Miller MD',
    'Carly Lucero',
],
    'json': {
    'name': 'Vanessa Schmidt',
    'address': 'PSC 0514, Box 5802\nAPO AA 60092',
},
    'key23330': 'value45752',
    'key8976': 'value81584',
    'key62104': 'value36767',
    'key29525': 'value71452',
    'key55561': 'value36540',
    'key81471': 'value36986',
    'key20939': 'value83764',
    'key30762': 'value55166',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Joshua Williams',
    'address': '1443 Gentry Grove\nSouth Lisaton, NC 33423',
    'text': 'Boy huge after rate style. Rock either radio the. Figure team story make hit concern debate. Official various later.',
    'email': 'rwatson@example.net',
    'phone_number': '001-463-661-2615',
    'array_int_dynamic': [
    7583,
],
    'array_varchar_dynamic': [
    'Melinda Price',
    'Shelley Barry',
    'Elizabeth Moreno',
    'David Anderson',
    'Rebecca Mullins',
    'Julie Branch',
],
    'json': {
    'name': 'Aaron Johnson',
    'address': '58343 Justin Roads\nPort Joannetown, FL 99590',
},
    'key90129': 'value14391',
    'key2859': 'value2450',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Abigail Clark',
    'address': '2044 Thomas Stravenue Apt. 750\nJohnnyside, MA 78704',
    'text': 'Would interest only fine collection one they. Say policy fly address just.\nEverybody type region page north town house. Our month whatever eight economy detail.',
    'email': 'douglas24@example.net',
    'phone_number': '7005551181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Lopez',
    'Juan Preston',
    'Tammy Mckee',
    'Tonya Brown',
    'Michelle Kline',
    'Brian Knight',
    'Christopher Brown',
    'John Sandoval',
],
    'json': {
    'name': 'Christopher Massey',
    'address': '7170 Barber Square Suite 599\nCharlottetown, WY 73817',
},
    'key72086': 'value39108',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jade Dean MD',
    'address': 'Unit 1309 Box 9407\nDPO AP 33188',
    'text': 'Happy brother yard dog movie.\nFuture but wall.\nSea forward later own trade add simple. Great positive two foot institution certainly member.',
    'email': 'kristinhull@example.net',
    'phone_number': '786-744-3983',
    'array_int_dynamic': [
    66257,
],
    'array_varchar_dynamic': [
    'Michael Payne',
    'Tammy Carroll',
    'Christian Jordan',
    'Jamie Brown',
    'Tammy Newman',
    'Adrian Huang',
    'Timothy Harrison',
    'Michael Carrillo MD',
    'Michael Miller',
],
    'json': {
    'name': 'Vincent Martinez',
    'address': '20463 Maria Drive\nLake Coryport, RI 81203',
},
    'key40590': 'value68861',
    'key49308': 'value72040',
    'key89582': 'value48029',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Rachel Mitchell',
    'address': '41530 Scott Well\nAndrewmouth, NE 05102',
    'text': 'Direction science approach certain care. Tv center million significant avoid. Behavior if style word some machine easy.',
    'email': 'smithanthony@example.com',
    'phone_number': '(888)997-4219',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Terri Montoya',
    'Jason Mora',
    'Melissa Davis',
],
    'json': {
    'name': 'Nathan Williams',
    'address': 'USNS Watkins\nFPO AA 84515',
},
    'key85987': 'value11368',
    'key44447': 'value64727',
    'key52267': 'value25575',
    'key44114': 'value5732',
    'key68079': 'value98037',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Jamie Roy',
    'address': '09104 Laura Terrace\nMitchellstad, ND 71475',
    'text': 'Practice quality good lead current nature.\nEntire you machine. So either style area blue law deep.\nHour my cultural skill current foot car. Today easy bag daughter involve agency degree.',
    'email': 'eingram@example.net',
    'phone_number': '(554)655-8654',
    'array_int_dynamic': [
    3835,
],
    'array_varchar_dynamic': [
    'Eugene Bridges',
    'Victoria Cameron',
    'Mary Wood',
    'Bradley Lucas',
    'Amanda Murphy',
    'Edward Dalton',
    'Karen King',
    'Pamela Young',
    'Katie Potter',
],
    'json': {
    'name': 'Sharon Mccullough',
    'address': '33683 Parsons Ford Suite 988\nJohnathanhaven, NC 32397',
},
    'key50477': 'value10975',
    'key114': 'value48041',
    'key14468': 'value60713',
    'key47997': 'value96601',
    'key61225': 'value42899',
    'key1341': 'value40153',
    'key1156': 'value76826',
    'key90045': 'value7779',
    'key35790': 'value36669',
    'key89071': 'value33610',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Dennis Harrell',
    'address': '99723 Miller Forges Suite 338\nToddburgh, AR 63284',
    'text': 'Available low win. Since act thousand know. Approach how sister method ready show magazine if.',
    'email': 'john08@example.net',
    'phone_number': '001-983-887-6995x56329',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Rojas',
],
    'json': {
    'name': 'Danielle Williams',
    'address': '259 Martin Pike Suite 719\nPort Tamara, NC 23227',
},
    'key72162': 'value73851',
    'key8748': 'value84499',
    'key3643': 'value33117',
    'key13548': 'value12948',
    'key7554': 'value27144',
    'key99312': 'value73866',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Evan Oneill',
    'address': 'PSC 5012, Box 0292\nAPO AP 31082',
    'text': 'My loss hour when later north himself. Political loss process us better.\nListen during trial writer prove. Within like tax allow food.',
    'email': 'tiffanygardner@example.net',
    'phone_number': '871-659-9957x711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Horton',
    'Kristen Rodriguez',
    'Anthony Giles',
    'Belinda Stanley',
    'George Lopez',
    'Mrs. Kimberly Best',
    'Larry Taylor',
],
    'json': {
    'name': 'Kevin Velazquez',
    'address': '61810 Douglas Place\nPort Christine, PR 06338',
},
    'key54536': 'value70049',
    'key1299': 'value74112',
    'key57688': 'value39007',
    'key39513': 'value59843',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Whitney Medina',
    'address': '3074 Randy Walk\nNew Amanda, AK 17287',
    'text': 'Series law plan usually break idea. Week mention this feel reason miss. Authority so brother finish.\nSame pull film many reveal against morning. Occur sure official stuff.',
    'email': 'jared01@example.org',
    'phone_number': '(321)961-0190x098',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Sims',
    'Nancy Beasley',
    'Kristin Torres',
    'Jessica Hernandez',
    'Amy Odonnell',
    'Jonathan Kaiser',
    'Charles Jenkins',
    'Benjamin Robinson',
],
    'json': {
    'name': 'Andrew Harris',
    'address': '2094 Helen Park Suite 202\nDonaldmouth, SC 13448',
},
    'key24000': 'value42561',
    'key59918': 'value42537',
    'key66404': 'value22965',
    'key58351': 'value77008',
    'key65172': 'value53117',
    'key83906': 'value86829',
    'key59456': 'value94776',
    'key66725': 'value71208',
    'key42097': 'value43710',
    'key94004': 'value31316',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Sharon Jackson',
    'address': '6299 Taylor Green Apt. 911\nNorth Andreatown, PA 33003',
    'text': 'Least finish adult trial set. Power budget agency. Imagine per north factor human.\nRoom whom low feel. Whether agreement also have truth future from.',
    'email': 'egilmore@example.net',
    'phone_number': '736-342-2430',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Caitlyn Smith',
    'Nicholas Ellis',
    'Melissa Hobbs',
    'Jonathan Kim',
    'Dr. Philip Smith',
    'Lisa Foster',
],
    'json': {
    'name': 'Cheryl Osborne',
    'address': '5239 David Creek\nAndrewburgh, CT 09601',
},
    'key57597': 'value56286',
    'key29858': 'value79900',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Stacey Craig',
    'address': '424 Charles Ports Suite 428\nNew Laurastad, UT 43735',
    'text': 'Others hope road really compare capital. Dark soon treatment executive it. South single reason statement case. There doctor security have sing.',
    'email': 'valenciasarah@example.org',
    'phone_number': '+1-711-817-6612x02141',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Luis Jackson',
    'Isabel Ortega',
    'Virginia Hall',
    'Rita Franklin',
    'William Vazquez',
    'James Knight',
    'Mr. Justin Morgan MD',
    'Margaret Owen',
    'Christine Johnson',
],
    'json': {
    'name': 'Vanessa Evans',
    'address': '5476 Justin Stream\nSouth Leroyville, AL 06270',
},
    'key76792': 'value14784',
    'key4350': 'value33012',
    'key19929': 'value86123',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Alexander Williams',
    'address': '456 Kelly Ramp Apt. 555\nAudreystad, HI 35795',
    'text': 'Throw air hit media. Lead fund writer style. Memory else none Democrat role.\nClearly long source wrong. Everything kitchen lose image business during.',
    'email': 'xrobbins@example.com',
    'phone_number': '+1-933-827-4889x64249',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tamara Solis',
    'Miranda Villarreal',
    'Kristen Russell',
    'Jill Smith',
],
    'json': {
    'name': 'Jessica Hernandez',
    'address': '098 Mcdaniel Radial\nJeremybury, UT 37199',
},
    'key3851': 'value76098',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Tyler Collins',
    'address': '64842 Kelly Manor Suite 189\nPort Laura, AK 22543',
    'text': 'Newspaper whether mother cold cultural just particularly its. Message government oil under society teacher expert lose. Arm community keep nation check.',
    'email': 'twebb@example.com',
    'phone_number': '+1-497-631-8874x890',
    'array_int_dynamic': [
    62781,
],
    'array_varchar_dynamic': [
    'Kelly Johnson',
    'Sean Taylor',
    'John Richardson',
    'Heather Anderson',
    'Sandra Faulkner',
],
    'json': {
    'name': 'Dylan Atkins',
    'address': '055 Valerie Knolls\nHarrismouth, CA 19675',
},
    'key78282': 'value98382',
    'key63970': 'value77812',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Brandon Barnes',
    'address': '1143 Jesse Avenue\nMichaelville, LA 56786',
    'text': 'Candidate nice parent product than town. Yard develop because not. Character a room east family. Baby early member condition enjoy language rate.',
    'email': 'kimberly38@example.net',
    'phone_number': '308-256-9668x83198',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Henry',
    'Mackenzie Singleton',
],
    'json': {
    'name': 'Sandra West',
    'address': '368 Williams Roads Suite 837\nJaredmouth, FL 74155',
},
    'key90033': 'value81952',
    'key79820': 'value25727',
    'key32384': 'value72286',
    'key38598': 'value55585',
    'key26788': 'value22959',
    'key23631': 'value18983',
    'key1254': 'value63257',
    'key88381': 'value29629',
    'key77957': 'value61875',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Nicole Lopez',
    'address': '9519 Courtney Parkway Suite 184\nLake Angela, OK 76356',
    'text': 'Vote story official professional true a garden. Dog democratic standard become. Goal really matter seat six. Father toward hear.\nChild senior first theory water. Population thank second become.',
    'email': 'chasesmith@example.com',
    'phone_number': '550-685-2173x8406',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Adam Parker',
    'Benjamin Walker',
    'Christopher Price',
    'Kathy Smith',
    'Kevin Fox',
],
    'json': {
    'name': 'Laura Williams',
    'address': '88437 Austin Loaf\nPort Caitlin, AS 81015',
},
    'key78708': 'value36201',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Anne Brown',
    'address': '8776 Scott Field Suite 451\nSanchezview, NM 42724',
    'text': 'Itself politics specific enjoy. Than value focus south lead rate poor. With floor their inside success especially tree.\nData look piece give. Sell step step whole.',
    'email': 'jesse78@example.net',
    'phone_number': '+1-457-413-5464',
    'array_int_dynamic': [
    10365,
],
    'array_varchar_dynamic': [
    'Mitchell Hopkins',
    'Lauren Robinson',
    'Margaret Steele',
    'Jill Jones',
    'Laura Whitney',
    'Ms. Lauren Hernandez',
    'Paige Parks',
    'William Brooks',
    'Janet Ramos',
    'Chad Taylor',
],
    'json': {
    'name': 'Nicholas Potter',
    'address': '82224 James Camp\nNew Scottburgh, GA 78357',
},
    'key44534': 'value28088',
    'key46470': 'value63395',
    'key29750': 'value755',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Alexa Christian',
    'address': '53174 Burton Field Apt. 842\nEast Pamelamouth, OH 75376',
    'text': 'Despite week common spend nothing father six. Ground should century. Will surface save president from message need.',
    'email': 'millershelly@example.org',
    'phone_number': '557-226-2043x704',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mark Hoffman',
    'Donald Martinez',
],
    'json': {
    'name': 'Courtney Hall',
    'address': '72009 Judith Burgs Apt. 600\nPamelabury, WV 93321',
},
    'key562': 'value10186',
    'key51958': 'value90019',
    'key92111': 'value41755',
    'key8881': 'value82098',
    'key54725': 'value54106',
    'key42775': 'value96032',
    'key36849': 'value10959',
    'key14567': 'value63321',
    'key67256': 'value88526',
    'key99575': 'value74784',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Elizabeth Blanchard',
    'address': '762 Phillips Wall Suite 614\nLake Robert, WY 07562',
    'text': 'They chance write fear. Price section mention.\nLive half message family with. Thus rather order arm bed example during from. Pretty send establish score answer.',
    'email': 'elizabethjones@example.org',
    'phone_number': '342.560.7945x2560',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Dylan Tran',
    'Alicia James',
    'Robert Wilkinson',
    'Yolanda Dougherty',
],
    'json': {
    'name': 'Brian Foster',
    'address': '6393 Henry Shore\nMccallfurt, LA 41863',
},
    'key14387': 'value49065',
    'key52235': 'value75306',
    'key16201': 'value59132',
    'key45659': 'value13195',
    'key50429': 'value45979',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Paul Diaz',
    'address': '14641 Donna Points Suite 349\nLake Robertstad, UT 34949',
    'text': 'Arm have young. Collection know view test point sell.\nStreet person significant western who. Easy all no culture power peace.\nCivil meet relate weight.',
    'email': 'krystalfrey@example.org',
    'phone_number': '(653)641-0860',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dana Parks',
    'Barbara Welch',
    'Margaret Oconnor',
    'Jennifer Thompson',
    'Karen Lucas',
    'Danielle Lewis',
    'Megan Clark',
    'Christina Hughes',
    'Brenda King',
],
    'json': {
    'name': 'Robert Little',
    'address': '2640 Jonathon Falls\nAvilastad, WY 20313',
},
    'key11660': 'value52892',
    'key18462': 'value78766',
    'key42763': 'value84702',
    'key93717': 'value77187',
    'key64464': 'value69299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Alexandra Shaw',
    'address': '4357 Contreras Avenue\nAlexanderton, OH 59603',
    'text': 'Apply risk small sit today choice. Improve child whom today. Official example blue civil will story. Field hold agency billion what few.\nConsider brother draw girl account record.',
    'email': 'deborahkirby@example.org',
    'phone_number': '(282)814-6729x80330',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Tran',
    'Christina Pena',
    'Jeffrey Black',
    'Sheila Case',
    'Ashley Harrison',
    'Isabella Cruz',
    'Travis Stephenson',
    'Cindy Anderson',
],
    'json': {
    'name': 'Nicholas Mann',
    'address': '4243 Joseph Landing\nWest Matthew, TX 48459',
},
    'key95199': 'value56052',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Joshua Stanley',
    'address': '3402 Kellie Plains Suite 427\nSouth David, NJ 07185',
    'text': 'Together but nation recent appear sign eye fight. Even head race radio where goal. Method hold organization machine. Provide positive from.',
    'email': 'robert69@example.com',
    'phone_number': '+1-827-727-7585x58276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Jennifer Miller',
    'Evan Harris',
],
    'json': {
    'name': 'William Harris',
    'address': '18429 Wagner Motorway Apt. 703\nPort Bryanport, SD 10691',
},
    'key63522': 'value9278',
    'key93923': 'value86547',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Andrew George',
    'address': 'Unit 7637 Box 9278\nDPO AA 64343',
    'text': 'Answer stuff magazine everybody.\nTogether bad leave difficult deal sister. Baby some ever how.\nEmployee type hit perform one music. Him prove particularly yourself spend force.',
    'email': 'johnhoward@example.com',
    'phone_number': '575.321.7780',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Russell',
    'Nicholas Snyder',
],
    'json': {
    'name': 'Janet Yates',
    'address': 'Unit 2251 Box 9124\nDPO AP 19957',
},
    'key78306': 'value24445',
    'key29336': 'value4344',
    'key45482': 'value6627',
    'key7666': 'value18781',
    'key59465': 'value15109',
    'key11599': 'value10808',
    'key17031': 'value76428',
    'key52540': 'value52348',
    'key31206': 'value61270',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Andrew Ross',
    'address': '9160 Chandler Wells Apt. 532\nSouth Lisa, RI 00984',
    'text': 'Even four safe value take until. Attention response present fly hold. Rich our leg.',
    'email': 'annchaney@example.net',
    'phone_number': '+1-578-649-9153x9802',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jenna Johnson',
    'Joshua White',
    'Daniel Bryan',
    'Scott Rios',
    'Jesus Hernandez',
    'Kimberly Anderson',
    'Daniel Parsons',
    'Justin Thomas',
    'Jeffrey Phillips',
    'Chelsea Mckenzie',
],
    'json': {
    'name': 'Andrew Cox',
    'address': '889 Dunlap Ville Apt. 710\nDennisfort, WY 77278',
},
    'key56009': 'value44383',
    'key94068': 'value60938',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Vincent Morris',
    'address': '108 Meyer Mission Apt. 095\nJordanville, WY 56498',
    'text': 'Style course explain exist girl. Mouth position though thought. Close hospital two class her.\nExample determine relationship majority apply. Spring star value bill among experience.',
    'email': 'timothyjohnson@example.com',
    'phone_number': '980-963-4096x31788',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Armstrong',
    'Gabrielle Mitchell',
    'Ryan Blair',
],
    'json': {
    'name': 'Doris Howard',
    'address': '249 Harmon Route\nSchultzstad, OK 51255',
},
    'key91127': 'value49283',
    'key54947': 'value37271',
    'key98704': 'value57603',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Scott Chang',
    'address': '883 Brown Lodge Suite 993\nChristopherberg, LA 51443',
    'text': 'Son action security decision note.\nCrime perform kid any. Commercial amount tax. Increase history stay take city fine. Argue plan as man.',
    'email': 'alyssa02@example.net',
    'phone_number': '890-960-3236x416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gail Palmer',
    'James David',
    'Russell Choi',
    'Michael Erickson',
    'Timothy Perry',
],
    'json': {
    'name': 'John Jones',
    'address': '8811 Kevin Path\nWest Amandatown, DE 87415',
},
    'key53695': 'value25757',
    'key72061': 'value7533',
    'key68688': 'value64340',
    'key78569': 'value5020',
    'key60527': 'value5573',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Stephen Johnson',
    'address': '01881 Katie Freeway\nMarkborough, PR 04119',
    'text': 'Really husband there less hit day look. Let moment anyone would do difference either stay. Bank organization letter well measure training number. Five action model system kitchen open energy head.',
    'email': 'lopezlinda@example.org',
    'phone_number': '(520)868-6275x3564',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Chad Turner',
    'Jonathan Hayes',
    'Kaitlyn Flynn',
    'Daniel Hughes',
    'Alexandra Hoffman',
    'Kevin Jackson',
    'Mark Blake',
    'Ryan Nelson',
    'Kendra Brown',
    'Matthew Bennett',
],
    'json': {
    'name': 'Joseph Keith',
    'address': '387 Brandon Well Apt. 047\nMillerstad, NJ 07169',
},
    'key60861': 'value31582',
    'key19535': 'value24225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Zachary Floyd',
    'address': '076 Glover Highway Suite 603\nWest Michael, WI 23322',
    'text': 'Technology professor require ball. The Mr city course ever. Trip son leave raise particularly herself option girl.\nLay draw walk discover. Cold there today on issue.',
    'email': 'melindathomas@example.com',
    'phone_number': '001-253-552-6402x959',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Connor Barton',
    'Nicole Campbell',
    'Philip Robles',
],
    'json': {
    'name': 'Amy Acevedo MD',
    'address': '053 Mcguire Mountain Apt. 962\nTranstad, IL 71067',
},
    'key7854': 'value79814',
    'key24174': 'value33115',
    'key34648': 'value47597',
    'key20292': 'value50025',
    'key45893': 'value8225',
    'key47489': 'value87075',
    'key10872': 'value23490',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Tony Pace',
    'address': '336 Crystal Square Apt. 505\nBrianland, KS 39604',
    'text': 'While hit region say left. About public general least these certain. Well board say discover.',
    'email': 'kristen42@example.net',
    'phone_number': '819.897.2917',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joyce Barr',
    'Joshua Preston',
    'Rachel Robinson',
    'Mr. Matthew Williams Jr.',
    'Jeffrey Buck',
    'Timothy Humphrey',
],
    'json': {
    'name': 'Monique Hart',
    'address': '1949 Payne Plains\nLaneview, LA 82173',
},
    'key99985': 'value41500',
    'key19937': 'value34123',
    'key6940': 'value10717',
    'key8110': 'value46535',
    'key90378': 'value84699',
    'key15639': 'value31191',
    'key2256': 'value38799',
    'key53276': 'value88445',
    'key67321': 'value86140',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Jennifer Shaw',
    'address': '8036 Meadows Walk Apt. 889\nMatthewville, NY 10344',
    'text': 'Certainly left camera act green. Protect score true smile firm test hot analysis.\nGas operation million street crime into. Several statement enter benefit.',
    'email': 'hhall@example.com',
    'phone_number': '5675439640',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brenda Larson',
    'Aaron Murray',
],
    'json': {
    'name': 'Jimmy Martinez',
    'address': '78158 Edwards Ridge Suite 369\nWest Kurtfurt, MP 31013',
},
    'key89980': 'value93452',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Craig Brown',
    'address': '21284 Christopher Trail\nPort Megan, FL 82416',
    'text': 'Should hair enough sign evening. Foreign major method statement cultural political table.\nFour quite author. Bag small important process individual world. Always among adult show participant.',
    'email': 'ghanson@example.com',
    'phone_number': '(906)373-4416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Russell Ortiz',
    'Patricia Young',
    'David Wagner',
    'Caitlin Paul',
    'Bryce Moore',
    'James Gutierrez',
    'Kathleen Woodard',
],
    'json': {
    'name': 'Jodi Stephens',
    'address': '0254 Davis Landing\nGomezberg, TX 24234',
},
    'key95145': 'value41899',
    'key85311': 'value57',
    'key50889': 'value9265',
    'key98047': 'value74343',
    'key42543': 'value280',
    'key25836': 'value24947',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Elizabeth Myers',
    'address': '60258 Kelly Ridges\nEast Christianfurt, MA 96717',
    'text': 'Interview white recent environment girl know. Whom effort choose case suddenly standard quickly.\nWhole next news. Most rich past else.',
    'email': 'cmartin@example.com',
    'phone_number': '+1-901-924-8688x52971',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Patty Johnson',
    'Lisa Silva',
    'Ashley Sullivan',
    'Jonathan Murray',
],
    'json': {
    'name': 'Kyle Wood',
    'address': '631 Stone Mission\nNorth Ryan, IA 76704',
},
    'key55599': 'value83807',
    'key98354': 'value95776',
    'key70029': 'value8479',
    'key20958': 'value86523',
    'key89994': 'value68127',
    'key25333': 'value83359',
    'key39436': 'value37988',
    'key52518': 'value73094',
    'key75976': 'value92813',
    'key58972': 'value38613',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'William Huang',
    'address': '5043 Good Cape Suite 008\nSouth Juanfort, PR 54600',
    'text': 'Including buy on within guy decision. Suffer pressure evening then activity these.',
    'email': 'shelbydiaz@example.net',
    'phone_number': '361-529-4086x3952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Whitney Simpson',
    'Jamie Sullivan',
    'James Morrison',
    'David Haney',
    'Jacob Ramirez',
    'Dennis Smith',
    'Jacqueline Martinez',
    'Thomas Wright',
    'Paul Randolph',
    'Melissa Henderson',
],
    'json': {
    'name': 'Mark Costa',
    'address': '26157 Nathan Circle\nCruzmouth, TX 38598',
},
    'key71418': 'value32071',
    'key67057': 'value78758',
    'key35721': 'value37467',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Mary Barnett',
    'address': '10965 Leonard Skyway\nSouth Antonio, DC 42609',
    'text': 'However ever along size. Herself forget statement center dog defense respond. Recognize red by whom time front side. Him try just spring.\nShoulder ago boy little.',
    'email': 'shieldsleslie@example.com',
    'phone_number': '635-335-8500',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Richard Warner',
],
    'json': {
    'name': 'Sean Jones',
    'address': '84862 William Trail Suite 981\nLaurenland, VT 52106',
},
    'key53': 'value99426',
    'key49435': 'value27559',
    'key97341': 'value47753',
    'key30410': 'value63042',
    'key29942': 'value95464',
    'key42540': 'value38068',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Thomas Goodman',
    'address': '948 Nicholas Station\nSouth Scott, UT 66694',
    'text': 'Economy chance into write collection stuff hundred hundred. Total good page cover.\nTree place foreign act. Recent court against meeting seem reveal soldier know. Management another reflect sing.',
    'email': 'joshuaclark@example.com',
    'phone_number': '(463)763-4368',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Willis',
    'Natasha Reese',
    'Erin Mckinney',
    'Roger Higgins',
    'Keith Hamilton',
    'Monica Turner',
],
    'json': {
    'name': 'Lisa Rice',
    'address': '144 Maldonado Trail\nOneillberg, MH 61761',
},
    'key37382': 'value55762',
    'key58184': 'value89049',
    'key98273': 'value31061',
    'key62867': 'value87162',
    'key55755': 'value16770',
    'key92896': 'value24752',
    'key11523': 'value65792',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Heather Hodge',
    'address': '700 Melissa Throughway Apt. 596\nLake Christinestad, MP 71982',
    'text': 'However listen purpose recognize happen. Weight her air prove head teacher your story. Would Democrat suggest.\nLaugh mouth collection employee force. Say out drug my open thousand give paper.',
    'email': 'denisewilson@example.com',
    'phone_number': '644-550-1413x3211',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Stewart',
    'Amber Adams',
    'Amy George',
],
    'json': {
    'name': 'Samuel Sullivan',
    'address': 'Unit 0581 Box 8427\nDPO AA 89098',
},
    'key85186': 'value1981',
    'key84688': 'value21913',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Grace Patel',
    'address': '7445 Alexander Bridge Suite 268\nCookborough, OR 33466',
    'text': 'Its subject focus activity wrong effort. Condition toward heart individual baby.\nTreat if expect number hot. Leader protect itself list. By show fish political believe. Decide out paper.',
    'email': 'riveramichelle@example.com',
    'phone_number': '876.964.2726x885',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Holmes',
    'Roberto Morgan',
    'Suzanne Brown',
    'Jonathan Martin',
    'Betty Martinez',
    'Deborah Maddox',
    'Mr. Mark Gilbert',
],
    'json': {
    'name': 'Kevin Maldonado',
    'address': '0747 Hunter Lake Apt. 602\nPort Richard, MT 41970',
},
    'key97928': 'value32205',
    'key39448': 'value94805',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'James Pham',
    'address': '278 Angelica View Apt. 607\nBrandiland, MT 75227',
    'text': 'Politics get region weight time. Catch cold option stage skin build TV.',
    'email': 'wilsonomar@example.com',
    'phone_number': '(206)783-3198x995',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Allen',
    'Erin Hayes',
    'Stacy Lopez',
    'Robert Calderon',
    'Chad Gamble',
    'Jesus Smith',
    'Lauren Robinson',
    'Donna Hunt',
    'David Lawrence',
    'Victoria Rodriguez',
],
    'json': {
    'name': 'Stephanie Brown',
    'address': '42323 Brown Ridge Apt. 751\nNorth Katie, AR 66022',
},
    'key93589': 'value17584',
    'key53107': 'value72437',
    'key49222': 'value25452',
    'key15522': 'value21939',
    'key93727': 'value62470',
    'key83693': 'value38420',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Daniel Trujillo',
    'address': '45813 Angela Point Suite 010\nNicoleside, DC 44501',
    'text': 'Head you with for Congress prevent. East also sound lawyer various modern.\nWide event think language oil fast administration. School pretty assume fund. Former live operation for know a group.',
    'email': 'jacksonroger@example.net',
    'phone_number': '+1-975-437-2381',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Bradley Day',
    'Cory Moyer',
    'Scott Washington',
    'Joshua Brown',
    'Karen Barnes',
],
    'json': {
    'name': 'Joseph Patton',
    'address': '1298 Wanda Plaza Apt. 632\nAnthonybury, WI 09602',
},
    'key84625': 'value1077',
    'key50703': 'value48008',
    'key69168': 'value17884',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Zachary Davis',
    'address': '35338 Lisa Mountain Suite 382\nNorth Christina, HI 16324',
    'text': 'Serve impact last. Our result religious turn.\nPattern wind respond reality with. Top campaign argue expert magazine. Arrive card civil middle.',
    'email': 'urusso@example.com',
    'phone_number': '818-828-8893',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jon Little',
    'Howard Washington',
],
    'json': {
    'name': 'Mike Hunt',
    'address': '7885 David Cape Suite 449\nHalltown, VI 18606',
},
    'key81188': 'value61471',
    'key40526': 'value73228',
    'key35900': 'value77302',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Tonya Macdonald',
    'address': '40671 Lopez Street\nSouth Michaelfort, ID 41189',
    'text': 'Plan but theory experience. Fast girl from make support. Face such detail before teacher. Fear apply worry option.\nEvening production yeah become. Often financial finally.',
    'email': 'charlesjackson@example.net',
    'phone_number': '965-483-3576x7170',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Reid',
    'Susan Evans',
    'Nicholas Klein',
    'Angela Smith',
    'Joseph Martinez',
    'Sandra Gonzales',
    'William Cruz',
],
    'json': {
    'name': 'Elizabeth Jordan',
    'address': '63708 Vazquez Unions Apt. 171\nSouth Christina, OR 65886',
},
    'key25907': 'value21123',
    'key40437': 'value46028',
    'key66482': 'value70789',
    'key84513': 'value31818',
    'key78129': 'value27090',
    'key47854': 'value54173',
    'key58459': 'value82530',
    'key47158': 'value56861',
    'key66844': 'value88343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Nicholas Anderson',
    'address': '5007 Brent Gardens Apt. 184\nMillermouth, AS 44571',
    'text': 'Drug a news effect. Sport college kitchen with strong.\nBudget develop heavy figure best thus. Body ten central.\nGreat adult agent. Environment or school.',
    'email': 'christinacummings@example.net',
    'phone_number': '+1-907-352-1689',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robin Cortez',
    'Kevin Jones',
    'John Evans',
],
    'json': {
    'name': 'Joseph Graves',
    'address': '90806 Becky Tunnel Suite 615\nSouth Tammy, LA 67353',
},
    'key46914': 'value40799',
    'key14482': 'value29067',
    'key71825': 'value17806',
    'key95269': 'value89549',
    'key78868': 'value58047',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Douglas Aguilar',
    'address': '752 Blackwell Causeway\nAmandashire, ME 25628',
    'text': 'Necessary perhaps left company may option.\nExecutive could population everybody Mr.\nKitchen accept husband fall including for. Focus front break join other. Happen ten pattern military large town.',
    'email': 'alicia07@example.com',
    'phone_number': '690-878-8226',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Silva',
    'Danielle Kaiser',
    'Stephen Perez',
    'Melissa Alvarado',
],
    'json': {
    'name': 'Mary Short',
    'address': '8854 Stanley Field\nMurphyton, PA 94829',
},
    'key59076': 'value43960',
    'key91399': 'value24885',
    'key39446': 'value5651',
    'key46427': 'value56469',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Denise Lewis',
    'address': '35605 Charles Creek Suite 040\nGarciaberg, DC 76781',
    'text': 'Girl security material mean. Public research condition water. Option among sell eye get.\nPublic quickly against imagine. Certainly thank six Democrat then fight perform.',
    'email': 'rebeccahughes@example.org',
    'phone_number': '(373)862-3685x107',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Regina Fuller',
    'Jacob Hill',
    'Glenda Gallagher',
    'Jonathan Powell',
    'Kathy Wilson',
    'Julie Campbell',
],
    'json': {
    'name': 'Joseph Hayes',
    'address': '04663 Felicia Junctions Suite 974\nMarciamouth, NE 60267',
},
    'key61415': 'value44450',
    'key79963': 'value12271',
    'key46785': 'value64287',
    'key52503': 'value99402',
    'key15884': 'value8728',
    'key18086': 'value59497',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Ryan Ramsey',
    'address': '563 Lee Falls\nSouth Erika, NH 05475',
    'text': 'Answer still case owner scientist message growth. Environmental study anything sound along. Hand prepare population.',
    'email': 'john93@example.org',
    'phone_number': '566-754-3302',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Pena',
    'Mario Lambert',
    'Crystal Rodriguez',
    'Brittney Kim',
    'Ashley Smith',
    'Ms. Sophia Wilson PhD',
],
    'json': {
    'name': 'Jesse Lewis',
    'address': '9979 Anderson Manors Suite 458\nParksborough, MH 79347',
},
    'key81487': 'value1505',
    'key61354': 'value63927',
    'key27887': 'value28574',
    'key15617': 'value26541',
    'key81080': 'value10589',
    'key34308': 'value77279',
    'key16172': 'value31481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Alexandra Mayer',
    'address': '899 James Path Suite 211\nRichardsonview, FL 92965',
    'text': 'Interesting front specific. According thought possible southern. Who range yeah billion visit.\nRich these church many suggest all indicate prove.',
    'email': 'patriciaevans@example.org',
    'phone_number': '(962)900-2638x369',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Pugh',
    'Daniel Dawson',
],
    'json': {
    'name': 'Isaac Berger',
    'address': 'Unit 1252 Box 2579\nDPO AA 97344',
},
    'key21017': 'value84440',
    'key74261': 'value26630',
    'key56154': 'value33253',
    'key27567': 'value59016',
    'key93707': 'value23048',
    'key85715': 'value45769',
    'key13036': 'value51181',
    'key70567': 'value91981',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'April Manning',
    'address': '2104 Nicholas Ranch Apt. 216\nAllisonfort, NJ 31718',
    'text': 'Court daughter hour determine entire notice since. Result build issue process also simple. Already forward require last half key.',
    'email': 'davidbenitez@example.org',
    'phone_number': '711-555-4583',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Davis',
    'Brent Rodriguez',
    'Cynthia Espinoza',
    'Frank Gutierrez',
    'Michael Evans',
    'Joshua Jones',
    'Cassandra Barnes',
    'Timothy Townsend',
    'Amy Barry',
],
    'json': {
    'name': 'Andrew Randall',
    'address': '954 Collins Ports\nWest Tiffany, AL 92682',
},
    'key4857': 'value65312',
    'key48534': 'value60548',
    'key10985': 'value63607',
    'key38967': 'value96478',
    'key13671': 'value30466',
    'key1542': 'value6631',
    'key90695': 'value33290',
    'key61303': 'value79880',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Austin Mcneil',
    'address': '48320 Ramos Pass\nJosephton, VI 46579',
    'text': 'Attention black bring to. Beat customer expect growth argue him after. Sort employee prepare.\nMoment seem can sister nor staff top. Year action service billion help gas area.',
    'email': 'hmartin@example.com',
    'phone_number': '001-754-771-1545x58648',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Sparks',
    'Christopher Miller',
    'Travis Wells',
    'Karina Holloway',
],
    'json': {
    'name': 'Samuel Pennington',
    'address': '73130 James Ford Apt. 419\nSouth Sean, NY 18234',
},
    'key2809': 'value42709',
    'key13167': 'value33377',
    'key18597': 'value18535',
    'key49607': 'value27285',
    'key92126': 'value32354',
    'key36146': 'value66052',
    'key43882': 'value48212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kevin Pham',
    'address': '489 Morris Mount Suite 131\nBarberside, TX 45815',
    'text': 'Man country after yes push. Relate have fall. Seven true question culture traditional condition improve.',
    'email': 'erika99@example.org',
    'phone_number': '+1-654-621-7173x8242',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Vazquez',
],
    'json': {
    'name': 'Ariana Smith',
    'address': '063 Kathleen Bypass Suite 966\nRodriguezhaven, GA 42266',
},
    'key31313': 'value322',
    'key69007': 'value54637',
    'key51314': 'value82904',
    'key72863': 'value21501',
    'key30872': 'value37193',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Carol Shaffer',
    'address': '13761 Leslie Mill Apt. 368\nWhiteside, GU 74050',
    'text': 'Save movie century simply entire window. Do method voice another.\nOur treat last power off light decision. When election give direction. Network goal word oil include later place.',
    'email': 'floresjanet@example.com',
    'phone_number': '812-854-1947x321',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Baldwin',
],
    'json': {
    'name': 'Dana Erickson',
    'address': '689 Parks Lodge\nEast Jeffreyville, NC 22146',
},
    'key89765': 'value40351',
    'key97196': 'value32339',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Kaylee Lane',
    'address': '2207 Jones Stream Apt. 756\nSouth Susan, IN 71148',
    'text': 'Street measure seven anything.\nBox financial moment grow new. Without source product organization believe still.',
    'email': 'bethany75@example.net',
    'phone_number': '2745153734',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carmen Smith',
    'Joseph Adams',
    'Ross Hubbard',
    'Gail Glover',
    'Natalie Baker',
],
    'json': {
    'name': 'Mrs. Brittany Booker',
    'address': '1801 Mckinney Camp Suite 627\nNew Kevinfort, NJ 37004',
},
    'key4529': 'value10375',
    'key6426': 'value72447',
    'key58730': 'value90670',
    'key67759': 'value26439',
    'key30881': 'value12497',
    'key69811': 'value66805',
    'key87622': 'value15819',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Danielle Mcdonald',
    'address': '7264 Paul Mountain Apt. 020\nCindyshire, OR 95019',
    'text': 'Weight operation end time eat they nothing. Move research probably industry because rule tax.\nHe head rest visit miss majority show. Floor responsibility he health fear.',
    'email': 'brenda73@example.org',
    'phone_number': '001-727-569-6167',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Smith',
    'Heather Welch',
    'Marcus Garcia',
    'Alan Macias',
    'Matthew Solomon',
    'Valerie Trevino',
    'Patricia Summers',
    'Jonathan Hughes',
],
    'json': {
    'name': 'Rachel Rios',
    'address': '662 Tanner Oval\nLake Arthurmouth, PA 52441',
},
    'key23815': 'value10749',
    'key96209': 'value59118',
    'key35538': 'value28098',
    'key8546': 'value88078',
    'key40767': 'value55494',
    'key16875': 'value29054',
    'key87954': 'value38079',
    'key31801': 'value7680',
    'key47296': 'value54134',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Colin Mccarty',
    'address': '32754 Mason Ranch\nAnnebury, WI 30616',
    'text': 'Official quality country floor too. Similar blue push yet save. Bed argue several six force.',
    'email': 'kellyjimenez@example.com',
    'phone_number': '(715)705-1562x47004',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Goodwin',
    'Michele Hobbs',
],
    'json': {
    'name': 'William Myers',
    'address': '4422 Chapman Lights Suite 265\nHinesview, NV 13922',
},
    'key52986': 'value37308',
    'key32102': 'value78232',
    'key58578': 'value62027',
    'key21559': 'value89436',
    'key13486': 'value34040',
    'key93310': 'value59961',
    'key96238': 'value75267',
    'key46276': 'value36865',
    'key54923': 'value88057',
    'key63373': 'value94040',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Emily Stone',
    'address': '701 Brown Rue Apt. 529\nEast Christinafurt, NC 69265',
    'text': 'Hundred him hold inside car best area animal. Us person pull within half plan. How wish tree degree country station.',
    'email': 'brittanyorozco@example.com',
    'phone_number': '840-968-5578x27665',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amber Jordan',
    'Daniel James',
    'Samantha Rose',
    'Cassandra Lutz',
    'Thomas Medina',
],
    'json': {
    'name': 'Katherine Myers',
    'address': '5053 Fowler Forks\nAndreatown, MN 94607',
},
    'key40570': 'value2077',
    'key86178': 'value16165',
    'key4865': 'value31767',
    'key6708': 'value75021',
    'key34284': 'value89959',
    'key14287': 'value25451',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Robert Townsend',
    'address': '53710 Hoover Walk Apt. 914\nThomastown, CA 74984',
    'text': 'Strategy politics few financial. Pm follow another newspaper store.\nWait school plan office.',
    'email': 'xsanchez@example.net',
    'phone_number': '001-889-714-5031x3551',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rebekah Avery',
    'Carla Zavala',
    'Raymond Espinoza',
    'Victoria Long',
    'Joseph Hall',
    'Mary Gray',
    'Paul Roberts',
    'Jared Lyons',
],
    'json': {
    'name': 'Christopher Sandoval',
    'address': '672 Ochoa Overpass\nRamosland, GU 60909',
},
    'key39228': 'value46388',
    'key36909': 'value16772',
    'key44800': 'value48921',
    'key79499': 'value18654',
    'key98025': 'value86282',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Amber Guerrero',
    'address': '75507 Emily Ford\nSouth Rebecca, GU 15944',
    'text': 'Per player win prove year peace. Without ever type professional hope shoulder. Member billion much life.',
    'email': 'steve97@example.com',
    'phone_number': '7403182185',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Olivia Palmer',
    'Margaret Lowe',
    'Patrick Vargas',
    'Charles Gilbert MD',
    'Melody Clay',
    'Amy Simmons',
    'Tyrone Hampton',
],
    'json': {
    'name': 'Christopher Bennett',
    'address': '484 Moore Shore Apt. 579\nRhodesburgh, PA 03408',
},
    'key7965': 'value19761',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'David Kerr',
    'address': '60159 Timothy Place Apt. 961\nLevinemouth, HI 10492',
    'text': 'Authority who thank sport development worker. As hear decision wear clear hard newspaper. Career play food owner long picture his.',
    'email': 'rossjennifer@example.org',
    'phone_number': '212-850-7282x5752',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kristin Trevino',
    'James Jacobs',
    'Deborah English',
],
    'json': {
    'name': 'Kimberly Grant',
    'address': '9795 Tracy Flats Suite 328\nPort Angela, CA 65544',
},
    'key47': 'value42630',
    'key637': 'value69031',
    'key48005': 'value93480',
    'key82629': 'value43742',
    'key16393': 'value21068',
    'key72937': 'value88404',
    'key62261': 'value14157',
    'key74220': 'value17690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Devin Evans',
    'address': '2997 Jennifer Roads\nLeeport, UT 45356',
    'text': 'Despite campaign seat. Own push physical relate two. Crime oil feel blood road foreign authority. Involve final and look million.',
    'email': 'ubrady@example.com',
    'phone_number': '+1-890-910-3745x3122',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Maureen Harvey',
    'Nicholas Pruitt',
    'Alexandra Miller',
    'Sean Craig',
    'Heather Moyer',
    'Michael Gutierrez',
    'Jacob Hayes',
],
    'json': {
    'name': 'Rachel Young',
    'address': '5333 Tina Port Suite 729\nPort Sarah, SC 26925',
},
    'key44707': 'value59658',
    'key33027': 'value45265',
    'key97594': 'value78624',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Mitchell Campbell',
    'address': '56477 Kathy Islands\nWilsonburgh, MA 11796',
    'text': 'Race when security soon. Want system management answer someone require.',
    'email': 'hdickson@example.org',
    'phone_number': '001-798-288-8264x463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Curtis Macias',
    'Christopher Smith',
    'Amanda Rivera',
    'Wendy Baxter',
    'Nancy White',
    'Steven Arnold',
],
    'json': {
    'name': 'Anthony Lane',
    'address': '14211 Vanessa Plain Suite 955\nBryantchester, IL 90861',
},
    'key68300': 'value26710',
    'key54415': 'value8109',
    'key4552': 'value10429',
    'key5552': 'value54191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Kelly Rios',
    'address': 'USNS White\nFPO AE 66670',
    'text': 'Institution most cold great. Success dinner south program politics service. Individual forget could go task serve tree.\nClaim region no describe word. See have I reduce.',
    'email': 'cookwilliam@example.com',
    'phone_number': '381.993.3647x0932',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Moore',
    'Joshua King',
    'Wendy Miller',
],
    'json': {
    'name': 'Lucas Carpenter',
    'address': '21743 Riley Points Suite 716\nCurtisborough, WI 94345',
},
    'key62273': 'value91567',
    'key59926': 'value43867',
    'key25996': 'value47645',
    'key59936': 'value63597',
    'key67824': 'value2230',
    'key91265': 'value56069',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Terri Guzman',
    'address': 'PSC 5125, Box 6812\nAPO AP 71632',
    'text': 'South level president popular. Management fish magazine.\nLong stop three game born level these. Peace difficult personal money. Child join artist.\nThemselves marriage history speak magazine.',
    'email': 'phaley@example.com',
    'phone_number': '(744)893-0080x073',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Luke Rodriguez',
    'Jose Sullivan',
    'Toni Gomez',
    'Anthony Stevenson',
    'Allison Thomas',
    'Marco Schroeder',
    'Kimberly Johnson',
    'Todd Chavez',
],
    'json': {
    'name': 'Mary Lopez',
    'address': '698 Hood Stream Suite 564\nThomasfurt, NM 45143',
},
    'key20754': 'value19076',
    'key44040': 'value15213',
    'key11636': 'value12204',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Alison Wang',
    'address': '58659 Gonzales Brook\nPort Nicolefurt, ME 61074',
    'text': 'Race deep hit usually soon.\nLife daughter allow note everyone. It left age always.\nGuess region have book.',
    'email': 'rschwartz@example.org',
    'phone_number': '5897643566',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Kline',
    'Patricia Martinez',
],
    'json': {
    'name': 'Teresa Branch',
    'address': '915 Barker Rapids Suite 210\nSalinasfort, KY 48445',
},
    'key26608': 'value99723',
    'key85070': 'value75217',
    'key57737': 'value13167',
    'key23564': 'value616',
    'key1056': 'value49292',
    'key68123': 'value3145',
    'key86247': 'value48439',
    'key70209': 'value11800',
    'key20723': 'value12915',
    'key35205': 'value40038',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jordan Shaw',
    'address': '21512 Bautista Cliff\nNorth Timothytown, AS 15457',
    'text': 'All expert day something paper raise three. Mean hear finally make minute town. Pay mouth benefit true serious my word. Everybody wide such return in dark.',
    'email': 'gerald34@example.com',
    'phone_number': '+1-736-676-6574x676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Joseph',
],
    'json': {
    'name': 'William Avery',
    'address': '409 Marco Square Apt. 754\nWhitneyfurt, NJ 17328',
},
    'key81510': 'value16482',
    'key87563': 'value23864',
    'key12238': 'value59363',
    'key18559': 'value7607',
    'key76763': 'value80643',
    'key73490': 'value41528',
    'key35926': 'value48404',
    'key37366': 'value28641',
    'key94751': 'value18621',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Emily Martin',
    'address': 'PSC 0226, Box 8328\nAPO AP 18064',
    'text': 'Event remember western what alone increase including.\nControl it along address officer a foot. Condition degree hope cold general interview else.\nRisk finish before affect high.',
    'email': 'linpaige@example.org',
    'phone_number': '(371)578-4984',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Harper',
],
    'json': {
    'name': 'Juan Walker',
    'address': '973 Chad Locks Apt. 391\nLake Traciland, CA 65116',
},
    'key86386': 'value24933',
    'key69450': 'value94047',
    'key60154': 'value15068',
    'key3877': 'value32680',
    'key80790': 'value65436',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Kevin Anderson',
    'address': '723 Ray Point\nPerrystad, OH 37763',
    'text': 'Bed training include day style face. Pick information also teach.\nAdd sometimes less. Choice candidate street become find move. Sport garden road third and manage Mrs.',
    'email': 'zbell@example.com',
    'phone_number': '204.362.6925x7896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tara Travis',
    'Richard Hall',
    'David Davis',
    'Kimberly Lloyd',
    'Jason Lowe',
    'Anthony Smith',
    'Nancy Monroe',
    'Erika Sutton',
],
    'json': {
    'name': 'Sean Roth',
    'address': '307 Schaefer Glens Apt. 090\nBobbyside, MP 01025',
},
    'key71443': 'value32461',
    'key80401': 'value92296',
    'key27773': 'value59082',
    'key67583': 'value45255',
    'key77870': 'value19781',
    'key5837': 'value68724',
    'key69376': 'value77165',
    'key89594': 'value27069',
    'key96576': 'value83580',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Douglas Ray',
    'address': '3275 Richard Junctions\nPeterside, KY 12590',
    'text': 'Father us citizen name check able material. Whom author debate blue.\nNatural case could now president community himself. Knowledge record behavior most.',
    'email': 'lpugh@example.com',
    'phone_number': '001-569-673-0361',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Breanna Cordova',
    'Michelle Aguilar',
    'Samantha Schneider',
    'Diana Davis',
    'Mario Castro',
    'Carl Kelley',
],
    'json': {
    'name': 'Julie Dunn',
    'address': '03331 Fischer Branch\nWest Michaelchester, PA 50229',
},
    'key73432': 'value48588',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Lisa Bennett',
    'address': '5275 Soto Mountain Apt. 203\nEast Christopher, PA 35822',
    'text': 'Role various business decade commercial hear glass. Door son toward high program federal answer. Speak song something plan relate between water.',
    'email': 'qroy@example.org',
    'phone_number': '372.949.9376x9943',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Roy Sexton',
    'Betty Olson',
    'Jorge Robbins',
],
    'json': {
    'name': 'Maria Evans',
    'address': '5286 Harris Ranch\nJamesfort, FL 06957',
},
    'key56107': 'value79416',
    'key98512': 'value93702',
    'key34725': 'value69765',
    'key97972': 'value97917',
    'key80150': 'value44760',
    'key69842': 'value17589',
    'key46430': 'value54022',
    'key56893': 'value57999',
    'key32923': 'value78436',
    'key1867': 'value96629',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Shirley Diaz',
    'address': '898 Michael Village Apt. 754\nJohnsonburgh, NE 77199',
    'text': 'Company drug although statement. Voice save risk reality mission time. Respond week seem hour meet billion. Rate picture actually position choose.',
    'email': 'tluna@example.org',
    'phone_number': '449.508.8896x09266',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David Nguyen',
    'Kathryn Bruce',
    'Cheryl Wilson',
    'Hailey Riggs',
    'Lynn Walton',
    'Jeremy Grant',
],
    'json': {
    'name': 'Brandon Lowery',
    'address': '096 Kelly Rapids Suite 703\nLake Colleen, VA 48523',
},
    'key33514': 'value15927',
    'key76405': 'value58630',
    'key80016': 'value31061',
    'key16232': 'value33241',
    'key12205': 'value75656',
    'key37008': 'value18264',
    'key95396': 'value19912',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Randy Jackson',
    'address': '765 Laura Landing\nNorth Sherribury, MT 12491',
    'text': 'Finish so past police member dark support. Work tax process impact Congress ground. Hit real operation me support. Local sport computer.',
    'email': 'usandoval@example.com',
    'phone_number': '641-281-2502x27255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Emily Ross',
    'Katelyn Estrada',
],
    'json': {
    'name': 'Derrick Jones',
    'address': 'USNS Norman\nFPO AP 15089',
},
    'key11351': 'value37875',
    'key99870': 'value47390',
    'key82659': 'value833',
    'key7494': 'value50148',
    'key44923': 'value82143',
    'key88023': 'value26510',
    'key89349': 'value86487',
    'key43691': 'value44135',
    'key33952': 'value16993',
    'key94670': 'value95273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Lindsay Taylor',
    'address': '989 Debbie Terrace\nWest Michealfurt, NJ 52401',
    'text': 'North when difficult very. Clearly thought value change.\nInto oil investment friend partner speak. Every beat recently think step.',
    'email': 'sreynolds@example.com',
    'phone_number': '+1-297-694-9036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Miller',
],
    'json': {
    'name': 'Cindy Blair',
    'address': '82685 William Forest\nMichaeltown, UT 00628',
},
    'key22755': 'value69154',
    'key15807': 'value30210',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Veronica Sanchez',
    'address': '0914 Angel Fall Suite 247\nWest Debrashire, OK 26788',
    'text': 'Only make argue. Management message at white forget.\nMajority rise one record part. Fear pick plan east control forward culture. Month rather professional produce economic hotel.',
    'email': 'smithderrick@example.org',
    'phone_number': '549-531-2569x6606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Mccormick',
    'Mandy Kelly',
    'Kelly Oliver',
    'Kristi Rose',
    'Robert Cook',
],
    'json': {
    'name': 'Eric Bradley',
    'address': '882 Jenna Meadows Suite 656\nSouth Daniel, TN 30628',
},
    'key47543': 'value39684',
    'key97510': 'value18266',
    'key31016': 'value16695',
    'key93151': 'value35677',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Amy David',
    'address': 'USS Sanders\nFPO AE 84512',
    'text': 'Early sound never thank different hospital in. Fund young person look.\nAge hit oil medical community. Second camera young goal though rest pick.',
    'email': 'tarafowler@example.com',
    'phone_number': '(996)480-1303x492',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Perez',
    'Kelly Ponce',
],
    'json': {
    'name': 'Linda Nelson',
    'address': 'Unit 9215 Box 2744\nDPO AP 35776',
},
    'key1633': 'value38595',
    'key84323': 'value61733',
    'key64099': 'value27194',
    'key98339': 'value61399',
    'key60768': 'value77641',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'John Scott',
    'address': '02343 Samantha Courts\nGregoryville, IN 23415',
    'text': 'Much learn truth. Manager activity federal. Better behind grow participant owner local charge.\nCitizen magazine language fight everyone. Blood mean daughter million.',
    'email': 'swinters@example.com',
    'phone_number': '622.579.3803x9516',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Hailey Martinez',
    'Ms. Sabrina Roman',
    'Nicole Park',
    'Chelsea Shaw',
    'Joseph Davidson',
    'John Davis',
    'Felicia Ross',
    'Amy Wolf',
    'Brooke Gibbs',
    'Denise Allen',
],
    'json': {
    'name': 'Laura Baker',
    'address': 'PSC 3130, Box 9428\nAPO AE 95226',
},
    'key79538': 'value78777',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Maria Brown',
    'address': '67839 Susan Tunnel\nSampsonland, CA 05339',
    'text': 'Deep increase important long least several hundred. Actually campaign such letter. Himself court piece for national.\nMaintain challenge crime today late back.',
    'email': 'flemingrhonda@example.com',
    'phone_number': '001-273-438-0551x699',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Cole',
],
    'json': {
    'name': 'Michael Parker',
    'address': '34615 Keith Center\nShelbychester, NM 49808',
},
    'key13697': 'value72375',
    'key96562': 'value32606',
    'key1196': 'value30365',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'James Navarro',
    'address': '2876 Choi Road Apt. 939\nPort Codyport, AZ 27910',
    'text': 'Lay special north wide investment. Yeah prepare back sense different religious market.\nNor nothing item way whether draw early. Despite something indicate stand.',
    'email': 'martinalan@example.net',
    'phone_number': '4222965397',
    'array_int_dynamic': [
    23633,
],
    'array_varchar_dynamic': [
    'Teresa Mcdaniel',
],
    'json': {
    'name': 'Robert Hamilton',
    'address': '566 Reid Shores\nGarciachester, SC 49541',
},
    'key58784': 'value8060',
    'key91793': 'value1292',
    'key23401': 'value15175',
    'key78118': 'value42213',
    'key83893': 'value68299',
    'key26265': 'value72452',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Samuel Sanchez',
    'address': '8698 Williams Mill\nWest Alexshire, MD 29240',
    'text': 'Project tree include individual item what year. College billion practice possible page. Health ability group.',
    'email': 'zle@example.com',
    'phone_number': '6807911780',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michele Davis',
    'Jessica Caldwell',
],
    'json': {
    'name': 'Tina Phillips',
    'address': '613 Diaz Dam Apt. 880\nEast Keithfurt, CT 30578',
},
    'key11690': 'value99661',
    'key73125': 'value42135',
    'key71775': 'value31062',
    'key76522': 'value39430',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Kimberly Young',
    'address': '92740 Garrett Run Apt. 912\nWest Victor, WV 51575',
    'text': 'War your strategy firm people available. Involve war number must. Test as high run almost identify. Brother movie either simply special.',
    'email': 'shannon68@example.net',
    'phone_number': '474-677-2554x3394',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Hamilton',
    'Patrick Ross',
    'Susan Myers',
    'James Harris',
],
    'json': {
    'name': 'Joshua Wells',
    'address': '0196 Roberts Fields\nSouth Brittany, FL 02426',
},
    'key26666': 'value88048',
    'key87090': 'value42314',
    'key13802': 'value58928',
    'key60062': 'value66255',
    'key37022': 'value61870',
    'key31056': 'value34778',
    'key83913': 'value17318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Timothy Black',
    'address': '028 James Courts\nPort David, WI 53950',
    'text': 'Research floor base. Wide floor free community great dream performance.\nGood magazine happen try poor. Beyond no may event develop will above.',
    'email': 'patricia29@example.com',
    'phone_number': '+1-764-275-7912x036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Lynch',
    'Anna Sullivan',
    'Thomas Pratt',
    'Sarah Brown',
    'Terry Winters',
],
    'json': {
    'name': 'Dale Gilbert',
    'address': '432 Rodney Mountains\nNorth Derekville, FM 53771',
},
    'key84426': 'value38151',
    'key10369': 'value65534',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Jonathan Bradley',
    'address': '03094 Allison Fort Suite 300\nStephaniebury, FM 31554',
    'text': 'Shoulder benefit not institution.\nResponsibility public even month benefit worry. Face within business within mission story defense. Follow agreement event listen form kitchen.',
    'email': 'emily63@example.com',
    'phone_number': '001-280-960-2593',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Roberson',
    'Jeremy Rogers',
    'Christopher Lowe',
    'Tracy West',
    'Rita Sellers',
    'Rachel Hodge',
],
    'json': {
    'name': 'Nicholas Simmons',
    'address': '48003 Thomas Land\nNathanielchester, DE 85069',
},
    'key46399': 'value44491',
    'key71962': 'value80782',
    'key30891': 'value53539',
    'key44716': 'value45380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Michael Haynes',
    'address': '24425 William Extensions Suite 887\nSouth William, PA 52032',
    'text': 'Society training form teach perform base through position. Hospital north fact author know hotel meet. Hair turn hotel drug watch charge. Single big contain.',
    'email': 'gabrielwashington@example.net',
    'phone_number': '969-206-5350x3175',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kerry Gonzales',
    'Jill Morrison',
    'Donna Hampton',
    'Heidi Edwards MD',
],
    'json': {
    'name': 'Martha Hamilton',
    'address': '6718 Alison Stravenue Suite 112\nSouth Jasonchester, LA 58218',
},
    'key63541': 'value40664',
    'key92224': 'value93100',
    'key57951': 'value98929',
    'key77447': 'value32663',
    'key76892': 'value44986',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Michelle Wood',
    'address': '2953 Miller Drive\nTylershire, GU 85435',
    'text': 'These white strategy set oil campaign. Item man dog country ever technology forward high. More state instead democratic.\nShoulder article education bag. Change policy experience.',
    'email': 'eddieherman@example.com',
    'phone_number': '874.478.8553x585',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Carl Carey',
    'Kenneth Fitzgerald',
    'Miss Stacie Wang',
    'Tammy Myers',
    'Raymond West',
],
    'json': {
    'name': 'Charles Gomez',
    'address': '004 William Square Suite 265\nOwenhaven, AS 85055',
},
    'key51841': 'value94215',
    'key99438': 'value11563',
    'key68297': 'value32664',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jill Salazar',
    'address': '36783 Angela Squares\nGomezshire, PA 25657',
    'text': 'Foot including feeling modern. Political whatever tough without.\nSeason seek million report send. Full instead international month certain town. Majority another morning cause town.',
    'email': 'kennethwallace@example.com',
    'phone_number': '(276)318-1244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Shirley Torres',
    'Jeffrey Valenzuela',
],
    'json': {
    'name': 'Alexandra King',
    'address': '88359 Medina Hollow\nEast Cassandrafort, AR 49017',
},
    'key34183': 'value13994',
    'key90806': 'value59769',
    'key61977': 'value40975',
    'key4775': 'value6666',
    'key97936': 'value18536',
    'key66610': 'value86150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Taylor Johnson',
    'address': '04930 Patterson Center Apt. 947\nJeremiahtown, MP 07166',
    'text': 'Assume war glass voice talk cause. Wonder focus phone effort reflect while analysis song. Hit join contain leader play reduce factor.',
    'email': 'jamestammy@example.com',
    'phone_number': '(804)468-0189x856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cody Morrow',
],
    'json': {
    'name': 'Sarah Pearson',
    'address': '2304 Fields Shores Apt. 923\nNew Daniellestad, NE 72306',
},
    'key57451': 'value40889',
    'key84294': 'value40615',
    'key5341': 'value39885',
    'key84035': 'value95637',
    'key93917': 'value15548',
    'key71894': 'value18569',
    'key24780': 'value16266',
    'key36865': 'value33873',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Rebecca Collins',
    'address': 'Unit 6108 Box 0351\nDPO AE 07258',
    'text': 'Play continue account peace sure itself inside. Whatever debate already effort.\nDefense name final short world. Conference seat among near.\nWeight stuff wide.',
    'email': 'joshua49@example.org',
    'phone_number': '001-723-706-9866',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Emily Taylor',
    'Diana Taylor',
    'Kevin Spence',
    'Samantha Hammond',
    'James Elliott',
    'Janice Hill',
    'Mindy Hill',
    'David Perez',
],
    'json': {
    'name': 'Rachel Tucker MD',
    'address': '162 Le Knoll Suite 528\nNorth Ronaldfurt, AL 41658',
},
    'key23011': 'value25046',
    'key29523': 'value22097',
    'key96324': 'value16171',
    'key722': 'value41068',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Samantha Benton',
    'address': '571 Maria Manor\nCarrollmouth, ME 51424',
    'text': 'Paper better effect personal represent. Fill candidate throughout south long see play.',
    'email': 'debra75@example.net',
    'phone_number': '709-878-4317',
    'array_int_dynamic': [
    74004,
],
    'array_varchar_dynamic': [
    'Jennifer Watson',
    'Barbara Rivers',
    'Mallory Jones',
    'Laura Harris',
    'Jackson Andrews',
    'Joseph Holland',
    'Brianna Wilson',
],
    'json': {
    'name': 'Brittney Hardin',
    'address': '4386 Mendoza Row Suite 058\nNorth Christopher, ME 34039',
},
    'key4093': 'value36185',
    'key63607': 'value44262',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Eric Graham',
    'address': '8911 Lee Loaf\nHarrisberg, GU 68491',
    'text': 'Outside third seat like five figure. College no follow doctor person.',
    'email': 'jamesharris@example.org',
    'phone_number': '(997)731-3131',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Gabrielle Bradley',
    'Christina Martinez',
    'Cheryl Rodriguez',
    'Christopher Williams',
],
    'json': {
    'name': 'Donald Rose',
    'address': '7410 Potts Center Suite 348\nLake Kimberlymouth, NV 71493',
},
    'key4213': 'value49273',
    'key71107': 'value20299',
    'key4583': 'value94870',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Mr. James Marquez',
    'address': '621 Eric Valleys Apt. 239\nPort Richardmouth, VT 56577',
    'text': 'Protect anyone difficult city picture nearly near nothing. Tv say among design stage store.\nStill life shake medical bit line. Trouble join much want ground.',
    'email': 'owensaaron@example.com',
    'phone_number': '561.294.3033',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Yvonne Meyer',
    'Vincent Jenkins',
    'Linda Hess',
    'Christine Holder',
    'Stephanie Simpson',
    'Austin Burns',
    'Holly Velazquez',
    'Christopher Erickson',
    'Sarah Garrett',
    'Morgan Hill',
],
    'json': {
    'name': 'Allison Stanley',
    'address': '20024 Zachary Hollow Suite 309\nEast Douglas, GU 16299',
},
    'key43979': 'value67000',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Jessica Thompson',
    'address': '352 David Ville\nStephanieside, AL 90511',
    'text': 'Value vote second behavior whose official.\nIt edge dog. Financial every west. Paper nice push audience end clear.\nYour red military two. Author feeling several present experience born perhaps kind.',
    'email': 'deborahlopez@example.org',
    'phone_number': '8336538169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David Roberson',
    'Julian Rush',
    'Brandon Shaw',
    'Charles Gibson',
    'Sara Ramirez',
    'William Berger',
    'Dennis Perez',
    'Michelle Greene',
],
    'json': {
    'name': 'Keith Wilcox',
    'address': '989 Hernandez Ville Apt. 935\nMaryside, MP 51781',
},
    'key28931': 'value89804',
    'key949': 'value72558',
    'key40959': 'value58336',
    'key38837': 'value1653',
    'key14124': 'value49359',
    'key22237': 'value40224',
    'key85320': 'value46407',
    'key35342': 'value61156',
    'key30775': 'value46939',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Amanda Bailey MD',
    'address': '4815 Sheryl Junctions\nBushmouth, IL 42688',
    'text': 'Him majority occur. Century improve government relationship add building law per.\nChance president serve market artist sometimes. Lay enter read fall century sit woman.',
    'email': 'lisa51@example.net',
    'phone_number': '001-737-459-2551x67580',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Bell',
    'Victoria Martin',
    'Debra Avila',
    'James Gregory',
    'Michael Diaz',
    'Joann Dominguez',
    'Bryan Swanson',
],
    'json': {
    'name': 'Kayla Aguilar',
    'address': 'PSC 0538, Box 7541\nAPO AP 61059',
},
    'key82884': 'value25391',
    'key49397': 'value69573',
    'key96851': 'value83140',
    'key82490': 'value99978',
    'key69640': 'value48558',
    'key38392': 'value68399',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Angela Wright',
    'address': '4451 Grant Forest Apt. 381\nMataside, MH 29662',
    'text': 'Really run change building. Bag forward order force hard maybe you. Only attack nature bring challenge.',
    'email': 'marshjeffery@example.net',
    'phone_number': '+1-231-992-3742x00902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Meadows',
    'Lindsey Barnett',
],
    'json': {
    'name': 'Donna Duncan',
    'address': '24575 Vicki Mission\nLake Jeremy, NE 10051',
},
    'key70885': 'value88587',
    'key36798': 'value50704',
    'key77123': 'value61054',
    'key28233': 'value46229',
    'key21954': 'value16008',
    'key90768': 'value9748',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Sheila Johnson',
    'address': '1086 Chan Park Apt. 350\nPort Debbiefurt, NY 64600',
    'text': 'Figure part them by alone. Expect talk claim system commercial son huge. Feel light reality after.\nSimilar year decade investment article.',
    'email': 'muellershelley@example.net',
    'phone_number': '918.858.4812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Chang',
    'Olivia Warren',
    'Gloria Johnston',
    'Seth Mcclain PhD',
    'Steven Simmons',
    'Kimberly Ramos',
    'Willie Delgado',
    'Daniel Hubbard',
    'Melissa Jordan',
    'Thomas Bradley',
],
    'json': {
    'name': 'Desiree Butler',
    'address': '194 Lauren Lake\nKeithchester, CT 18923',
},
    'key55298': 'value38645',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Brittany Martin',
    'address': '23499 Dunn Brook\nSmithmouth, IN 63012',
    'text': 'End throw process process. Together part total my letter. Air loss agreement raise politics professor buy final.',
    'email': 'perezharry@example.org',
    'phone_number': '+1-963-228-0663',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Collins',
],
    'json': {
    'name': 'Samantha Klein',
    'address': '517 Mark Walk Suite 880\nPort Heather, OR 83442',
},
    'key82676': 'value79283',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Tammy Jacobs',
    'address': '949 Lyons Burgs\nRobertstad, ME 63847',
    'text': 'Way quickly walk history continue method. Boy couple shoulder what economic.\nDesign hope team part yeah green. Save foot money rich make ready. Know able study real though moment degree.',
    'email': 'wreed@example.net',
    'phone_number': '(743)775-0084',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Norman Adams',
],
    'json': {
    'name': 'Jennifer Gray',
    'address': '84135 Martinez Stravenue\nAndrewside, AR 08950',
},
    'key92813': 'value46553',
    'key14252': 'value9687',
    'key76851': 'value91786',
    'key26695': 'value25852',
    'key44914': 'value24905',
    'key59288': 'value39681',
    'key9285': 'value96248',
    'key27549': 'value15951',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Joseph Walker',
    'address': '971 Fitzgerald Station Apt. 891\nPort Andrewfort, NV 82857',
    'text': 'Standard stop audience thing perform. Enjoy foreign may. Several catch something movement hard.\nCourt head interesting fast can check someone. Modern able whom enjoy interesting subject.',
    'email': 'newmanangela@example.com',
    'phone_number': '(378)775-7476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Emily Bass',
    'Antonio Dorsey',
    'Darrell Johnson',
    'Cameron Mitchell',
    'Scott Mccormick',
    'Amy Shelton',
    'Allison Moore',
],
    'json': {
    'name': 'Amanda Jacobs',
    'address': '5241 Steven Street Suite 402\nVillegasland, AZ 76360',
},
    'key60224': 'value11369',
    'key18304': 'value74598',
    'key19788': 'value99957',
    'key24361': 'value78349',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Crystal Baker',
    'address': '8347 Benjamin Club\nPenaland, GU 68553',
    'text': 'Home social whom. There lawyer sure always radio budget become. Knowledge care discussion pick peace painting.\nAlways coach maintain develop.',
    'email': 'lindahill@example.net',
    'phone_number': '001-443-749-7193x3370',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Cox',
    'Cynthia Henry',
    'Katherine Cortez',
    'Jennifer Potts',
    'John Gilmore',
    'Andrew Page',
    'Kim Oconnor',
    'Stacy Fleming',
    'Carla Davis',
    'Larry Jensen',
],
    'json': {
    'name': 'Adriana Miller',
    'address': '449 George Ports Apt. 387\nEast Eric, IL 57420',
},
    'key15854': 'value51405',
    'key95196': 'value48661',
    'key75253': 'value16700',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Hannah Kaufman',
    'address': '01921 Daniels Union\nPort Tony, TN 41207',
    'text': 'Edge couple offer something kid interest. About decade eight memory get marriage.\nWin feeling beautiful. Peace floor way. Sense reach natural two first physical bad pass.',
    'email': 'gbarber@example.net',
    'phone_number': '+1-744-522-7954',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Carrie Carpenter',
    'Amy Rogers',
    'John Parker',
    'Danny Gonzalez',
    'William Bautista',
    'Andrew Carter',
    'Jennifer Ward',
    'Michael Castillo',
    'Jamie Jones',
],
    'json': {
    'name': 'Amanda Scott',
    'address': '77063 Jones Cove Apt. 539\nClarkhaven, NC 45977',
},
    'key41486': 'value35150',
    'key79664': 'value61766',
    'key65856': 'value4949',
    'key82848': 'value40434',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Eric Lewis',
    'address': '8402 Shawn Cove\nWest Nancyberg, KY 53451',
    'text': 'Fine energy total. Term enjoy table whole.\nFall answer politics she if road. Whose alone serve left note who itself.\nCommercial decade fill authority society shake Mrs. Agency identify free.',
    'email': 'lesliedavis@example.net',
    'phone_number': '+1-835-470-6765x489',
    'array_int_dynamic': [
    63107,
],
    'array_varchar_dynamic': [
    'Tyler Kim',
    'Rachel Jennings',
    'Anthony Nguyen',
    'Felicia Walker',
    'Brett Hood',
    'Jeffrey Perez',
    'Leslie Holmes',
],
    'json': {
    'name': 'Michael Cobb',
    'address': 'PSC 2595, Box 3745\nAPO AP 02062',
},
    'key6185': 'value95655',
    'key51644': 'value14741',
    'key42004': 'value16420',
    'key24568': 'value79597',
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
    'RequestId': '36bcd6bc-62f1-11f0-86f1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_07_075029jckqIvMd',
    'filter': 'uid > -100 and uid < 100',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'phone_number',
    'name',
    'email',
    'json',
    'uid',
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



    def test_request_3(self):
        """测试请求 3 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '3004dfa5-62f1-11f0-9a87-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_07_075029jckqIvMd',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > -100 and uid < 100]_1752744859.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid100AndUid1001752744859Json()
    test.run_tests()
