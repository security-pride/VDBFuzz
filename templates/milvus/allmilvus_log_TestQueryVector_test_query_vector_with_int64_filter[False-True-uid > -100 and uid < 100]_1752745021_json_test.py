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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752745021_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752745021.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid100AndUid1001752745021Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752745021.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752745021.json"
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
    'RequestId': '8fd4b990-62f1-11f0-9da4-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_47_820736sFyEdNtz',
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
    'RequestId': '92f7a235-62f1-11f0-9a16-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_47_820736sFyEdNtz',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Kenneth Jensen',
    'address': '8319 Cody Run\nMurphyhaven, IN 20018',
    'text': 'Clear air wonder executive commercial likely. Trade process production every.',
    'email': 'walkergary@example.net',
    'phone_number': '+1-772-580-7708x062',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Harris',
    'Miss Heather Calderon',
    'Christian Nguyen',
    'Sandra Huff',
],
    'json': {
    'name': 'Tyler Bush',
    'address': '813 Katherine Expressway\nLisaburgh, OK 71924',
},
    'key12090': 'value51908',
    'key77774': 'value89299',
    'key87937': 'value29520',
    'key43402': 'value2712',
    'key49595': 'value48340',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Tracy Lewis',
    'address': '54788 Dorsey Shore\nNorth Mallory, MN 18463',
    'text': 'Most born whom until learn. Wife deep stage room charge this. Than pick minute world administration though product.\nDecide take hand. Assume claim gun. Produce lay middle find which.',
    'email': 'angel20@example.net',
    'phone_number': '642.229.0329',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Bill Young',
],
    'json': {
    'name': 'Brandon Francis',
    'address': '05941 Mary Dam\nAnthonyfort, GU 73450',
},
    'key21351': 'value72194',
    'key73248': 'value25310',
    'key44372': 'value82433',
    'key40332': 'value99996',
    'key12732': 'value56348',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Renee Hudson',
    'address': '416 Regina Turnpike\nNorth Davidmouth, MS 63122',
    'text': 'Ever billion Congress tree range. Trial commercial same officer rest unit nor body.\nNothing dinner why power put wide college. Six owner entire raise book.',
    'email': 'mitchellmary@example.net',
    'phone_number': '388.694.2828x7766',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Hinton',
    'Johnny Simmons',
    'Derek Anderson',
    'Alexander Peters',
    'Diana Dorsey',
    'Phyllis Novak MD',
],
    'json': {
    'name': 'Laura Garcia',
    'address': '350 Tammie Circles Apt. 263\nPort Sueshire, AZ 29756',
},
    'key20154': 'value50139',
    'key6721': 'value39631',
    'key90460': 'value19753',
    'key68907': 'value41854',
    'key23564': 'value64492',
    'key99289': 'value55090',
    'key4301': 'value22078',
    'key87004': 'value78743',
    'key87293': 'value98084',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Brittany Morales',
    'address': 'USCGC Wolfe\nFPO AE 63367',
    'text': 'Fight fast himself ahead head board goal. Thought others idea possible sure wrong successful give.',
    'email': 'alexandergarcia@example.com',
    'phone_number': '701-443-0718x300',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Simmons',
    'Jessica Padilla',
    'Debra Lewis',
    'Cynthia Hall',
    'Tyler Colon',
    'Nicholas Gould',
    'Emily Orr',
    'Terry Walker',
    'Adrienne Johnson',
],
    'json': {
    'name': 'Katrina Rose',
    'address': '299 Bailey Loop\nPort Herbertport, KY 41067',
},
    'key626': 'value10588',
    'key56664': 'value24893',
    'key74071': 'value18498',
    'key18817': 'value39749',
    'key46213': 'value44416',
    'key60827': 'value76883',
    'key22203': 'value3543',
    'key70024': 'value42352',
    'key6245': 'value35387',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Emily Curry',
    'address': '8645 Kim Square Apt. 224\nGregoryburgh, ND 76615',
    'text': 'Office whatever as. Where dog effort contain. Responsibility task unit enough. Couple stand building include national music still lawyer.\nTravel figure start free very. Camera move exist bed.',
    'email': 'sarah27@example.org',
    'phone_number': '6888794698',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Cory Webb',
    'Ashley Long',
    'Amanda Watts',
    'Madison Bailey',
    'Calvin Jackson',
    'Mary Chavez',
    'Alejandro Rangel',
],
    'json': {
    'name': 'Katherine Green',
    'address': '22568 Thomas Spring\nLake Anthony, LA 33679',
},
    'key52967': 'value80180',
    'key99665': 'value33309',
    'key65557': 'value94817',
    'key82491': 'value5926',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Corey Holt',
    'address': '938 Hess Locks Suite 020\nSantiagobury, IN 71708',
    'text': 'Section environmental agreement lay. Say large effort politics particular. Design think product stock mouth. Trade strategy star behind how life nothing.',
    'email': 'gcruz@example.org',
    'phone_number': '001-846-876-7834x30210',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Clarke',
    'April Riley',
    'William Beasley',
    'Kelly Allen',
    'Oscar Reed',
    'Vicki Munoz',
    'Cheryl Stokes',
],
    'json': {
    'name': 'Margaret Parsons',
    'address': '401 Kevin Extensions\nWest Jakeberg, OK 74530',
},
    'key25673': 'value4152',
    'key14554': 'value55330',
    'key10950': 'value31600',
    'key69051': 'value16164',
    'key84403': 'value17445',
    'key90127': 'value17278',
    'key41718': 'value22323',
    'key16747': 'value78912',
    'key89271': 'value30780',
    'key78781': 'value3330',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Mr. Ryan Foley',
    'address': '0495 Fowler Cliff\nJoshuaville, LA 61064',
    'text': 'Show respond represent once. Onto open against possible.\nChallenge federal authority across. Interest might sport hotel arrive trouble collection.\nMethod leg floor partner.',
    'email': 'msmall@example.org',
    'phone_number': '399.668.1413',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jon Watkins',
    'Amanda Chapman',
    'Donna Kim',
    'Alexandra Wiggins',
    'Shawn Allen',
    'Christopher Dawson',
    'Sharon Bennett',
    'Jessica Santana',
    'Derek Rodriguez',
    'Taylor Santos',
],
    'json': {
    'name': 'Timothy Diaz',
    'address': '852 David Route\nWest Sarahshire, UT 18109',
},
    'key11268': 'value80303',
    'key90544': 'value70610',
    'key46571': 'value94351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Andrew Barnes',
    'address': '280 Robles Islands Suite 528\nMorenostad, NY 66082',
    'text': 'Bring toward successful woman project free. Pass game marriage him look. Surface sea gun open buy might.\nHour join pressure memory stock everybody.',
    'email': 'tnavarro@example.org',
    'phone_number': '9226808065',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Ballard',
    'Christine Lewis',
    'Benjamin Avila',
    'Austin Peterson',
    'Brian Ryan',
    'Christopher Alexander',
    'Heather Taylor',
],
    'json': {
    'name': 'Joshua Eaton',
    'address': '496 Garrett Viaduct\nOwensmouth, NE 84144',
},
    'key36348': 'value18075',
    'key8045': 'value78273',
    'key9145': 'value61011',
    'key240': 'value67780',
    'key9272': 'value17262',
    'key65618': 'value51263',
    'key25971': 'value33097',
    'key84871': 'value92662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Tasha Reed',
    'address': '7555 Ellis Coves Suite 782\nWest Haley, CT 62403',
    'text': 'Whole despite more southern north gun task. Data type then become east. Red customer strategy land none attack go.',
    'email': 'shannonkathleen@example.com',
    'phone_number': '402-620-2252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Willis',
    'Scott Smith',
],
    'json': {
    'name': 'Laura Davis',
    'address': '3289 Weeks Gardens\nWilkinsmouth, ID 34538',
},
    'key97512': 'value22236',
    'key78305': 'value41665',
    'key42008': 'value78699',
    'key36810': 'value51500',
    'key54327': 'value37675',
    'key72565': 'value9827',
    'key92795': 'value70752',
    'key78313': 'value36421',
    'key98213': 'value7437',
    'key88450': 'value45642',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Pamela Morales',
    'address': '937 Kathy Freeway Apt. 780\nJohnfort, PW 90094',
    'text': 'Which can avoid statement.\nMovement participant visit six. Trade under us organization by man realize like.',
    'email': 'collinsjay@example.net',
    'phone_number': '001-499-745-9711x63267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Janice Moore',
],
    'json': {
    'name': 'Tamara Hodges',
    'address': '760 Jeffrey Path Suite 930\nVickichester, NH 47418',
},
    'key55768': 'value83501',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Kimberly Turner',
    'address': '36715 Hughes Point\nEast Chadview, TX 97745',
    'text': 'Current machine close still. Wonder their place treat.\nAction tend suggest back serious especially. Address parent despite be.\nTax college citizen car. Again stay free leave while.',
    'email': 'warnerarthur@example.org',
    'phone_number': '001-577-267-5581x87050',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jody Hood',
    'John James',
    'Shannon Mata MD',
    'Katelyn Garrett',
],
    'json': {
    'name': 'Jason Watts',
    'address': '5426 Amy Streets\nLauriehaven, VI 48495',
},
    'key35819': 'value61295',
    'key90964': 'value11557',
    'key32094': 'value18799',
    'key71762': 'value19566',
    'key94159': 'value55194',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Charles Stevenson',
    'address': '92339 Amanda River\nLawrenceburgh, ME 72443',
    'text': 'Here difficult peace property whom name. Relate daughter land doctor water state. About child policy general professional nice.',
    'email': 'jasmine88@example.net',
    'phone_number': '(268)750-7233x835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Carson',
],
    'json': {
    'name': 'Cody Johnson',
    'address': '27564 Christine Lodge Suite 257\nDavidland, OK 15540',
},
    'key50614': 'value54035',
    'key73936': 'value37574',
    'key2095': 'value74217',
    'key31238': 'value88250',
    'key2140': 'value75866',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Patricia Choi',
    'address': '67605 Ronald Ports Apt. 353\nEast Shawn, MP 15569',
    'text': 'End recognize score minute their laugh. Technology find so hospital.\nEducation drive blood simply over training. White memory drop public community pretty.',
    'email': 'tonihicks@example.org',
    'phone_number': '001-924-955-9955',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Green',
    'Nicole Lester',
],
    'json': {
    'name': 'Keith Jones',
    'address': '55886 Katie Road\nSparksfurt, MO 19505',
},
    'key11939': 'value33109',
    'key83998': 'value40040',
    'key30187': 'value97387',
    'key41941': 'value69698',
    'key87021': 'value33420',
    'key40028': 'value12135',
    'key90584': 'value76489',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Joseph Miller',
    'address': '57981 Ryan Prairie Apt. 443\nMyersfurt, WA 79347',
    'text': 'Less adult notice growth. Partner decide exactly amount him data those.\nIf end low nothing strong because establish city. Toward talk just low continue find. Well hear Congress sell.',
    'email': 'brandyhaynes@example.org',
    'phone_number': '001-849-446-1271',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Byrd',
    'Sara Jenkins',
    'Cynthia Gonzalez',
    'Cheyenne Terrell',
],
    'json': {
    'name': 'Wesley Monroe',
    'address': '25453 Tamara Views Apt. 838\nChristophermouth, WA 84338',
},
    'key69624': 'value32645',
    'key64357': 'value56954',
    'key73176': 'value27568',
    'key96784': 'value61760',
    'key97529': 'value42850',
    'key10839': 'value6611',
    'key88775': 'value93574',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Leah Foster',
    'address': 'Unit 4889 Box 9900\nDPO AP 84358',
    'text': 'Recently actually message nice nothing cell. Oil to hotel.\nDrive crime realize writer present respond skin inside. Administration political church research value majority second factor.',
    'email': 'rclark@example.org',
    'phone_number': '336-471-4446x310',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Brock',
],
    'json': {
    'name': 'Deborah Nguyen',
    'address': '6005 Mclaughlin Green\nJeffreyfort, MO 14662',
},
    'key96849': 'value68980',
    'key81775': 'value25617',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jennifer Patrick',
    'address': '4783 Roberson Prairie\nAndersonchester, OH 43324',
    'text': 'International material before space. Sure body key director. Character baby describe quality surface letter off cold. Purpose have spend describe name.',
    'email': 'benjamin84@example.com',
    'phone_number': '745.957.4111x223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Mcdonald',
    'William Ali',
    'Brooke Walters',
],
    'json': {
    'name': 'Patrick Morgan',
    'address': '90188 Harvey Circles Apt. 443\nHaynestown, MN 83870',
},
    'key87847': 'value67103',
    'key53213': 'value40362',
    'key66817': 'value71502',
    'key30884': 'value5288',
    'key42086': 'value66968',
    'key46962': 'value82913',
    'key54474': 'value96999',
    'key66156': 'value84836',
    'key81581': 'value70215',
    'key55083': 'value63523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Jennifer Wise',
    'address': '18493 Amanda Groves Apt. 539\nPort Danielborough, VT 39445',
    'text': 'Main pass tree house professor subject occur.\nFigure hair interesting ability medical training decide just. Break education former the Mr activity. Day high research near.',
    'email': 'michaelcross@example.net',
    'phone_number': '841-936-4142x1573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Monica Wade',
    'Kathy Morales',
    'Tracy Woods',
    'Sean Thompson',
    'Alex Rodriguez',
],
    'json': {
    'name': 'Andrew Jones MD',
    'address': 'Unit 1998 Box 6964\nDPO AE 01092',
},
    'key60755': 'value34978',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Tom Morales',
    'address': '6255 Crawford Lane Apt. 740\nSouth Darrenstad, DC 42558',
    'text': 'Where conference trouble laugh open face concern. Especially how husband past last able decade.',
    'email': 'rogerswayne@example.net',
    'phone_number': '(762)278-5932',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Cook',
    'Shannon Wilson',
    'Michael Lawrence',
    'Joshua White',
    'Lauren Roman',
    'Amanda Johnson',
    'Eric Jenkins',
],
    'json': {
    'name': 'Kimberly Shaw',
    'address': '1539 Deanna Islands\nNew Jennifer, OK 20931',
},
    'key68526': 'value33626',
    'key83612': 'value88217',
    'key16138': 'value18953',
    'key74179': 'value40279',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Austin Campbell',
    'address': '612 Michael Plaza\nSmithberg, AR 98350',
    'text': 'Crime chance no space front agree new.\nTotal marriage capital customer operation. Particularly mean cold society ground center affect stay.',
    'email': 'heather62@example.com',
    'phone_number': '975.429.4145x021',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Trevor Andrews',
    'Nathan Barnes',
    'Ethan Smith',
    'David Hahn',
],
    'json': {
    'name': 'Daniel Hayes',
    'address': '1093 Gregory Mall Apt. 644\nGarciaton, WA 43508',
},
    'key82050': 'value65221',
    'key20237': 'value51069',
    'key62616': 'value64140',
    'key33941': 'value63569',
    'key50775': 'value80633',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Juan Knight',
    'address': '75207 Moreno Lake Suite 877\nKaneland, LA 64139',
    'text': 'Car although political American style sister mission yourself.\nDetermine could begin son. Better chance light of four several. Necessary similar husband concern beat.',
    'email': 'megansalinas@example.net',
    'phone_number': '789.770.3397x6024',
    'array_int_dynamic': [
    62030,
],
    'array_varchar_dynamic': [
    'Robin Miller',
    'Robert Hall',
    'Christopher Odom',
    'Lindsey Taylor',
    'Randy Branch',
    'Melanie Luna',
    'Amy Mclaughlin',
    'Paul Hansen',
    'Brandon Jimenez',
    'Cody Adams',
],
    'json': {
    'name': 'Christopher Ramsey',
    'address': '1642 Jeremy Glen Suite 038\nWest Ashleyshire, NJ 73130',
},
    'key15150': 'value17433',
    'key17499': 'value67452',
    'key56228': 'value39402',
    'key78097': 'value99970',
    'key55284': 'value15083',
    'key2671': 'value59561',
    'key8686': 'value96357',
    'key61165': 'value37587',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Larry Owen',
    'address': '3456 Curtis Parks\nCarrieberg, MP 73489',
    'text': 'Religious speech he past reach. Natural risk environmental student step. Than onto stay somebody story.\nCivil certain late party produce card his. Area business west get stay no authority.',
    'email': 'johnsontravis@example.net',
    'phone_number': '+1-407-653-1345x372',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Roberts',
    'Christina Payne',
    'Jason Rodriguez',
    'Thomas Padilla',
    'John Solomon',
    'Jason Cruz',
    'Alexa Atkinson',
    'Latoya Goodwin',
],
    'json': {
    'name': 'Jose Solis',
    'address': '19296 Cole Square Apt. 716\nLyonsside, AR 92511',
},
    'key87067': 'value961',
    'key45698': 'value90747',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Mark Smith',
    'address': '174 Roth Avenue\nNew Michelle, ME 64262',
    'text': 'End quality impact family about action very. Today better ago market.',
    'email': 'donna83@example.net',
    'phone_number': '5367995808',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mark Brown',
    'Steven Morris',
    'Antonio Herrera',
    'Jennifer Allen',
    'Lynn Davis',
    'David King',
    'Jorge Hill',
    'Kevin Mcmahon',
    'Suzanne Smith',
    'Steven Zuniga',
],
    'json': {
    'name': 'Matthew Ramos',
    'address': '06975 Reyes Trafficway\nHarrisberg, WY 78439',
},
    'key49822': 'value66138',
    'key133': 'value48468',
    'key23618': 'value27629',
    'key89787': 'value39361',
    'key9451': 'value9483',
    'key89903': 'value82192',
    'key42747': 'value22299',
    'key1051': 'value73225',
    'key56835': 'value2878',
    'key14509': 'value55957',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Toni Rodgers',
    'address': '2163 Douglas Ways Apt. 779\nNorth Samanthabury, GU 77150',
    'text': 'Since clearly raise order. Apply indeed project yard week despite she. Rock eight here would detail actually.',
    'email': 'elaine26@example.org',
    'phone_number': '936-327-5926x149',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Angela Allison',
    'Gavin Blake',
    'Ronald King',
    'Jason Caldwell',
    'James Lyons',
    'Jeffrey Zuniga',
    'Kimberly Charles',
    'Matthew Bass',
    'Michele Willis',
    'Joseph Bailey',
],
    'json': {
    'name': 'Amy Yoder',
    'address': '39979 Perkins Throughway\nWest John, AR 90240',
},
    'key59032': 'value53073',
    'key26575': 'value65522',
    'key80327': 'value99',
    'key11102': 'value72013',
    'key14224': 'value32349',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Ricky Martin',
    'address': '89332 Pearson Island\nEast Michaelchester, AR 57658',
    'text': 'Put among be process science as so close. Indicate rule talk finish remember newspaper cost never.',
    'email': 'plyons@example.com',
    'phone_number': '(283)802-3716x2890',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cathy Edwards',
    'Jenna White',
],
    'json': {
    'name': 'Randy Juarez',
    'address': '18046 Patrick Green Suite 168\nJoseview, HI 64284',
},
    'key25086': 'value2266',
    'key36316': 'value70527',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Aaron Jordan',
    'address': '326 April Spring\nAliciaport, GA 10242',
    'text': 'Create response civil back. Coach magazine activity character present. Although less during like defense record. Important same under many fly.',
    'email': 'brian21@example.org',
    'phone_number': '001-816-817-8574x77697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Burke',
    'Brandy Day',
    'Amy Galloway',
    'Anna Stewart',
    'Felicia Cook',
    'Carlos Smith',
    'Tony Burton',
    'Andrea Baker',
],
    'json': {
    'name': 'Blake Mitchell',
    'address': '060 Alexis Parkway Apt. 325\nNorth Sarah, RI 68868',
},
    'key11977': 'value99762',
    'key56781': 'value48518',
    'key48255': 'value27226',
    'key37398': 'value82850',
    'key4490': 'value62721',
    'key86397': 'value91056',
    'key18643': 'value62458',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Shelia Campbell',
    'address': '415 King Square Suite 441\nCarrberg, UT 91597',
    'text': 'Peace road speech dark role movie painting. Meeting rate college main political someone. Create sing executive possible spring forward research.',
    'email': 'clarkkyle@example.com',
    'phone_number': '822.509.3137x773',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Meyers',
    'Jonathan Wilkerson',
    'Jeffrey Hays',
    'Lauren Wallace',
    'William Hughes',
    'David Li',
    'Melissa Francis',
    'Kimberly Carroll',
],
    'json': {
    'name': 'William Gomez',
    'address': '404 Gallegos Course Apt. 282\nLake Natalie, WV 51759',
},
    'key43693': 'value45823',
    'key96004': 'value51420',
    'key64794': 'value40320',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Peter Rocha',
    'address': '0888 Walters Roads Suite 693\nSouth Edwardbury, NV 30286',
    'text': 'Behind official follow according bag clearly in. Partner up coach.\nCell instead send cultural hear plant cut. Public space note specific make. State fast yard discussion week want of.',
    'email': 'rpetty@example.net',
    'phone_number': '412.928.0620',
    'array_int_dynamic': [
    76713,
],
    'array_varchar_dynamic': [
    'Kimberly Gibson',
    'Rebecca Johnson',
    'Lauren Carrillo',
    'William Le',
],
    'json': {
    'name': 'Kyle Howell',
    'address': '45418 Smith Greens\nPort Williamfurt, IL 08563',
},
    'key16277': 'value59139',
    'key49269': 'value25703',
    'key70114': 'value22790',
    'key46619': 'value23156',
    'key68047': 'value86494',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Larry Mccarty',
    'address': '340 Robert Valley\nJuliefurt, KS 72106',
    'text': 'Mother suffer trade successful safe subject occur. Water yet heavy think half. Coach our care choose.',
    'email': 'paigezhang@example.net',
    'phone_number': '896.919.8666x74388',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Gutierrez',
    'Barbara Hancock',
    'Timothy Woods',
    'Lisa Smith',
    'Jacob Davis',
    'Brandon Moore',
    'Bruce Chang',
    'James Simpson',
    'Lisa Miles',
    'Marvin Bell',
],
    'json': {
    'name': 'Jenna Miller',
    'address': '37351 Johnson Pass\nPort Anneside, DE 53091',
},
    'key70458': 'value66699',
    'key92523': 'value20450',
    'key94742': 'value94402',
    'key2327': 'value58678',
    'key87569': 'value56790',
    'key19960': 'value63575',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Lisa Lopez',
    'address': '0708 Crane Ferry\nSouth Mindyland, SD 53967',
    'text': 'Listen finally tough. Top draw anything what raise. Never suggest himself article ball such ground.',
    'email': 'jamie29@example.net',
    'phone_number': '947-809-4626',
    'array_int_dynamic': [
    59714,
],
    'array_varchar_dynamic': [
    'Dylan Swanson',
    'Christopher Lane',
    'Alexis Phillips',
    'Brandon Lee',
    'Stephanie Wells DVM',
    'Austin Hayes',
    'Terry Montgomery',
    'Tammy Diaz',
    'Jennifer Harrell',
],
    'json': {
    'name': 'Jessica Vazquez',
    'address': '0775 Kenneth Prairie Apt. 166\nSouth Colin, TN 49962',
},
    'key79331': 'value34576',
    'key77290': 'value58933',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Joseph Hendricks',
    'address': '1331 Smith Walk Apt. 436\nEnglishchester, VI 44872',
    'text': 'Line sound necessary speak clear. Morning early yeah. Remember how production more.\nList degree bank education want. Time exist job soldier sport edge open staff.',
    'email': 'judy57@example.org',
    'phone_number': '836.666.5381',
    'array_int_dynamic': [
    84324,
],
    'array_varchar_dynamic': [
    'Christopher Cox',
    'Rachel Wilkins',
    'Fernando Hampton',
],
    'json': {
    'name': 'Kendra Murphy',
    'address': '348 Gwendolyn Meadow Suite 068\nJeannefort, LA 42666',
},
    'key89526': 'value15486',
    'key32342': 'value92753',
    'key81407': 'value17529',
    'key94797': 'value22105',
    'key42950': 'value71237',
    'key12674': 'value36049',
    'key46093': 'value56993',
    'key93722': 'value83443',
    'key67686': 'value97352',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Lindsey Carroll',
    'address': '140 Mcmillan Center Suite 652\nKiddmouth, NJ 05510',
    'text': 'Reveal others the professor. Store would Mrs teach top involve something.\nSix picture order right sort church hand some. Young spend head two there purpose. Performance enough then.',
    'email': 'james95@example.com',
    'phone_number': '001-898-217-9408x573',
    'array_int_dynamic': [
    3138,
],
    'array_varchar_dynamic': [
    'Mark Perez',
    'Harry Klein',
],
    'json': {
    'name': 'Nicole Peterson',
    'address': '626 Cobb Springs\nValentineton, UT 38998',
},
    'key96326': 'value12903',
    'key81156': 'value8019',
    'key24328': 'value87766',
    'key94772': 'value22987',
    'key35348': 'value49276',
    'key22485': 'value59120',
    'key33250': 'value52133',
    'key38422': 'value15630',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Alexis Davis',
    'address': '7664 Crystal Villages Suite 134\nJoshire, IL 98266',
    'text': 'Information government break news. Authority service yard after before.\nBoard position space now former point. Book mind scene none some house deal.',
    'email': 'smithpeggy@example.org',
    'phone_number': '001-321-796-7198',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Fleming',
    'Amber Harper',
    'Robert Hicks',
    'Patricia Reed',
    'Douglas Rich',
    'Lawrence Peterson',
    'Edward Flores',
    'Sherry Mata',
    'Mary Smith',
    'Brian Bullock',
],
    'json': {
    'name': 'Alison Sanchez',
    'address': '85423 Smith Fort Apt. 146\nOlivermouth, OK 33672',
},
    'key24123': 'value28076',
    'key97072': 'value32410',
    'key84679': 'value62564',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Ashley White',
    'address': '8366 Jennifer Trail\nHebertfort, TN 95810',
    'text': 'Say throughout customer develop chair attention.\nStay land different already officer maybe morning. Eight chair miss the art perhaps majority industry. Focus Democrat lead tonight.',
    'email': 'cynthiagardner@example.com',
    'phone_number': '(985)458-6626x896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Denise Green',
    'Jesus Swanson',
    'Jordan Myers',
    'Aaron Hardy',
    'Stephanie Young',
    'Joshua Wood',
    'Katherine Lowe',
    'Anthony Maldonado',
    'David Murray',
    'Aaron Evans',
],
    'json': {
    'name': 'Vanessa Sosa',
    'address': '05102 Diaz Rest Apt. 007\nRodriguezbury, WV 70702',
},
    'key72897': 'value80884',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jill Munoz',
    'address': '06865 Tucker Islands\nPatrickstad, VI 43073',
    'text': 'Standard site election. Evening notice more. Born lose behind after determine member.\nEither indicate both financial especially throw. Up occur race blue.',
    'email': 'jcooper@example.com',
    'phone_number': '448-615-6431',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brian Hines',
    'Chelsea Davis',
    'Yolanda White',
    'Mrs. Tricia Marquez DDS',
    'Neil Hurley',
    'Mario Brooks',
    'Sean Barajas',
],
    'json': {
    'name': 'Sarah Wright',
    'address': 'PSC 1290, Box 0600\nAPO AA 29941',
},
    'key19916': 'value11032',
    'key46808': 'value73944',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Karen Johnson',
    'address': '5117 Stevens Rue\nPaulland, PW 17439',
    'text': 'Eat more value water speak concern. And condition people song. Together change result skin let fight food.',
    'email': 'david94@example.org',
    'phone_number': '+1-675-215-6807x524',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jean Summers',
    'Melissa Mccarthy',
    'Cynthia Ruiz',
    'Samuel Stevens',
    'Aaron Williams',
    'Calvin Perez',
    'Tyler Cobb',
    'Gina Jefferson',
],
    'json': {
    'name': 'Stephen Wolfe',
    'address': 'PSC 2174, Box 9640\nAPO AP 60052',
},
    'key6235': 'value12624',
    'key46219': 'value58065',
    'key72909': 'value87001',
    'key69065': 'value28509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Kayla Ward',
    'address': '01169 Martinez Mountains Apt. 653\nPort Scottbury, ME 76735',
    'text': 'Position art deal wait concern painting other public. Soon bag modern believe say ask effect.',
    'email': 'ronald09@example.com',
    'phone_number': '348-887-0988x27370',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Scott',
    'John Solomon',
    'William Martin',
    'Shelby Johnson',
    'Christopher Schwartz',
    'Stephanie Good',
    'Amy Thompson',
    'Christopher Lee',
    'Amy Wells',
],
    'json': {
    'name': 'Julie Williams',
    'address': '740 Mark Views\nChadmouth, OH 83614',
},
    'key91015': 'value19941',
    'key72093': 'value9724',
    'key90718': 'value22238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Karen Newman',
    'address': '91760 Pamela Ferry Apt. 236\nJuarezburgh, NH 43229',
    'text': 'Room rest society sometimes store medical push force. Why deal nation leave every after heavy outside.\nSummer hand model however financial good. Radio hard report already now.',
    'email': 'morrowtimothy@example.net',
    'phone_number': '001-783-908-4838x07241',
    'array_int_dynamic': [
    67696,
],
    'array_varchar_dynamic': [
    'Margaret Anderson',
    'Isabella Miranda',
    'Cody Morrow',
    'Sandra Hall',
    'Mary Evans',
],
    'json': {
    'name': 'Christina Davis',
    'address': 'PSC 9883, Box 0659\nAPO AP 88043',
},
    'key37225': 'value27771',
    'key96294': 'value46637',
    'key51665': 'value39254',
    'key98492': 'value90594',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Anna Melendez',
    'address': '0831 Welch Forks Suite 599\nDylantown, ND 05633',
    'text': 'Record network bit nature last writer. Population let want opportunity man appear miss none. Source start former newspaper more.',
    'email': 'charlesdoyle@example.org',
    'phone_number': '304-901-4870x5941',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ricky Stanley',
],
    'json': {
    'name': 'Joshua Anderson',
    'address': '05288 Sandra Flat Suite 940\nRicardofort, MN 40704',
},
    'key69242': 'value7211',
    'key64477': 'value82048',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Frederick Washington',
    'address': '3366 Bennett Plaza\nAndrewland, NC 40566',
    'text': 'Road create leader story nice. Still language religious career institution really. Finish during make buy both relationship major front.\nMagazine standard role by lead. Ball thousand effect.',
    'email': 'robert13@example.net',
    'phone_number': '7927400111',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Greg Wright',
    'David Garrison PhD',
    'John Morrow',
    'Keith Garcia',
    'Virginia Rosales',
    'Melissa Valencia',
    'Brittany Graham',
    'Michelle Saunders',
    'Alyssa Stewart',
],
    'json': {
    'name': 'Jasmine Floyd',
    'address': '0398 Williams Curve\nKatherinemouth, VT 52417',
},
    'key97817': 'value81151',
    'key80122': 'value43981',
    'key37004': 'value9343',
    'key93225': 'value88697',
    'key13471': 'value23255',
    'key4478': 'value24729',
    'key42438': 'value46635',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Shirley Woods',
    'address': '3840 Morris Estate\nLake Travis, NM 82925',
    'text': 'Report citizen environmental. Appear wrong record few. Owner country different analysis site.',
    'email': 'charles05@example.com',
    'phone_number': '(768)436-1496x2200',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Braun',
    'Katie Castro',
],
    'json': {
    'name': 'Antonio Mueller',
    'address': '1774 Angela Views\nHarpermouth, GU 48871',
},
    'key40903': 'value10092',
    'key38056': 'value8238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Joseph Curry',
    'address': '410 Lauren Stravenue\nWest Patrickfurt, MO 95435',
    'text': 'Involve high necessary personal wall society maybe.\nNetwork something certainly these easy win long. Material road science keep during time lay.',
    'email': 'jillferguson@example.org',
    'phone_number': '448.949.1953x71130',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christina Larson',
    'Valerie Jones',
    'Reginald Brown',
    'Jennifer Murray',
    'Michelle Henson',
    'Molly Collier',
    'Courtney Barker',
    'Ashley Williams',
],
    'json': {
    'name': 'Donna Davis',
    'address': '2978 Lisa Pines\nEast Todd, DE 55269',
},
    'key76794': 'value75413',
    'key74617': 'value5969',
    'key27635': 'value72177',
    'key37841': 'value48945',
    'key64413': 'value55079',
    'key1988': 'value13474',
    'key77048': 'value16677',
    'key95842': 'value4592',
    'key4740': 'value37524',
    'key79693': 'value92132',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Elizabeth Holland MD',
    'address': 'PSC 7659, Box 9423\nAPO AE 64232',
    'text': 'Quite value own season billion. Land worry south laugh relate fine but.\nReduce today off computer site purpose wrong. Message similar child hit.',
    'email': 'kathleen22@example.com',
    'phone_number': '+1-802-455-7589x9725',
    'array_int_dynamic': [
    25662,
],
    'array_varchar_dynamic': [
    'Paul Martinez',
    'Arthur Patel',
    'Melissa Gutierrez',
],
    'json': {
    'name': 'Elizabeth Peterson',
    'address': '7027 Kelley Estate Suite 587\nEast Joseph, MT 84976',
},
    'key92367': 'value93241',
    'key46973': 'value23245',
    'key4714': 'value87362',
    'key99973': 'value34384',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Victoria Wilkins',
    'address': '70288 Christensen Road Apt. 940\nSouth Meganton, NH 61747',
    'text': 'Everybody building call yet painting professional. From study series debate.\nUntil how direction site every then. White professional toward. Give nation part strategy any.',
    'email': 'lisa70@example.org',
    'phone_number': '990-379-9358x93190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Klein',
    'George Clark',
    'Ryan Livingston',
    'Travis Morrow',
],
    'json': {
    'name': 'Natasha Farmer',
    'address': '23345 Sean Ridges Suite 087\nLisaburgh, WI 44864',
},
    'key64453': 'value95003',
    'key31280': 'value92152',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Christopher Howell',
    'address': '89877 Amanda Parkway Apt. 887\nLake Richard, TN 03318',
    'text': 'Particular study director interesting remain whom Republican. Wind station industry baby fire anyone run. Decade within itself teach consumer decide. Foot back short every race finish.',
    'email': 'erinhubbard@example.com',
    'phone_number': '985-377-5074',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Debra Perry',
    'Dr. Kimberly Harvey',
    'Frank Palmer',
    'Kara Rangel',
    'Kelly Andrews',
],
    'json': {
    'name': 'Jeffrey Collins',
    'address': '32703 Reginald Mall\nNorth Kaylahaven, OK 07150',
},
    'key95983': 'value62041',
    'key50108': 'value22982',
    'key85199': 'value72861',
    'key38601': 'value96104',
    'key84931': 'value84430',
    'key24279': 'value43265',
    'key94835': 'value33934',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Christopher Chan III',
    'address': '64760 Anthony Cliffs Apt. 899\nJohnsonburgh, NM 24379',
    'text': 'Understand trade call prevent. Spring chance goal economic each current. Similar board adult possible.\nMission perhaps pull space. Before goal kid consider white change start unit.',
    'email': 'ybennett@example.org',
    'phone_number': '(287)907-5436x97244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tony Snyder',
    'Christopher Rodriguez',
    'Sheila Hunter',
    'Alexander Jefferson',
    'Eric Guzman',
    'Matthew Martin',
    'Bradley Tapia',
    'John Stewart',
    'David Nichols',
],
    'json': {
    'name': 'Brittany Potter',
    'address': '655 Randall Mount\nPort Sabrina, ND 84972',
},
    'key84950': 'value94332',
    'key33827': 'value28412',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Lori Wood',
    'address': '19925 Bell Highway\nWest Mark, KY 04529',
    'text': 'Teacher field page ball worry. Race boy parent mouth kid catch two.',
    'email': 'dannybarnes@example.net',
    'phone_number': '(566)842-3279x01874',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Scott',
    'Ashley Brown',
    'Wayne Price',
    'Eric Barton',
    'Lonnie Lewis',
    'Denise Smith',
    'Jennifer Bautista DVM',
    'William Murphy',
    'Philip Wilson',
    'Sean Daugherty',
],
    'json': {
    'name': 'Joe Foster',
    'address': '08221 Wilson Crest\nHobbsfurt, RI 58518',
},
    'key74781': 'value59508',
    'key31240': 'value50584',
    'key71578': 'value56119',
    'key84314': 'value22669',
    'key47379': 'value88562',
    'key61552': 'value4844',
    'key3370': 'value32768',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Brandon Spears',
    'address': '9925 Hall Hills\nShawchester, NC 88215',
    'text': 'Tree by unit might through clearly. Letter benefit author help message him.\nEntire add include compare. Professor this story property. Investment explain avoid number.',
    'email': 'kellyburton@example.org',
    'phone_number': '593-687-1790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Dakota Hunter',
    'Kenneth Jones',
    'Tonya Walker',
    'Christine Hughes',
],
    'json': {
    'name': 'Heather Mercado',
    'address': '27652 Wendy Bridge\nGregorymouth, AS 42148',
},
    'key74259': 'value35640',
    'key87627': 'value53410',
    'key54646': 'value70877',
    'key94050': 'value57339',
    'key70496': 'value15595',
    'key18121': 'value40096',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Christopher Ho',
    'address': 'PSC 5476, Box 2608\nAPO AP 90879',
    'text': 'Collection by listen partner nice onto source. Serious figure whose back yes within.',
    'email': 'judy87@example.net',
    'phone_number': '+1-232-926-9152x58119',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Caleb Johnson',
    'Hannah Palmer',
    'Micheal Ellis',
    'Charles Mills',
    'Timothy Martinez',
    'Bradley Booker',
    'Alicia Campos',
    'Haley Austin',
    'Rebecca Williams',
],
    'json': {
    'name': 'Thomas Phillips',
    'address': '8614 Traci Glens\nJenniferland, DC 33029',
},
    'key41154': 'value10817',
    'key83452': 'value61437',
    'key29943': 'value78599',
    'key93545': 'value38872',
    'key51645': 'value65755',
    'key26472': 'value30656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Benjamin Miller',
    'address': '0182 Daniel Viaduct Apt. 088\nEast Lawrencestad, CT 15504',
    'text': 'Information us another make election need. Oil traditional adult star body.',
    'email': 'robertleon@example.net',
    'phone_number': '453-647-6613x53652',
    'array_int_dynamic': [
    49462,
],
    'array_varchar_dynamic': [
    'Zachary Yoder',
    'Donald Miller',
    'Mr. Jackson Baker DDS',
    'Michael Ayala',
    'Geoffrey Mccullough',
    'Lawrence Nichols',
    'Cynthia Pierce',
    'Ann Jordan',
    'Michael King',
    'Dustin Johnson',
],
    'json': {
    'name': 'Ryan Crawford',
    'address': '262 Gonzalez Parks Apt. 179\nHarrismouth, RI 58441',
},
    'key97841': 'value44903',
    'key37105': 'value26886',
    'key9679': 'value44995',
    'key93026': 'value76975',
    'key38835': 'value35518',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Carol Bowen',
    'address': '7318 Baker Station\nRowlandland, MN 95369',
    'text': 'Mission our stop place.\nLikely assume poor sister power. Suggest country lose prevent price. Place yourself drug wrong area tree eye only.\nDoor write appear break. Education travel full at.',
    'email': 'dhall@example.net',
    'phone_number': '6085882879',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amy Ruiz MD',
    'Katherine Stewart',
    'Kristy Atkinson',
],
    'json': {
    'name': 'Tyler Ware',
    'address': '64933 Daniel Port\nChadmouth, OH 12424',
},
    'key77567': 'value13650',
    'key79247': 'value97270',
    'key84187': 'value61223',
    'key39347': 'value79565',
    'key58238': 'value9581',
    'key17588': 'value68006',
    'key1903': 'value59456',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Samantha Welch',
    'address': '7032 Raymond Path\nWest John, VI 68515',
    'text': 'Cut rich teacher past expect lot. Upon threat improve oil girl. Then least choose really adult low food look. General mouth trial meeting identify.',
    'email': 'amypierce@example.net',
    'phone_number': '526.851.0929x9437',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Justin Shelton',
    'Leslie Hendricks',
    'Susan Ryan',
    'Wanda Carter',
    'Michael Curry',
    'Rodney Stevenson',
    'Caroline Davis',
],
    'json': {
    'name': 'Chris Mitchell',
    'address': '1245 Whitney Neck\nHessland, CT 09409',
},
    'key31572': 'value35807',
    'key45410': 'value51438',
    'key22244': 'value475',
    'key35288': 'value63590',
    'key96402': 'value31790',
    'key78039': 'value13793',
    'key18798': 'value98596',
    'key20553': 'value11052',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Angela Gonzalez',
    'address': '2508 Smith Roads\nBowenport, ID 24726',
    'text': 'Raise he TV Republican. White clear fly full tree. Put interest natural so. Two beat long enjoy.',
    'email': 'figueroalaura@example.org',
    'phone_number': '(789)965-9649x472',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Latoya Evans',
    'Amy Burton',
    'Stacy Delgado',
    'Michael Raymond',
    'Joseph Cox',
    'Jessica Cruz',
    'Gregory Miller',
    'Brandy Simmons',
],
    'json': {
    'name': 'Katrina Robinson',
    'address': '162 Cunningham Junctions Suite 420\nRobertside, OK 78250',
},
    'key40850': 'value86583',
    'key18147': 'value52532',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Elizabeth Chang',
    'address': '09175 Richard Mews\nNew Jonathan, CO 10532',
    'text': 'Color woman four season admit local. Attorney price cost about student. Reach past across able always consider again. Stuff trial area conference once recently present thing.',
    'email': 'gwalker@example.net',
    'phone_number': '615-369-4132',
    'array_int_dynamic': [
    33214,
],
    'array_varchar_dynamic': [
    'David Durham',
    'Joseph Richmond',
    'Denise White',
    'Katrina Matthews',
],
    'json': {
    'name': 'Richard Sanchez',
    'address': '923 Walker Passage\nAndreside, NC 67380',
},
    'key43626': 'value74824',
    'key52714': 'value58952',
    'key10040': 'value28582',
    'key54486': 'value85630',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Lisa Graham',
    'address': '4474 Pamela River Apt. 160\nTraceyborough, CO 49299',
    'text': 'Pattern manager whether page window. Nor everyone wear get.\nParty hope drive morning without collection. Yard yard whose try.',
    'email': 'amber04@example.net',
    'phone_number': '(833)674-1914x09939',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Gina Brown',
    'Erika Baker',
    'Nicholas Anderson',
    'Holly Miller',
    'Felicia Bishop',
    'Jordan Hood',
    'Brandon Evans',
    'Willie Clark',
    'Sara Durham',
    'Debra Nolan',
],
    'json': {
    'name': 'Troy Hays',
    'address': '97358 Tucker Fort\nCarlosberg, AK 04064',
},
    'key54804': 'value74941',
    'key22988': 'value74244',
    'key77439': 'value45576',
    'key93486': 'value40703',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Thomas Combs',
    'address': '5029 Catherine Lock\nCampbellport, VI 15097',
    'text': 'Buy around safe material book some. Property general positive shoulder. Figure Congress you government baby.',
    'email': 'mallen@example.org',
    'phone_number': '560.866.7565',
    'array_int_dynamic': [
    23422,
],
    'array_varchar_dynamic': [
    'Eric Conner',
],
    'json': {
    'name': 'Tina Ellis',
    'address': '352 Kaitlin Plains Apt. 194\nNorth Charles, SC 90011',
},
    'key8478': 'value77989',
    'key63974': 'value71173',
    'key74555': 'value92875',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Erin Oneill',
    'address': 'Unit 4671 Box 5899\nDPO AE 39552',
    'text': 'Get worker air return step. About democratic one style.',
    'email': 'shawchristopher@example.org',
    'phone_number': '+1-887-992-5020x101',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Cooper',
    'Miranda Rodriguez',
    'Vanessa Barnett',
    'Julie Grant',
],
    'json': {
    'name': 'Ashlee Miller',
    'address': '68304 Anderson Shores\nPort William, IN 46397',
},
    'key66960': 'value93644',
    'key622': 'value70935',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Jason Santiago',
    'address': '6894 Hernandez Roads\nMcgrathborough, WY 08493',
    'text': 'Fast stop state smile future bring. Follow bed town race special policy.\nThree television certain sometimes many course prepare. Feel spring half kid tonight piece poor leader. Cup for water.',
    'email': 'jason32@example.org',
    'phone_number': '(597)948-9296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Ramos',
    'Cynthia Bradshaw',
    'Kathleen Baker',
    'Melissa Evans',
    'Dr. Megan Carter',
    'Darryl Clayton',
    'Melinda Lowe',
    'Melissa Hutchinson',
    'Michael Norris',
],
    'json': {
    'name': 'Mark Marsh',
    'address': '301 Murphy Manors\nMelaniestad, WY 48908',
},
    'key91864': 'value60025',
    'key76816': 'value67480',
    'key26655': 'value57942',
    'key78119': 'value21821',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Bonnie Branch',
    'address': 'USNS Lopez\nFPO AA 73461',
    'text': 'Speak professor Congress that above machine. Seat alone cover deal political. School ever unit six before.\nTruth plant item bill language. Agree stop for although second so.',
    'email': 'slawson@example.org',
    'phone_number': '001-557-745-9224x45305',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Karen Jones',
    'Christopher Walters',
    'Danielle Robinson',
    'Megan Nichols',
    'Brandi Potter',
    'William Smith II',
],
    'json': {
    'name': 'Jeremiah Lynn',
    'address': '984 Kelly Skyway Apt. 779\nEast David, ME 32266',
},
    'key54876': 'value32844',
    'key52841': 'value98661',
    'key68839': 'value7221',
    'key53090': 'value38161',
    'key5588': 'value83195',
    'key92483': 'value72289',
    'key96681': 'value13580',
    'key92156': 'value90236',
    'key77706': 'value94668',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Eric Rose',
    'address': '964 Brown Walk\nEast Patrickchester, NE 06171',
    'text': 'Staff present place organization run. Area lot its worker father heavy. Or line history determine end policy.',
    'email': 'sharon15@example.org',
    'phone_number': '001-540-328-6481x53169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Harrison',
    'Luis Morgan',
    'Leslie Wade',
    'Nicole Singh',
    'James Scott',
    'Kim Wright',
    'Robin Melendez',
    'Travis Patel',
],
    'json': {
    'name': 'Frank Roberts',
    'address': '725 Clark Burg\nEast Marieland, TN 20582',
},
    'key77820': 'value35700',
    'key21272': 'value53540',
    'key75646': 'value24089',
    'key21294': 'value24606',
    'key56629': 'value82178',
    'key7279': 'value55986',
    'key55304': 'value35394',
    'key68289': 'value96014',
    'key68544': 'value71792',
    'key89791': 'value86258',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Christine Brooks',
    'address': 'Unit 9794 Box 6008\nDPO AE 84417',
    'text': 'Black drop control writer. Enjoy cause prove myself huge. Thought one option east certain yeah.\nFront notice manage great organization only strategy owner. Girl spend say thus pass.',
    'email': 'rodriguezlaura@example.org',
    'phone_number': '+1-560-963-6564x01321',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Diane Evans',
    'Jack Ferrell',
    'Sandra Woodward',
    'Kenneth Taylor',
    'Jordan Roberts',
],
    'json': {
    'name': 'Jon Henry',
    'address': '615 Brandt Trail Suite 800\nEast Michellestad, GA 09758',
},
    'key52277': 'value54954',
    'key95195': 'value79643',
    'key40869': 'value75950',
    'key95219': 'value41992',
    'key94350': 'value31516',
    'key69373': 'value78994',
    'key9898': 'value95950',
    'key71238': 'value81028',
    'key42685': 'value63753',
    'key53901': 'value96512',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Derek Beard',
    'address': '2539 Park Drive\nSouth Benjaminmouth, MS 22725',
    'text': 'Property area once black power wish reach. Policy own every.\nEasy second professor training baby. Financial lose surface movie style.',
    'email': 'fvasquez@example.com',
    'phone_number': '370-992-4315x27811',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cindy White',
    'James Smith',
    'Shelley Haley',
    'Kayla Perez',
    'Samuel Roberts',
    'Joseph Perez',
    'Rebecca Mills',
    'Shelia Cole',
    'Caitlyn Lyons',
],
    'json': {
    'name': 'Sheryl Hawkins',
    'address': '53851 Adam Skyway Suite 138\nMichaelfort, ID 85955',
},
    'key64879': 'value3912',
    'key37565': 'value24486',
    'key72361': 'value39800',
    'key55069': 'value625',
    'key1591': 'value8012',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'David Stephens',
    'address': '416 Moore Underpass\nWest Lisa, UT 02142',
    'text': 'Task than computer job test rather account message. Explain nearly star start. True hold member describe work fly officer.',
    'email': 'brianna68@example.net',
    'phone_number': '294.322.6907x624',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brady Carlson',
    'James Sawyer',
    'David Curry',
    'Ronald Brown',
    'Thomas Davis',
    'Cindy Hughes',
    'Mckenzie Holden',
    'Jacob Baker',
    'Kathy Gardner',
    'Edward Ponce',
],
    'json': {
    'name': 'Angel Thomas',
    'address': '62801 Baker Haven\nSouth Kennethburgh, IA 22915',
},
    'key92832': 'value16418',
    'key85103': 'value97077',
    'key42201': 'value63171',
    'key21361': 'value98515',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Debra Christensen',
    'address': '08505 Taylor Port\nReidton, WV 43359',
    'text': 'Section remember all artist forward foreign catch. Wrong black agree although remember what really.\nThem usually most. Citizen truth move key past message.',
    'email': 'uharris@example.org',
    'phone_number': '001-710-468-6455x311',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'David Patterson',
    'Andrew Ortega',
    'Kathryn Wilkinson',
],
    'json': {
    'name': 'Jessica Johnson',
    'address': '3639 Timothy Centers\nNew Alexandra, ND 82695',
},
    'key55538': 'value54449',
    'key32315': 'value10206',
    'key46226': 'value14927',
    'key47237': 'value20677',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Gregory Randall',
    'address': '34472 Donald Lock\nWest Vanessabury, DC 42082',
    'text': 'Cold officer point suggest would field movie if. Theory individual analysis.',
    'email': 'christianstanley@example.org',
    'phone_number': '975.942.9426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Cody Perez',
    'Amanda Copeland',
    'Clifford Dunn',
    'Kyle Freeman',
],
    'json': {
    'name': 'Eric Alvarez',
    'address': '394 Terry Spring Suite 372\nNorth Rachel, KY 10440',
},
    'key3192': 'value10452',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Pamela English',
    'address': '7015 Sherry Divide Apt. 924\nPort Rebecca, MN 84545',
    'text': 'Commercial staff hair collection baby decade. Interesting she price carry do. Executive ok job manage as.',
    'email': 'fordmatthew@example.com',
    'phone_number': '001-671-547-9077',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Lane',
],
    'json': {
    'name': 'Stephanie Little',
    'address': '94202 Nunez Lodge\nNorth Steven, MI 34255',
},
    'key19397': 'value76237',
    'key88365': 'value77948',
    'key25292': 'value79374',
    'key63951': 'value37857',
    'key53807': 'value33800',
    'key47938': 'value42836',
    'key59953': 'value22534',
    'key36415': 'value74372',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jessica Cooper',
    'address': '70336 Chen Stream Apt. 014\nNew James, OR 63737',
    'text': 'Write foot million laugh soon grow protect. Minute plant civil moment be simple.',
    'email': 'dmccarthy@example.com',
    'phone_number': '293.984.7378x8490',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Brown',
    'George Perez',
    'Michael Stafford',
],
    'json': {
    'name': 'Wendy Nunez',
    'address': '199 White Rapids Suite 549\nSouth Deborah, FL 31939',
},
    'key97788': 'value43121',
    'key87981': 'value42750',
    'key22323': 'value2334',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Amy Mcclain',
    'address': 'USNS Blair\nFPO AP 29084',
    'text': 'Win decade total team. Course tell manage.\nBeyond affect heavy worry. Find present through once.\nPrice see administration spend. Per decade control successful add short offer.',
    'email': 'turnerkristine@example.net',
    'phone_number': '4083910479',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Shannon Taylor',
    'Kelly Webb',
    'Samuel Mcdonald',
    'Alexander Tran',
    'Cheyenne Wolf',
    'Yvonne Rice',
    'Tamara Collins',
    'Carol Dickerson',
],
    'json': {
    'name': 'James Conner',
    'address': '361 James Stream Suite 763\nTaylorton, FM 03041',
},
    'key79352': 'value82232',
    'key89371': 'value73731',
    'key92891': 'value52147',
    'key27424': 'value38705',
    'key91394': 'value38655',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Eric Cruz',
    'address': '29424 Hunt Garden Suite 304\nJustinmouth, AR 80427',
    'text': 'In east land that learn to owner deal. Sort sport cold peace rather. From carry as herself phone.\nBillion environment reach report little. Rich from do quite.',
    'email': 'burtonamanda@example.com',
    'phone_number': '723.592.2517x9837',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lori Branch',
    'Ryan Jackson',
    'Sally Adams',
    'Daniel Snyder',
    'Michael Thompson',
    'Tina Brown',
    'Alicia Hendrix',
    'Dana Franklin',
    'Megan Clark',
],
    'json': {
    'name': 'Amanda Brown',
    'address': '795 Guzman Falls\nDavidborough, SC 02465',
},
    'key30385': 'value55952',
    'key51910': 'value95108',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Robert Patel',
    'address': '17707 Hicks Courts Apt. 340\nLake Danielview, PA 07896',
    'text': 'Board already manager raise. Good everybody must ball if. Brother join agent gun account serious game.\nGlass moment picture letter save improve society. Life professor effort pull.',
    'email': 'dennishoward@example.org',
    'phone_number': '446.614.4904',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Hensley',
    'Cheryl Richardson',
    'Whitney Price',
    'Margaret Acosta',
],
    'json': {
    'name': 'Elizabeth Harris',
    'address': '58476 Thomas Wells Apt. 523\nWest Robin, RI 87997',
},
    'key35058': 'value78340',
    'key10932': 'value52801',
    'key49212': 'value10983',
    'key84376': 'value32820',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Alexandria Garrett',
    'address': '078 Brian Mount Suite 267\nLopezhaven, WV 97514',
    'text': 'Window building attack above season.\nFocus her seven guy. Than ability drug learn. Remain explain play result. Strong or system change open sort.',
    'email': 'codywood@example.com',
    'phone_number': '938.966.0004x463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Natasha Rodriguez',
    'Gerald Garza',
    'Kerry Mcdaniel',
    'Michael Lee',
    'Ryan Rojas',
    'Erica Young',
],
    'json': {
    'name': 'Erin Payne',
    'address': '95073 Sarah Passage\nMonicaborough, GA 57335',
},
    'key32507': 'value19576',
    'key67844': 'value52212',
    'key61176': 'value99708',
    'key5686': 'value93457',
    'key27540': 'value38506',
    'key95558': 'value96491',
    'key17374': 'value9014',
    'key37216': 'value90021',
    'key94137': 'value17765',
    'key65761': 'value20209',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Brooke Hopkins',
    'address': '0069 Gray Flat Apt. 901\nPattersonview, FL 81486',
    'text': 'Number education short sense it life throughout. War but keep science cut participant.\nMe same form activity. Your accept thousand spend. Hope reason investment hair.',
    'email': 'jboyle@example.org',
    'phone_number': '(797)936-6823x994',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Susan Kelley',
],
    'json': {
    'name': 'Jasmine Williams',
    'address': 'USCGC Gilbert\nFPO AA 41731',
},
    'key212': 'value53474',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Dominique Stevens',
    'address': '262 Clarke Expressway\nNew Pamelastad, OH 53141',
    'text': 'Interesting always next inside wait would.\nEye by guess special develop. Simply PM top coach short half forward individual. These customer financial education.',
    'email': 'jean64@example.com',
    'phone_number': '(922)238-2651x11207',
    'array_int_dynamic': [
    72117,
],
    'array_varchar_dynamic': [
    'Karen Garner',
    'William Morales',
],
    'json': {
    'name': 'Craig Nguyen',
    'address': '7732 Sarah Mill Suite 528\nWalkerhaven, AS 07397',
},
    'key32649': 'value31519',
    'key32839': 'value58081',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Pamela Adams',
    'address': '855 King Village Apt. 330\nTorreshaven, VI 35528',
    'text': 'Important them deal majority offer role. Decade perhaps central also model wrong.\nItem develop like. Religious prove change minute all recently if.',
    'email': 'ywashington@example.org',
    'phone_number': '6134783264',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. April Barber',
    'Michael Harrison',
    'Kathleen Murphy',
    'Andre Stanley MD',
    'Anthony Harrell',
    'Timothy Ramos',
    'Dr. Justin Sanchez',
    'Kyle Blair',
    'Sheena Nguyen',
],
    'json': {
    'name': 'Chad Castro',
    'address': '3420 Smith Hill Apt. 452\nBryanbury, IN 34097',
},
    'key49342': 'value77728',
    'key26571': 'value81412',
    'key17195': 'value25279',
    'key72453': 'value28449',
    'key15965': 'value39433',
    'key4531': 'value2550',
    'key89529': 'value10175',
    'key94546': 'value99957',
    'key54627': 'value93127',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Gina Hays',
    'address': '266 Amber Plains\nNew Heather, OR 59665',
    'text': 'Ever senior risk agreement recently bed kid. Lawyer something process wonder suffer tax describe author.\nEye scene center everyone six attorney main. Themselves serve management agree whose move.',
    'email': 'ashlee58@example.org',
    'phone_number': '280.806.8154x155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Linda Leonard',
    'Susan Mills',
    'Whitney Campos',
    'Frank Knight',
    'Eddie Harris',
    'Sharon French',
    'Jose Acosta',
],
    'json': {
    'name': 'Meghan Carr',
    'address': '66387 Blake Islands\nWest Danielle, KY 49318',
},
    'key93433': 'value62647',
    'key65833': 'value2377',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Emma Mejia',
    'address': '5369 Hutchinson Plaza Apt. 182\nCarolynhaven, IL 65784',
    'text': 'Town explain occur boy.\nCut get time teacher effect.',
    'email': 'rodriguezterri@example.net',
    'phone_number': '491.257.0817',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Thomas',
    'Christopher Murray',
],
    'json': {
    'name': 'Laura Lee',
    'address': '11783 Sarah Pines\nWest Ryanville, WI 86242',
},
    'key48142': 'value45897',
    'key37507': 'value43480',
    'key97604': 'value37159',
    'key14089': 'value98573',
    'key1481': 'value54860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Ashley Morgan',
    'address': '10452 Brian Junction Suite 660\nDanatown, MI 29467',
    'text': 'Quickly message rock think Mr big green. Role away pay herself green catch. Knowledge treat worry.',
    'email': 'lisamarks@example.org',
    'phone_number': '(767)470-0156x6323',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Rodgers',
],
    'json': {
    'name': 'Misty Hansen',
    'address': 'USCGC Oconnell\nFPO AP 75263',
},
    'key78525': 'value7783',
    'key99984': 'value10795',
    'key58273': 'value28582',
    'key81387': 'value69583',
    'key13595': 'value66599',
    'key70700': 'value95676',
    'key78684': 'value70901',
    'key13158': 'value64381',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Lisa Green',
    'address': '79352 Shelton Port Apt. 099\nGraymouth, WY 35957',
    'text': 'Low doctor specific authority value stop put. Nor must natural wide. Phone Congress note.\nDeal several allow. Image president drive power often leave himself.',
    'email': 'wharrison@example.org',
    'phone_number': '+1-508-541-3344x41361',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Frank Logan',
],
    'json': {
    'name': 'Jeffrey Diaz',
    'address': '0305 Winters Mountain\nNorth Kimberlymouth, SC 04904',
},
    'key78494': 'value41755',
    'key37': 'value82610',
    'key56286': 'value17002',
    'key8181': 'value72929',
    'key42122': 'value27894',
    'key85230': 'value46667',
    'key59752': 'value2073',
    'key50894': 'value7096',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Stephen Parker',
    'address': '88073 Gloria Plains Apt. 246\nJessicastad, CO 92996',
    'text': 'Certainly tax various activity allow. Decide then determine amount. Relationship city issue.\nProve themselves marriage raise. Left president mean who image cold become. Moment agree hand rise.',
    'email': 'stacy22@example.org',
    'phone_number': '+1-724-804-0219x99319',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Leonard',
],
    'json': {
    'name': 'Chelsea Perez',
    'address': '33075 Ellen Mount Apt. 721\nNorth Janet, MP 33082',
},
    'key211': 'value79882',
    'key39460': 'value47809',
    'key78171': 'value76465',
    'key62585': 'value7576',
    'key46543': 'value23541',
    'key78474': 'value95262',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Courtney Benson',
    'address': '7442 Guerra Run\nNew Brentport, ME 84644',
    'text': 'By ask price across hand support. Stage per middle certainly choice worry. Concern agent require professor.',
    'email': 'greenlarry@example.net',
    'phone_number': '(234)874-8316x3806',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Santos',
    'Victoria Taylor',
    'Gregory Bryant',
    'Jennifer Evans',
    'Tara Morris',
],
    'json': {
    'name': 'Connor West',
    'address': '4651 Thornton Run\nWallmouth, MO 77437',
},
    'key18651': 'value29376',
    'key84257': 'value64493',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Rachael Kim',
    'address': '35957 Amy Trail\nWest Breannaville, IL 24732',
    'text': 'Wonder effect report decide life fear. Tonight necessary street add. Others personal side will family drug work.\nGovernment build might once successful energy.',
    'email': 'patricia09@example.com',
    'phone_number': '001-703-858-1395x401',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Benjamin',
    'Antonio Marshall',
],
    'json': {
    'name': 'April Garcia',
    'address': '44639 Edward Station Apt. 441\nMonicachester, NM 54256',
},
    'key70477': 'value13998',
    'key61324': 'value23397',
    'key58975': 'value57208',
    'key74866': 'value51752',
    'key4721': 'value8252',
    'key19962': 'value12845',
    'key28235': 'value24270',
    'key10088': 'value13630',
    'key6889': 'value2890',
    'key33795': 'value14834',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Joshua Simpson',
    'address': '94324 Dillon Causeway\nEast Michelle, WV 53084',
    'text': 'Protect letter once new. Popular just important firm myself study investment.',
    'email': 'qperez@example.com',
    'phone_number': '9724670627',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Ferguson',
    'Jay Baldwin',
],
    'json': {
    'name': 'David Tucker',
    'address': '87880 Lewis Fall Apt. 192\nTracyfurt, CA 04887',
},
    'key66060': 'value4961',
    'key77766': 'value96143',
    'key23080': 'value80300',
    'key87701': 'value25823',
    'key261': 'value51624',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Alyssa Taylor',
    'address': '1570 Randall River Apt. 170\nMossmouth, LA 36040',
    'text': 'Practice soon century certainly here. Table contain probably security past. None likely probably become she.\nSimply popular run drop full thank.',
    'email': 'thompsonjames@example.com',
    'phone_number': '001-670-914-1326x48462',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Blanchard',
    'Jessica Perez',
    'Abigail Pittman',
    'Joy Murphy MD',
    'Tyler Carter',
    'Riley Garcia',
],
    'json': {
    'name': 'Paula Wright',
    'address': '51242 Mckinney Lane Suite 000\nLesliemouth, AZ 28941',
},
    'key62391': 'value43019',
    'key33740': 'value19913',
    'key87071': 'value71226',
    'key36827': 'value71657',
    'key14048': 'value35430',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Mark Wilson',
    'address': '63912 Kristin Stravenue\nSouth Richardberg, MT 96536',
    'text': 'Moment song visit final evening. Health later likely. Arrive pressure old like care today.',
    'email': 'gibbsjacqueline@example.com',
    'phone_number': '001-970-588-0697x90474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Wanda Nolan',
    'Cindy Kim',
    'Kyle Mccoy',
    'Tammy Yang',
    'Jennifer Daniels',
    'Erica Mack',
    'Lisa Hendrix',
    'Darryl Haney',
],
    'json': {
    'name': 'Stephen Lopez',
    'address': '491 Michael Lights Apt. 010\nEast Johnton, IN 14547',
},
    'key58080': 'value1453',
    'key40970': 'value34836',
    'key85628': 'value47795',
    'key5563': 'value80554',
    'key93584': 'value25487',
    'key61064': 'value67100',
    'key78918': 'value22159',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Kelly Perkins',
    'address': 'Unit 5514 Box 0720\nDPO AA 14527',
    'text': 'Federal generation from series method eye. Away yourself bad draw discover once everybody partner.\nSuccessful factor child month.\nChoose interest list. Head cause relate world.',
    'email': 'terrybrian@example.com',
    'phone_number': '5094470874',
    'array_int_dynamic': [
    55496,
],
    'array_varchar_dynamic': [
    'Christopher Hogan',
    'Angela Bryant',
    'Derrick Reynolds',
],
    'json': {
    'name': 'Rachael Graves',
    'address': '229 Maria Manor Apt. 401\nMcguiretown, CO 76258',
},
    'key91621': 'value24988',
    'key13718': 'value7352',
    'key75621': 'value58318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Dave Roberson',
    'address': '4364 Casey Springs Suite 865\nAndreaburgh, WI 12678',
    'text': 'Rule real lay identify. Everything learn evidence sort certain. Ground option from friend.',
    'email': 'piercechristine@example.com',
    'phone_number': '786.964.4843x51333',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Antonio Lutz',
    'Patrick Nelson',
    'Kenneth Petersen',
    'Connie Rios',
    'Melissa Horton',
    'Kyle Lopez',
    'Alicia Erickson',
],
    'json': {
    'name': 'Clinton Rhodes',
    'address': '65248 John Manors Suite 582\nPort Kenneth, IL 87046',
},
    'key26122': 'value7988',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Rachel George',
    'address': '7241 Davis Extension\nNew Robert, NY 13453',
    'text': 'Support environment fall remain beautiful risk. Go price every officer year.\nScene policy beat fall pick very. Impact nature small magazine event citizen. Career offer open leader woman.',
    'email': 'anthony47@example.com',
    'phone_number': '8804756385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Morgan',
    'Christopher Grant',
    'Bonnie Moore',
    'David Aguirre',
],
    'json': {
    'name': 'Benjamin Lee',
    'address': '1057 Kristi Field\nSouth Troyhaven, MH 84425',
},
    'key29625': 'value83666',
    'key48416': 'value81458',
    'key55136': 'value2026',
    'key77821': 'value73628',
    'key22555': 'value84679',
    'key11799': 'value28505',
    'key42901': 'value16715',
    'key69261': 'value66279',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Brittany Martinez',
    'address': '18071 Maynard Shores\nPort Cynthiafort, MA 49652',
    'text': 'True central treatment collection. This bar rather edge. Charge conference go force.\nOnly customer community they everyone police. Opportunity option catch believe require consider.',
    'email': 'santanarobert@example.org',
    'phone_number': '690-568-7509x361',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Steele',
    'Patricia Graham',
    'Stacey Taylor',
    'Marie Rice',
],
    'json': {
    'name': 'Ryan Cooper',
    'address': 'PSC 0883, Box 7967\nAPO AP 15289',
},
    'key54132': 'value73801',
    'key81360': 'value93429',
    'key58090': 'value79370',
    'key33264': 'value99363',
    'key17321': 'value93903',
    'key12534': 'value3617',
    'key83892': 'value66017',
    'key11007': 'value52398',
    'key12425': 'value96826',
    'key13880': 'value75481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Jonathan Johnson',
    'address': '750 Sean Throughway\nAnthonymouth, NY 40340',
    'text': 'Local loss citizen enjoy. Culture figure trip talk. Soon decision travel as morning glass west.',
    'email': 'kaitlynsmith@example.org',
    'phone_number': '(620)364-3896x58052',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Green',
    'Barbara Nash',
    'Ariana Gonzalez',
    'Jorge Adams',
    'Barbara Barton',
    'David Lewis',
    'Debra Clements',
    'Joseph Webster',
],
    'json': {
    'name': 'Richard Ramirez',
    'address': '555 Danny Mount\nNew Ginaport, ID 59304',
},
    'key16761': 'value93958',
    'key86901': 'value40231',
    'key57913': 'value82024',
    'key60434': 'value44502',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Robin Patterson',
    'address': '2764 Eric Shoal Suite 948\nLake Aaron, KY 05873',
    'text': 'Consumer agree environmental travel choose. Simply professional ready not miss reason magazine.',
    'email': 'josephstevens@example.org',
    'phone_number': '614.242.8446x0912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Webb',
    'Kristin Odom',
    'Molly Henderson',
],
    'json': {
    'name': 'Christopher Rodriguez',
    'address': '30001 Peters Ville Suite 969\nKathyshire, MO 02053',
},
    'key27178': 'value68212',
    'key32488': 'value21509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Heather Espinoza',
    'address': '614 Ross Branch Apt. 494\nLake Tracey, IN 43664',
    'text': 'Spend if stop rich himself point. Her peace health walk surface prevent manager.\nBack focus toward run political serve. Deal side kitchen.\nHold during score yeah film man.',
    'email': 'gonzalesjennifer@example.net',
    'phone_number': '771.325.7683x5969',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Reginald Smith',
],
    'json': {
    'name': 'Dakota Merritt',
    'address': '690 Fisher Mall Apt. 120\nWest Deborahville, WI 92792',
},
    'key41056': 'value86446',
    'key58435': 'value37637',
    'key51719': 'value46089',
    'key5634': 'value56160',
    'key89206': 'value44896',
    'key82165': 'value73170',
    'key89054': 'value78329',
    'key81825': 'value93805',
    'key13111': 'value62015',
    'key82287': 'value56479',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Alexa Ortiz',
    'address': '3823 Hanson Glen Suite 050\nBelltown, FM 58409',
    'text': 'Score impact series. Similar stay model.\nSpecial budget lot mother without side believe. Thing fact per wrong. Indeed structure event.',
    'email': 'patellinda@example.com',
    'phone_number': '(519)776-2319x3783',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Guerrero',
    'Frank Brown',
    'Martha Smith',
    'Jamie Martinez',
    'Tyler Johnson',
    'John Weaver',
    'Jason Fleming',
],
    'json': {
    'name': 'Savannah Eaton',
    'address': '9607 Parker Flats Suite 976\nKevinburgh, VT 78369',
},
    'key53296': 'value57961',
    'key34757': 'value44167',
    'key16851': 'value17474',
    'key72940': 'value32376',
    'key31148': 'value33092',
    'key94097': 'value60337',
    'key30329': 'value54156',
    'key27556': 'value77311',
    'key89115': 'value40643',
    'key39483': 'value59273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Tiffany Moore',
    'address': 'USS Higgins\nFPO AA 30945',
    'text': 'Economic both expect new give international education. Conference team wish. Least pretty magazine month none.',
    'email': 'michelle84@example.org',
    'phone_number': '622.382.2814',
    'array_int_dynamic': [
    27010,
],
    'array_varchar_dynamic': [
    'Jacqueline Ross',
    'Charlene Coleman',
    'Courtney Turner',
    'Paula Hebert',
    'Kathy Webster',
],
    'json': {
    'name': 'Scott Robinson',
    'address': 'Unit 8027 Box 8271\nDPO AA 07237',
},
    'key90089': 'value24518',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Brenda Hernandez',
    'address': '11159 Kathryn Throughway\nSouth Ericstad, MS 51965',
    'text': 'Than rich agree north music Mr level. Catch civil benefit including. Him reflect artist.\nLong seek through. Ten our line very box into reveal.',
    'email': 'yfisher@example.com',
    'phone_number': '001-987-703-9402x2545',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Daniels',
    'Christine Mccoy',
    'Carolyn Nichols',
    'Karen Rose',
    'Amanda Valentine',
    'Jade Simmons',
    'Mr. Justin Hawkins',
    'Nicholas Charles',
],
    'json': {
    'name': 'Christopher Douglas',
    'address': '0259 Robert Rapids Apt. 909\nMcclainstad, TN 75791',
},
    'key83821': 'value76559',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Christopher Williams',
    'address': '078 Trevor Freeway Apt. 315\nMistyfort, SD 47102',
    'text': 'Son back crime address. If senior order value set. Relationship now value news doctor community soldier.',
    'email': 'anne69@example.net',
    'phone_number': '+1-716-430-5068x9171',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Walter Aguirre',
    'Calvin Wolf',
    'Jorge Stephenson',
    'Dawn Oliver',
    'Sara Hooper',
    'Brandon Hill',
    'David Pena',
    'Nicole Thomas',
    'Jamie Bennett',
],
    'json': {
    'name': 'Audrey Bowen',
    'address': '1249 Sanders Burgs\nPort Hannah, PR 51089',
},
    'key33906': 'value91088',
    'key27132': 'value14886',
    'key21117': 'value91763',
    'key17416': 'value37330',
    'key13851': 'value207',
    'key25700': 'value45665',
    'key37118': 'value70932',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Steven Tapia',
    'address': '8390 Martinez Knolls Suite 167\nMikaylafort, OH 14417',
    'text': 'Wind wide enough night least recognize magazine. Must space mouth star young determine.',
    'email': 'ndiaz@example.net',
    'phone_number': '(940)935-8642',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christina Evans',
    'Brittney Mckee',
    'Mark Martin',
    'Stacey Anderson',
    'Megan Solis',
],
    'json': {
    'name': 'Mary Singh',
    'address': '91901 Latasha Plains Suite 809\nBerryshire, SC 60948',
},
    'key25633': 'value30426',
    'key92164': 'value74564',
    'key21145': 'value12488',
    'key63737': 'value41556',
    'key68411': 'value89215',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Sandra Brown',
    'address': '413 Paige Junctions Suite 091\nPrattview, WY 96072',
    'text': 'Sit ball miss require. Whose approach why because. Policy stuff article car big pattern quality. Agree glass learn letter.\nWhat six card fear husband.',
    'email': 'hcook@example.net',
    'phone_number': '866.534.4163x61594',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Grace Brady',
    'John Howard',
    'Joseph Jones',
],
    'json': {
    'name': 'Michael Todd',
    'address': '4875 Dakota Mews Suite 335\nWest Tiffanyfurt, MA 72570',
},
    'key8755': 'value83740',
    'key96326': 'value6220',
    'key78725': 'value63523',
    'key55474': 'value95215',
    'key29259': 'value19066',
    'key14125': 'value16755',
    'key62109': 'value66300',
    'key47165': 'value41386',
    'key56863': 'value29184',
    'key63173': 'value40363',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Natalie Grimes',
    'address': '6562 Fernandez Mill\nFrancestown, AK 89049',
    'text': 'Perhaps wait environment would. Food current hundred center boy response. Majority open next never risk.',
    'email': 'cynthia92@example.com',
    'phone_number': '+1-612-417-1496x892',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christina Marquez',
    'Kayla Parker DVM',
    'Rebecca Spencer',
    'Joshua Silva',
],
    'json': {
    'name': 'Cory Fields',
    'address': '053 Lauren Passage Apt. 989\nNew Maurice, WA 60183',
},
    'key22570': 'value79962',
    'key74163': 'value30217',
    'key40753': 'value92648',
    'key51029': 'value41728',
    'key69672': 'value8345',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Jo Bryant',
    'address': '8176 Franklin Walk\nMorrischester, AZ 90815',
    'text': 'Age experience board since child. End try develop section your value. White box offer.\nGrow adult tax go with. Industry low likely her business material. Born per next.',
    'email': 'nancybaker@example.org',
    'phone_number': '+1-696-215-8292x1791',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Luis Reynolds',
    'Jeffery Davis',
    'Richard Keller',
],
    'json': {
    'name': 'Jason Fields',
    'address': '46289 Molly Pines Apt. 526\nNorth Peterstad, VT 53624',
},
    'key89512': 'value21269',
    'key4621': 'value74907',
    'key18789': 'value13021',
    'key67037': 'value6577',
    'key63721': 'value94221',
    'key27497': 'value43377',
    'key19588': 'value99623',
    'key67797': 'value81636',
    'key11473': 'value13561',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Richard Hines',
    'address': '809 Lee Port Suite 173\nDamonside, MD 43180',
    'text': 'Congress information run indeed your student first take. Effort show give bring care.\nShow raise actually quality my fine growth. Line event attention order culture wait.',
    'email': 'aguilarmelinda@example.net',
    'phone_number': '966-829-7923x9417',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Julie Brown',
    'Susan Martinez DDS',
    'Natasha Smith',
    'Bethany Moore',
    'Sara White',
    'Wendy Shea',
],
    'json': {
    'name': 'Kathleen Gomez',
    'address': '9456 Anthony Mountains\nPort Tami, VI 24514',
},
    'key82574': 'value60845',
    'key22605': 'value54072',
    'key96503': 'value52021',
    'key68102': 'value73940',
    'key97298': 'value31711',
    'key78979': 'value53907',
    'key18742': 'value19004',
    'key87942': 'value93973',
    'key68137': 'value48529',
    'key71600': 'value92448',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Samuel Fernandez',
    'address': '41582 Benjamin Vista Suite 762\nLake Victoria, NV 22001',
    'text': 'Huge reality team know operation. Speak attention difficult glass.\nHalf boy cultural art region southern debate.\nHuman detail him thank low firm. Main clear organization garden build six minute.',
    'email': 'adiaz@example.net',
    'phone_number': '3485885996',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Hayes',
    'Christopher Stewart',
    'Jose Rogers',
    'Richard Blake MD',
    'Jennifer Salazar',
    'Jacqueline Giles',
    'Amy Hernandez',
    'Marc Garcia',
],
    'json': {
    'name': 'Lisa Smith',
    'address': '4598 Avila Way\nSouth Dean, MH 61120',
},
    'key56901': 'value27472',
    'key79632': 'value70806',
    'key71538': 'value10837',
    'key74506': 'value1151',
    'key46089': 'value338',
    'key71201': 'value57625',
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
    'RequestId': '96916922-62f1-11f0-a8a1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_47_820736sFyEdNtz',
    'filter': 'uid > -100 and uid < 100',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'phone_number',
    'name',
    'email',
    'json',
    'uid',
    'array_varchar_dynamic',
    'address',
    'text',
    'vector',
    'array_int_dynamic',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v1/vector/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '9734f274-62f1-11f0-b44f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_47_820736sFyEdNtz',
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
    'RequestId': '8fd4b990-62f1-11f0-9da4-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_36_47_820736sFyEdNtz',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > -100 and uid < 100]_1752745021.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid100AndUid1001752745021Json()
    test.run_tests()
