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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752744939_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752744939.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid100AndUid1001752744939Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752744939.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752744939.json"
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
    'RequestId': '5fe82590-62f1-11f0-863e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_27_417398NdoOYLAp',
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
    'RequestId': '630867e5-62f1-11f0-842d-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_27_417398NdoOYLAp',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Maria Atkins',
    'address': '2806 Salazar Plaza Apt. 258\nNew Samantha, LA 48084',
    'text': 'Color building worry different dream impact among. Base side employee rise.\nSomebody attention center design most involve. Serious break coach career sit feeling entire.\nCover mention a plan your.',
    'email': 'kchen@example.org',
    'phone_number': '509-942-5017',
    'array_int_dynamic': [
    80316,
],
    'array_varchar_dynamic': [
    'William White',
    'Michele Martinez',
    'Raymond Rodriguez',
    'Megan Griffin',
],
    'json': {
    'name': 'Elizabeth Blake',
    'address': '49538 Avery Hill\nShannonfort, NM 90272',
},
    'key33448': 'value39464',
    'key95630': 'value72696',
    'key44284': 'value38208',
    'key54572': 'value83147',
    'key1012': 'value76294',
    'key55730': 'value37502',
    'key35198': 'value13991',
    'key44458': 'value6383',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Amy Wallace',
    'address': '446 Fitzgerald Club Apt. 231\nWest Christopher, CO 27943',
    'text': 'Organization evidence address environmental. Person ten involve road listen town reach age.',
    'email': 'lunalynn@example.org',
    'phone_number': '415.587.4582x7960',
    'array_int_dynamic': [
    36979,
],
    'array_varchar_dynamic': [
    'Doris Bryant',
    'Jessica Wilson',
    'Samantha Gonzalez',
    'Christine Morgan',
    'Chelsea Ross',
    'Derek Black',
    'Dylan Young MD',
    'Kimberly Brown',
    'Philip Hawkins',
    'Dr. Cheryl Blackburn',
],
    'json': {
    'name': 'James Farrell',
    'address': '1290 Miller Forges Suite 168\nReginaldborough, AK 14226',
},
    'key42328': 'value79601',
    'key97460': 'value46745',
    'key24721': 'value2505',
    'key18567': 'value84643',
    'key38647': 'value6092',
    'key80638': 'value67414',
    'key79465': 'value19021',
    'key35035': 'value36812',
    'key1242': 'value65826',
    'key18052': 'value54346',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Joseph Mckinney',
    'address': '32983 Steven Lock Suite 624\nSmithmouth, CA 09170',
    'text': 'Major first learn senior state agent cultural. Price mission billion bar building up.',
    'email': 'ncunningham@example.com',
    'phone_number': '397.584.0185x95791',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amy Mckee',
    'Randy Smith',
    'Michael Lee',
    'Louis Porter',
],
    'json': {
    'name': 'David Key',
    'address': '0128 Richard Rapids\nEast Jessica, OK 74188',
},
    'key62456': 'value78907',
    'key59649': 'value85914',
    'key51163': 'value24394',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'David Estrada',
    'address': '99251 Patrick Extension Suite 535\nNorth Williamville, MI 14804',
    'text': 'Region the capital report help. Grow care as food weight common its. Society agency wish character parent.\nWorld this cause painting. Explain total long never myself society budget.',
    'email': 'hbutler@example.com',
    'phone_number': '477-225-0106',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Timothy Decker MD',
    'Cassandra Lee',
    'Danielle Gray',
    'Christopher Knight',
    'Matthew Walker',
    'Robert Torres',
],
    'json': {
    'name': 'Stephanie Wilson',
    'address': '32968 Gutierrez Crossing\nSchultzburgh, MA 02642',
},
    'key96900': 'value87913',
    'key88107': 'value58656',
    'key85970': 'value15989',
    'key62749': 'value39602',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Mark Thompson',
    'address': '1662 Munoz Summit Apt. 806\nSouth Ianside, PW 12881',
    'text': 'Central probably most. Month reflect figure paper.\nThese prepare heavy write identify rise. High although chance heart my them. Factor manage threat real author.',
    'email': 'romerokeith@example.org',
    'phone_number': '895.644.3424x716',
    'array_int_dynamic': [
    80043,
],
    'array_varchar_dynamic': [
    'Jennifer Blackwell',
    'Donna Delgado',
],
    'json': {
    'name': 'Gina Weber',
    'address': '708 Mullen Camp Suite 856\nHuberborough, NJ 37928',
},
    'key57594': 'value1279',
    'key30359': 'value56045',
    'key40176': 'value93134',
    'key38551': 'value69691',
    'key29884': 'value36190',
    'key12228': 'value59191',
    'key45905': 'value7680',
    'key27909': 'value16834',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Andrea Thompson',
    'address': '66239 Fowler Turnpike\nNorth Lorifurt, NM 86428',
    'text': 'According TV machine often nearly sign physical. Data traditional process or house.',
    'email': 'louis82@example.org',
    'phone_number': '785-775-3957x525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Wilkins',
    'Justin Alexander',
    'Jason Morrison',
    'Stacy Lambert',
    'Deborah Williams',
    'Jeffrey Romero',
    'Jared Dalton',
    'Paul Spence',
    'Cathy Hebert',
    'Taylor Harmon',
],
    'json': {
    'name': 'Darlene Schultz',
    'address': 'PSC 4535, Box 7427\nAPO AP 93569',
},
    'key11263': 'value51404',
    'key7595': 'value79988',
    'key26137': 'value72903',
    'key51678': 'value33316',
    'key78017': 'value97075',
    'key36426': 'value54986',
    'key8639': 'value94633',
    'key56200': 'value8159',
    'key2373': 'value61297',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Michelle Downs',
    'address': '206 Cummings Station Apt. 253\nSnyderstad, MA 63793',
    'text': 'Consider boy deep high. Even yourself at large right realize.\nDaughter answer both girl into.\nKnow pressure prevent history allow. Investment good hotel.',
    'email': 'melinda41@example.net',
    'phone_number': '001-569-766-0405x029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Baker',
    'Kelly Kelly',
    'Chase Mathews',
    'Terry Robertson',
    'Jamie Melendez',
    'Amy Harris',
    'Nathan Hansen',
],
    'json': {
    'name': 'Olivia Cunningham',
    'address': '04409 Ortega Divide\nBrookston, VI 71710',
},
    'key98763': 'value1023',
    'key85929': 'value14822',
    'key6724': 'value17900',
    'key77167': 'value35350',
    'key77956': 'value94006',
    'key78327': 'value82986',
    'key32902': 'value78816',
    'key27975': 'value31878',
    'key47981': 'value32509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Austin Miller',
    'address': '749 Pamela Views Suite 069\nEast Andrew, CO 47946',
    'text': 'First into use child hotel that. Garden allow property police.\nGround group military loss. Attack fund official citizen toward type. Officer process significant option form hear financial enough.',
    'email': 'ichavez@example.org',
    'phone_number': '+1-771-335-7482x295',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Cummings',
    'Becky Green',
    'Michael Johnson',
    'Thomas Dalton',
    'Carl Pennington',
    'Kevin Wilkerson',
    'Sabrina Brown',
    'Amy Anderson',
    'Stacy Gray',
],
    'json': {
    'name': 'Andrew Horton',
    'address': '98394 Kenneth Drive\nWest Natalieburgh, SD 94383',
},
    'key14265': 'value4955',
    'key84845': 'value22855',
    'key92302': 'value43358',
    'key58622': 'value8',
    'key2631': 'value69265',
    'key4061': 'value55005',
    'key77225': 'value53951',
    'key98793': 'value91680',
    'key41057': 'value18513',
    'key15260': 'value4229',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Seth Moon',
    'address': '0496 Sheila Vista\nNew Corybury, NC 61471',
    'text': 'Yeah political begin represent strong center forget instead. Others continue yet ago effort sure hope. Subject Mr finally record store no risk. Return ground civil stock.',
    'email': 'allison55@example.org',
    'phone_number': '(420)549-6223x4982',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marco Flores',
    'Julie Boyle',
    'Megan Fuentes',
    'Seth Gross',
    'Benjamin Smith',
    'Timothy Perry',
],
    'json': {
    'name': 'Terri Williams',
    'address': '82572 King Lane Suite 360\nEast Jennifer, WV 11893',
},
    'key34250': 'value62798',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Blake Washington',
    'address': '30399 Reynolds Mission Apt. 992\nNew Tonyport, MO 68689',
    'text': 'Affect medical partner medical. Avoid wear truth. Tax later mother body.\nLanguage similar thus next find. Everyone serve during.\nDown north choose avoid.',
    'email': 'wilsonjames@example.net',
    'phone_number': '642.887.7638x7710',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Huerta',
    'Elizabeth Chavez',
    'Crystal Marsh',
    'Nicholas Bishop',
    'Thomas Murray',
    'Laura Walker',
    'Judy Hernandez',
    'Tiffany Mclaughlin',
    'Louis Davenport',
],
    'json': {
    'name': 'Nicole Smith',
    'address': '40705 Steven Plains Apt. 626\nNathanhaven, MS 73000',
},
    'key58364': 'value22148',
    'key14260': 'value37694',
    'key54557': 'value88427',
    'key60543': 'value80452',
    'key15847': 'value49794',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Keith Little',
    'address': '78715 Baker Tunnel\nMeganborough, VI 56266',
    'text': 'Education writer power crime also play religious. May share surface. Help country travel first society dog. Should factor during thing others across.',
    'email': 'keithroberts@example.com',
    'phone_number': '936-584-1848',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Vincent Wiggins',
    'Matthew Christian',
    'William Li',
],
    'json': {
    'name': 'Michelle Owen',
    'address': '7871 Gonzalez Way Suite 267\nNorth Michele, MD 96806',
},
    'key13348': 'value56030',
    'key80508': 'value26647',
    'key56': 'value93819',
    'key32358': 'value15459',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Eileen Gardner DVM',
    'address': '2074 Brittany Plaza Suite 582\nEast Micheal, GU 76755',
    'text': 'Bit improve minute allow. Anyone wide kitchen answer arm central. Degree drop reveal huge.\nTotal Mrs discuss day son tree. Hair along site whether particular bar chance.',
    'email': 'jeremytaylor@example.com',
    'phone_number': '539.652.3395',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Wendy Riddle',
    'Tyler Winters',
],
    'json': {
    'name': 'Lisa White',
    'address': '203 Dougherty Club\nWolfestad, DC 41808',
},
    'key6015': 'value50879',
    'key24074': 'value55903',
    'key71105': 'value12034',
    'key42860': 'value83429',
    'key4776': 'value49440',
    'key97199': 'value21285',
    'key36638': 'value44429',
    'key32211': 'value1121',
    'key95887': 'value64963',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Gabriel Garcia',
    'address': '92286 Rhonda Oval\nWest April, MH 86252',
    'text': 'Road certainly before old skill. Parent animal culture finally. Risk front data data side arm.\nPopular all into avoid question treatment.',
    'email': 'rowelisa@example.org',
    'phone_number': '267.468.9699x856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Diana Baldwin',
    'Jasmine Tucker',
    'Jennifer Clayton',
    'Barbara Jones',
    'Erika Fuller',
    'Kristine Harris',
    'Terri Snyder',
    'Kayla Brown',
    'Mariah Vargas',
    'Zachary Harvey',
],
    'json': {
    'name': 'Sierra Melendez',
    'address': '4383 Quinn Squares Apt. 372\nWest Evan, TX 82632',
},
    'key99992': 'value15909',
    'key59949': 'value91331',
    'key2975': 'value32157',
    'key18163': 'value91458',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Leah Martinez',
    'address': '94079 Diane Drives\nLake Natasha, WA 19874',
    'text': 'Important east source various true group design.\nEnergy forget bed under anyone. Hold song quite improve choice gas none.',
    'email': 'justinnichols@example.org',
    'phone_number': '+1-323-518-8688x427',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Cindy Glover',
    'James Rodriguez',
    'Brittany Walker',
    'Courtney Evans',
],
    'json': {
    'name': 'Brenda Stewart',
    'address': '29150 Nunez Junction Suite 757\nFranciscohaven, GU 88440',
},
    'key67529': 'value1723',
    'key54293': 'value17042',
    'key56431': 'value39237',
    'key25192': 'value60219',
    'key39596': 'value98759',
    'key24526': 'value60715',
    'key60680': 'value61527',
    'key65652': 'value19122',
    'key74845': 'value8435',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Diana Tanner',
    'address': '436 Brad Passage Suite 148\nPort Angelamouth, AK 98545',
    'text': 'Left tonight child. Mother parent hard same increase.\nOfficial national civil wait than shake. Early its upon.\nResearch break generation whose bag. Hit these all. Discuss expert say store TV.',
    'email': 'morozco@example.net',
    'phone_number': '567.236.3078',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Abigail Lee',
    'Karen Long',
    'James Harrison',
    'Dr. Patricia Zavala',
],
    'json': {
    'name': 'Jill Robinson',
    'address': '320 Bryan Hills Suite 007\nRogersville, VT 37228',
},
    'key74184': 'value36584',
    'key61920': 'value51535',
    'key24168': 'value34621',
    'key36051': 'value25878',
    'key39079': 'value65457',
    'key26280': 'value53972',
    'key90791': 'value78449',
    'key22305': 'value92486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Carl Brown',
    'address': '4924 David Ville Apt. 425\nLake Heather, MD 79736',
    'text': 'Movement answer town political become bed. Ability people get player. Agree water force cell race name benefit. Five site however determine poor coach stuff.',
    'email': 'christiewillis@example.org',
    'phone_number': '(666)489-6645',
    'array_int_dynamic': [
    40378,
],
    'array_varchar_dynamic': [
    'Michelle Smith',
    'Kristy Lee',
    'Wendy Reyes',
    'Tyler Cox',
    'Justin Short',
],
    'json': {
    'name': 'Alicia Grant',
    'address': '23183 Young Light Apt. 059\nWest Kylefort, MA 19877',
},
    'key68771': 'value69919',
    'key35850': 'value2643',
    'key75332': 'value46453',
    'key91296': 'value94885',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Isabel Gates',
    'address': '074 English Manors\nJessicachester, NE 74256',
    'text': 'Wish money suffer team hard only move.',
    'email': 'brownjackson@example.net',
    'phone_number': '892-569-3697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brian Romero',
    'Timothy Fernandez',
    'Matthew Rios',
    'David Johnson',
    'Melissa Montoya',
    'Kelly Pope',
    'Ryan Carter',
    'Benjamin Torres',
    'Andrew Perkins',
    'Leah Murillo',
],
    'json': {
    'name': 'Andrew Alexander',
    'address': '8739 Torres Station\nBeckstad, WI 98830',
},
    'key24370': 'value68048',
    'key57519': 'value69834',
    'key9387': 'value46205',
    'key4822': 'value38120',
    'key51838': 'value57558',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Teresa Cannon',
    'address': '045 Moore Radial Suite 129\nWest Aprilfurt, IN 83986',
    'text': 'Stage he enjoy run. Medical voice expect lead speech treatment point. Push its lose grow.\nUntil during may ball themselves vote. Agreement happen evidence thing however.',
    'email': 'gomezlori@example.com',
    'phone_number': '+1-655-723-4467',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Karen Tate',
    'Jessica Banks',
    'Scott Bell',
    'Jocelyn Shaw',
    'Christine Williams',
    'Brenda Rubio',
    'Thomas Shaffer',
    'Connie Pitts',
],
    'json': {
    'name': 'David Gibson',
    'address': '580 Michelle Skyway Suite 988\nBentleychester, IA 46027',
},
    'key30397': 'value25160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Sarah Ruiz',
    'address': '071 Kyle Inlet Apt. 421\nNew Dylan, UT 93363',
    'text': 'Actually tell area seem order agreement around professional. Democratic when candidate health. Young book bag begin collection rather these organization.',
    'email': 'natalie54@example.net',
    'phone_number': '531.405.2611',
    'array_int_dynamic': [
    567,
],
    'array_varchar_dynamic': [
    'Thomas Bradley',
],
    'json': {
    'name': 'Laurie Poole',
    'address': '42212 Kenneth Islands Suite 559\nLake Kevin, IN 98372',
},
    'key76586': 'value95847',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Kevin Mccoy',
    'address': '300 Wendy Inlet\nWest Jamesville, HI 11162',
    'text': 'Standard describe here. Nature call card respond. Budget medical blue cup face economy both. Water body heart even possible trip.\nAs democratic out us adult nor. Land hot while.',
    'email': 'jessica61@example.net',
    'phone_number': '653-970-9902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Smith',
    'Johnny Smith',
    'Robert Ward',
],
    'json': {
    'name': 'Timothy Dixon',
    'address': '4829 Gamble Shore\nNew Mark, GU 93347',
},
    'key29442': 'value79582',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Karla Sanders',
    'address': 'PSC 9756, Box 9032\nAPO AA 26137',
    'text': 'Maintain arrive environment someone positive skin name. Sing clearly account learn. Report sound agreement artist off line.',
    'email': 'johnsonashley@example.org',
    'phone_number': '001-254-480-7544x4235',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Scott',
],
    'json': {
    'name': 'Peter Aguilar',
    'address': '6161 Little Bypass Suite 587\nScottton, IN 93319',
},
    'key33846': 'value78626',
    'key28175': 'value36292',
    'key14868': 'value67988',
    'key13003': 'value91784',
    'key87176': 'value98049',
    'key43053': 'value65603',
    'key66168': 'value74176',
    'key80041': 'value23943',
    'key28464': 'value5593',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Hannah Smith',
    'address': '15598 Church Circle Suite 077\nJaredmouth, CA 18587',
    'text': 'Worker truth station worker stuff dark. Expect since food address time professor country. Time attorney down financial stage often staff second.',
    'email': 'gabriela86@example.net',
    'phone_number': '916-528-7734x3373',
    'array_int_dynamic': [
    32226,
],
    'array_varchar_dynamic': [
    'Daniel Carson',
    'Adam Davidson',
    'Andrea Ruiz',
],
    'json': {
    'name': 'Austin Martin',
    'address': '562 Michael Rapid\nCrystalhaven, PA 81002',
},
    'key68356': 'value40710',
    'key7334': 'value89685',
    'key32588': 'value83997',
    'key57459': 'value50696',
    'key60371': 'value12252',
    'key13257': 'value70624',
    'key89419': 'value31299',
    'key63244': 'value69447',
    'key4978': 'value6997',
    'key63271': 'value11342',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Justin Bryant',
    'address': 'Unit 9652 Box 8099\nDPO AP 73186',
    'text': 'Final man would yes. Teacher office attention drive push five sing have. Child defense billion water.\nNews entire recognize heart thousand along manage green. Her what describe article day.',
    'email': 'darryl69@example.org',
    'phone_number': '(252)876-1219x9445',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Manning MD',
    'Ronald Martinez',
    'Kayla Mcintosh',
    'Michael Lee',
    'Kenneth Anderson',
    'Dr. Carol Hahn',
    'Marie Mills',
    'Thomas Mitchell MD',
    'Duane Stephens',
],
    'json': {
    'name': 'Lauren Fowler',
    'address': '214 Larry Expressway\nAprilside, MH 91691',
},
    'key40028': 'value35933',
    'key94047': 'value76811',
    'key74420': 'value55004',
    'key16664': 'value97386',
    'key60079': 'value54450',
    'key92227': 'value78786',
    'key74998': 'value94356',
    'key79593': 'value63203',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Andrew Morris',
    'address': '901 Jackson Mews\nGuzmanland, OK 88254',
    'text': 'Police process learn. Accept together throughout everybody three decision reflect we.\nCheck explain pressure character.\nStrong specific respond it. Charge inside difference huge before sport.',
    'email': 'zachary78@example.org',
    'phone_number': '001-610-972-6763x904',
    'array_int_dynamic': [
    58066,
],
    'array_varchar_dynamic': [
    'Jack Haynes',
    'Margaret Hebert',
    'Ethan Mclaughlin',
    'Katrina Clark',
    'Ashley Knight',
    'Gregory Wright',
    'Michael Simmons',
    'Danielle King',
    'Keith Turner',
],
    'json': {
    'name': 'Jesse Wolfe',
    'address': '6062 Logan Harbor\nSouth Danielfort, OH 18894',
},
    'key61844': 'value63124',
    'key54834': 'value48210',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Catherine Scott',
    'address': '72622 Robert Squares Suite 732\nWest Randy, OK 97384',
    'text': 'Drop wish life dark rest case affect check. Though economic something free clear forward. Total course myself especially.\nFact laugh real beyond. Without yet through population.',
    'email': 'reyessteve@example.com',
    'phone_number': '(744)473-3377x832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Hannah Wood',
    'Daniel Yu',
    'Marissa Carter',
],
    'json': {
    'name': 'Mary Jordan',
    'address': '4700 Danny Expressway\nNew Jamie, PA 54155',
},
    'key42725': 'value21904',
    'key3129': 'value63929',
    'key85970': 'value45940',
    'key91759': 'value18196',
    'key65165': 'value94612',
    'key88352': 'value777',
    'key82946': 'value87795',
    'key35507': 'value55739',
    'key21754': 'value67582',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Edwin Thompson',
    'address': '7866 Andrew Cove Suite 330\nWest Danielle, AR 06191',
    'text': 'Base from more bed. However painting recent organization. Interview show history politics specific manage peace. View both form continue fish.\nWhen would product against six. Ever play skin.',
    'email': 'cantujonathan@example.com',
    'phone_number': '+1-978-622-5570x2668',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Cruz MD',
    'Shane Nguyen',
    'Nathan Wood',
],
    'json': {
    'name': 'Stephen Ramirez',
    'address': '547 Lewis Plain Suite 466\nEast David, MH 02233',
},
    'key45757': 'value96867',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Paul Perkins',
    'address': 'Unit 7744 Box 3189\nDPO AA 11672',
    'text': 'Class once next. Stop less next. The side learn spend animal.\nBoard hotel case fly cost. Agency nothing listen arm time describe.\nFront along teach. Statement wonder purpose remember hear.',
    'email': 'timothylewis@example.com',
    'phone_number': '951.867.0560x2759',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Luis Johnson',
    'Jacqueline Calderon',
    'Brandon Rogers',
],
    'json': {
    'name': 'Anthony Koch',
    'address': 'PSC 1773, Box 5953\nAPO AP 04815',
},
    'key92445': 'value2946',
    'key48262': 'value68528',
    'key51372': 'value73368',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Melissa Baker',
    'address': 'Unit 4869 Box 3893\nDPO AA 74065',
    'text': 'Leg probably similar raise take herself she teach. Hour western explain win seek bring. Know raise model rock yard sell.',
    'email': 'derrick73@example.com',
    'phone_number': '(399)966-5463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Collins',
    'Natalie Bell',
    'Carol Sanchez',
],
    'json': {
    'name': 'Brian Scott',
    'address': '851 Alexander Track Suite 830\nBenjaminborough, CT 51883',
},
    'key58720': 'value17480',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Emily Beck',
    'address': 'USCGC Malone\nFPO AA 81939',
    'text': 'Find I expect mother mean study. Million wall interest tell PM.\nEvening part class five turn decide check. Keep will quality wish. Of marriage second.',
    'email': 'wlynch@example.com',
    'phone_number': '2184034155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Mclaughlin',
    'Elizabeth Flores',
    'Lynn Todd',
    'Christopher Sampson',
    'Samantha Butler',
    'Laura Griffin',
    'Stephen Miller',
    'Catherine Peterson',
    'Juan Ingram',
],
    'json': {
    'name': 'Lori Romero',
    'address': '3140 Gray Passage\nRobinsonport, CT 60661',
},
    'key88542': 'value5091',
    'key22131': 'value17330',
    'key2995': 'value58595',
    'key22494': 'value52158',
    'key99123': 'value18298',
    'key94569': 'value13031',
    'key97532': 'value48058',
    'key43340': 'value69797',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Vanessa Kane',
    'address': '843 Bailey Plains\nAmberside, PW 01397',
    'text': 'Last audience daughter. Care add brother. Dream relate strong suggest push.\nDifferent small particular face. Yourself start drop national past especially another.',
    'email': 'wesley44@example.com',
    'phone_number': '5042618826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Maria Walter',
    'Richard Woods',
    'Tiffany Gomez',
    'Jessica Ford',
    'Hunter Thompson',
    'Patrick Edwards',
    'Jose Knight',
    'Debbie Brock',
    'Richard Leach',
    'Ryan Hansen',
],
    'json': {
    'name': 'Jill Scott',
    'address': '139 Ortiz Shoals Apt. 455\nNew Lynn, MA 32172',
},
    'key63485': 'value96585',
    'key33114': 'value30195',
    'key42050': 'value39975',
    'key12963': 'value12939',
    'key8350': 'value40176',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Angela Dixon',
    'address': '22892 Amy Squares Apt. 051\nNorth Catherine, DC 13373',
    'text': 'Majority within could radio game. Personal respond land sign easy party black.\nSimply position spend former hand herself out enjoy.',
    'email': 'flynncurtis@example.org',
    'phone_number': '(297)724-9361x48734',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Estrada',
    'Eric Gould',
],
    'json': {
    'name': 'Ronald Smith',
    'address': '6734 Dillon Ridge Apt. 738\nDuffyborough, OR 58456',
},
    'key3674': 'value25827',
    'key20565': 'value61502',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Gregory Hunt',
    'address': '3481 Edward Shoal\nChristinemouth, AR 10677',
    'text': 'Through unit interview admit point. House year food adult agree.',
    'email': 'brian68@example.org',
    'phone_number': '765.655.2328x890',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mathew Stout',
    'Mrs. Kristen Chambers PhD',
    'Lori Gibson',
    'Suzanne Chan',
    'David Smith',
],
    'json': {
    'name': 'Adam Gutierrez',
    'address': '3352 Gabriel Expressway\nBrittanyside, AR 33088',
},
    'key5444': 'value6426',
    'key23259': 'value69564',
    'key47009': 'value1827',
    'key36516': 'value73368',
    'key56310': 'value54869',
    'key68852': 'value47078',
    'key8469': 'value75550',
    'key78362': 'value82640',
    'key46381': 'value60106',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Stacy Johnson',
    'address': '2140 Collins Motorway\nNorth Kathy, DC 96630',
    'text': 'Will information image teacher. Threat those prove edge really agency.\nThing natural interview policy certain. Claim last north best international. Doctor professor claim before guy.',
    'email': 'kleinamanda@example.net',
    'phone_number': '826.960.4997',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Patel',
    'Kyle Walker',
    'Daniel Phelps',
    'Kenneth Lucas',
    'Chase Hansen',
    'Amanda White',
    'Beth Perkins',
],
    'json': {
    'name': 'Emily Thompson',
    'address': '6342 Scott Hills Suite 838\nAnnfort, NH 38880',
},
    'key98401': 'value96676',
    'key74856': 'value58118',
    'key76496': 'value60336',
    'key43402': 'value36015',
    'key24025': 'value78408',
    'key12649': 'value88107',
    'key47167': 'value95333',
    'key75527': 'value14376',
    'key68569': 'value57523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jennifer Williams',
    'address': '31156 Fletcher Place Suite 270\nJohnathanside, OK 69783',
    'text': 'Air reduce event of cut increase last. Very leg might.\nGroup partner tough big. Measure community allow talk. Attack provide attack able cost.',
    'email': 'iflowers@example.com',
    'phone_number': '636.689.5584',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Morton',
    'Travis Thomas',
    'James Smith',
    'Jennifer Conrad',
    'Shaun Hunt',
    'Kathleen Johnson',
],
    'json': {
    'name': 'Roger Stuart',
    'address': '3688 Megan Drives Suite 270\nEast Rachelmouth, FL 34845',
},
    'key12272': 'value1635',
    'key18515': 'value94653',
    'key87927': 'value27486',
    'key68437': 'value24135',
    'key14703': 'value79843',
    'key75777': 'value26127',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Renee Mcclain',
    'address': 'PSC 9278, Box 5186\nAPO AE 49076',
    'text': 'East political discover popular image well. Rule knowledge east gun. Skin subject help next nice development tell.',
    'email': 'garrett85@example.org',
    'phone_number': '(357)937-9257',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kaitlin Walker',
    'Margaret Padilla',
    'Tina Barajas',
    'Carlos Mcknight',
    'Lisa Norton DDS',
    'Trevor Young',
    'Thomas Li',
    'Brian Mayer',
],
    'json': {
    'name': 'Alexandra Cortez',
    'address': '4952 Jose Throughway Apt. 303\nDavidview, MT 30780',
},
    'key84844': 'value26542',
    'key79677': 'value70',
    'key17410': 'value89523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Amanda Mills',
    'address': '664 Faulkner Union Suite 810\nElizabethburgh, OR 70209',
    'text': 'Whole rich there issue lead wrong listen. These end my recent. Any that bag or talk month short.\nForm continue but Democrat window end.',
    'email': 'timothycox@example.net',
    'phone_number': '001-437-512-0875x34190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Castillo',
    'Christopher Hardin',
    'Sara Fisher',
    'Michael Miller',
],
    'json': {
    'name': 'Rachel Bauer',
    'address': '0259 Samantha Hollow Suite 838\nElizabethchester, MP 60941',
},
    'key6267': 'value15629',
    'key247': 'value70761',
    'key15836': 'value17049',
    'key51892': 'value43294',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Walter Cunningham',
    'address': '3578 John Corner\nEast Stacie, WY 13987',
    'text': 'Decide cause picture trouble game account. Ball probably sing can production who human.\nTruth around talk media. Home increase data these theory be husband. Old little development song.',
    'email': 'wrightjamie@example.com',
    'phone_number': '+1-838-998-0220x76324',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mary Davis',
    'Alison Schneider',
    'Ryan Mueller',
    'Amanda Clark',
    'Jeremy Brennan',
    'Adam Wise',
    'Tina Jacobs',
    'Ricky Hammond',
],
    'json': {
    'name': 'Debra Boyle',
    'address': '191 Hayes Dale Apt. 469\nThomasville, OK 41761',
},
    'key46396': 'value65474',
    'key79738': 'value99285',
    'key28827': 'value63464',
    'key43857': 'value15036',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Cameron Clark',
    'address': '6710 Copeland Prairie Apt. 992\nSouth Brandon, AS 34971',
    'text': 'Important investment both these third. Marriage hand activity reason room any sort.\nBlue look sure human. Building daughter decision officer positive may their. Structure third off.',
    'email': 'jenkinsmelissa@example.com',
    'phone_number': '(873)697-1248x614',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Fernando Sampson',
    'Kathleen Armstrong',
    'Jerry Holt',
    'Janet Young',
    'Jose Brown',
    'Cynthia Costa',
    'Brian Gibson',
],
    'json': {
    'name': 'Rebecca Mcdowell',
    'address': '72649 Moss Hollow\nSmithton, HI 12091',
},
    'key54354': 'value96626',
    'key93034': 'value82020',
    'key92328': 'value39948',
    'key77058': 'value81554',
    'key7636': 'value13688',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Victoria Kelly',
    'address': '2416 Elizabeth Harbors Apt. 097\nMartintown, LA 89267',
    'text': 'Task international occur seven huge option dog. Nice receive garden history.\nPower learn determine feeling similar chair decision itself. Maybe end attack still. Sport occur apply structure.',
    'email': 'acook@example.net',
    'phone_number': '+1-507-679-7491x331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Diane Green',
    'Derek Smith',
    'Tammy Hernandez',
    'Todd Proctor',
    'Nicholas Morris',
    'Dr. Natalie Hubbard',
    'Timothy Taylor',
],
    'json': {
    'name': 'Xavier Hayes',
    'address': '34231 Thompson Lights Suite 682\nSouth Jessicaland, MP 71293',
},
    'key61288': 'value69613',
    'key19972': 'value54531',
    'key10126': 'value33344',
    'key20974': 'value77565',
    'key32023': 'value37195',
    'key68690': 'value62248',
    'key24604': 'value4784',
    'key1619': 'value38753',
    'key70451': 'value32425',
    'key50281': 'value51482',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'John Baker',
    'address': '62267 Denise Grove Suite 956\nNorth Timothy, LA 75225',
    'text': 'Same rise raise accept toward present. Center paper conference organization garden. Information spend of.\nClear role write effort. Thus yeah agency onto. Of word wonder myself.',
    'email': 'iwilkerson@example.org',
    'phone_number': '252.906.3422x573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Smith',
    'William White',
],
    'json': {
    'name': 'Anthony Hawkins',
    'address': '566 Joshua Vista\nJonesland, PW 80310',
},
    'key1773': 'value94323',
    'key92112': 'value75867',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Hannah Bailey',
    'address': '9325 David Mill Suite 180\nWendyton, AZ 26597',
    'text': 'Black travel office foreign. Bit me hard leave others others. Pretty everyone else enter.\nTeam go can. Follow green charge federal. Environmental newspaper traditional message true character.',
    'email': 'hpena@example.org',
    'phone_number': '306-622-4449',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Moore',
    'Leslie Ellison',
    'Matthew Johnson',
    'Lauren Davidson',
    'Anthony Cooper',
    'Susan Ray',
    'Warren Hammond',
    'Anthony Nguyen',
],
    'json': {
    'name': 'Jordan Richardson',
    'address': '99441 Salas Glens\nEast Kathychester, IN 52267',
},
    'key73539': 'value29546',
    'key52794': 'value82082',
    'key12995': 'value79817',
    'key25267': 'value99495',
    'key68842': 'value80817',
    'key78771': 'value26565',
    'key14037': 'value51051',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jeffrey Santos',
    'address': '927 Michael Walks\nNorth Cynthiafort, MA 91005',
    'text': 'Voice guess stock deep peace. Particular often tough store population beautiful. Prove pass cost. Minute employee when money.',
    'email': 'perkinssara@example.com',
    'phone_number': '001-806-770-9449',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kaitlyn Huang',
    'Carla Stark',
    'Ashley Carroll',
    'Christopher Watson',
    'Michael Casey',
],
    'json': {
    'name': 'Michael Foster',
    'address': '337 Alec Loop Suite 563\nJosephborough, LA 14361',
},
    'key37886': 'value67717',
    'key46388': 'value71939',
    'key49520': 'value34378',
    'key25997': 'value80084',
    'key94251': 'value3909',
    'key89532': 'value9197',
    'key16256': 'value85828',
    'key8024': 'value62090',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Christopher Smith',
    'address': '2012 Rice Street Apt. 705\nPort Tonishire, HI 71788',
    'text': 'Middle including remain fear your side land recognize. Drop lot take water impact though.\nWhatever nothing since American support. Carry month impact executive look property fire special.',
    'email': 'wmoreno@example.net',
    'phone_number': '+1-696-746-9915x92351',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Harris',
    'Angela Fowler',
    'Jacqueline Robles',
    'Tracy Evans',
    'Amber King',
    'Madeline Robertson',
    'Elizabeth Gordon',
    'Jenna Jordan',
    'Joshua Norris',
],
    'json': {
    'name': 'Justin Paul',
    'address': '678 Rodriguez Shores\nGibsonside, CT 38605',
},
    'key42947': 'value15645',
    'key82888': 'value42120',
    'key10316': 'value31783',
    'key17890': 'value9995',
    'key32897': 'value32311',
    'key59718': 'value85671',
    'key87978': 'value63883',
    'key73396': 'value44705',
    'key46950': 'value20724',
    'key12096': 'value80173',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Samantha Mccann',
    'address': '31068 Michael Flat\nJasminemouth, GU 15657',
    'text': 'Miss still rock home listen high political. Black across pretty feel.',
    'email': 'gdawson@example.org',
    'phone_number': '813.551.7739x9155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kerry Robles',
    'Matthew Johnson',
    'Jeffery Shelton Jr.',
    'Mr. Gavin Rose MD',
    'Jose Thomas',
],
    'json': {
    'name': 'Michael Fletcher',
    'address': '795 Joyce Branch Apt. 405\nLake Stanleystad, AZ 54589',
},
    'key18750': 'value82042',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Gregory Johnson',
    'address': '800 Walker Ridge Apt. 312\nJonesshire, WV 89682',
    'text': 'Book notice personal report assume senior director cost. No upon prevent doctor girl skill statement. Young conference per. News exactly rich agency decade event call fast.',
    'email': 'robertlewis@example.org',
    'phone_number': '256-874-0010x984',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Johnson',
    'Alexandra Terry',
    'Timothy Chapman',
    'Michael Martin',
    'James Cooley',
    'Jason Kelly',
],
    'json': {
    'name': 'Jennifer Hammond',
    'address': '9768 Benjamin Branch\nAndersonmouth, MO 07850',
},
    'key85321': 'value72434',
    'key29105': 'value81957',
    'key21509': 'value68538',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Danielle Page',
    'address': '235 Bowman Row Apt. 123\nKirkberg, MA 31539',
    'text': 'Recently call quite off program serious time. Treat minute local song history. Option hair stay reason.\nTeach write plant. Expect site culture education increase window give. Feel all do light.',
    'email': 'brandonbaldwin@example.net',
    'phone_number': '+1-707-642-0684',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Ellis',
    'Laura Kane',
    'Amanda Moran',
    'Eduardo Gamble',
    'Matthew Smith',
    'Anthony Harvey',
    'Lori Morgan',
    'Robert Smith',
    'Robert Cummings',
],
    'json': {
    'name': 'Mary Hale',
    'address': '47010 Daniel Road\nLake Christopherstad, VI 06889',
},
    'key65558': 'value61013',
    'key6853': 'value12697',
    'key31589': 'value42410',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Carly Newman',
    'address': '0399 Travis Unions Apt. 275\nDavidburgh, ME 41718',
    'text': 'Eat beyond born picture medical. Defense body Mr table attorney entire. People situation artist administration evidence.\nSkill mouth out. Candidate southern approach shoulder water charge national.',
    'email': 'lambertterri@example.org',
    'phone_number': '548.901.8001x406',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Frank Harrell',
],
    'json': {
    'name': 'Bradley Holloway',
    'address': '3341 Reyes Forest Suite 716\nWest Courtney, PR 28772',
},
    'key580': 'value20190',
    'key269': 'value71982',
    'key88917': 'value79194',
    'key68828': 'value88711',
    'key97749': 'value29326',
    'key92911': 'value79488',
    'key67534': 'value5070',
    'key74593': 'value6661',
    'key37787': 'value89716',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Laurie Hernandez',
    'address': '5184 West Groves Suite 463\nNorth Justin, MS 50575',
    'text': 'General hot article cold memory. Goal policy high be owner explain. Push stuff home easy personal. Raise write once student full.',
    'email': 'staceyjenkins@example.net',
    'phone_number': '8645058421',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Victor Pitts',
    'Tyler Murphy',
    'Logan Macdonald',
    'Julie Gutierrez',
    'Lori Powers',
    'Brittany Gardner',
    'Stephanie Buchanan',
],
    'json': {
    'name': 'Tiffany Manning',
    'address': '012 Jones Meadow\nLake Jessica, AS 59573',
},
    'key14274': 'value74128',
    'key58779': 'value89817',
    'key38411': 'value35005',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Tom Williams',
    'address': '4754 Jason Coves\nNorth Hunter, PW 25652',
    'text': 'Him interest really central. Give live hot.\nRemember candidate first us. Nation before human about plan gas.\nExist stage risk maintain world line cost exist. Chair week form there.',
    'email': 'tjohnson@example.org',
    'phone_number': '227.525.9393',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mercedes Marshall',
    'James Mack',
    'Karen Rogers',
    'Anthony Wilkerson',
    'Wendy Chen',
    'Anna Ferrell',
    'Michael Brewer',
    'David Reyes',
    'Natalie Garcia',
],
    'json': {
    'name': 'William Mueller',
    'address': '40958 Anderson Meadows Apt. 148\nEast Antonioburgh, IA 57255',
},
    'key85774': 'value96280',
    'key67457': 'value1672',
    'key74367': 'value12963',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Albert Stout',
    'address': '37193 Gutierrez Station Suite 452\nNew Nicole, NC 49388',
    'text': 'Be discussion majority born field use goal practice. Cover will day all medical movement. Study short suffer raise country present position.',
    'email': 'taylor54@example.org',
    'phone_number': '+1-647-589-6503x3583',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Nunez',
    'Reginald Collins',
    'Dr. Samuel Fuller Jr.',
    'Sean Preston',
    'Ashley Clark',
    'Christopher Jones',
],
    'json': {
    'name': 'Jennifer Diaz',
    'address': '042 Chelsea Forge Apt. 566\nMelanieberg, NC 99572',
},
    'key22941': 'value20864',
    'key25037': 'value98307',
    'key48299': 'value74510',
    'key9062': 'value90387',
    'key94254': 'value50782',
    'key44028': 'value69693',
    'key53749': 'value98458',
    'key63148': 'value3049',
    'key84526': 'value18194',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Samuel Ellis',
    'address': '08326 John Dam Suite 384\nPort Kristentown, OR 98320',
    'text': 'Citizen or itself note. Man thing these travel company.\nSimilar enjoy down camera happen dinner. Assume brother PM treatment mission in. City education hotel with debate.',
    'email': 'autumnmorris@example.org',
    'phone_number': '748-833-7210',
    'array_int_dynamic': [
    26994,
],
    'array_varchar_dynamic': [
    'Jason Miller',
    'Bradley Liu',
    'John Wallace',
    'Robert Martin',
    'Cheryl Porter',
    'Brian Alvarado',
    'Adam Smith',
    'Cory Huang',
    'Annette Reed',
    'Troy Carter',
],
    'json': {
    'name': 'Shane Hughes',
    'address': '91260 Hall Rapid\nErinchester, FL 73187',
},
    'key14554': 'value82869',
    'key6943': 'value92288',
    'key22012': 'value396',
    'key73357': 'value73798',
    'key65541': 'value56736',
    'key34160': 'value38148',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Nicholas Fletcher',
    'address': '023 Elizabeth Lodge Suite 732\nNew Christineland, MN 03359',
    'text': 'Skill turn none discussion. Just production democratic big draw help pretty. Time pretty represent space any.',
    'email': 'jenkinsjohn@example.org',
    'phone_number': '001-885-696-9353x1465',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Howell',
    'Crystal Gibson',
    'John Hubbard',
    'Richard Smith',
    'Benjamin Anderson',
    'Rhonda Long',
    'Catherine Washington',
],
    'json': {
    'name': 'Amanda Mcdaniel',
    'address': '00303 Baker Expressway\nLake Austin, NH 76361',
},
    'key24169': 'value78322',
    'key73845': 'value73508',
    'key36326': 'value72968',
    'key60589': 'value37445',
    'key68832': 'value26183',
    'key50352': 'value92400',
    'key16573': 'value2265',
    'key3179': 'value12848',
    'key16911': 'value72454',
    'key42056': 'value82331',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Bridget York',
    'address': '6583 Gonzalez Walks\nSouth Robert, AR 90687',
    'text': 'Get beautiful probably computer power. Analysis form court tree station field natural room. Tough relate act discussion.',
    'email': 'robert25@example.org',
    'phone_number': '642-496-0306x85047',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Decker',
    'Shannon Alvarez',
    'Eduardo Reese',
    'Derrick Brown',
    'Beth Lee',
],
    'json': {
    'name': 'Ariel Williams',
    'address': '7260 Timothy Falls Apt. 251\nSouth Reginald, NC 73577',
},
    'key72881': 'value95623',
    'key85403': 'value758',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Alexandra Adams',
    'address': '84756 White Springs Suite 855\nEricfort, NY 64451',
    'text': 'About be light resource. Light lot notice best PM four enter.\nEasy charge four information. Lose type power across sing practice.',
    'email': 'elizabethdennis@example.org',
    'phone_number': '583.754.4856x489',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Wright',
    'Austin Fields',
    'Jacob Fields',
    'Zachary Pruitt',
    'Christian Guzman',
],
    'json': {
    'name': 'Joann Russo',
    'address': 'PSC 3759, Box 5447\nAPO AP 58419',
},
    'key87228': 'value77501',
    'key65986': 'value2860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Wendy Ortiz',
    'address': '3399 Brandi Harbor Apt. 604\nGarrettmouth, NV 82534',
    'text': 'Any important two property employee because. Choice eye million guess detail.\nGoal opportunity business them building up. Market man exist inside ground.',
    'email': 'brittany59@example.net',
    'phone_number': '(814)686-0345',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Bradley',
    'Kathleen Perry',
    'Andrew Stephenson',
    'Alexander Ward',
],
    'json': {
    'name': 'Timothy Olson',
    'address': 'USS Lewis\nFPO AP 41141',
},
    'key33199': 'value97755',
    'key37789': 'value5293',
    'key1314': 'value69069',
    'key76269': 'value43557',
    'key35107': 'value42305',
    'key27902': 'value10874',
    'key96628': 'value88107',
    'key18477': 'value40774',
    'key78269': 'value31818',
    'key46182': 'value80706',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Casey King',
    'address': '6618 Carl Mills Suite 931\nDanielside, LA 25582',
    'text': 'Report word red. Although learn financial information risk seat. Job protect large provide not notice interesting. Stage rate move military article back.',
    'email': 'kathryn26@example.com',
    'phone_number': '+1-699-354-4050x8449',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Crawford',
    'Teresa Ortiz',
    'William Willis',
    'Angela Miller',
    'Kaitlyn Butler',
    'Nicholas Haynes',
    'Tommy Hoover',
    'Charles Williams',
    'Paul Hood',
],
    'json': {
    'name': 'Amber Oliver',
    'address': 'PSC 9106, Box 3262\nAPO AE 09546',
},
    'key24658': 'value5374',
    'key13929': 'value10876',
    'key53948': 'value84178',
    'key26943': 'value89029',
    'key25810': 'value37885',
    'key91534': 'value77028',
    'key28895': 'value987',
    'key25262': 'value8158',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Brett Johnson',
    'address': '25528 Adams Village\nSandrachester, MO 56644',
    'text': 'Room option sister although feel.\nStatement region fill street. Father myself yard ready once fire fall. Suggest rock model exist building beat movement.',
    'email': 'nnunez@example.net',
    'phone_number': '(890)653-4524x98075',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Eric Davis',
    'Donna Williams',
    'Randy Castillo',
    'Matthew Parker',
    'Brittany White',
    'Tricia Ferguson',
    'Debra King',
    'Mr. David Gay DDS',
    'Lorraine Hoffman',
    'Natalie Gomez',
],
    'json': {
    'name': 'Jesse Little',
    'address': '8097 Morales Plain\nWest Saraview, KS 98481',
},
    'key83826': 'value34423',
    'key2717': 'value14124',
    'key59681': 'value9273',
    'key64131': 'value23589',
    'key10467': 'value42630',
    'key16868': 'value60706',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Edward Wright',
    'address': '82995 Benjamin Via Apt. 928\nJoseborough, IN 48430',
    'text': 'Can American open view floor affect. Science region cup senior Mr.\nHard trip successful.\nReach staff between specific. Dog church share. Body look society town since official indeed.',
    'email': 'maurice50@example.net',
    'phone_number': '410.657.5097x0660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Horton',
    'Jason Craig',
    'Erica Robinson',
],
    'json': {
    'name': 'Ashley Jones',
    'address': 'Unit 2522 Box 8153\nDPO AE 43787',
},
    'key8941': 'value25359',
    'key29590': 'value19823',
    'key70864': 'value27288',
    'key31633': 'value14273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Lori Sanchez',
    'address': '1564 Ellison Isle\nMichaelburgh, NM 44879',
    'text': 'Media support see between. Sport must size tend. Two time activity employee six toward candidate.\nCertainly treat structure where. Evidence house sport why no. Agent them day may.',
    'email': 'heatherkelly@example.org',
    'phone_number': '977.283.2819',
    'array_int_dynamic': [
    55324,
],
    'array_varchar_dynamic': [
    'Stephen Mccarty',
    'Laura Williams MD',
    'Kenneth Castillo',
    'Timothy Barnes',
],
    'json': {
    'name': 'Marissa Graham',
    'address': '4410 Richardson Shore\nNew Derek, NM 75810',
},
    'key66140': 'value6264',
    'key33290': 'value99656',
    'key65438': 'value65693',
    'key50524': 'value20162',
    'key82286': 'value1032',
    'key68761': 'value36061',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Kristy Baxter',
    'address': '19138 Hammond Stream\nRaystad, PR 73657',
    'text': 'Black everything at risk education example. Someone eye last head. Population tough than account our mean.\nLow say choose three black. Mean list whether area.',
    'email': 'tgarcia@example.com',
    'phone_number': '879-312-0198',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Zimmerman',
    'Joseph Jensen',
    'Joseph Gonzales',
    'Sandra Vance',
    'Andrea Campbell',
],
    'json': {
    'name': 'Christopher Castillo',
    'address': '479 Ramos Tunnel Apt. 434\nNew Sandra, MD 92582',
},
    'key2833': 'value25052',
    'key25891': 'value26930',
    'key976': 'value76113',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Dennis Mata',
    'address': '764 Rodgers Trail Apt. 101\nNorth Jessicahaven, VI 50088',
    'text': 'Standard rock accept charge our car administration. Run pattern identify away score where. List discover anything garden. Forward turn step task oil father though.',
    'email': 'smithanthony@example.com',
    'phone_number': '5776506644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jay Love',
    'Jamie Owens',
    'Shawn Miles',
    'Melissa Riddle',
    'Michelle Adams',
    'Erika Mcintyre DVM',
    'Nathan Smith',
    'Nathan Romero',
    'Eric Vargas',
    'Amy Randall',
],
    'json': {
    'name': 'Marc Sparks',
    'address': '4569 Heather Mountains\nNew Edwintown, ID 99061',
},
    'key18554': 'value40381',
    'key12076': 'value24271',
    'key90341': 'value91523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Kevin Salinas',
    'address': '5349 Leslie Valley\nTonyachester, IA 52400',
    'text': 'Best young perform those quality door present. List number hair least ten administration strategy.',
    'email': 'marksims@example.net',
    'phone_number': '350.519.4968x9389',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Steven Esparza',
    'Jamie Ramirez',
    'Tanya Johnson',
    'Jennifer Garcia',
    'Taylor Rice',
    'Adrienne Perez',
],
    'json': {
    'name': 'Sarah Gilmore',
    'address': '89924 Price Gateway Apt. 278\nNew William, ID 55650',
},
    'key4259': 'value70630',
    'key67690': 'value37561',
    'key52158': 'value72084',
    'key27848': 'value52104',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Tammy Smith',
    'address': '155 Amy Rapids Suite 372\nMoralesmouth, OK 47183',
    'text': 'Middle land area pretty.\nHigh check lot. Travel pass production arrive federal activity hundred.',
    'email': 'kelsey49@example.com',
    'phone_number': '9598639685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Monica Gonzalez',
    'Melissa Trevino',
    'Mark Smith',
    'Melinda Townsend',
    'Elizabeth Bennett',
    'Suzanne Hanna',
    'Michael Ellis',
    'Kenneth Cole',
],
    'json': {
    'name': 'John Walton',
    'address': '0523 Dyer Spur Apt. 919\nPort Adam, NC 78839',
},
    'key86232': 'value95913',
    'key46955': 'value80238',
    'key55777': 'value38947',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Nancy Kennedy',
    'address': '2461 Jesus Throughway Apt. 400\nWest Jessicamouth, VT 98377',
    'text': 'History read prove religious important send east. These mother dinner religious option morning cell cultural. Price sign in effect could.\nHappen heavy public eight. Rich admit clearly later.',
    'email': 'zparks@example.com',
    'phone_number': '(948)371-9781x9361',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michele Wallace',
    'Heather Colon',
    'Chelsea Smith',
    'Patricia Allen',
    'Jennifer Williams',
    'Megan Smith',
],
    'json': {
    'name': 'David English',
    'address': '37473 Hill Throughway Suite 758\nTylerchester, MN 34384',
},
    'key97334': 'value42741',
    'key89521': 'value421',
    'key25307': 'value79484',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Clifford Baker',
    'address': '3754 Hayden Spur Suite 138\nJenniferport, NE 68089',
    'text': 'Travel again book wall record. Mrs do thing executive own. Look nation small treat production attorney cell.',
    'email': 'ychristensen@example.com',
    'phone_number': '+1-327-576-8711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Preston',
    'Rachel Rios',
    'Richard Buck',
    'Cynthia Morris',
    'Brittany Gray',
    'Barbara Wilson',
    'Micheal Ray',
    'Vincent Adams',
    'Teresa Hayes',
],
    'json': {
    'name': 'Alexander Schultz',
    'address': '9598 Powers Stream\nNorth Madison, TN 04593',
},
    'key4482': 'value33060',
    'key75284': 'value51106',
    'key30062': 'value85740',
    'key51868': 'value86220',
    'key56489': 'value99480',
    'key45808': 'value7445',
    'key38111': 'value89455',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Michael Hernandez',
    'address': 'PSC 5269, Box 7181\nAPO AE 84616',
    'text': 'Money approach generation production police. Able war will stuff.\nClear keep focus democratic. Watch stock serious over something set cover pay. Fight item daughter between method foot.',
    'email': 'jonathandavidson@example.org',
    'phone_number': '(665)532-5598x06845',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Cook',
    'Timothy Kim',
    'Gabriel Melton',
    'Kristen Copeland DVM',
    'Toni Walker',
    'Kristin Moore',
],
    'json': {
    'name': 'Raymond Hudson',
    'address': '9569 Eric Canyon\nEast Michaelfurt, NM 46022',
},
    'key16392': 'value9721',
    'key37463': 'value31022',
    'key79907': 'value85710',
    'key70920': 'value16712',
    'key24523': 'value55390',
    'key93864': 'value49663',
    'key25266': 'value10459',
    'key82935': 'value99917',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Jon Weaver',
    'address': '089 Long Harbors Apt. 319\nPort Amy, AZ 47113',
    'text': 'Clearly drug as accept. Situation today form office your. Little effort adult claim glass concern.',
    'email': 'adam23@example.com',
    'phone_number': '001-661-263-3884',
    'array_int_dynamic': [
    272,
],
    'array_varchar_dynamic': [
    'Troy Franklin',
],
    'json': {
    'name': 'Kenneth Jenkins',
    'address': '350 Lawrence Coves\nJonesport, KY 58553',
},
    'key71560': 'value60264',
    'key13640': 'value65041',
    'key12776': 'value78578',
    'key10749': 'value53287',
    'key96216': 'value4302',
    'key54377': 'value81541',
    'key73945': 'value4356',
    'key5088': 'value32658',
    'key79997': 'value77634',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Molly Perez',
    'address': '5059 Rose Plaza Apt. 184\nHendrixbury, PW 70163',
    'text': 'Your day much box. Agree teach research ball interesting their enjoy throw.\nGround music yet technology person own address. Still send coach serious onto real himself.',
    'email': 'smithjuan@example.com',
    'phone_number': '001-520-264-2544',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Oliver',
    'Roger Holt',
    'Joy Hill',
    'Matthew Love',
    'Crystal Carroll',
],
    'json': {
    'name': 'Nicolas Jennings',
    'address': 'Unit 0830 Box 5391\nDPO AP 31783',
},
    'key75237': 'value16377',
    'key70055': 'value3459',
    'key19571': 'value66199',
    'key10737': 'value6394',
    'key4465': 'value53319',
    'key45827': 'value38563',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Ashley Cooley',
    'address': '8735 Barbara Roads\nPort Cindyburgh, FL 65987',
    'text': 'Them long themselves risk. Similar must low policy see simple teach. Call person ago.\nChild pass one reduce identify new kid. Dark show yes from. Deep store whose growth remain risk personal.',
    'email': 'cruzvincent@example.com',
    'phone_number': '268.230.4365',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Phillips',
    'Lisa Davis',
    'Kimberly Shelton',
    'Yesenia Patel',
    'Kyle White',
    'Samantha Clark',
    'Zachary Davis',
    'Hector Reynolds',
    'Tracy Poole',
    'Chris Schaefer',
],
    'json': {
    'name': 'Amanda Sherman',
    'address': '3762 Silva Village\nStevensonmouth, MN 93696',
},
    'key49850': 'value85854',
    'key73968': 'value63089',
    'key93900': 'value29418',
    'key97670': 'value42349',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Robert Chapman PhD',
    'address': '698 Brian Stream\nNew Jeffreyburgh, FM 25457',
    'text': 'International husband send. Certainly likely magazine stage provide score could far. Perhaps bar born. Family appear home character writer development choice.',
    'email': 'lbenton@example.com',
    'phone_number': '(505)821-6861x14189',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Griffith',
    'Jaime Maxwell',
    'Kevin Lee',
],
    'json': {
    'name': 'Leonard Lee',
    'address': '0227 Elliott Tunnel Suite 809\nLake Vanessaland, LA 34903',
},
    'key89951': 'value33872',
    'key59374': 'value82320',
    'key49275': 'value42883',
    'key92877': 'value83821',
    'key98512': 'value71994',
    'key40761': 'value26477',
    'key69283': 'value69634',
    'key40047': 'value14776',
    'key31828': 'value84417',
    'key48916': 'value36764',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Luke Schwartz',
    'address': '140 Larry Stream Suite 022\nStonemouth, PA 11378',
    'text': 'Structure begin like particular question country area knowledge. Available letter drug. So area three type young.\nAuthor where consumer body training. Risk suddenly wonder occur might without TV.',
    'email': 'wagnerbenjamin@example.org',
    'phone_number': '+1-280-511-3136x888',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Morales',
    'Crystal Hamilton',
],
    'json': {
    'name': 'Jimmy Ferguson',
    'address': '8389 Graham Via Apt. 837\nLake Brooketown, DC 06134',
},
    'key74336': 'value25160',
    'key1384': 'value86487',
    'key27104': 'value65069',
    'key44743': 'value14528',
    'key14333': 'value38070',
    'key32085': 'value89910',
    'key55616': 'value48636',
    'key47404': 'value44314',
    'key40582': 'value27253',
    'key25149': 'value69803',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Tamara Rodriguez',
    'address': '598 Amy Summit\nWest Jamesport, GA 12565',
    'text': 'Question state home democratic others. Second agree and.\nPopular no include many. Two western source support low away wear return.',
    'email': 'lorivazquez@example.org',
    'phone_number': '001-285-878-4254x4134',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Morgan',
    'Arthur Mccormick',
    'Angelica Mueller',
    'Antonio Graham',
    'Cheryl Butler',
],
    'json': {
    'name': 'Andre Hawkins',
    'address': '9784 Graves Courts Suite 785\nWest Paul, ID 78093',
},
    'key18207': 'value3265',
    'key20117': 'value5189',
    'key94294': 'value17653',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Jeffrey Smith',
    'address': '907 Jessica Extension\nColemanland, OH 32029',
    'text': 'Training necessary leave report. Amount agreement maybe move argue song. Beautiful rest interesting none. Focus lead knowledge finally.',
    'email': 'dixonbeth@example.com',
    'phone_number': '+1-598-382-8070',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Owens',
    'Juan Garrison',
    'Steven Cooper',
    'Erik Davis',
    'Jodi Arnold',
    'Paul Gardner',
],
    'json': {
    'name': 'Lisa Gates',
    'address': '80194 Greene Locks Suite 333\nCunninghamfurt, WI 51516',
},
    'key68743': 'value1952',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Brooke Miller',
    'address': '4894 Jennifer Parkways Apt. 378\nMorganborough, KS 74131',
    'text': 'Painting almost if truth travel oil teach. Reach why name chance. Begin Congress provide drive significant magazine treat call. Writer dog step effect.',
    'email': 'michael86@example.net',
    'phone_number': '001-599-926-8535',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Shane Johnson',
    'Amy Stuart',
    'Stacey Smith',
    'Christopher Miller',
    'Luis Mendoza',
    'Elizabeth Walker',
    'Todd Yang',
    'Kim Hammond',
    'Chad Robinson',
],
    'json': {
    'name': 'Monica Davis',
    'address': '4343 Lynch Highway\nBradmouth, NH 04698',
},
    'key61495': 'value64622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Savannah Smith',
    'address': '883 John Gardens Suite 463\nKristenstad, VI 18918',
    'text': 'Growth quality speech check day present. Company group administration sign. Prevent last low fund.\nLow Congress check hospital what. Trade its vote situation what.',
    'email': 'troydouglas@example.com',
    'phone_number': '+1-590-870-4386x00783',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Elijah Williams',
    'Brooke Williamson',
    'Joshua Clark',
],
    'json': {
    'name': 'Jessica Evans',
    'address': '704 Arnold Lane Apt. 366\nEast Tiffany, ID 74309',
},
    'key73067': 'value25198',
    'key91302': 'value61310',
    'key83082': 'value25967',
    'key34146': 'value87390',
    'key39353': 'value91406',
    'key11117': 'value80554',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Nicole Simmons',
    'address': '83565 Sarah Valley Apt. 383\nWoodland, ND 52039',
    'text': 'Data child decide inside million. Vote provide little he her film surface.\nTeam must project. Ability although pick. Eight ball oil policy.\nBall TV government exist woman reason.',
    'email': 'jennifer02@example.com',
    'phone_number': '413-506-3508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dana Moore',
    'Rebecca Zimmerman',
    'Kevin Taylor',
    'Sarah Brown',
    'Erika Jones',
    'Dorothy Jones',
    'Mr. Robert Booth',
    'Cheryl Davis',
    'Brad Schultz',
],
    'json': {
    'name': 'Mason Conner',
    'address': 'PSC 5109, Box 2992\nAPO AP 47835',
},
    'key11893': 'value98734',
    'key3188': 'value6668',
    'key78261': 'value68143',
    'key81050': 'value50468',
    'key10585': 'value20172',
    'key42391': 'value46725',
    'key5909': 'value26784',
    'key23241': 'value466',
    'key86272': 'value19385',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Jacob Mitchell',
    'address': '31415 Campbell Walk\nNew Richardside, MD 74826',
    'text': 'Yourself traditional write mouth. Recognize strong investment power building school record. Manager her successful.',
    'email': 'ashleybowman@example.net',
    'phone_number': '280.564.7507',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Shaffer',
    'Courtney Martinez',
    'Carol Armstrong',
    'John Sherman',
    'Angela Gibbs',
    'Stephanie Thomas',
    'Timothy Alexander',
    'Jeffrey Curry',
    'Daniel Hendrix',
],
    'json': {
    'name': 'Alexis Dunn',
    'address': '66728 Patrick Brooks\nLake Jennifer, MP 50606',
},
    'key50824': 'value92813',
    'key98549': 'value48816',
    'key88792': 'value39556',
    'key98415': 'value355',
    'key70769': 'value59373',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Cathy Floyd',
    'address': '57149 Benjamin Springs\nColeland, ME 52370',
    'text': 'Bill summer money when. Thousand letter marriage full nor choice forget. Political man medical loss new.',
    'email': 'edwardmartin@example.com',
    'phone_number': '(822)220-2607x79339',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Toni Smith',
    'Sarah Garrison',
    'Kyle Allen',
    'Mariah Brown',
    'Jennifer Johnson',
    'Thomas Hebert MD',
    'Jason Long',
    'Christine Garza',
    'Tammy Garcia',
    'Ashley Simmons',
],
    'json': {
    'name': 'Alexander Merritt',
    'address': 'USNV Thomas\nFPO AE 75603',
},
    'key19219': 'value98756',
    'key45748': 'value2261',
    'key36243': 'value77636',
    'key43587': 'value74450',
    'key21394': 'value76860',
    'key56881': 'value49703',
    'key85559': 'value34334',
    'key96500': 'value31810',
    'key9802': 'value51062',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Shaun Jones',
    'address': '6026 Joseph Field Apt. 997\nLewisburgh, GA 87474',
    'text': 'Long industry back grow. Class term wrong sometimes produce plant gas.\nSkill cold easy idea. Marriage view cost Mr improve model lose recently.',
    'email': 'jessica86@example.org',
    'phone_number': '(341)728-5417',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Gabriel Payne',
    'William Wilkins',
    'Stephanie Evans',
    'Angela Bell',
    'Dylan Gibbs',
    'Cassidy Mitchell',
    'Angela Wallace',
    'Stephanie Hunt',
],
    'json': {
    'name': 'Michelle Li',
    'address': '629 Maynard Tunnel\nJonmouth, ME 55423',
},
    'key69967': 'value88526',
    'key62764': 'value51950',
    'key53161': 'value62226',
    'key73321': 'value49082',
    'key38880': 'value5225',
    'key43746': 'value52156',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Tanya Lawrence',
    'address': '25798 Edward Landing\nLake Benjamin, ND 66137',
    'text': 'Wait top rule once everyone only allow. Interesting lead doctor sort national. Media artist model smile on go.\nCheck early talk.',
    'email': 'floresterri@example.org',
    'phone_number': '(562)860-1158x3745',
    'array_int_dynamic': [
    76289,
],
    'array_varchar_dynamic': [
    'Jordan Wilkinson',
    'Veronica Maldonado',
    'Betty Anderson',
    'Debbie Norris',
    'Connor Oneal',
    'Jessica Nichols',
    'Kristen Daniels',
    'Amanda Martinez',
    'Victoria Murphy',
],
    'json': {
    'name': 'Monica Sandoval',
    'address': '0506 Butler Station\nMurillofort, CT 48525',
},
    'key96625': 'value51348',
    'key73098': 'value29670',
    'key31393': 'value33085',
    'key62906': 'value87879',
    'key28258': 'value86745',
    'key2052': 'value41565',
    'key91550': 'value99196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Shane Weber',
    'address': '6193 Reid Squares Suite 911\nDylanmouth, PR 24906',
    'text': 'Go plan stock consumer part student. Everything matter glass network. She join for crime serve.\nPerform door two central. Series nor vote.',
    'email': 'masonzachary@example.org',
    'phone_number': '(656)574-3506x672',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Harper',
    'Jason Davis',
    'Karen Young',
    'Bryan Martinez',
    'Douglas Baker',
    'Anthony Tyler',
    'Jamie Watson',
],
    'json': {
    'name': 'David Rivera',
    'address': '33506 Martin Crossing Suite 630\nSouth Ericshire, VT 51728',
},
    'key2337': 'value77552',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Evelyn Miller',
    'address': '78161 Smith Route Apt. 639\nNorth Travis, NE 76853',
    'text': 'Seven door pattern physical so drug.\nUp born foreign. West positive second. Traditional shoulder conference us. Find send economic certain itself region need floor.',
    'email': 'peter83@example.com',
    'phone_number': '(746)719-5113x3580',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Diana Andersen',
    'Katherine Jacobs',
    'Robin Crawford',
    'Sandra Harris',
],
    'json': {
    'name': 'Derek Hall',
    'address': '1062 Hernandez Meadows\nSouth Shelby, MI 23191',
},
    'key23803': 'value56207',
    'key71268': 'value84321',
    'key82980': 'value57677',
    'key4470': 'value56121',
    'key2607': 'value28899',
    'key83037': 'value128',
    'key46525': 'value1094',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Makayla Johnson MD',
    'address': '328 Williams Lodge\nSouth Richardburgh, IL 07658',
    'text': 'Nearly daughter place table same research can.\nEnvironmental man issue money east. Whose include skin believe rich father. Apply record decide top TV full.',
    'email': 'rodriguezmichelle@example.net',
    'phone_number': '953.487.6039x397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Brooks',
    'Martin Farrell',
    'Jennifer Harris',
    'Karen Simmons',
],
    'json': {
    'name': 'Haley Liu DVM',
    'address': '9068 Harris Keys\nHaroldside, FL 37792',
},
    'key70250': 'value34200',
    'key22546': 'value57305',
    'key23507': 'value76455',
    'key22808': 'value34009',
    'key67380': 'value84954',
    'key24811': 'value99112',
    'key51033': 'value26354',
    'key1681': 'value92883',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Daryl Wallace',
    'address': '947 Cruz Junction Apt. 240\nNorth David, PR 78668',
    'text': 'Wear article over book. Wind activity traditional finally knowledge series. Black occur personal parent.\nMeasure throw may. Region family just each throughout. Field foreign or ready plant.',
    'email': 'jared53@example.com',
    'phone_number': '650.506.7086x1097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Morris',
],
    'json': {
    'name': 'Jay Barton',
    'address': '388 Ethan Curve Suite 599\nLake Henry, ME 71969',
},
    'key37983': 'value40612',
    'key3364': 'value860',
    'key42356': 'value35918',
    'key5761': 'value69217',
    'key84617': 'value20665',
    'key14331': 'value37399',
    'key97704': 'value38860',
    'key57928': 'value21673',
    'key56324': 'value62617',
    'key56167': 'value50047',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Richard Johnson',
    'address': '8034 Jackson Keys\nCallahanfort, CA 79032',
    'text': 'Raise stage herself boy exist later across long. Ten decision once give suffer phone respond Democrat. Deal center look indicate address response man.',
    'email': 'xsullivan@example.net',
    'phone_number': '5829527406',
    'array_int_dynamic': [
    1745,
],
    'array_varchar_dynamic': [
    'Vanessa Collins',
    'Matthew Wood',
],
    'json': {
    'name': 'Janet Fisher',
    'address': '34968 Lisa Garden Suite 464\nChristianton, MI 58616',
},
    'key68314': 'value37826',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Kevin Reed',
    'address': 'USNV Davis\nFPO AA 30445',
    'text': 'Teacher deep draw goal brother. Difference expect put represent. Design agreement land turn.\nCountry system ball policy authority before notice. Those seven trouble money.',
    'email': 'elizabethcruz@example.org',
    'phone_number': '625.211.2824x419',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brian Sanchez',
    'Christopher Velez',
    'Anita Johnson',
    'Benjamin Lopez',
    'Ashley Gonzalez',
    'Paula Gomez',
    'Margaret Simmons',
],
    'json': {
    'name': 'Crystal Delgado',
    'address': '383 Jon Ranch\nHernandezbury, SC 61323',
},
    'key79516': 'value98018',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Mary Choi',
    'address': '412 Richard Track\nNorth April, AK 38844',
    'text': 'Test really under hold among and. Your season most stand voice.\nMoment hospital factor wear decade major figure. Notice mouth seem. Although arrive likely energy play road letter.',
    'email': 'anamartinez@example.org',
    'phone_number': '+1-960-969-7632x8758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Meredith Rogers',
],
    'json': {
    'name': 'Nicole Ward',
    'address': '371 Dunn Tunnel\nSouth Holly, OH 64162',
},
    'key12520': 'value14099',
    'key79919': 'value12667',
    'key40864': 'value349',
    'key56912': 'value18722',
    'key32845': 'value13270',
    'key34251': 'value30789',
    'key84568': 'value25834',
    'key11428': 'value35771',
    'key99667': 'value63458',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Tammie Jackson',
    'address': '598 Angela Tunnel\nMaddenport, WY 68607',
    'text': 'Only chair thought north their national allow. Early woman rather one conference. Phone whole another pull ahead.\nImagine into film. Heart according around manage thus live husband.',
    'email': 'bbradley@example.net',
    'phone_number': '6057079469',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carol Diaz',
    'Jill Nelson',
    'Brittany Fox',
    'Mark Lloyd',
    'Joel Larson',
    'Ellen Vaughn',
    'Helen Hart',
    'Jason Parker',
    'Jane Reed',
],
    'json': {
    'name': 'Michelle Evans',
    'address': 'USS Patton\nFPO AA 60605',
},
    'key33486': 'value36526',
    'key67615': 'value48352',
    'key2330': 'value42867',
    'key39688': 'value46052',
    'key66842': 'value29251',
    'key59981': 'value58984',
    'key8832': 'value23909',
    'key5135': 'value59813',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Michael Hutchinson',
    'address': '884 Williams Skyway Suite 140\nMcclureshire, MT 98047',
    'text': 'Fly statement prove agency.\nWithin six here remain floor. Produce campaign walk white listen late industry out.\nSeek discussion perform future modern. Tonight enjoy building check perform usually.',
    'email': 'stephanie63@example.com',
    'phone_number': '546-275-5063x270',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Richard Marshall',
    'Ryan Mullins',
    'Bridget Gilbert',
    'Dr. Paula Brown',
    'Kim Willis',
    'Diane Wiley',
    'Michael Haynes',
    'Edward Rodriguez',
    'Kenneth Marks',
],
    'json': {
    'name': 'Timothy Larson',
    'address': '64099 Bishop Light Apt. 401\nNorth Aprilland, SD 85250',
},
    'key45150': 'value38400',
    'key88552': 'value5333',
    'key58534': 'value52854',
    'key50370': 'value61845',
    'key97957': 'value79114',
    'key2848': 'value5403',
    'key44398': 'value55627',
    'key24100': 'value75646',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Melissa Sanders',
    'address': '03378 David Summit\nRodriguezbury, MT 66007',
    'text': 'Region institution explain read avoid name.',
    'email': 'sherylramirez@example.com',
    'phone_number': '436.671.3832x65797',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Moore',
    'Jerry Ramirez',
    'Kristin Johnson',
    'Sarah Robinson',
    'Jeffrey Herrera',
    'Maria Roberts',
],
    'json': {
    'name': 'Nicole Adkins',
    'address': '24015 Andrea Canyon Apt. 654\nNew Brianna, CO 31003',
},
    'key41763': 'value68018',
    'key96479': 'value73883',
    'key75385': 'value45535',
    'key9827': 'value4901',
    'key10321': 'value70324',
    'key66082': 'value24107',
    'key41108': 'value34155',
    'key40897': 'value17921',
    'key45850': 'value27525',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Cynthia Garcia',
    'address': '101 Sara Unions Apt. 011\nEast Pamela, CT 24413',
    'text': 'Decision what beat more. Senior begin best.\nTime talk pretty nice she police. Ok spring Mrs thing million people. Center science not care seat.',
    'email': 'zoneill@example.org',
    'phone_number': '956.529.7288x226',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Hogan',
    'Rebecca Hahn',
    'Cassie Thomas',
    'John Holmes',
    'Janet Rodgers',
    'Julie Young',
    'Catherine Rivera',
    'Michelle Brown',
],
    'json': {
    'name': 'Ian Gray',
    'address': '32673 William Fall\nNorth Tylertown, PA 45790',
},
    'key65686': 'value17941',
    'key21697': 'value66132',
    'key9545': 'value25385',
    'key77850': 'value66911',
    'key55263': 'value64260',
    'key48041': 'value2166',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Michael Walter',
    'address': '512 Fernandez Spurs Apt. 114\nRachelfurt, PW 66242',
    'text': 'Care step hotel understand agree all whose. Everything week eye training choice memory feel. Feel ever central find mention.',
    'email': 'hbowen@example.com',
    'phone_number': '+1-567-581-8366x84596',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Maxwell Franco',
],
    'json': {
    'name': 'Kelly Hudson',
    'address': '625 Johnson Squares Apt. 922\nWest Danielton, SD 08627',
},
    'key45452': 'value10874',
    'key78389': 'value64563',
    'key31148': 'value64397',
    'key17572': 'value5662',
    'key18366': 'value23029',
    'key3942': 'value9120',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Joy Ford',
    'address': '8769 Graham Heights\nLake Maryland, MD 89644',
    'text': 'Catch word tough occur interview everybody. Turn city sometimes help image interview. Buy local relationship cut campaign show.',
    'email': 'donaldrodriguez@example.org',
    'phone_number': '+1-247-517-0857x48527',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Lee',
    'Abigail Davis',
    'Ashley Moreno',
    'Thomas Rodriguez',
],
    'json': {
    'name': 'Matthew Thompson',
    'address': '310 Abigail Extension\nNorth Victor, CO 43483',
},
    'key18651': 'value55931',
    'key34161': 'value11086',
    'key60672': 'value52099',
    'key74484': 'value29344',
    'key34861': 'value65236',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Krystal Espinoza',
    'address': '27842 Stephanie Rue\nOdomshire, PR 52439',
    'text': 'Early discussion town. Begin also happy near agent.\nMessage explain station fall. Off road though attack.\nEasy worry environment tell long law husband. Development computer explain theory east what.',
    'email': 'mortiz@example.net',
    'phone_number': '638-648-5951x699',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sherry Anderson',
    'Kyle Taylor',
    'Derek Sanchez',
    'Michael Hanson',
    'Lawrence Hoffman',
    'Kimberly Hurley',
    'Harold Johnson',
    'Lauren Shepherd',
    'Donna Smith',
],
    'json': {
    'name': 'Megan Montes',
    'address': '20558 Nelson Views\nGeorgeton, KS 94924',
},
    'key33582': 'value84159',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Carol Perry',
    'address': '66757 Weber Fall\nFrankton, IL 96944',
    'text': 'Police become east away statement enjoy. When amount home.\nSpend break onto paper. Start include recent law. Enough heart pattern forward art run front.',
    'email': 'xweaver@example.com',
    'phone_number': '466.462.2982x80392',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rhonda Campbell',
    'Terri Watts',
    'Curtis Summers',
    'Katherine Sanchez',
    'Jessica Foster',
    'Dakota Jones',
    'Austin Johnson',
    'Christopher Molina',
    'Michael Harrington',
    'Sharon Hernandez',
],
    'json': {
    'name': 'Veronica Adams',
    'address': '3087 Adams Mountain Apt. 362\nEast Mark, AK 99923',
},
    'key90844': 'value64920',
    'key69855': 'value18221',
    'key68700': 'value9391',
    'key18782': 'value31930',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Joseph Williams',
    'address': '21964 Robert Groves Apt. 749\nWardport, PA 59019',
    'text': 'Professional hold her apply. Specific bad finally practice southern.\nMaintain per cultural us support. Over whom popular stand employee.',
    'email': 'gina47@example.net',
    'phone_number': '516.653.4961x398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Barnes',
    'Bradley Cruz',
],
    'json': {
    'name': 'Robert Martinez',
    'address': '3536 William Plain\nNatalieburgh, WY 79411',
},
    'key16842': 'value46060',
    'key81166': 'value92143',
    'key79012': 'value5141',
    'key12089': 'value91351',
    'key92266': 'value72323',
    'key92907': 'value53504',
    'key8038': 'value25759',
    'key38015': 'value17859',
    'key56982': 'value68512',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Nancy Hubbard',
    'address': '35743 Gibson Club\nLake David, IN 88297',
    'text': 'West want word hear. Machine beat up day.\nMajor five live information us than. Deal cultural base woman its. But occur employee quality.',
    'email': 'williambradford@example.net',
    'phone_number': '+1-540-923-3193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Bowman',
    'Bryan Thomas',
    'Barry Castro',
    'Robert Green',
    'Natalie Odonnell',
    'Tom Kelly',
    'Cathy Gregory DDS',
    'Alexandra Little',
    'Jennifer Hill',
],
    'json': {
    'name': 'Brittany Beard',
    'address': '49904 James Fork Apt. 424\nNorth Nathanielland, OK 97940',
},
    'key63812': 'value13165',
    'key29497': 'value2445',
    'key65038': 'value62722',
    'key50965': 'value7226',
    'key38576': 'value17834',
    'key33556': 'value37392',
    'key65931': 'value22344',
    'key95826': 'value73732',
    'key76218': 'value68922',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Heather Hall',
    'address': 'USNS Gray\nFPO AA 86247',
    'text': 'Suddenly official almost man wait tend. Cell despite pattern body despite little.',
    'email': 'bdavis@example.net',
    'phone_number': '001-272-953-0793x6753',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Perkins',
    'Jennifer English',
    'Heather Mcclain',
    'Rebecca Clark',
],
    'json': {
    'name': 'Corey Rodriguez',
    'address': '31986 Amy Run\nJanicemouth, NM 37353',
},
    'key2205': 'value45242',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Michelle Hurley',
    'address': '869 Sandra Row\nCunninghamburgh, MN 79289',
    'text': 'Appear light pull over site color area. Just new protect.\nAny matter serve down college five nice where. Find woman thank evidence. Itself charge section place.',
    'email': 'williamclark@example.com',
    'phone_number': '865.855.2323',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Potter',
    'Melissa Valencia MD',
    'John Peterson',
    'Lisa Farley',
    'Beth Martinez',
    'Harry Lawrence',
    'Grant Brooks',
],
    'json': {
    'name': 'Amanda Allen',
    'address': '411 Hudson Square Suite 146\nDeborahton, GA 98931',
},
    'key92993': 'value10310',
    'key62231': 'value22695',
    'key65200': 'value20778',
    'key35088': 'value81162',
    'key97650': 'value27508',
    'key95668': 'value10211',
    'key96357': 'value11097',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Raymond Davis',
    'address': '70583 Smith Points Suite 818\nAndersonton, NC 59721',
    'text': 'Positive to defense above receive sea discuss. Opportunity parent firm too item everything front.',
    'email': 'daughertyleah@example.org',
    'phone_number': '001-877-745-4680x02136',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Meyer',
    'Sergio Bowman',
    'Ryan Gibson',
    'Ashley Smith',
],
    'json': {
    'name': 'Angela Grimes',
    'address': '6861 Douglas Garden Apt. 687\nDaviston, SC 81699',
},
    'key29773': 'value26737',
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
    'RequestId': '66a24f63-62f1-11f0-834b-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_27_417398NdoOYLAp',
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
        """测试请求 3 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '5fe82590-62f1-11f0-863e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_27_417398NdoOYLAp',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > -100 and uid < 100]_1752744939.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid100AndUid1001752744939Json()
    test.run_tests()
