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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-1]_1752744146_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-1]_1752744146.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl3210011752744146Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-1]_1752744146.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-1]_1752744146.json"
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
    'RequestId': '8da395ec-62ef-11f0-b071-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_25_149801wqanANtO',
    'dimension': 32,
    'primaryField': 'url',
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
    'RequestId': '8dce2dc5-62ef-11f0-a3e6-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_25_149801wqanANtO',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Margaret White',
    'address': '201 Nicole Parks Apt. 847\nLucasfort, NJ 86051',
    'text': 'Red put cause age audience professor. Scene budget against life. Everything class world girl site data perform.',
    'email': 'kimberlyrivera@example.org',
    'phone_number': '001-380-853-7750x1478',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Gomez',
    'Julie Alvarado',
    'Stephen Green',
    'Cameron Alvarez',
    'Ethan Odonnell',
    'Mitchell Rivers',
],
    'json': {
    'name': 'Donald Adams',
    'address': '164 Jones Heights Suite 741\nLake Louisstad, WY 75366',
},
    'key65619': 'value93239',
    'key9430': 'value15428',
    'key37673': 'value55174',
    'key57288': 'value21528',
    'key76204': 'value49479',
    'key42738': 'value8104',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Johnny Jones',
    'address': '9532 Nancy Vista\nConnorburgh, AZ 50143',
    'text': 'Different it first radio what type there. Really kitchen sign generation. Recent your represent property institution. Yes Democrat window ten trade.',
    'email': 'sharifuentes@example.com',
    'phone_number': '+1-225-744-0302x068',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'William Stout',
    'Charles Moreno',
    'Glenda Valdez',
    'Mr. Billy Hill',
    'Mary Patterson',
    'Gabrielle Lewis',
    'Tonya Flores',
    'Brian Petty',
],
    'json': {
    'name': 'Charles Chen',
    'address': '4982 Flores Summit Apt. 750\nKaylaburgh, WY 89270',
},
    'key7300': 'value61047',
    'key81323': 'value29332',
    'key964': 'value78522',
    'key8469': 'value5047',
    'key16814': 'value64780',
    'key63478': 'value89813',
    'key28517': 'value97025',
    'key80527': 'value31792',
    'key62178': 'value26783',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Thomas Moore',
    'address': '27415 Samantha Plaza Suite 722\nCruzbury, ME 72405',
    'text': 'Act dinner best.\nPlay every accept newspaper cold product recent. Recently same start responsibility wish boy present. Old truth off company.',
    'email': 'jonesronnie@example.com',
    'phone_number': '(253)809-9290',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brenda Martin',
    'Tyler Burke PhD',
    'Jonathan Hardin',
    'Patrick Rice',
    'Lindsay Castillo',
    'Gary Greene',
],
    'json': {
    'name': 'Elizabeth Wright',
    'address': '775 Mark Wells\nBrewerbury, LA 50784',
},
    'key4002': 'value33831',
    'key7398': 'value64925',
    'key23839': 'value64608',
    'key42842': 'value15348',
    'key87085': 'value6380',
    'key94853': 'value5765',
    'key1969': 'value41181',
    'key96437': 'value20396',
    'key50625': 'value73671',
    'key15575': 'value61326',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Kenneth Boone',
    'address': '01660 Sutton Prairie Apt. 857\nSparksfurt, MD 99198',
    'text': 'Whose natural late behind natural main side. Truth decision something size.\nSeveral reflect instead professional art report wish. Eye would clear than. Pm want design have since.',
    'email': 'kristopher22@example.com',
    'phone_number': '533.221.0496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Eric Caldwell',
    'Douglas Rice',
    'Kim Hart',
],
    'json': {
    'name': 'Brandon Davis',
    'address': '260 Monroe Flats Apt. 431\nChristianmouth, VA 11449',
},
    'key69316': 'value94667',
    'key38434': 'value26377',
    'key66472': 'value27213',
    'key36274': 'value96948',
    'key76085': 'value78934',
    'key87430': 'value54368',
    'key10287': 'value95449',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Christina Morris',
    'address': '17695 Tammie Rue\nNorth David, PW 79043',
    'text': 'Practice role this. Though than tree child huge market concern.',
    'email': 'emendoza@example.org',
    'phone_number': '(962)556-0778x989',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Susan Smith',
    'Steven Mccoy',
    'Sergio Pierce PhD',
    'Steven Carr',
    'Janice Chang',
    'Robert Lucas',
    'Grace Jones',
    'Daniel King',
    'Angela Leon',
],
    'json': {
    'name': 'Carrie Castaneda',
    'address': '21588 Cameron Cove Suite 108\nCameronmouth, OK 67592',
},
    'key88057': 'value98714',
    'key10578': 'value78952',
    'key81676': 'value9383',
    'key98755': 'value23954',
    'key42930': 'value83530',
    'key13077': 'value64258',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Adam Griffin',
    'address': 'Unit 3842 Box 0260\nDPO AA 16683',
    'text': 'Another perform do hand. Avoid technology they over white. Page well build thing street guess. Building television rest reality three tough.',
    'email': 'thomaskristina@example.net',
    'phone_number': '+1-706-717-7635',
    'array_int_dynamic': [
    6353,
],
    'array_varchar_dynamic': [
    'Justin Baldwin',
    'Jessica Johnson',
    'Jason Foster',
    'Kathy Castaneda',
    'Jordan Jordan',
    'Nicholas Hester',
    'Lauren Parker',
],
    'json': {
    'name': 'Lee Bryant',
    'address': '201 Smith Corners Apt. 012\nSouth Ethanbury, HI 43834',
},
    'key79662': 'value90526',
    'key15663': 'value27001',
    'key94358': 'value34561',
    'key11969': 'value48278',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'David Jackson',
    'address': '982 Joe Cliff\nNorth Diana, AS 70152',
    'text': 'Glass summer effort happy cut add threat begin. Author voice population drug coach action source.\nChild consumer what before price despite number. Somebody care truth return.',
    'email': 'jasonward@example.com',
    'phone_number': '868.737.9885x141',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Price',
    'John Booth',
    'Jamie Martin',
    'Miss Melissa Wyatt PhD',
    'Michael Wallace',
    'Tammy Hayes',
    'Teresa Leon',
],
    'json': {
    'name': 'Blake Salinas',
    'address': '489 Hanson Hollow\nLake Mary, AZ 39926',
},
    'key56217': 'value84721',
    'key99295': 'value74135',
    'key3766': 'value61091',
    'key12631': 'value23346',
    'key85118': 'value81910',
    'key57830': 'value44415',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Melissa Anderson',
    'address': '89742 Hamilton Street Apt. 351\nSouth Emily, MT 81653',
    'text': 'Section return better drug beyond hotel. Particularly ready skill without.\nScience college analysis enough series while medical.',
    'email': 'alexanderjennifer@example.com',
    'phone_number': '001-292-939-3275x6624',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lindsey Bailey',
    'Eric Powell',
    'Michael Jones',
    'Patricia Johns',
],
    'json': {
    'name': 'Nathan Hansen',
    'address': '424 Kelly Village\nSamuelstad, VT 82259',
},
    'key4655': 'value87432',
    'key10954': 'value78048',
    'key69721': 'value53751',
    'key240': 'value48837',
    'key97069': 'value32745',
    'key12175': 'value81341',
    'key86761': 'value34364',
    'key73947': 'value86163',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Raymond Evans',
    'address': '2156 Samantha Union\nLake Vanessa, AZ 26914',
    'text': 'Something standard agreement traditional note international moment. Evening help performance do anyone will thousand trouble.\nMethod evidence across economy. Southern agency ball animal.',
    'email': 'bcarter@example.com',
    'phone_number': '563.442.7717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Yates',
    'Michael Grimes',
    'Barbara Garza',
    'Tanya Powers',
    'Nathaniel Shepherd',
    'Christina Sims',
    'Donna Flowers',
    'Kathleen Peterson',
    'Jose Rivera',
],
    'json': {
    'name': 'Shawn Burgess',
    'address': '1298 Johnny Expressway Suite 652\nSouth Taylortown, ME 52470',
},
    'key71984': 'value36754',
    'key86409': 'value40298',
    'key30685': 'value55173',
    'key40970': 'value11158',
    'key59635': 'value11003',
    'key83878': 'value76324',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Jessica Flores',
    'address': '097 Warren Viaduct Apt. 155\nHeatherstad, CO 13506',
    'text': 'Anyone parent coach person data maintain analysis. Support task though chair.',
    'email': 'jamescrane@example.com',
    'phone_number': '+1-383-973-3678x659',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Troy Adams',
],
    'json': {
    'name': 'Vicki Butler',
    'address': '82783 Erik Haven\nAnnafurt, MH 36838',
},
    'key79521': 'value51592',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Roger Haynes',
    'address': '6775 Jennifer Ridges Suite 388\nJohnsonville, LA 17008',
    'text': 'Take economy purpose. Risk simply book fall plant. Bad send treatment impact. Chair service hand today traditional traditional firm treat.',
    'email': 'maria50@example.com',
    'phone_number': '298-311-8603x482',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amy Young',
    'Carrie King',
    'Anna Burton',
    'Connor Jackson',
    'Jean Ingram',
    'Kristi Pollard',
],
    'json': {
    'name': 'Zachary Hawkins',
    'address': '163 Edwards Center\nJohnstonfort, MD 43355',
},
    'key10468': 'value82724',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'William Graves',
    'address': 'USS Kaiser\nFPO AE 67492',
    'text': 'Current energy government teacher. Democratic service technology. Cup game discussion politics.',
    'email': 'april54@example.org',
    'phone_number': '321.374.6731',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sheri Shaw',
    'Jacqueline Harris',
    'Matthew Saunders',
    'Debra Flynn',
    'James King MD',
    'Brittany Russell',
    'Erin Evans',
],
    'json': {
    'name': 'David Strickland',
    'address': '073 Carrie Shoals Apt. 973\nJacksonfort, MA 69692',
},
    'key73674': 'value32179',
    'key84008': 'value69506',
    'key5142': 'value46573',
    'key477': 'value33658',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Robin Blair',
    'address': '431 Thomas Extension Suite 996\nLake Kristenborough, SD 09345',
    'text': 'Number contain structure learn American. Foreign many experience and movie impact.',
    'email': 'millerrichard@example.net',
    'phone_number': '+1-568-387-7609x716',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brian Turner',
    'Kenneth Holmes',
    'Bonnie Gilbert',
    'Christopher Blake',
],
    'json': {
    'name': 'Kayla Hahn',
    'address': '534 Hernandez Turnpike Suite 768\nSierraport, OR 73576',
},
    'key40729': 'value54998',
    'key24112': 'value51382',
    'key26989': 'value14101',
    'key35273': 'value47541',
    'key43281': 'value68939',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Douglas Hall',
    'address': '0978 Cooper Field\nEast William, IL 94704',
    'text': 'Share knowledge seek specific condition. Sing man simple instead doctor third.',
    'email': 'ryan33@example.net',
    'phone_number': '976-601-3376x8572',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Henry',
    'James Winters',
],
    'json': {
    'name': 'Troy Moore',
    'address': '307 Friedman Ways Suite 984\nJamiemouth, IN 02617',
},
    'key93490': 'value77475',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Jerry Miller',
    'address': '9294 Thomas Avenue Suite 861\nMurphyton, PA 69422',
    'text': 'Respond image man take ground. Throughout technology worker. Policy Mr economy crime. Law pass option test man party realize.',
    'email': 'david32@example.net',
    'phone_number': '+1-282-844-8673x510',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'George Mann',
    'Brooke Taylor',
],
    'json': {
    'name': 'Brittany Palmer',
    'address': '2267 Elizabeth Trail\nWhitneyfort, NH 77098',
},
    'key1669': 'value5116',
    'key85796': 'value78689',
    'key30436': 'value6424',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Matthew Fuller',
    'address': '06438 Rocha Haven\nSarahaven, AZ 19430',
    'text': 'Stock customer sister who appear if. Feel measure clearly general.\nSkin pay audience. Seem today natural friend force. Perform miss gas person type office there rich.',
    'email': 'jeffrey19@example.org',
    'phone_number': '(611)974-2036x45246',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Eileen Austin',
    'Patty Williams',
    'William Scott',
],
    'json': {
    'name': 'Crystal Hendricks',
    'address': 'USS Hancock\nFPO AP 78789',
},
    'key92432': 'value42140',
    'key92564': 'value5855',
    'key83675': 'value92351',
    'key72211': 'value40693',
    'key59960': 'value42260',
    'key91600': 'value10293',
    'key67998': 'value30014',
    'key51307': 'value44402',
    'key40545': 'value71977',
    'key13378': 'value62196',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Victoria Sanchez',
    'address': 'USCGC Herrera\nFPO AE 09029',
    'text': 'South find beat receive fund. Air this street reason lot future another more. Sign different long store receive interest. Rock car power walk others hear.',
    'email': 'jzhang@example.net',
    'phone_number': '237.932.6736x521',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Nichole Bell',
],
    'json': {
    'name': 'Robert Wagner MD',
    'address': '5613 Trevor Pass\nLake Bettyhaven, DC 60082',
},
    'key83070': 'value31188',
    'key99264': 'value8477',
    'key22005': 'value43286',
    'key35172': 'value34171',
    'key26708': 'value18177',
    'key51323': 'value40052',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Austin Fry',
    'address': 'USNV Jones\nFPO AA 85487',
    'text': 'Be player light. Friend half happy fire.\nReach live prevent assume house east edge clearly. Sea important information talk a.',
    'email': 'bethhinton@example.com',
    'phone_number': '(288)524-8276x459',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Ferguson',
    'Kayla Bryant',
    'Alexander Hanson',
    'Elizabeth Irwin',
    'John Morgan',
    'Taylor Duncan',
    'Vincent Garza',
],
    'json': {
    'name': 'Leonard Warner',
    'address': '447 Brandon Forge\nEast Karen, FL 46556',
},
    'key50734': 'value78367',
    'key86884': 'value35679',
    'key76910': 'value19498',
    'key72759': 'value89488',
    'key6718': 'value59045',
    'key50840': 'value22511',
    'key38996': 'value37257',
    'key79421': 'value46684',
    'key18078': 'value59339',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Michael Cooper',
    'address': '75703 Melissa Bridge\nPort Randall, FL 02201',
    'text': 'Investment market career company imagine religious bill. Account key arm.',
    'email': 'kristen20@example.org',
    'phone_number': '(920)469-3033x9759',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Terri Jimenez',
    'Tiffany Burns',
    'Laura Blair',
    'Nicholas Boyd',
    'Anna Johnson',
    'Sarah Olson',
    'Jason Greer',
    'Marilyn Miller',
],
    'json': {
    'name': 'Shawn Delacruz',
    'address': '3335 Aaron Shoals\nWest Nancy, AZ 47584',
},
    'key9435': 'value68188',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Regina Butler',
    'address': 'Unit 6384 Box 1444\nDPO AA 83096',
    'text': 'Half stop billion right. Guess chair realize these represent. Eye up party space.\nCommercial nature white century none interesting. Never run young friend forget improve.',
    'email': 'smithlisa@example.net',
    'phone_number': '001-743-805-6930x5877',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Norman Harrison',
    'Linda Montoya',
    'Valerie Ferguson',
    'Timothy Harris',
    'Rebekah Cline',
    'Jeremiah Hahn',
    'Michelle Gallagher',
    'Matthew Rangel',
    'Erika Green',
],
    'json': {
    'name': 'William Ruiz',
    'address': 'Unit 0642 Box 7480\nDPO AA 91096',
},
    'key74883': 'value79467',
    'key8696': 'value96103',
    'key49371': 'value59013',
    'key85471': 'value37620',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Lynn Hunter',
    'address': '0039 Brown Springs Suite 605\nWest Nancyport, PR 22761',
    'text': 'Once foreign entire effort level middle rule. Exist trial teacher finally chair ten.',
    'email': 'obrown@example.org',
    'phone_number': '270-632-5136x2787',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Thomas',
    'Nicholas Clayton',
    'Jacqueline Beck',
],
    'json': {
    'name': 'James Horn',
    'address': '825 Dawn Ville\nSouth Christopher, PA 12215',
},
    'key79816': 'value1767',
    'key78405': 'value829',
    'key31313': 'value83149',
    'key18450': 'value6002',
    'key43790': 'value44961',
    'key79197': 'value92271',
    'key90122': 'value85798',
    'key17665': 'value69892',
    'key84949': 'value30406',
    'key60199': 'value64310',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Gary Miller',
    'address': '049 Burgess Radial Suite 062\nRebeccatown, KY 62315',
    'text': 'Crime suggest improve suddenly cost. Make happy ever fund at collection best. Situation benefit figure suggest.',
    'email': 'zgates@example.com',
    'phone_number': '(622)691-3837x850',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Hill',
    'Stacy Fernandez',
],
    'json': {
    'name': 'Jeffrey Fisher',
    'address': '068 Bishop Via Apt. 385\nSaraport, VI 85119',
},
    'key45268': 'value21319',
    'key49119': 'value79574',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Scott Gardner',
    'address': '48888 Hamilton Heights\nNew Mark, OR 30752',
    'text': 'Design many property Mr series. Summer itself collection practice win simply. Health fact house natural.\nDrop media more easy provide guy police baby.',
    'email': 'steven09@example.com',
    'phone_number': '(813)700-9624x8321',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Harris',
    'Ethan Navarro',
    'Samuel Morrison',
    'Mr. Joshua Rogers',
    'Michael Ross',
    'Nancy Walters',
    'Brittney Spencer',
    'Emily Kim',
    'Kenneth Clark',
    'Amber Baird',
],
    'json': {
    'name': 'Susan Tate',
    'address': '8645 Samantha Station Apt. 182\nNew Aaronside, AL 38257',
},
    'key66510': 'value12747',
    'key28858': 'value6883',
    'key73425': 'value26831',
    'key91799': 'value81957',
    'key22125': 'value76248',
    'key33580': 'value89978',
    'key24624': 'value90798',
    'key14989': 'value85338',
    'key90835': 'value60478',
    'key43869': 'value44209',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Mrs. Stephanie Eaton',
    'address': '425 Johnson Burg Suite 901\nWest Crystalhaven, MI 80952',
    'text': 'Bring book future bed style medical senior either. Enough contain management audience lead right store.\nSport worry any deep. Interest skin evening authority change law.\nOrganization rock outside.',
    'email': 'gibsonjanice@example.com',
    'phone_number': '206.645.8657',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Noble MD',
    'Amy Nguyen',
    'Amanda Munoz',
],
    'json': {
    'name': 'Robert Chambers',
    'address': 'USNS Young\nFPO AP 22811',
},
    'key60476': 'value89073',
    'key41693': 'value34193',
    'key65199': 'value58756',
    'key18691': 'value74214',
    'key45468': 'value66847',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Crystal West',
    'address': '9353 Chandler Point\nBarbaratown, IL 32989',
    'text': 'Only address event various enough face. Term truth than thus yeah I hard commercial. Open us edge customer.',
    'email': 'annashepherd@example.net',
    'phone_number': '424-618-2289x01717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Scott Myers',
    'Stephen Campbell',
    'Laura Thomas',
    'Ashley Hall',
    'Jennifer Lewis',
    'Melissa Baxter',
    'James Walton',
    'Susan Williams',
    'Wendy Wilson',
    'Ronald Williams',
],
    'json': {
    'name': 'Anthony Greene',
    'address': '801 Grant Estate Suite 316\nWilliamsburgh, AS 78563',
},
    'key52261': 'value7325',
    'key91951': 'value26131',
    'key1258': 'value19753',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Kenneth Young',
    'address': '5297 Gonzales Mill Apt. 811\nWest Melissa, AZ 72435',
    'text': 'Leave computer want information. Foreign school only south total guy.\nMost environmental toward different.\nLittle market social there capital stand. End bed card course course national several.',
    'email': 'meredith81@example.org',
    'phone_number': '582-237-7570x685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Cole Haley',
    'Anthony Johnson',
    'Anthony Lopez',
    'Jennifer Ward',
    'Benjamin Fields',
    'Kelly Henderson',
],
    'json': {
    'name': 'Anita Russo',
    'address': '122 Brian Flats Suite 205\nClarkland, CA 83273',
},
    'key42463': 'value1082',
    'key4292': 'value78557',
    'key95713': 'value7924',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'David Ford',
    'address': '10979 Cowan Mountains Apt. 161\nSouth David, AR 54960',
    'text': 'Want few yet focus. Edge sister ask Democrat size. Future always consumer still.\nStock fact among lose child type. Drive onto economic trip. Dream realize dog hard.',
    'email': 'liujonathan@example.net',
    'phone_number': '+1-871-556-0950x45320',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lawrence Ray',
    'Daniel Carter',
    'Daniel Cook',
    'Valerie Roy',
    'Angel Hernandez',
    'Betty Marshall',
],
    'json': {
    'name': 'Ralph Mason',
    'address': '1807 Pineda Green\nNew Nicoleport, NC 51823',
},
    'key16718': 'value95727',
    'key72609': 'value82673',
    'key6618': 'value2077',
    'key56400': 'value22152',
    'key28544': 'value27969',
    'key79761': 'value88212',
    'key80926': 'value18540',
    'key91408': 'value92766',
    'key52649': 'value65363',
    'key60916': 'value88471',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Kristina Mason',
    'address': '36250 Parker Landing\nSouth Zacharymouth, WY 38096',
    'text': 'Eat feeling prepare themselves purpose fight. Manage only dinner plant wait product father.\nPart game claim yet sure. Value course lay production color. Bit than or age into.',
    'email': 'bhill@example.com',
    'phone_number': '001-537-873-7346x7999',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mark Holden',
    'Hannah Campos',
    'Timothy Owen',
    'Mackenzie Blake',
    'Shane Bell',
    'Samantha Taylor',
    'Jennifer Martinez',
],
    'json': {
    'name': 'Tristan Wilson',
    'address': '52192 Michael Summit Suite 422\nPorterborough, NY 49161',
},
    'key36615': 'value77073',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Janice Cook',
    'address': '79238 Chambers Mission\nManningburgh, CT 47992',
    'text': 'Change tell increase grow occur she behavior. Room live second analysis although.\nSit painting she want. Until spend lay consumer.\nBeautiful decide partner night.',
    'email': 'whitealicia@example.net',
    'phone_number': '730-866-0592x7180',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Paul',
    'Anthony Roberts',
    'Cory Conway Jr.',
    'Martin Cole',
    'Robert Gomez',
    'Anna Wiggins',
    'Kimberly Edwards',
    'Madison Harper',
    'Aaron Monroe',
],
    'json': {
    'name': 'Tamara Romero',
    'address': '581 Garza Glens Suite 337\nWest Carlos, WI 51765',
},
    'key8425': 'value5050',
    'key86423': 'value23058',
    'key89517': 'value52647',
    'key10337': 'value90799',
    'key85816': 'value94969',
    'key33521': 'value88304',
    'key67680': 'value24120',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Patrick Mcfarland',
    'address': '0783 Harris Wall Suite 192\nWest Jennifer, KS 55403',
    'text': 'Second store why they. How itself himself produce certainly sign. Letter nor camera nice tonight put.\nContinue training outside plan. Impact bar outside herself yourself.\nFire lead sell.',
    'email': 'troy55@example.net',
    'phone_number': '734-924-7498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Laurie Gibbs',
    'David Flores',
    'David Smith',
    'Charles Russell',
    'Dennis Dennis',
],
    'json': {
    'name': 'Susan Ellis',
    'address': '74824 Joy Passage Suite 310\nNathanielport, HI 11285',
},
    'key91144': 'value76085',
    'key42113': 'value48263',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Joseph Price',
    'address': 'Unit 0324 Box 4930\nDPO AE 07848',
    'text': 'Tv main particular season movie. Plant commercial guess our dinner personal particular.\nFilm trial early. Site check either media building agency. Thought these voice base.',
    'email': 'ramseyjennifer@example.net',
    'phone_number': '995-626-8808x8917',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Marshall',
    'Christian Parker',
    'Gwendolyn Martin',
    'Tammy Thomas',
    'Mia Rivera',
    'Michael Lopez',
    'Timothy Davis',
    'Kelsey Reeves',
    'Nicole Harrington',
],
    'json': {
    'name': 'Sherry Houston',
    'address': '3789 Porter Meadow Apt. 354\nDanielfurt, NY 85247',
},
    'key16088': 'value19304',
    'key31583': 'value17852',
    'key19392': 'value98963',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Nicole Simpson',
    'address': '45155 Amy Canyon Apt. 493\nNew Bernardfort, IN 41056',
    'text': 'Grow us in responsibility car listen sit. Partner opportunity cost.\nHow yet suggest identify interest more. Condition month long few care.',
    'email': 'anita98@example.net',
    'phone_number': '+1-859-896-1262x01205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Marcia Torres',
    'Martin Anderson',
],
    'json': {
    'name': 'Alison Welch',
    'address': 'PSC 0988, Box 2474\nAPO AE 66780',
},
    'key9089': 'value88928',
    'key99929': 'value93077',
    'key94265': 'value74816',
    'key47265': 'value85039',
    'key67587': 'value61569',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Paul Adams',
    'address': '8103 Alicia Lakes Apt. 266\nWest Matthew, MD 65235',
    'text': 'Follow design rise cold structure. Economic medical many.\nArtist skin live action image for.\nTelevision upon me parent. Feeling wait determine mission enter painting then.',
    'email': 'james41@example.org',
    'phone_number': '2368866279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Levi Nguyen',
    'Corey Mccoy',
    'Jessica Hendrix',
    'Julie Acosta',
],
    'json': {
    'name': 'Jacob Hopkins',
    'address': '0443 Reynolds Curve Apt. 144\nCoxchester, MS 66330',
},
    'key13099': 'value6519',
    'key40475': 'value44759',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Rebecca Graham',
    'address': '8436 Carr Mountain Suite 329\nLake Laurenfurt, TX 65000',
    'text': 'Church on you every type create. Nothing full better price claim yeah. Whom will agree test where.\nGoal consider reveal everything time themselves above. Our total morning sure computer information.',
    'email': 'vincentwalker@example.com',
    'phone_number': '7347451091',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Craig Evans',
    'Donald Carr',
],
    'json': {
    'name': 'Vincent Norris',
    'address': '8469 Rachel Lane\nConleyview, OH 56278',
},
    'key4746': 'value69043',
    'key33447': 'value41765',
    'key23701': 'value50504',
    'key11064': 'value80761',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Steven Smith',
    'address': '489 Walker Plaza\nPort Andrea, WA 28671',
    'text': 'Article easy her begin realize. Along find degree pay. Grow page close house water consumer sometimes.',
    'email': 'micheleschneider@example.org',
    'phone_number': '001-479-425-5335x6146',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sierra Stephens',
    'Anthony Burton',
    'Joseph Jones',
    'Donna Peterson',
    'Erik Smith',
],
    'json': {
    'name': 'Jonathan Ellis',
    'address': '2488 Graves Junctions\nNew Cynthia, WI 66155',
},
    'key40939': 'value47414',
    'key6116': 'value64371',
    'key94104': 'value10587',
    'key31727': 'value96587',
    'key49882': 'value79315',
    'key36806': 'value47911',
    'key65140': 'value46545',
    'key52315': 'value21542',
    'key30173': 'value2312',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Rebecca Martin',
    'address': '16632 Curry Creek Suite 894\nNorth Judymouth, TX 82711',
    'text': 'Apply within could else. In sort avoid build around.\nThird real down scene. Buy so science drive. Fire finish away risk community. Building concern possible including per behavior certainly.',
    'email': 'josenguyen@example.net',
    'phone_number': '774.860.5217x69951',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Donald Jones',
    'Leslie Jones',
    'Kelli Smith',
    'Michael Barnes',
    'Daniel Robinson',
    'Stephanie Perez',
    'Richard Knight',
    'Ernest Sanchez',
],
    'json': {
    'name': 'Kyle Cruz',
    'address': '018 Karen Knolls\nNew Joseph, KS 66007',
},
    'key4290': 'value68776',
    'key59461': 'value21741',
    'key45999': 'value38084',
    'key49123': 'value28182',
    'key21403': 'value36037',
    'key45068': 'value27999',
    'key38163': 'value53067',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Ann Crawford',
    'address': '947 Bryan Greens Apt. 570\nNorth Manuelshire, UT 66769',
    'text': 'Total put national itself. Morning economic condition part. Method improve baby radio eight since religious.\nFigure again role relate forget those performance.',
    'email': 'hsmith@example.net',
    'phone_number': '465.608.1565x85835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brittney Brooks',
],
    'json': {
    'name': 'Jesse Hawkins',
    'address': '33151 Burgess Squares\nWest Emily, VI 93913',
},
    'key4431': 'value88768',
    'key39824': 'value37737',
    'key79243': 'value41648',
    'key23066': 'value84785',
    'key50184': 'value16673',
    'key71500': 'value17195',
    'key46320': 'value94148',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Jason Briggs',
    'address': '79880 Tasha Square\nTaylormouth, MH 26429',
    'text': 'Allow religious by health per reveal. State before wide top move. Subject commercial others soldier TV of.',
    'email': 'mary63@example.net',
    'phone_number': '+1-281-584-8794x04024',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Richard Patrick',
    'Bethany Gray',
    'Jon Ramos',
    'Mrs. Nicole Clark DDS',
    'Keith Johnson',
    'David Paul',
    'Sara Miranda',
    'Maurice Thomas',
],
    'json': {
    'name': 'Bruce Stewart',
    'address': '873 Carlson Brook\nAdamshire, VT 65547',
},
    'key53158': 'value86551',
    'key16426': 'value8210',
    'key37655': 'value56853',
    'key28033': 'value63029',
    'key19151': 'value26386',
    'key71884': 'value94859',
    'key14782': 'value85651',
    'key29327': 'value59992',
    'key24796': 'value46122',
    'key83746': 'value24841',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Christian Stewart',
    'address': '10715 Hart Islands Suite 024\nEast Katherinechester, KS 54603',
    'text': 'Rock perform reach push expect her. Computer these western civil bar wife.\nLine wish often reveal travel agent nature. Newspaper matter American church design season. Have authority wide set science.',
    'email': 'huertajaime@example.com',
    'phone_number': '595-785-3845',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Justin Weiss II',
    'Taylor Allen',
    'Tyrone Blevins',
],
    'json': {
    'name': 'Derek Moore',
    'address': '46538 Cook Crescent Apt. 314\nRobertsmouth, PW 35760',
},
    'key78984': 'value34633',
    'key60898': 'value19014',
    'key99132': 'value14718',
    'key91702': 'value56957',
    'key8077': 'value1258',
    'key3007': 'value15772',
    'key35124': 'value49737',
    'key35347': 'value66706',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Tony Espinoza',
    'address': '86145 Lam Terrace Suite 703\nMayoland, ID 41058',
    'text': 'Pattern example yet laugh skill anything. Environment plan change act it stock song place.\nLocal name serve himself four charge final. All size whether change them on relationship.',
    'email': 'jesselin@example.net',
    'phone_number': '711.501.4193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Destiny Lindsey MD',
    'Christian Olson',
    'Maria Blair',
    'Neil Martin',
],
    'json': {
    'name': 'Crystal Kidd',
    'address': '224 Melissa Motorway Apt. 482\nWest Molly, ME 88100',
},
    'key78468': 'value15655',
    'key47968': 'value77252',
    'key66269': 'value40874',
    'key87790': 'value68770',
    'key60588': 'value68934',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Charles Reed',
    'address': '95747 Stephanie Divide Suite 891\nEspinozaburgh, WV 87245',
    'text': 'Option wind wide how. Issue everybody popular middle late.\nAfter across southern organization example even find. So south likely individual half ready person.',
    'email': 'edwardstammy@example.com',
    'phone_number': '(764)735-6537',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Wilson',
    'James Hawkins',
    'Maria Crawford',
    'Melissa Lee',
    'Shane Faulkner',
    'Duane Fowler',
    'Michael Blackwell',
    'Joseph Wood',
    'Ronald Kennedy',
    'Thomas Smith',
],
    'json': {
    'name': 'Kelly Cardenas',
    'address': '10170 William Parks\nNew Daisyborough, OH 77341',
},
    'key82133': 'value41822',
    'key43439': 'value85821',
    'key17504': 'value37932',
    'key89986': 'value65903',
    'key60924': 'value62888',
    'key12448': 'value30595',
    'key89799': 'value70',
    'key79571': 'value15582',
    'key50126': 'value72171',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'James Richard',
    'address': 'Unit 2616 Box 4479\nDPO AP 63393',
    'text': 'Cup paper maybe. Sing challenge pretty industry. Else purpose affect those particularly.',
    'email': 'ilane@example.com',
    'phone_number': '697.254.4967x5109',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steve Beck',
    'Wendy Franklin',
    'Emily Smith',
    'Travis Hudson',
    'Taylor Beasley',
    'Christopher Williams',
    'Steve Long',
],
    'json': {
    'name': 'Jeremy Mack',
    'address': '167 Mark Crest\nLake Jessica, AZ 25558',
},
    'key67811': 'value85457',
    'key63817': 'value10010',
    'key23509': 'value39674',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Nicole Moody',
    'address': '1789 Jennifer Union Apt. 154\nPort Stacytown, WY 30467',
    'text': 'Hit activity bring site stand. Player and for.\nExpect garden step evidence. Such war at mention want. Should politics at. Nature road war tough sing bit majority official.',
    'email': 'sullivankevin@example.net',
    'phone_number': '(398)269-7071',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Casey Greer',
    'Robert Villarreal',
    'Kelsey Hall',
],
    'json': {
    'name': 'Cassandra Lopez',
    'address': '019 Smith Cape\nTracybury, AK 28835',
},
    'key83576': 'value47543',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Elizabeth Chen',
    'address': '950 Morris Mountains Apt. 483\nRickyberg, VA 43853',
    'text': 'Author reflect politics wind take. Listen over source opportunity table nothing camera.\nTravel share care along country final.\nDevelop room better method past. Lot set civil above.',
    'email': 'kathleenmiller@example.net',
    'phone_number': '9785421955',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Mcdaniel',
    'Troy Rogers',
    'Diane Waters',
],
    'json': {
    'name': 'Christina Woods',
    'address': '0034 Joseph Ways\nGrossbury, VA 99926',
},
    'key67606': 'value39226',
    'key70510': 'value12963',
    'key70240': 'value93745',
    'key96869': 'value35887',
    'key57970': 'value34667',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Chad Carson',
    'address': '3274 Marissa Passage\nPriceland, CT 99557',
    'text': 'Fall real paper how science. Husband have affect. Have last letter fast measure commercial resource.\nPersonal opportunity become success board. Later reflect sell here. Six sound suffer.',
    'email': 'dawsonjulie@example.org',
    'phone_number': '782-679-2772x43427',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'John Rivera',
],
    'json': {
    'name': 'Erik Burns',
    'address': '7154 Miller Trace\nNorth Samanthaborough, SD 15260',
},
    'key85273': 'value86349',
    'key35423': 'value47636',
    'key3130': 'value82602',
    'key2258': 'value54927',
    'key9745': 'value54325',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Sandra Green',
    'address': '816 Sharon Motorway Apt. 695\nJohnsonmouth, GA 83730',
    'text': 'Or close structure sign serious weight. Action show knowledge nature so.\nOffice available cultural anything rather little. Avoid since authority.',
    'email': 'singhrebecca@example.org',
    'phone_number': '(340)564-0005',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Miss Jo Russell',
    'Molly Macias',
],
    'json': {
    'name': 'Rebecca Holland',
    'address': '1374 House Island Suite 766\nLake Nancy, NE 59135',
},
    'key98276': 'value58625',
    'key69380': 'value60635',
    'key92243': 'value73116',
    'key85257': 'value13056',
    'key85328': 'value39453',
    'key20064': 'value92988',
    'key30121': 'value50445',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Shannon Martin',
    'address': 'USCGC Lopez\nFPO AP 83027',
    'text': 'Natural against face dog data break individual. Bill little within act civil protect. Well senior relate.\nOther industry his course. Discussion break sure now ten. Technology four ago card stay.',
    'email': 'btaylor@example.net',
    'phone_number': '306-606-5606x6174',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Roger Barr',
    'Sarah Carter',
    'Christopher Chan',
    'Joshua York',
    'Leslie Barker',
    'Jaime Olson',
    'Dr. Charles George Jr.',
    'Derek Weeks',
    'Felicia Brown',
    'Alexander Newman',
],
    'json': {
    'name': 'Shane Brown',
    'address': '62574 Ford Street\nRodneyport, NC 62643',
},
    'key77989': 'value5194',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Brandon Simpson',
    'address': '3038 Walter Circles\nJessicaborough, OK 70417',
    'text': 'Can from even stand. Difference summer region art.\nReturn glass certainly sometimes poor surface.\nMr worker knowledge yes. Special building but beautiful.',
    'email': 'kenneth33@example.com',
    'phone_number': '+1-593-619-5939x95785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Lindsey White',
],
    'json': {
    'name': 'Walter Mcguire',
    'address': '51213 Christian Mountains\nSouth Sophia, SD 18199',
},
    'key41257': 'value4994',
    'key5164': 'value14417',
    'key43524': 'value61608',
    'key74972': 'value37117',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Daniel Reynolds III',
    'address': '950 Matthews Cape\nWest Brittanytown, NJ 93295',
    'text': 'Not travel through hotel lawyer deal mission. Bad pattern agree. Political matter move institution.\nFamily still Mr well country recognize could. Blood herself nothing research such under.',
    'email': 'zmcgee@example.net',
    'phone_number': '496-782-2485x2785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Webb',
    'Christopher Taylor',
    'Jeffrey Brady',
    'Mandy Palmer',
    'Jennifer Rodriguez',
],
    'json': {
    'name': 'Jorge Conway',
    'address': '40984 Garrison Loop Suite 473\nLake Anthonyland, VI 97009',
},
    'key40537': 'value18061',
    'key22327': 'value62620',
    'key3584': 'value35681',
    'key4893': 'value19766',
    'key69823': 'value87755',
    'key45369': 'value63651',
    'key62845': 'value92136',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Justin Rosario',
    'address': '4825 Kirk Bypass Apt. 939\nNorth Glen, AK 08595',
    'text': 'Service expert bed positive. Bed six sell occur hope data true.\nBusiness security green you.\nTalk term central story example. Cup of none.\nHowever dream save big although animal least.',
    'email': 'jtownsend@example.com',
    'phone_number': '359.790.9216',
    'array_int_dynamic': [
    51446,
],
    'array_varchar_dynamic': [
    'Natalie Gomez',
    'Kelly Adkins',
],
    'json': {
    'name': 'Ms. Sonya Wilson',
    'address': '5713 Rodriguez Mountains\nMarquezville, OH 91623',
},
    'key91834': 'value43952',
    'key80597': 'value22794',
    'key95501': 'value74528',
    'key3965': 'value15137',
    'key46338': 'value28358',
    'key97842': 'value16234',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Betty Moreno',
    'address': '206 Nelson Via Apt. 600\nMichaelmouth, MT 95762',
    'text': 'Within author dog stock.\nWhy threat let particularly imagine look program. Key sense college detail threat explain current. Happen financial concern physical.',
    'email': 'ericsimmons@example.net',
    'phone_number': '001-930-998-7474x55561',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Karen Jones',
    'Ashley Lewis',
    'Jennifer Foster',
    'Mr. Austin Barrett PhD',
    'Bianca Mills',
    'Nathan Adams',
    'Hannah Hale',
    'Ray Tyler',
    'Ryan Gomez',
],
    'json': {
    'name': 'Christopher Ramirez',
    'address': '40744 Holt Prairie Suite 321\nMatthewston, ID 24223',
},
    'key87711': 'value2498',
    'key3207': 'value78821',
    'key69889': 'value64433',
    'key3659': 'value94033',
    'key34052': 'value15217',
    'key89751': 'value37390',
    'key55124': 'value90839',
    'key69304': 'value15633',
    'key85012': 'value75165',
    'key98088': 'value42805',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Jillian Smith',
    'address': '908 Chapman Freeway Suite 714\nEast Jamie, WA 18585',
    'text': 'Process investment specific sure rate figure necessary manager. Want television direction attack least plant require. Truth season though travel member hundred recognize pick.',
    'email': 'bwright@example.org',
    'phone_number': '(597)709-2571x86011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jason Blanchard',
    'Troy Stone',
    'Maria Thomas',
    'Karen Carlson',
    'Jessica Cabrera',
    'Danny Nichols',
    'Douglas Hood',
    'Glen Mora',
    'Joel Thompson',
],
    'json': {
    'name': 'Anna Gill',
    'address': '8353 Nixon Fort\nPamelamouth, WV 27336',
},
    'key16143': 'value71302',
    'key3530': 'value72933',
    'key86242': 'value39260',
    'key7097': 'value76006',
    'key22487': 'value26935',
    'key60323': 'value36381',
    'key1352': 'value86995',
    'key97871': 'value6522',
    'key44094': 'value60601',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Robert Mccarty',
    'address': '193 Franklin Union\nDawnmouth, NV 62512',
    'text': 'Somebody above skill address series. Attack choose common benefit office. Long science field space state clear various.',
    'email': 'joan07@example.org',
    'phone_number': '(963)302-7252x4810',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Soto',
    'Theresa Smith',
    'Isabella Mendez MD',
    'Dr. Lindsey Mitchell',
    'Wayne Thomas',
    'Amanda Simpson',
    'Julie Suarez',
    'Christina Pena',
    'Shelly Murillo',
],
    'json': {
    'name': 'Kimberly Clark',
    'address': '623 Dunn Glen\nConnorborough, KS 42072',
},
    'key31659': 'value77741',
    'key80603': 'value99482',
    'key49573': 'value69536',
    'key3629': 'value15456',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Mary Mendoza',
    'address': '72900 Brooke Shore\nNorth Darrenfort, AL 43901',
    'text': 'Among senior push nice. Anything imagine ability management leave fight.\nContinue own seven. Push what mean power. Market fight gun agent book sing.',
    'email': 'james12@example.com',
    'phone_number': '(649)473-2417x2212',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tina Taylor',
    'Deborah Lee',
    'Theresa Norton',
    'Mr. Raymond Hernandez',
    'Crystal Medina',
    'Jennifer Burgess',
    'Daniel Franklin',
    'Kevin Alexander',
    'Jerry Garza',
],
    'json': {
    'name': 'Emily Anderson',
    'address': '4104 Young Prairie Apt. 096\nLake Michaelmouth, PA 81044',
},
    'key31759': 'value54816',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Ross Davis',
    'address': '847 Nancy Square Suite 747\nWest Scott, TX 55585',
    'text': 'Word analysis even computer mean account pull. Sport consumer hour. Within arrive seek within deep plant. Size hundred onto record feeling claim.',
    'email': 'goodmantina@example.net',
    'phone_number': '001-275-679-1686x7147',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Munoz',
    'Rebecca Hawkins',
    'Michael Suarez',
    'Lauren Rodriguez',
    'Heather Mathews',
    'Brooke Lewis',
    'Daniel Walls',
    'James Garza',
    'Joseph Kennedy',
],
    'json': {
    'name': 'Toni Munoz',
    'address': '4854 Dakota Avenue\nAndrewsstad, MN 60599',
},
    'key86374': 'value39106',
    'key92704': 'value54035',
    'key25782': 'value68917',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Amanda Dominguez',
    'address': '2665 Ward Valley Apt. 676\nChristinafort, WY 06360',
    'text': 'Suffer fish recognize blue. Put bad century word. Age bag whose. Deal leader new travel.',
    'email': 'moorerebecca@example.net',
    'phone_number': '724.651.2032x109',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Derrick Herrera',
    'Sarah Maddox',
    'Matthew Gibbs',
    'Richard Mays',
    'Tyler Rocha',
    'Shaun Harrison',
    'Jason Mitchell',
],
    'json': {
    'name': 'Angela Parker',
    'address': '2057 Jodi Isle Apt. 511\nWest Richard, MO 89672',
},
    'key89877': 'value91235',
    'key67794': 'value70546',
    'key17953': 'value4455',
    'key93779': 'value18064',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Matthew Wright',
    'address': '885 Amy Mission Apt. 434\nKyleton, NH 20158',
    'text': 'Reveal rest many reduce only. Personal land always fish. New even seek. Three expect rest first certain field open.\nFormer find attention standard than morning main. House far charge.',
    'email': 'fernando28@example.net',
    'phone_number': '(903)782-6080x68659',
    'array_int_dynamic': [
    54904,
],
    'array_varchar_dynamic': [
    'Lee Gibbs',
    'Joel Miller',
    'Joshua Zuniga',
    'Donna Oliver',
    'Mr. Ricardo Owen DDS',
    'Ryan Perez',
    'Terry Newman',
    'Cheryl Sanders',
],
    'json': {
    'name': 'Randy Anderson',
    'address': '873 Ariana Street Apt. 457\nLake Lauren, VT 83174',
},
    'key23959': 'value67128',
    'key66128': 'value44502',
    'key45882': 'value83080',
    'key29170': 'value32107',
    'key3241': 'value17674',
    'key13150': 'value24660',
    'key9467': 'value76822',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Jacob Allen',
    'address': 'USNV Sherman\nFPO AP 38708',
    'text': 'Piece hope already. Great weight goal nature consider yourself. Side price key vote perhaps course war.',
    'email': 'agonzalez@example.net',
    'phone_number': '764.780.4992x2267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Jacobs',
],
    'json': {
    'name': 'Andrew Estrada',
    'address': '8445 Williams Ridges\nEast Jamesburgh, SC 90373',
},
    'key82482': 'value85539',
    'key16908': 'value44945',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Melissa Parrish',
    'address': '814 Richard Junction\nMichellemouth, ND 39400',
    'text': 'Themselves campaign center matter actually answer inside. Military us who relationship grow study oil. Use star must decide enter story.',
    'email': 'jimmyadams@example.net',
    'phone_number': '+1-977-386-6494x22713',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl Young',
    'Julian Anderson',
    'Daniel Valentine',
    'Colleen Meadows',
    'James Logan',
    'Crystal Garcia',
    'Michelle Payne',
    'Mark Gutierrez',
    'Eric Smith',
],
    'json': {
    'name': 'Melissa Owens',
    'address': '7912 Oconnor Center Suite 940\nBakermouth, IA 25436',
},
    'key32128': 'value72532',
    'key2103': 'value4985',
    'key99886': 'value30761',
    'key58356': 'value55707',
    'key93745': 'value76885',
    'key74971': 'value3280',
    'key44388': 'value8957',
    'key78253': 'value4049',
    'key58951': 'value11769',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Tony Smith',
    'address': 'PSC 7938, Box 6814\nAPO AA 43916',
    'text': 'Wear majority institution sit full raise less. Mention decision smile agency open. It argue rule risk.',
    'email': 'banksricky@example.org',
    'phone_number': '5209502597',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Gonzalez',
    'Ashley Murray',
    'Jennifer Miller',
    'Natalie Ward',
    'Jennifer Beck',
    'Jennifer Thompson',
    'Benjamin Craig',
],
    'json': {
    'name': 'Rebecca Brewer',
    'address': '0501 Rachel Port Suite 961\nLake Francis, NY 16208',
},
    'key23016': 'value13358',
    'key44320': 'value27250',
    'key97922': 'value68318',
    'key73414': 'value20630',
    'key8057': 'value57327',
    'key79705': 'value69031',
    'key6594': 'value59604',
    'key3185': 'value82876',
    'key90819': 'value30805',
    'key65115': 'value48138',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Joseph Jackson',
    'address': '4808 Maria Light\nSouth Michael, CA 40745',
    'text': 'Blue pick side rather dinner test remember. Despite others system. Relationship box suggest practice young well institution. Military arrive good young.',
    'email': 'pattersonbonnie@example.net',
    'phone_number': '+1-265-958-5641x766',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Choi',
    'Tina Freeman',
    'Anita Hall',
    'Robert Doyle',
    'Frank Ryan',
],
    'json': {
    'name': 'Adrian White',
    'address': '6846 Donovan Brook\nLake Rose, WY 02382',
},
    'key95543': 'value2906',
    'key91184': 'value94316',
    'key32794': 'value25434',
    'key64121': 'value29608',
    'key48468': 'value30287',
    'key37417': 'value86138',
    'key25607': 'value97399',
    'key19547': 'value8479',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Penny Hutchinson',
    'address': '00869 Blake Point\nJacquelineview, MI 83281',
    'text': 'Also nice place leader prove be before. Whom treat TV order. Any according international section million try.\nAffect two front store among girl behind. Management court play increase decade.',
    'email': 'ballardjessica@example.net',
    'phone_number': '828-637-7420',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Phyllis Gates',
    'Rebecca Lee',
    'Jennifer Huber',
],
    'json': {
    'name': 'Eric Estrada',
    'address': '261 Perry Forge Suite 302\nEast Matthew, OK 02586',
},
    'key76019': 'value94824',
    'key47819': 'value22414',
    'key38326': 'value75231',
    'key28770': 'value95445',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Felicia Edwards',
    'address': '232 Espinoza Canyon Suite 781\nLake Cynthiamouth, PA 93909',
    'text': 'Writer write environmental magazine. Report image too various enjoy ok sit.\nFrom first interesting administration board. Tell hold lead sometimes animal process.',
    'email': 'mary10@example.org',
    'phone_number': '857.961.4717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Frank Hernandez',
    'Julie Craig',
    'Heather Hawkins',
    'Margaret Rojas',
    'Margaret Smith',
    'Jennifer Robinson',
    'Anthony Mccormick',
    'Andrew Williams',
    'Michelle Osborne',
],
    'json': {
    'name': 'Samantha Butler',
    'address': '123 William Hollow Apt. 285\nSouth Tom, AZ 64805',
},
    'key93984': 'value64237',
    'key42340': 'value98790',
    'key21870': 'value46711',
    'key66419': 'value57086',
    'key38053': 'value24747',
    'key70569': 'value58885',
    'key82536': 'value91307',
    'key24385': 'value50443',
    'key80159': 'value8159',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Christopher Castro',
    'address': '5580 Brown Skyway\nSouth Courtney, MP 92813',
    'text': 'Light occur daughter. Bar city hotel door culture. Defense find conference future player feeling.\nStreet quickly bar ready value. Investment soon sound.',
    'email': 'mscott@example.com',
    'phone_number': '606.808.2578x46457',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'William Jones',
    'Michael Duncan',
    'Mrs. Beth Kelly',
    'Ryan Scott',
    'Melinda Kidd',
    'Scott Reyes',
    'Cheryl Lopez',
    'Cynthia Rangel',
],
    'json': {
    'name': 'Melissa Holder',
    'address': '488 Micheal Villages\nDuartebury, IL 31261',
},
    'key49722': 'value84422',
    'key30303': 'value69169',
    'key72049': 'value41332',
    'key40219': 'value2865',
    'key93455': 'value8536',
    'key41402': 'value3583',
    'key87435': 'value34819',
    'key53429': 'value61806',
    'key80022': 'value22399',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Ashley Escobar',
    'address': '55177 Chambers Ridges Apt. 831\nLake Reneeborough, SC 57862',
    'text': 'Style head stock blue along street indeed.\nEight treat couple piece spend sometimes. Summer history item market one. Will none energy.',
    'email': 'brownelaine@example.com',
    'phone_number': '+1-347-585-4685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Gonzales',
    'Frank Guzman',
    'Lisa Wright',
    'Pamela Mitchell',
],
    'json': {
    'name': 'Jane Salazar',
    'address': '629 Espinoza Station Suite 309\nNorth Sierraview, FL 20232',
},
    'key88998': 'value61152',
    'key30825': 'value3438',
    'key18339': 'value93209',
    'key68506': 'value21789',
    'key3371': 'value89384',
    'key86621': 'value14672',
    'key9322': 'value77078',
    'key7751': 'value63334',
    'key87098': 'value70539',
    'key62380': 'value56469',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Mike Weaver',
    'address': '7559 Ochoa Grove Suite 104\nNew Darlenetown, PW 93238',
    'text': 'Just share some senior begin second reality. Use fire physical company.\nSociety save threat family member listen. Sound relate cover service. Special moment capital add.',
    'email': 'chelseyprice@example.org',
    'phone_number': '4374108006',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Erika Stevens',
    'Molly Reynolds',
    'Kathleen Carlson',
    'Billy Santana',
    'Bobby Escobar',
    'Amber Chase',
    'Angela Hamilton',
    'Marisa Smith',
    'Derek Carter',
    'William Colon',
],
    'json': {
    'name': 'Michelle Snyder',
    'address': '1341 Cunningham Parkway Suite 412\nWest Amberland, OR 78069',
},
    'key21605': 'value82749',
    'key91205': 'value5647',
    'key73873': 'value18689',
    'key60620': 'value23714',
    'key37057': 'value21569',
    'key79363': 'value69597',
    'key7945': 'value53868',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Paul Thomas',
    'address': '28971 Avery Fall Suite 998\nLake Rebecca, PA 70438',
    'text': 'Sound audience line sound.\nCongress important sit win difference early. Success business while school raise cold trip.\nGeneration unit strategy new. Close nothing card claim.',
    'email': 'manuel97@example.net',
    'phone_number': '201.941.2634x7274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tara Cisneros',
    'Andrea Price',
    'Jennifer Flores',
    'Penny Hernandez',
    'Jennifer Collier',
    'Kathryn Daugherty',
    'James Yu',
    'Kelly Briggs',
],
    'json': {
    'name': 'Jasmine Smith',
    'address': '4990 Wilson Heights\nWendymouth, DC 56674',
},
    'key14216': 'value33965',
    'key6952': 'value12185',
    'key15260': 'value70840',
    'key1908': 'value66575',
    'key74649': 'value78302',
    'key72685': 'value12262',
    'key88933': 'value76346',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Madison Flores',
    'address': '3964 Smith Shore\nPort Katherine, IL 23534',
    'text': 'Seat he morning member range visit. Past recently get break order whole quality. See yourself half history.',
    'email': 'andersonmonica@example.com',
    'phone_number': '418.435.3888',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Cooper',
    'Joseph Cox',
    'Daniel Parker',
    'Steven Armstrong',
    'Frances Kim',
    'Samantha Strong',
    'Bruce Harrington',
    'Adam Simpson',
    'Monica Harris',
],
    'json': {
    'name': 'Nathan Lee',
    'address': '814 Johnson Valley\nMarcoborough, VI 13526',
},
    'key84342': 'value81966',
    'key41726': 'value97995',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Miguel Sanders',
    'address': '055 Patrick Parkway\nRobinport, MA 65461',
    'text': 'Energy particular lead yet suffer page for human. Understand author public just operation.',
    'email': 'nicholas76@example.com',
    'phone_number': '(645)528-9885x8475',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amy Simpson',
    'Brian Vargas',
    'Adrienne Hall',
    'Adam Haney',
    'Morgan Wilson',
    'Sydney Velez',
    'Patricia West',
],
    'json': {
    'name': 'Howard Erickson',
    'address': '0978 Browning Meadows\nTarashire, MN 93730',
},
    'key77612': 'value73960',
    'key51617': 'value65525',
    'key97544': 'value57286',
    'key95797': 'value61395',
    'key6837': 'value1290',
    'key59405': 'value83517',
    'key31079': 'value58799',
    'key15817': 'value34963',
    'key12725': 'value13776',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Sierra Little',
    'address': '8815 Gabrielle Circles\nMillerton, UT 46294',
    'text': 'Against rather situation company officer receive me. Final environment some also hair discussion radio force.',
    'email': 'melissa29@example.com',
    'phone_number': '+1-871-476-5282x568',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Diana Jones',
    'Anthony Hicks',
    'Gregory Orr',
    'Mary Robinson',
    'Katie Garrison',
    'Danielle Petersen',
    'Sarah Curtis',
],
    'json': {
    'name': 'Elizabeth Hill',
    'address': 'Unit 7212 Box 0061\nDPO AP 61691',
},
    'key92854': 'value50402',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Jeffery Mcfarland',
    'address': '33004 Karen Freeway Apt. 443\nAndrewfort, HI 32945',
    'text': 'Maintain force type value.\nLand myself network political if near recent continue. Pay spend third. Fact young oil second. Occur strategy itself level.',
    'email': 'kellyvelasquez@example.net',
    'phone_number': '240-823-8392x803',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Natasha Miller',
    'Benjamin Castillo',
    'Dustin Cunningham',
    'Jeffrey Carter',
    'Brandon Wallace',
    'Cristian Richard',
    'Brian Pierce',
    'Christine Gates',
    'Linda Mora',
    'James Fitzgerald',
],
    'json': {
    'name': 'Kimberly Owens',
    'address': '563 Hancock Parkway\nSouth Amberview, KY 55580',
},
    'key80259': 'value21892',
    'key79723': 'value22444',
    'key4370': 'value56344',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Rachael Bishop',
    'address': '26778 Stacy Corners Suite 162\nNew Dawnhaven, VT 53399',
    'text': 'Special certain happen class structure. Stop experience practice example cause fact. Operation better specific.\nLater ask country yes education. Bar quickly drop hundred book.',
    'email': 'juan27@example.org',
    'phone_number': '4764434527',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Gutierrez',
    'Carla Medina',
    'Sylvia Collins',
    'Malik Jones',
    'Lisa Romero',
    'Karen Herrera',
    'Jason Burns',
    'Tonya Payne',
],
    'json': {
    'name': 'Nicole Prince',
    'address': '5091 Sanchez Shores Suite 044\nPort Christine, VT 04162',
},
    'key44308': 'value92299',
    'key19166': 'value57192',
    'key68779': 'value81891',
    'key972': 'value65209',
    'key96704': 'value52708',
    'key98490': 'value33844',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Sandra Lane',
    'address': '43106 Hunter Row Suite 690\nNorth Lisa, WI 07149',
    'text': 'Method state opportunity finally box. Stay size cost your partner health. Character its game usually star together true.',
    'email': 'hawkinskristina@example.com',
    'phone_number': '8726260255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Howell',
    'Michael Simpson',
    'Brandon Hill',
    'Hannah Ritter',
    'Cathy Washington',
    'Robert Wood',
    'Amanda Warren',
    'Ryan Mitchell',
    'Erin Sherman',
    'Jessica Mclaughlin',
],
    'json': {
    'name': 'Brittany Higgins',
    'address': '128 Travis Ranch Apt. 410\nPort Eileen, RI 61667',
},
    'key31760': 'value50480',
    'key11820': 'value83256',
    'key60459': 'value76159',
    'key42213': 'value25959',
    'key54027': 'value77454',
    'key16637': 'value54861',
    'key95615': 'value55740',
    'key69179': 'value36191',
    'key15424': 'value84663',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Bobby Martinez',
    'address': '91457 Green Prairie Suite 674\nNew Mariahport, CA 81311',
    'text': 'Design well activity international member. My item stay.\nShare practice read small. For can daughter cause town. Study model peace sort.',
    'email': 'pricemichelle@example.com',
    'phone_number': '(228)649-5202x791',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Jackson',
    'Gabriela Lopez',
    'Sandra Rice',
    'Kelsey Hernandez',
    'Michael Foster',
    'Sarah Holder',
],
    'json': {
    'name': 'Peter Long',
    'address': '810 Miller Mountains\nCarolynfurt, CT 99611',
},
    'key10224': 'value85472',
    'key71301': 'value64420',
    'key86861': 'value72111',
    'key45096': 'value19823',
    'key45283': 'value1773',
    'key3804': 'value13570',
    'key59663': 'value7379',
    'key9056': 'value94',
    'key6471': 'value73359',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'William Carter',
    'address': '63590 John Green\nNorth Anthonyview, PR 60465',
    'text': 'Half admit blue deep. Two purpose middle impact responsibility. Beautiful visit situation hope keep agreement.\nIndeed family seat five draw wonder mother another.',
    'email': 'lware@example.net',
    'phone_number': '+1-371-439-0876x343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Burton',
],
    'json': {
    'name': 'Katie Pruitt',
    'address': '21506 Taylor Wells\nPort Kevin, UT 52812',
},
    'key31285': 'value95148',
    'key80451': 'value22772',
    'key74372': 'value48818',
    'key37913': 'value94265',
    'key54002': 'value65800',
    'key92764': 'value23495',
    'key59586': 'value94521',
    'key47212': 'value79870',
    'key12461': 'value54284',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Rhonda Mccarthy',
    'address': '1991 Bernard Stravenue Suite 917\nMorganmouth, NM 45331',
    'text': 'Meet those red become. Indeed per second seat. Build bad body Mrs. While action accept offer.',
    'email': 'christopherparker@example.com',
    'phone_number': '(519)209-2739x9800',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tara Payne',
    'Michelle Fisher',
],
    'json': {
    'name': 'Cassandra Nguyen',
    'address': '19877 Robert Summit Suite 247\nAlexisstad, CA 75437',
},
    'key59378': 'value46587',
    'key96043': 'value37556',
    'key59471': 'value22683',
    'key76292': 'value12118',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Tracy Wright',
    'address': 'PSC 8086, Box 5596\nAPO AE 11132',
    'text': 'Particularly deep exactly nothing today line. For within value edge material real.\nAuthority become modern. If call western hope service start.',
    'email': 'kyle02@example.org',
    'phone_number': '984.457.1834x23224',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Morales',
    'William Berry',
],
    'json': {
    'name': 'Caitlin Thomas',
    'address': '11267 Elijah Lane\nAmbertown, AL 50353',
},
    'key17751': 'value100',
    'key33704': 'value2440',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Matthew Kelly',
    'address': '34579 Strong Junctions Suite 848\nRichardschester, KS 56788',
    'text': 'At energy still above. Assume member would his rise. Order reduce southern item place. Herself whatever growth.',
    'email': 'elizabeth89@example.net',
    'phone_number': '+1-974-970-2197',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Boyd',
    'Nicholas Woodward',
    'Ricardo Cook',
    'Melissa Charles',
    'Rachael Knight',
    'Anthony Jennings',
],
    'json': {
    'name': 'Jeremy Yang',
    'address': '5062 Joshua Valley\nKennedyland, ND 06175',
},
    'key80339': 'value87310',
    'key51282': 'value3666',
    'key85399': 'value77664',
    'key10415': 'value28714',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Ashley Green',
    'address': '796 Ernest Rapids Suite 254\nNew Christopher, UT 40882',
    'text': 'Cell identify magazine weight tax recent little. Into first worry vote off catch task. Deal office stuff only. Idea laugh test seek such degree indicate.\nProve one deal fly site. Will news model dog.',
    'email': 'spatterson@example.com',
    'phone_number': '723-309-2449x5265',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Powell',
    'Amy Rodriguez DDS',
    'Kim Parks',
    'Vanessa Johnson',
    'Elizabeth Benson',
],
    'json': {
    'name': 'Dennis Carter',
    'address': '80432 Amy Branch\nEvansmouth, CA 44719',
},
    'key18229': 'value39006',
    'key94029': 'value90339',
    'key71267': 'value14447',
    'key14853': 'value89156',
    'key50551': 'value93692',
    'key9047': 'value95052',
    'key30828': 'value21504',
    'key18189': 'value18277',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Scott Richards',
    'address': '311 Paul Orchard Apt. 508\nMaryfort, NY 41013',
    'text': 'Three nearly catch mention. Require indicate less professor product.\nSend product everybody hold event marriage save modern. Authority anything red. Off inside direction oil want.',
    'email': 'vtaylor@example.org',
    'phone_number': '+1-435-454-0671x99971',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Guzman',
    'Caitlin Krause',
    'Jessica Brooks',
    'Kenneth King II',
    'Brandon Rios',
    'Sheena Johns',
    'Mary Lee',
],
    'json': {
    'name': 'Jeremy Johnson',
    'address': '37869 Santiago Street\nSarahmouth, PW 19807',
},
    'key61484': 'value66215',
    'key10948': 'value56586',
    'key78677': 'value53284',
    'key73730': 'value53680',
    'key29776': 'value83161',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Nancy Dunn',
    'address': '64306 Joshua Roads\nPort Maurice, FL 47402',
    'text': 'Single opportunity source up ago hot popular final. Bill throw guy buy. Certainly five hold high suggest. Wait leg report consumer.',
    'email': 'ialvarez@example.net',
    'phone_number': '450-957-8715x77398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mandy Brady',
    'Joshua Hall',
    'Luis Harper',
    'Ryan Parker',
    'Dillon Weaver',
    'Richard Rodriguez',
    'Valerie Johnson',
    'Alison Salazar',
    'Jennifer Costa',
],
    'json': {
    'name': 'Michael Gonzalez',
    'address': 'PSC 3869, Box 5523\nAPO AE 89626',
},
    'key88720': 'value68263',
    'key60168': 'value15045',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Elizabeth Williamson',
    'address': '922 Julia Lane\nKevinfort, PR 80353',
    'text': 'Build right few quickly watch direction year.\nSpecial drop in change successful news animal.',
    'email': 'ryan75@example.com',
    'phone_number': '948.799.8827x588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Powers',
    'Mrs. Ashley Mitchell',
    'Brandon Pugh',
    'Alexander Reyes',
],
    'json': {
    'name': 'Michael Johnson',
    'address': '020 Mullen Plain\nSouth Saraport, TX 56198',
},
    'key46893': 'value95826',
    'key93090': 'value87841',
    'key76835': 'value47711',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Richard Jimenez',
    'address': '6014 Steele Loaf\nBrettland, KY 81549',
    'text': 'Believe tend very her point eight authority. One alone movement land large or expect.\nSense ok chair peace piece hundred least.',
    'email': 'christensenmonique@example.com',
    'phone_number': '497.202.2232',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jason Smith',
    'David Hoffman Jr.',
    'Brittany Molina',
],
    'json': {
    'name': 'Ryan Walker',
    'address': '7388 Timothy Mountain Apt. 603\nRogersfort, MO 33621',
},
    'key97533': 'value22786',
    'key96291': 'value84011',
    'key41000': 'value65963',
    'key43467': 'value9536',
    'key44178': 'value34852',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Heather Norman',
    'address': '077 Brown Plaza\nDoughertyfort, PR 47074',
    'text': 'Standard he and learn deep meeting range blood. Deep continue kind move culture human forget. Upon challenge item surface later different.',
    'email': 'clementstrevor@example.com',
    'phone_number': '(226)272-2968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Patel',
    'David Beard DVM',
    'Elizabeth Mitchell',
    'John Adkins',
    'Kara Watson',
    'Seth Hahn',
    'Scott Martinez',
],
    'json': {
    'name': 'Michael Garrison',
    'address': '964 Carolyn Forks\nNorth Williamtown, SC 35603',
},
    'key27700': 'value64332',
    'key18226': 'value82692',
    'key88711': 'value33628',
    'key99242': 'value66113',
    'key5254': 'value67748',
    'key96787': 'value51973',
    'key31180': 'value9737',
    'key97379': 'value68496',
    'key45109': 'value2985',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Gary Maynard',
    'address': '283 Tonya Greens Apt. 701\nRhodeston, NC 92454',
    'text': 'Send try keep enter hope organization toward. Candidate sometimes administration kind piece receive for. Create force crime thank edge there.',
    'email': 'ronald60@example.net',
    'phone_number': '845.962.0795',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Barnes',
    'Mary Reyes',
    'Katie Bruce',
],
    'json': {
    'name': 'Sandra Collins',
    'address': 'PSC 2801, Box 6187\nAPO AE 26944',
},
    'key17896': 'value62728',
    'key70550': 'value53721',
    'key32533': 'value62327',
    'key96083': 'value55406',
    'key24097': 'value97354',
    'key37040': 'value41043',
    'key87905': 'value80085',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Brianna Harrison',
    'address': '0831 Robert Summit Suite 988\nHartville, MA 82223',
    'text': 'Development serious open toward. Employee apply effect nature mention along Mrs.',
    'email': 'kennedypamela@example.org',
    'phone_number': '786-988-3060',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Parker',
],
    'json': {
    'name': 'Aaron Medina',
    'address': '997 Caitlin Passage Suite 347\nLake Hannahburgh, PW 23097',
},
    'key29417': 'value98948',
    'key4720': 'value82210',
    'key4005': 'value4120',
    'key81021': 'value36124',
    'key51248': 'value25229',
    'key51392': 'value58836',
    'key7774': 'value66406',
    'key18436': 'value60500',
    'key83482': 'value53211',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Michael Golden',
    'address': '493 Wagner Spurs\nNorth Nicholas, DC 28427',
    'text': 'Difference how policy a here big. Little someone hard report.\nIssue economic reason report. Type audience color law. Remember have nice full.\nAlong reveal second subject consumer. Crime more until.',
    'email': 'graykatie@example.com',
    'phone_number': '253-357-4606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Salazar',
    'Yolanda Brown',
    'Mark Kelley',
    'Margaret West',
],
    'json': {
    'name': 'Anthony Rodriguez',
    'address': '660 Jacqueline Rapid\nKelleyport, RI 78033',
},
    'key2312': 'value14634',
    'key49060': 'value52553',
    'key67521': 'value19564',
    'key11199': 'value25367',
    'key22125': 'value62555',
    'key49117': 'value24235',
    'key20625': 'value76186',
    'key11153': 'value38205',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Hayden Maldonado',
    'address': '83815 Michael Locks\nChelseaport, NV 75307',
    'text': 'Indeed heavy future month bed. Certainly cost picture reach heavy kid. Trade anything people north campaign little sign its. Safe house book election reveal.',
    'email': 'heather73@example.net',
    'phone_number': '(589)550-0273x45902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Wendy Harris',
    'Ruben Smith',
    'Mandy Haney',
    'Cheyenne Thompson',
    'Jennifer Wilkerson',
    'Victor Martin',
    'Paul Gray',
    'Hannah Berry',
    'Rebecca Richardson',
],
    'json': {
    'name': 'Juan Frazier',
    'address': '43952 Kenneth Stravenue\nJosefurt, ND 84453',
},
    'key84819': 'value10301',
    'key37330': 'value64505',
    'key66808': 'value37867',
    'key67143': 'value83618',
    'key19668': 'value81991',
    'key51888': 'value72120',
    'key31312': 'value99123',
    'key18611': 'value79172',
    'key70586': 'value99',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Charles Duncan',
    'address': '782 Jessica Groves Apt. 878\nLake Cheryl, PA 22423',
    'text': 'Natural night stock throw certainly. People player smile scientist you common general. Mother site base teach.',
    'email': 'cjohnson@example.net',
    'phone_number': '(826)653-6505',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Leblanc',
],
    'json': {
    'name': 'Albert Lee',
    'address': '16341 James Neck\nBeverlystad, WY 24112',
},
    'key45051': 'value73842',
    'key50833': 'value718',
    'key36146': 'value12533',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Jennifer Reyes',
    'address': '451 Finley Port\nPort Karenfort, PA 44539',
    'text': 'Left baby group issue fine simple study. Popular move effort. Listen too remember quickly far great begin.',
    'email': 'pamelalewis@example.com',
    'phone_number': '+1-351-782-3499x53606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dustin Clark',
    'Carla Hutchinson',
    'Richard Hardy',
],
    'json': {
    'name': 'Nicholas Turner',
    'address': '87767 Luna Spurs Suite 593\nPort Michellebury, MS 67235',
},
    'key88125': 'value15002',
    'key19804': 'value63126',
    'key42235': 'value42795',
    'key42412': 'value79000',
    'key64821': 'value38163',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Christopher Bowman',
    'address': '23048 Sarah Square Apt. 991\nNorth Douglaston, MA 89103',
    'text': 'Here car allow bad bad. Do clear full stuff.\nSay test color unit school. Model campaign interesting personal decide it remember. And call firm fish chance forget short two.',
    'email': 'castillostephanie@example.net',
    'phone_number': '348.798.5574',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christine Estes',
    'Glenn Hall',
    'Vanessa Watkins',
    'Zachary Wallace',
    'Dylan Hubbard',
    'Steven Wells',
],
    'json': {
    'name': 'Melissa Cortez',
    'address': 'PSC 6753, Box 4220\nAPO AP 54433',
},
    'key51693': 'value30973',
    'key84356': 'value36117',
    'key78381': 'value85510',
    'key54427': 'value50616',
    'key34664': 'value66647',
    'key90385': 'value36495',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Glen Williams',
    'address': '6541 Thomas Turnpike Suite 476\nWest Kirkstad, MA 52848',
    'text': 'Never serious human later. Eat whom agent my sense.\nLong only life someone wish. Himself information manager.',
    'email': 'waltermoore@example.com',
    'phone_number': '472-752-4635x660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Jones',
    'Mr. James Brown',
    'Kristin Ford',
],
    'json': {
    'name': 'Madison Davis',
    'address': '94518 Martinez Alley\nNorth Toddborough, NV 09945',
},
    'key94999': 'value74211',
    'key67460': 'value56171',
    'key22742': 'value74238',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Jorge Yates',
    'address': 'USCGC Miller\nFPO AP 64918',
    'text': 'Glass recognize most order decide I. Military young blue audience song.\nBlack action some order would reality big. Mouth eight meeting score country opportunity community.',
    'email': 'jeremy48@example.org',
    'phone_number': '+1-941-205-1680x2452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Baxter',
    'Dr. John Hammond',
],
    'json': {
    'name': 'Megan Chapman',
    'address': 'USNS Vega\nFPO AP 42965',
},
    'key47866': 'value6207',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Shawn Reeves',
    'address': '015 Makayla Cliffs\nNorth Kennethton, KS 29514',
    'text': 'Movie course safe up large management.\nSeven program region audience firm. House so ok computer return. Meeting region summer miss.\nBreak fast nature house. Season particularly billion past.',
    'email': 'steven34@example.net',
    'phone_number': '(469)228-7783',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Raymond Wolfe',
    'Amy Cisneros',
    'Michael Kelly',
    'Bailey Taylor',
    'Jill Jones',
    'Shannon Gonzalez',
    'Carol Watson',
    'Rachel Dillon',
    'Austin Douglas',
    'Tricia Harrison',
],
    'json': {
    'name': 'Joseph Gutierrez',
    'address': '518 Shane Roads Apt. 829\nNew Douglas, KY 92478',
},
    'key255': 'value76724',
    'key7884': 'value26659',
    'key42035': 'value43738',
    'key85935': 'value18743',
    'key77257': 'value69699',
    'key98594': 'value99044',
    'key82412': 'value41697',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Timothy Garcia',
    'address': '2752 Phillips Station\nOrtizborough, NM 65362',
    'text': 'Right moment huge nearly some at. Instead environment similar else everything often. Allow dog finally after.\nTruth exactly summer good method appear. Hot girl general machine everyone Republican.',
    'email': 'terrelljames@example.org',
    'phone_number': '001-622-862-4267x0033',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Miller',
    'Andrew Herrera',
    'Michael Monroe',
    'David Shepard',
],
    'json': {
    'name': 'Laura Cummings',
    'address': '48294 Pruitt Points\nWilliamsbury, ND 22560',
},
    'key54978': 'value27018',
    'key63579': 'value40216',
    'key93009': 'value34625',
    'key69116': 'value84783',
    'key5901': 'value16152',
    'key22545': 'value93914',
    'key85964': 'value83198',
    'key35742': 'value55666',
    'key6470': 'value6069',
    'key67898': 'value23606',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'John Johnson',
    'address': '3979 Murphy Way Suite 316\nLesliemouth, MT 98508',
    'text': 'Court would hand around understand thing. Feel away develop population compare.\nRun road card arrive ground.\nBrother few age every. Education concern yourself probably development civil.',
    'email': 'alisha00@example.net',
    'phone_number': '584.290.0701',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jason Perry',
    'Norma Mitchell',
    'James Flores',
],
    'json': {
    'name': 'Linda Henderson',
    'address': '3196 Robert Ways\nWebbfort, NJ 49069',
},
    'key31059': 'value41874',
    'key76212': 'value84333',
    'key48167': 'value37522',
    'key64688': 'value92663',
    'key15720': 'value57412',
    'key9394': 'value84977',
    'key68663': 'value85072',
    'key16255': 'value75027',
    'key22687': 'value57259',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Sonya Bennett',
    'address': '0666 Lisa Mews Apt. 675\nPort Julie, NV 53784',
    'text': 'Lose together interesting cause skill. Moment gun case bad camera reveal enter.\nParty either war figure miss building. Strong western color participant pass account.',
    'email': 'kimerin@example.net',
    'phone_number': '229-532-1437x8432',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Bradley Wilkinson',
    'Sharon Baker',
    'Brian Frazier',
    'Timothy Shelton',
],
    'json': {
    'name': 'Jose Lowe',
    'address': '9796 Young Forest Apt. 447\nAshleytown, WA 78394',
},
    'key70735': 'value7849',
    'key88065': 'value95019',
    'key20459': 'value9412',
    'key84251': 'value19289',
    'key33726': 'value39264',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Jennifer Berry',
    'address': '925 John Greens Suite 480\nGarciachester, OR 13506',
    'text': 'Soon well group friend head may wonder.\nSometimes over probably car especially amount heavy. Sometimes woman provide financial popular.',
    'email': 'drusso@example.net',
    'phone_number': '270.584.3815',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Perez',
    'Kristy Turner',
    'Molly Savage',
    'Tracey Page',
    'Vicki Harris',
    'Aaron Elliott',
    'Dustin Lowery',
],
    'json': {
    'name': 'Melanie Clark',
    'address': '75969 Kristen Freeway\nPort Jeanetteview, ME 78436',
},
    'key18315': 'value62320',
    'key53230': 'value18380',
    'key78802': 'value8598',
    'key17385': 'value79397',
    'key21158': 'value84268',
    'key29788': 'value95381',
    'key76641': 'value78888',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Lori Bennett',
    'address': '01164 Haley Haven Apt. 874\nTatechester, DC 27142',
    'text': 'Information else many role know either. Social score bad. After bag dark moment prepare.\nWater attorney course. Still give much film region vote. Strong edge piece officer bank account high.',
    'email': 'kyle16@example.com',
    'phone_number': '665.390.2393x2744',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Lawrence',
    'Lisa Mcdonald',
    'Philip Love',
    'Rodney Henderson',
    'Traci Welch MD',
    'Jamie Spencer',
],
    'json': {
    'name': 'Justin Meyer',
    'address': '5207 Morrison Junction Suite 561\nNorth Donald, MP 46770',
},
    'key12017': 'value27485',
    'key12278': 'value66491',
    'key18229': 'value86875',
    'key4079': 'value24503',
    'key7776': 'value19396',
    'key88476': 'value50700',
    'key48994': 'value79131',
    'key19471': 'value77376',
    'key19850': 'value52901',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Robert Villa',
    'address': 'PSC 1989, Box 1664\nAPO AP 03752',
    'text': 'Visit least simple strong property. Property both plan organization.',
    'email': 'yduran@example.org',
    'phone_number': '7395053905',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Brown',
    'Tina Sweeney',
    'Mallory Mcpherson',
    'Joanna Diaz',
    'Alex Hays',
    'Kara Lamb',
    'Brittany Pacheco',
],
    'json': {
    'name': 'Joshua Ramirez',
    'address': '448 Richard Station Apt. 386\nStephanieview, NY 14123',
},
    'key68296': 'value16080',
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
    'RequestId': '8da395ec-62ef-11f0-b071-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_25_149801wqanANtO',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-1]_1752744146.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl3210011752744146Json()
    test.run_tests()
