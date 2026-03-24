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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-100-2]_1752744116_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-100-2]_1752744116.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl3210021752744116Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-100-2]_1752744116.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-100-2]_1752744116.json"
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
    'RequestId': '7b7fad3d-62ef-11f0-9974-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_54_715490VlyyESHj',
    'dimension': 32,
    'primaryField': 'url',
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
    'RequestId': '7ba312fb-62ef-11f0-8c2a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_54_715490VlyyESHj',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Jane Bush',
    'address': '65039 Williams Ranch Apt. 469\nHutchinsonport, CT 06805',
    'text': 'Your church once year fear. Best stuff challenge professor. Beautiful full answer meeting bank maybe.\nPaper generation American today tough serious decide. Must where baby.',
    'email': 'anthony12@example.net',
    'phone_number': '558-750-1829x7536',
    'array_int_dynamic': [
    34536,
],
    'array_varchar_dynamic': [
    'Dr. Cassandra Sheppard',
    'Courtney Jackson',
    'Stephanie Nicholson',
    'John Patterson',
    'Brian White',
    'Samuel Harris',
    'Adrian Wilkinson',
    'Kristen Atkinson',
],
    'json': {
    'name': 'Douglas Smith',
    'address': '13740 Harrison Rest Suite 506\nPort Ashley, IA 41452',
},
    'key52913': 'value14693',
    'key75669': 'value43221',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Alfred Johnson',
    'address': '6454 Nichole Viaduct\nJamesport, NY 34786',
    'text': 'For we heavy where. My risk specific interest skill perhaps.\nSpace stand star. Red society truth television sound argue argue scene.',
    'email': 'katelyn57@example.net',
    'phone_number': '3587214286',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Terrance Nelson',
    'Shelley Murphy',
    'Michelle House',
    'Jeremy Lowe',
    'Jacob Brady',
    'Scott Howell MD',
    'Melissa Terry',
    'Jamie Duke',
],
    'json': {
    'name': 'Jennifer Sanchez',
    'address': '31613 Michael Forest\nPetershaven, NC 02542',
},
    'key34446': 'value23525',
    'key79983': 'value48680',
    'key54992': 'value59457',
    'key86814': 'value76103',
    'key52868': 'value74694',
    'key67515': 'value84569',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Alex Morales',
    'address': '8731 Smith Port\nGutierrezside, PW 45791',
    'text': 'Scene ball option. Still however more four blue third certainly green. With opportunity law always network.\nDifferent full window smile threat. Anything specific way serious bring wall.',
    'email': 'bennettelizabeth@example.org',
    'phone_number': '256.773.4913x3733',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Adam Burke',
    'Michelle Oliver',
],
    'json': {
    'name': 'Holly Price',
    'address': '1151 Taylor Branch Apt. 866\nSouth Tannerville, WA 48943',
},
    'key33147': 'value70140',
    'key63837': 'value51933',
    'key98416': 'value29355',
    'key9543': 'value86137',
    'key25318': 'value73640',
    'key94608': 'value5473',
    'key52407': 'value88321',
    'key29100': 'value24320',
    'key97043': 'value49571',
    'key66596': 'value62117',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Michelle Torres',
    'address': '352 Lewis Gardens Suite 980\nNorth Paul, GU 05348',
    'text': 'Opportunity hundred in. As five but establish. Story for go maintain must another involve should.\nAction say method style this student economic which. Which finally place exactly.',
    'email': 'hardinerik@example.com',
    'phone_number': '+1-304-436-9226',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Hudson',
    'Justin Brown DVM',
    'Daniel Brown',
    'Amy Thompson',
],
    'json': {
    'name': 'Eric Washington',
    'address': '054 Parker Plaza Suite 523\nNorth Meganview, VT 54251',
},
    'key68210': 'value43720',
    'key68313': 'value93411',
    'key76559': 'value49051',
    'key88978': 'value74282',
    'key34132': 'value6811',
    'key52805': 'value74886',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Bethany Chang',
    'address': '26712 Regina Port\nLake Brandonville, MA 86316',
    'text': 'Kid child however range nature determine. Two hotel among author. Guy young long remain.\nTv father yes machine him line. Deep same husband under meeting impact state behavior. She ago over energy.',
    'email': 'prichardson@example.com',
    'phone_number': '001-815-270-0967',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Judy Beasley',
    'Cheryl Riley',
    'Meagan Wood',
    'Matthew Shaffer',
    'Sarah Thompson',
    'Jenna Huang MD',
    'Courtney Jones',
],
    'json': {
    'name': 'Jonathon Ramirez',
    'address': '26189 Ronnie Gateway Suite 269\nLake Austinland, WA 29999',
},
    'key92614': 'value23745',
    'key28033': 'value19467',
    'key60905': 'value88135',
    'key6054': 'value64449',
    'key26299': 'value82560',
    'key785': 'value42274',
    'key65465': 'value73055',
    'key91718': 'value10491',
    'key42296': 'value92189',
    'key31150': 'value22148',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Jason Cameron',
    'address': '879 Pope Overpass Suite 583\nEmmaside, NE 73122',
    'text': 'Machine piece reduce deep Democrat. Later suffer hand it.\nImpact southern take officer suddenly day. Number matter compare analysis marriage food. Become concern more purpose pretty throughout.',
    'email': 'laurie25@example.net',
    'phone_number': '+1-284-642-3594x877',
    'array_int_dynamic': [
    85375,
],
    'array_varchar_dynamic': [
    'Kayla Shaffer',
    'Harold Medina',
    'Janice Lin',
    'Lauren Hawkins',
    'Elizabeth Whitaker',
    'Ashley Rogers',
    'Laurie Hall',
    'Casey Stein',
    'Linda Harper',
],
    'json': {
    'name': 'Brittany Brooks',
    'address': '55004 Gutierrez Cape\nMorganburgh, LA 31506',
},
    'key62653': 'value6541',
    'key35218': 'value51304',
    'key38731': 'value33847',
    'key54993': 'value42493',
    'key34073': 'value88481',
    'key21745': 'value41775',
    'key67395': 'value38053',
    'key52351': 'value60071',
    'key28820': 'value36617',
    'key78315': 'value66557',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Roger Sutton',
    'address': '97402 Gerald Meadows Apt. 694\nPowershaven, NC 28600',
    'text': 'Republican think enter appear raise live attorney. Event play where old.\nAway seven various these shake democratic. Between car describe finish economy west sister.',
    'email': 'nathancampbell@example.org',
    'phone_number': '578-619-4600x27363',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Moore',
    'Mr. Kyle Hughes',
    'Lindsey Wells',
    'Matthew Elliott',
    'Jacob Jones',
    'Adam Maxwell',
    'Ronnie Mitchell',
    'Phillip Burton',
    'Steven Rodriguez',
    'Allen Burke',
],
    'json': {
    'name': 'Margaret Barron',
    'address': '2360 Frederick Union\nDavidmouth, RI 56230',
},
    'key90744': 'value43043',
    'key86133': 'value19219',
    'key75530': 'value61452',
    'key73620': 'value54966',
    'key17143': 'value3210',
    'key83637': 'value70042',
    'key4770': 'value50089',
    'key48492': 'value97544',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Christian Turner',
    'address': 'Unit 7211 Box 5578\nDPO AP 73259',
    'text': 'Cold soon fire nation consider probably worker. Director safe year service company reflect fine.',
    'email': 'paul34@example.com',
    'phone_number': '+1-879-677-3380x0413',
    'array_int_dynamic': [
    53885,
],
    'array_varchar_dynamic': [
    'Tiffany Bauer',
    'Christopher Montes',
    'Jerry Hawkins',
    'Matthew Benjamin',
],
    'json': {
    'name': 'Mr. Jeffrey Martinez II',
    'address': '27547 Jason Station\nNew Amber, GA 62560',
},
    'key36097': 'value33454',
    'key61092': 'value12191',
    'key10746': 'value52805',
    'key71257': 'value53451',
    'key29430': 'value16934',
    'key58016': 'value33957',
    'key16152': 'value20061',
    'key7499': 'value980',
    'key20757': 'value99337',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Lisa Brock',
    'address': '4927 Michelle Vista\nJosehaven, MO 25540',
    'text': 'Management include occur. To citizen win rate last.\nSouthern nearly use us majority. Time worker face if situation.',
    'email': 'fadams@example.com',
    'phone_number': '3363747209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dana Roth',
    'Manuel Robinson',
    'Michelle Wood',
    'Timothy Hill',
    'Tammy Edwards',
    'James Marshall',
    'Thomas Shah',
    'Christopher Haney',
],
    'json': {
    'name': 'Jason Smith',
    'address': '1622 Edwards Trace\nNatalieside, MA 24237',
},
    'key27088': 'value95131',
    'key41559': 'value9468',
    'key70706': 'value34955',
    'key90540': 'value98192',
    'key75780': 'value22901',
    'key7314': 'value65689',
    'key56849': 'value51352',
    'key66404': 'value48177',
    'key41275': 'value52131',
    'key78002': 'value16184',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Stephanie Park',
    'address': '77483 Lee Motorway\nCassandramouth, VI 25513',
    'text': 'Your up make audience. Nor determine east maintain car Republican nice. Western morning spend specific really foreign week. Appear continue day question kind the.',
    'email': 'elong@example.org',
    'phone_number': '001-675-399-9721',
    'array_int_dynamic': [
    18865,
],
    'array_varchar_dynamic': [
    'Kristen Scott',
    'Christina Mcneil',
    'Jesse Taylor',
    'Amy Wheeler',
    'Marcus Cross',
    'Debra Jones',
    'Robert Howe',
    'Jacqueline Page',
    'Kelly Oneal',
],
    'json': {
    'name': 'Jacob Martinez',
    'address': '12669 Benjamin Pine\nKevinville, ID 40903',
},
    'key88895': 'value26578',
    'key38192': 'value19413',
    'key28721': 'value5859',
    'key4612': 'value74585',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'James Martinez',
    'address': '265 Burns Shore Suite 574\nNew Lauren, IA 66144',
    'text': 'Join threat choice effect most sing chair. Skill ok certain now road. Black mean stand as. Fall threat indicate design foot happen director home.',
    'email': 'sabrina66@example.org',
    'phone_number': '(243)221-7939x57253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Soto',
    'David Sellers',
    'Robert Chapman',
],
    'json': {
    'name': 'Elizabeth Leach',
    'address': '77942 Rebecca Club Suite 249\nEast Wayne, DE 88682',
},
    'key59490': 'value68799',
    'key42881': 'value52142',
    'key68701': 'value81257',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Robert Norris',
    'address': '9690 Bowman Mews Apt. 017\nLewishaven, GU 02631',
    'text': 'Believe miss finish. Window should game blue oil.\nBar tough turn people little ok wish.\nLearn tough training thought begin. Check make tend. Hold item buy lead statement usually.',
    'email': 'berryjonathan@example.org',
    'phone_number': '390.853.7832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Julia Jackson',
    'Julia Gonzalez',
    'Jose Simmons Jr.',
    'Heather Parker',
    'Lisa Swanson',
    'Timothy Roberts',
    'Theresa Brewer',
],
    'json': {
    'name': 'Julie Miller',
    'address': '184 Hernandez Neck\nLibury, WI 16933',
},
    'key35720': 'value12205',
    'key7197': 'value4031',
    'key24191': 'value55714',
    'key8778': 'value61631',
    'key95562': 'value93805',
    'key66641': 'value90627',
    'key1028': 'value43318',
    'key32619': 'value74012',
    'key17753': 'value19113',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Rebecca Bowman',
    'address': '9810 Reed Prairie Suite 558\nSimmonstown, TX 05594',
    'text': 'Though professional hundred enjoy. Could set hour mention.\nWrite old record five require word glass at.',
    'email': 'elizabeth79@example.com',
    'phone_number': '462-812-6470x291',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lynn Saunders',
    'Gregory Phelps',
    'Lindsey Gomez',
    'Allison Weber',
    'Krista Davis',
],
    'json': {
    'name': 'Tiffany White',
    'address': '5241 Cody Street\nKeithmouth, WV 27740',
},
    'key73355': 'value12205',
    'key46343': 'value15216',
    'key93369': 'value60290',
    'key78146': 'value85024',
    'key24660': 'value19476',
    'key7402': 'value72371',
    'key2135': 'value30192',
    'key86359': 'value58830',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Natalie Allen',
    'address': '1869 Garcia Rue\nSouth Davidchester, WI 72459',
    'text': 'This remain wear history guy born research. Responsibility moment while purpose wonder far.\nQuality toward young all want strategy.\nImage glass right group want black. More consumer value medical.',
    'email': 'opayne@example.net',
    'phone_number': '2166324673',
    'array_int_dynamic': [
    83005,
],
    'array_varchar_dynamic': [
    'Antonio Holt',
    'Jody Nelson',
    'Dawn Phillips',
    'Lori Taylor',
    'Donald Williams',
    'William Norman',
    'James Kline',
    'Barbara Todd',
    'Kevin Thomas',
],
    'json': {
    'name': 'Patricia Summers',
    'address': 'USNS Morrow\nFPO AE 98202',
},
    'key88348': 'value8143',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Debra Rogers',
    'address': '18870 Jones Springs\nSarahbury, MP 65671',
    'text': 'Possible black evidence without clearly. To business culture. Necessary it cost start spend cell.',
    'email': 'littlekathryn@example.com',
    'phone_number': '556.288.6347',
    'array_int_dynamic': [
    70922,
],
    'array_varchar_dynamic': [
    'Eric Patrick',
    'Mark Wright',
    'Joshua Smith',
],
    'json': {
    'name': 'Nicholas Murphy',
    'address': '456 Angela Burg\nStewartside, IN 05464',
},
    'key55541': 'value35268',
    'key94436': 'value35023',
    'key74274': 'value67890',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Chad Anderson',
    'address': '7532 Kristin Vista\nNew Allison, KS 05528',
    'text': 'Network stage have. Painting which sea task during.\nWin national soldier improve determine such management. Bit sometimes firm raise on. Spend issue agent.',
    'email': 'webbrichard@example.org',
    'phone_number': '301-367-4993x110',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Logan',
    'Stephanie Wolfe',
    'Brandon Schultz',
    'Colleen Wright',
    'Mercedes Perez',
    'Theresa Coleman',
    'Elizabeth Gibbs',
    'Kyle Carson',
    'Aaron Goodman',
],
    'json': {
    'name': 'Dalton Garza',
    'address': '667 Stewart Meadows\nNorth Hollybury, MS 25192',
},
    'key15200': 'value6791',
    'key57198': 'value64945',
    'key27806': 'value95576',
    'key26737': 'value56443',
    'key19765': 'value64851',
    'key97187': 'value34229',
    'key80026': 'value3534',
    'key72602': 'value36191',
    'key25949': 'value98316',
    'key64825': 'value4520',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Ricardo Mcgee MD',
    'address': '3120 John Rue Apt. 617\nMoniquefort, TN 61423',
    'text': 'Nor decide discuss TV claim moment.\nRoad state probably term center. Good night glass keep.',
    'email': 'ecline@example.net',
    'phone_number': '6028747380',
    'array_int_dynamic': [
    71431,
],
    'array_varchar_dynamic': [
    'Corey Wall DVM',
    'Kelly Anderson',
    'Sarah Walton',
],
    'json': {
    'name': 'Robert Walker',
    'address': '63829 Linda Mountain\nEmilyland, AS 28551',
},
    'key35804': 'value4304',
    'key79256': 'value72817',
    'key92866': 'value10117',
    'key68371': 'value38813',
    'key29426': 'value85007',
    'key71086': 'value74209',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Ann Jones',
    'address': '0576 Walker Neck Suite 572\nGibsonberg, ND 33429',
    'text': 'A detail interview them look those at. Toward talk us meet. Part partner not save physical series quickly ago. Himself rich up front deep long.',
    'email': 'yjackson@example.net',
    'phone_number': '687-502-5629x558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Reynolds',
    'Michelle Benson',
    'Christine Lee',
    'Stephanie Coffey',
    'Raymond Huffman',
],
    'json': {
    'name': 'Mitchell Galloway',
    'address': '48261 Donna Parkways Apt. 563\nNorth Rachel, ND 88561',
},
    'key37053': 'value65409',
    'key92072': 'value36483',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Sylvia Dixon',
    'address': 'USNV Sanchez\nFPO AE 30012',
    'text': 'Life happen fill clearly even decision anyone make. Happy both during production defense.\nWay year happy under. Activity college test choose event. Send capital increase last.',
    'email': 'kphillips@example.org',
    'phone_number': '+1-298-625-7433x6128',
    'array_int_dynamic': [
    77138,
],
    'array_varchar_dynamic': [
    'Melissa Griffin',
    'George Burns',
    'Melissa Rosales',
    'Brandon Morgan',
    'Jennifer Robinson',
    'Melissa Copeland',
    'Tammie Guerra',
    'Jennifer Williamson',
    'Vincent Newman',
],
    'json': {
    'name': 'Clinton Coleman',
    'address': '95233 Harmon Mill\nPrattland, VI 29281',
},
    'key68204': 'value19297',
    'key76479': 'value78210',
    'key94893': 'value38074',
    'key18610': 'value23599',
    'key98757': 'value56499',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Amanda Wood',
    'address': '518 Williams Way Suite 541\nWest Alexanderside, UT 34573',
    'text': 'Situation challenge amount page. Simple run too major where. Author figure lawyer ten past central.',
    'email': 'nicholscheyenne@example.org',
    'phone_number': '3559441367',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Martin',
    'Steven Nelson',
    'Robert French',
],
    'json': {
    'name': 'Rebecca Johnson',
    'address': '2921 Pierce Shore\nRussellview, MI 64038',
},
    'key30092': 'value8181',
    'key72729': 'value60630',
    'key35212': 'value86201',
    'key96234': 'value3169',
    'key42098': 'value71606',
    'key65652': 'value39585',
    'key3261': 'value55881',
    'key88488': 'value53356',
    'key14056': 'value39751',
    'key93663': 'value764',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Aaron Briggs',
    'address': '0818 David Streets Apt. 353\nNew Derektown, AL 70075',
    'text': 'Drive expect east why even from. Read by forward population there listen truth.\nStill fill culture stuff case site somebody act.',
    'email': 'qolson@example.com',
    'phone_number': '307.679.0769x8485',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Garcia',
    'Jacob Maldonado',
    'Shannon Pearson',
    'Margaret Blevins',
    'Michael Solomon',
    'Madison Davis',
],
    'json': {
    'name': 'Joshua Romero',
    'address': '23943 Elizabeth Gateway\nHillview, AR 46248',
},
    'key33348': 'value3105',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Lauren Watson',
    'address': '346 Cassandra Mission\nSuarezton, AL 00983',
    'text': 'But third money.\nPush including sign conference. Drop role west bill show direction. Only mouth finish practice.',
    'email': 'jenniferzavala@example.org',
    'phone_number': '(202)937-8595x586',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Smith',
    'Jennifer Maynard',
    'Kimberly Cruz',
    'Erika Santos',
    'Michael Allen',
    'Samantha White',
],
    'json': {
    'name': 'Mary Boyd',
    'address': '626 Johnson Via Suite 602\nKellyburgh, VT 36265',
},
    'key46542': 'value47341',
    'key82574': 'value91303',
    'key63524': 'value12849',
    'key93661': 'value71039',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Jessica Sutton',
    'address': '81554 Hamilton Lane Suite 890\nNew Lesliechester, ME 76313',
    'text': 'Organization city road nor after TV.\nAgain improve try organization. Somebody know far public. Town customer employee attention report grow table.',
    'email': 'samuel89@example.net',
    'phone_number': '(806)460-1646x749',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Megan Mcdonald',
    'Victor Cortez',
    'Emily Little',
    'Sharon Washington',
    'Pamela Pearson',
    'Aaron Martinez',
    'Brenda Spears',
    'James Robertson',
    'Danielle Barber',
],
    'json': {
    'name': 'Dennis Stuart',
    'address': '34533 Robert Stravenue Apt. 770\nNew Lorraine, IN 39014',
},
    'key50840': 'value92017',
    'key22313': 'value26661',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Kelsey Jackson',
    'address': '11862 Debbie Freeway\nGarciamouth, SC 80460',
    'text': 'Book red beyond per take likely. Finally bad chair after.\nTend just between draw player. Despite may country design.',
    'email': 'melissa91@example.com',
    'phone_number': '(607)552-9859x533',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Powell',
    'Christopher Swanson',
    'Eric Ward IV',
    'Timothy Johnson',
    'Victoria Bryant',
    'Mackenzie Reed',
    'Natalie Johnson',
    'Paul Miller',
    'James Esparza',
    'Brandon Lambert',
],
    'json': {
    'name': 'Michael Ward',
    'address': '510 Alejandra Canyon Suite 259\nThomasburgh, ID 75969',
},
    'key44272': 'value33415',
    'key30654': 'value26597',
    'key40076': 'value96916',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Vincent Whitaker',
    'address': '96079 Sarah Squares\nRiverashire, PA 02461',
    'text': 'Month according growth situation listen. Age her involve future toward fight. Million work worry past.\nLess song serve until. Physical sport small consumer.\nOld of yourself step.',
    'email': 'joshuabullock@example.org',
    'phone_number': '960-999-5676x6382',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Freeman',
    'Troy Wallace',
],
    'json': {
    'name': 'Melissa Gibson',
    'address': '269 Randy Landing Apt. 480\nWesleyport, IA 38008',
},
    'key51506': 'value57684',
    'key95398': 'value69515',
    'key25576': 'value29630',
    'key61854': 'value96263',
    'key39738': 'value42719',
    'key14541': 'value62361',
    'key42180': 'value92004',
    'key65317': 'value83592',
    'key23004': 'value74819',
    'key68442': 'value80396',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Mrs. Melanie Copeland',
    'address': '417 Nguyen Island\nSouth Jamesfurt, IL 20499',
    'text': 'Enter smile that culture task. They state cultural opportunity.\nDiscuss open move long I. Policy key money career. Write book threat produce program.',
    'email': 'jacksonjessica@example.org',
    'phone_number': '325.675.4826x2440',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Madeline Washington MD',
    'April Holden',
    'David Sellers',
    'Savannah Hodge',
    'Michael Freeman',
    'Christina Evans',
],
    'json': {
    'name': 'Barbara Allen',
    'address': '11962 Williams Curve\nBakerfort, AZ 51815',
},
    'key22632': 'value25074',
    'key99336': 'value84494',
    'key52701': 'value8557',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Allison Roth',
    'address': '766 Serrano Knoll Apt. 697\nWest Bettymouth, OH 98760',
    'text': 'To political first throw type. Yard reflect agency study spend they.\nGuess free clear skill pretty group big each. Her business move movie marriage. Entire accept both develop.',
    'email': 'murraypatricia@example.com',
    'phone_number': '+1-639-793-2303x2465',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Porter',
    'Kelsey Armstrong',
    'Kara Anderson',
    'Matthew Simpson',
    'Stephen Freeman',
],
    'json': {
    'name': 'Justin Robinson',
    'address': 'PSC 2319, Box 1312\nAPO AA 33130',
},
    'key59805': 'value98371',
    'key5344': 'value69833',
    'key69886': 'value86976',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Robert Olsen',
    'address': '0662 Delgado Gardens Apt. 308\nLoweryberg, DE 70015',
    'text': 'Book politics concern simple cell. Example collection kitchen finally even case. Coach next purpose even newspaper evening.',
    'email': 'tmiller@example.com',
    'phone_number': '+1-236-473-5513x508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Johnson',
    'Kerry Solomon',
    'David Flowers',
    'Alejandro Khan',
    'Mr. Edwin Robinson',
    'Mariah Mayer',
    'Tiffany Green',
    'Ruth Jackson',
],
    'json': {
    'name': 'Daniel Moore',
    'address': '8615 Jordan Views\nPort Andrea, ID 06691',
},
    'key57279': 'value27559',
    'key67649': 'value61217',
    'key66935': 'value93836',
    'key9157': 'value20378',
    'key25782': 'value78844',
    'key67086': 'value50674',
    'key72764': 'value48625',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Hector Hensley',
    'address': '17508 Haley Turnpike\nRachelchester, DE 60317',
    'text': 'Design recently wait college deep something natural. Movie lot stop amount.\nCurrent myself recent can do out. Too owner huge thought.',
    'email': 'thomas29@example.com',
    'phone_number': '517-588-5460',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Lindsay Hall',
    'Carolyn Mcguire',
],
    'json': {
    'name': 'David Thomas',
    'address': '7335 Wood Locks\nWest Ann, SC 24790',
},
    'key5991': 'value47987',
    'key2383': 'value30034',
    'key95471': 'value69146',
    'key20694': 'value74236',
    'key26797': 'value99910',
    'key93766': 'value74533',
    'key61444': 'value72781',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Donna Nichols',
    'address': '51525 Williams Centers Suite 794\nAndrewland, NC 96533',
    'text': 'Idea throw cultural ago. Send top tough quickly phone. Cell present fund serious.\nKitchen alone range. Plant cup eat compare record service. Article car hotel beat.',
    'email': 'jamesfritz@example.net',
    'phone_number': '(307)233-8363x607',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amy Alvarez',
    'Ronald Dominguez',
    'Stuart Webb',
    'Kathleen West',
    'Brian Bowers',
    'Veronica Williams',
    'Bridget Woods',
    'Amy Williams',
    'Todd Howard MD',
],
    'json': {
    'name': 'Amanda Goodwin',
    'address': 'PSC 3052, Box 2827\nAPO AE 55703',
},
    'key13424': 'value68769',
    'key29082': 'value28917',
    'key28490': 'value90102',
    'key72037': 'value23831',
    'key32030': 'value8844',
    'key93780': 'value48667',
    'key11463': 'value99053',
    'key48713': 'value9305',
    'key94260': 'value95935',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Kathleen Patterson',
    'address': '66036 Conner Mountains\nSouth Eric, AZ 35786',
    'text': 'Sport Mr happy throw lose college west. Purpose cut upon begin. Guy argue else gun television born.\nSister imagine enjoy bank because. Under its summer eat. Past Democrat soon include medical board.',
    'email': 'shane92@example.com',
    'phone_number': '(960)803-5816x8056',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Laura Lawrence',
    'Melanie Ramirez',
    'Mark Waters',
    'Jason Howard',
    'Susan Castillo DVM',
    'Ruth Webb',
    'Joseph Williams',
    'Catherine Blake',
    'Lacey Acosta',
    'Megan Nguyen',
],
    'json': {
    'name': 'Connie Ray',
    'address': '0838 Carl Light\nNew Robertview, AR 42103',
},
    'key97129': 'value80386',
    'key38101': 'value90747',
    'key3624': 'value87950',
    'key21343': 'value22075',
    'key28764': 'value44294',
    'key11867': 'value83198',
    'key90922': 'value31296',
    'key52093': 'value90380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Shannon Frye',
    'address': '571 Jody Circle Suite 325\nLake Jasmin, MH 51083',
    'text': 'Pay practice itself throughout. Candidate response study care north PM result. Rule he article various. Life candidate author ok include space.',
    'email': 'valerie34@example.com',
    'phone_number': '(795)846-2376x9569',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Caitlin Watson',
    'Steven Davis',
],
    'json': {
    'name': 'Charles Graham',
    'address': '471 Kerr Circles\nWest Wanda, GU 45089',
},
    'key44857': 'value20898',
    'key98049': 'value93867',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Joanna Carson',
    'address': '578 Johnson Port Apt. 979\nEast Jesse, MN 24682',
    'text': 'Land too time important maybe section. Consider key top add meeting two.\nUse sport could sport step officer. Fire election enter budget serve herself. Under chair blood could sell right attention.',
    'email': 'rjones@example.net',
    'phone_number': '(855)343-4210x671',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Turner',
],
    'json': {
    'name': 'Kyle Smith',
    'address': 'USNV Thomas\nFPO AA 38138',
},
    'key38079': 'value70444',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Jessica Gomez MD',
    'address': '8268 Joseph Path\nNew Emilyton, ND 03481',
    'text': 'Picture necessary green. Serious share bag his make. Wait price require close prove.\nEither however eight senior see. Rule hospital research.',
    'email': 'crystal31@example.org',
    'phone_number': '939-374-9802',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gary Robinson',
    'Alexis Pope',
    'Katie Higgins',
    'Stephanie Booth',
    'Mary Gallagher',
    'Christopher Allen',
],
    'json': {
    'name': 'Andrew Little',
    'address': '237 Morrison Court Suite 504\nPort Davidside, RI 95227',
},
    'key93996': 'value45931',
    'key54565': 'value67200',
    'key98126': 'value81903',
    'key53798': 'value75526',
    'key27712': 'value10972',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Phillip Anderson',
    'address': '109 Hopkins Underpass\nRyanfort, GU 50215',
    'text': 'Manager himself region decision the green. Student difference dog order plan police sound.\nThat purpose reason specific star plant. Much professor development beat be last kitchen.',
    'email': 'qanderson@example.net',
    'phone_number': '295.358.3583x30289',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Ortiz',
    'William Hoffman',
    'Robert Burns',
    'David Woods',
    'Scott Moses',
    'Tina Davis',
    'John Stevens',
],
    'json': {
    'name': 'Patty Wilson',
    'address': '51848 Beth Via Suite 151\nLake Jennabury, SD 60369',
},
    'key6842': 'value76430',
    'key21537': 'value7023',
    'key69779': 'value22352',
    'key33241': 'value17104',
    'key29230': 'value26682',
    'key41044': 'value75748',
    'key37124': 'value42373',
    'key37228': 'value44629',
    'key29304': 'value11837',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Dakota Johnson',
    'address': '2373 Steven River\nLake Toddside, DC 82857',
    'text': 'Book voice current professor admit. Reality light man third bar certainly down. Ground east know minute whether its evening child.',
    'email': 'patrickamy@example.com',
    'phone_number': '+1-394-827-1063x6769',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Terry White',
    'David Sandoval',
],
    'json': {
    'name': 'David Hernandez',
    'address': '82614 Sims Spurs Apt. 647\nNew Brittneyshire, ME 14628',
},
    'key36051': 'value95245',
    'key94789': 'value52794',
    'key74940': 'value87764',
    'key29176': 'value53904',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Tammy Jones',
    'address': '6596 Sherry Wells\nNorth Jamesbury, NH 23831',
    'text': 'Themselves lot scene above. Scientist air my. Protect prove know human along.\nHot man over about. Stop friend stand law change behind. International pay side seek knowledge list.',
    'email': 'leslie53@example.org',
    'phone_number': '607-986-3421',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Meza',
    'Heather Rivera',
    'Becky Ramos',
    'Elizabeth Glover',
    'Ruth Taylor',
    'Brandon York',
],
    'json': {
    'name': 'Yesenia Bates',
    'address': '568 Gibson Forest Apt. 175\nPort Eric, MI 97957',
},
    'key11133': 'value2539',
    'key72018': 'value82913',
    'key2185': 'value69702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Frederick Vargas',
    'address': '829 Tiffany Overpass\nWest Bobbystad, ME 11393',
    'text': 'Fire too trouble can partner receive fire. Thing candidate than wear involve how agent.',
    'email': 'drobinson@example.net',
    'phone_number': '+1-920-935-7831x27902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Willie Fry',
    'Thomas Fuentes',
    'Roger Smith',
    'David Brown',
],
    'json': {
    'name': 'Emily Hernandez',
    'address': '384 Martinez Run Suite 719\nBrooksmouth, AK 59428',
},
    'key95279': 'value25225',
    'key42873': 'value68543',
    'key50501': 'value27826',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Daniel Mullins',
    'address': '7027 Cherry Plaza\nNorth Christine, FL 19888',
    'text': 'Pass matter perform family. Call prove single town.\nPeople three community support management month. Treatment whole study nothing. Tax exist might easy decide edge try.',
    'email': 'ysloan@example.com',
    'phone_number': '001-894-518-5820x1385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jenna Powers',
    'Kathryn Perry',
    'Joseph Shepard',
    'Maria Martin',
    'David Richardson',
    'Melissa Hernandez',
],
    'json': {
    'name': 'Greg Moore',
    'address': '407 Jessica Terrace\nLake Kaylaville, SD 68601',
},
    'key24281': 'value55198',
    'key75438': 'value97193',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Gregory Hunt',
    'address': '2627 Johnson Hill\nWest Elizabeth, HI 09502',
    'text': 'To these hold police. Air arm than to hit strategy.\nForce history write. Report sure let she.\nIn TV best over cold other Republican billion.\nFace option organization eye end his enter.',
    'email': 'lisaburton@example.com',
    'phone_number': '475-723-0414',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Frederick Walker',
    'Joseph Taylor',
    'Robert Macias',
    'Brandon Wright',
    'Christina Richardson',
    'Joshua Terry',
    'Chloe Warner',
    'Bruce Burgess',
    'Christopher Willis',
],
    'json': {
    'name': 'Nicholas Evans',
    'address': '6595 Rhonda Throughway\nSouth Theresabury, WA 82175',
},
    'key33121': 'value64511',
    'key72221': 'value85729',
    'key92556': 'value6938',
    'key56680': 'value11683',
    'key3948': 'value92789',
    'key11811': 'value30570',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Cory Miller',
    'address': 'PSC 0406, Box 7651\nAPO AE 44462',
    'text': 'Us safe total fish I. Theory bring voice decade item. Win present away trouble quality lead choose. Start project fund stay great.',
    'email': 'jessica04@example.com',
    'phone_number': '373-490-3960',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Randy Edwards',
    'Christopher Brown',
    'Kelly Sanchez',
    'Shannon Lester',
    'Dawn Oconnor',
    'Paul Ramirez',
    'Meghan Wallace',
    'Andrea Holland',
],
    'json': {
    'name': 'Nancy Frazier',
    'address': '377 Sandra Underpass\nNorth Luisville, MI 10161',
},
    'key35568': 'value97369',
    'key38175': 'value39387',
    'key75650': 'value49381',
    'key60520': 'value36480',
    'key17122': 'value38032',
    'key24107': 'value1622',
    'key56409': 'value19682',
    'key6159': 'value71028',
    'key99775': 'value95462',
    'key19748': 'value66098',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Christopher Long',
    'address': '78133 Walls Points\nPort Kellymouth, ND 28139',
    'text': 'Theory somebody require knowledge. Letter region message form then.\nChance likely tough economic science teach. Minute nearly kitchen not foot. Prove if attack data time room series show.',
    'email': 'mlang@example.net',
    'phone_number': '(451)498-3330x8262',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mark Garza',
    'Rebecca Prince',
    'Tonya Johnson',
],
    'json': {
    'name': 'Daniel Pierce',
    'address': '7103 Scott Avenue Apt. 570\nRodriguezfurt, VT 83892',
},
    'key49942': 'value8702',
    'key83919': 'value45570',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Keith Barnes',
    'address': '6561 Pamela Keys\nRichardside, CA 09853',
    'text': 'Civil choose project choose music. Agree big science themselves.\nWay public local report pass both report. They oil wind certainly.',
    'email': 'oreeves@example.org',
    'phone_number': '(330)503-4639x472',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Jacobson',
    'Michael Willis',
    'David Brooks',
    'Robert Knight',
    'Amy Fox',
    'Chad Rodriguez',
],
    'json': {
    'name': 'Jessica Wood',
    'address': '0597 Michelle Walk Apt. 918\nPort Matthew, VT 83426',
},
    'key96144': 'value12129',
    'key2753': 'value82474',
    'key67083': 'value43388',
    'key36119': 'value51637',
    'key5498': 'value3037',
    'key77883': 'value67144',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Mark Jackson',
    'address': '924 Melanie Keys\nWest Victoriaton, CA 69992',
    'text': 'Language theory forget attack partner. Spring game group we again life drop. Almost technology order station.\nDebate mention step listen. Simply structure community western.',
    'email': 'daltonveronica@example.com',
    'phone_number': '+1-824-638-3610x033',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Randall Hanson',
    'Natalie Lozano',
    'John Ochoa',
    'Megan Jackson',
    'Michael Thompson',
],
    'json': {
    'name': 'Candice Woods',
    'address': '781 Kenneth Village Suite 325\nLake Davidshire, VI 27158',
},
    'key86459': 'value38299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Emily Miller',
    'address': '988 Carlson Coves Suite 269\nWest Linda, NH 64565',
    'text': 'Meeting environmental better admit often get city billion. Health kind fine executive knowledge north.',
    'email': 'utaylor@example.com',
    'phone_number': '672.460.0032x08075',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Alex Bruce',
    'Aaron Adams',
    'Russell Mcguire',
    'Carolyn Powers',
    'Tricia Simmons',
    'Mike Gonzalez',
    'Brandon Bennett',
    'Richard Butler',
    'Devin Hunt',
    'Mrs. Ashley Jefferson',
],
    'json': {
    'name': 'Gerald Mcpherson',
    'address': '296 Patricia Common Apt. 100\nWest Donna, MH 08329',
},
    'key44301': 'value2352',
    'key58420': 'value43100',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Dustin Cabrera',
    'address': '955 Moreno Crossroad Suite 204\nPort Kennethhaven, WV 50840',
    'text': 'Send specific team true. Congress agreement style day wall morning.\nDebate water just shake man water. Edge reveal task financial.\nOutside case line.',
    'email': 'christopherlee@example.com',
    'phone_number': '001-654-429-5809x080',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Williams',
    'Erica Williams',
    'Angela Maldonado',
    'Gail Ellison',
    'Dominique Turner',
    'Joshua Gibbs',
    'Alicia Pierce',
    'Samantha Sanders',
    'Tracey Carey',
],
    'json': {
    'name': 'Debra Jones',
    'address': '46131 Kaitlyn Spring\nSouth Katiebury, VI 27293',
},
    'key73805': 'value14348',
    'key44675': 'value85367',
    'key54799': 'value86043',
    'key14128': 'value28749',
    'key43097': 'value27221',
    'key89171': 'value24588',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Amy Miller',
    'address': '2531 Steven Ferry Suite 075\nLake Melissa, VA 77632',
    'text': 'Approach smile executive. Democratic worry bed however. Successful into relationship the win laugh. Particular notice board last.',
    'email': 'amiller@example.org',
    'phone_number': '001-395-556-2484',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Robert James',
    'Lindsey Williams',
    'Tracy Hurst',
    'Melissa Hicks',
    'Kathleen Kelley',
    'Paul Murray',
    'David Lewis',
    'Lisa Ruiz',
    'Oscar Jordan',
    'Nicholas Russell',
],
    'json': {
    'name': 'Kevin Johnson',
    'address': '021 Jose Burgs\nLake Emily, NV 99104',
},
    'key44976': 'value57372',
    'key19684': 'value59519',
    'key32983': 'value82558',
    'key89044': 'value47680',
    'key94710': 'value76481',
    'key93687': 'value18427',
    'key91160': 'value7895',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Chad Davis',
    'address': '2100 Cardenas Heights\nTanyaland, MO 46209',
    'text': 'During skin mission general future good field provide. Spend full report strong less specific firm.\nParticularly hair able board glass it. Speech cold gun require teacher.',
    'email': 'joshua94@example.net',
    'phone_number': '351-727-1290x3837',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Nguyen',
    'Corey Jones',
    'Teresa Cox',
    'Jonathan Rivas',
    'Lynn Henson',
],
    'json': {
    'name': 'David Collins',
    'address': '47461 Kaitlin Dam Apt. 689\nGravesview, NY 77017',
},
    'key57440': 'value6118',
    'key8897': 'value77451',
    'key59899': 'value67070',
    'key35768': 'value22337',
    'key19090': 'value67810',
    'key29578': 'value71606',
    'key83232': 'value92492',
    'key35475': 'value15986',
    'key43924': 'value20617',
    'key83170': 'value29554',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Dr. Amy West',
    'address': '22972 Michaela Estates\nLake Davidtown, RI 88133',
    'text': 'Ready pass foot fire. Nearly throughout relationship must process prove.\nRather wish art arrive trial me where. Break national sound culture your.',
    'email': 'tiffany72@example.net',
    'phone_number': '(460)321-3931x3680',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Cook',
    'Eric Hancock',
    'Lawrence Smith',
    'Keith Jensen',
    'Jeffrey Morris',
],
    'json': {
    'name': 'David Little MD',
    'address': 'PSC 7139, Box 4588\nAPO AA 47161',
},
    'key83293': 'value93701',
    'key78136': 'value79227',
    'key8014': 'value94047',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Mr. Daniel Lawrence MD',
    'address': '201 Gonzalez Ports\nEast Ashleyview, FL 19575',
    'text': 'Huge decade before both plan. Mission space major century. Seem east man and money prove life.\nGovernment put election nice throw happen eight. Customer including claim work.',
    'email': 'xjarvis@example.com',
    'phone_number': '+1-837-273-0477x273',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Gonzalez',
    'Teresa Becker',
],
    'json': {
    'name': 'Chad Evans',
    'address': '57617 Dylan Pines\nRichardborough, PR 14506',
},
    'key15063': 'value32305',
    'key84302': 'value99313',
    'key87394': 'value86717',
    'key26871': 'value8000',
    'key73143': 'value44732',
    'key69974': 'value17358',
    'key13882': 'value59613',
    'key16927': 'value65972',
    'key77947': 'value12204',
    'key28062': 'value10854',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Kayla Holmes',
    'address': '988 Amber Ports\nStarkchester, UT 65709',
    'text': 'Reality maybe focus recent wall. Speech image bring return technology.\nPerform career mission pretty word everyone alone. Democratic them phone machine. Will class state author far save face.',
    'email': 'nicholsgerald@example.com',
    'phone_number': '361-697-1704',
    'array_int_dynamic': [
    63041,
],
    'array_varchar_dynamic': [
    'David Gonzalez',
    'Renee Hunt',
],
    'json': {
    'name': 'Heather King',
    'address': '1581 Ruiz Squares Suite 056\nPort Mike, OR 89282',
},
    'key34459': 'value69611',
    'key64062': 'value25691',
    'key33478': 'value80839',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Mr. Craig Osborn',
    'address': 'USNV Koch\nFPO AP 16486',
    'text': 'Cup high relationship like once carry now show.\nLand road notice both effect. Instead camera collection institution.',
    'email': 'hmorgan@example.com',
    'phone_number': '940.317.3862x6415',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Jenkins',
    'Susan Butler',
    'Michael Welch',
    'Sandra Allen',
    'Robert Roman',
    'Robert Richards',
    'Angela Johnson',
],
    'json': {
    'name': 'Joshua Rich',
    'address': '97329 Ward Burg\nNorth Johnmouth, KS 46036',
},
    'key73096': 'value83413',
    'key43151': 'value45320',
    'key34284': 'value34081',
    'key63315': 'value82760',
    'key73547': 'value7040',
    'key19436': 'value4535',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Diamond Davidson',
    'address': '6573 Tiffany Stravenue Apt. 666\nJasonbury, CO 77579',
    'text': 'Clear history billion environment born explain situation. Population apply not information movie white.',
    'email': 'danielcindy@example.org',
    'phone_number': '(820)970-1233x5949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Caitlin Dennis',
    'Ms. Catherine Davis',
    'Nicole Leon',
    'Ryan Irwin',
    'Kathryn Hughes',
    'Audrey Wilson',
    'David Lewis',
    'Gail West',
    'Wanda Rivera',
    'Debra Owens',
],
    'json': {
    'name': 'John Berry',
    'address': '482 Horton Loaf\nPort Ashley, CO 10964',
},
    'key37387': 'value72629',
    'key81510': 'value20961',
    'key60370': 'value33073',
    'key12672': 'value87998',
    'key86193': 'value85772',
    'key10225': 'value58848',
    'key47487': 'value49574',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Thomas Riley',
    'address': '4773 Wallace Causeway Suite 841\nSouth Nicholasshire, MN 66058',
    'text': 'Wind though there democratic girl. Air author shoulder leg. Up bill speak cost first thought success. Chance war send us stuff.',
    'email': 'ramosjenna@example.net',
    'phone_number': '(940)312-7237x3968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Linda Cohen',
    'Erica Johnson',
    'Jason Garcia',
    'Jacqueline Malone',
    'Debra Ritter',
    'Kevin Jones',
    'Christina Wilson',
    'Jennifer Williams',
    'Stacey Kent',
],
    'json': {
    'name': 'Kenneth Anderson',
    'address': '4569 Ethan Rapid\nNorth Matthew, IA 18796',
},
    'key95489': 'value62874',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Miguel Harrison',
    'address': '428 Murphy Motorway Apt. 727\nKarenbury, GU 60677',
    'text': 'Onto expect use around chance sometimes. Clear court police a age both.\nHappen other their paper myself system blue. Camera those it food.',
    'email': 'angela64@example.net',
    'phone_number': '(896)643-9131x63044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Pamela Huffman DDS',
    'Dylan Fisher',
    'John Cooper',
    'Henry Burke',
    'Jerry Lucas',
    'Jonathan Smith',
    'Rachel Bartlett',
],
    'json': {
    'name': 'Richard Guerra',
    'address': '3403 Melissa Harbors Suite 865\nErikaland, AL 97950',
},
    'key94806': 'value68495',
    'key43766': 'value6702',
    'key95431': 'value31908',
    'key30491': 'value59460',
    'key38915': 'value59397',
    'key64952': 'value57177',
    'key64126': 'value44382',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Rebecca Martinez',
    'address': '889 Johnston Fort Apt. 830\nDominguezville, ID 64522',
    'text': 'Special live husband child dinner general. Decision east coach remember accept push.\nAround month mean the really. Bar happy these consider shoulder. Color staff way happen again.',
    'email': 'ysmith@example.com',
    'phone_number': '001-278-347-9953',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Smith',
    'Joyce Figueroa',
    'Jessica Osborne',
],
    'json': {
    'name': 'Hailey Griffith',
    'address': '58680 Gonzalez Plains\nHensleystad, HI 37154',
},
    'key64061': 'value73988',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Chelsey Clay',
    'address': '96854 Tyler Rapids Apt. 391\nRussellfurt, MO 20253',
    'text': 'Market discussion choice three. You interview new.\nCheck sense even dark enter. Boy good hit American something morning pass.',
    'email': 'edwardsmaria@example.org',
    'phone_number': '842-780-4310',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Obrien',
    'Brian Vasquez',
    'Kristin Miller',
    'Annette Butler',
    'Olivia Tyler',
    'Susan Smith',
],
    'json': {
    'name': 'Christie Torres',
    'address': '7680 Terri Forest\nPhamborough, AL 19243',
},
    'key10685': 'value15447',
    'key99765': 'value39433',
    'key43789': 'value82491',
    'key82112': 'value74808',
    'key28127': 'value96634',
    'key8689': 'value1854',
    'key87003': 'value85786',
    'key13599': 'value74770',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Michael Oconnor',
    'address': '95556 Nunez Via Suite 540\nNew Eric, UT 07155',
    'text': 'Manager seem who together. System science couple sometimes resource anyone approach. Our sell person trouble pick write.',
    'email': 'jordanstephanie@example.net',
    'phone_number': '(733)763-9901x00903',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Walker',
    'Cassandra Wong',
    'Joshua Johnson',
    'Cristian Reyes',
    'Heather Reyes',
    'Jaime Gardner',
    'Tiffany Mann',
    'Christopher Murphy',
    'Jeffery Taylor',
    'Amy Sanchez',
],
    'json': {
    'name': 'Edward Salazar',
    'address': '48131 Kelsey Burgs Apt. 941\nWest Kimfort, OH 43145',
},
    'key54721': 'value1488',
    'key33602': 'value81779',
    'key36713': 'value98561',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Matthew Newman',
    'address': '1222 Mccoy Extensions Suite 521\nJacobsmouth, HI 06957',
    'text': 'Morning film body later specific shake exactly. Better you edge which.\nDrug drive western month.',
    'email': 'danielwilliams@example.com',
    'phone_number': '001-816-687-0394',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alan Nguyen',
    'Jennifer Gay',
    'Gabriel Moore',
    'Hannah Patterson',
    'Travis Walker',
    'Mrs. Mia Weiss',
    'Joshua Green',
    'Amber Camacho',
    'Doris Patrick',
    'Terry Garcia',
],
    'json': {
    'name': 'Shannon Turner',
    'address': '97180 Rebecca Island Suite 192\nEast Jennifer, PR 87381',
},
    'key49263': 'value38572',
    'key48565': 'value42313',
    'key39470': 'value44186',
    'key58001': 'value63924',
    'key2288': 'value63582',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Jacqueline Thompson',
    'address': '62911 Long Forest\nLake Jose, FM 84700',
    'text': 'Even remember husband even feel number kind family.\nWhich study point medical item popular page. Fly above full growth skill. Learn current suggest prove smile.\nPrepare happy especially.',
    'email': 'meyerrichard@example.com',
    'phone_number': '(248)506-1078x5653',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Robinson',
    'Sarah Miller',
    'David Bell',
    'Michael Armstrong',
    'Shaun Lopez',
    'Laura Stewart',
],
    'json': {
    'name': 'Jennifer Curtis',
    'address': '540 Golden Squares Suite 789\nBenjaminland, HI 83944',
},
    'key17725': 'value48786',
    'key53977': 'value81890',
    'key55238': 'value99215',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Samuel Burke',
    'address': '135 Jennifer Islands\nColemanchester, OH 80358',
    'text': 'Research goal recent. Fly amount financial beyond peace exactly. Minute reflect hard national hear.',
    'email': 'eric95@example.org',
    'phone_number': '292.571.6640x752',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Angela Dunlap',
    'Meagan Hamilton',
    'Erika Lopez',
],
    'json': {
    'name': 'Anthony Hughes',
    'address': '2886 William Square\nJudithville, MI 11878',
},
    'key47415': 'value95633',
    'key46850': 'value63296',
    'key82607': 'value26909',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Katherine Maldonado',
    'address': 'USNS Prince\nFPO AP 29931',
    'text': 'Everyone trouble appear military study both time.\nMind specific practice commercial anyone. Hospital pattern sing foot understand. Service skill side traditional above reason down.',
    'email': 'gentrymichelle@example.net',
    'phone_number': '(232)998-9257',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Alice Haley',
],
    'json': {
    'name': 'Ashley Dean',
    'address': '5367 Lucas Valley\nMarkburgh, NV 75538',
},
    'key52704': 'value10801',
    'key3409': 'value21551',
    'key19843': 'value57670',
    'key24318': 'value49055',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Bridget Davis',
    'address': '1502 Cannon Overpass\nWest Angel, TX 88894',
    'text': 'Sea physical enough free condition truth simply news. School history wife certain before.\nThere direction may participant run field poor. Central entire hard way.',
    'email': 'craigjessica@example.net',
    'phone_number': '728.430.5452x1541',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Green',
    'Anna Cisneros',
    'Stephen Turner',
    'Henry Bryant',
    'Carl Phillips',
],
    'json': {
    'name': 'Robert Moreno',
    'address': '017 Miller Pass\nHillview, AS 54372',
},
    'key87247': 'value76403',
    'key33892': 'value91233',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Jeffery Turner',
    'address': '841 Ana Extensions Suite 197\nNew Gracechester, NM 44353',
    'text': 'High away loss condition piece history myself wind.',
    'email': 'petersonbrandon@example.org',
    'phone_number': '416-477-7178x10174',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mallory Sanders',
    'Karen Ingram',
    'John Thomas',
    'Diane Le',
    'Mary Nelson',
],
    'json': {
    'name': 'Bruce Patterson',
    'address': '48055 Jose Lodge Suite 694\nSouth Wayne, VT 73552',
},
    'key54586': 'value50069',
    'key3836': 'value93313',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Teresa Moore',
    'address': '782 Brown Parkways Suite 602\nLake Theresaberg, NM 68489',
    'text': 'Husband Republican part artist democratic. Everything take black. Ground couple house range start. Food citizen control off decision amount.\nJob project hold again finally tree.',
    'email': 'erikahaney@example.net',
    'phone_number': '+1-710-744-1760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Raven Evans',
    'Joseph Montgomery',
    'Corey Murphy',
    'John Hall',
    'Travis Golden',
    'Debra Summers',
    'Daniel Larson',
],
    'json': {
    'name': 'Hannah Navarro',
    'address': '647 Levi Pass\nNew Manuelhaven, WY 88747',
},
    'key96652': 'value81452',
    'key66104': 'value53318',
    'key498': 'value67850',
    'key12191': 'value50782',
    'key54484': 'value64214',
    'key74548': 'value39083',
    'key60702': 'value31465',
    'key16563': 'value13725',
    'key40672': 'value2952',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'James Johnson',
    'address': '3891 Taylor Port\nMartinstad, FL 88610',
    'text': 'Up real responsibility must stop. Late we ask church pick film. Money baby music guess report keep.\nTerm international drop military. Issue someone stage within environmental price.',
    'email': 'gzimmerman@example.net',
    'phone_number': '663.240.8306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Vargas',
    'Kristin Grant',
    'Thomas Baker',
    'Alexander Knight',
    'Troy Roberts',
    'Linda Ford',
    'Samuel Camacho',
    'Anthony Thomas',
    'Jonathan Ramsey',
],
    'json': {
    'name': 'Ana Walker',
    'address': '21779 Lawrence Ville\nMoranberg, MD 86034',
},
    'key23201': 'value94722',
    'key81215': 'value73212',
    'key90569': 'value62686',
    'key54851': 'value60020',
    'key85432': 'value17037',
    'key10451': 'value68093',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Sara Simon',
    'address': '67779 Gonzales Rue Apt. 649\nOlsonmouth, MT 43346',
    'text': 'Hold country wife black hard should difference. Natural phone standard however change knowledge use. Face policy tax social.\nYeah charge its rather air. Stop movement off buy your step while.',
    'email': 'thomaspatton@example.org',
    'phone_number': '+1-809-590-8264x172',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amber Young',
    'Casey Scott MD',
    'David Hays',
    'Valerie Washington',
    'Denise Collins',
    'Shawn Adams',
    'Eric Aguirre',
    'Bryan Brown',
],
    'json': {
    'name': 'Michael Baker',
    'address': 'Unit 0258 Box 6319\nDPO AE 28469',
},
    'key69283': 'value90748',
    'key70458': 'value56438',
    'key74596': 'value32458',
    'key25825': 'value86882',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Brandi Fields',
    'address': '9494 Tonya Canyon Suite 556\nNorth Gailton, TN 26697',
    'text': 'Build white hour cost down then according. Final computer newspaper enter.\nEach soldier beat who should form send new.\nResponse wish however growth goal Mr. Tend ever arrive girl.',
    'email': 'moorelouis@example.net',
    'phone_number': '+1-227-928-1027x526',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Beth Montoya',
    'Robert Thompson',
    'Henry Foster',
    'Lisa Garcia',
    'Mark Gomez',
    'Danielle Moyer',
    'David Bartlett',
    'Kiara Nguyen',
    'Jennifer Rios',
    'Christopher Washington',
],
    'json': {
    'name': 'Justin Hill',
    'address': '02067 Herrera Garden\nWardmouth, AL 78212',
},
    'key18226': 'value83105',
    'key19900': 'value80093',
    'key93639': 'value23174',
    'key55904': 'value52112',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Tara Lewis',
    'address': '4248 Patricia Extension Apt. 169\nLake Ryanland, AZ 81250',
    'text': 'Pull half full least forward should enough. One him walk ask expect story. Four create continue.',
    'email': 'john53@example.com',
    'phone_number': '(851)785-3188',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Erik Moreno',
    'Andrew Peterson',
    'Christian Colon',
    'Amanda Guerra',
    'Damon Black',
    'Mrs. Mary Anderson',
    'Krista Pruitt',
    'Rebecca Martinez',
    'John Mendoza',
],
    'json': {
    'name': 'Jessica Castillo',
    'address': '55646 Meyer Shore\nGomezshire, PR 76724',
},
    'key94235': 'value59019',
    'key41463': 'value63313',
    'key66946': 'value75177',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Mrs. Laurie Smith',
    'address': '5270 Megan Mill\nBrittanyland, TX 23971',
    'text': 'Stop control nothing court. Mr perform inside day guy figure best clear. Occur once response away military.\nSister price major more these. Turn left method such work later loss.',
    'email': 'morrisdonna@example.com',
    'phone_number': '971.822.5627',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Reyes',
    'Haley Reid',
    'Anthony Levine',
    'Kristen Rose',
    'Francisco Bird',
    'Glen Benson',
    'Harold Ruiz',
    'Christopher Pollard',
    'Scott Frost',
],
    'json': {
    'name': 'John Middleton',
    'address': '389 Sparks Station\nColemanmouth, OK 23002',
},
    'key68368': 'value71137',
    'key18384': 'value89453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Amy Cohen',
    'address': '239 Michael Ridges\nNguyenburgh, VA 09469',
    'text': 'How around get beautiful outside us and method. Rock brother anything.\nTough adult building would without. Image general administration meeting home.',
    'email': 'allenjohn@example.net',
    'phone_number': '910.330.4001x282',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Gabriel Sullivan',
    'Brittany Wong',
    'Carol Chambers',
],
    'json': {
    'name': 'Anne Castaneda',
    'address': '372 Martin Squares Suite 998\nMichaelburgh, VT 74304',
},
    'key15301': 'value55137',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Juan French',
    'address': '974 Harvey Street\nNew Mark, NM 78207',
    'text': 'Several much line worker. Hotel poor across remember sense.\nResearch center old good gas conference at. Out system away.',
    'email': 'osmith@example.org',
    'phone_number': '798.594.2513x6979',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Renee Coleman',
    'Sarah Kaiser',
    'Norma Marshall',
    'Patrick Smith Jr.',
    'Wendy Wilson',
    'Brenda Jackson',
    'Joel Robinson',
    'Adam Smith',
    'Dr. Joshua Johnson II',
],
    'json': {
    'name': 'Anthony Leonard',
    'address': '5365 Banks Grove\nKevinborough, NY 60304',
},
    'key58420': 'value99546',
    'key16627': 'value94697',
    'key31082': 'value50074',
    'key42348': 'value74687',
    'key10421': 'value77514',
    'key49760': 'value44188',
    'key61843': 'value68155',
    'key93510': 'value7318',
    'key83596': 'value10897',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Stephanie Webb',
    'address': 'USNV Bentley\nFPO AE 99799',
    'text': 'Tax run too science.\nStart chair suffer involve hope discuss main without. Amount picture behavior create other appear. Pull ever himself role arm husband.',
    'email': 'henry19@example.net',
    'phone_number': '(409)524-9527x69209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Reese',
    'Alexis Martin',
],
    'json': {
    'name': 'Melanie Schneider',
    'address': '8694 Dennis Trail Apt. 897\nHenrychester, MN 39506',
},
    'key22177': 'value60073',
    'key51563': 'value38888',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Jennifer Hall',
    'address': '14373 Gray Plains\nLewisshire, WA 97457',
    'text': 'Among manage body ok good approach. Yes natural among current five dog compare charge. From knowledge huge read hour.\nNumber purpose necessary tonight sign. Social administration business miss class.',
    'email': 'xclay@example.net',
    'phone_number': '804.879.0676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robin Martin',
    'Judy Bryant',
    'Kevin Nichols',
    'Gabriel Dickson',
    'Kelli Turner',
    'Monique Jackson',
    'Anne Harding',
    'Erica Martin',
    'Todd Allen',
    'Jessica Gonzalez',
],
    'json': {
    'name': 'Matthew Richards',
    'address': '523 Glenn Village\nWest Eric, CA 09308',
},
    'key67601': 'value75659',
    'key57863': 'value25108',
    'key21922': 'value4848',
    'key27815': 'value21702',
    'key70484': 'value98921',
    'key6188': 'value11712',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Kimberly Campbell',
    'address': '417 Henderson Expressway Apt. 188\nPort Christy, KY 88258',
    'text': 'Site forget speech long lay gas. Meet budget rest suddenly. Building thank home manager feel one hope or.\nGreen visit but. Also produce hour enjoy office order.',
    'email': 'robertslori@example.com',
    'phone_number': '(604)658-5389',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Karina West',
    'Tabitha Hall',
    'Lisa Silva',
    'John Ellis',
    'Scott Martin',
    'Jessica Brown',
    'Monica Evans',
    'Cameron Clark',
    'Gilbert Pineda',
],
    'json': {
    'name': 'Stephanie Leach',
    'address': 'Unit 3921 Box 1713\nDPO AE 77327',
},
    'key94964': 'value45050',
    'key89779': 'value4627',
    'key28218': 'value56925',
    'key94876': 'value60000',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Dennis King',
    'address': '3730 Macdonald Village Apt. 665\nWest Courtney, GA 82273',
    'text': 'Television stop police everything speak remember. Service our manager writer reason. Eat reveal cover glass year anyone usually.\nWonder door fast blood. Safe offer century ready follow.',
    'email': 'uwilliams@example.org',
    'phone_number': '(886)328-9807x6836',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Barry Howell',
    'Chad Garcia',
    'Pamela Soto',
    'Bill Stephens',
    'Cynthia Nolan',
],
    'json': {
    'name': 'Bobby Hughes',
    'address': 'PSC 4429, Box 9865\nAPO AE 32712',
},
    'key91278': 'value3718',
    'key74784': 'value12216',
    'key18525': 'value66882',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Cynthia Baker',
    'address': 'PSC 3816, Box 1194\nAPO AE 54454',
    'text': 'Attack listen son type part be. Magazine capital trade yet lay quality. You skill standard education seat treatment show.\nTrade floor up.',
    'email': 'tammy29@example.com',
    'phone_number': '(939)621-3425x47861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Donna Alexander',
    'Patrick Trevino',
    'Mary Spears',
    'Michael Pitts',
    'Christina Taylor',
    'James Curtis',
    'Matthew Webster',
    'Emily Williams',
    'Ruben Lowe',
],
    'json': {
    'name': 'Logan Robertson',
    'address': '23276 Taylor Hills Suite 921\nCarriehaven, CO 78310',
},
    'key71782': 'value94317',
    'key4379': 'value302',
    'key11646': 'value1001',
    'key10004': 'value79901',
    'key40049': 'value97204',
    'key22798': 'value74732',
    'key53950': 'value89422',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Darryl Garcia',
    'address': '404 Ryan Keys\nNorth Zacharytown, AS 59257',
    'text': 'Billion yes catch energy step magazine. Would office attorney. Pick safe to quite expect past.\nOwn add because miss no. Shoulder think end any. Stage measure skin mouth.',
    'email': 'rpatton@example.net',
    'phone_number': '001-916-791-4970x4538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Ryan Miller',
    'Dawn Norman',
    'Tiffany Nguyen',
    'Barbara Sims',
    'Stephanie Steele',
    'Rachel Best',
    'Breanna Lewis',
    'Charles Brown',
    'Nicole Zimmerman',
    'Angela Hernandez',
],
    'json': {
    'name': 'Craig Phillips',
    'address': '219 Eric Oval Suite 719\nNew Brittany, IN 81502',
},
    'key2309': 'value75915',
    'key1007': 'value95542',
    'key90165': 'value44662',
    'key94468': 'value60483',
    'key16335': 'value86891',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'George Weber',
    'address': '2447 Howell Mills Apt. 190\nSouth Julieburgh, KS 28034',
    'text': 'Possible training environment protect which raise. Clearly attack process.\nPressure write ability call write than. Mission degree international.',
    'email': 'stacey83@example.net',
    'phone_number': '512-705-4722x482',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Donald Jenkins',
    'Deborah Curry',
    'Robert Kelley',
    'Ellen Quinn',
    'Christopher Williams',
    'Brandi Hines',
],
    'json': {
    'name': 'Kevin Fleming',
    'address': '599 James Drive Apt. 622\nNorth James, AR 77308',
},
    'key57022': 'value29581',
    'key36168': 'value30426',
    'key89232': 'value44221',
    'key25645': 'value81720',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Jeffrey James',
    'address': '105 Mccormick Locks Apt. 638\nJoeland, AS 64854',
    'text': 'Owner practice expect especially purpose sometimes environmental.\nMedia clear best management pass can one. Safe tree positive check. Evidence firm religious world benefit.',
    'email': 'amanda33@example.org',
    'phone_number': '2628331969',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Joseph Jr.',
    'Zachary Morgan',
    'Lisa Anderson',
    'Bobby Hamilton',
    'Melinda Harris',
    'Michael Sullivan',
    'Andrew Scott',
    'Melissa Pearson',
    'Mark Carlson',
    'Danielle Garcia DDS',
],
    'json': {
    'name': 'Patricia Scott',
    'address': '94205 Donna Falls\nVictoriashire, AR 81150',
},
    'key11567': 'value58474',
    'key78365': 'value21726',
    'key43167': 'value74639',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Michelle Clark',
    'address': '54264 John Streets\nMcguiremouth, CA 65640',
    'text': 'Prevent quite stay whose matter among. Find network health wrong out system. Enter bring site can quite course.\nDay catch mouth factor trouble.',
    'email': 'whorton@example.com',
    'phone_number': '+1-991-398-5716x64276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Duncan',
    'Larry Waters',
    'Kaylee Watson',
    'Kenneth Williams',
    'Melissa Anderson',
    'Jennifer Marsh',
    'Cynthia Hampton',
],
    'json': {
    'name': 'Linda Lopez',
    'address': '088 Philip Hill\nSouth Eugenefurt, AL 36314',
},
    'key93292': 'value84065',
    'key91399': 'value19357',
    'key30936': 'value10073',
    'key45751': 'value22788',
    'key45687': 'value81947',
    'key14397': 'value69974',
    'key57484': 'value95701',
    'key46647': 'value74453',
    'key84143': 'value52724',
    'key39691': 'value43474',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Samuel Cole',
    'address': '3511 Miller Greens\nMichelleshire, SD 96274',
    'text': 'Song short how. Attack continue arm technology.\nCatch son past policy none now. Response everybody look manage couple.\nThought meeting raise set type. You black leader field simply.',
    'email': 'amandadavis@example.org',
    'phone_number': '001-910-335-2814x26407',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Hicks',
    'David Miller',
    'Justin Kim',
    'Jeffrey Webb DVM',
    'John Baxter',
],
    'json': {
    'name': 'Stephen Ross',
    'address': '7369 Ramirez Coves\nSouth Charles, DE 60125',
},
    'key97591': 'value13189',
    'key95925': 'value66297',
    'key99858': 'value6031',
    'key89851': 'value20563',
    'key86022': 'value95134',
    'key73485': 'value42568',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Timothy Chavez',
    'address': '9655 Carl Inlet Apt. 224\nPort Matthew, MI 62388',
    'text': 'Southern explain five our feeling above. Act range president trial room.\nSerious again pretty wall statement court. Just performance still five happen stock number stage.',
    'email': 'christophersmith@example.com',
    'phone_number': '929-256-0388',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Clark',
    'Samuel Kline',
],
    'json': {
    'name': 'Mr. Derrick Kramer PhD',
    'address': '453 Herrera Haven\nLindastad, ID 42400',
},
    'key86579': 'value77831',
    'key54466': 'value31900',
    'key43003': 'value36110',
    'key62263': 'value87326',
    'key30183': 'value76406',
    'key37418': 'value4045',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Mark Kline',
    'address': '417 Franklin Summit\nValdezchester, NH 35362',
    'text': 'Win position house across. Value cell TV very where beyond. East issue air yes former from. Quality customer technology hour would always.\nSort benefit realize high participant good.',
    'email': 'wjohnson@example.org',
    'phone_number': '573-247-7982',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jill Brown',
    'John Mora',
    'Lindsay Matthews',
    'Victoria Smith',
    'Christian Randall',
],
    'json': {
    'name': 'James Smith',
    'address': '980 Robinson Freeway\nJeffreyview, VT 03947',
},
    'key60306': 'value36918',
    'key41946': 'value47213',
    'key32003': 'value40845',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'John Graham',
    'address': '6206 Miranda Lake Apt. 708\nStephenton, KY 44897',
    'text': 'Family personal research million. Minute them discover price well herself improve.',
    'email': 'mpacheco@example.org',
    'phone_number': '254-215-7798',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Horne',
    'Timothy Mueller',
    'Jesse Perez',
    'Jennifer Davis',
    'Charles Sloan',
    'Donald Maxwell',
    'Nicole Alexander',
    'Scott Roberts',
    'Regina Garrett',
],
    'json': {
    'name': 'Patrick Gomez',
    'address': 'Unit 5382 Box 1281\nDPO AP 24454',
},
    'key31550': 'value30003',
    'key54485': 'value53851',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Nicolas West',
    'address': 'USNV Carroll\nFPO AA 20009',
    'text': 'Safe alone learn list level ago. Raise drive fact glass. Their inside source sense avoid despite school old.',
    'email': 'qrush@example.com',
    'phone_number': '(601)272-4310x70242',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Johnson',
    'Gregory Salazar',
    'Robert Best',
    'Alexander Long',
    'Harry Flores',
    'Bradley Robinson',
    'Randall Wagner',
],
    'json': {
    'name': 'Kerri Smith',
    'address': '901 Heather Stream\nRomeroland, AZ 92599',
},
    'key72860': 'value14132',
    'key53776': 'value71754',
    'key24827': 'value71873',
    'key11527': 'value181',
    'key8872': 'value52229',
    'key22702': 'value78261',
    'key42029': 'value80463',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Jessica Reeves',
    'address': '34604 Allen Loaf Suite 666\nColemouth, KS 15849',
    'text': 'Money age yet seven board economic position. Particularly open career. Play well matter smile father generation.',
    'email': 'james62@example.net',
    'phone_number': '001-667-683-5728',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Bright',
    'Beth Dean',
    'Carlos Nguyen',
    'Jake Lee',
    'James Maxwell',
    'Andrew Warner',
    'James Taylor',
    'Shane Dean',
    'Joshua Lopez',
    'James York',
],
    'json': {
    'name': 'Nicholas Spencer',
    'address': '65849 Williams Point Apt. 155\nMaytown, AZ 20440',
},
    'key40697': 'value64157',
    'key20105': 'value97868',
    'key52753': 'value27075',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Virginia Murphy',
    'address': '64820 Galvan Row\nNorth Sharon, KS 77190',
    'text': 'Popular beautiful member. Democratic one cause candidate very field.\nMonth point report player. What order fill product.\nWithout listen lawyer able. Human heavy three base manage.',
    'email': 'heatherromero@example.net',
    'phone_number': '001-996-555-5990',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Ramos',
    'Alyssa Ryan',
    'Nicholas Logan',
    'Jennifer Dyer',
    'Sheri Johnson',
    'Derek Watson',
    'Mr. Kyle Acosta PhD',
    'Natalie Martin',
    'Cynthia Castro',
],
    'json': {
    'name': 'Reginald Woods',
    'address': '51227 Robert Trace\nAngelahaven, TN 43105',
},
    'key88291': 'value91130',
    'key57799': 'value17147',
    'key19058': 'value37955',
    'key86661': 'value12543',
    'key11335': 'value11843',
    'key82675': 'value85348',
    'key40667': 'value33533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Stephanie Barnett',
    'address': '509 Pearson Place Apt. 605\nBarbermouth, NJ 94971',
    'text': 'Machine thing family three fish necessary heavy ability. Exist should very.\nAlready nice tell usually area particularly air. Father authority city.',
    'email': 'droberts@example.com',
    'phone_number': '713.932.8151x3060',
    'array_int_dynamic': [
    8658,
],
    'array_varchar_dynamic': [
    'Melinda Simon',
    'Alexandria Miller',
    'Gregory Collins',
    'Mark Roach',
],
    'json': {
    'name': 'Daniel Rodriguez',
    'address': '635 Davidson Street\nSouth Norma, MD 17717',
},
    'key3937': 'value52971',
    'key55102': 'value84555',
    'key23041': 'value97051',
    'key90707': 'value41146',
    'key37920': 'value69897',
    'key73073': 'value1826',
    'key62551': 'value95242',
    'key70573': 'value34764',
    'key96272': 'value31336',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Jack Jones',
    'address': '00078 John Dam Suite 383\nNew Diana, WI 31418',
    'text': 'While space interview child. Middle coach lawyer popular baby. Recognize pull company democratic baby.',
    'email': 'douglas28@example.com',
    'phone_number': '6722050634',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Parker Rhodes',
    'Kelly Moore',
    'Shelia Dalton',
    'Brittany Long',
    'Sarah Bennett',
    'Gabriella Pena',
    'Kyle Oconnor',
    'Jeanette Mcdonald',
    'Jasmine Jones',
],
    'json': {
    'name': 'Theresa Rodriguez',
    'address': '468 Sanders Causeway\nPetersonbury, PR 79982',
},
    'key74507': 'value4141',
    'key37178': 'value51346',
    'key35519': 'value29637',
    'key69352': 'value1045',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Steven Jacobs',
    'address': '3184 Alejandra Well\nNorth Josephland, SC 20977',
    'text': 'House free professional. Nearly network from last send. Put million five agency entire. Director expert positive only.',
    'email': 'cooleytammy@example.net',
    'phone_number': '(275)710-3516',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brandy Shelton',
    'Tracy Hughes',
    'Abigail Hill',
    'Stephen Smith',
    'Jennifer Alvarez',
    'Emily Webb',
    'Christopher Hall',
    'Melinda Romero',
    'Ross Pugh',
],
    'json': {
    'name': 'Pam Novak',
    'address': '210 Vazquez Fields Suite 689\nCarlborough, KS 61117',
},
    'key87126': 'value51134',
    'key26163': 'value79830',
    'key85484': 'value26145',
    'key78706': 'value8298',
    'key45314': 'value43765',
    'key51922': 'value62676',
    'key19682': 'value605',
    'key72616': 'value37054',
    'key47768': 'value92240',
    'key63452': 'value28082',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Michael Luna',
    'address': 'USS Valdez\nFPO AE 57464',
    'text': 'Stage vote else. War short education it range. Available fund court positive well.\nExperience dark heavy space chair. Experience board heavy similar there.',
    'email': 'nicolerangel@example.net',
    'phone_number': '+1-941-796-8096',
    'array_int_dynamic': [
    52872,
],
    'array_varchar_dynamic': [
    'Kelsey Ramirez',
    'Stephanie Guzman',
    'Sean Fisher',
],
    'json': {
    'name': 'Cameron Weeks',
    'address': '89002 Davis Bypass\nSouth Lindseyberg, AR 05183',
},
    'key29254': 'value59272',
    'key74119': 'value13081',
    'key73449': 'value56887',
    'key90851': 'value87479',
    'key53797': 'value57850',
    'key50220': 'value64722',
    'key69904': 'value62957',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Shannon Wilkins',
    'address': '4929 Smith Common Apt. 083\nPatelborough, OK 56956',
    'text': 'Everybody player it test. Better explain seat great house condition better to. Mention success open gun beyond.',
    'email': 'tammy04@example.net',
    'phone_number': '+1-800-839-8715',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robert Gay',
    'Michelle Howard',
    'Jessica Brown',
    'Kimberly Gilbert',
    'Andrea Wilson',
    'Jeffrey Wood',
    'Curtis Barnett',
    'Mark Hogan',
    'Nathan Williams',
],
    'json': {
    'name': 'Emma Hernandez',
    'address': '9059 Isaac Mission\nChelseaport, NC 68358',
},
    'key54444': 'value30358',
    'key1097': 'value89340',
    'key58613': 'value95398',
    'key66679': 'value19060',
    'key48667': 'value54149',
    'key67499': 'value88967',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Christine Gonzalez',
    'address': '99662 Bradford Cove\nSamuelstad, TX 74419',
    'text': 'For himself relate give song next who.\nFeel could in subject campaign family. Young involve way standard seat ahead clear Mr.',
    'email': 'qcampbell@example.com',
    'phone_number': '(755)905-4784x0353',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'James Chapman',
    'Derrick Drake',
    'Lisa Schneider',
],
    'json': {
    'name': 'Jessica Moon',
    'address': '6749 Debbie Rue\nKimberlyville, WI 76781',
},
    'key40572': 'value90004',
    'key5199': 'value21467',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Cynthia Snow',
    'address': '9334 Jennifer Extension\nPort Andreberg, FL 85507',
    'text': 'Must process here example feeling she hospital. Cell follow exactly several.\nUnit event child rather piece ever. Those ago other order four. Public hot can meet really natural.',
    'email': 'rachaelbarnett@example.com',
    'phone_number': '630.683.4634x41502',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Jenkins',
    'Jerome Pena',
    'Stephanie Jones',
    'Richard Smith MD',
    'Cindy Morales',
    'Maria Moore',
],
    'json': {
    'name': 'Lisa Nelson',
    'address': '15921 Charles Prairie Apt. 800\nDoyleton, OR 67189',
},
    'key37616': 'value25319',
    'key26919': 'value81904',
    'key83411': 'value89300',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Emily Rojas',
    'address': '286 Frederick Lock\nLake Misty, AZ 41996',
    'text': 'Describe north group senior whether. Support simply system relationship family.\nCenter more resource top house. Central whether leave certain leave have. Road environment decide almost.',
    'email': 'hmiller@example.com',
    'phone_number': '+1-691-577-7551x727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Krystal Steele',
    'Ashley Shaw',
    'Paul Hill',
    'Michael Brown',
    'Joshua Brown',
    'Megan Santos',
    'Lisa Fox',
    'Valerie Wise',
    'Chelsea Walker',
],
    'json': {
    'name': 'Joy Scott',
    'address': '9466 Sanders Fall Apt. 602\nNew Jamesmouth, OH 81585',
},
    'key54705': 'value54379',
    'key37319': 'value23361',
    'key17447': 'value57251',
    'key31881': 'value76580',
    'key58273': 'value64006',
    'key4863': 'value49268',
    'key40896': 'value22743',
    'key45697': 'value44763',
    'key24514': 'value90933',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Teresa Dennis',
    'address': '1450 Wilson Haven\nWest Keith, KS 72365',
    'text': 'Throughout charge explain practice north. College end school seek town.\nDo plan than assume go sure movement. Third improve until realize some him. Door break miss radio.',
    'email': 'aprildavis@example.org',
    'phone_number': '757-706-3978',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Dougherty',
    'Randy Wagner',
    'Sara Vargas',
    'Amy Smith',
    'Jared Tran',
    'Herbert Davis',
    'Joshua Fisher',
    'Michael Peterson',
    'Jordan Rodriguez',
],
    'json': {
    'name': 'Gregory Vazquez',
    'address': '6167 Beck Expressway Suite 160\nGuzmanburgh, MS 04371',
},
    'key80267': 'value62938',
    'key63439': 'value36540',
    'key28346': 'value23689',
    'key48392': 'value39433',
    'key81650': 'value9888',
    'key34641': 'value59450',
    'key93053': 'value95715',
    'key16545': 'value44998',
    'key41033': 'value23630',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Sarah Gallegos',
    'address': '965 Browning Keys Apt. 841\nLake Matthewland, IL 87485',
    'text': 'Dream forward arrive method staff style thus. Single reveal ever purpose truth.\nMain see production media end walk. Cut political sister by upon. Fund need size these role.',
    'email': 'kathrynreed@example.org',
    'phone_number': '618-478-0792x9662',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Eric White',
    'Rebecca Baldwin',
    'Vanessa Ramos',
    'Sarah Wilcox',
],
    'json': {
    'name': 'Clayton Alvarado',
    'address': '29073 Marcus Landing Apt. 719\nScottborough, MS 08856',
},
    'key51371': 'value34667',
    'key86602': 'value87597',
    'key57156': 'value11874',
    'key88307': 'value57746',
    'key55049': 'value75085',
    'key37311': 'value36317',
    'key66321': 'value10457',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Andre Smith',
    'address': '1817 Bruce Road\nOrtegaberg, AS 62194',
    'text': 'Measure like purpose condition born financial. Move light everything system.\nWould education effect south fly lawyer. Growth fact development consumer.',
    'email': 'weberbrian@example.net',
    'phone_number': '001-973-886-0875x6620',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sierra Sanchez',
    'Daniel Gardner',
    'David Bradshaw',
    'Mark Ellis',
    'Patricia Davis',
    'Juan Wilson',
    'Frances Bennett',
    'Paula Martinez',
],
    'json': {
    'name': 'Gregory Harmon',
    'address': 'PSC 1646, Box 4974\nAPO AE 84472',
},
    'key16216': 'value89228',
    'key92595': 'value42371',
    'key62442': 'value76688',
    'key76901': 'value55480',
    'key57717': 'value64992',
    'key18703': 'value33161',
    'key81176': 'value52849',
    'key22665': 'value29115',
    'key44612': 'value13294',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Sheila Wallace',
    'address': '6804 Nelson Highway Suite 986\nLake Jennifer, MD 45471',
    'text': 'Behind hit success including account. Economic few right sign table both such. Media newspaper PM level item number east.',
    'email': 'anna64@example.org',
    'phone_number': '726.740.7991x1237',
    'array_int_dynamic': [
    84826,
],
    'array_varchar_dynamic': [
    'Tina Hutchinson',
    'William Humphrey',
    'Michael Woods',
],
    'json': {
    'name': 'Jeremy Potter',
    'address': 'Unit 5797 Box 2759\nDPO AE 02750',
},
    'key50105': 'value6215',
    'key86640': 'value37962',
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
    'RequestId': '7b7fad3d-62ef-11f0-9974-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_54_715490VlyyESHj',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-100-2]_1752744116.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl3210021752744116Json()
    test.run_tests()
