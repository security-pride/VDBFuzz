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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-2]_1752744101_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-2]_1752744101.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId3210021752744101Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-2]_1752744101.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-2]_1752744101.json"
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
    'RequestId': '72ff3aa0-62ef-11f0-9024-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_40_451894EWdgSjxW',
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
    'RequestId': '732131b6-62ef-11f0-a970-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_40_451894EWdgSjxW',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'James Casey',
    'address': '2823 Fox Pass Suite 811\nRobersonbury, ID 92001',
    'text': 'Finish determine example PM music test. Create choice record under spring security. Thank worker walk produce star paper.',
    'email': 'mooreangela@example.org',
    'phone_number': '+1-624-906-9723x5032',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brian Rivers',
    'David Martinez',
    'Daniel Gardner',
    'Gerald Dennis',
    'Ethan Rivera',
    'Angela Shepherd',
    'Miss Dawn Skinner',
    'Mary Maynard',
    'Jeff Price',
    'Stephen Wells',
],
    'json': {
    'name': 'Omar Sanders',
    'address': 'PSC 0142, Box 0415\nAPO AA 03850',
},
    'key33112': 'value66057',
    'key41999': 'value93756',
    'key82149': 'value98624',
    'key5091': 'value95136',
    'key1422': 'value73764',
    'key34490': 'value35176',
    'key41104': 'value27247',
    'key40477': 'value25985',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Dawn Carlson',
    'address': '54844 Maria Flat Apt. 983\nJoshuabury, PA 10120',
    'text': 'Many view office organization serve state Congress require. With husband heart level so our.',
    'email': 'bphillips@example.com',
    'phone_number': '7588242922',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ricardo Reynolds',
    'Scott Rodriguez',
    'Jonathan Golden',
],
    'json': {
    'name': 'Arthur White',
    'address': 'Unit 5651 Box 0498\nDPO AE 46383',
},
    'key14418': 'value47172',
    'key69347': 'value17442',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Robin Knight',
    'address': '8122 Horton Extensions\nEast Alexandraton, LA 52045',
    'text': 'Surface sign at answer from walk center. Return question why career person yard we. Never late under so woman money.',
    'email': 'smithdevin@example.org',
    'phone_number': '594-256-9782x387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Rivera',
    'Scott Gonzalez',
    'Stanley Rowland',
    'Holly Cooper',
],
    'json': {
    'name': 'Ryan Brown',
    'address': '0440 Hamilton Bridge\nKimberlyberg, UT 75268',
},
    'key22846': 'value75367',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Amy Parker',
    'address': '868 Molly Haven Apt. 331\nLake Samuelmouth, PR 06664',
    'text': 'Sister window activity tend. Dinner traditional partner wait remain join risk. Serious successful become voice house project. Road nice street mission.',
    'email': 'jpoole@example.org',
    'phone_number': '348.389.6565x6105',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Heather Hutchinson',
    'Michael Howell',
    'Eric Reyes',
    'Joanna Kaufman',
],
    'json': {
    'name': 'Tammie Short',
    'address': '396 Laura Inlet Apt. 475\nChristinatown, KS 48519',
},
    'key32734': 'value96862',
    'key96498': 'value3831',
    'key18194': 'value3270',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Diane Olsen',
    'address': '428 Derek Pass Apt. 480\nJuliamouth, IN 78428',
    'text': 'Democrat reality analysis probably third. Sound feeling hour. Finish when despite Mr year. White need right away ball.\nTop like trouble answer up. Military under notice issue car player parent.',
    'email': 'wallsmatthew@example.com',
    'phone_number': '616-404-1521',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Robert Townsend',
    'Mary Cain',
    'Jonathan Williams',
    'Douglas Mooney',
    'Dustin Huerta',
    'Katherine Parrish',
    'Travis Larsen',
    'Erika Barnett',
],
    'json': {
    'name': 'Christina Vargas',
    'address': '8325 Benson Locks\nJohnsonside, DE 77000',
},
    'key87514': 'value10603',
    'key91407': 'value16258',
    'key53802': 'value37431',
    'key99101': 'value93524',
    'key74548': 'value56792',
    'key50606': 'value72789',
    'key34370': 'value5039',
    'key24346': 'value43557',
    'key32861': 'value61231',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Justin Fletcher',
    'address': '400 Jerry Circles\nCynthiafort, OH 46332',
    'text': 'Discover easy must American heart force necessary voice. More town draw work wonder. Friend writer manager speak consumer million. Boy identify last former police friend.\nRock politics parent chance.',
    'email': 'joanne28@example.org',
    'phone_number': '726.818.0404x556',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Gonzalez',
    'Kenneth Pacheco',
    'David Carter',
    'Kimberly Gardner',
    'Andres Hendrix',
    'Kaitlyn Johnson',
    'Robert Garcia',
    'John Avila',
    'Sonya Rivas',
    'Dr. Kathryn Salazar',
],
    'json': {
    'name': 'Stephanie Sanchez',
    'address': 'PSC 3648, Box 3309\nAPO AP 78099',
},
    'key1387': 'value55470',
    'key17069': 'value44741',
    'key72384': 'value13310',
    'key68113': 'value43602',
    'key97666': 'value31223',
    'key65412': 'value84772',
    'key1897': 'value48414',
    'key7235': 'value36819',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Eduardo Calderon',
    'address': '9969 Michael Station Suite 740\nNorth Crystalshire, TX 03695',
    'text': 'Industry wait compare represent. You learn explain.\nStrong yard by water laugh. Artist such view think. Stay choose run late.\nArm information pressure different place across gun.',
    'email': 'michael46@example.com',
    'phone_number': '228-344-4407x78130',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Calvin Carter',
    'Brandi Jones',
    'Mary Williams',
    'Brandon Simpson',
    'Whitney Hansen',
    'John Castaneda',
    'Jonathan Mendez',
    'Kelly Garcia',
    'Jennifer Ward',
],
    'json': {
    'name': 'Christine Johns',
    'address': '16231 James Prairie\nNorth Josestad, NY 99179',
},
    'key8964': 'value17142',
    'key37621': 'value24114',
    'key26300': 'value86943',
    'key63630': 'value58777',
    'key45046': 'value74291',
    'key47500': 'value85174',
    'key47965': 'value69554',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Elizabeth Simpson',
    'address': '48250 Mitchell Stravenue\nPhillipschester, ND 68944',
    'text': 'Prepare peace sense approach according major old point. Job interesting growth me better policy wait.\nRed worker within baby the goal certainly director. Drop key drop listen only.',
    'email': 'perezandrew@example.net',
    'phone_number': '001-299-585-1459x127',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Hobbs',
],
    'json': {
    'name': 'Susan Horne',
    'address': '246 Hudson Hollow\nBlackside, HI 58868',
},
    'key18690': 'value37690',
    'key98381': 'value25600',
    'key94320': 'value92401',
    'key39620': 'value62485',
    'key87437': 'value96498',
    'key78544': 'value72882',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Donna Lynch',
    'address': 'Unit 2970 Box 5325\nDPO AP 54430',
    'text': 'Share happen open avoid provide.\nBeautiful community bag maybe technology receive fly.',
    'email': 'campbellchristopher@example.com',
    'phone_number': '+1-539-230-5230x726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Cook',
    'John Cooke',
    'Sarah White',
    'Thomas Pham',
    'Tammy Lang',
    'Shannon Smith',
],
    'json': {
    'name': 'Tiffany Brown',
    'address': '698 Meyer Spur\nNew Andreaville, WI 60879',
},
    'key73254': 'value16630',
    'key14017': 'value78216',
    'key56218': 'value63849',
    'key81554': 'value15091',
    'key47290': 'value65120',
    'key67063': 'value51351',
    'key4495': 'value51163',
    'key28157': 'value81872',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Karen Gregory',
    'address': '5494 Petersen Glens Apt. 624\nRamirezmouth, VA 31295',
    'text': 'Sell drug move. Remember bag student eight worry.\nConcern worry maintain. She sea no fast. Dog occur human to affect.',
    'email': 'uroberson@example.org',
    'phone_number': '001-586-860-8552x3886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Madeline Knight',
],
    'json': {
    'name': 'Patricia Lopez',
    'address': '21772 Jonathan Springs\nAustinfort, MN 54217',
},
    'key67178': 'value89212',
    'key37505': 'value99985',
    'key47780': 'value21239',
    'key38237': 'value65252',
    'key77770': 'value16095',
    'key26596': 'value4748',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Tamara Young',
    'address': '09572 Janet Islands Apt. 551\nLukehaven, PR 28006',
    'text': 'Scientist chance number land. Ready let approach threat. This example medical across. Could green section six weight ability him turn.',
    'email': 'jennifer00@example.com',
    'phone_number': '001-679-365-1781x428',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Ortiz',
    'Charles Baird',
    'Benjamin Brock',
    'Nancy Gates',
    'Ms. Nancy Schneider',
    'Kevin Gordon',
    'Breanna Vance',
    'Kyle Watson',
    'Gloria Hess',
    'Manuel Calderon',
],
    'json': {
    'name': 'Virginia Ferrell',
    'address': '9552 Potter Station Apt. 846\nShortfurt, IL 40708',
},
    'key90275': 'value50672',
    'key92106': 'value38674',
    'key88729': 'value13036',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Patrick Coleman',
    'address': '5907 Woods Flats Apt. 823\nHeidiville, SC 76524',
    'text': 'Improve story politics despite effect environment.\nMeet month key. Significant respond data guy offer field true.\nMouth west station PM. Us husband early service because.',
    'email': 'iayers@example.com',
    'phone_number': '(313)392-5195x203',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Katrina Bell',
    'David Campbell',
    'Craig Osborne',
    'Alexis Fitzgerald',
    'Michael Martinez',
    'Austin Evans',
    'Dawn Garcia',
    'Mrs. Jamie Garza',
    'Michael Colon',
    'Robert Douglas',
],
    'json': {
    'name': 'Anthony Crawford',
    'address': '483 Flynn Fall\nCantuborough, KY 29259',
},
    'key30009': 'value45943',
    'key86674': 'value6683',
    'key97445': 'value66601',
    'key71198': 'value85250',
    'key32558': 'value5613',
    'key20534': 'value90475',
    'key65759': 'value6937',
    'key68383': 'value97236',
    'key2922': 'value57175',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Caroline Young',
    'address': '8316 Chase Curve Apt. 534\nEllisside, MO 94454',
    'text': 'Money save you research source whole million. Meet final against clearly tonight score. Win contain visit together. Protect law nor throw nearly success.',
    'email': 'jesus99@example.com',
    'phone_number': '733-337-3759x331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Jacobson',
    'Cassandra Foster',
    'Jason Richardson',
    'Andrea Green',
    'Cheyenne Hall',
    'Claudia Phillips',
    'David Wu',
    'Cassandra Williams',
    'Darlene Deleon',
],
    'json': {
    'name': 'Haley Turner',
    'address': '7737 Bradley Plain\nMargaretside, DC 03701',
},
    'key20773': 'value24613',
    'key11859': 'value10122',
    'key48543': 'value62001',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Christopher Garcia',
    'address': '57751 Arias Point Suite 211\nSouth Patriciashire, SC 67575',
    'text': 'Law memory hand. Born night fear war near. Read trip all well. Leg star ever where fall.\nNote manager although hard far stay. Impact star know step.',
    'email': 'staceypowell@example.com',
    'phone_number': '001-978-977-1232',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Wood',
    'Jessica Watkins',
    'Adam Sheppard',
],
    'json': {
    'name': 'Cynthia Silva',
    'address': 'Unit 5226 Box 0223\nDPO AE 90081',
},
    'key20845': 'value71756',
    'key28620': 'value60989',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Cody Baker Jr.',
    'address': '7772 Mary Shoal\nDonnaview, NC 77923',
    'text': 'Various month start trade. Man lose example grow. Put magazine analysis realize improve summer probably.\nTeam notice somebody much politics. Industry simple buy call collection owner.',
    'email': 'owagner@example.com',
    'phone_number': '594.559.4514',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Bullock',
    'Kimberly Weaver',
    'Matthew Williams',
    'Angela Wilson',
    'Linda Peterson',
    'James Montgomery',
    'Matthew Duran',
    'Meagan Price',
    'Eric Nolan',
    'Leslie Fields',
],
    'json': {
    'name': 'Mark Evans',
    'address': '9831 Robertson Ridges Suite 454\nBlackwelltown, KS 91202',
},
    'key41306': 'value3002',
    'key71364': 'value21231',
    'key57999': 'value32636',
    'key49317': 'value58556',
    'key30565': 'value52306',
    'key44227': 'value99842',
    'key13395': 'value46430',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Molly Wilson',
    'address': '074 Jennifer Estates\nChristopherton, MH 13056',
    'text': 'Firm good off strong reveal. Quite able security police change paper.\nMethod student maybe admit here ago. Customer available black west.\nRead boy our southern mouth.',
    'email': 'baileyashley@example.com',
    'phone_number': '001-687-712-8149x2637',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Louis Merritt',
    'Curtis Lang',
    'Morgan Collins',
    'Heather Ware',
    'Nathan Cooper',
],
    'json': {
    'name': 'Timothy Cole',
    'address': '832 Michelle Roads\nWillisland, OK 74561',
},
    'key15128': 'value71805',
    'key96153': 'value69107',
    'key10066': 'value5254',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Sean Guerrero',
    'address': '597 Franco Dam\nMichaelville, HI 82856',
    'text': 'Kind he cover. Ahead evidence near despite position direction. Both plant like chance.',
    'email': 'dennisjackson@example.org',
    'phone_number': '392.903.1574x9761',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Johnson',
    'Keith White',
    'Veronica Strong',
    'Lisa Baldwin',
    'Samantha Elliott',
    'Makayla Lewis',
    'Melissa Davis',
],
    'json': {
    'name': 'Mr. Stephen Soto Jr.',
    'address': '4817 Kathleen Mount Apt. 281\nSaundersberg, NC 59948',
},
    'key92798': 'value71840',
    'key6969': 'value55364',
    'key50014': 'value76567',
    'key93411': 'value96353',
    'key78446': 'value72805',
    'key18436': 'value71280',
    'key98292': 'value29587',
    'key63860': 'value1959',
    'key61204': 'value42559',
    'key51094': 'value52881',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Melanie Silva',
    'address': '59364 Stephanie Pike Apt. 391\nAntoniohaven, NE 91458',
    'text': 'Both entire ok laugh career fill religious low. Though special take film draw figure.\nTime provide positive off alone conference.\nTeacher huge me service.',
    'email': 'patrickgarcia@example.org',
    'phone_number': '+1-428-509-3517x2083',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mary Craig',
    'William Meyers',
    'Mitchell Moore',
    'Susan Luna',
    'Carrie Hansen',
],
    'json': {
    'name': 'Lawrence Davis',
    'address': '20503 Crystal Row\nPort Richardmouth, PA 83240',
},
    'key46002': 'value64312',
    'key56110': 'value74527',
    'key88813': 'value59145',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Rebecca Curtis',
    'address': '53720 Leonard Rest Apt. 286\nWest Heatherborough, NM 77311',
    'text': 'Beautiful usually career fund second receive involve. Know put turn large character again her. Name at television Republican effort training.',
    'email': 'vford@example.com',
    'phone_number': '565.841.0889x43106',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Bennett',
    'Carmen Dixon',
    'Elijah Richardson',
    'Christian Thompson',
    'Michael Santos',
    'Nathan Curtis',
    'Scott Gonzalez',
    'Cheryl Diaz',
],
    'json': {
    'name': 'Cynthia Gibbs',
    'address': '72208 Kendra Flat\nSouth Sarahstad, WY 48483',
},
    'key17075': 'value6347',
    'key55649': 'value98500',
    'key5342': 'value61351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Curtis Fleming',
    'address': '879 Brooks Views Apt. 774\nStephenhaven, SD 50688',
    'text': 'Parent lot bag bad option. Style community place impact man seek happen.\nRealize when almost change. Around today after.',
    'email': 'haleyolsen@example.org',
    'phone_number': '566-415-8406',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christian Stark',
    'Paul Anderson',
    'Jeffery Bryant',
    'Lori Gray',
],
    'json': {
    'name': 'Robert Owen',
    'address': '89619 Hobbs Flats Apt. 222\nPort Michaelton, NM 56979',
},
    'key24797': 'value68070',
    'key7086': 'value85791',
    'key95203': 'value27411',
    'key18489': 'value51683',
    'key13885': 'value69640',
    'key66988': 'value8616',
    'key3863': 'value77562',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Monica Watts',
    'address': '79024 Ford Harbors\nValenciaside, OH 58473',
    'text': 'Head physical politics nice technology people modern.\nNight investment force lot line indicate. Someone by degree suffer rich. Collection decide organization someone.',
    'email': 'aaron21@example.net',
    'phone_number': '262-595-5721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Smith',
    'David Clark',
    'Anthony Lee',
    'Deanna Harrison',
    'Amy Thompson MD',
    'Amy Cooper',
],
    'json': {
    'name': 'Jody Chambers',
    'address': '28718 Jennifer Run Apt. 696\nHendersonburgh, UT 05694',
},
    'key8500': 'value17480',
    'key93546': 'value36581',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Richard Walsh',
    'address': '31013 Thomas Cliff\nPort Gregory, NC 37496',
    'text': 'Media prepare war. Middle whom glass pattern customer. No whose last board.\nHistory modern message three. Beat today agree international.',
    'email': 'lfitzgerald@example.com',
    'phone_number': '786-772-1837x6753',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'William Simmons',
    'Brittany Lewis',
    'Christina Brooks',
    'Thomas Coleman',
    'Cynthia Mitchell',
    'Seth Mendoza',
    'Alyssa Brock',
    'Jasmine Oconnell DDS',
    'Christopher Howard',
    'Sarah Wilkerson',
],
    'json': {
    'name': 'Anthony Grant',
    'address': '1946 John Fork\nLake Joanne, NV 65474',
},
    'key19528': 'value30841',
    'key97208': 'value97846',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Brian Jones',
    'address': '2899 Brown Turnpike\nJohnsonberg, WA 21489',
    'text': 'General simple while air western side break anyone.\nItself because third car wrong coach opportunity media. Yard central threat and deal alone black. Hot government along or organization hit.',
    'email': 'derrick50@example.org',
    'phone_number': '(395)470-1630x34667',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mary Dunlap',
    'David Mayer',
    'Colleen Warner',
    'Amy Morales',
    'Ashley Wright',
    'Rodney Taylor',
    'Kevin Martin',
],
    'json': {
    'name': 'Kelly Brown',
    'address': 'PSC 5749, Box 5741\nAPO AA 15119',
},
    'key27870': 'value76155',
    'key4422': 'value75221',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Jessica Robertson',
    'address': '9428 Travis Ford\nLake Kaylachester, DC 66238',
    'text': 'Understand official some work writer. Now line white institution gun focus. Ball turn boy stay will week ability.',
    'email': 'zedwards@example.org',
    'phone_number': '001-208-990-0929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Maldonado',
    'Brandon Sweeney',
    'Vicki Mccarthy',
    'Harold Williams',
    'Robert Shields',
    'Natalie Humphrey',
],
    'json': {
    'name': 'Sabrina Wiley',
    'address': '9390 Sara Way Apt. 894\nBrownland, GU 91320',
},
    'key98280': 'value14325',
    'key39146': 'value66426',
    'key88997': 'value4322',
    'key68387': 'value1233',
    'key10919': 'value63743',
    'key49368': 'value64727',
    'key71956': 'value68257',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Jonathan Williams',
    'address': '05046 Carrie Stream\nEmilyport, KY 78277',
    'text': 'Stock clear news available enjoy. Lose audience situation blood.\nMeeting friend discuss street responsibility remain fly. Director against happy throughout little heart exist.',
    'email': 'priscilla74@example.org',
    'phone_number': '750.822.0876x266',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Phillip Hayes',
    'Katelyn Reyes',
    'Caitlin Harris',
    'Brittany Baldwin',
    'Matthew Mata',
    'Erica Pineda',
    'Benjamin King',
    'Andrew Stewart',
    'Gregory Nolan',
    'Jonathan Hernandez',
],
    'json': {
    'name': 'Kimberly Baker',
    'address': '514 Chaney Groves\nNew Joshuamouth, RI 23563',
},
    'key35310': 'value95429',
    'key99106': 'value29237',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Charles Cortez',
    'address': '3067 Frank Manors Suite 967\nJessicaborough, ND 82226',
    'text': 'Election month toward true son. Actually between already policy ball wide professional. Surface whether per economy these serve teacher.',
    'email': 'timothybrandt@example.net',
    'phone_number': '4289834816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jason Ponce',
    'Linda Schneider',
    'Danielle Nelson',
    'Christopher Evans MD',
    'Herbert Griffith',
    'Christopher Nicholson',
],
    'json': {
    'name': 'Kimberly Castro MD',
    'address': '8624 Thomas Rest\nEllisonfurt, CT 65659',
},
    'key45629': 'value34229',
    'key26019': 'value49185',
    'key20793': 'value2566',
    'key89967': 'value3329',
    'key63177': 'value36444',
    'key60564': 'value92626',
    'key40976': 'value68895',
    'key75314': 'value18654',
    'key60095': 'value50872',
    'key88243': 'value42909',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Brianna Hurley',
    'address': '4254 Becker Shore Apt. 076\nNorth Donna, KS 82327',
    'text': 'Expect manager firm pull choice.\nSeason look though affect reason. Should whom check enjoy suggest.',
    'email': 'kayla24@example.com',
    'phone_number': '6326620036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Bartlett',
    'Patrick Martinez',
    'Mr. Jeffery Kemp',
    'Mr. Travis Moyer',
    'Tracy Cooper',
    'Rita Hernandez',
    'Christy Baker',
    'Jason Arias',
],
    'json': {
    'name': 'Elizabeth Clark',
    'address': '977 Atkinson Underpass\nPerkinsport, IA 04584',
},
    'key50447': 'value10160',
    'key98513': 'value36480',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'John Williams',
    'address': '3145 Adam Forks Apt. 180\nPort Chadfurt, ID 28010',
    'text': 'Player mission including tough miss. Clear season show box dog own. Pm listen bring million practice somebody. Thousand teach personal many all.\nDifference heart city push. Green police mention know.',
    'email': 'jenkinsamanda@example.org',
    'phone_number': '909.442.9628',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Martin',
    'Jennifer Smith',
    'George Todd',
    'Sherry Nichols',
    'Kevin Moore',
    'Leonard Fischer',
    'Mackenzie Daniel',
    'Kimberly Ray',
],
    'json': {
    'name': 'Alexa Gray',
    'address': '58704 Dillon Roads Apt. 743\nWest Jilltown, ME 27049',
},
    'key47247': 'value89019',
    'key70094': 'value20036',
    'key75849': 'value69444',
    'key40780': 'value22122',
    'key30411': 'value70986',
    'key73063': 'value24500',
    'key79646': 'value97801',
    'key42294': 'value37108',
    'key22037': 'value4537',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Haley May',
    'address': '9946 Kristine Fall\nElizabethshire, UT 58757',
    'text': 'Feeling stop voice study someone benefit within difficult. Million prepare wish perhaps.',
    'email': 'williamsjeffery@example.com',
    'phone_number': '406.676.8491x5099',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Jimenez',
    'Pamela Martinez',
    'Amanda Lindsey',
    'Denise Arnold',
    'John Chase',
    'Gabriel Gay',
    'Lauren Allen',
    'Dawn Williams',
],
    'json': {
    'name': 'Joseph Watkins',
    'address': '84757 Allison Street Apt. 163\nMitchellmouth, NM 61191',
},
    'key66619': 'value46909',
    'key64268': 'value69179',
    'key36130': 'value38642',
    'key87743': 'value92519',
    'key97716': 'value17729',
    'key73469': 'value58601',
    'key76457': 'value10687',
    'key41538': 'value3163',
    'key97431': 'value92546',
    'key94265': 'value21601',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Kenneth Bryant',
    'address': 'Unit 0120 Box 2593\nDPO AA 84506',
    'text': 'Likely view note quickly build level plant what.\nRoad card camera enough perhaps animal edge. Team begin fire notice lose outside. Fact our through action current value.',
    'email': 'greenerica@example.org',
    'phone_number': '+1-558-237-0666x45780',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Harry Rice',
    'Sarah Ryan',
    'Debra Horton',
    'Kathy Farmer',
    'Jeffrey Robinson',
    'Duane Carter',
    'Bryan Huff',
    'Sonya Wilson',
    'Jessica Stewart',
    'Sandra Bailey',
],
    'json': {
    'name': 'Brandon Cain',
    'address': '63998 Lewis Neck\nNorth Mark, AS 33895',
},
    'key11234': 'value19549',
    'key66333': 'value77037',
    'key2497': 'value76613',
    'key7277': 'value24708',
    'key97741': 'value18984',
    'key7385': 'value62903',
    'key65188': 'value27391',
    'key4969': 'value14593',
    'key22686': 'value67274',
    'key15058': 'value15150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Alicia Holmes',
    'address': '46954 Yoder Extension\nChristopherfurt, PR 17319',
    'text': 'Recent beyond activity man individual weight million. Enjoy generation minute energy machine over base. Most another person fine general.',
    'email': 'jamesacevedo@example.com',
    'phone_number': '(549)438-0089',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Darrell Baker',
    'Gloria Salazar',
    'Shelley Williams',
    'Christopher Williams',
    'Janet Porter',
],
    'json': {
    'name': 'Crystal Page',
    'address': 'PSC 7791, Box 6190\nAPO AA 85467',
},
    'key64324': 'value37185',
    'key48827': 'value70782',
    'key83136': 'value14374',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Julie Johnson',
    'address': '3284 Kevin Corner Apt. 706\nSouth Louis, TX 55082',
    'text': 'Sister would win interview. Attention keep green there eight later fast.\nKey point at number. Mean development catch husband. Until knowledge trial from girl ago last be.',
    'email': 'angelica25@example.com',
    'phone_number': '(914)211-6414x64981',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Evelyn Hutchinson',
    'Sherry Petty',
    'Matthew Franklin',
    'Rhonda King',
    'Theresa James',
    'Tyler Jensen',
    'Tonya Chen',
    'Peter Taylor',
    'Hailey Martinez',
],
    'json': {
    'name': 'Victoria Davis',
    'address': '1691 Ross Underpass\nThomasview, AL 08334',
},
    'key67832': 'value53892',
    'key6623': 'value16863',
    'key37329': 'value82010',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Tamara Williams',
    'address': '700 Nicholas Union Suite 441\nSmithport, ID 52258',
    'text': 'Material begin sea or on require than try. Important ever ready guy consider heart store. Particularly myself do health factor.',
    'email': 'brogers@example.org',
    'phone_number': '666.590.0816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Best',
    'Alicia Christian',
    'Kevin Parks',
    'Tony Solis',
    'Jennifer Johnson',
    'Mark Donovan',
    'Anthony Medina',
],
    'json': {
    'name': 'Kelly Chavez',
    'address': '06593 Miller Unions\nSouth Cody, MT 71627',
},
    'key85484': 'value45842',
    'key89315': 'value13493',
    'key70495': 'value96602',
    'key79069': 'value72415',
    'key11630': 'value40924',
    'key36001': 'value18733',
    'key1821': 'value38192',
    'key5606': 'value40249',
    'key97457': 'value51132',
    'key61777': 'value40394',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Richard Mckinney',
    'address': '305 Miles Heights\nPort Rodney, AR 53304',
    'text': 'Involve win picture PM social. Course ten join site above hot bad. Experience his really fine.\nInformation work quickly word. Me police suddenly white she others.',
    'email': 'leashley@example.net',
    'phone_number': '(418)505-7307',
    'array_int_dynamic': [
    36096,
],
    'array_varchar_dynamic': [
    'Richard Sutton',
    'Grace Mitchell',
    'Sarah Roach',
    'Phillip Lowe',
],
    'json': {
    'name': 'Mr. Austin Perry',
    'address': '317 Katherine Fork\nSouth Alyssa, RI 13814',
},
    'key90072': 'value39946',
    'key3844': 'value3837',
    'key95468': 'value75686',
    'key57299': 'value37586',
    'key76975': 'value37365',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Cameron Vasquez',
    'address': '981 Jacob Wall\nWelchchester, ME 48645',
    'text': 'Page discuss sense score.\nPurpose sense arm when. Trial walk raise out marriage according miss. Support experience pick physical.',
    'email': 'paulgreen@example.org',
    'phone_number': '+1-876-262-5711x53397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Duke',
    'Monique Holder',
    'Joseph Carpenter',
    'Megan Hicks',
    'Jared Gonzales',
],
    'json': {
    'name': 'Anthony Weiss',
    'address': '8874 Larsen Pines\nKaylabury, FM 93529',
},
    'key24472': 'value78520',
    'key86205': 'value20783',
    'key34473': 'value79670',
    'key25661': 'value49855',
    'key34029': 'value17595',
    'key7044': 'value46372',
    'key75862': 'value90649',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Sabrina Clark',
    'address': '89648 Shawn Route\nPort Peggyshire, LA 40990',
    'text': 'Dark research east reveal major. Admit kid sister young theory site experience effort. Perform just rule writer. Must property serious true agency town suddenly.',
    'email': 'james39@example.org',
    'phone_number': '938-383-4774',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Hernandez',
    'Joshua Myers',
    'David Rodriguez',
    'Kaitlyn Brown',
    'Kelly Maldonado',
    'Pamela Shea',
    'Robert Davis',
    'Renee Smith',
],
    'json': {
    'name': 'Ryan Wells',
    'address': '1931 Garcia Fields Suite 873\nEast Michelle, ME 95904',
},
    'key30094': 'value83492',
    'key93098': 'value60260',
    'key30501': 'value33989',
    'key72943': 'value77613',
    'key46517': 'value29128',
    'key19010': 'value45428',
    'key93052': 'value32515',
    'key74566': 'value82103',
    'key74092': 'value47184',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Gabriel Williams',
    'address': '5277 Mccoy Passage\nJasonport, SD 74636',
    'text': 'Represent apply not thousand war. Action staff over anything if. Every left foot although answer trial finish.\nRequire civil pretty nor baby. During crime form arm marriage.',
    'email': 'trobinson@example.net',
    'phone_number': '732.716.8690x849',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Griffin',
    'James Cruz',
    'Mrs. Kaylee Reyes',
    'Jennifer Hayes',
    'Andrew Bauer',
],
    'json': {
    'name': 'Susan Mendoza',
    'address': '678 Jasmine Brook\nNew Lori, IN 85624',
},
    'key96543': 'value5811',
    'key57612': 'value65722',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Casey Baker',
    'address': 'PSC 6991, Box 2380\nAPO AE 78667',
    'text': 'Step kitchen his.\nLaugh material back up. Region respond tell both we should politics trouble. Between government special chair plant there agreement.\nCandidate face finish home require huge.',
    'email': 'jonathanmitchell@example.org',
    'phone_number': '+1-677-212-9836x331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Ray',
    'David Schroeder',
    'Ruth Schultz',
    'Eric Harrington',
    'Bethany Walker',
    'Joseph Garrett',
    'Robert Perez',
],
    'json': {
    'name': 'Michael Wilson',
    'address': '18365 April Camp\nEast Lynn, NV 23319',
},
    'key97412': 'value63707',
    'key59333': 'value90369',
    'key27295': 'value24407',
    'key59041': 'value30994',
    'key5589': 'value22350',
    'key15492': 'value87039',
    'key26502': 'value52442',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Jason Porter',
    'address': '673 Raven Crest Suite 354\nJimmyshire, TX 51588',
    'text': 'Still open worker.\nReveal product establish much hotel far require. Hospital police scientist admit.',
    'email': 'vanessacuevas@example.org',
    'phone_number': '832.616.8717x686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Lee',
    'Sherri Roberts',
    'Dennis Davis',
    'Lori Hoffman',
],
    'json': {
    'name': 'Barry Davenport',
    'address': 'PSC 0775, Box 5634\nAPO AP 50714',
},
    'key68205': 'value14866',
    'key38676': 'value31480',
    'key74087': 'value44072',
    'key59495': 'value62894',
    'key84693': 'value80058',
    'key76365': 'value21534',
    'key69498': 'value29186',
    'key24162': 'value38058',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Becky Stokes',
    'address': '711 Jackson Parkway\nNew Cindy, KS 34197',
    'text': 'Painting organization already likely score memory opportunity.',
    'email': 'markfrench@example.com',
    'phone_number': '+1-918-439-4942x0133',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Erica Salinas',
    'Destiny Martin',
    'Todd Ballard',
    'Jordan Herrera DDS',
    'Wendy Rangel',
    'Taylor Ortiz',
    'Stephanie Taylor',
],
    'json': {
    'name': 'Dr. Joshua Holland',
    'address': 'USS Washington\nFPO AA 53438',
},
    'key2000': 'value51513',
    'key64359': 'value32578',
    'key72141': 'value56246',
    'key47205': 'value79257',
    'key6149': 'value83125',
    'key70441': 'value75057',
    'key9158': 'value75267',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Kathleen Burnett',
    'address': '94566 Anthony Pines\nJacobhaven, AK 35047',
    'text': 'Head arrive economy late decide fact national everyone. Culture suddenly among these.\nShow message anyone oil senior not. Last anything medical force house.',
    'email': 'ellisrobin@example.org',
    'phone_number': '532-648-3198x21083',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Conner',
    'Anna Goodwin',
    'Angel Adams',
    'Nancy Guzman',
    'Kathleen Brown',
    'Patricia Davidson',
],
    'json': {
    'name': 'Noah Hall',
    'address': '861 Melissa Expressway\nHuertafurt, IN 12948',
},
    'key6157': 'value67107',
    'key4910': 'value41964',
    'key63530': 'value66217',
    'key80523': 'value40258',
    'key99155': 'value30794',
    'key67424': 'value93591',
    'key16185': 'value99239',
    'key20443': 'value16564',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Scott Lewis',
    'address': '9094 Carlos Plaza Suite 080\nNew Hectorhaven, NJ 98938',
    'text': 'Past executive environmental always three indeed community. Tree perhaps democratic south. Rise begin low per.\nProduct chair offer learn social spend mention themselves. General head wife call.',
    'email': 'michele65@example.net',
    'phone_number': '+1-264-884-3181x8603',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Yvonne Nelson',
    'Luke Castillo',
    'Michelle Martinez',
    'Melody Armstrong',
],
    'json': {
    'name': 'Ryan Craig',
    'address': '81600 Tiffany Roads Apt. 741\nTravisshire, AS 14449',
},
    'key26996': 'value53205',
    'key25032': 'value51782',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Joseph Casey',
    'address': '768 Knapp Roads\nPort Michael, OK 96815',
    'text': 'Arrive firm white peace staff. Personal religious suddenly point. Attorney radio brother to third garden.\nAdministration laugh morning black meeting. Think kind against soon administration new.',
    'email': 'brandon61@example.com',
    'phone_number': '(220)929-6110x839',
    'array_int_dynamic': [
    99717,
],
    'array_varchar_dynamic': [
    'Calvin Sparks',
    'Joseph Gonzalez',
],
    'json': {
    'name': 'John Williams',
    'address': '89457 Joshua Camp\nPort Denise, CT 64626',
},
    'key71560': 'value50969',
    'key5093': 'value20082',
    'key23926': 'value14504',
    'key17832': 'value85630',
    'key2382': 'value43284',
    'key3134': 'value95780',
    'key23288': 'value80184',
    'key4096': 'value26157',
    'key4493': 'value31789',
    'key38498': 'value29210',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Amanda Buck',
    'address': '56575 Christina Shores Apt. 571\nEast Josephmouth, MH 20900',
    'text': 'Travel near black resource.\nRoad make message speak. Community political should soldier. Worker ok strategy get director company by. Product along say spend trouble bit.',
    'email': 'marybauer@example.org',
    'phone_number': '+1-311-567-6770x67641',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Campbell',
    'Hailey Hunt',
    'Tiffany Smith',
    'Diana Andrews',
    'Juan Butler',
    'Jessica Willis',
    'Blake Turner',
    'Francisco Torres',
    'Erika Brandt',
],
    'json': {
    'name': 'Nichole Gamble',
    'address': '056 Joshua Meadow\nSantiagoville, MN 80122',
},
    'key63450': 'value52210',
    'key46660': 'value92535',
    'key26816': 'value32065',
    'key87498': 'value4161',
    'key9127': 'value41811',
    'key53466': 'value14207',
    'key40079': 'value42853',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Joan Smith',
    'address': 'PSC 9977, Box 9934\nAPO AA 31257',
    'text': 'Best some finally debate food film world. Red challenge itself thing.\nLot experience meeting theory. Image tree Congress. Condition and garden American natural forget.',
    'email': 'aperez@example.net',
    'phone_number': '291.494.8570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Annette Wright',
    'Brianna Montoya DDS',
    'Jimmy May',
],
    'json': {
    'name': 'Kevin Harrington MD',
    'address': '368 Dana Mall Suite 706\nLake Andreaside, WI 76774',
},
    'key28014': 'value68095',
    'key68950': 'value81528',
    'key36271': 'value3369',
    'key59569': 'value83899',
    'key28366': 'value62023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Jonathan Peterson',
    'address': 'Unit 1448 Box 0323\nDPO AA 39059',
    'text': 'Significant especially should clearly couple.\nMiss knowledge north. Away leader final concern scientist. To others probably system stock itself stuff.\nNow too try wonder. Ready wide record sort.',
    'email': 'bmedina@example.org',
    'phone_number': '517-955-3733x1707',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Arthur Baker',
    'Christopher Johnson',
],
    'json': {
    'name': 'Phillip Jones',
    'address': '500 James Heights\nWest Sharontown, FM 91866',
},
    'key80813': 'value57463',
    'key45850': 'value1905',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Dr. Gary Hoffman',
    'address': '1903 Rachel Springs Apt. 510\nLake Linda, LA 02700',
    'text': 'Trouble especially simple green whose reason. Animal give different bank indeed. Close do sure. Either value people.',
    'email': 'daviscody@example.net',
    'phone_number': '223.367.6177',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Donald Marshall',
    'Larry Dickerson',
    'Amanda Tran DDS',
    'David Hoffman',
    'Dan Mcmillan',
    'Angela Thornton',
    'Melissa Stephens',
    'Amanda Mills',
    'Joshua Mcintyre',
],
    'json': {
    'name': 'Lori Armstrong',
    'address': '9234 Santiago Freeway Apt. 744\nHernandezshire, AZ 78702',
},
    'key53637': 'value8398',
    'key14565': 'value3621',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Alec Henry',
    'address': '9073 Vazquez Pike\nEast Paul, IN 09926',
    'text': 'He author range big range meeting. Report see cold office dinner.\nLoss central total particularly. Level final direction medical maybe production. Trade number would.',
    'email': 'broach@example.net',
    'phone_number': '(338)240-3710x2028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Fischer',
    'Randy Cordova',
    'Lisa Sosa',
    'Nicholas Haynes',
    'Tiffany Johnson',
    'Christina Hall',
    'Jordan Gibson',
    'Michael Murphy',
],
    'json': {
    'name': 'Dustin Jenkins',
    'address': '525 Wendy Hollow\nPort Anthonyborough, IN 60130',
},
    'key57185': 'value38459',
    'key28354': 'value54430',
    'key64966': 'value19908',
    'key5341': 'value46574',
    'key89712': 'value37934',
    'key29776': 'value75586',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Stephen Price',
    'address': '584 Sanders Lake\nAntoniofort, TN 66685',
    'text': 'Very price expert conference maintain. From follow support store. Fire worry study amount never.\nGo little vote doctor maintain himself walk. Never week cut. Five should anyone.',
    'email': 'jameskeith@example.net',
    'phone_number': '714-703-2196x63771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Jennifer Allen DVM',
    'Emma Spears',
    'Brenda Franklin',
    'Jennifer Rush',
],
    'json': {
    'name': 'Heather Lewis',
    'address': '1953 Wall Drives Suite 228\nCynthiamouth, NH 98924',
},
    'key20883': 'value14608',
    'key74371': 'value44045',
    'key36275': 'value95583',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Francis Reeves',
    'address': '38925 Santos Crescent\nChurchside, VT 55232',
    'text': 'Lawyer too theory two seat debate knowledge. Produce paper according customer. Voice benefit floor bag sense southern close.\nStill tax ready leader. If teach church before specific financial.',
    'email': 'higginsmaria@example.com',
    'phone_number': '563.921.9292x22008',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Dunn MD',
    'Wayne Mcguire',
    'Karen Taylor',
    'Dr. Lori Johnson',
    'Heather Edwards',
    'Kristen Rice',
    'Holly Martin',
    'Tiffany Roy',
    'Zachary Carter',
    'Derek Wong',
],
    'json': {
    'name': 'Andrea Thompson',
    'address': '52162 Laura Islands\nSouth Tanyaberg, MN 12503',
},
    'key67258': 'value80008',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Katherine Rose',
    'address': '88686 Scott Route Suite 638\nPort Michaelmouth, WV 46901',
    'text': 'Yeah practice same line much. Floor us sometimes also.\nAhead those ago. Treatment turn series friend weight.\nBenefit option sit argue day media treatment. More leave dog. Address pay such bank.',
    'email': 'rwillis@example.org',
    'phone_number': '6714620735',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Steven Wilson',
    'Christopher Lara',
    'Kathryn Ellis',
    'Katherine Burch',
],
    'json': {
    'name': 'Timothy Compton',
    'address': '5583 Stephen Springs\nRamirezland, WV 94086',
},
    'key38836': 'value28196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Pamela Walker',
    'address': '49047 Escobar Prairie Apt. 639\nSamuelstad, VA 06165',
    'text': 'Break group parent forward east development. Investment threat anything fly.\nWalk pay new almost foreign TV carry. Many different suggest policy life.',
    'email': 'jessica77@example.org',
    'phone_number': '492.275.9246x62386',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dale Jenkins',
    'Andrew Butler',
    'Lisa Lucas',
    'Nicholas Meyer',
    'Elizabeth Jackson',
    'Justin Rogers',
],
    'json': {
    'name': 'Samantha Oconnor',
    'address': '138 Mitchell Spurs\nWest Samuel, CO 18100',
},
    'key69149': 'value70311',
    'key66343': 'value28345',
    'key60764': 'value99934',
    'key63318': 'value45040',
    'key97081': 'value23856',
    'key52872': 'value68137',
    'key30331': 'value15530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Robert Carroll DDS',
    'address': '5307 Holt Plains Apt. 088\nLake Melanie, TX 69798',
    'text': 'Early hard when. Candidate identify scientist perhaps also exactly.',
    'email': 'browntimothy@example.net',
    'phone_number': '827.737.6609',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Sheppard',
    'Tammy Gilbert',
    'Deborah Beck',
    'David Leon',
    'Joseph Pope',
    'Alison Garcia',
    'Kylie Daniels',
    'William Ball',
],
    'json': {
    'name': 'Jill Richardson',
    'address': '4581 Dominguez Freeway\nRobertton, WI 87074',
},
    'key56315': 'value54917',
    'key50739': 'value47703',
    'key39391': 'value65440',
    'key83637': 'value52703',
    'key495': 'value83411',
    'key57100': 'value755',
    'key38930': 'value41418',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Michelle Young',
    'address': '89155 Ashley Summit Suite 902\nPort Danielfurt, WV 95318',
    'text': 'Often trip behind finish wear method believe. Must lead assume similar magazine doctor sense cost. Order probably late idea manager rather.',
    'email': 'christopher95@example.org',
    'phone_number': '+1-980-916-8488x205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tim Lindsey',
    'Robert Tate',
    'Elijah Patterson',
    'Sharon Hull',
    'Barbara Anderson',
    'Taylor Davis',
    'Brenda Bradley',
    'Jeanette Palmer',
],
    'json': {
    'name': 'Tiffany Griffith',
    'address': '995 Flores Turnpike\nRoseshire, IA 63826',
},
    'key88060': 'value70',
    'key14517': 'value90688',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Lacey Duffy',
    'address': '4965 Howell Walk\nNew Thomas, OR 81573',
    'text': 'Sell sign painting impact never themselves beautiful. Up hear choice behavior floor sing. Degree arm pass more. Water explain listen economic.',
    'email': 'jareddrake@example.com',
    'phone_number': '(507)612-6193',
    'array_int_dynamic': [
    1710,
],
    'array_varchar_dynamic': [
    'Ellen Choi',
    'Sandra Jacobs',
    'George Navarro',
    'Joseph Hawkins',
    'Carrie Hess',
    'Mary Perry',
    'Jasmine Johnson',
    'Connor Fernandez',
    'Latasha Garcia',
],
    'json': {
    'name': 'Monica Taylor',
    'address': '5594 Hayden Stravenue\nStephaniefurt, RI 58492',
},
    'key62205': 'value85813',
    'key46855': 'value33473',
    'key3253': 'value17215',
    'key27325': 'value37548',
    'key1968': 'value48983',
    'key77485': 'value92789',
    'key53411': 'value68901',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Daniel Torres',
    'address': '640 Johnson Pass Apt. 492\nLake Jessica, WA 81579',
    'text': 'Avoid own tend near music condition agent fall. Relationship try wall room community.\nHit task improve apply investment draw billion. Ten give bring paper program.',
    'email': 'georgeeddie@example.com',
    'phone_number': '912.530.5622',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Henry Jones',
    'Brian Velazquez',
],
    'json': {
    'name': 'Larry Williamson',
    'address': '3169 Lisa Street\nEast Rachel, AR 21986',
},
    'key98346': 'value96170',
    'key52438': 'value60123',
    'key45162': 'value31904',
    'key3145': 'value4225',
    'key64162': 'value59222',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'James Taylor',
    'address': '79426 Sarah Ville\nNew Julietown, ND 81803',
    'text': 'Movement here administration current modern such indicate billion. His everybody day thank central travel note.',
    'email': 'laurendavis@example.com',
    'phone_number': '656-719-7285',
    'array_int_dynamic': [
    54588,
],
    'array_varchar_dynamic': [
    'Pamela Roberts',
],
    'json': {
    'name': 'Sydney Adams',
    'address': '144 Berry Flats\nPatriciabury, PW 10008',
},
    'key82485': 'value48622',
    'key32733': 'value61639',
    'key20184': 'value71053',
    'key85898': 'value91128',
    'key45566': 'value22666',
    'key88731': 'value36876',
    'key68939': 'value29044',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Justin Davila',
    'address': '71148 Hall Points\nEugeneberg, WV 40760',
    'text': 'Business through hope traditional. Return perform operation situation.',
    'email': 'matthew45@example.org',
    'phone_number': '(688)904-7991x7002',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Strickland',
    'Mary Huff',
    'Benjamin Higgins',
    'Betty Cummings',
],
    'json': {
    'name': 'Charles Douglas',
    'address': '7504 Campbell Garden Apt. 010\nReneeshire, MS 21201',
},
    'key49203': 'value34809',
    'key19756': 'value44631',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Heather Lopez',
    'address': '132 Thompson Path\nPort Matthewmouth, IN 97877',
    'text': 'Explain clear onto order head. Politics management ball beat reveal. Certain office top network.\nAfter model help employee. Thing full walk attack oil quality.',
    'email': 'hayesdustin@example.org',
    'phone_number': '(703)805-4644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Larry Roberts',
    'Russell Heath',
    'Joshua Rhodes',
    'William Wright',
    'Erin Stewart',
],
    'json': {
    'name': 'Trevor Jones',
    'address': '85432 Timothy Port\nRaymondbury, NV 28121',
},
    'key80983': 'value33559',
    'key40963': 'value44818',
    'key24257': 'value63202',
    'key48330': 'value97794',
    'key29575': 'value78321',
    'key30029': 'value42697',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Ryan Ruiz',
    'address': '183 Morgan Plaza\nWest Markborough, NM 61441',
    'text': 'Yard song poor every more form member. What idea environmental house represent wall.',
    'email': 'sfranklin@example.com',
    'phone_number': '+1-732-963-2065x919',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Carl Elliott',
    'Laurie Ford',
    'Brandon Fox',
    'Bruce Lam',
    'Daniel Kent',
    'Collin Chambers',
],
    'json': {
    'name': 'Patricia Barton',
    'address': '25309 Mejia Forge\nPatriciahaven, NM 50469',
},
    'key53862': 'value43555',
    'key51034': 'value17650',
    'key96778': 'value53919',
    'key5317': 'value84191',
    'key20035': 'value71423',
    'key75622': 'value14144',
    'key34430': 'value81967',
    'key75737': 'value82683',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Zachary Phillips',
    'address': '54994 Mccarty Spur Suite 404\nFryfurt, AK 11854',
    'text': 'Bad care nothing camera myself rest smile building. Board design plan group. Down medical reason reveal.',
    'email': 'markmcdonald@example.org',
    'phone_number': '638.662.9675x2296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Gaines',
    'Chloe Rivas',
    'William Bond',
    'Vanessa Rodriguez',
],
    'json': {
    'name': 'Dr. Mark Brock',
    'address': '25282 Barbara Pass\nEast Joshuaberg, NC 49524',
},
    'key65327': 'value20547',
    'key38577': 'value85739',
    'key9781': 'value7866',
    'key67362': 'value65652',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'James Ellis',
    'address': '049 Gary Canyon Suite 103\nPort William, NV 59336',
    'text': 'Page produce recently instead describe cost interview. Fine certainly account though board continue final.',
    'email': 'johnhernandez@example.org',
    'phone_number': '820.243.6459x13378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Alicia Wallace',
    'Theresa Farrell',
    'Crystal Rodriguez',
    'Morgan Jones',
    'Brendan Saunders',
    'Ronnie Taylor',
    'Tiffany Lopez',
    'Steven Lawson',
],
    'json': {
    'name': 'Ashley Roberts',
    'address': '450 Booker Row\nSouth Anthony, IA 37822',
},
    'key27537': 'value42915',
    'key60238': 'value68836',
    'key61891': 'value23307',
    'key24714': 'value30537',
    'key40615': 'value31022',
    'key77305': 'value87706',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Jeffrey Colon',
    'address': '873 Kevin Island\nSouth Kari, TN 54079',
    'text': 'Become many firm your statement in. Exactly away left magazine break mother.\nGarden travel card. Operation onto think wonder hair enough war. Coach whom wonder cost school hand.',
    'email': 'hensleyjohn@example.org',
    'phone_number': '734-406-4763',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Dana Young',
    'Sergio Davis',
    'Bryan Ramirez',
    'Todd Jennings',
    'Carlos Mitchell',
    'Michael Herrera',
    'Deanna Miranda',
    'Anthony Rodriguez',
],
    'json': {
    'name': 'Steven Ramirez',
    'address': '04761 Christopher Circles\nNew Isabella, DC 89669',
},
    'key87425': 'value10157',
    'key99549': 'value94854',
    'key6217': 'value40531',
    'key13962': 'value8017',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Dr. Valerie Hart PhD',
    'address': '0752 Wanda Mountain\nEast Kimberly, RI 03405',
    'text': 'Far wall story decade business.\nGo answer cover nature analysis society election. Everyone same design resource off. Assume very story.',
    'email': 'saunderscurtis@example.org',
    'phone_number': '7639156569',
    'array_int_dynamic': [
    92489,
],
    'array_varchar_dynamic': [
    'Michael Wilson',
    'Lindsey White',
    'Michael Watson',
    'Craig Anderson',
    'Ronald Peterson',
    'Robin Calhoun DDS',
    'Patrick Herrera MD',
    'Thomas Carter',
],
    'json': {
    'name': 'Ashley Willis',
    'address': '8898 Karen Knoll\nNorth Chelseaborough, ID 13940',
},
    'key77765': 'value79203',
    'key51373': 'value58463',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Donald Garza',
    'address': 'USNV Klein\nFPO AE 03056',
    'text': 'Space better back trade.\nSecond watch body leader perform price. Financial performance stock figure him. Line church four baby people per. Turn whom describe between adult away.',
    'email': 'abuck@example.org',
    'phone_number': '682-790-3269x77958',
    'array_int_dynamic': [
    1439,
],
    'array_varchar_dynamic': [
    'Patricia Nichols',
    'Adrian Butler',
    'Chelsea Rodriguez',
    'Joshua Benson',
    'Cassandra Flynn',
    'Adam Ward',
    'David Lee',
    'Carl Wheeler',
],
    'json': {
    'name': 'Karen Bright',
    'address': '215 Henry Field Apt. 777\nBrianville, VA 34824',
},
    'key36735': 'value88994',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Devin Jensen',
    'address': '20442 Maria Burg\nSouth Joshua, AL 30518',
    'text': 'Agent would parent born. Smile start something final popular network free. Cost we agreement option.\nFar culture local ok kid boy above. Small picture mean assume specific.',
    'email': 'dstewart@example.net',
    'phone_number': '215-819-2505',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Oliver',
    'Christine Herrera',
    'Christine Liu',
    'Nathan Wood',
    'Whitney Hughes',
],
    'json': {
    'name': 'Tyrone Willis',
    'address': '53407 Murray Pike\nAndreaborough, VA 66759',
},
    'key38443': 'value59812',
    'key70574': 'value76118',
    'key13260': 'value99917',
    'key46917': 'value27266',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Jamie Brown',
    'address': '7899 Gonzalez Flat\nPerezside, HI 46230',
    'text': 'Treat enter yourself player into relate yet. Side rest data short wait fish consider. Art audience lot.',
    'email': 'kimberly42@example.org',
    'phone_number': '975-363-0751x6397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Troy Clark',
    'Jennifer Carlson',
    'Elizabeth Nelson',
],
    'json': {
    'name': 'Jennifer Hamilton',
    'address': '16300 Joseph Ford Suite 045\nNorth Sharon, NJ 35184',
},
    'key39564': 'value3068',
    'key68575': 'value98192',
    'key18055': 'value23646',
    'key62133': 'value7192',
    'key9103': 'value72277',
    'key32699': 'value16287',
    'key62985': 'value69521',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Steven Bean',
    'address': '65100 Justin Mill Apt. 008\nPort Christinahaven, WI 54356',
    'text': 'Nature soldier appear common choose provide. Lay think great.\nBudget senior bill piece media space. Now discuss lead contain value know when. Bag own order star similar ahead.',
    'email': 'patriciajackson@example.org',
    'phone_number': '(302)801-7001x0121',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Lewis',
    'Zachary Khan',
    'Christopher Carter',
    'Jennifer Peterson',
    'Jordan Hodges',
    'Troy Collins',
    'Sandra York',
    'Sean West',
    'Katherine Benton',
    'Jesse Rodriguez',
],
    'json': {
    'name': 'Matthew Jarvis',
    'address': '564 Arnold Fields\nNew Danielleburgh, MO 69539',
},
    'key76996': 'value13848',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Stacey Allen',
    'address': '5007 Meyer Mill Suite 973\nThompsonhaven, KY 53788',
    'text': 'Occur image finally certainly or position important. Claim find least on owner.\nThrough space contain series understand off rise. Coach suffer someone look tonight next. Hot crime beautiful million.',
    'email': 'tberg@example.org',
    'phone_number': '589.643.5188x45708',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Soto',
    'Mitchell George',
    'Michael Dalton',
    'April Guerrero',
    'David Stuart',
    'Lori Browning',
    'James Warren',
],
    'json': {
    'name': 'Evelyn Chapman',
    'address': 'Unit 5206 Box 3485\nDPO AP 38969',
},
    'key78208': 'value59934',
    'key11935': 'value73367',
    'key84561': 'value50033',
    'key10705': 'value76683',
    'key95634': 'value48609',
    'key30216': 'value63630',
    'key11762': 'value12210',
    'key86960': 'value68207',
    'key95182': 'value74633',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Martha Compton',
    'address': '7512 Kathryn Cliff\nWest Randallland, NE 31798',
    'text': 'Single quite task Congress. Statement fact look PM agree rest method leg. Test base draw face.',
    'email': 'riverajustin@example.com',
    'phone_number': '478-736-8221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Smith',
    'Jennifer Sexton',
    'Mario Anderson',
    'Erin Smith',
    'Amy Boone',
    'Michelle Gallagher',
    'Carol Robinson',
    'Adam Salazar',
    'Jack Miller',
    'Danielle Flowers',
],
    'json': {
    'name': 'Rachel Rose',
    'address': '2013 Brooks River Suite 397\nEast Kirkborough, NM 27817',
},
    'key50977': 'value40394',
    'key43129': 'value31165',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Andrew Carter',
    'address': '62813 Jillian Motorway Apt. 236\nNorth John, OK 84783',
    'text': 'Class safe return they speak national myself best. Available discover not her image admit affect surface. Service decide nature room true.\nInstitution significant speech TV our compare.',
    'email': 'aaronanderson@example.com',
    'phone_number': '(658)534-8534x8143',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Shaw',
    'Lorraine Gibbs',
],
    'json': {
    'name': 'Miss Karen Livingston',
    'address': '7536 Massey Divide\nPort Peterport, WY 07798',
},
    'key76494': 'value19071',
    'key66763': 'value61387',
    'key89184': 'value93144',
    'key74334': 'value70051',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Roger Sharp',
    'address': '0424 Carr Manors\nCollinstown, DC 72683',
    'text': 'Trouble however quality wind. Expect position minute interesting. Thing risk put cup.\nSmall recent good majority game machine reflect fund. Point any despite still could.',
    'email': 'shawn45@example.net',
    'phone_number': '784.869.7315',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mary Franco',
    'Joseph Reed',
    'Jennifer Herrera',
    'Jason Cannon',
    'Robert King',
],
    'json': {
    'name': 'Kristen Johnson',
    'address': '35677 Williams Branch Apt. 702\nLake Chasetown, MP 56498',
},
    'key27392': 'value58644',
    'key74882': 'value96621',
    'key21942': 'value41196',
    'key59430': 'value21873',
    'key27844': 'value8824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'John Phillips',
    'address': 'Unit 9100 Box 4505\nDPO AP 82467',
    'text': 'Moment quite up important fight off guess. Officer team rule interview. Trip six benefit trial cold purpose him.\nStore prepare rest network. Section dark wonder share.',
    'email': 'william52@example.net',
    'phone_number': '001-555-598-6068',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Mcbride',
    'Michael Bennett',
    'Jennifer Davies',
    'April Harris',
    'Gary James',
    'Jacob Graham',
    'Duane Sutton',
    'Thomas Thompson',
    'Ryan Bond',
],
    'json': {
    'name': 'Susan Beck',
    'address': '0890 Mccoy Grove\nShortshire, NC 46641',
},
    'key50505': 'value90351',
    'key17292': 'value80988',
    'key92313': 'value19563',
    'key81656': 'value18651',
    'key76837': 'value72653',
    'key5020': 'value25770',
    'key92446': 'value19922',
    'key12133': 'value72640',
    'key38300': 'value39114',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Mariah Evans',
    'address': '7188 Wright Forest\nWardberg, IL 02162',
    'text': 'Into address three student treatment career. Medical able pressure.\nSecurity to build.\nPressure during keep medical top assume front. Expect field sound store movie.',
    'email': 'virginia17@example.net',
    'phone_number': '(896)424-1944',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Austin',
    'Samuel Page MD',
    'Samantha Acevedo',
],
    'json': {
    'name': 'Troy Franklin',
    'address': '89103 Mccullough Mountains\nEast Wendyburgh, IL 45027',
},
    'key33774': 'value57215',
    'key34448': 'value96351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Nicholas King',
    'address': '74219 Diaz Extension\nNorth Phyllistown, PR 35441',
    'text': 'Best want everything north. Learn test guess forget compare onto. Your minute democratic decision.\nOur surface without decide. Budget evidence right wish. Lawyer seek behavior cultural issue.',
    'email': 'spowers@example.org',
    'phone_number': '+1-615-867-7660x45244',
    'array_int_dynamic': [
    83698,
],
    'array_varchar_dynamic': [
    'Angela Allen',
    'Molly Johnson DDS',
    'Patrick Cooper',
    'Kenneth Miller',
    'David Garcia',
    'Jennifer Parker',
    'Tamara Fitzgerald',
],
    'json': {
    'name': 'Pamela Duffy',
    'address': '1908 James Mill Suite 921\nHillfort, AL 62859',
},
    'key1200': 'value27085',
    'key95964': 'value12446',
    'key14564': 'value23193',
    'key7737': 'value6516',
    'key56806': 'value73405',
    'key13694': 'value6804',
    'key69340': 'value25245',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Caitlyn Martin',
    'address': '89719 Diana Ford Suite 200\nLake Megan, AS 88956',
    'text': 'Form write maybe those rather more civil leave. Somebody could shoulder big join become later. Area report fund part case be small according.',
    'email': 'uyoung@example.org',
    'phone_number': '951-604-6216',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Richardson',
    'Mark Liu',
    'Jessica Wilson',
    'Nicole Steele',
    'Andrea Horton',
    'Michael Johnson',
    'Pamela Nash',
    'Willie Romero',
],
    'json': {
    'name': 'Anthony James',
    'address': '2604 Gonzalez Prairie\nEast Kayleeberg, MS 16538',
},
    'key78012': 'value11271',
    'key82357': 'value95682',
    'key27606': 'value69520',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Katie Trevino',
    'address': '683 John Brooks\nKingchester, MN 16021',
    'text': 'Your such special be human family particular. Everything movie training north financial movement professional. Wrong anyone provide.',
    'email': 'wgreene@example.org',
    'phone_number': '+1-385-566-9243x826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Sullivan',
    'Jennifer Cox',
    'Terry Alexander',
],
    'json': {
    'name': 'Madeline Hahn',
    'address': '46918 Barbara Groves Suite 961\nRodrigueztown, IL 70478',
},
    'key87117': 'value36434',
    'key6217': 'value22676',
    'key25050': 'value2316',
    'key86678': 'value11211',
    'key75440': 'value27286',
    'key38319': 'value59094',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Kathy Lee',
    'address': '5265 Benjamin Glens Apt. 336\nPort Angelatown, NV 38936',
    'text': 'Letter contain defense indicate. Miss cut ability cell fear choice.\nNews late report above will figure. Condition know claim side clearly respond and.',
    'email': 'michaelstout@example.net',
    'phone_number': '957-219-7792x8862',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Archer',
    'Tammy Thomas',
    'Katherine Ramirez',
    'Alejandra Smith',
    'Dale Sawyer',
    'Carol Smith',
    'Megan Caldwell',
],
    'json': {
    'name': 'Emma Hays',
    'address': 'Unit 1675 Box 3923\nDPO AP 73420',
},
    'key37572': 'value66382',
    'key12836': 'value28122',
    'key52068': 'value92749',
    'key24380': 'value964',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Taylor Brooks',
    'address': '139 Allen Port\nWest Josephtown, DC 25966',
    'text': 'Win through particular resource eight week left. Somebody return land trouble energy free.\nItself another church change thought. Student specific consumer serve star carry your.',
    'email': 'andrewgreen@example.com',
    'phone_number': '001-510-266-2728x588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amber Valencia',
    'Tammy Pugh',
    'Robert Kelley',
    'Allen Thompson',
    'Patricia Ellis',
    'Shawna Jackson',
    'Shannon Turner',
    'Holly Martinez',
    'Adrian Day',
],
    'json': {
    'name': 'Joel Williams',
    'address': '028 Warren Course Apt. 535\nLake Mercedes, HI 22206',
},
    'key44266': 'value38809',
    'key25271': 'value3286',
    'key37761': 'value55827',
    'key91798': 'value45099',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Rebecca Bradley',
    'address': '19285 Patrick Lodge\nPort Ericafurt, FM 07571',
    'text': 'Bag from far article step debate spring. Training support certain heavy.\nSea special newspaper tough wish finish.',
    'email': 'eduardothompson@example.org',
    'phone_number': '001-918-644-8709x44954',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Austin Fleming',
    'Donna West',
    'Daisy Sloan',
    'Sandra Stephens',
    'Kim Herrera',
    'Harold Nolan',
    'William Brown',
],
    'json': {
    'name': 'Christian Bond',
    'address': '0031 Blackwell Cliffs\nNorth Nicole, AS 78871',
},
    'key94983': 'value70304',
    'key6891': 'value90273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Edward Prince',
    'address': '9346 Hernandez Garden\nRichardmouth, OH 60946',
    'text': 'Do statement keep war. Job member politics.\nYard if network listen. Employee choose career far identify space. Station place bank step.',
    'email': 'mchen@example.net',
    'phone_number': '+1-629-714-7581x906',
    'array_int_dynamic': [
    12790,
],
    'array_varchar_dynamic': [
    'Dominique Martin',
    'Claudia Davis',
    'Mary Erickson',
],
    'json': {
    'name': 'Stephanie Galloway',
    'address': '35413 Kristin Meadow\nSouth Randyside, MN 58643',
},
    'key51102': 'value56468',
    'key19962': 'value92731',
    'key60078': 'value53434',
    'key43570': 'value68570',
    'key85634': 'value72442',
    'key73253': 'value33901',
    'key43166': 'value44449',
    'key59490': 'value9608',
    'key81515': 'value64520',
    'key47721': 'value83586',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Kimberly Hughes',
    'address': '099 David Parkway\nPort Brandon, OR 94196',
    'text': 'Detail ready result reality clear behavior information. Create nice idea remember ready type. Send north recognize stage economy if anyone.\nVisit maybe staff since no. Ball draw green explain admit.',
    'email': 'cjames@example.com',
    'phone_number': '(954)394-3066',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Dunn',
    'Daniel Smith',
    'Ruben Gomez',
    'Scott Adams',
    'Michael Cruz',
],
    'json': {
    'name': 'Tiffany Schultz',
    'address': '635 James Camp\nWest Patty, NY 42276',
},
    'key92550': 'value24908',
    'key90499': 'value32123',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Erica Barry',
    'address': '30884 Reid Springs Suite 078\nEast Nicole, MA 18164',
    'text': 'Necessary star structure audience stop product month. Need have second step option color.\nIssue respond middle tonight. Level trial can deal set. Behavior management you.',
    'email': 'samuelkelley@example.com',
    'phone_number': '890.239.5690x800',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jenny Long',
    'Joshua Black',
    'Craig Taylor',
    'Jason Johnson DVM',
    'Tracy Mcdonald',
    'Nancy Phillips',
    'Sabrina White',
    'Adam Tyler',
],
    'json': {
    'name': 'Daniel Johnson',
    'address': '38440 White Burg Apt. 906\nSouth Anthonyside, IN 56884',
},
    'key77868': 'value1974',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Mrs. Donna Perez',
    'address': '771 Manuel Village Apt. 587\nLake Micheleport, MA 35569',
    'text': 'Rest class dream research. Book environmental culture bad upon same picture generation. There create speech floor.\nThreat eye recent court eye wife. Choice hold technology subject identify.',
    'email': 'joseph07@example.net',
    'phone_number': '476.874.9899x295',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Bell',
    'Travis Johnson MD',
    'Crystal Acevedo',
    'Charles Baker',
    'James Smith',
    'Jennifer Salinas',
],
    'json': {
    'name': 'Brandon Gilbert',
    'address': '6524 Kelly Plaza\nAndrewview, VT 73125',
},
    'key91588': 'value72605',
    'key68687': 'value92500',
    'key6805': 'value5645',
    'key80950': 'value58397',
    'key31986': 'value75945',
    'key46394': 'value38392',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Trevor Rose',
    'address': '2456 Alexander Via\nSouth Robert, IA 06513',
    'text': 'Create fine minute fear institution shake past. Skill sign maybe game.\nProbably weight today outside actually enter watch. Agent partner however.',
    'email': 'courtneykelley@example.com',
    'phone_number': '890.220.0846',
    'array_int_dynamic': [
    6702,
],
    'array_varchar_dynamic': [
    'Miranda Hart',
    'Cindy Burns',
    'Wendy Peterson',
    'Kenneth Gonzalez',
    'Bonnie Snow',
    'Brandon Nicholson',
    'Jacob Combs',
    'Charles Clayton',
],
    'json': {
    'name': 'Michael Perez',
    'address': '363 Charles Walk Suite 056\nRossfort, IA 94902',
},
    'key162': 'value55940',
    'key47755': 'value38455',
    'key71238': 'value92306',
    'key41719': 'value34696',
    'key98816': 'value30283',
    'key76919': 'value30096',
    'key47477': 'value70580',
    'key15468': 'value30464',
    'key76247': 'value54398',
    'key2854': 'value71697',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Edward Ramos',
    'address': '181 Sydney Park\nMichaeltown, PR 07728',
    'text': 'Spring family heart particular. War garden part case successful may.\nGrowth game thousand rather support drug. Build wind item wall modern work price care.',
    'email': 'aliciahayes@example.net',
    'phone_number': '001-803-883-0072x653',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Maria Lee',
    'Chelsea Duarte',
    'Justin Brown',
    'Matthew James',
    'Raymond Rodriguez',
    'Samuel Rollins',
    'Tina Boyer',
    'Heather Joyce',
    'Jamie Lawrence',
    'Sarah Reyes',
],
    'json': {
    'name': 'Robert Johnson',
    'address': '39298 Ortiz Falls\nLoriport, NY 77617',
},
    'key13901': 'value65446',
    'key66404': 'value25763',
    'key84900': 'value20661',
    'key53032': 'value18700',
    'key10667': 'value55131',
    'key88978': 'value66502',
    'key52776': 'value34377',
    'key99739': 'value32592',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Rachel Clark',
    'address': '656 Watson Springs\nEmilystad, TX 98864',
    'text': 'Individual true require statement effect open say. Teacher travel detail in only.\nSchool rather himself tend TV same. Long will tax.',
    'email': 'igross@example.net',
    'phone_number': '202.729.9040x479',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Murphy',
],
    'json': {
    'name': 'Alexander Sutton DDS',
    'address': '2674 Harrell Forges Suite 586\nWilliamsberg, RI 81605',
},
    'key378': 'value89165',
    'key14864': 'value76902',
    'key13621': 'value23130',
    'key86003': 'value76857',
    'key956': 'value42652',
    'key87739': 'value21026',
    'key82873': 'value46584',
    'key1538': 'value87895',
    'key40673': 'value8451',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Brittany Villarreal',
    'address': '870 Harvey Cape\nNorth Michael, KS 69949',
    'text': 'Author positive leave place bill total agent. Lead beat turn. Never among language president establish simply.\nLoss daughter western. Price example central save. Seem off cup picture charge.',
    'email': 'hudsonsarah@example.net',
    'phone_number': '+1-927-905-4785x4866',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Winters',
],
    'json': {
    'name': 'Melissa Evans',
    'address': '8454 Robert Unions Suite 767\nWest Kimberg, FM 66453',
},
    'key19063': 'value21288',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Joy Diaz',
    'address': '470 Stacy Point Apt. 634\nAnthonymouth, DE 22498',
    'text': 'Study pay career far article a.\nResult analysis international agree director research thought. Fly respond trouble hair. Woman over front writer fund almost central.',
    'email': 'vhenry@example.net',
    'phone_number': '738-726-0969x866',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Cruz',
    'Tammy Taylor DDS',
    'Lori Oneal',
    'Patrick Valenzuela',
    'Maria Rodriguez',
],
    'json': {
    'name': 'Darrell Eaton',
    'address': '2594 Smith Junction Apt. 163\nLauriestad, AR 10835',
},
    'key10966': 'value3428',
    'key64128': 'value50308',
    'key17442': 'value78745',
    'key8373': 'value50593',
    'key83765': 'value72658',
    'key23794': 'value61131',
    'key37604': 'value65357',
    'key45190': 'value3276',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Mary Gonzales',
    'address': '665 Diane Crossing\nAmandaburgh, TX 56696',
    'text': 'Treat produce develop score ahead. Two among purpose civil story seat. Inside subject staff year event vote serve.',
    'email': 'debragomez@example.net',
    'phone_number': '001-378-994-8058x825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Haley Stephens',
],
    'json': {
    'name': 'Mark Smith DDS',
    'address': '46470 Tonya Ridges\nNorth Tyler, OK 30618',
},
    'key24115': 'value12019',
    'key80550': 'value10166',
    'key80960': 'value54903',
    'key30900': 'value54449',
    'key10767': 'value75211',
    'key47042': 'value86873',
    'key56448': 'value95258',
    'key98733': 'value19047',
    'key46983': 'value15770',
    'key50259': 'value78221',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Karen Frye',
    'address': '1934 Lucero Wells Apt. 610\nNorth Deborahland, OR 08465',
    'text': 'Other fall memory radio. Able while four.\nProcess possible into official positive.\nCharge mouth same option second social grow doctor. Model bill available human.',
    'email': 'watsonjeffrey@example.com',
    'phone_number': '9788271272',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Taylor',
    'Danny Alvarez',
    'Devin Marshall',
],
    'json': {
    'name': 'Gary Rodriguez',
    'address': '625 Julie Roads Suite 221\nSouth William, FL 33686',
},
    'key99184': 'value43478',
    'key72415': 'value41630',
    'key48873': 'value12928',
    'key94689': 'value70638',
    'key96606': 'value49953',
    'key21611': 'value65139',
    'key14706': 'value88573',
    'key19739': 'value7070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Sean Gutierrez',
    'address': '047 Jose Passage\nErikahaven, NE 78028',
    'text': 'Will possible cold anything contain put. Amount leg traditional people person.\nMagazine American interest matter girl beyond. Officer team wear far simple start product provide.',
    'email': 'bryceperez@example.net',
    'phone_number': '(818)944-3528x84855',
    'array_int_dynamic': [
    83078,
],
    'array_varchar_dynamic': [
    'Dawn Matthews',
    'Stephanie Waters',
    'Andrew Robinson',
],
    'json': {
    'name': 'Michael Wang',
    'address': '76108 Richard Mission Apt. 496\nBrettburgh, VT 00938',
},
    'key38796': 'value81173',
    'key5236': 'value34209',
    'key38190': 'value42006',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Monica Palmer',
    'address': '0632 Randall Hill Apt. 338\nWest Timothyborough, PA 96800',
    'text': 'Natural forward say. Prevent responsibility avoid before help. Quickly call mean hospital society live.',
    'email': 'colleen24@example.net',
    'phone_number': '854-507-8331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Julie Logan',
    'Amber Santos',
    'Tammy Butler',
    'Gregory Ross',
    'Kevin Griffin',
    'Michelle Bennett',
    'Kevin Waters',
    'William Fuller',
    'Gregory Morris',
],
    'json': {
    'name': 'Gary Harmon',
    'address': '114 Susan Canyon Suite 480\nPowellview, SD 61425',
},
    'key94059': 'value33174',
    'key89714': 'value85443',
    'key65017': 'value24197',
    'key27110': 'value10131',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Joseph Clark',
    'address': '362 Delgado Plains Suite 150\nYoungstad, PR 47167',
    'text': 'Charge century try face heart imagine. Special charge report provide.\nRemember section group feel community gun history. Woman science push so structure state.',
    'email': 'henryschneider@example.com',
    'phone_number': '804-806-2854x0069',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Misty Thomas',
    'Deborah Hoover',
    'Veronica Jarvis',
    'Jesse Ramirez',
    'Michelle Roberts',
    'Holly Hughes',
],
    'json': {
    'name': 'Norma Griffin',
    'address': '7473 Kristi Plaza\nSerranoview, IA 78634',
},
    'key8839': 'value97893',
    'key52284': 'value24069',
    'key14314': 'value44412',
    'key30833': 'value70951',
    'key49012': 'value46727',
    'key48811': 'value43244',
    'key69228': 'value4505',
    'key45626': 'value68995',
    'key70887': 'value43804',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Michele Hunt',
    'address': '4604 King Manor Apt. 662\nNew Dylanview, UT 65470',
    'text': 'Arrive lead bed risk ever try buy. Receive bed scientist conference. Part party body business budget organization.',
    'email': 'pmoore@example.com',
    'phone_number': '001-864-522-2071x65285',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Justin Young',
    'Tracy Marsh',
    'Haley Holden',
],
    'json': {
    'name': 'Bonnie Hill',
    'address': '58875 Chris Summit\nNorth Danielmouth, MH 59856',
},
    'key46527': 'value94268',
    'key34277': 'value43995',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Tracy Smith',
    'address': '681 Arnold Pines\nNorth Tyler, MO 58358',
    'text': 'Draw court director. Rise easy employee dinner stuff medical type contain.\nForward within however. Employee with third career natural into should.',
    'email': 'catherine40@example.org',
    'phone_number': '713.894.7059',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Washington',
    'Ronald Weaver',
    'Jenna Miller',
    'Karen Patrick',
],
    'json': {
    'name': 'Amanda Shepherd',
    'address': '8364 Theresa Lodge\nAnthonybury, RI 62450',
},
    'key73913': 'value62219',
    'key76408': 'value8963',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Michael Garner Jr.',
    'address': '1640 Samantha Pines\nJohnfort, GU 35165',
    'text': 'Lead stop example radio. Our various camera mean magazine. Worry material design just challenge eight.\nAlready decision food reveal more certain. Quickly simply serious.',
    'email': 'mark14@example.com',
    'phone_number': '607.295.5607',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Savannah Dixon',
    'Heather Sullivan',
    'Michelle Green',
    'James Alexander',
    'Mark Oconnor',
    'Katherine Wagner',
    'Kristen Smith',
    'Connor Stout',
    'Amy Howard',
    'Jeffery Evans',
],
    'json': {
    'name': 'Ethan Park',
    'address': '14705 Sullivan Terrace Apt. 224\nRandolphtown, NV 88043',
},
    'key3222': 'value27261',
    'key67434': 'value64871',
    'key67518': 'value76037',
    'key10073': 'value75856',
    'key34644': 'value30699',
    'key98863': 'value5304',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Diana Welch',
    'address': '903 Lisa Fork Apt. 101\nRodneymouth, TX 22276',
    'text': 'Environment ground election. Away will also truth.\nView environment seek health create. Police training north president. Save cut station example article.',
    'email': 'william30@example.com',
    'phone_number': '(941)580-6734x314',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Todd Torres',
    'Christopher Ferguson',
    'Edward Myers',
],
    'json': {
    'name': 'William Hunt',
    'address': '49190 Ortega Garden Apt. 370\nMckenzietown, NH 79796',
},
    'key75928': 'value50316',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Denise Curry',
    'address': '9956 Desiree Via\nBarbarabury, DC 07661',
    'text': 'Attorney trade international difficult life million seat. Floor great record.\nMyself simply morning run car politics when management.',
    'email': 'patrick81@example.org',
    'phone_number': '(522)201-1789x705',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Chelsea Wood',
    'Dennis Rowland',
    'Andrew Brown',
    'Dana Morales',
],
    'json': {
    'name': 'Seth Murphy',
    'address': '62076 Mathis Creek\nTerrenceside, PR 75125',
},
    'key79728': 'value43888',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Caroline Ramirez',
    'address': '7825 Debra Courts\nEast Susan, PA 60396',
    'text': 'Movie third way officer generation indicate.\nPrice time heavy. Cause beyond even through daughter camera have.',
    'email': 'michaeljohnson@example.com',
    'phone_number': '+1-830-341-2399x751',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Sanchez',
    'Gabriel Nicholson',
    'Erin Hale',
    'Cheryl Turner',
    'Andrew Logan',
    'Kimberly Phelps',
    'Rebecca Ryan',
    'Marcus Gordon',
],
    'json': {
    'name': 'Matthew Mitchell',
    'address': '437 Ashley Plaza\nChristinamouth, NM 21748',
},
    'key37914': 'value58865',
    'key21794': 'value17021',
    'key92244': 'value98055',
    'key86981': 'value46942',
    'key69450': 'value45889',
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
    'RequestId': '72ff3aa0-62ef-11f0-9024-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_40_451894EWdgSjxW',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-100-2]_1752744101.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId3210021752744101Json()
    test.run_tests()
