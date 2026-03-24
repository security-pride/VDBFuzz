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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-1]_1752744168_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-1]_1752744168.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId12810011752744168Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-1]_1752744168.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-1]_1752744168.json"
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
    'RequestId': '9ad7a744-62ef-11f0-9890-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_47_301352DogZUnDe',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
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
    'RequestId': '9af8e787-62ef-11f0-852f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_47_301352DogZUnDe',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Keith Horne',
    'address': '1940 Schmidt Vista Suite 084\nWilliamstad, MD 45493',
    'text': 'Space attorney they point. Them parent no.\nKind but before sign growth. Everything in when red season marriage. Leave wife population yourself international.',
    'email': 'mary01@example.com',
    'phone_number': '281.210.7228x232',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Villanueva',
    'David Williams',
    'Kelly Campos',
    'William Alexander',
    'Travis Hall',
    'David Park',
    'James Salas',
    'Elizabeth Gomez',
    'Brendan Young',
],
    'json': {
    'name': 'Michael Hawkins',
    'address': '7648 Kristin Glens Apt. 041\nGouldside, SD 94556',
},
    'key23344': 'value24753',
    'key63435': 'value35597',
    'key6561': 'value81131',
    'key66219': 'value83549',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Kayla Butler',
    'address': '90647 Chad Fields\nPort Jenniferstad, WV 24257',
    'text': 'Area personal water foot cut ten account. Training daughter maintain same write. Quality control current value.',
    'email': 'whitejason@example.com',
    'phone_number': '482-352-7995',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Jackson',
    'William Bolton',
    'Elizabeth Smith',
],
    'json': {
    'name': 'Walter Ferguson',
    'address': '508 Baker Gateway\nLeebury, KY 25349',
},
    'key53571': 'value5967',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Judith Reed',
    'address': '88156 Lauren Junction Suite 763\nNew Anthonyview, NH 71531',
    'text': 'Hope term born stage. Year about remain three nature.\nFloor none camera employee civil us though. Trouble find safe.',
    'email': 'rossstacy@example.org',
    'phone_number': '323.207.7255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Eric Owens',
    'Kimberly Harris',
    'John Williams',
],
    'json': {
    'name': 'Keith Gonzales',
    'address': '375 Andrew Avenue\nSydneymouth, ND 06931',
},
    'key80901': 'value57',
    'key6960': 'value44067',
    'key3176': 'value90212',
    'key97946': 'value52002',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Madison Carter',
    'address': '4859 Joshua Keys\nEast Brittanyberg, FL 28142',
    'text': 'Miss seven my modern federal strategy score. Perhaps too answer maybe.',
    'email': 'holly39@example.org',
    'phone_number': '001-971-499-5309x2001',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Pratt',
    'Michael Oneill',
    'Christina Wong',
    'Daniel Thomas',
    'Mary Ray',
    'Benjamin Williams',
],
    'json': {
    'name': 'Kenneth Johnson',
    'address': '8819 Velez Bridge\nPort Ana, MT 19841',
},
    'key79624': 'value31303',
    'key58292': 'value73885',
    'key34641': 'value4264',
    'key68025': 'value63641',
    'key84418': 'value31421',
    'key31688': 'value9373',
    'key36182': 'value56104',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Brandon Williams',
    'address': '243 Anthony Burg\nWest Tylerhaven, OK 10288',
    'text': 'Safe sell relate cause wrong miss. Worry vote sea something. Seat quality scientist miss yard politics support point.',
    'email': 'kimberlysummers@example.net',
    'phone_number': '(925)204-4293',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Gardner',
    'Amanda Roberson',
    'Valerie Clark',
    'Dylan Nguyen',
    'Jeremiah James',
    'Joshua Ali',
    'Tom Barrera',
    'Abigail Holder',
],
    'json': {
    'name': 'Alexander Campbell',
    'address': '341 Justin Isle Apt. 921\nEast Javierbury, VI 55997',
},
    'key99995': 'value43277',
    'key77404': 'value93678',
    'key21781': 'value68538',
    'key46855': 'value50016',
    'key96466': 'value2023',
    'key3010': 'value29988',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Mr. Kevin Casey',
    'address': '9377 Mullins Key\nGreenberg, DE 47221',
    'text': 'Note yes consumer I. Become really blue guy control bit by.\nPage order special watch medical. Spend surface year agent laugh behind short. Recent spring major within.',
    'email': 'johnsontimothy@example.com',
    'phone_number': '528-922-9187',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Donna Kramer',
    'Brittany Riley',
    'Laura Hood',
    'Victoria Thomas',
    'Gina Wallace',
],
    'json': {
    'name': 'James Harris',
    'address': '3069 Glenn Passage Suite 879\nHansenchester, AZ 82440',
},
    'key90258': 'value93470',
    'key57668': 'value8905',
    'key51480': 'value61198',
    'key8610': 'value27045',
    'key12309': 'value76100',
    'key71648': 'value39816',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Elizabeth Petty',
    'address': '44732 Garza Avenue Suite 928\nAdrianburgh, OH 41752',
    'text': 'Sense join fast child happy. Fact employee realize eye. Deal design industry choice. Law nature three end commercial blood effect.',
    'email': 'nharrison@example.org',
    'phone_number': '+1-300-415-8730x752',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Hughes',
    'Grace Baldwin',
    'Caroline Wheeler',
    'Darryl Long',
    'Aaron Jones',
    'Nicholas Hunter',
    'Dylan Jackson',
],
    'json': {
    'name': 'Beth Freeman',
    'address': '728 Michael Garden\nVargasbury, AL 46768',
},
    'key79774': 'value76560',
    'key1928': 'value40245',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Erik Mejia',
    'address': 'Unit 4822 Box 2871\nDPO AE 48142',
    'text': 'Window scientist buy cup tonight mention.\nDecade into trouble their throw tough determine short. Recently among hospital throw among beyond feel feel.',
    'email': 'whenderson@example.net',
    'phone_number': '563-712-9692x7896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sylvia Wilson',
    'Sharon Torres',
    'Donna Hawkins',
],
    'json': {
    'name': 'Austin Stephens',
    'address': '492 Alexander Bridge Apt. 031\nJesseberg, SC 20402',
},
    'key42462': 'value53056',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Kevin Griffin',
    'address': 'PSC 6485, Box 5001\nAPO AE 62495',
    'text': 'Run future pay be begin. Cell movement unit population identify loss sing.\nDo base best. Economy company which.\nExist class executive vote. Final get skin second same ten whatever boy.',
    'email': 'david34@example.net',
    'phone_number': '(644)951-0949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Love MD',
    'Jesse Townsend',
    'Daniel Smith',
],
    'json': {
    'name': 'Andrea Reynolds',
    'address': 'USS York\nFPO AA 49369',
},
    'key17836': 'value9138',
    'key70579': 'value89517',
    'key98830': 'value28682',
    'key27050': 'value29697',
    'key84013': 'value77251',
    'key62933': 'value11222',
    'key49988': 'value5853',
    'key3466': 'value51124',
    'key94994': 'value44061',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Sean Smith',
    'address': '08174 Vanessa Village\nWest Charlesmouth, GU 20737',
    'text': 'If draw forward simple power build. Coach fight area message. Within street list far.\nCountry let goal college exist really. Want single health blue get million.',
    'email': 'williamsoncorey@example.org',
    'phone_number': '586.791.0956x31899',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Andre Parks',
    'Dr. Amy Wyatt',
    'Timothy Morgan',
    'Amy Johnston',
    'Steven Jones',
    'Aaron Newton',
    'Lisa Davis',
    'Darren Odonnell Jr.',
    'Jennifer Blevins',
    'David Figueroa',
],
    'json': {
    'name': 'Perry Cruz',
    'address': '7449 Veronica Orchard Suite 929\nWendyhaven, TX 98552',
},
    'key2140': 'value44980',
    'key76038': 'value9452',
    'key42476': 'value37902',
    'key22874': 'value60029',
    'key91739': 'value98417',
    'key18541': 'value97405',
    'key30617': 'value80718',
    'key47942': 'value71666',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Anna Lopez',
    'address': '159 Stanton Falls\nPierceside, GU 83936',
    'text': 'Material forward staff statement television produce. Down image summer meeting.\nRock peace position range key start can. Seat perhaps standard do stop.',
    'email': 'charleshamilton@example.net',
    'phone_number': '667-941-3305',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Larry Phelps',
    'Dorothy Adams DDS',
    'Jose Miller',
    'Heather Khan',
    'Miss Kayla Allison',
    'Timothy Patterson',
    'Henry Griffith',
],
    'json': {
    'name': 'Mr. Keith Davidson',
    'address': '70313 Michael Harbor\nPort Laceyview, NM 14543',
},
    'key55113': 'value14595',
    'key86785': 'value37127',
    'key4009': 'value82350',
    'key21000': 'value49363',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Christopher Mann',
    'address': 'USS Fox\nFPO AP 56445',
    'text': 'As something modern purpose stock bit happy. Defense parent any write.\nSoon detail late he yes. Simply three probably effect.',
    'email': 'erica68@example.net',
    'phone_number': '(770)846-7796x4193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Denise Guzman',
    'April Bishop',
],
    'json': {
    'name': 'Shawn Brewer',
    'address': '1339 Sharon Trafficway Apt. 425\nPort Jennifer, ND 08669',
},
    'key45273': 'value47485',
    'key37195': 'value63631',
    'key3983': 'value35824',
    'key81746': 'value74557',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Lori Edwards',
    'address': '5562 Jerry Club\nPort April, MO 30645',
    'text': 'Media somebody population act state condition stay. Worry activity action or each key feel.\nWide ready ahead benefit. Option draw mission state number.',
    'email': 'sbautista@example.com',
    'phone_number': '2883605628',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Cristian Ortega',
    'David Flynn',
],
    'json': {
    'name': 'Corey Moody',
    'address': 'USS Carter\nFPO AA 70177',
},
    'key13424': 'value9595',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Nathan White',
    'address': '943 Charles Pine Apt. 643\nWest Daisy, NV 03311',
    'text': 'Official me attention after interview. Seat might establish he history fear.',
    'email': 'carriejones@example.net',
    'phone_number': '831-634-3073',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Logan Chapman',
    'Linda Marshall',
    'Rachel Parrish',
    'Austin Hubbard',
    'Joseph Norris',
    'Anna Lang DVM',
    'Brian Murphy',
],
    'json': {
    'name': 'Brandon Martinez',
    'address': '71635 Carolyn Fields Suite 294\nEast Jeffrey, WY 52471',
},
    'key84485': 'value55584',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Teresa Barron',
    'address': '5480 Paul Freeway Suite 409\nKathleenview, WI 36709',
    'text': 'Economy cause product white have stand offer. Leave sister situation evening development serve. People learn minute traditional nor sign tree.',
    'email': 'ajohnson@example.com',
    'phone_number': '(440)811-8565',
    'array_int_dynamic': [
    69864,
],
    'array_varchar_dynamic': [
    'Frank Hartman',
    'Brandon Martin',
    'Lindsey Carter',
    'Mandy Dean',
    'Michael Pham',
    'Jeff Valdez',
    'Leah Wells',
],
    'json': {
    'name': 'Lisa Sanders',
    'address': '0351 Cynthia Row Apt. 285\nAmyshire, CA 59775',
},
    'key11192': 'value8011',
    'key70168': 'value25350',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Chad Hoffman',
    'address': '732 Berry Circles Apt. 351\nSarahburgh, ND 50662',
    'text': 'Nothing perform without follow marriage. Sport laugh away small. Grow sport himself mind.',
    'email': 'elliskimberly@example.net',
    'phone_number': '378.730.5515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Turner',
    'Veronica Browning',
    'James Farrell',
    'David Barnett',
    'Erin Sellers',
    'Angela Santiago',
    'Kayla Villegas',
    'Brad Hanson',
    'Kenneth Mays',
],
    'json': {
    'name': 'Cassandra Hicks',
    'address': '2349 Daniel Cape\nSloanfurt, FL 33901',
},
    'key36196': 'value93895',
    'key88385': 'value91485',
    'key54555': 'value99636',
    'key70762': 'value71613',
    'key14163': 'value75186',
    'key97909': 'value28252',
    'key20903': 'value31011',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'William Robertson',
    'address': '95785 Ramos Station\nEast Jenniferton, MS 03919',
    'text': 'Season though system clearly alone work drug. Different nor think course.\nFor husband effort cut. Attack from serve space away edge it.',
    'email': 'elizabeth12@example.net',
    'phone_number': '+1-921-302-5296x7191',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alex Cain',
    'Teresa Foster',
],
    'json': {
    'name': 'Kimberly Johnson',
    'address': '901 Harry River\nSouth Marcusstad, AR 68596',
},
    'key83636': 'value69842',
    'key8667': 'value95546',
    'key63349': 'value37639',
    'key84065': 'value63612',
    'key49471': 'value49585',
    'key25754': 'value3708',
    'key46034': 'value68452',
    'key75234': 'value72005',
    'key17649': 'value78733',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Mr. Joseph Bridges',
    'address': '781 Martinez Pine\nParsonstown, FL 62861',
    'text': 'Red leader become good ahead. Year loss teacher dark song toward account. Price hot world newspaper foreign his growth.\nAddress mean mission agent.',
    'email': 'fnguyen@example.com',
    'phone_number': '809-504-6492x8570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Carr',
    'Eric Edwards',
    'Kevin Sanders',
    'Barbara Evans',
],
    'json': {
    'name': 'Diane Hansen',
    'address': '4576 David Center\nDavidbury, KY 18216',
},
    'key91026': 'value16083',
    'key60955': 'value30513',
    'key17387': 'value79443',
    'key12258': 'value3353',
    'key85704': 'value31667',
    'key93700': 'value38745',
    'key91698': 'value86331',
    'key63895': 'value74916',
    'key69688': 'value95953',
    'key61737': 'value8757',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Christopher Jennings',
    'address': '553 Johnson Shoal Suite 491\nMalloryview, LA 74049',
    'text': 'Call during wait it voice. Hear cut identify or. Article follow oil green least environmental plant.\nParent else or where ten be. Since little thousand.',
    'email': 'ericglass@example.org',
    'phone_number': '513.203.1094x399',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dominique Watson',
    'David Hernandez',
    'Jessica Robinson',
    'Robert Eaton',
    'David Stephenson',
],
    'json': {
    'name': 'Robin Nelson',
    'address': '16228 Aguilar Roads Apt. 765\nNorth Melissatown, LA 52674',
},
    'key87712': 'value49589',
    'key13689': 'value43678',
    'key87622': 'value99127',
    'key42022': 'value40682',
    'key16637': 'value77073',
    'key67962': 'value64768',
    'key28925': 'value40792',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Daniel Peterson',
    'address': '72739 Johnson Terrace Suite 065\nNorth Allenton, MS 21650',
    'text': 'Former indeed door financial. Blood poor apply put or toward call. Republican notice sometimes.\nDrug which catch. Might realize subject concern fly.',
    'email': 'scottarias@example.net',
    'phone_number': '289.292.5398',
    'array_int_dynamic': [
    9276,
],
    'array_varchar_dynamic': [
    'Robert Johnson',
    'Whitney Wells',
    'Michelle Murphy',
    'Daniel Smith',
    'Marisa Nguyen',
],
    'json': {
    'name': 'Timothy Lucas',
    'address': '548 Roberts Ranch\nPort Randy, AR 93462',
},
    'key10145': 'value28497',
    'key38438': 'value69219',
    'key34161': 'value88025',
    'key33457': 'value51697',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Julie Morris',
    'address': '8294 Charles Burg Apt. 220\nAtkinsonview, WI 96501',
    'text': 'Time his about off value time expect. Build now system before difficult message fill. These say product six similar sing artist.',
    'email': 'susanhumphrey@example.net',
    'phone_number': '2114723897',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Newton',
    'Amber Williams',
    'Mary Guerrero',
    'Daniel Martinez',
    'Brandon Day',
],
    'json': {
    'name': 'Ann Terry',
    'address': '803 Chase Mission\nEast Paul, NV 51980',
},
    'key75789': 'value64670',
    'key54260': 'value89740',
    'key54670': 'value27605',
    'key54583': 'value26117',
    'key75480': 'value76152',
    'key10931': 'value47944',
    'key45381': 'value32435',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Christina Reyes',
    'address': '24417 Mullins Branch Apt. 670\nRandolphshire, KY 69757',
    'text': 'Rest cut finish executive source. Bring analysis entire firm cultural respond bank whatever. Whatever majority others guy cover there.',
    'email': 'rosechristina@example.com',
    'phone_number': '(593)945-3816x6100',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Foster',
    'William Taylor',
    'Amanda Hoffman',
    'Christopher Peters',
    'Sabrina Hines',
    'Joel Gardner',
    'James Johnson Jr.',
    'Harry Harmon',
    'Jasmine Rogers',
    'Stephen Camacho',
],
    'json': {
    'name': 'Robert Wagner',
    'address': 'PSC 6380, Box 0000\nAPO AA 59985',
},
    'key60559': 'value80400',
    'key94112': 'value65368',
    'key34172': 'value9872',
    'key52414': 'value37023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Adrian Howe',
    'address': '76573 Scott Gateway Suite 110\nLake Lindaborough, VT 99149',
    'text': 'Dark four traditional image inside better. Next cell body single politics exist hair.',
    'email': 'christopher54@example.org',
    'phone_number': '700-372-7349x49154',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Heather Foster',
    'Dale Mitchell',
    'Sarah Rojas',
    'Fernando Valencia',
],
    'json': {
    'name': 'Stacey Yates',
    'address': '11963 Abigail Alley\nRebeccaport, OH 02369',
},
    'key29090': 'value52426',
    'key12589': 'value63059',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Diana Jones',
    'address': 'USNS Harris\nFPO AE 28601',
    'text': 'Young likely special election night beautiful wind. Here summer ground stuff well participant. Better lay true investment crime would.\nShort thousand military.',
    'email': 'jenniferrivera@example.com',
    'phone_number': '001-393-563-2861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Schneider',
    'Sydney Frank',
    'Leah Donaldson',
    'Trevor Golden',
],
    'json': {
    'name': 'David Castaneda',
    'address': '27412 Kayla Crossing\nOlsonland, MI 21599',
},
    'key53545': 'value76166',
    'key99323': 'value76270',
    'key91423': 'value1745',
    'key78945': 'value87002',
    'key7357': 'value29571',
    'key55462': 'value97163',
    'key37903': 'value80024',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'David Reynolds',
    'address': '20680 Pamela Extension\nEast Jennifer, PW 00719',
    'text': 'Accept scene key unit skin central heart. Hand effect us himself.\nReport major agency difficult central. Son treatment popular police oil agent example.',
    'email': 'christopher53@example.com',
    'phone_number': '+1-473-772-3906x92538',
    'array_int_dynamic': [
    40541,
],
    'array_varchar_dynamic': [
    'Ruben Snow',
    'Bradley Perry',
    'John Morris',
    'Phillip Hernandez',
],
    'json': {
    'name': 'Nicole Mccullough',
    'address': '1211 Christopher Run\nNorth Patriciahaven, SD 25213',
},
    'key88625': 'value28109',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'John Conner',
    'address': '803 Lewis Oval\nLuisfurt, TX 04957',
    'text': 'Later soldier model for affect sing. Itself policy almost billion space let. Position door hope argue rate.\nDown page else land write big type. Occur public consumer another crime.',
    'email': 'hamiltonthomas@example.net',
    'phone_number': '997.656.3160x967',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Villarreal',
    'Patrick Rogers',
    'James Bailey',
    'Jonathan Williams',
    'Brittany Parker',
    'Brittany Harris',
    'Anthony Garcia',
    'Ray Wallace',
    'Lisa Jones',
    'Sylvia Peterson',
],
    'json': {
    'name': 'Kelly Edwards',
    'address': '1262 Anthony Greens Suite 681\nEast Karenburgh, MH 50683',
},
    'key86235': 'value43009',
    'key46814': 'value92130',
    'key24157': 'value28686',
    'key81097': 'value26645',
    'key14916': 'value14702',
    'key53729': 'value15595',
    'key66775': 'value27594',
    'key41920': 'value19132',
    'key2909': 'value2669',
    'key68451': 'value95606',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Elizabeth Cordova',
    'address': '1719 Jessica Squares Suite 075\nAnthonyborough, PR 61601',
    'text': 'Appear work manage religious present. Nor different hotel year fish important see discuss.',
    'email': 'alexismorrow@example.com',
    'phone_number': '001-842-591-2664x13473',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew White',
    'Cassidy Huff',
    'Laura Gonzalez',
    'Melissa Chavez',
    'Barbara Mann',
],
    'json': {
    'name': 'Paul Anderson',
    'address': '35726 Christopher Prairie\nDorothyborough, MP 79601',
},
    'key26131': 'value89223',
    'key35786': 'value44381',
    'key90603': 'value19661',
    'key86908': 'value86693',
    'key80101': 'value6903',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Nicholas Boyle',
    'address': '3543 Jones Parks\nNorth Ryanberg, WY 74003',
    'text': 'Than long task probably report campaign. Everyone official establish worker.\nEdge minute out during order. Agreement style reveal small check.',
    'email': 'ggarner@example.net',
    'phone_number': '(935)295-0977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sydney Ingram',
    'James Rogers',
    'Nicole George',
    'Tina Singh',
    'Tracy Mclean DDS',
    'Jennifer Hampton',
    'Edward Ferguson',
],
    'json': {
    'name': 'Arthur Espinoza',
    'address': 'Unit 4074 Box 9772\nDPO AE 67320',
},
    'key77680': 'value56319',
    'key47392': 'value59337',
    'key87902': 'value52713',
    'key40201': 'value83033',
    'key37475': 'value69073',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'John Conner',
    'address': '02195 Jessica Mountains Suite 480\nJennifershire, MD 59192',
    'text': 'Would physical or both prepare really paper. Change begin effort action.\nStrong including good point argue usually college. Apply project baby pass nature.',
    'email': 'ivangill@example.org',
    'phone_number': '001-389-531-4719x76112',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Hayden Olsen',
    'Luke Bernard',
    'Joseph Smith Jr.',
    'Edward Brown',
    'Christopher Parrish',
    'Jessica Hanson',
    'Makayla Lopez',
    'James Nichols',
    'Paul Reed',
    'Kevin Turner',
],
    'json': {
    'name': 'Alexandra Ramos',
    'address': '5893 John Estates Apt. 380\nChambersfort, AS 50767',
},
    'key18507': 'value62730',
    'key90058': 'value3403',
    'key98241': 'value23048',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Dennis Meadows',
    'address': '1375 Brown Viaduct\nLake Elizabeth, AL 90890',
    'text': 'Low discuss heavy there. Travel test claim same produce building. Third top better science.\nNote water positive as. Claim himself industry matter enjoy building. Style economy we face draw some.',
    'email': 'cgarza@example.net',
    'phone_number': '+1-372-567-6800x494',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Harris',
    'Nicole David',
    'Anthony Lee',
    'Brenda Freeman',
    'Mr. Christopher Gross',
],
    'json': {
    'name': 'Kevin Montgomery',
    'address': '87497 Price Neck\nSouth Philipberg, NV 13182',
},
    'key99084': 'value15935',
    'key10400': 'value29762',
    'key51607': 'value19184',
    'key76196': 'value62719',
    'key99480': 'value95483',
    'key51671': 'value34586',
    'key92703': 'value80495',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Marcus Clarke',
    'address': '7132 Bowers Squares Apt. 989\nNew Patricia, WI 63647',
    'text': 'Century now though already quite two feel each. Movie whom life. Federal style responsibility oil admit parent first.',
    'email': 'smithkaitlyn@example.net',
    'phone_number': '001-469-526-5874x605',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jason Bird',
    'Yesenia Lane',
    'Sarah Cole',
    'Frank Ellison',
    'Mrs. Sarah Rivas MD',
    'Jessica Mitchell',
    'Mitchell Hill',
    'Eugene Best',
],
    'json': {
    'name': 'Lisa Ramos',
    'address': '382 Scott Land Apt. 921\nJenniferfurt, AL 23453',
},
    'key83170': 'value57137',
    'key36043': 'value55701',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Cory Pierce',
    'address': '418 Patrick Drive Suite 037\nLake Jeremytown, MI 77538',
    'text': 'Possible stand TV Mr. Case take admit gas final allow big. On space hit several interesting agency pressure. Different meet art attention source.\nNearly value several too. Until skin exactly.',
    'email': 'edwardsevan@example.net',
    'phone_number': '+1-986-425-5374x9871',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Phillip Jensen',
    'Ashley Rivera',
    'Julian Stewart',
    'Mr. Matthew Howell',
    'Christine Harmon',
    'Michael Patton',
    'Ryan Humphrey',
    'Mary Alvarado',
    'Brittany Hart',
],
    'json': {
    'name': 'John Obrien',
    'address': '4669 Cheryl Pass Apt. 923\nHumphreyborough, MA 66890',
},
    'key78749': 'value30045',
    'key30477': 'value25483',
    'key55665': 'value6180',
    'key36225': 'value57283',
    'key53172': 'value9042',
    'key5618': 'value26228',
    'key26899': 'value3295',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Zachary King',
    'address': '08051 Adkins Springs Apt. 287\nChristophermouth, ID 75550',
    'text': 'Month after want free. Company road yet. Let far prepare detail feel section.',
    'email': 'juliekelley@example.org',
    'phone_number': '399-405-2779x025',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Hoffman',
    'Mr. Timothy Rubio',
    'Eric Jackson',
    'Rebecca Jimenez',
    'Hannah Richardson',
    'Elizabeth Aguilar',
    'Daniel Carr',
    'Shelly Walker',
    'Ryan Marks',
],
    'json': {
    'name': 'Jennifer Bradford',
    'address': '338 Janet Heights Suite 502\nWest Sharistad, MD 63056',
},
    'key52805': 'value42693',
    'key42226': 'value54475',
    'key38005': 'value74866',
    'key58135': 'value66156',
    'key46775': 'value73108',
    'key80521': 'value37938',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michael Hopkins',
    'address': '1856 Carol Passage\nWest Aaron, NY 58197',
    'text': 'Ask short create clear car. More receive card stage author. Truth indeed ahead education available tough.',
    'email': 'froth@example.com',
    'phone_number': '269-323-7962x77962',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Trevor Howard',
    'Gina Garza',
    'Heather Rice',
],
    'json': {
    'name': 'Matthew Wright',
    'address': '5979 Caldwell Viaduct\nConnorton, KY 62971',
},
    'key68304': 'value58071',
    'key62642': 'value97269',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Wendy Reynolds',
    'address': '55893 Danielle Mill\nRachelport, VI 33530',
    'text': 'Simple even apply agreement learn recently. Myself since production use environmental customer stand.',
    'email': 'brandonpotts@example.org',
    'phone_number': '431.945.9354x9493',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Rodriguez',
    'Kelsey Mooney',
    'Robin Martin',
    'Justin Wagner',
],
    'json': {
    'name': 'Stephanie Hall',
    'address': '7946 Carter Stream Suite 160\nWest Rebeccashire, PA 49404',
},
    'key51638': 'value94962',
    'key91417': 'value57852',
    'key84044': 'value84234',
    'key39445': 'value71765',
    'key10150': 'value1150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Kathy Sutton',
    'address': '42027 Caldwell Mill Suite 781\nWest Theresahaven, ID 50069',
    'text': 'Believe protect deal entire reflect. Foot last next time finally century. Sometimes process amount management sing ability star.',
    'email': 'jeffrey65@example.com',
    'phone_number': '315-847-8449x8257',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Maria Kirk',
],
    'json': {
    'name': 'Adam Henderson',
    'address': '435 Stafford Inlet Apt. 993\nNorth Jamesside, MP 13539',
},
    'key30464': 'value35325',
    'key11846': 'value91174',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Tara Kim',
    'address': '412 James Lodge\nSouth Jonathon, DE 36736',
    'text': 'Hour yeah call shake hold mean environment. Those less rule level if before would.\nShoulder various just production inside light kind. Concern whatever seem fine type onto.',
    'email': 'johnmorton@example.com',
    'phone_number': '001-880-982-2677x40183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Sherri Diaz',
    'Steven Salazar',
    'Anna Wilkinson',
    'Tyler Miller',
    'Amanda Hudson',
    'Karen Lopez',
    'Terry Long',
    'Michael Casey',
],
    'json': {
    'name': 'Anthony Jensen',
    'address': '182 Malone Stravenue\nLake Nathanielfort, ID 45417',
},
    'key88972': 'value92414',
    'key97073': 'value88342',
    'key34123': 'value39755',
    'key51047': 'value13839',
    'key19213': 'value73844',
    'key6111': 'value16795',
    'key16207': 'value43341',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Debra Harris',
    'address': '66523 Rodriguez Points Apt. 126\nWest Patrick, MA 65551',
    'text': 'Her deal teacher. Second remember answer occur.\nDefense cause test section truth hair wall. Court memory pressure stuff after sit court. Kid per whole plant dog itself loss.',
    'email': 'vmartin@example.org',
    'phone_number': '955.484.0037',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'David Moran',
    'Arthur Cole',
    'James Orozco',
    'Christina Vasquez',
    'Matthew Mays',
    'Eric Johnson',
    'Tammy Rivera',
    'Amanda Yates',
    'Jessica Cole',
    'Amber Benitez',
],
    'json': {
    'name': 'Jessica Ramos',
    'address': '20340 Reyes Land Apt. 437\nBobbychester, MI 22501',
},
    'key72527': 'value62699',
    'key61174': 'value94154',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Isaac Walker',
    'address': '428 Smith Row Suite 241\nSouth Sabrina, MT 48236',
    'text': 'Care rule clearly whatever speak about. Century put top chance kitchen bring. Water feel heart on mean support.\nRespond box memory later group site firm. Daughter rate offer thing include.',
    'email': 'edwardsmalik@example.com',
    'phone_number': '433-680-1623x8227',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Melinda Medina',
    'Amanda Johnston',
    'Lisa Taylor',
    'Joanna Jones',
    'Penny Nelson',
    'Summer Marshall',
],
    'json': {
    'name': 'Brett Kennedy',
    'address': '737 Larson Burgs\nPort Andrew, KS 26524',
},
    'key63793': 'value46479',
    'key46746': 'value34612',
    'key98231': 'value48992',
    'key19382': 'value13517',
    'key97008': 'value66373',
    'key27266': 'value44296',
    'key58186': 'value13904',
    'key35841': 'value42355',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Christopher Barnett',
    'address': '0227 Stephanie Court Suite 836\nJamesmouth, PA 59128',
    'text': 'Face once television treatment. Man bed true public push operation bad after. Crime perhaps stuff live.\nService list town miss serious. Argue work big management.',
    'email': 'david48@example.com',
    'phone_number': '+1-583-708-7149x163',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Harris',
    'James Anderson',
    'Kathleen Huber',
],
    'json': {
    'name': 'Kenneth Lloyd',
    'address': '611 Kelly Road\nMarthaside, NV 61793',
},
    'key56070': 'value94070',
    'key59283': 'value47037',
    'key67348': 'value62113',
    'key77762': 'value51632',
    'key66295': 'value57784',
    'key57253': 'value8157',
    'key87357': 'value59882',
    'key13391': 'value78585',
    'key74336': 'value75330',
    'key65743': 'value55182',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Thomas Lynch',
    'address': '871 Brown Harbor\nNew Omar, WA 71328',
    'text': 'Carry away positive rock finally. Stuff necessary rate how type myself interview. Safe marriage usually finally strategy night thing.',
    'email': 'larrybrown@example.net',
    'phone_number': '(726)824-6043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Brown',
    'Scott Howard',
    'Maurice Henderson',
    'Joshua Smith',
    'Cynthia Vargas',
    'Joshua Farley',
    'Kathy Morse',
    'Tracy Reese',
    'Nicole Martin',
    'Tamara Perez',
],
    'json': {
    'name': 'Gregory Williams',
    'address': 'PSC 5190, Box 7657\nAPO AE 81862',
},
    'key59611': 'value93533',
    'key59882': 'value23168',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Veronica Williams',
    'address': '8409 Raymond Courts\nPort Michael, WV 86486',
    'text': 'Example my person drop skin every relate.\nLate scientist why because article other science. Seem have debate material matter yourself.\nRead fish attack effect. Either song few suggest.',
    'email': 'pamelamacdonald@example.org',
    'phone_number': '(943)438-3237',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Leonard',
    'Kevin Dunn',
    'Carl Nelson',
    'Jonathan Fox',
    'James Wilson',
    'Julie Oliver',
    'April Nelson',
    'Jennifer Patterson',
    'Andrea Long',
],
    'json': {
    'name': 'Elizabeth Shea',
    'address': '719 Young Junction Apt. 892\nKrausefurt, PA 21637',
},
    'key97156': 'value11798',
    'key77487': 'value25229',
    'key19092': 'value17778',
    'key16614': 'value9573',
    'key72900': 'value24147',
    'key73720': 'value82791',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Bethany Wilson',
    'address': '7920 Smith Dam Suite 350\nPort Karenbury, WY 01150',
    'text': 'Receive direction yeah. Ahead former factor language.\nTogether describe allow. A successful carry air apply. Stock benefit even center how reason arrive.',
    'email': 'crawfordmichael@example.org',
    'phone_number': '4063424876',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christy Terry',
    'Jesse Turner',
    'Troy Ewing',
    'Carolyn Mason',
    'Tommy Bullock',
    'Kristen Velasquez',
    'Tracy Mckenzie',
    'Kelly Butler',
],
    'json': {
    'name': 'Candice Turner',
    'address': '4973 Mejia Ferry Suite 319\nGlennland, MS 38592',
},
    'key12064': 'value89388',
    'key12523': 'value7509',
    'key95244': 'value9992',
    'key28616': 'value61488',
    'key51756': 'value69702',
    'key95617': 'value45048',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Krista Morales',
    'address': '95342 Vazquez Course\nEast Kenneth, KY 07465',
    'text': 'Knowledge cell fact movie story. Per a push various lawyer laugh president risk.\nGoal remain herself vote chance. Hard rule firm win close. Note beyond us fine computer. Create young from.',
    'email': 'unewman@example.net',
    'phone_number': '(425)626-1785',
    'array_int_dynamic': [
    53470,
],
    'array_varchar_dynamic': [
    'Mark Fields',
    'Cody Tucker',
],
    'json': {
    'name': 'Christina Walker',
    'address': '86741 White Landing Suite 596\nAshleyborough, KS 41779',
},
    'key57233': 'value9038',
    'key41063': 'value43062',
    'key12110': 'value81464',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Ryan Williams',
    'address': '9498 Rose Brooks\nMitchellburgh, MP 35620',
    'text': 'Tough cup list degree. Race attorney war leave former cell suffer. Oil middle show relationship.',
    'email': 'kevin88@example.net',
    'phone_number': '831-736-7378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Barnes',
    'Amy Edwards',
    'Robert Carter',
    'William Parker',
    'Brian Powell',
    'Nichole Coleman',
    'Ryan Anderson',
    'Samuel Jacobs',
    'Carl Garcia',
],
    'json': {
    'name': 'Jennifer Contreras',
    'address': 'Unit 3365 Box 5261\nDPO AE 02296',
},
    'key89088': 'value69003',
    'key90329': 'value3958',
    'key56487': 'value31869',
    'key66296': 'value80360',
    'key17226': 'value20774',
    'key5996': 'value87393',
    'key25626': 'value4829',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Danny Carroll',
    'address': '3916 Kristina Summit Apt. 264\nPort Shaun, WI 05187',
    'text': 'Standard man down field let assume. Institution especially son month conference offer recognize production. Lay series north voice.',
    'email': 'emilyjackson@example.org',
    'phone_number': '909-811-0605x702',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Gross',
    'Anne Dixon',
    'Jason Jones',
    'Gina Lopez',
],
    'json': {
    'name': 'Whitney Spencer',
    'address': '027 Alexandria Inlet Apt. 076\nHaleville, MA 84221',
},
    'key80451': 'value71651',
    'key65012': 'value14839',
    'key34602': 'value92295',
    'key45599': 'value97899',
    'key80439': 'value83167',
    'key29295': 'value61981',
    'key52874': 'value33683',
    'key9301': 'value21956',
    'key21937': 'value57603',
    'key40489': 'value43252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Mary Smith',
    'address': '5688 Kim Mountain Suite 420\nJamesfurt, RI 80515',
    'text': 'It account reveal perform seven but but magazine. History green idea. Themselves type effect seven attorney.\nAnd organization visit source listen. There quickly first get.',
    'email': 'zlee@example.net',
    'phone_number': '001-623-643-8020',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Debra Reyes',
    'Alex Hall',
    'Tammie Mclaughlin',
    'Dana Maldonado',
],
    'json': {
    'name': 'Lori Zamora',
    'address': '3706 Dustin Radial Apt. 288\nDianafurt, UT 64886',
},
    'key97877': 'value57236',
    'key23782': 'value17890',
    'key66039': 'value26077',
    'key78949': 'value87760',
    'key74573': 'value57938',
    'key45891': 'value30827',
    'key83559': 'value55464',
    'key55246': 'value89681',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Brandon Butler',
    'address': '3831 Shelly Orchard Apt. 837\nLake Gregory, AK 40518',
    'text': 'Herself research us operation social growth all.',
    'email': 'jenningsterry@example.org',
    'phone_number': '(353)612-2371',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brooke Cortez',
    'Emma Baxter',
    'Elizabeth Edwards',
],
    'json': {
    'name': 'Tonya Henry',
    'address': '51935 Stein Land Apt. 203\nYorkland, NH 34973',
},
    'key89078': 'value75954',
    'key34005': 'value48041',
    'key19351': 'value18741',
    'key2016': 'value4069',
    'key70264': 'value51865',
    'key3597': 'value11585',
    'key81074': 'value95585',
    'key52855': 'value50507',
    'key64838': 'value57242',
    'key50112': 'value95894',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Deborah Alvarado',
    'address': '6866 Donna Flats\nJonesburgh, AZ 49434',
    'text': 'Again performance government. Kid miss wrong pretty tend.\nFinally senior effect staff produce. News rule decide economy research piece practice.',
    'email': 'ramirezzachary@example.org',
    'phone_number': '880.495.1802x841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gabriel Craig',
    'Robert Long',
    'Kathryn Woods',
    'Nicole Johnson',
    'Jessica Gonzalez',
    'Marc Lang',
    'Kimberly Love',
],
    'json': {
    'name': 'Kelli Allen',
    'address': '45214 Porter Hollow\nMichaelmouth, PR 88858',
},
    'key17751': 'value19778',
    'key85057': 'value46157',
    'key80121': 'value50841',
    'key12831': 'value87871',
    'key68622': 'value44742',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Ryan Castro',
    'address': '17430 Joseph Tunnel\nBryantton, TX 90526',
    'text': 'Military even think care. Everyone eight guy particular. Also threat three realize.\nLate be power thought. Prevent indicate baby morning. House ahead wide cause.',
    'email': 'ericaneal@example.net',
    'phone_number': '001-593-374-1940x05570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Cook',
    'Tonya Sutton',
    'Thomas Guerrero',
    'Thomas Cruz',
],
    'json': {
    'name': 'Joel Jenkins',
    'address': '2370 Trevor Common\nNew Scottbury, MS 54016',
},
    'key58167': 'value60571',
    'key97250': 'value17126',
    'key95094': 'value65051',
    'key77522': 'value96802',
    'key44343': 'value94347',
    'key1546': 'value95664',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Bradley Martinez',
    'address': '973 Sutton Lights Apt. 992\nNorth David, WY 88930',
    'text': 'Include people prevent give. Employee doctor cost up know project hour. To law nearly magazine.',
    'email': 'jodyschultz@example.com',
    'phone_number': '511.266.6469x957',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Arias',
    'William Garrison',
    'Stephanie Smith',
    'Diane Hobbs',
],
    'json': {
    'name': 'Kristina Frank',
    'address': '219 Kelly Parkways Suite 140\nGilesborough, NY 26254',
},
    'key23230': 'value60679',
    'key96880': 'value78104',
    'key64956': 'value46752',
    'key34446': 'value46268',
    'key74502': 'value58807',
    'key20051': 'value40177',
    'key97006': 'value58759',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Stephanie Rivera',
    'address': 'USNV Moore\nFPO AE 62520',
    'text': 'Arrive meeting think. War these across blue after you. Table play management just. Deal unit home event the oil very.',
    'email': 'lindacampos@example.net',
    'phone_number': '791.508.2783',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Harris',
    'Richard Moore',
    'Angie Pennington',
    'Tami Buck',
    'Caitlyn Bryant',
    'Daniel Cook',
    'Joshua Green',
    'Crystal Hudson',
],
    'json': {
    'name': 'Ralph Stevens',
    'address': '4489 Bennett Forest Suite 363\nJosephtown, DE 09864',
},
    'key93225': 'value20507',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Matthew Flores',
    'address': 'PSC 9021, Box 4611\nAPO AP 67579',
    'text': 'Determine run military.\nWide such throw.\nAgree participant own officer we point east. Response health decade stock I simply. Tough during total girl list.',
    'email': 'lewiszachary@example.org',
    'phone_number': '001-250-734-9040x6627',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Johnson',
    'Bailey Lee',
],
    'json': {
    'name': 'Tamara Weber',
    'address': '086 Martinez Locks\nBrianastad, PA 36873',
},
    'key47464': 'value90720',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Courtney George DVM',
    'address': '4978 Travis Loop\nNorth Mariaville, NJ 33442',
    'text': 'Dark without production grow. Structure after successful person which truth. Guess instead shake choice agent.\nThree technology section apply action create law.',
    'email': 'sandrafields@example.net',
    'phone_number': '773.961.8248x3282',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Page',
    'Jennifer Williams',
    'James Johnson',
    'Mrs. Jennifer Randolph',
    'Brian Graves',
    'Brenda Taylor',
    'Ashley Smith',
],
    'json': {
    'name': 'Barry Coffey',
    'address': '1572 Butler Mount\nDianeland, WI 16686',
},
    'key50795': 'value18714',
    'key81747': 'value68805',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Elijah Kane',
    'address': '12658 Arroyo Row Apt. 321\nWest Hannahshire, LA 83373',
    'text': 'Green voice produce we modern positive. Fear white series threat market. Concern condition PM. Might its relate.\nEnvironment nice likely ask perform something. Spend can task business how.',
    'email': 'barbara47@example.com',
    'phone_number': '2079182321',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alison Nguyen',
    'Kevin Collins',
    'David Lopez',
    'Lisa Davidson',
    'Pamela Griffith',
    'John Austin',
    'Mrs. Sheila Dillon MD',
    'Angela Stewart',
],
    'json': {
    'name': 'Brian Crawford',
    'address': '708 Jennifer Underpass\nNorth Angela, NE 20820',
},
    'key94065': 'value42523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Renee Morgan',
    'address': '1103 Jeffrey Ports Apt. 781\nJoneshaven, AS 90949',
    'text': 'Art mission never international poor daughter. Artist foreign such become defense.\nCentral remain magazine enough work. Government enter plant citizen night ground guy go.',
    'email': 'toddconrad@example.com',
    'phone_number': '001-248-689-2490x48857',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Carmen Gallegos',
    'Heather Welch',
    'Sharon Khan',
    'Phyllis Hunt',
    'Anthony Tucker',
    'Elizabeth Hall',
    'Raven Ross',
],
    'json': {
    'name': 'Douglas Page',
    'address': '4344 Janice Dam Apt. 082\nEast Robert, IL 40743',
},
    'key15265': 'value60520',
    'key7166': 'value33613',
    'key92071': 'value24842',
    'key98424': 'value85123',
    'key85518': 'value97257',
    'key56242': 'value43128',
    'key82125': 'value31781',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Allison Reyes',
    'address': '4260 Dean Gardens\nCrystalmouth, ND 61649',
    'text': 'Why bed later after matter avoid. Drive especially cup country.\nStandard hit goal report draw effort design. Increase avoid drop cut near ready mother. Easy figure high involve evidence type.',
    'email': 'regina77@example.org',
    'phone_number': '+1-703-440-6679x24376',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Donna Phillips',
    'Kenneth Rivera',
    'Brett Vega',
],
    'json': {
    'name': 'Ann Thomas',
    'address': 'Unit 2773 Box 8091\nDPO AA 21430',
},
    'key44159': 'value85622',
    'key42376': 'value86441',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Brandon Cooper',
    'address': '07917 Campbell Common\nTheresashire, DE 06263',
    'text': 'Fund culture that great break party official. Throw administration evidence best real security two. Receive smile trouble.\nStand between building police sister speech. Fine treat law give.',
    'email': 'gregorysanders@example.net',
    'phone_number': '001-943-326-2557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lindsay Rodriguez',
    'Daniel Roberts',
    'William Vance',
    'Samantha Cole DVM',
    'Anthony Mahoney',
    'Christian Scott',
    'Pamela Clarke',
],
    'json': {
    'name': 'Laurie Campbell',
    'address': 'PSC 3945, Box 9254\nAPO AE 64223',
},
    'key18127': 'value28419',
    'key67251': 'value81989',
    'key67304': 'value97397',
    'key8932': 'value24256',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Melissa Taylor',
    'address': '3860 Brian Route Suite 779\nEast Bradleymouth, MH 47149',
    'text': 'Information prepare agreement like. Radio course include magazine or table explain.',
    'email': 'carol78@example.net',
    'phone_number': '001-447-534-5621',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Jones',
],
    'json': {
    'name': 'Vincent Evans',
    'address': 'USNS Ward\nFPO AE 58431',
},
    'key11909': 'value92750',
    'key18223': 'value95704',
    'key8712': 'value51912',
    'key73026': 'value17988',
    'key81204': 'value81505',
    'key99091': 'value71978',
    'key66828': 'value51925',
    'key83092': 'value15725',
    'key74273': 'value286',
    'key39116': 'value41077',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'John Garcia',
    'address': '35062 Stout Spurs\nKochville, OR 51865',
    'text': 'Beautiful ask baby sing. Next kitchen son hair size establish.',
    'email': 'wjones@example.com',
    'phone_number': '7175655861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jason Reynolds',
],
    'json': {
    'name': 'Robert Terry',
    'address': '3989 Miller Hills\nWilliamsmouth, NC 76603',
},
    'key318': 'value56748',
    'key21952': 'value25872',
    'key55137': 'value42452',
    'key82274': 'value85430',
    'key79013': 'value17006',
    'key41120': 'value14379',
    'key10119': 'value68779',
    'key10353': 'value23629',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Eric Ward',
    'address': 'PSC 5125, Box 3278\nAPO AP 11395',
    'text': 'Sea wall quality stage police dream.',
    'email': 'kellerdavid@example.net',
    'phone_number': '299-450-9399',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amy Porter',
    'Jordan Perez',
    'Jeffery Montes',
    'John Schultz',
],
    'json': {
    'name': 'Frank Holland',
    'address': '07095 Lewis Burg Apt. 123\nTimothyshire, MS 83404',
},
    'key19707': 'value24998',
    'key60463': 'value41039',
    'key19148': 'value72185',
    'key11843': 'value36477',
    'key2362': 'value70486',
    'key59192': 'value37285',
    'key27939': 'value37027',
    'key38491': 'value28431',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Melissa Brandt',
    'address': '096 Jones Passage\nNorth Sean, KS 09914',
    'text': 'Reason address minute draw story thing officer. Purpose movie soldier fast mean bill role.\nAdult drop true quite assume natural join. Price according the modern window.',
    'email': 'robert86@example.com',
    'phone_number': '(513)938-1632x7426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Johnson',
    'Joseph Coleman',
    'Denise Fields',
    'Jessica Adams',
],
    'json': {
    'name': 'Matthew Stevens',
    'address': '03845 Kent Lake Apt. 061\nGreenshire, OK 13499',
},
    'key41715': 'value84176',
    'key81641': 'value14025',
    'key77792': 'value93511',
    'key8555': 'value1216',
    'key89572': 'value63779',
    'key8081': 'value94727',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Charles Wheeler',
    'address': '33679 Cordova Wall\nPort Theresa, NH 57384',
    'text': 'Deal whole concern north keep. Establish sea conference adult true father between particularly. Create market receive into far interesting according blue. Whether into record appear trade certainly.',
    'email': 'john79@example.org',
    'phone_number': '690-265-0061',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Nguyen',
    'Thomas Scott',
    'Bryan Jones',
],
    'json': {
    'name': 'Michael Cardenas',
    'address': 'PSC 1785, Box 4366\nAPO AA 50682',
},
    'key44817': 'value51752',
    'key77568': 'value11295',
    'key78404': 'value84451',
    'key77112': 'value88419',
    'key28808': 'value55309',
    'key99129': 'value79827',
    'key91364': 'value23146',
    'key25553': 'value5528',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Leslie Bond',
    'address': 'PSC 5792, Box 8940\nAPO AA 03282',
    'text': 'Industry treat television specific. Practice car deep team mother.\nRest realize run effort cause make baby institution. Hot seat hotel rise. Them significant manager trade nor check.',
    'email': 'marymosley@example.net',
    'phone_number': '001-864-288-6346x565',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Smith',
    'Daniel Matthews',
    'Katelyn Kerr',
    'Monica Parsons',
    'Andrew Nguyen',
    'Christopher Obrien',
    'Pamela Simon',
    'Kenneth Gomez',
],
    'json': {
    'name': 'Kevin Smith',
    'address': '45712 Brianna Lake\nWest Emilytown, AS 88808',
},
    'key16925': 'value24404',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Emily Smith',
    'address': '064 Baker Divide\nLake Codyberg, ID 99931',
    'text': 'Back seven life financial national drug charge level. Board the beautiful mouth list forward lawyer. Debate important good particularly brother song production page.',
    'email': 'trevor33@example.net',
    'phone_number': '858.636.3554x777',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amy Cruz',
    'Brenda Lane',
],
    'json': {
    'name': 'Kevin Lawrence',
    'address': 'USCGC Lee\nFPO AA 52157',
},
    'key9340': 'value94049',
    'key21501': 'value35798',
    'key81853': 'value99839',
    'key95852': 'value6675',
    'key81527': 'value60522',
    'key3444': 'value19446',
    'key98957': 'value37084',
    'key6442': 'value53084',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Melanie Williams',
    'address': '32717 Ellen Track\nDonaldborough, ND 02175',
    'text': 'Campaign prepare maybe certain. Pressure fill far just. Field strong market author little us.\nEveryone ask candidate work line never lot never. Hundred beautiful movement poor experience contain.',
    'email': 'emilylozano@example.org',
    'phone_number': '790.980.6579',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Rodriguez',
    'Tasha Anderson DDS',
    'Michael Thompson',
    'Kenneth Graham',
    'Stephen Taylor',
],
    'json': {
    'name': 'Christina Bailey',
    'address': '278 Perez Wells\nLake Chelsealand, AR 66990',
},
    'key52728': 'value25632',
    'key53048': 'value33429',
    'key54732': 'value35547',
    'key51365': 'value47781',
    'key33890': 'value56694',
    'key72992': 'value85253',
    'key19562': 'value13815',
    'key21676': 'value78509',
    'key59645': 'value29713',
    'key61999': 'value52760',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Michael White',
    'address': 'PSC 5683, Box 4875\nAPO AP 18410',
    'text': 'Give rock bag determine own. Most ever technology arrive. Wear community father soon generation economy bit.\nEconomy state mean window. Drug they social concern. Any rather try indicate.',
    'email': 'oalexander@example.net',
    'phone_number': '534.299.5515x9835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Todd Morales',
    'Francisco Mcdonald',
    'Laura Jones',
    'Gloria Murphy',
    'Ryan Tanner',
    'Ashley Bowers',
    'Breanna Elliott',
],
    'json': {
    'name': 'Barbara King',
    'address': '01770 Brown Harbors Apt. 815\nLake Nathanielchester, MA 69702',
},
    'key62522': 'value96296',
    'key37318': 'value56715',
    'key2661': 'value11792',
    'key400': 'value74139',
    'key19797': 'value68128',
    'key1856': 'value16788',
    'key33662': 'value72855',
    'key19816': 'value65029',
    'key77874': 'value16889',
    'key96044': 'value53797',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jessica Farmer',
    'address': '874 Sergio Keys Apt. 191\nMartinezfurt, SC 62129',
    'text': 'Miss turn lay option. Standard million report by improve.\nSister practice series look account security. Attention recently order increase least music. His wonder much far.',
    'email': 'mckenziejose@example.net',
    'phone_number': '769-272-0493',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Franco',
    'Cindy Mitchell',
    'Ruth Waters',
    'Ebony Foster',
    'Heather Ramos',
    'Eric Marshall',
    'Peter Parker',
    'Lisa Bennett',
    'Corey Johnson',
],
    'json': {
    'name': 'Jason Williams',
    'address': 'USNS Dillon\nFPO AE 91158',
},
    'key17900': 'value62036',
    'key77973': 'value60723',
    'key5816': 'value56785',
    'key70524': 'value94611',
    'key36482': 'value13890',
    'key30751': 'value2282',
    'key63990': 'value50594',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Chloe Mcclure',
    'address': '05196 Hall Tunnel\nGregoryburgh, TX 29798',
    'text': 'Society writer chair hot easy.\nTough grow guy low truth health she. Fill central western.\nClear than world cause. Government street central glass form leg tonight. Truth north agreement decade.',
    'email': 'bwarren@example.net',
    'phone_number': '(843)380-8920x5275',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Lewis',
    'Justin Booker',
    'Sean Hartman',
    'Karen Green',
    'Joseph Martin',
    'Christopher Suarez',
    'Brandy Patterson',
    'Sierra Jackson',
],
    'json': {
    'name': 'Grant Pineda',
    'address': '79415 Sean Shoals\nNew Brandon, OR 98732',
},
    'key56268': 'value14698',
    'key52919': 'value78465',
    'key8252': 'value68404',
    'key95527': 'value34720',
    'key16248': 'value7237',
    'key73357': 'value72471',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jenna Dixon',
    'address': '93333 Juan Mill Suite 822\nWagnerhaven, AL 06750',
    'text': 'Cover sport gas employee create capital few determine. Feeling quite central if dinner.\nState have new without. One return father open member. Take who door that down pass word seek.',
    'email': 'smithmatthew@example.net',
    'phone_number': '001-993-271-4458x09896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Bush',
    'Jack Shelton',
    'Ryan Mcbride',
    'Elizabeth Miller',
    'Ricky Johnson',
    'Heather Goodwin',
    'Katelyn Sanchez',
    'Sarah Brooks',
],
    'json': {
    'name': 'Michael Burgess',
    'address': '697 Katie Plain Suite 530\nStevenbury, MA 22293',
},
    'key62869': 'value42247',
    'key82655': 'value5792',
    'key32975': 'value62870',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Randy Thomas',
    'address': '9286 Nixon Avenue\nMeyermouth, WI 24658',
    'text': 'International do probably number argue again player. Performance law site.',
    'email': 'joseph01@example.net',
    'phone_number': '(586)424-3644x551',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Hunter Mitchell',
],
    'json': {
    'name': 'Lauren Rowe',
    'address': 'USCGC Vaughan\nFPO AE 72515',
},
    'key3103': 'value88495',
    'key97759': 'value46820',
    'key87738': 'value27576',
    'key48524': 'value74955',
    'key9887': 'value44408',
    'key84167': 'value81226',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Mary Oliver',
    'address': '41918 Willis Mall\nSouth Darryl, NH 20106',
    'text': 'Product southern value book media case world police. Bag late image experience cause not offer. House during article song north.',
    'email': 'glennmegan@example.com',
    'phone_number': '6473846682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Ramirez',
    'Jill Ruiz',
    'Scott Powell',
],
    'json': {
    'name': 'Karen Foster',
    'address': '022 Richard Harbor\nNicolechester, TX 44777',
},
    'key84420': 'value68628',
    'key64890': 'value77181',
    'key25994': 'value15224',
    'key82177': 'value39392',
    'key81330': 'value54496',
    'key63969': 'value28792',
    'key51542': 'value59739',
    'key7984': 'value70047',
    'key25326': 'value56371',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Lisa Conley',
    'address': 'Unit 7770 Box 8075\nDPO AE 86171',
    'text': 'Our money economy ball quickly part page. Decade show machine. May speak well.\nVote discussion yes account rise. Difference foreign lose. He individual send age.',
    'email': 'mcampos@example.net',
    'phone_number': '453-267-4780',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Molina',
    'Michael Tran',
    'Jon Powers',
],
    'json': {
    'name': 'Kevin Peterson',
    'address': '9254 Brown Divide Suite 875\nNew Christopher, TN 16720',
},
    'key48887': 'value94912',
    'key47587': 'value9216',
    'key64306': 'value13014',
    'key14031': 'value83833',
    'key19002': 'value16314',
    'key74942': 'value68289',
    'key27282': 'value37533',
    'key95894': 'value82645',
    'key11264': 'value82215',
    'key48436': 'value95112',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Lori Duke',
    'address': '82677 John Point\nLake Alexander, KY 67410',
    'text': 'Reveal air not like say list begin. Drug position whether without. Thus order recently.\nReflect teach catch low follow everybody. Country interesting south inside later.',
    'email': 'angelicaramos@example.com',
    'phone_number': '674-761-5654',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Terrence Garcia',
    'Jaime Cook',
    'Melissa Chavez',
    'George Thompson',
    'Andrew Farley',
    'Cynthia Garcia',
],
    'json': {
    'name': 'Amber Ellis',
    'address': 'USNV Maxwell\nFPO AA 11068',
},
    'key86536': 'value89878',
    'key59255': 'value51895',
    'key62383': 'value66421',
    'key20034': 'value38387',
    'key63074': 'value90508',
    'key56573': 'value7590',
    'key28193': 'value27704',
    'key5095': 'value12118',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Rodney Fitzgerald',
    'address': '65480 Clark Street\nNew Angelamouth, AR 36598',
    'text': 'Price various coach report. Major investment different memory ever. Sea none baby sit lawyer.\nCamera high food protect his why dream. Boy remember seat.',
    'email': 'rschneider@example.com',
    'phone_number': '001-582-656-2280x6541',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Williams',
    'Richard Solis',
    'Christian Weaver',
    'Susan Boone',
    'James Barnett',
    'George Grant',
    'Douglas Stein',
    'Corey Butler',
],
    'json': {
    'name': 'Danny Lyons',
    'address': '411 Jordan Dam\nRileyland, DC 22555',
},
    'key6999': 'value69708',
    'key90251': 'value93049',
    'key97577': 'value80133',
    'key49775': 'value40959',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Michelle Reyes',
    'address': '46560 Nathaniel Greens\nJamesshire, VT 37919',
    'text': 'Parent media whether land management opportunity. Tough hospital rise war grow. Bag under decision.',
    'email': 'kevin61@example.org',
    'phone_number': '6564143674',
    'array_int_dynamic': [
    43670,
],
    'array_varchar_dynamic': [
    'Amber Hughes',
    'Courtney Mayo',
    'Timothy Garza',
    'James Booth',
    'Christine Burns',
    'Charles West',
    'Melissa Singleton',
    'Gabrielle Pearson',
    'Jeffrey Meadows',
],
    'json': {
    'name': 'Maria Sims',
    'address': '65759 Anthony Lights\nJohnsonview, NJ 37289',
},
    'key96969': 'value35456',
    'key62655': 'value50034',
    'key91360': 'value84530',
    'key19269': 'value28435',
    'key65315': 'value76467',
    'key95673': 'value8592',
    'key43430': 'value9744',
    'key96676': 'value39368',
    'key87766': 'value22843',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Dawn Kennedy',
    'address': '678 Veronica Passage Apt. 874\nWest Heatherberg, AK 96503',
    'text': 'Feeling position front hair black. Off within soon look resource trouble fall.\nExist which call decide garden. Open many prevent effort company price.',
    'email': 'wschmidt@example.com',
    'phone_number': '837-921-0819x448',
    'array_int_dynamic': [
    30906,
],
    'array_varchar_dynamic': [
    'Andrew Harris',
    'Thomas Garcia',
    'Ariana Johnston',
    'Tina Ingram',
    'Michael Robinson',
    'Mrs. Nancy Perry',
    'Thomas Davis',
    'Tabitha Bowers',
    'Mr. Eric Lewis',
],
    'json': {
    'name': 'Mark Wright',
    'address': '259 Warren Lodge Suite 042\nAlvareztown, CO 54258',
},
    'key39781': 'value87331',
    'key84499': 'value43052',
    'key48149': 'value58827',
    'key54224': 'value7627',
    'key91594': 'value97220',
    'key79993': 'value1001',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Daniel Raymond MD',
    'address': '20352 Laura Union Suite 334\nRobertsonmouth, ID 05530',
    'text': 'Mrs man town effort determine one. Another this leave article. Paper stage hot. Loss study experience make daughter name.\nLeader total author rise operation around must. Trip imagine from.',
    'email': 'katiesimon@example.org',
    'phone_number': '001-302-900-8883x9336',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Miss Sandra Mendez DDS',
    'Lisa Moore',
    'Eileen Lopez',
    'Gregory Hamilton',
    'Brittany Soto',
    'Audrey Alexander',
],
    'json': {
    'name': 'Michael Foster',
    'address': '1863 Robert Station\nKristieburgh, NC 62054',
},
    'key3100': 'value16411',
    'key55850': 'value39113',
    'key59174': 'value35111',
    'key20204': 'value32289',
    'key23564': 'value6036',
    'key38328': 'value18355',
    'key44339': 'value35556',
    'key86829': 'value64978',
    'key81341': 'value25132',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Bryan Brown',
    'address': '910 Alvarez Path\nJeannebury, AL 94333',
    'text': 'Stand federal manage actually. Very remain good play end deep. For world century positive.\nAbout analysis onto development forward try itself. Last huge nearly step finish respond feel old.',
    'email': 'john33@example.com',
    'phone_number': '8632850676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kristina Allen',
],
    'json': {
    'name': 'Mr. Mark Wilson',
    'address': '30224 Sanford Meadows Suite 812\nSouth Kevinshire, NJ 04030',
},
    'key27150': 'value82104',
    'key1111': 'value73325',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Kathy Garrett',
    'address': '5107 Katherine Field Apt. 633\nWilsonmouth, PA 84583',
    'text': 'Could huge food. Much kind item bed skill.\nPopulation increase while member put join institution teach.\nWar matter however. Goal various agent situation ball. Head cup account talk bill yard.',
    'email': 'dean22@example.com',
    'phone_number': '879.307.0271',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Raymond Torres',
    'Kathleen Riley',
    'Marie Ortega',
    'Thomas Holt',
    'James Ford',
],
    'json': {
    'name': 'Patricia Richards',
    'address': '133 Grimes Mill\nJustinstad, SD 61852',
},
    'key64585': 'value69464',
    'key23630': 'value41730',
    'key1532': 'value15781',
    'key12811': 'value92553',
    'key92236': 'value32922',
    'key84035': 'value79298',
    'key4749': 'value21149',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Monica Johnson',
    'address': '206 Timothy Street\nNew Alec, PR 83250',
    'text': 'Television difference benefit economic loss effort can. Her free green special near game director current.',
    'email': 'usmith@example.com',
    'phone_number': '340-726-8385x417',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Tonya Scott',
    'Joshua Moore',
    'Joseph Silva',
    'Amy Allen',
    'Anthony Rhodes',
    'Haley Johnson',
    'Stephen Alvarez',
],
    'json': {
    'name': 'Tommy Stewart',
    'address': '0479 Kiara Knoll Suite 935\nNorth Michellemouth, IL 79349',
},
    'key69774': 'value10879',
    'key99466': 'value54168',
    'key9109': 'value87313',
    'key29111': 'value92612',
    'key93366': 'value66606',
    'key48748': 'value55814',
    'key82817': 'value96403',
    'key98': 'value54082',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Rebecca Ramirez',
    'address': '15837 David Islands\nMarcbury, OR 99282',
    'text': 'Fact property action ok choice. Alone bring better service central system truth.\nEdge itself level student admit movement example among. Floor network once site thus city.',
    'email': 'brettwatson@example.net',
    'phone_number': '+1-807-264-8076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Sullivan',
    'Sheri Rich',
    'Rachel Pierce',
    'Todd Turner',
    'Martha Lewis',
    'Antonio Ballard',
],
    'json': {
    'name': 'Mrs. Patricia Miller',
    'address': '17251 Blackburn Knolls Apt. 656\nRebeccafort, TN 10310',
},
    'key21528': 'value20606',
    'key66749': 'value18552',
    'key621': 'value13129',
    'key84914': 'value87648',
    'key62275': 'value19775',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Cindy Coleman',
    'address': '627 Ruiz Cove Apt. 372\nSteveberg, MN 70295',
    'text': 'Too would PM nearly forward price.\nSimple help letter better. Person exactly fine whose affect. Establish value early very.',
    'email': 'thomasmary@example.net',
    'phone_number': '2518183627',
    'array_int_dynamic': [
    75444,
],
    'array_varchar_dynamic': [
    'Aaron Randall',
    'Sara Miller',
    'Traci Roman',
    'Brian Allen',
    'Nicholas Bryant',
    'Gary Alvarez',
    'Michael Thomas',
    'Angela White',
],
    'json': {
    'name': 'Faith Reed',
    'address': '47422 Snyder Mountain\nCardenasshire, MP 42813',
},
    'key11003': 'value29939',
    'key43280': 'value81843',
    'key89125': 'value9859',
    'key49328': 'value51179',
    'key89063': 'value11658',
    'key44118': 'value95023',
    'key88669': 'value73469',
    'key38385': 'value7051',
    'key73390': 'value32711',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Kathy Santiago',
    'address': '050 Matthew Terrace Suite 930\nBruceborough, ME 09547',
    'text': 'Compare receive garden upon than bed these. That business before individual challenge anyone when mention. Wonder side stage scientist.\nYou majority arrive really. Start subject population medical.',
    'email': 'mhays@example.com',
    'phone_number': '(502)793-6333x408',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Cristian Hayes',
    'Ann Huber',
],
    'json': {
    'name': 'Jason Villarreal',
    'address': '899 Martinez Branch\nEast Leahburgh, NJ 07317',
},
    'key38501': 'value15534',
    'key92646': 'value29308',
    'key79799': 'value31357',
    'key45267': 'value44201',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Tonya Logan',
    'address': '804 Luis Cape Apt. 325\nMathewsfort, NJ 93910',
    'text': 'Seek free cold both marriage bill present. Owner card third sport. Fast lay only smile interest these win special.',
    'email': 'rodneyevans@example.org',
    'phone_number': '332.238.8661x3886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Donna Hunter',
    'Matthew Chang',
    'Kim Cox',
    'Gina Briggs',
    'Andrea Austin',
    'Natasha Thomas',
],
    'json': {
    'name': 'Mitchell Smith',
    'address': '13879 Vaughan Station Suite 497\nSouth Patrick, PA 59828',
},
    'key75624': 'value57345',
    'key15079': 'value74711',
    'key76966': 'value46114',
    'key9824': 'value84301',
    'key75375': 'value44280',
    'key60418': 'value84875',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Theresa Ortiz',
    'address': 'Unit 9053 Box 4162\nDPO AA 48667',
    'text': 'Live yes story feel interesting everything. Better finally market our race.\nPretty majority my nor smile not teacher. Body community in up. Could consider figure direction would career crime true.',
    'email': 'spearsnancy@example.org',
    'phone_number': '349-594-1685x71072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Gregory',
    'Emma Oneill',
    'Matthew Silva',
],
    'json': {
    'name': 'Brittney Villanueva',
    'address': '871 Adam Haven\nLunaland, VA 02625',
},
    'key38117': 'value73863',
    'key47653': 'value20328',
    'key57918': 'value44721',
    'key75205': 'value31486',
    'key9200': 'value33312',
    'key97717': 'value54663',
    'key90805': 'value70754',
    'key11887': 'value55458',
    'key68605': 'value45041',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'James Hall',
    'address': '8835 Robert Divide\nEast Kenneth, VT 67926',
    'text': 'Fine decide talk per I positive. Black very to really factor.\nClaim theory argue level. Fact line president author gun letter school many. Everything movement style establish.',
    'email': 'millerevan@example.org',
    'phone_number': '580.961.1668x0904',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Baker',
    'Rebecca Cooper DDS',
    'Charles Esparza',
],
    'json': {
    'name': 'Leslie Mathews',
    'address': '09631 Long Squares Apt. 158\nCraneview, OH 54406',
},
    'key88043': 'value88900',
    'key9987': 'value6083',
    'key78268': 'value49710',
    'key59598': 'value53060',
    'key86985': 'value62611',
    'key50636': 'value11123',
    'key33026': 'value59281',
    'key99953': 'value75162',
    'key84375': 'value90426',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Megan Livingston',
    'address': '07944 Nguyen Extensions\nVictormouth, GA 15954',
    'text': 'Yard myself blood two fish street. Subject lose economy accept sometimes.\nCare fill chance arm. Allow peace keep artist kitchen organization outside. Political direction list natural.',
    'email': 'rcannon@example.net',
    'phone_number': '849.421.3739',
    'array_int_dynamic': [
    95766,
],
    'array_varchar_dynamic': [
    'Lauren Alvarado',
    'Margaret Hernandez',
    'Stacey Rogers',
    'Chad Kerr',
    'John Carroll',
],
    'json': {
    'name': 'Larry Crawford',
    'address': '637 Oliver River Suite 372\nRobertshire, NY 51683',
},
    'key48005': 'value59664',
    'key55563': 'value68457',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Tracy Strickland',
    'address': '8246 Allen Islands\nPort Meghan, OK 93656',
    'text': 'Development treatment how computer body. Interest live half add. Establish off realize total. Suggest hair better any continue.\nNever cup to sell goal. Adult training especially manage teacher three.',
    'email': 'xmcgee@example.com',
    'phone_number': '(808)882-3241x31929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Shawn Schmidt',
    'Deborah Howard',
    'Kayla Zamora',
    'Taylor Bradley',
],
    'json': {
    'name': 'Jeremy Barrett',
    'address': '71440 Webb Tunnel\nBryanhaven, OK 22066',
},
    'key5130': 'value66996',
    'key97614': 'value22589',
    'key94507': 'value92549',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'James Coleman',
    'address': 'USS Henry\nFPO AE 89515',
    'text': 'Worry himself skill help opportunity statement see close. Heavy travel field catch message rate. Bad upon project arm bar medical many.',
    'email': 'dannylowe@example.com',
    'phone_number': '+1-574-354-7391',
    'array_int_dynamic': [
    81070,
],
    'array_varchar_dynamic': [
    'Stephanie Mills',
    'William Rush',
    'Kendra Little',
    'James Bonilla',
    'Matthew Clements',
    'Jessica Morgan',
],
    'json': {
    'name': 'Laura Lester',
    'address': '9582 Melissa Burgs Suite 341\nWest Julie, CA 67613',
},
    'key52190': 'value38853',
    'key3884': 'value44509',
    'key88515': 'value60366',
    'key86045': 'value99286',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'John Nichols',
    'address': '369 Stephanie Station Apt. 792\nPort Savannah, VI 57016',
    'text': 'Better probably exactly career. Election much represent.\nHis could become mouth officer suggest how officer. Animal bit add. Break up conference bit small.',
    'email': 'powersdanny@example.com',
    'phone_number': '2602301068',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tanner Kelley',
    'Andrew Smith',
    'Michelle Hale',
    'Samuel Holmes',
    'Caleb Strickland',
    'Michael Anderson',
    'Paula Clarke',
    'Carl Mitchell',
    'Kenneth Parker MD',
    'Bob Cole',
],
    'json': {
    'name': 'Dana Thomas',
    'address': '22686 Petty Meadow\nEast Christopher, ID 64994',
},
    'key27714': 'value24799',
    'key19786': 'value59885',
    'key84993': 'value44560',
    'key19261': 'value7072',
    'key49763': 'value75354',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'John Davis',
    'address': '3497 Angela Groves\nNorth Roy, PR 47590',
    'text': 'Tv least office white. Build purpose capital prevent.\nSince remember that different process the. Age rich year loss today by put.',
    'email': 'nhaynes@example.org',
    'phone_number': '+1-488-861-4799x811',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Anne Durham',
    'Patricia Murphy',
    'Samantha Cole',
    'Richard Arellano',
    'Bryan Anderson',
    'Jillian Gonzalez',
    'Mackenzie Nixon',
    'Zachary Henderson',
    'Caleb Wang',
],
    'json': {
    'name': 'Eric Jones',
    'address': '20423 Angela Tunnel Apt. 661\nCarpenterview, DE 59078',
},
    'key9057': 'value29914',
    'key94771': 'value58946',
    'key83588': 'value87386',
    'key27026': 'value97921',
    'key82930': 'value7093',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Mandy Ford',
    'address': '947 Beard Creek\nWest Crystal, AK 32926',
    'text': 'Play future program. Professor main guess store song.\nAmong pick itself world. Third physical no ok degree current answer. Talk our five outside nearly. End throw including American him.',
    'email': 'shayes@example.net',
    'phone_number': '+1-316-397-3224x230',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Thomas',
    'Brent Mcclure',
    'David Navarro',
],
    'json': {
    'name': 'Alex Carter',
    'address': '51021 Terry Mission\nLake Shawnview, AS 76786',
},
    'key69214': 'value4016',
    'key61773': 'value71145',
    'key51722': 'value40731',
    'key59610': 'value31415',
    'key64275': 'value17246',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Roger Smith',
    'address': '926 Crosby Lodge\nGoodwinberg, WV 82888',
    'text': 'Society fill your contain move tax. Have accept cause teacher social know remain air. Mrs about education say administration do two or.',
    'email': 'davisclaudia@example.net',
    'phone_number': '(670)201-6969x724',
    'array_int_dynamic': [
    40473,
],
    'array_varchar_dynamic': [
    'Elizabeth Whitaker',
    'Melissa Olson',
    'Sandra Simpson',
    'Zachary Li',
    'Cynthia Wood',
    'Jason Brown',
    'Grant Roberts',
    'David Grant',
],
    'json': {
    'name': 'Austin Mccormick',
    'address': '2338 Tammy Grove Suite 558\nWest Andrewfurt, NH 58526',
},
    'key11589': 'value27646',
    'key3680': 'value76385',
    'key28661': 'value22101',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Joseph Chapman',
    'address': 'Unit 6741 Box 3328\nDPO AA 15621',
    'text': 'Reflect remember accept.\nHand foreign safe third lot. Pass appear recent use successful character allow.\nMatter address street.',
    'email': 'ashleytorres@example.org',
    'phone_number': '(394)324-0531x150',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kara Anderson',
    'Gordon Mack',
    'Sarah Watts',
    'Jennifer Anderson',
    'Natasha Chavez',
    'Laura Howard',
],
    'json': {
    'name': 'Jonathon Wilson',
    'address': '973 Ortega Motorway Suite 603\nDanielleburgh, UT 22904',
},
    'key33894': 'value35307',
    'key70379': 'value82938',
    'key75202': 'value2867',
    'key36768': 'value21254',
    'key4488': 'value13814',
    'key6281': 'value48408',
    'key49899': 'value46143',
    'key98245': 'value3833',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Candace Wells',
    'address': '3986 Ross Drives\nLopezbury, MS 73726',
    'text': 'Several mention cover wind. Story fish interesting operation side situation.\nForget difficult lead high direction either record theory. Test traditional one exist account role change.',
    'email': 'christinemitchell@example.com',
    'phone_number': '+1-755-925-1908x8316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Latoya Francis',
    'Kelly Adams',
    'Lauren Walker',
    'Ian Wallace DVM',
],
    'json': {
    'name': 'Pamela Davis',
    'address': '846 Black Cove Apt. 155\nCaseyfurt, SD 02810',
},
    'key79535': 'value9596',
    'key71852': 'value64891',
    'key14088': 'value62852',
    'key83019': 'value2239',
    'key10104': 'value16076',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Alexander Harris',
    'address': '730 Williams Crest Apt. 480\nPriscillaborough, IN 35211',
    'text': 'Clearly physical half effort. Traditional like reflect election run eat. Above interview turn church history. Employee theory southern mother inside call.',
    'email': 'itran@example.org',
    'phone_number': '694-842-1046x423',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'April Bell',
    'Mr. Matthew Herrera MD',
    'Jeffrey Davis',
    'Douglas Moore',
    'Carolyn Juarez',
    'Cindy Willis',
    'Jessica Hughes',
    'Christine Brown',
],
    'json': {
    'name': 'Dustin Hayes',
    'address': 'USNV James\nFPO AE 09775',
},
    'key10054': 'value19827',
    'key97021': 'value87308',
    'key51379': 'value41654',
    'key6177': 'value7427',
    'key36510': 'value80439',
    'key34924': 'value4394',
    'key70638': 'value30844',
    'key36866': 'value98529',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Kenneth Jensen',
    'address': '100 James Shores Suite 138\nDanielleside, RI 45318',
    'text': 'Same stuff evidence million past goal sea. Billion even down leader very career. Future new author guess how doctor American.\nThree suddenly challenge situation.',
    'email': 'heather71@example.org',
    'phone_number': '001-251-332-6830x402',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Harry Woods',
    'John Jenkins',
    'Stephen Larson',
    'Caroline Green',
    'Nicholas Coleman',
],
    'json': {
    'name': 'Jennifer Thompson',
    'address': '57515 James Lodge Suite 633\nEast Tyrone, UT 03762',
},
    'key39673': 'value80249',
    'key98170': 'value18057',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Jacqueline Collins',
    'address': '83747 Brenda Place Suite 101\nFoxborough, MA 38309',
    'text': 'Must enter run draw realize different. Huge church call international everything forward throw.\nNecessary detail his animal. Feeling modern trouble drive.',
    'email': 'joanneguzman@example.com',
    'phone_number': '801-944-8694',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joanna Smith',
    'Katie Barnett',
    'Brittney Huff',
    'Mariah Torres',
    'Tyler Carr',
    'Melissa Lopez',
],
    'json': {
    'name': 'John Mcdonald',
    'address': '1388 Burton Canyon\nBishopshire, LA 04915',
},
    'key34828': 'value56739',
    'key39572': 'value39829',
    'key82396': 'value203',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Andrew Mcdonald',
    'address': '36725 Mason Manor\nHughesshire, CO 38926',
    'text': 'When our head suffer oil bad ago. These town light respond than police. Natural carry federal finally tend. Its study age share state.\nFirm station edge.',
    'email': 'helenmatthews@example.org',
    'phone_number': '+1-216-419-7240x9212',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Marks',
    'Glenn Wheeler',
    'Joseph Smith',
    'Miss Donna Garcia DDS',
    'Amy Gregory',
    'Colin Reid',
    'Mike Bender',
    'Lawrence Simmons',
    'Nicholas Lopez',
    'Lindsay Camacho',
],
    'json': {
    'name': 'Bridget Mcclure',
    'address': 'PSC 7795, Box 2920\nAPO AE 76397',
},
    'key72433': 'value50367',
},
],
    'dbName': 'default',
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
    'RequestId': '9ad7a744-62ef-11f0-9890-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_47_301352DogZUnDe',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-1]_1752744168.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId12810011752744168Json()
    test.run_tests()
