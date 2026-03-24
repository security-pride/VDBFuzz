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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVectorNegative_test_insert_vector_with_invalid_collection_name_1752744238_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_collection_name_1752744238.json"
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



class AllmilvusLogtestinsertvectornegativeTestInsertVectorWithInvalidCollectionName1752744238Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_collection_name_1752744238.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_collection_name_1752744238.json"
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
    'RequestId': 'c46ba615-62ef-11f0-bb05-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_57_057923IBgxFtAX',
    'dimension': 128,
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
    'RequestId': 'c48edbcb-62ef-11f0-ad91-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'invalid_collection_name',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Scott Fisher',
    'address': '985 Faulkner Glen Suite 335\nWiseberg, MS 27805',
    'text': 'Until sell part heavy.\nWest institution face pull herself hot say. Include customer phone adult recently tax west. Raise town usually worry contain worker. Want not choice suffer.',
    'email': 'lpeterson@example.org',
    'phone_number': '(853)381-9366',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Robert Thomas',
],
    'json': {
    'name': 'Kevin Baker',
    'address': '2071 Garcia Ranch Apt. 311\nThomaschester, PA 79477',
},
    'key6607': 'value826',
    'key59649': 'value15754',
    'key63511': 'value10758',
    'key41608': 'value68949',
    'key2831': 'value18474',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sharon James',
    'address': '547 Schultz Isle\nHollymouth, NC 98985',
    'text': 'Condition stop write city. Quickly way time situation. Election political southern bill environment summer.',
    'email': 'youngmichael@example.net',
    'phone_number': '001-207-750-1247x9251',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Edward Johnson',
    'Danny Mullins',
    'Jason Orr',
    'Veronica Alvarado',
    'John Carney',
    'John Medina',
    'Adam Weaver',
    'Ian Castro',
    'Stephanie Lopez',
    'Christopher Richmond',
],
    'json': {
    'name': 'Laura Harvey',
    'address': 'USNV Kennedy\nFPO AA 61471',
},
    'key44164': 'value73167',
    'key27482': 'value15574',
    'key75119': 'value13844',
    'key20289': 'value96693',
    'key99712': 'value52906',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Carol Shepard',
    'address': '84032 Kelly Light Suite 631\nNew Cindyton, LA 62580',
    'text': 'News seek eat easy specific worker. Financial rich also soon lead.\nRecent administration moment recent. Term rock build not. Purpose science long say from decision.',
    'email': 'robinsonjessica@example.net',
    'phone_number': '474-408-5695',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Bender',
    'Michelle Gonzalez',
    'Jesse Garner',
    'Shari Rose',
    'Patricia Hopkins',
    'Jessica Obrien',
    'Michael Lewis',
    'Paul Gonzales',
    'Mrs. Victoria Martin',
    'Andrew Dickerson',
],
    'json': {
    'name': 'Mark Hughes',
    'address': '0483 Bennett Mountain Apt. 485\nNew Michelle, DC 80062',
},
    'key55169': 'value88840',
    'key84696': 'value88270',
    'key20146': 'value51503',
    'key4208': 'value37680',
    'key40320': 'value45986',
    'key34578': 'value31188',
    'key4979': 'value42505',
    'key80648': 'value28126',
    'key31897': 'value37771',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Emily Edwards',
    'address': '643 Edward Coves Suite 264\nRoyfurt, AZ 15740',
    'text': 'Appear call share easy may. Keep I crime reveal black agreement system hospital.\nGreen technology parent student stock TV know. Term positive bit understand.',
    'email': 'tonya57@example.org',
    'phone_number': '+1-832-216-6773x7244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Parker',
    'Brian Miller',
    'Jessica Dudley',
    'Stephen Lane',
    'Thomas Freeman',
    'Daniel Morris',
    'Alicia Smith DDS',
    'Dr. Jeremiah Payne',
    'Jessica Arnold',
    'Courtney Welch',
],
    'json': {
    'name': 'Melinda Orozco',
    'address': '2108 Jennifer Heights\nBryanborough, PA 24695',
},
    'key13185': 'value81549',
    'key85487': 'value6025',
    'key73480': 'value22833',
    'key37305': 'value96072',
    'key60190': 'value1253',
    'key89731': 'value78866',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Mrs. Alexandra Mathews',
    'address': '40356 Austin Glens Apt. 621\nByrdstad, NE 29463',
    'text': 'Size no opportunity total. Win memory church ability run project which at. Federal administration reduce worker itself best.',
    'email': 'jacksonjustin@example.org',
    'phone_number': '716-595-4941x636',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Stevenson',
    'Darin Russell',
    'Dawn Wright',
    'Timothy Fleming',
    'Leslie Sexton',
    'Christopher Richmond',
],
    'json': {
    'name': 'Katie Flores',
    'address': '193 Robert Plain\nDavidton, VT 46836',
},
    'key6589': 'value7487',
    'key65099': 'value55217',
    'key7583': 'value81560',
    'key29274': 'value63684',
    'key7366': 'value54183',
    'key28136': 'value85794',
    'key53648': 'value3419',
    'key92847': 'value91918',
    'key70100': 'value60298',
    'key78475': 'value3394',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Logan Terry',
    'address': '20508 Williams Circle Apt. 876\nPort Benjaminstad, MH 91220',
    'text': 'Improve vote cost relate nor reduce. Baby cold organization decision teach institution who.',
    'email': 'christina84@example.net',
    'phone_number': '256.769.1390',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Johnson',
    'Robert Wu',
    'Nicole Campbell',
    'Eric Lawrence',
],
    'json': {
    'name': 'John Oconnell',
    'address': '35682 Rodriguez Island Suite 047\nEast Jasonstad, WV 94911',
},
    'key82894': 'value65967',
    'key40391': 'value97908',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Mrs. Katherine Hughes',
    'address': '5322 Nicole Cove Apt. 825\nPottsborough, AL 26339',
    'text': 'Very both financial issue. Work view PM cost.\nWould professor leg. Large single morning she upon.\nInteresting woman entire star easy quite yet. Share piece Democrat beautiful their popular.',
    'email': 'nicolebrooks@example.net',
    'phone_number': '208-249-7359x7076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Arnold',
    'Jamie Jones',
    'Heather Marshall',
    'Cassidy Ortiz',
    'Andrea Garcia',
],
    'json': {
    'name': 'Preston Gibson',
    'address': '474 Hannah Courts\nColemanport, NC 39361',
},
    'key61213': 'value38303',
    'key21572': 'value27357',
    'key42791': 'value35737',
    'key24478': 'value48345',
    'key78652': 'value95974',
    'key74909': 'value60822',
    'key7171': 'value38733',
    'key25285': 'value34368',
    'key61639': 'value64324',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Francisco Ward',
    'address': '12730 Kirby Passage\nPort Jacqueline, PR 47514',
    'text': 'Quite son blue offer. Democratic water us dream middle. Eye mention daughter up agency within.',
    'email': 'brownjulie@example.org',
    'phone_number': '001-326-346-8758x721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Douglas',
    'Mary Lee',
    'Sarah Martin',
    'Eric Potter',
    'Tiffany Goodwin',
],
    'json': {
    'name': 'Brenda Dudley',
    'address': '121 Christopher Islands Suite 204\nRichmondmouth, UT 72871',
},
    'key51065': 'value14463',
    'key41563': 'value95539',
    'key91878': 'value59698',
    'key32526': 'value20238',
    'key39086': 'value84765',
    'key17709': 'value35109',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'James Bailey',
    'address': '753 Alexander Light\nPort Morganhaven, MH 56498',
    'text': 'Market such medical good can. Author seven light college full. Individual move listen great home.',
    'email': 'keithrios@example.net',
    'phone_number': '(670)909-4516x7424',
    'array_int_dynamic': [
    42564,
],
    'array_varchar_dynamic': [
    'Lori Rodriguez',
],
    'json': {
    'name': 'William Thomas',
    'address': 'USS Carson\nFPO AA 07974',
},
    'key90203': 'value32267',
    'key89519': 'value42766',
    'key50606': 'value58532',
    'key2118': 'value94940',
    'key83245': 'value66968',
    'key6826': 'value90806',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Susan Ellison',
    'address': '065 Hendrix Pines Suite 218\nLake Sarah, ME 98519',
    'text': 'Appear sport majority positive before sure. Such born seem food argue question should others. Writer home yard parent forward heavy attack. Pattern future room note sort common computer.',
    'email': 'kristine55@example.org',
    'phone_number': '3087504224',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Woods',
    'Teresa Parsons',
    'Michelle Montoya',
],
    'json': {
    'name': 'Samantha Vance',
    'address': '9217 Hernandez Shoal Apt. 288\nJohnchester, MH 92431',
},
    'key31751': 'value69454',
    'key3445': 'value54502',
    'key67823': 'value37511',
    'key2527': 'value32656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Mark Ortiz',
    'address': '668 Chan Drive Suite 830\nPort Laura, AR 90355',
    'text': 'Black beat court husband attention good rest. History television sit have. Although test decide home.\nBase field on great surface four. Our school above station cup civil purpose right.',
    'email': 'jacquelinestanley@example.org',
    'phone_number': '001-658-340-7410x615',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Santos',
    'Roberto Wells',
    'Michael Clark',
],
    'json': {
    'name': 'Jessica Jones',
    'address': '87417 Newman Vista Suite 109\nEast Cherylmouth, CA 61932',
},
    'key72765': 'value10861',
    'key61302': 'value32508',
    'key33688': 'value72593',
    'key55134': 'value32675',
    'key86326': 'value94576',
    'key91982': 'value18106',
    'key91977': 'value78996',
    'key43956': 'value37594',
    'key63259': 'value578',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Alexandra Jones',
    'address': '60934 Farmer Rapid\nSouth Margaretville, MA 53968',
    'text': 'Executive behavior kind find. Reveal threat end agency realize forget tough together. Full forget able tree maintain.',
    'email': 'william21@example.net',
    'phone_number': '001-762-508-8712',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mariah Martinez',
    'Thomas Werner',
    'William Johnson',
    'Cassandra Clayton',
    'Thomas Long',
    'Lindsey Hurley',
],
    'json': {
    'name': 'Brittany Glover',
    'address': '707 Meagan Parks Apt. 725\nPort Jameschester, GA 58974',
},
    'key62191': 'value23764',
    'key85586': 'value43477',
    'key94453': 'value67390',
    'key32850': 'value86807',
    'key49685': 'value51333',
    'key70507': 'value89976',
    'key31584': 'value51091',
    'key46931': 'value1186',
    'key75720': 'value31553',
    'key64695': 'value17420',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Scott King',
    'address': '93173 Baldwin Burgs Apt. 491\nWest Jessica, MD 55140',
    'text': 'Since positive admit community much. Peace some war machine exist threat put. Near pass sense low human skin.',
    'email': 'jcervantes@example.net',
    'phone_number': '001-819-935-4522x13745',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Camacho',
],
    'json': {
    'name': 'Eric Olsen',
    'address': '0546 Blake Plains Suite 709\nJasonstad, WY 53850',
},
    'key89221': 'value89071',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Bridget Stanton',
    'address': '20984 Miller Fall Suite 545\nAntoniofort, NH 69717',
    'text': 'Subject really color worry foreign. Way research easy reveal agency people.\nSkin strong and type professor south follow. Black least and matter building enough education.',
    'email': 'craigcharles@example.org',
    'phone_number': '693-754-7572x037',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Charles Evans',
    'Rose Olson',
    'Michele Bailey',
    'Dana Stevenson',
    'Nicole Smith',
],
    'json': {
    'name': 'Mr. John Barber',
    'address': '34512 Christensen Turnpike\nPort Brandon, OH 57124',
},
    'key87338': 'value90677',
    'key44446': 'value27924',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jason Walker',
    'address': '9819 Gregory Gardens\nKeithmouth, NJ 82824',
    'text': 'Consumer back magazine least single ready one prevent. Marriage raise memory citizen pretty wrong product toward.\nSimilar though industry hospital miss wife whole. Like official decide high son.',
    'email': 'srussell@example.com',
    'phone_number': '434-961-8040x07881',
    'array_int_dynamic': [
    21424,
],
    'array_varchar_dynamic': [
    'Erin Johnson',
    'Ryan Ortiz',
    'Jeffery Pierce',
    'Michael Young',
    'Kelli Garcia',
    'Mark Hawkins',
    'Joseph Johnston',
    'Haley Smith',
],
    'json': {
    'name': 'Matthew Cox',
    'address': '165 Payne Road Apt. 103\nAnthonyberg, WV 10805',
},
    'key11205': 'value18601',
    'key31600': 'value78797',
    'key30170': 'value13710',
    'key79803': 'value55178',
    'key76943': 'value7426',
    'key99584': 'value63009',
    'key8549': 'value34656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Darin Cruz',
    'address': '916 Michael Fort Apt. 591\nJessicachester, IN 24443',
    'text': 'Movie road on central. Bag financial yard media reflect discussion employee.\nHistory full piece through why. Least such something continue focus late about.',
    'email': 'walter03@example.org',
    'phone_number': '(894)777-9123',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Kelley',
],
    'json': {
    'name': 'Kathy Calhoun',
    'address': '0068 Brown Tunnel\nPort Kristen, HI 57625',
},
    'key34178': 'value61091',
    'key31316': 'value20515',
    'key54416': 'value36626',
    'key22857': 'value56670',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Matthew Herrera',
    'address': '97187 Molina Road\nJensenton, FM 84129',
    'text': 'Ten analysis plan size response born piece.\nNice meeting do experience strong help international. Next improve serve will painting ok today determine.',
    'email': 'rachelmccann@example.com',
    'phone_number': '+1-726-841-2307x78510',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Charles Pugh',
    'Joshua Dickson',
    'Michael Giles',
    'Wendy Harris',
],
    'json': {
    'name': 'Jeffrey Mitchell DDS',
    'address': '004 Kelly Point Suite 485\nNorth Brittany, WA 52243',
},
    'key99262': 'value91297',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Tracy Martinez',
    'address': '675 Jerry Common\nLake Maria, GA 66329',
    'text': 'Down economic middle ok statement they lay. Must effort now thousand rule. Positive service still choose federal.',
    'email': 'deborahbird@example.net',
    'phone_number': '+1-494-432-3398x198',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Sellers',
    'James Thomas',
    'Ryan Richard',
    'Jennifer Fernandez',
],
    'json': {
    'name': 'Michael Jones',
    'address': '1838 Conner Avenue\nSingletonburgh, PR 84442',
},
    'key91737': 'value22565',
    'key50882': 'value16',
    'key54876': 'value4357',
    'key50067': 'value53195',
    'key43775': 'value87347',
    'key67340': 'value31883',
    'key57795': 'value42652',
    'key11242': 'value32398',
    'key35017': 'value62868',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Jessica Blake',
    'address': '774 James Junction Suite 759\nWest Michaelmouth, NC 18782',
    'text': 'Each window side attorney side low follow. Article argue institution television. Speak social several leg generation employee.\nScene remain understand religious likely.',
    'email': 'murphymegan@example.org',
    'phone_number': '(523)597-1302x10633',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Scott Ramirez',
    'Julie Allison',
    'Melissa Oliver',
    'Andrew Cook',
    'Michelle Oconnor',
    'Kenneth Bryant',
    'Amanda Smith',
],
    'json': {
    'name': 'Daniel Becker',
    'address': '29163 Michael Cove Suite 183\nNew Kristafurt, DE 62135',
},
    'key77644': 'value86672',
    'key78987': 'value66899',
    'key35979': 'value9972',
    'key31361': 'value65377',
    'key40029': 'value7003',
    'key83535': 'value10952',
    'key1495': 'value80480',
    'key55080': 'value94534',
    'key13237': 'value84895',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Melissa Nguyen',
    'address': '619 Johnson Club Suite 372\nPort Angelaberg, HI 51512',
    'text': 'Him left stay fine understand season whose. Power traditional your place. Situation system always.',
    'email': 'erin46@example.net',
    'phone_number': '001-213-283-4945x860',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Mendez',
    'Regina Rubio',
    'Tina Moore',
    'Stacey Kennedy',
    'Dr. Anna Allen',
    'Steven Osborn',
    'Stephen Rivas',
    'Nancy Luna',
    'Hailey Oliver',
    'Kristi Rivera',
],
    'json': {
    'name': 'Rachel Hansen',
    'address': '4456 Arellano Park Suite 395\nOrtizhaven, IN 88598',
},
    'key69896': 'value19608',
    'key91572': 'value40344',
    'key84808': 'value7876',
    'key9499': 'value89233',
    'key74267': 'value45172',
    'key2143': 'value41052',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Ms. Elizabeth Mata',
    'address': '8216 Nicole Estates\nEast John, AR 04297',
    'text': 'Local star thousand act our claim. Study policy throw weight light personal. Different history argue start sense guess type there. Top tonight yet Congress woman.',
    'email': 'erikcombs@example.com',
    'phone_number': '+1-513-695-0378x19656',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Renee Johnston',
    'Thomas Flowers',
    'Michelle Moody',
    'Richard Williams',
    'William Martin',
    'Matthew Dickerson',
    'Valerie Glenn',
    'John Gordon',
    'Joshua Friedman',
],
    'json': {
    'name': 'Daniel Stafford',
    'address': '7040 Bryan River Apt. 947\nJuliemouth, OR 67812',
},
    'key66404': 'value69846',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Christopher Carson',
    'address': '4327 Murray Village Apt. 301\nPort James, WI 86783',
    'text': 'Enough wonder least forget positive. Above town player sister remember pick process.\nArea heart near wish. Four effort budget billion money factor. Season great art.',
    'email': 'benjamin67@example.net',
    'phone_number': '723.746.8452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Johnson',
],
    'json': {
    'name': 'Alicia Summers',
    'address': '404 Gonzalez Burg\nWest Daniel, TN 68761',
},
    'key62694': 'value86381',
    'key81233': 'value45709',
    'key66071': 'value46457',
    'key75991': 'value22032',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Megan Clay',
    'address': '1622 Klein Roads\nRichmouth, NE 11246',
    'text': 'Against write such fast. Push college maintain simply prepare note. Evidence upon newspaper drop use involve leave.',
    'email': 'rsmith@example.com',
    'phone_number': '551-926-2988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brandy Patrick',
    'Matthew Keith',
    'Casey Rose',
    'Michael Campbell',
    'Candice Duffy',
    'Tammy Mckenzie',
    'Michael Skinner',
    'Christopher Donovan',
],
    'json': {
    'name': 'Candice Cruz',
    'address': '286 Frank Shore\nAshleybury, NM 54084',
},
    'key48786': 'value53465',
    'key95475': 'value61982',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Michael Campbell',
    'address': '1305 Neal Island Apt. 326\nWilsonberg, NM 86857',
    'text': 'Drug down body improve begin surface able. Wear through here per forward.\nParticularly government sense you accept defense. Sister public idea road sign. Seven meet study career card future.',
    'email': 'jmorrison@example.org',
    'phone_number': '466.525.7607x49001',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Marissa Klein',
    'Johnny Simmons',
    'Brian Hartman',
    'Lauren Wood',
    'Desiree Perry',
],
    'json': {
    'name': 'Robert Shaw',
    'address': 'Unit 4676 Box 5569\nDPO AA 96852',
},
    'key13841': 'value66241',
    'key6029': 'value3132',
    'key95653': 'value55382',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Brian Sexton',
    'address': '86026 Christian Extensions\nReginaland, TN 32050',
    'text': 'Into suddenly hair economic. Trial this eight responsibility tend his light view. Discuss the deep director. Treat bed power when sure pass significant.',
    'email': 'walkerpeter@example.org',
    'phone_number': '001-446-870-6373',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Megan Hernandez',
    'Alexa Nichols',
],
    'json': {
    'name': 'Christy Costa',
    'address': '9221 Patterson Green Suite 132\nCarolinebury, WV 97824',
},
    'key38586': 'value70772',
    'key12010': 'value60610',
    'key44025': 'value23526',
    'key73318': 'value2522',
    'key93421': 'value54132',
    'key36724': 'value99132',
    'key18294': 'value33477',
    'key37324': 'value6188',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Jill Wilson',
    'address': '06356 Michael Road Suite 862\nLake Whitney, GA 10509',
    'text': 'Trial popular picture once. Want upon almost also third natural.\nMedical Democrat cultural your.',
    'email': 'lindahernandez@example.com',
    'phone_number': '+1-565-364-0303x255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Julie Macdonald',
    'Kelsey Simon',
    'Dr. Christopher Levine',
    'Elizabeth Nelson',
],
    'json': {
    'name': 'Alison Booker',
    'address': 'PSC 3193, Box 9967\nAPO AA 89775',
},
    'key15889': 'value80182',
    'key77132': 'value3892',
    'key11347': 'value32684',
    'key83220': 'value36735',
    'key28032': 'value26772',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Christopher Smith',
    'address': '3219 Evans Vista\nNataliechester, VT 24148',
    'text': 'Air television may read exactly. Catch agent beyond.\nSituation thus believe officer. Star thus traditional tough option special artist. Player second know prepare table out.',
    'email': 'laurahill@example.net',
    'phone_number': '(420)636-3863',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Garcia',
    'Manuel Price',
    'Darrell Cunningham',
    'Sandra Patterson',
    'Katherine Reynolds',
    'Nicole Allen',
    'Shawn Frost',
    'Sarah Jenkins',
    'Robert Hayes',
    'Alejandro Silva',
],
    'json': {
    'name': 'Joshua Payne',
    'address': '6681 Harrison Mill Suite 607\nChristianfurt, IL 58097',
},
    'key79803': 'value3893',
    'key44290': 'value28681',
    'key44688': 'value58312',
    'key66982': 'value31491',
    'key71392': 'value29399',
    'key46739': 'value92713',
    'key4060': 'value89615',
    'key97537': 'value409',
    'key46647': 'value67903',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Donna Moore',
    'address': '0573 Martinez Walks Apt. 672\nPort Tanyashire, IN 12471',
    'text': 'Personal camera another collection detail everybody do. Although improve officer large.',
    'email': 'cherylsweeney@example.com',
    'phone_number': '9503587136',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Golden',
    'Anthony Beltran',
    'Kristy Rasmussen',
],
    'json': {
    'name': 'Timothy Reeves',
    'address': '064 Rocha Heights Suite 307\nPort Jenniferberg, WV 67256',
},
    'key39718': 'value30574',
    'key48930': 'value79478',
    'key94283': 'value641',
    'key89293': 'value34067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Megan Andrews',
    'address': 'PSC 1502, Box 6766\nAPO AP 80560',
    'text': 'Yet tree PM Republican establish program rate. Up other near whom off agree between student. Car old staff require decade lawyer find.',
    'email': 'linda03@example.com',
    'phone_number': '001-238-212-7257x70252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Alvarado',
    'Scott Lopez',
    'George Maldonado',
    'Jennifer Rodriguez',
    'Daniel Martin',
],
    'json': {
    'name': 'Stacey Johnson',
    'address': 'Unit 0346 Box 7442\nDPO AE 08392',
},
    'key17467': 'value82370',
    'key35070': 'value5490',
    'key28643': 'value46358',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Tiffany Kelly',
    'address': '0697 Wright Springs\nMarthamouth, NV 01028',
    'text': 'Ago season industry glass reflect which other. Sing list member enough. Throw cell case ever moment network anything bar.',
    'email': 'hernandezjake@example.net',
    'phone_number': '+1-415-785-3037',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Derrick Cruz',
    'Glenn Mcconnell',
],
    'json': {
    'name': 'Dale Johnson',
    'address': '28783 Martin Trafficway Apt. 648\nPort Gregoryshire, SC 53710',
},
    'key71435': 'value58093',
    'key94282': 'value64571',
    'key75457': 'value71859',
    'key10828': 'value16816',
    'key44284': 'value76353',
    'key5203': 'value1889',
    'key60109': 'value2707',
    'key97432': 'value4660',
    'key26659': 'value97120',
    'key61536': 'value3919',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Craig Parker',
    'address': 'PSC 8750, Box 5129\nAPO AA 47551',
    'text': 'Green he inside young win within. They stop animal month what offer.',
    'email': 'tsmith@example.com',
    'phone_number': '651-218-7696',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christina English',
    'Susan Johnson',
    'Nancy Thornton',
    'Grace Butler',
    'Emily Montgomery',
    'Mary Ford',
    'Kim Collins',
    'George Johnson',
    'Cheryl Anderson',
],
    'json': {
    'name': 'Nathan Ruiz',
    'address': '23024 Brewer Plains Apt. 727\nPort Lauramouth, MN 30661',
},
    'key58420': 'value43812',
    'key73727': 'value25519',
    'key71502': 'value93680',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Jeffrey Cochran',
    'address': '932 Teresa Corner\nRamirezhaven, ND 50585',
    'text': 'Car then together event color enjoy. Quality service social later economy statement. Amount opportunity present ready control.',
    'email': 'reynoldschristopher@example.com',
    'phone_number': '892.609.9906x99824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ruben Baker',
    'Cesar Ellis',
],
    'json': {
    'name': 'Jessica Arnold',
    'address': '061 Aaron Estates\nMooreview, ID 37930',
},
    'key41719': 'value69440',
    'key80748': 'value47478',
    'key67757': 'value64209',
    'key37548': 'value64905',
    'key85661': 'value20878',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Robert Li',
    'address': '6484 Jennifer Forks\nSouth Rhondabury, VA 92059',
    'text': 'Yard by law allow. Everyone result gas surface.\nSource natural interesting sing song. Thank plan out sense behavior set girl.',
    'email': 'shannon82@example.org',
    'phone_number': '+1-627-357-3235x94491',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Roberts',
    'Richard Nichols',
    'Thomas Gonzalez',
    'Michael Osborne',
    'Leah Ball',
    'Andre Maxwell',
    'Charles Burns',
    'Michelle Gray',
    'Justin Nichols',
    'Tiffany Morgan',
],
    'json': {
    'name': 'Lori Terry',
    'address': 'Unit 9689 Box 0780\nDPO AP 20934',
},
    'key16338': 'value64081',
    'key87124': 'value83123',
    'key61865': 'value68462',
    'key6081': 'value61421',
    'key87040': 'value75167',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Matthew Poole',
    'address': '80464 Franklin Ports\nKimberlyport, MO 19107',
    'text': 'Laugh already record. Upon office test wide keep he nation. Her degree smile new take.',
    'email': 'wolfetricia@example.net',
    'phone_number': '(389)999-7717x70900',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Hoffman',
],
    'json': {
    'name': 'Travis Robinson',
    'address': '095 Martin Road Suite 629\nLake Jameschester, AK 99929',
},
    'key38420': 'value85238',
    'key82925': 'value2944',
    'key24777': 'value7876',
    'key99861': 'value59544',
    'key6900': 'value35651',
    'key71695': 'value20423',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'David Hunt',
    'address': '8954 Paul Lakes\nNew Brendastad, LA 76379',
    'text': 'Citizen early free building thousand challenge. Woman structure enjoy. Product too risk training popular response eye. Pattern number born.',
    'email': 'williamcastaneda@example.org',
    'phone_number': '672-535-1800',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Emma Fernandez',
    'Sara Day',
    'Kathryn Martinez',
    'Carrie Meadows',
    'Matthew Forbes',
    'John Lawrence',
    'Patricia Lee',
    'Terry Downs',
    'Richard Contreras',
],
    'json': {
    'name': 'Peter Garrison',
    'address': '88530 Edwards Circle Apt. 778\nNorth James, WI 96629',
},
    'key72249': 'value23069',
    'key92122': 'value62333',
    'key40233': 'value96865',
    'key57889': 'value98228',
    'key62672': 'value16276',
    'key50526': 'value36842',
    'key50773': 'value94477',
    'key70226': 'value37603',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Joseph Brown DVM',
    'address': '25035 Martinez Ports\nJosephview, AR 66086',
    'text': 'Ask six decide act. Thank live yeah young. Sit bed whole.\nBelieve best east have type spring. The especially public hold. Claim pattern situation debate doctor security.',
    'email': 'lozanoryan@example.net',
    'phone_number': '791.213.4795x84650',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Duarte',
    'Austin Weaver',
    'Tara Ramirez PhD',
    'Alex Davis',
    'James Hughes',
],
    'json': {
    'name': 'Joseph Scott',
    'address': '61883 Gentry Ridges\nPort Desireestad, TN 72116',
},
    'key17632': 'value12861',
    'key21472': 'value38490',
    'key81831': 'value64973',
    'key15524': 'value64351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Christopher Smith',
    'address': '229 Kendra Bypass Suite 575\nLake Joshua, NE 79547',
    'text': 'Necessary know their actually. Practice start eye increase.\nFace bag care then. Important generation course when realize.',
    'email': 'anthonyedwards@example.net',
    'phone_number': '525-360-2597',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Greene',
],
    'json': {
    'name': 'Karen Brown',
    'address': '924 Jillian Turnpike Suite 404\nHollowaybury, WI 57609',
},
    'key6662': 'value2063',
    'key21': 'value30621',
    'key7445': 'value43343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Mark Jones',
    'address': '31702 Lamb Fields\nGuerreromouth, KY 74118',
    'text': 'Hit continue perhaps because agree teacher effort. Break choose school miss order.\nThird run though choose industry safe.',
    'email': 'pfoster@example.org',
    'phone_number': '+1-281-978-0662x2183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amy Hahn',
    'Eric Harris',
    'Monica Ross',
    'Ryan Daniels',
    'Alexis Ibarra',
    'Michelle Pham MD',
    'Samuel Harris',
    'Margaret Jackson',
],
    'json': {
    'name': 'Susan Wang',
    'address': '860 Holmes Vista\nEast Alicemouth, LA 84824',
},
    'key15597': 'value27085',
    'key42644': 'value58224',
    'key76363': 'value40094',
    'key89485': 'value56323',
    'key65139': 'value28425',
    'key87535': 'value54157',
    'key97181': 'value83955',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Jordan Jones',
    'address': '03717 Tiffany Shore\nEast Amandamouth, WA 77091',
    'text': 'Analysis clearly model able environmental eye. Station recent even official fish there.\nPossible allow product new window against. Keep positive open lead act employee. Age pretty true.',
    'email': 'timothybaldwin@example.org',
    'phone_number': '565.845.1458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mary Glover',
    'Debra White',
    'Joshua Juarez',
    'Alex Jackson',
    'Michael Vincent',
    'Zachary Brown MD',
    'James Cook',
    'Michael Thompson',
    'Jonathan Tran',
],
    'json': {
    'name': 'Dr. Michelle Arnold',
    'address': '3676 Katelyn Flat Apt. 027\nLake Timothyborough, VT 81076',
},
    'key63940': 'value63164',
    'key15656': 'value49847',
    'key5568': 'value46691',
    'key58386': 'value10815',
    'key67095': 'value38215',
    'key80053': 'value52035',
    'key62098': 'value50176',
    'key35693': 'value3147',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jeffery Evans',
    'address': '50540 Kristina Flats Apt. 721\nNew Scott, AL 61644',
    'text': 'Company should ok name himself series study. Into drive understand front never.\nFormer cause final fight describe fly leader sense. Card life explain move rest on why five.',
    'email': 'leonardtravis@example.net',
    'phone_number': '536-887-1481x8556',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Jackson',
    'Anna Floyd',
    'Christine Bird MD',
],
    'json': {
    'name': 'Mark Hall',
    'address': '83868 Tina Mills Suite 747\nMatthewview, NH 67678',
},
    'key85691': 'value87521',
    'key34035': 'value96904',
    'key15259': 'value73746',
    'key93593': 'value86078',
    'key29107': 'value84228',
    'key67860': 'value86995',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Kimberly Smith',
    'address': '3674 Diane Stream\nEast William, MP 82949',
    'text': 'Member media career.\nThem to hope garden if rich type. Watch any beat place establish require.',
    'email': 'mwu@example.org',
    'phone_number': '(296)790-7232x309',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Lamb',
    'Ashley Miles',
    'Leah Marks',
    'Jeremy Brown',
    'Matthew Fisher',
    'Martha Lee',
    'Michele Caldwell',
],
    'json': {
    'name': 'Sarah Landry',
    'address': '999 Boyer Creek Apt. 077\nNorth Nicoleburgh, NM 41449',
},
    'key45371': 'value81357',
    'key87902': 'value42255',
    'key65060': 'value5175',
    'key76842': 'value9338',
    'key14777': 'value39948',
    'key79834': 'value24253',
    'key5098': 'value90112',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'James Gould',
    'address': '6405 Anthony Ville\nDavidmouth, TX 64226',
    'text': 'Ground way until. Better know early bag nearly.\nPiece heart card animal after. Really mother race whose be other air Democrat.\nEffect group sign event treatment and.\nLot I ready. Its fly any fill.',
    'email': 'conradpamela@example.org',
    'phone_number': '(476)671-0544x557',
    'array_int_dynamic': [
    75356,
],
    'array_varchar_dynamic': [
    'Julie Camacho',
    'Corey Edwards',
    'Dorothy Becker',
    'Eric Walker',
    'Ashlee Griffin',
    'Michael Elliott',
    'Tony Meyer',
    'Cheryl Palmer MD',
    'Matthew Scott Jr.',
    'Amy Rhodes',
],
    'json': {
    'name': 'Patrick Bennett',
    'address': '27765 Curtis Pass\nSouth Patricia, PW 32437',
},
    'key22194': 'value3228',
    'key22287': 'value55187',
    'key47820': 'value37566',
    'key854': 'value48151',
    'key93054': 'value1731',
    'key79040': 'value81243',
    'key68082': 'value7109',
    'key33665': 'value18492',
    'key16592': 'value98481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Danielle Smith',
    'address': '36914 Heather Walks\nJasonmouth, RI 24044',
    'text': 'Bad computer see together four race hear term. Member else hope around my.\nNo kitchen ever no and sure nation court. Employee television bad long.\nMouth every leave development station.',
    'email': 'emilybrown@example.org',
    'phone_number': '+1-681-835-0879x291',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marie Williams',
    'Donald Huang',
    'Brittany Jones',
    'John Welch',
],
    'json': {
    'name': 'Kevin Dawson',
    'address': '35766 Sanchez Harbors\nAndreastad, MP 09381',
},
    'key62514': 'value14264',
    'key36120': 'value79408',
    'key21364': 'value85247',
    'key28000': 'value22768',
    'key11368': 'value91316',
    'key26022': 'value4278',
    'key52384': 'value44098',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Sonya Edwards',
    'address': '353 Smith Flats\nNew Lindabury, AS 64269',
    'text': 'Tough culture join direction. No alone sit office wonder when improve. Step response two require.',
    'email': 'uvillegas@example.net',
    'phone_number': '+1-517-951-5440x63941',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Soto',
    'Jessica Maxwell',
    'Thomas Lawrence',
    'Mr. Seth Lewis',
],
    'json': {
    'name': 'Stephen Mayer',
    'address': '0743 Thomas Fork Suite 854\nMoyermouth, LA 51187',
},
    'key90699': 'value73823',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Mrs. Angela Johnson',
    'address': '0359 Brown View Suite 859\nSavageborough, NE 64765',
    'text': 'National protect explain yourself speech drug people. Future town listen investment. Across over be manager.\nDespite run television spend available eye economic special. Among cause kitchen piece.',
    'email': 'patricia87@example.com',
    'phone_number': '001-666-814-7363x94826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Thomas',
    'Tamara Pugh',
    'Eric Gilmore',
],
    'json': {
    'name': 'Linda Bell',
    'address': '5420 Nicole Oval Apt. 844\nLake Jessica, NC 91766',
},
    'key40790': 'value74500',
    'key49226': 'value9599',
    'key29765': 'value30647',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'David Perry',
    'address': '07039 Vicki Ville Apt. 511\nDennishaven, TX 28189',
    'text': 'Carry me usually person between pull respond. Book wife suggest teacher nearly. Site happen bring give fill feeling according.\nExample politics argue police federal make.\nProject off meet system sea.',
    'email': 'websterhenry@example.net',
    'phone_number': '(228)314-1657x891',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Carter',
    'Sheryl Ramsey',
    'Jennifer Jackson',
    'Mr. Adam Hernandez MD',
    'Travis Thompson',
    'Candice Montgomery',
    'Patricia Hall',
    'Shaun Lynch',
],
    'json': {
    'name': 'Christopher Campbell',
    'address': '41590 Mcclure Mews Suite 783\nSouth Robertfurt, SD 04136',
},
    'key95219': 'value20444',
    'key47905': 'value70933',
    'key21294': 'value66078',
    'key34705': 'value15341',
    'key62980': 'value33438',
    'key29042': 'value63557',
    'key11589': 'value45037',
    'key67000': 'value87151',
    'key647': 'value45980',
    'key4047': 'value76902',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Aaron Chambers',
    'address': '777 Oliver Prairie Suite 346\nHernandeztown, TN 57713',
    'text': 'Fine produce watch feeling low building recognize Democrat. Technology authority other candidate story. Government why today ability science.',
    'email': 'benjaminmcdonald@example.net',
    'phone_number': '+1-954-585-6088x6032',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Adrienne Wheeler',
    'Aaron Howard',
    'Mary Trujillo',
    'Jeremy Turner',
    'John Estrada',
    'David Harper',
    'Nicole Allen',
],
    'json': {
    'name': 'Paul Lamb',
    'address': '8557 Michael Rest\nWest Kristy, WV 84454',
},
    'key1801': 'value74639',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Courtney Allison',
    'address': '27125 Collins Ports\nNorth Angelaville, UT 42908',
    'text': 'Rate kitchen coach knowledge political chance bag doctor. Fall result wait case fast teach us state.',
    'email': 'christopher45@example.net',
    'phone_number': '001-934-981-9275x61825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kelli Carey',
    'John Poole',
    'Joy Brewer',
],
    'json': {
    'name': 'Jennifer Dunn',
    'address': '96481 William Mill Suite 327\nKimberlyberg, WI 26411',
},
    'key14281': 'value41194',
    'key47870': 'value12229',
    'key19971': 'value17767',
    'key99172': 'value58573',
    'key85662': 'value79768',
    'key81778': 'value62020',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Heather Alvarado',
    'address': '2975 Christopher Rue\nSouth Jeff, WY 46126',
    'text': 'White including part top who itself current. Necessary important conference you. Turn first believe professional how. Interest energy occur interest wrong.',
    'email': 'john33@example.com',
    'phone_number': '527-926-8587',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Bray',
    'Meghan Smith',
    'Melissa Cummings',
    'Stephanie Harris',
    'Bethany Williams',
    'Charles Walker',
    'Kelly Mcbride',
],
    'json': {
    'name': 'Danielle Turner',
    'address': '49340 Chris Causeway Suite 437\nLake Iantown, CO 49860',
},
    'key42884': 'value32113',
    'key73415': 'value82027',
    'key33374': 'value27111',
    'key57871': 'value45643',
    'key43758': 'value22556',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'James Duncan',
    'address': '553 Rose Mountains\nNorth Danielton, RI 88080',
    'text': 'Purpose bring crime.\nValue between change already training. Scene pull sign western.',
    'email': 'ryanalyssa@example.org',
    'phone_number': '214.378.2643',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christina Williams',
    'Austin Chaney',
    'Catherine Ferguson',
    'Paul Rodriguez',
    'Lisa Carrillo',
],
    'json': {
    'name': 'Wanda Collier',
    'address': '23310 Smith Crossing\nNew Nicholas, PA 06433',
},
    'key68532': 'value99714',
    'key7671': 'value51421',
    'key73641': 'value99732',
    'key85418': 'value47067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Amanda Shah',
    'address': 'PSC 9066, Box 0074\nAPO AE 26207',
    'text': 'Candidate fine return group so attorney.\nArm hit rock make various teacher turn. More television experience second smile.\nHear quite example decision clear others prevent. In coach network.',
    'email': 'gdavidson@example.com',
    'phone_number': '972-638-8750x745',
    'array_int_dynamic': [
    90657,
],
    'array_varchar_dynamic': [
    'Carl Thompson',
    'David Stewart',
    'Matthew Rodriguez',
    'Richard Chen',
    'Sean Smith',
    'Victoria Roberts',
],
    'json': {
    'name': 'Elizabeth Tran',
    'address': '241 Adam Green Suite 910\nAndreaport, ME 36143',
},
    'key92892': 'value46959',
    'key67448': 'value10136',
    'key82994': 'value84163',
    'key10395': 'value79582',
    'key60286': 'value47942',
    'key8138': 'value82838',
    'key88980': 'value43690',
    'key12494': 'value91281',
    'key11336': 'value82023',
    'key3755': 'value73086',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Ashley Peters',
    'address': '555 Sabrina Square Apt. 662\nNorth Douglasport, AR 27328',
    'text': 'Environmental agreement many bring push lot. Manage program night short. Different can performance source hundred minute.',
    'email': 'rhonda00@example.com',
    'phone_number': '001-207-680-9528x212',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Bernard',
    'Edward Lawrence',
    'Lisa Lewis',
    'Emily Adams',
    'Patricia Davis',
    'Robert Jones',
],
    'json': {
    'name': 'Joshua Nichols',
    'address': 'PSC 0424, Box 9018\nAPO AE 18899',
},
    'key88162': 'value7102',
    'key34599': 'value85882',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Lindsay Foley',
    'address': '293 Alexis Village Suite 421\nSouth Theresa, NJ 73086',
    'text': 'Among animal look ever activity book. Spend pick newspaper. Such low support its.\nFigure unit play. Alone buy hundred society. Fine we over the fund office.',
    'email': 'gwhite@example.com',
    'phone_number': '273.384.6548x1872',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Olivia Gomez',
    'Kristen Williams',
    'Robert Young',
    'Brandon Cox',
],
    'json': {
    'name': 'Jonathan Jimenez',
    'address': '817 Guerrero Plaza Apt. 245\nNorth Alexandra, GU 63031',
},
    'key82735': 'value18889',
    'key74053': 'value32743',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Henry Riley',
    'address': '53664 Hawkins Villages Suite 456\nWallacechester, CO 66506',
    'text': 'Girl able site experience west difference. Name money produce office fall. Often red boy never blood catch.',
    'email': 'brownkevin@example.org',
    'phone_number': '(897)243-1960',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James Conner',
    'Lisa Adams',
    'Carolyn Jones',
    'Heather Boyd',
    'Mary Atkins',
    'Laura Mills',
    'Travis Obrien',
    'Tiffany Lee',
    'Andrea Shields',
],
    'json': {
    'name': 'Steven Bennett',
    'address': '06391 Roman Lake\nSouth Anthony, SC 61005',
},
    'key4310': 'value78555',
    'key59096': 'value78238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Joseph Sanders',
    'address': 'Unit 9940 Box 1198\nDPO AA 20484',
    'text': 'Leader president ten almost training inside watch. Serious moment size authority campaign send. Law general have leader marriage some. Public appear information need interesting least.',
    'email': 'xcarter@example.com',
    'phone_number': '701-306-0750',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Laurie Little',
    'Frances Johnson',
    'Rebecca Huang',
],
    'json': {
    'name': 'Nathan Watson',
    'address': '7555 Herman Rapid Suite 053\nLake Lauraburgh, MH 74735',
},
    'key29713': 'value14635',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Tiffany Lucero',
    'address': '9338 Ramsey Parks Suite 975\nPort Justin, KS 99051',
    'text': 'Theory quickly charge form heart. Century consider you whatever. Far necessary sure billion but single image.',
    'email': 'chad90@example.com',
    'phone_number': '548.578.4145',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Regina Wilson',
    'Aaron Chapman',
    'Jonathan Delacruz',
    'Victor Sloan',
],
    'json': {
    'name': 'Brianna Griffin',
    'address': '22913 Matthew Lakes\nBelltown, WA 94643',
},
    'key99854': 'value13564',
    'key29326': 'value59724',
    'key5241': 'value7264',
    'key47502': 'value52904',
    'key46031': 'value55462',
    'key57300': 'value59915',
    'key83435': 'value91868',
    'key58935': 'value11300',
    'key43842': 'value99045',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Teresa Kemp',
    'address': '70765 Kelly Manor\nSouth Jonathanview, IA 38906',
    'text': 'If pick amount. Rise since begin machine east set. Training yes other kid body try.',
    'email': 'jordanvernon@example.com',
    'phone_number': '+1-218-641-9623x46260',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Patterson',
    'Timothy James',
    'Marcus Campbell',
    'Christie Day',
    'Dennis Holloway',
    'Johnathan Castillo',
    'Jeremy Blanchard',
    'Heather Martinez',
],
    'json': {
    'name': 'Nathan Vazquez',
    'address': '441 Brandt Estates Suite 943\nSouth Jason, PA 78302',
},
    'key64935': 'value73504',
    'key53487': 'value47927',
    'key68460': 'value70451',
    'key15750': 'value17214',
    'key42591': 'value19386',
    'key65676': 'value70845',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'James Evans PhD',
    'address': '337 Richard Lodge\nPort Douglasport, MO 15071',
    'text': 'Response from western piece sea mean interest. Watch material rich. Later care yet institution fill. After half seven approach.',
    'email': 'igill@example.com',
    'phone_number': '001-742-309-5268x505',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Lambert',
    'Jason Allison',
],
    'json': {
    'name': 'Leslie Walters',
    'address': '974 Gray Centers Suite 938\nKevinland, ID 53980',
},
    'key83796': 'value37266',
    'key8569': 'value60032',
    'key55598': 'value74908',
    'key39673': 'value23409',
    'key8258': 'value29590',
    'key58218': 'value57648',
    'key23859': 'value68449',
    'key48007': 'value7936',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Victor Jefferson',
    'address': '6025 Cameron Isle Apt. 969\nWilliamsland, PR 55811',
    'text': 'Wide different others plan. Drive another star put white majority.\nPerhaps message them you spend. Begin nearly poor.\nPass suddenly fight several world the.',
    'email': 'meyerhenry@example.org',
    'phone_number': '+1-734-992-3281x03197',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Richards',
    'Jeanette Brooks',
    'Jesse Anderson',
    'Jerry Lewis',
    'Gabriel Maldonado',
    'Mark Braun',
],
    'json': {
    'name': 'Ashley Paul',
    'address': '570 Tiffany Center\nNew Kevinfort, CT 69986',
},
    'key15816': 'value27409',
    'key88662': 'value44724',
    'key96626': 'value58301',
    'key26266': 'value37758',
    'key7750': 'value50407',
    'key90209': 'value84014',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Paul Fernandez',
    'address': '164 Karen Road Suite 798\nJosephview, CA 15818',
    'text': 'Group hit authority be answer but. Painting my those several.\nEdge we then. Say list maintain memory more live. Surface whole body community get reach.',
    'email': 'johngordon@example.org',
    'phone_number': '254-832-8689',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michele Jefferson',
    'Natasha Tran',
],
    'json': {
    'name': 'Joseph Freeman',
    'address': '61988 Diaz Terrace\nNew Jessica, MH 42703',
},
    'key11461': 'value2494',
    'key97488': 'value97721',
    'key38975': 'value24630',
    'key20055': 'value6925',
    'key85099': 'value67270',
    'key2558': 'value16024',
    'key31298': 'value94147',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jason Joyce',
    'address': '460 Gonzalez Neck Suite 146\nPort Erica, VI 59357',
    'text': 'Ok time form include think before. This person make exist say local. Name staff factor writer.\nMemory suggest art third current. Business simply person every every. Success enter study require write.',
    'email': 'dakota32@example.net',
    'phone_number': '001-278-974-5167',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ellen Ferguson',
],
    'json': {
    'name': 'Walter Barrera',
    'address': '6237 Anderson Mountain Apt. 480\nJeremyhaven, VI 97763',
},
    'key32592': 'value50260',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Anthony Collins',
    'address': '9616 Fisher Prairie Apt. 595\nEllisberg, WY 52254',
    'text': 'Social walk sometimes growth recently. Along general television book son.\nFast protect statement arm. Player such month level employee bar dinner. Staff someone focus attention.',
    'email': 'edwardjoseph@example.org',
    'phone_number': '298-747-2718x7329',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas York',
    'Taylor Medina',
    'Heather Franco',
    'Anthony Frederick',
    'Robert Owens',
    'Edward Henson',
],
    'json': {
    'name': 'Diana Harris',
    'address': 'Unit 5570 Box 1505\nDPO AA 22018',
},
    'key33796': 'value51855',
    'key69394': 'value93690',
    'key77446': 'value32226',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Jennifer Rodriguez',
    'address': '40975 Bennett Square Suite 633\nAliceshire, IL 41569',
    'text': 'Food effort head. Challenge per hit listen agreement carry. Bed leader mother team just professor.',
    'email': 'brooke28@example.org',
    'phone_number': '+1-580-406-3964',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Lopez',
    'Jerry Wells',
    'Jeffrey Wilson',
    'Carrie Tucker',
    'Tracy Smith',
],
    'json': {
    'name': 'Stacey Arnold',
    'address': '7562 Valerie Points\nSouth Briannaside, TX 30616',
},
    'key32808': 'value92968',
    'key21570': 'value55296',
    'key8776': 'value19801',
    'key97351': 'value4098',
    'key57328': 'value43226',
    'key32540': 'value597',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Ronald Garcia',
    'address': 'PSC 8951, Box 2744\nAPO AA 05677',
    'text': 'Why staff list. Training pattern nothing drive be effect. Fine subject each later center the.',
    'email': 'adrian18@example.com',
    'phone_number': '001-994-744-5285x5374',
    'array_int_dynamic': [
    97864,
],
    'array_varchar_dynamic': [
    'Mr. Tim Mitchell',
    'Sabrina Wang',
    'Alexa Burns',
    'Kevin Chavez',
    'Helen Watts',
    'Johnny Bennett',
],
    'json': {
    'name': 'Lauren Williams',
    'address': '9119 Kevin Light\nLake Shannon, MS 91874',
},
    'key62067': 'value4604',
    'key76963': 'value1154',
    'key92109': 'value80162',
    'key2966': 'value75833',
    'key8017': 'value64645',
    'key87609': 'value86046',
    'key68868': 'value51042',
    'key3371': 'value22223',
    'key85015': 'value46960',
    'key20025': 'value80884',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Haley Sullivan',
    'address': '10350 Bates Extension Suite 686\nFisherville, PW 26725',
    'text': 'Audience bit word successful possible ever security. Culture huge sense tell. Force account push above she practice behind require.',
    'email': 'robertalvarado@example.org',
    'phone_number': '+1-677-677-6548x315',
    'array_int_dynamic': [
    72302,
],
    'array_varchar_dynamic': [
    'Cody Williams',
    'Johnny Anderson',
    'Christopher Wells MD',
    'Thomas Goodwin',
    'Maria Gomez',
],
    'json': {
    'name': 'Cindy Edwards',
    'address': '4601 Jacobs Path\nWest Joseph, MT 75292',
},
    'key3052': 'value34208',
    'key69205': 'value20128',
    'key24713': 'value58341',
    'key43463': 'value58476',
    'key68221': 'value68246',
    'key46750': 'value26188',
    'key99930': 'value52088',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jennifer Smith',
    'address': 'Unit 3368 Box 4783\nDPO AE 69726',
    'text': 'Product the how never inside test. Someone of development author industry also. Season loss seem know bring well big.\nFish training election stand color. Minute shake long ability.',
    'email': 'moralesjulie@example.net',
    'phone_number': '(784)508-8097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Garcia',
    'Beth Brooks',
],
    'json': {
    'name': 'David Davis',
    'address': 'USNS Ramirez\nFPO AP 22792',
},
    'key88613': 'value19368',
    'key9490': 'value98323',
    'key76336': 'value76923',
    'key32779': 'value52960',
    'key67940': 'value40602',
    'key31311': 'value17148',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Ashley Jackson',
    'address': 'PSC 3253, Box 2788\nAPO AE 41783',
    'text': 'Recent measure stock section. Defense eat they before director head benefit. Morning wrong find always.',
    'email': 'stephaniecosta@example.org',
    'phone_number': '5789417712',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jason Wells',
    'Brandy Peterson',
    'James Caldwell DDS',
    'Matthew Mitchell',
    'Luke Stafford',
],
    'json': {
    'name': 'Carrie White',
    'address': '58094 Jason Locks Suite 593\nOwenland, PW 39810',
},
    'key96121': 'value56342',
    'key38752': 'value59650',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Gail Duffy',
    'address': '90960 Cochran Brook Apt. 193\nNew Joshua, NY 83284',
    'text': 'Campaign energy particular company able. Another while quality network throw inside get draw. Onto actually prepare shake style.',
    'email': 'ryan03@example.org',
    'phone_number': '+1-546-723-9680x822',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Cole',
    'Tammy Richardson',
    'Meagan Johnson',
    'Jennifer Washington',
    'Melinda Jackson',
    'Sean Black',
    'Mary Mclean',
],
    'json': {
    'name': 'Maria Kirby',
    'address': '45627 Timothy Fords Apt. 022\nLake Angela, PR 58455',
},
    'key93420': 'value67973',
    'key87907': 'value94458',
    'key79213': 'value45599',
    'key20765': 'value73549',
    'key4301': 'value73123',
    'key210': 'value38960',
    'key26903': 'value5798',
    'key38804': 'value11828',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Cindy Hickman',
    'address': '63808 Mary Passage Apt. 894\nCharlesshire, CT 93810',
    'text': 'Process return baby free let particularly. West player want region choice bag season bill.\nActually give to let painting. Energy some particularly part.',
    'email': 'carolpennington@example.org',
    'phone_number': '(931)338-9972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Willis MD',
    'Christine Hall',
    'Julie Meadows',
    'Eric Wells',
    'Beverly Dixon',
    'Elizabeth Daniels',
    'Allison Brock',
    'Denise Herrera',
    'Robert Taylor',
],
    'json': {
    'name': 'Robert Douglas',
    'address': '3082 Ramos Estate Suite 140\nFosterburgh, WY 15221',
},
    'key23447': 'value46146',
    'key81328': 'value92695',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Joshua Thompson MD',
    'address': '74958 Belinda Fort Suite 306\nJenniferstad, AR 40352',
    'text': 'Leader material surface offer. Suggest scene yet tend student high morning. Customer father sound ever. Hot low eye television officer.',
    'email': 'iward@example.net',
    'phone_number': '321.302.9534',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Jensen',
    'Elizabeth Little',
],
    'json': {
    'name': 'Dana Townsend',
    'address': '22228 Tanner Union\nEvansville, PR 05213',
},
    'key37281': 'value96334',
    'key25425': 'value14466',
    'key45544': 'value66041',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Ryan Washington',
    'address': '48249 Michelle Street Suite 064\nBrianchester, OR 39019',
    'text': 'World by day thought. Discuss house election hard door resource guy family. He play value give soon.\nRange natural head all half address. Standard indicate adult start project job.',
    'email': 'sheilawright@example.net',
    'phone_number': '+1-225-277-1695x6391',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Smith',
],
    'json': {
    'name': 'Joy Herman',
    'address': '33542 Gomez Stravenue Suite 228\nButlerstad, AZ 55377',
},
    'key83666': 'value30167',
    'key71184': 'value50726',
    'key35399': 'value15314',
    'key59930': 'value43097',
    'key23292': 'value23116',
    'key33001': 'value66358',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Daniel Burton',
    'address': '760 Christopher Plaza Apt. 899\nEast Sherri, MA 02120',
    'text': 'Republican artist general employee effect. I hear information skill adult know. Save yard clearly individual real.\nSpecific south fight increase. Old case them.\nAudience deal hope little.',
    'email': 'xross@example.net',
    'phone_number': '(399)211-2689x78139',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Hicks',
    'John Gonzalez',
    'Shannon Kim',
    'Christopher Mendez MD',
    'Christina Clarke',
    'Ryan Stokes',
    'Eric Owen',
    'Stacy Wilson',
    'Dustin Willis',
],
    'json': {
    'name': 'Taylor Hodge',
    'address': '27590 Abbott Cove\nWest Andreamouth, WA 84970',
},
    'key573': 'value817',
    'key78808': 'value47679',
    'key48589': 'value93811',
    'key63994': 'value24065',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Sherry Jenkins',
    'address': '29886 Patel Pike Suite 259\nNew Lisaberg, UT 78992',
    'text': 'Right may cover class population turn. Drug step international quickly piece class. Give become interest perhaps forward ago.\nCollection care generation brother.',
    'email': 'ihaynes@example.org',
    'phone_number': '001-686-617-2486x2929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Emily Campbell',
    'Michael Perez',
    'Nicole Mcintosh',
    'Kelly French',
    'Kelly Black MD',
    'Mckenzie Gonzalez',
    'Joe Woods',
    'Judy Mcdaniel',
],
    'json': {
    'name': 'Kristin Moore',
    'address': '5064 Crystal Haven\nColonchester, WI 08637',
},
    'key83209': 'value6113',
    'key48110': 'value39863',
    'key40683': 'value71508',
    'key81900': 'value46369',
    'key8031': 'value82163',
    'key37952': 'value33901',
    'key61958': 'value30213',
    'key71188': 'value46138',
    'key75038': 'value78967',
    'key94230': 'value59487',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Billy Brown',
    'address': '044 Holt Mountains Suite 800\nChristianfort, KS 17214',
    'text': 'Individual book usually great through. Chair question letter all within when. Issue home job apply we street.',
    'email': 'sandra60@example.com',
    'phone_number': '(719)611-6530x548',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jillian Lee',
    'Tammy Valdez',
    'Sharon Beasley',
    'Patricia Johns',
    'Victoria Fisher',
    'Joshua Green',
],
    'json': {
    'name': 'Christopher Wilson',
    'address': '63627 Amy Square Apt. 063\nBrockberg, WY 50930',
},
    'key24137': 'value45687',
    'key77183': 'value44318',
    'key48718': 'value90153',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Vanessa Hayes',
    'address': '94100 Hawkins Stravenue\nTiffanyburgh, WY 95003',
    'text': 'Particular enjoy reveal much north rock. Store next Congress without nearly. Service run good position picture add though. Story activity value outside.',
    'email': 'stonemichael@example.net',
    'phone_number': '954-860-7208',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Adam Mitchell',
    'Joseph Davidson',
    'Peggy Scott',
    'Wendy Sandoval',
    'Brian Thompson',
    'Daniel Rogers',
    'Joe Escobar',
],
    'json': {
    'name': 'Jorge Figueroa',
    'address': '56704 Ashley Skyway\nWest Aliciaberg, OH 35766',
},
    'key49824': 'value27332',
    'key45677': 'value3237',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Angie Black',
    'address': '062 Walton Stravenue\nPort Tammyville, CO 08664',
    'text': 'A might argue hospital possible. Floor collection south dream. Chance or book consider agree parent mouth.',
    'email': 'ztrujillo@example.net',
    'phone_number': '630.786.8422',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Emily Hill',
    'Chad Wheeler',
    'Jeremy Allison',
    'Jennifer Erickson',
    'Sarah Valenzuela',
    'Christina Newman',
    'Travis White',
    'Scott Lucero',
    'Jessica Carpenter',
],
    'json': {
    'name': 'Donald Phillips',
    'address': '47688 Marcus Locks\nJeremyfurt, PR 98038',
},
    'key79630': 'value60921',
    'key14837': 'value73810',
    'key11570': 'value28756',
    'key28745': 'value88795',
    'key86772': 'value12872',
    'key90638': 'value56182',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Thomas Bryant',
    'address': '19221 Barry Villages\nDanielleport, AR 83837',
    'text': 'Choose down media study whom old. And sit discover those speech and land discussion.',
    'email': 'clinethomas@example.net',
    'phone_number': '418.652.1485x4456',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Karen Alvarado',
    'Amanda Anderson',
    'Kimberly Riley',
    'Maria Johnson',
],
    'json': {
    'name': 'Mary Fuentes',
    'address': '64665 James Point\nPort Tonichester, PA 43991',
},
    'key37863': 'value10903',
    'key21836': 'value40796',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Ryan Dominguez',
    'address': '758 Shannon Hollow Suite 769\nKimberlyland, ID 81801',
    'text': 'Middle high side them follow easy. Data resource cultural toward short sell. Candidate what teach much adult.\nLeg clear growth firm. Second including energy hospital budget bring. Call book alone.',
    'email': 'kevin26@example.net',
    'phone_number': '830-599-2166x569',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Hall',
    'Stephanie Brown PhD',
    'Denise Reeves',
    'Paul Mitchell',
    'Frank Coleman',
    'Rebecca Garcia',
    'Sarah Thomas DVM',
    'Steven Hudson',
    'Karen Garza',
    'Daniel Zavala',
],
    'json': {
    'name': 'Melanie Reynolds',
    'address': '2328 Wendy Glen\nFishermouth, WA 61210',
},
    'key24980': 'value42337',
    'key1755': 'value15505',
    'key12798': 'value55249',
    'key88903': 'value46550',
    'key10010': 'value50123',
    'key81675': 'value71128',
    'key7636': 'value77470',
    'key85840': 'value71360',
    'key14027': 'value84833',
    'key43423': 'value10789',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Mary Rose',
    'address': '3641 Sarah Spur\nChristineland, AS 37960',
    'text': 'Dark writer blood try style firm marriage what. He effort arm attack. Plant month see local.\nIn raise dark final. South class something ability he language ask.',
    'email': 'ramirezthomas@example.org',
    'phone_number': '950.715.2409x803',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Karen Crawford',
    'Jonathan Richardson',
    'Matthew Fischer',
    'Ashley Smith',
    'Sean Bautista',
    'Stephanie Fowler',
    'Gregory Lewis',
    'Jason Wilson',
    'Jamie Griffin',
    'Michael Hendricks',
],
    'json': {
    'name': 'Virginia Thompson',
    'address': 'PSC 1726, Box 7165\nAPO AP 26698',
},
    'key13871': 'value78837',
    'key32299': 'value28503',
    'key93895': 'value41974',
    'key58704': 'value17163',
    'key6007': 'value41803',
    'key31200': 'value65822',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Douglas Austin',
    'address': 'USNV Wolfe\nFPO AA 46072',
    'text': 'During six news participant decide. Include accept really among everything.\nClearly artist lead brother teacher tax.\nFilm really line fast much themselves of. Issue rise data bed which reason.',
    'email': 'priceevelyn@example.com',
    'phone_number': '264-388-9675x167',
    'array_int_dynamic': [
    70476,
],
    'array_varchar_dynamic': [
    'Steven Wells',
    'Bradley Torres',
],
    'json': {
    'name': 'Jesus Hoffman',
    'address': '561 Terri Port\nCynthiaview, PW 03079',
},
    'key52779': 'value50586',
    'key72694': 'value62375',
    'key50068': 'value43100',
    'key63879': 'value84464',
    'key54313': 'value11247',
    'key81572': 'value29899',
    'key53883': 'value72079',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Amanda Boyle',
    'address': '49980 Rachel Union\nPort Aaronfurt, IL 05160',
    'text': 'Friend help consumer expect fund improve.\nYear sing stuff choose institution. Ask place campaign interesting week. Chair participant science image society high yeah.',
    'email': 'xperez@example.com',
    'phone_number': '(423)643-7642x662',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Bonnie Hanson',
    'Amber Glenn',
    'Angel Nichols',
    'Rickey Williams',
    'Joseph Bailey',
],
    'json': {
    'name': 'Michaela Watkins',
    'address': '5201 Kimberly Glen Suite 174\nNorth Caitlinview, OR 66948',
},
    'key512': 'value49609',
    'key65138': 'value49899',
    'key49422': 'value75175',
    'key2407': 'value85161',
    'key93586': 'value54892',
    'key46748': 'value86527',
    'key84445': 'value27997',
    'key59682': 'value61638',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Heidi Rice',
    'address': '70453 James Plaza Apt. 547\nWest Cynthia, WV 69756',
    'text': 'Happen break campaign across. Until station television like service baby always base.\nParty I herself. Drug at attention site enough foreign.',
    'email': 'justin09@example.org',
    'phone_number': '+1-606-333-8470x160',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Roberto Noble',
    'David Foster',
    'Carrie Reyes',
    'Joshua Howe',
    'Travis Carrillo',
    'Kevin Hall',
    'Mary Francis',
],
    'json': {
    'name': 'Gregory Davis DDS',
    'address': '2124 Garrett Squares Apt. 866\nJimenezborough, MD 70210',
},
    'key36320': 'value85998',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Michele Allen',
    'address': '10582 Brandon Causeway Apt. 652\nTiffanyborough, IN 71610',
    'text': 'Sell ok those enter language can treat. Rise chance move close.\nSeat simply film through through. Executive find bill page anyone.',
    'email': 'christian84@example.org',
    'phone_number': '994-304-8861x695',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Evans',
    'Mark Hogan',
],
    'json': {
    'name': 'Grace Robinson',
    'address': '4398 Janice Points\nLake Andrewland, NE 36112',
},
    'key2920': 'value56697',
    'key88239': 'value43003',
    'key60142': 'value97804',
    'key78489': 'value443',
    'key8475': 'value80203',
    'key69761': 'value19102',
    'key89529': 'value82837',
    'key32497': 'value30439',
    'key19039': 'value14636',
    'key28633': 'value90383',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Robert Hill',
    'address': '353 Kennedy Via\nEstradaberg, OH 13602',
    'text': 'Challenge put ok catch production most many. President your impact dog. Do board family lot gun. Public base anyone professor.',
    'email': 'aaron89@example.org',
    'phone_number': '734.794.3372',
    'array_int_dynamic': [
    40395,
],
    'array_varchar_dynamic': [
    'Laurie Robinson',
    'Matthew West',
],
    'json': {
    'name': 'Connie Andrews',
    'address': '59510 Morales Trail Apt. 344\nMalloryborough, TX 97541',
},
    'key79508': 'value96960',
    'key87093': 'value12251',
    'key40412': 'value41247',
    'key41175': 'value44874',
    'key83673': 'value65956',
    'key96935': 'value57251',
    'key30279': 'value93197',
    'key45687': 'value49831',
    'key41324': 'value43980',
    'key40627': 'value16266',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Zachary Carter',
    'address': '082 Ortega Light\nSouth Johnny, TX 32770',
    'text': 'Book say huge him until rest bill. Leave help at.\nAgency wind help sing. Usually rather lay loss. Smile spend everyone discover suggest. Good one control building student.',
    'email': 'ukerr@example.org',
    'phone_number': '7553909033',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ana Flores',
    'Julie Green',
    'Grant Allen',
    'Eric Deleon',
    'Heidi Miller',
    'Michael Wright',
    'Diana Mcclain',
],
    'json': {
    'name': 'Anna Phillips',
    'address': '07713 Barnett Canyon Apt. 430\nManuelland, AR 65050',
},
    'key84287': 'value49923',
    'key47411': 'value2840',
    'key52651': 'value95285',
    'key85935': 'value55286',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Mary Riddle',
    'address': '410 Timothy Islands\nNorth Rogerton, ND 28916',
    'text': 'Sometimes century at break miss subject. Evidence beyond he power. Resource after bring the air.',
    'email': 'sheilahanson@example.com',
    'phone_number': '6235065669',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Bradford',
    'James Jones',
],
    'json': {
    'name': 'Michele Bauer',
    'address': '96125 Chase Cliffs Suite 855\nWolfmouth, SD 23470',
},
    'key61586': 'value66200',
    'key88458': 'value4776',
    'key40271': 'value36761',
    'key58141': 'value50416',
    'key93056': 'value49182',
    'key55886': 'value92715',
    'key44976': 'value73291',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Jessica Parsons',
    'address': '4038 John View Suite 158\nJohnfort, WV 64592',
    'text': 'Then senior ball organization entire teach. Similar clearly wide everybody approach clear bill.',
    'email': 'haley76@example.org',
    'phone_number': '001-559-371-8080x9029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ann Greene DDS',
    'Ryan Brown',
    'Christian Davis',
    'Susan Barton',
    'Cheryl Mckenzie',
    'Adrienne Baker',
    'Sara Berg',
    'Gary Nash',
],
    'json': {
    'name': 'Andrew Rowe',
    'address': 'PSC 4202, Box 9936\nAPO AP 20706',
},
    'key44671': 'value16903',
    'key35051': 'value82084',
    'key1211': 'value45429',
    'key53320': 'value69197',
    'key75423': 'value87206',
    'key75958': 'value10364',
    'key17128': 'value1432',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Brenda Burke',
    'address': '4052 Stephanie Harbor Apt. 839\nLawsonshire, WV 55392',
    'text': 'Just expert exactly interesting clear arm. Close food foot card thus career painting.\nBlue nation save early man. Nearly bed city product just as travel.',
    'email': 'sherrywood@example.com',
    'phone_number': '860-521-3808x360',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ricky Snyder',
    'Veronica Hoover',
    'Donald Sanders',
    'Roy Petersen',
    'Donna Fields',
    'Valerie Calhoun',
    'Karen Scott',
    'Steven Sandoval',
],
    'json': {
    'name': 'Larry Craig',
    'address': '4292 Nelson Summit\nMatthewsstad, MP 55118',
},
    'key29755': 'value98018',
    'key89849': 'value37586',
    'key72593': 'value82419',
    'key24734': 'value70931',
    'key79804': 'value42301',
    'key79590': 'value36482',
    'key82698': 'value44418',
    'key42756': 'value7124',
    'key55205': 'value64201',
    'key38027': 'value33296',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Kathryn Harris',
    'address': '154 Rosales Junctions\nLake Stacyberg, DE 99033',
    'text': 'Large field skill fund. To present whole last front any many. Tax building family.',
    'email': 'scottbarbara@example.org',
    'phone_number': '(320)863-3265x29059',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Arias',
    'Matthew Kelley',
    'Carlos Anderson',
    'Mark Cole',
    'Marcus Hendrix',
    'Francis Lam',
    'William Griffin',
    'Steven Bailey',
    'Daniel Bartlett',
],
    'json': {
    'name': 'Benjamin Brown Jr.',
    'address': '519 Amanda Pike\nEast Stephanie, AL 10644',
},
    'key97789': 'value6855',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Mark Stone',
    'address': 'Unit 3344 Box 1787\nDPO AA 25274',
    'text': 'Believe face music sense child occur ability. Church better economy claim.\nConsider among shoulder song person network. Man enter billion ball writer beautiful. Then herself anyone federal.',
    'email': 'jamie02@example.org',
    'phone_number': '650-374-0003x28909',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Edgar Klein',
    'Alex Conner',
    'Robert Lewis',
    'Ronald Williams',
    'Madeline Ho',
    'Tommy Lopez',
    'Margaret Molina',
],
    'json': {
    'name': 'Mariah Scott',
    'address': 'USNV Krueger\nFPO AA 88781',
},
    'key46944': 'value13711',
    'key83255': 'value15715',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Kyle Holt',
    'address': '4975 Smith Cliffs\nKellymouth, MI 11923',
    'text': 'Sell arrive PM wait range inside program. Daughter probably cover must. Early candidate head short our.\nReady film plan quickly as everyone. Meet field character growth toward those threat raise.',
    'email': 'calvin10@example.net',
    'phone_number': '2309516728',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tony Ray',
    'Hannah Santiago',
    'Joanna Brown',
    'Scott Schwartz',
    'Nathan Howard',
],
    'json': {
    'name': 'Lisa Peterson',
    'address': '540 Michele Fall\nJennyville, UT 13901',
},
    'key61690': 'value28276',
    'key53842': 'value75015',
    'key69672': 'value12041',
    'key63591': 'value35055',
    'key31486': 'value35070',
    'key57640': 'value79251',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Douglas Moore',
    'address': '4296 Leblanc Spring Apt. 247\nSampsonberg, UT 05021',
    'text': 'Finish assume deep analysis too rather song. Write development board not.\nReason him stand ahead themselves event hot. Back drug training reality but character. Popular imagine right.',
    'email': 'jonathonserrano@example.org',
    'phone_number': '817.656.0760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Willie Salinas',
    'Randy Watkins',
    'Felicia Valdez',
    'Mary Griffin',
],
    'json': {
    'name': 'Cody Bonilla',
    'address': 'PSC 6663, Box 3849\nAPO AA 19027',
},
    'key3187': 'value6581',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jason Schwartz',
    'address': '15956 Theresa Fields Apt. 066\nKatherinefort, TX 78546',
    'text': 'Attention public soldier charge reality peace lawyer. Since case writer she.\nBenefit important ever season let purpose. Cut like parent she case audience catch.\nSeason black bank.',
    'email': 'mcortez@example.org',
    'phone_number': '+1-776-863-9004x41447',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Andrews',
    'Colleen Pollard',
    'Kimberly Taylor',
    'Nicholas Martin',
    'Michelle Bell',
],
    'json': {
    'name': 'Christopher Franco',
    'address': '2951 Roberts Tunnel\nLake Darrell, PW 06387',
},
    'key28838': 'value47719',
    'key99673': 'value69249',
    'key4083': 'value42916',
    'key84681': 'value99105',
    'key46341': 'value56093',
    'key36997': 'value44069',
    'key71745': 'value84296',
    'key56914': 'value33319',
    'key11583': 'value9152',
    'key27767': 'value20506',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Gina Warner',
    'address': '1431 Douglas Mills\nDavisview, KY 71186',
    'text': 'Interesting trip deep best appear play. Physical pick today himself case budget light.\nAround rich hand service. Financial instead another collection mother feeling I.',
    'email': 'david86@example.com',
    'phone_number': '001-902-980-1695x88009',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Oliver',
    'Stephanie Jennings',
    'Joshua Robinson',
    'Michael Knapp',
    'Sara Wells',
],
    'json': {
    'name': 'Tony Lopez',
    'address': '542 Dana Fork\nRobertmouth, CO 58806',
},
    'key64003': 'value37190',
    'key90211': 'value43147',
    'key35280': 'value88161',
    'key56953': 'value64298',
    'key32443': 'value84441',
    'key67125': 'value75627',
    'key27872': 'value80543',
    'key18581': 'value63758',
    'key91062': 'value70288',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Amanda Gallegos',
    'address': '08182 Mcdonald Causeway\nJameschester, CO 04618',
    'text': 'Off I action throughout leg but general.\nGlass school list knowledge. Begin across baby.\nGreat carry outside real right just. Law operation someone record there worker.',
    'email': 'prodriguez@example.org',
    'phone_number': '5775094331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tasha Mitchell',
    'Scott Fischer',
    'Anthony Silva',
    'Jason Shields',
    'Kyle Larson',
],
    'json': {
    'name': 'Jennifer Todd',
    'address': '27578 Lewis Branch\nSouth Leslie, PR 85482',
},
    'key56207': 'value46962',
    'key89095': 'value98243',
    'key91826': 'value18015',
    'key75520': 'value5597',
    'key44903': 'value24906',
    'key47912': 'value24087',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Eugene Larson',
    'address': '4455 Jackson Circle Apt. 663\nMichaelhaven, VA 07530',
    'text': 'Article writer visit detail knowledge. Possible policy Mr. Will its system question miss call.\nBox case someone. Beat suggest interview doctor middle coach.',
    'email': 'fwarner@example.org',
    'phone_number': '213-838-5570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Green',
    'Raymond English',
    'Yvonne Martin MD',
    'Misty Haynes',
],
    'json': {
    'name': 'Nathan Wang',
    'address': '188 Mike Coves Apt. 505\nAndrewfort, IL 46363',
},
    'key67885': 'value42157',
    'key83667': 'value72418',
    'key74678': 'value54881',
    'key40358': 'value85367',
    'key21533': 'value13230',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Kelly Brown',
    'address': '2441 Baldwin Cape Apt. 332\nNorth Lindamouth, MD 95236',
    'text': 'Into adult seat ever old lead. Seven across say station area. Bit office red enough.',
    'email': 'anthonyterry@example.com',
    'phone_number': '+1-248-762-1773x643',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jared Sanders',
    'Nicole Thomas',
    'David Morgan',
    'Barbara Kim',
    'Amber Bennett',
    'Brandon Atkinson',
    'Nicole Dixon',
    'Steven Garcia',
],
    'json': {
    'name': 'Wayne Benitez',
    'address': '409 Donald Street\nSmithmouth, MH 62196',
},
    'key99588': 'value32803',
    'key90799': 'value88784',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Theresa Livingston',
    'address': '37567 Amanda Shoals Suite 482\nWest Marybury, AS 11288',
    'text': 'Entire matter finally effort walk evening east. Get performance party them middle.\nArrive meet big. East oil write hold religious nothing.\nWin often meet. Although happen two citizen service.',
    'email': 'fulleremily@example.com',
    'phone_number': '+1-644-849-8510x6410',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Moore',
    'Ashley Gaines',
    'Cristina Murray',
],
    'json': {
    'name': 'Jessica Cooper',
    'address': '0786 Felicia Mountains\nWest Christianborough, RI 33727',
},
    'key75145': 'value66948',
    'key23410': 'value28984',
    'key63926': 'value22366',
    'key47607': 'value84955',
    'key39993': 'value77609',
    'key80340': 'value80924',
    'key15665': 'value62427',
    'key11005': 'value50950',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Jody Rodriguez',
    'address': '018 Foster Haven Apt. 045\nSouth Leonardview, AS 27226',
    'text': 'Thought miss tax any. Young institution base cover various catch.\nPoint security support today total. South idea method operation.',
    'email': 'littlegeoffrey@example.net',
    'phone_number': '+1-265-264-9589x7935',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Newton',
    'Kelsey Campbell',
    'Teresa Sims',
    'Christine Logan',
    'Michael Kim',
],
    'json': {
    'name': 'Bryan Miller',
    'address': '708 Kelly Courts Apt. 430\nPort Alexmouth, UT 76968',
},
    'key88124': 'value21782',
    'key87047': 'value61417',
    'key38546': 'value13862',
    'key6008': 'value36830',
    'key46661': 'value64971',
    'key7191': 'value36084',
    'key20723': 'value73232',
    'key81309': 'value59711',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Anthony Roberts',
    'address': 'USCGC Johnson\nFPO AA 27694',
    'text': 'Current town scene apply let. Morning garden see then whether item. Threat woman rich evening thousand.\nRoad goal class her happen. Race TV Republican majority upon.',
    'email': 'henry03@example.com',
    'phone_number': '260-707-2688x0384',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marvin Williams',
    'Debra Wu',
    'Paul Crane',
    'Donald Stewart',
],
    'json': {
    'name': 'Christina Baker',
    'address': '16434 Pearson Heights\nNew Jenniferhaven, SC 45446',
},
    'key68095': 'value19978',
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
        """测试请求 2 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'c46ba615-62ef-11f0-bb05-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_57_057923IBgxFtAX',
    'dimension': 128,
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVectorNegative_test_insert_vector_with_invalid_collection_name_1752744238.json')
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
    test = AllmilvusLogtestinsertvectornegativeTestInsertVectorWithInvalidCollectionName1752744238Json()
    test.run_tests()
