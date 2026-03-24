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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-1]_1752744161_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-1]_1752744161.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId3210011752744161Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-1]_1752744161.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-1]_1752744161.json"
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
    'RequestId': '967cd372-62ef-11f0-9035-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_39_995246QFxpUaeH',
    'dimension': 32,
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
    'RequestId': '969df159-62ef-11f0-a7ac-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_39_995246QFxpUaeH',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Jessica Jackson',
    'address': '419 Alicia Valleys Apt. 453\nPaulview, CO 24894',
    'text': 'Old religious either us fall sport reality trade. Television whole receive relationship star green give professor.',
    'email': 'amanda39@example.org',
    'phone_number': '595.967.5925x9763',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Thornton',
],
    'json': {
    'name': 'Robert Jones',
    'address': '43133 David Streets Suite 683\nSouth Carla, NY 93374',
},
    'key91491': 'value43387',
    'key67264': 'value65511',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Jeremy Kane',
    'address': 'PSC 5467, Box 7132\nAPO AP 19696',
    'text': 'Discuss police analysis indeed attention beautiful. Agent leave major time.\nBlack strategy baby affect same executive foot. Drop skill society able.',
    'email': 'eugene40@example.com',
    'phone_number': '(726)646-9537x465',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Adam Holt',
    'Michael Fischer',
],
    'json': {
    'name': 'Barry Rowe',
    'address': '3483 Scott Highway\nOliviashire, CO 69068',
},
    'key59001': 'value59925',
    'key71849': 'value37622',
    'key43280': 'value73705',
    'key14136': 'value37382',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Jeff Baker',
    'address': '2375 Morris Camp Suite 782\nEast Teresafort, CT 30478',
    'text': 'Letter spring enter peace rather spring. Director explain positive those mention game.\nNo particular style.',
    'email': 'joshuarussell@example.org',
    'phone_number': '560-548-6606x113',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'David Waller',
    'Alejandro Gonzales',
    'Michele Mitchell',
],
    'json': {
    'name': 'Jared Ferguson',
    'address': 'USNV Henderson\nFPO AP 39110',
},
    'key36414': 'value47839',
    'key8931': 'value91565',
    'key83815': 'value66823',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Lindsay Mercado',
    'address': '74373 Cooper Burgs\nLake Jasonburgh, MH 99866',
    'text': 'Enter land nor guess position fear should. Suddenly any put every. Attack learn start window.\nBillion believe whom gas maybe. Moment final same boy him.',
    'email': 'terryjackson@example.com',
    'phone_number': '+1-399-918-4295x39287',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Janet Horn',
    'Jennifer Caldwell',
    'Lisa Thompson MD',
    'Joseph Santana',
    'Jason Thompson',
],
    'json': {
    'name': 'Christian Huerta',
    'address': '300 Karen Port Apt. 780\nPort Todd, VA 07682',
},
    'key89290': 'value97945',
    'key49135': 'value90406',
    'key4203': 'value57202',
    'key76013': 'value29723',
    'key70837': 'value48667',
    'key28999': 'value23741',
    'key97249': 'value6959',
    'key32021': 'value15864',
    'key19614': 'value4444',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Nancy Mejia',
    'address': '440 Bond Prairie\nSouth Alisha, WY 86225',
    'text': 'Rock player sometimes various. Standard rich compare instead. Response everyone present true season common.\nMission avoid everybody method. Site economic pattern language understand.',
    'email': 'sgray@example.net',
    'phone_number': '001-282-386-4379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Angela Jackson',
    'Laura Mills',
    'Emily Baxter',
    'Colleen Morgan',
],
    'json': {
    'name': 'Joseph Oliver',
    'address': '75572 Brown Tunnel Apt. 456\nLeeland, PA 51189',
},
    'key48464': 'value7385',
    'key3479': 'value97529',
    'key96057': 'value56147',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Maurice Abbott',
    'address': '67915 Cline Junctions\nMaryville, KS 66598',
    'text': 'Form guy different game admit. Relationship street interest country. Present it federal.',
    'email': 'ryan06@example.org',
    'phone_number': '779-987-3281x925',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jodi Rosario',
    'Kelly Burnett',
    'Matthew Morrison',
    'Bruce Barrett',
    'Jason Morales',
    'Joel Bridges',
    'Beth Waller',
    'Kyle Mason',
],
    'json': {
    'name': 'John Davis',
    'address': '27529 Cox Parks Suite 133\nHoustonchester, PR 46225',
},
    'key45059': 'value56985',
    'key67697': 'value73656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Mary Stewart',
    'address': '242 Blake Square\nSouth Davidmouth, NM 01597',
    'text': 'Prove it consider radio rather officer. Today option let technology Democrat. End middle officer within old instead even.\nEight forward able morning. Back fast behavior issue movement line today.',
    'email': 'williamwarner@example.org',
    'phone_number': '310-619-2370',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sara Hansen',
    'Samuel Keller',
],
    'json': {
    'name': 'Joseph Weaver',
    'address': '892 Tara Forest\nSouth Andrewland, MP 35545',
},
    'key37146': 'value3206',
    'key40866': 'value87074',
    'key95741': 'value13499',
    'key68858': 'value47035',
    'key54992': 'value38674',
    'key83713': 'value17913',
    'key3538': 'value5853',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Randall Hall',
    'address': '588 Marc Extension\nNorth Shelbybury, IA 53931',
    'text': 'Suggest industry way food teach rate you.\nMiddle stop idea manage successful. Produce research plant southern. Benefit capital provide democratic white wrong half.',
    'email': 'fguerrero@example.net',
    'phone_number': '(941)871-9522x4818',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Charles Green',
    'Jessica Cummings',
    'Bryan Ramirez',
    'Shawn Morales',
],
    'json': {
    'name': 'Dr. Travis Campbell',
    'address': 'PSC 2468, Box 7814\nAPO AP 21820',
},
    'key21468': 'value298',
    'key8631': 'value94967',
    'key76244': 'value17495',
    'key3813': 'value21788',
    'key23967': 'value5460',
    'key89446': 'value26882',
    'key63406': 'value95733',
    'key29572': 'value41443',
    'key9146': 'value46119',
    'key11982': 'value49386',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'William Richardson',
    'address': '695 Williams Centers Apt. 428\nNorth David, CO 56032',
    'text': 'Build understand billion smile site allow.\nCertainly subject kind trip attorney claim. Computer mind southern western. Pressure just place between close area game.',
    'email': 'martinezjennifer@example.com',
    'phone_number': '904.340.3966',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Raymond',
    'Timothy Lopez',
    'Bryan Warren',
    'Dawn Evans',
    'Ashley Lopez',
    'Alexandra Willis',
    'Samantha Walker',
],
    'json': {
    'name': 'Sandra Atkins',
    'address': '442 Richard Flats\nEast Gwendolyn, MP 98230',
},
    'key3363': 'value19436',
    'key40794': 'value69429',
    'key26130': 'value18976',
    'key57492': 'value80449',
    'key82600': 'value52099',
    'key18562': 'value68499',
    'key94174': 'value28520',
    'key6143': 'value14570',
    'key67025': 'value73337',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Anna Shelton',
    'address': 'Unit 1859 Box 3529\nDPO AE 55167',
    'text': 'Easy gun mind since sell career. Guy character stage high foot. Yes ten investment nor. Defense cell list mouth speak including lay.',
    'email': 'castromelissa@example.net',
    'phone_number': '001-299-773-9117x22051',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Miller Jr.',
    'Paul Vazquez',
    'Dawn Garcia',
],
    'json': {
    'name': 'Karen Curtis',
    'address': '767 Robert Way\nRalphland, AK 05274',
},
    'key22196': 'value7699',
    'key89999': 'value47231',
    'key94656': 'value78318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Michael Glover',
    'address': '04564 Lori Loaf Suite 644\nLake John, HI 35836',
    'text': 'Become focus college yeah work act open various. Stop others spring next.\nBeat seek field meet. Feeling away writer culture model the.',
    'email': 'romeromichael@example.com',
    'phone_number': '001-337-426-5855',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Abigail Perez',
    'Mr. Ronnie Ramirez DDS',
    'Meagan Rhodes',
    'Scott Hall',
    'Jacob Brock',
    'Willie Dennis',
    'Meghan Fischer',
    'Nancy Lopez',
    'Terry Greene',
],
    'json': {
    'name': 'Nancy Buchanan',
    'address': '6709 Jessica Ferry Apt. 318\nPort Williemouth, VT 02582',
},
    'key68720': 'value46247',
    'key2049': 'value822',
    'key63324': 'value34503',
    'key43062': 'value40202',
    'key45289': 'value98164',
    'key89220': 'value30132',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Loretta Lee',
    'address': '660 Downs Parkway Suite 835\nLake Leehaven, PA 63676',
    'text': 'Enjoy forget order natural lose. Air message establish over down become say chance.\nWar trade enjoy hour performance. Thank often wide approach school civil. Thing see under too force claim.',
    'email': 'ericksonchristine@example.org',
    'phone_number': '001-715-277-9261x1885',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Herrera',
    'Kelly Flores',
    'Tony Cohen',
    'Jennifer Hampton',
    'Paula Wood',
    'Charles Gallegos',
    'Steven Meadows',
    'Anne Miles',
],
    'json': {
    'name': 'Matthew Evans',
    'address': '4692 Becker Summit Suite 362\nRussellberg, OR 59012',
},
    'key55775': 'value93072',
    'key9854': 'value90542',
    'key15101': 'value6080',
    'key95194': 'value41092',
    'key32873': 'value79584',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Suzanne Mcdonald',
    'address': 'USNS Reyes\nFPO AA 46025',
    'text': 'Opportunity hope million conference foot. Forget reason local. Someone according maintain beyond whether throw into.',
    'email': 'plawson@example.org',
    'phone_number': '+1-408-251-3102x385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Kane',
    'Tracey Smith DVM',
    'Alexis Mullen',
    'Kevin Reyes',
    'William Williams',
    'Robin Archer',
],
    'json': {
    'name': 'Sarah Rivas',
    'address': '9379 Virginia Road Suite 139\nPeterland, NY 88361',
},
    'key65233': 'value25204',
    'key2776': 'value7183',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Beth Lee',
    'address': '56556 Jennifer Spring Apt. 147\nScottbury, PA 25210',
    'text': 'Nearly drug court between imagine happen. Dream really those rich song. Official play gas rate upon view set measure.\nCultural else mention hit practice determine bad.',
    'email': 'zwilson@example.net',
    'phone_number': '206-859-7800',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Edwards',
    'Samantha Smith',
    'Timothy Matthews',
    'Marissa Young',
    'Jennifer Lambert',
    'Anthony Perez',
    'Brandi Pope',
    'Alexander Bowen',
    'Chelsea Thompson',
],
    'json': {
    'name': 'Andrea Fernandez',
    'address': '0882 Carrie Walks\nDeborahland, AR 20499',
},
    'key57965': 'value54283',
    'key42294': 'value7902',
    'key79994': 'value82844',
    'key72269': 'value85234',
    'key60502': 'value64269',
    'key65455': 'value77618',
    'key75573': 'value25110',
    'key13234': 'value2523',
    'key22295': 'value47907',
    'key54880': 'value35143',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Cynthia Taylor',
    'address': '8310 Rice Cliff\nWest Morganchester, VA 12718',
    'text': 'Allow note situation world. Available fund able part ever thousand. Protect candidate whom effect simple some. Those region happen parent rise.\nModel near director executive. We free put set among.',
    'email': 'christianchandler@example.org',
    'phone_number': '001-342-726-0729',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'William Harris',
    'David Lewis',
    'Tracy Tucker',
],
    'json': {
    'name': 'Justin Turner',
    'address': '3601 Brittney Fort\nWest Patriciastad, MP 79343',
},
    'key18040': 'value16550',
    'key48377': 'value47434',
    'key58623': 'value30875',
    'key77186': 'value51951',
    'key53771': 'value14531',
    'key53346': 'value29740',
    'key21519': 'value87479',
    'key79254': 'value10504',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Timothy Gomez',
    'address': '4812 Stephanie Ville Suite 553\nJulieland, TN 14286',
    'text': 'Task growth key shake road carry knowledge. Hospital them certain including. Practice dark our authority participant.\nAttack establish character staff. Hospital production change small think similar.',
    'email': 'shelleywright@example.com',
    'phone_number': '(416)412-2544x6303',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Cabrera',
    'Paula Anderson MD',
    'Mary Wiley',
],
    'json': {
    'name': 'Beth Herman',
    'address': '281 Taylor Village Apt. 982\nJennifermouth, NM 98124',
},
    'key62608': 'value65263',
    'key36398': 'value92558',
    'key30834': 'value65077',
    'key92276': 'value47792',
    'key39503': 'value55425',
    'key24286': 'value63822',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Sara Mcclain',
    'address': '8288 Davis Club Suite 278\nHeidimouth, AK 06145',
    'text': 'Perhaps return become weight view black. That task better side tree. Choice will trial glass culture wish question.\nTruth former we PM. Parent recently action commercial almost degree.',
    'email': 'joe34@example.com',
    'phone_number': '001-647-205-1723x1018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brian Daniels',
],
    'json': {
    'name': 'Eric Dominguez',
    'address': '52412 Johnson Island Suite 865\nSouth Paigemouth, ND 45035',
},
    'key74785': 'value7068',
    'key82561': 'value18005',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Ryan Allen',
    'address': '2314 Welch Fall\nDanahaven, OK 68360',
    'text': 'Memory grow almost much ten laugh only. Actually our mission nothing late.\nMy woman put herself.',
    'email': 'jonesanthony@example.com',
    'phone_number': '331.639.5836x86340',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Archer',
    'Daniel Sherman',
    'Elizabeth Juarez',
    'Lisa Marquez',
    'Richard King',
],
    'json': {
    'name': 'Joshua Weiss',
    'address': 'USNS Johnson\nFPO AA 69829',
},
    'key59143': 'value3401',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Frank Woodard',
    'address': '731 Matthew Motorway\nBurkeville, KS 33568',
    'text': 'One pick buy role skin which project race. Her arm close amount become food author free.\nRaise Mrs social but. Between it doctor his. Significant shake message leave least television doctor.',
    'email': 'kimberlystone@example.org',
    'phone_number': '(876)452-7913',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Heather Delgado',
],
    'json': {
    'name': 'Andrew Harmon Jr.',
    'address': '00240 David Plain Suite 176\nClaytonfurt, IL 59404',
},
    'key16101': 'value45044',
    'key3925': 'value15280',
    'key20820': 'value22524',
    'key949': 'value13134',
    'key62223': 'value69614',
    'key51843': 'value44213',
    'key33484': 'value26554',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Jason Torres',
    'address': '1825 Davis Island\nNew Lisa, WI 38348',
    'text': 'Win capital important hair behind himself amount. Citizen just new smile that. Republican close shake soon real yeah majority listen.',
    'email': 'sotojohn@example.com',
    'phone_number': '615.775.3489',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Smith',
    'Brittney Wright',
    'Russell Farmer',
    'Timothy Hernandez',
    'Michelle Flores',
    'Debbie Larsen',
    'Diana Jones',
    'Tina Bush',
    'Donald Lozano',
],
    'json': {
    'name': 'Craig Ramirez',
    'address': '1603 David Extensions Suite 719\nJonathanshire, DC 48883',
},
    'key81410': 'value75514',
    'key39907': 'value6998',
    'key2118': 'value31193',
    'key16697': 'value9041',
    'key73827': 'value50632',
    'key73012': 'value48768',
    'key45711': 'value1930',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Daniel Cohen',
    'address': '16905 Nichols Field Suite 201\nLake Emilyshire, NV 43783',
    'text': 'Certain very design seven support. Modern leg reality want crime serve country.\nHit arm address institution Democrat none its. Kid kid after key. Important cut leave window wind general.',
    'email': 'nelsonmichael@example.net',
    'phone_number': '001-958-461-8995x588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl Nguyen',
    'Teresa Fisher',
    'Joshua Cruz',
    'Michael Chambers',
    'Kim Thomas',
    'Maria Morris',
    'Craig Savage',
    'Amber Taylor',
    'Bryan Thompson',
],
    'json': {
    'name': 'Jennifer Garcia',
    'address': '44331 Gwendolyn Spring\nWest Stevefurt, CA 94840',
},
    'key96821': 'value99867',
    'key91797': 'value80879',
    'key97750': 'value29111',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Kari Frost',
    'address': '4225 Blair Flats Apt. 759\nMarqueztown, OH 16064',
    'text': 'Shoulder sit skill letter. Today laugh read manage catch subject. Perhaps politics deal away.\nOffice first member risk quality mouth. Hour drive both phone.',
    'email': 'danielmurphy@example.org',
    'phone_number': '(998)586-1469',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Suzanne Jones',
    'Wesley Huang',
    'Cheryl Flores',
    'Colleen Ramirez',
    'Michelle Benton',
    'Justin Herrera',
    'Ryan Ramirez',
    'Aaron Brown',
    'Jeffery Alvarez',
],
    'json': {
    'name': 'Adam Anderson',
    'address': '098 Robin Cape Apt. 079\nBernardchester, AS 57345',
},
    'key88905': 'value7563',
    'key79193': 'value51121',
    'key53783': 'value52577',
    'key26421': 'value15665',
    'key66605': 'value95398',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Anthony Benson',
    'address': 'USS Davis\nFPO AP 62247',
    'text': 'Lead process parent field religious walk knowledge capital. Any recently popular different manage age movie.',
    'email': 'klewis@example.org',
    'phone_number': '7694062765',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Juan Lee',
    'Scott Black',
    'Lisa Vargas',
    'Ricardo West',
    'Melanie Gentry',
    'James Sharp',
    'Elizabeth Fitzgerald',
],
    'json': {
    'name': 'Taylor Rodriguez',
    'address': 'PSC 2821, Box 2065\nAPO AP 74025',
},
    'key65751': 'value2209',
    'key29572': 'value76389',
    'key3986': 'value86271',
    'key33487': 'value26494',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Fred Sanchez',
    'address': '566 Nelson Lights\nBarbaramouth, AK 38398',
    'text': 'Technology administration detail doctor prepare campaign.\nFirst meet amount it necessary size. Rather lawyer crime shoulder feel peace.',
    'email': 'alexis14@example.net',
    'phone_number': '(944)243-8682x2625',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cristian Cooley',
    'James Abbott',
    'Audrey Mcdonald',
    'Mary Taylor',
    'Brenda Reese',
    'Ernest Salinas',
    'Melissa Davis',
    'Mary Stewart',
],
    'json': {
    'name': 'Lynn Andrews',
    'address': '809 Erin Street\nSouth John, NY 16670',
},
    'key11216': 'value90214',
    'key61442': 'value63350',
    'key93595': 'value81746',
    'key90716': 'value50998',
    'key36802': 'value18233',
    'key9418': 'value1330',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Tyler Lee',
    'address': '71746 Brian Island\nWest Jeffreyhaven, PW 18486',
    'text': 'Marriage hand grow begin move herself. Seven how keep concern few water. Pm week clearly left article.\nThis agency must skill. Indeed fly hospital important PM research. Still meet article far.',
    'email': 'gomezmiranda@example.org',
    'phone_number': '+1-780-427-9623x87770',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Claire Kelly',
    'Dawn Reese',
    'Scott Nguyen',
    'Kathryn Keith',
    'Mia Gordon',
    'Doris Jackson',
    'Daniel Carter',
    'Jenna Huynh',
],
    'json': {
    'name': 'Elizabeth Delacruz',
    'address': '2600 William Pine Suite 626\nMonicahaven, WY 99308',
},
    'key26828': 'value51845',
    'key56198': 'value81920',
    'key11811': 'value6723',
    'key38954': 'value34581',
    'key1614': 'value5713',
    'key50746': 'value86068',
    'key54360': 'value52512',
    'key79242': 'value45224',
    'key30494': 'value92258',
    'key52930': 'value57790',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Shannon Johnson',
    'address': '650 Ashley Brooks\nSouth Tamiville, NC 01409',
    'text': 'Up happy notice from their federal. Husband current both learn open. Concern risk before significant get interest lose economy. Once get have own north.\nHouse cell field as. Picture ever clear sea.',
    'email': 'qwilson@example.com',
    'phone_number': '917.962.2734',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Ward',
    'David Hurst',
    'Zachary Gonzales',
    'Michael Hart',
    'Tony Walton',
    'Christopher Schwartz',
    'Sophia Steele',
    'Preston Lopez',
    'Tiffany Conley',
    'Jeff Johnson MD',
],
    'json': {
    'name': 'Andrew Taylor',
    'address': 'USCGC Bradley\nFPO AP 84667',
},
    'key42834': 'value54887',
    'key47679': 'value94706',
    'key84873': 'value77957',
    'key20057': 'value15897',
    'key88864': 'value68402',
    'key67956': 'value80250',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Taylor Fowler',
    'address': '0611 Aguirre Well Apt. 724\nPort Jared, VA 51731',
    'text': 'Billion rich heart all positive carry identify. Six mention second.\nOfficial keep movement send pick. Entire alone and any find former.',
    'email': 'williamscynthia@example.com',
    'phone_number': '(640)669-4620',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Fisher',
    'Joshua Curtis',
    'Jeremy Reynolds',
    'Stacey Murphy',
    'Lisa Torres',
    'Anthony Butler',
    'Wayne Perry',
],
    'json': {
    'name': 'Peter Moore',
    'address': '82950 Taylor Greens\nWest Matthew, AS 65265',
},
    'key65754': 'value72395',
    'key84209': 'value27560',
    'key8737': 'value14919',
    'key62071': 'value90949',
    'key77342': 'value65437',
    'key32899': 'value36674',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Melanie Bennett',
    'address': '9056 Gerald Island\nSouth Joshuamouth, CA 87284',
    'text': 'As democratic first change. Particularly between themselves. Answer science need admit.\nAhead city including important land well.',
    'email': 'mccannkimberly@example.net',
    'phone_number': '(692)427-3005x31403',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brenda Jones',
    'Lauren Perry',
    'Tara Gordon',
    'Craig Levine',
    'Christine Nelson',
    'Henry Castro',
    'Christopher Long',
    'Beverly Underwood',
    'Kathryn Pearson',
    'Christina Morgan',
],
    'json': {
    'name': 'Lisa Young',
    'address': '3114 Christian Parks Suite 151\nNorth Christopherbury, NC 37052',
},
    'key88513': 'value45004',
    'key98970': 'value87150',
    'key21568': 'value16147',
    'key62885': 'value59049',
    'key11530': 'value53822',
    'key85959': 'value50235',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Heather Dunn',
    'address': '71687 Johnson Cape\nSchultzmouth, MO 98122',
    'text': 'Bar particular save Mr middle several.\nAbout son that theory himself mouth. Avoid investment number free might treat. Especially skill second of eight.',
    'email': 'ldavis@example.net',
    'phone_number': '945-357-2213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Osborne',
],
    'json': {
    'name': 'Christopher Myers',
    'address': '180 Lauren Plain Suite 673\nNew John, IN 74760',
},
    'key65013': 'value14222',
    'key2990': 'value55797',
    'key42393': 'value81617',
    'key88525': 'value58482',
    'key2493': 'value8539',
    'key11561': 'value1738',
    'key58758': 'value5700',
    'key57209': 'value8726',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Maria Ochoa',
    'address': '9246 Kenneth Brook\nRussellbury, IN 96547',
    'text': 'Energy face sure suddenly throughout edge condition. Around religious drop road standard. There dinner down huge yard sea beautiful conference.',
    'email': 'lloyddenise@example.org',
    'phone_number': '(582)352-6362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Austin',
    'Scott Snyder',
    'Russell Velasquez',
    'Alexandra Mills',
    'Scott Norton',
    'Jerry Mendez',
    'Charles Navarro',
    'Yvonne James',
    'Darrell Moore',
],
    'json': {
    'name': 'Alyssa Pham',
    'address': '419 King Meadows\nSmithview, LA 78755',
},
    'key43992': 'value90098',
    'key9025': 'value49893',
    'key43377': 'value35827',
    'key37906': 'value26457',
    'key53056': 'value20417',
    'key87044': 'value57262',
    'key11334': 'value57823',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Mark Brown',
    'address': 'PSC 0346, Box 6491\nAPO AE 30415',
    'text': 'Administration pass tax theory find mean. Per suggest expert year remember common. No or girl recognize.',
    'email': 'murphymorgan@example.com',
    'phone_number': '632-467-3936x5973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Jenkins',
    'Maria Martin',
    'Michele Terry',
    'Stephanie Norris',
],
    'json': {
    'name': 'Allison Rodriguez',
    'address': '4499 Ian Unions Suite 424\nLaurentown, RI 95036',
},
    'key87268': 'value29303',
    'key30164': 'value8149',
    'key34398': 'value57913',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Kelsey Hester',
    'address': '35063 Caldwell River\nLake Karla, NJ 78001',
    'text': 'Director skill then eye teach card military.\nBlue marriage start hotel. Kind participant home. Water himself two rate doctor know.',
    'email': 'thompsonfrank@example.org',
    'phone_number': '715.918.5633x6446',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elaine Gilbert',
    'Glenn Bryant',
    'Wendy Morgan',
    'Amber Day',
    'Steve Terrell',
    'Jessica Davis',
    'Ms. Emily Long',
    'Lauren Burton',
    'Heather Ward',
    'Chloe Barker',
],
    'json': {
    'name': 'Steven Contreras',
    'address': '384 Cook Hills\nTimothyview, MS 51331',
},
    'key97869': 'value87183',
    'key75295': 'value33660',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'William Barnett',
    'address': '6065 Lee River Apt. 505\nEast Monica, PR 37274',
    'text': 'Between parent stay when their require half. War second house bank tell nice follow great.\nSend ready recently recognize speak. President since end hope clear culture reach.',
    'email': 'xsanders@example.org',
    'phone_number': '7392024561',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Dylan Green',
    'Ryan Williams',
    'Wayne Avery',
    'Anthony Roberts',
    'Deborah Hunter',
],
    'json': {
    'name': 'Olivia Hendrix',
    'address': '093 Orozco Trail Suite 763\nChristineton, MT 41532',
},
    'key11671': 'value28515',
    'key16765': 'value69505',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Kyle Gentry',
    'address': '6171 Shannon Cliff\nBrandifort, DE 33423',
    'text': 'These style firm certain. Truth old material baby.\nWord policy fund news. Population fish agent tree clear region. Top page family enter industry born if. Them politics sport.',
    'email': 'greenbreanna@example.org',
    'phone_number': '(890)227-8961x08072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jack Doyle',
    'Nicholas Cobb',
    'Amber Melendez DVM',
    'Chelsea Morris',
    'Jessica Pierce',
    'Steven Turner',
    'Elizabeth Fisher',
    'Ashley Jimenez',
],
    'json': {
    'name': 'Paige Brown',
    'address': '3052 Smith Spurs\nWest Teresa, PA 46612',
},
    'key35347': 'value24866',
    'key3069': 'value10071',
    'key58730': 'value76606',
    'key65245': 'value10670',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Audrey Stevens',
    'address': '421 Kidd Bridge Apt. 092\nLeahstad, NV 69609',
    'text': 'Goal their type really type difference. Attorney just study boy fine through. See green suggest alone high until.',
    'email': 'david86@example.net',
    'phone_number': '001-294-226-6203x885',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Luis Guzman',
    'Derek Keller',
    'Elizabeth Jimenez',
    'Ryan Moss',
    'Matthew Villarreal',
],
    'json': {
    'name': 'Dr. Haley Pierce',
    'address': '85339 Vincent Dam Suite 427\nLongland, NM 76422',
},
    'key19501': 'value32063',
    'key18704': 'value82462',
    'key97090': 'value39687',
    'key13130': 'value92195',
    'key60954': 'value70555',
    'key20204': 'value9125',
    'key77221': 'value54906',
    'key63485': 'value88846',
    'key48793': 'value80494',
    'key18582': 'value14231',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'William Silva',
    'address': '97622 Abigail Camp\nKennethport, SC 76545',
    'text': 'Get number artist be. Conference land tax single. Live clearly with relationship something.',
    'email': 'morriskrista@example.com',
    'phone_number': '493-701-2320x52047',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Brandt',
    'Stephen Vazquez',
    'Victoria Smith',
    'Andre Lewis',
    'Robert Boyle',
    'Emily Cummings',
],
    'json': {
    'name': 'Joseph Owens',
    'address': '3264 Morgan Crossroad Suite 428\nBassfurt, ID 83807',
},
    'key54354': 'value43134',
    'key59515': 'value43576',
    'key98310': 'value99447',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Carolyn Lane',
    'address': '356 Flores Crescent\nPort Deborah, SC 21247',
    'text': 'Day shake word thus age. Laugh executive loss foot. Program your environmental.',
    'email': 'jennaanderson@example.net',
    'phone_number': '+1-562-257-9768x83955',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Adams',
],
    'json': {
    'name': 'Savannah Tyler',
    'address': '4895 Jones Springs\nSouth Henrymouth, AL 73623',
},
    'key84932': 'value59665',
    'key85545': 'value41717',
    'key7888': 'value97067',
    'key3447': 'value15097',
    'key11818': 'value91882',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Jasmine Graham',
    'address': 'Unit 3209 Box 0096\nDPO AE 04987',
    'text': 'Author change subject painting security former. Everything common director. Else bill art everything happy red pull remember.',
    'email': 'ljenkins@example.com',
    'phone_number': '262-213-0642x43016',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Cindy Donaldson MD',
    'Bethany Evans',
    'Johnathan Dickerson',
    'Mark Owens',
],
    'json': {
    'name': 'Jason Moore',
    'address': '5116 Hill Isle Suite 936\nHallberg, SD 19340',
},
    'key13165': 'value56478',
    'key58834': 'value551',
    'key19844': 'value58941',
    'key39148': 'value52127',
    'key29000': 'value28235',
    'key92174': 'value38181',
    'key51316': 'value63950',
    'key18338': 'value29456',
    'key6830': 'value1142',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Sheila Wright',
    'address': '85165 Mendez Plaza\nLake Bethanychester, OR 15887',
    'text': 'Various agent central why tree yet. Prepare mind win thing reach record friend. Rise certain foreign tax would down.',
    'email': 'johnrios@example.net',
    'phone_number': '(653)817-3235x6067',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Woods',
    'Michelle Li',
    'Seth Garcia',
    'Scott Hall',
    'Timothy Fuentes',
    'Brooke Giles',
    'Rebecca Klein',
],
    'json': {
    'name': 'Darren Ray',
    'address': '147 Connor Cove\nGeraldton, PR 44783',
},
    'key41542': 'value41004',
    'key89478': 'value8541',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Elizabeth Williams',
    'address': '7174 Garcia Pass Apt. 606\nNunezmouth, OR 36746',
    'text': 'Material fly finally type. Lawyer several short suggest art enjoy. And suggest shake sit light son.\nInterview heart miss carry too rule every. Man think history customer.',
    'email': 'blackkaren@example.org',
    'phone_number': '+1-951-516-2909',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Connie Dyer',
],
    'json': {
    'name': 'Kerry Torres',
    'address': '2688 Dustin Landing Suite 772\nNorth Steven, WY 61916',
},
    'key87064': 'value77309',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Miss Anita Lyons',
    'address': '49717 Foster Rest\nNorth Andrewtown, CA 51521',
    'text': 'Threat account student out marriage cover itself reveal. Story when available soon.\nTo suddenly interest hour that author opportunity.',
    'email': 'qsmith@example.net',
    'phone_number': '+1-924-800-0735x130',
    'array_int_dynamic': [
    35770,
],
    'array_varchar_dynamic': [
    'Katherine Keller',
    'Kelly Green',
    'Laura Boone',
    'Christopher Cole',
    'Nicholas Smith',
],
    'json': {
    'name': 'Bridget Clark',
    'address': '26261 Nunez Ford Suite 548\nSextonburgh, MI 96301',
},
    'key31156': 'value55023',
    'key35627': 'value91920',
    'key40668': 'value45146',
    'key35335': 'value48136',
    'key38852': 'value29725',
    'key61977': 'value59100',
    'key84498': 'value57076',
    'key6545': 'value63330',
    'key4817': 'value47009',
    'key16423': 'value72864',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Perry Gibson',
    'address': '517 Christian Groves Suite 706\nChristinehaven, ME 90563',
    'text': 'Exist rise before realize bag woman effect. Public bring ability artist. That generation throughout sister base country laugh vote. Recognize smile food wife western result fear.',
    'email': 'joshua47@example.net',
    'phone_number': '2285015031',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Stewart',
    'Susan Kirby',
    'Brenda Baker',
    'Tim Hoover',
    'Taylor Guzman',
    'Janet Gordon',
    'Sarah Long',
    'Rose Hunt',
],
    'json': {
    'name': 'Daniel Robertson',
    'address': '577 Carlos Ridge Suite 725\nAnnshire, VT 13767',
},
    'key43280': 'value78058',
    'key68204': 'value83206',
    'key97129': 'value93994',
    'key96809': 'value11410',
    'key53394': 'value69591',
    'key8919': 'value58008',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Lisa Shields',
    'address': '2108 Garcia Road Apt. 506\nStevenland, SD 98956',
    'text': 'Field tell model street. None stay create really doctor.\nStop seek too law. Road little service two carry action whether.',
    'email': 'caitlingonzales@example.net',
    'phone_number': '765.663.3970x93284',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Derrick Gilmore',
    'Michael Gonzales',
    'Kenneth Costa',
],
    'json': {
    'name': 'Dustin Dalton',
    'address': '18883 Cody Lodge Apt. 901\nLake Jacquelinefort, MO 18680',
},
    'key17916': 'value76743',
    'key35234': 'value89911',
    'key44703': 'value78140',
    'key39480': 'value53982',
    'key77771': 'value45440',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Sierra Watkins',
    'address': '32587 Lopez Well\nNorth Robertville, KY 72978',
    'text': 'Clear kid place. What home take leg capital.\nWell life itself address PM. Hair agent own no certainly watch of throughout.',
    'email': 'rmurphy@example.org',
    'phone_number': '566.371.7868x716',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Cooper',
    'Joseph Webb',
],
    'json': {
    'name': 'Cynthia Gilbert',
    'address': '60752 Sean Station\nDonaldport, RI 99457',
},
    'key29588': 'value81971',
    'key20667': 'value74514',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Philip Oliver Jr.',
    'address': '2077 Shepherd Rapid Suite 240\nLake Victoria, GA 30736',
    'text': 'Become forget team wall small push couple ready. Provide gas couple different response.\nTest employee name interest many field. Role can market. Decision writer second likely organization.',
    'email': 'barkererik@example.org',
    'phone_number': '684.898.0402',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Holly Lang',
    'Tyler Clark',
],
    'json': {
    'name': 'Luis Harmon',
    'address': '7059 Krista Summit Apt. 274\nEast Loganmouth, WA 20773',
},
    'key52933': 'value20863',
    'key19531': 'value21601',
    'key34156': 'value10426',
    'key99038': 'value95019',
    'key41396': 'value6446',
    'key37926': 'value24574',
    'key62520': 'value90291',
    'key33953': 'value20809',
    'key51162': 'value81330',
    'key60748': 'value66844',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Shane Brown',
    'address': '84061 Miller Path Apt. 604\nColemanfurt, NJ 86030',
    'text': 'Make cultural big pass stay necessary. Walk station majority pretty. American change probably number defense.',
    'email': 'gregory21@example.com',
    'phone_number': '+1-491-591-5093x99741',
    'array_int_dynamic': [
    75454,
],
    'array_varchar_dynamic': [
    'Crystal Thompson',
    'Kimberly Bailey',
    'Thomas Weber',
    'Gabriel Jordan',
    'Rodney Marquez',
],
    'json': {
    'name': 'Jermaine Brown',
    'address': '84091 Harvey Bridge\nRobertchester, AZ 04226',
},
    'key83694': 'value82199',
    'key88008': 'value16335',
    'key14231': 'value80961',
    'key75081': 'value13013',
    'key4842': 'value70004',
    'key10785': 'value62230',
    'key21331': 'value70278',
    'key35941': 'value25533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Cole Wyatt',
    'address': '1345 David Camp Apt. 522\nMorrisview, FM 27750',
    'text': 'Up respond recent positive couple arm. That order low group. Day single challenge ask remain. Back another prove power agree.',
    'email': 'ggolden@example.org',
    'phone_number': '632-802-9076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Steven Tate',
    'Alicia Jenkins',
    'Richard Medina',
],
    'json': {
    'name': 'Dalton Gomez',
    'address': '7306 Lawson Neck Apt. 025\nLaurieland, IA 57349',
},
    'key21375': 'value81129',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Steven Hayes',
    'address': '5806 Richard Prairie Apt. 431\nBernardville, NJ 92314',
    'text': 'Wife business about yeah. Your situation build often fund may. Event world doctor one event impact.\nBegin test blue catch yard decide now. Player month section oil. Left cut on leader.',
    'email': 'adamsstephanie@example.com',
    'phone_number': '304.551.0238x3384',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Hicks',
    'Jeffrey Johnson',
    'Breanna Bright',
    'Paul Freeman',
    'Raven Sullivan',
    'Courtney Villanueva',
    'Miguel Conway',
    'Mrs. Chelsea Campbell',
    'Adam Dean',
],
    'json': {
    'name': 'Justin Williams',
    'address': '219 Chelsea Rest\nSweeneyfurt, NH 58338',
},
    'key30123': 'value70440',
    'key92350': 'value2187',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Travis Solomon',
    'address': '41551 Marshall Glen Apt. 980\nBryanfurt, IA 40514',
    'text': 'True culture my radio law forward. Hard where some artist become money order.\nHuman candidate event eight glass. Use strong well across in.\nInto safe watch. Company area instead court turn.',
    'email': 'angeladay@example.com',
    'phone_number': '280-443-5558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Foster',
    'Allison Hanson',
],
    'json': {
    'name': 'Rhonda Key',
    'address': '979 Jenkins Throughway Suite 818\nLake Madeline, LA 26543',
},
    'key30986': 'value53894',
    'key58404': 'value36065',
    'key14791': 'value68667',
    'key48818': 'value59028',
    'key33826': 'value44312',
    'key6912': 'value91774',
    'key86251': 'value58964',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Natalie Torres',
    'address': '836 Rodriguez Knoll Suite 597\nAliland, SD 21264',
    'text': 'Like present product candidate clear. Leader always reason dog. Other change far.\nSerious discuss discussion whole direction own.',
    'email': 'clayton48@example.com',
    'phone_number': '+1-879-204-0121x1533',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Mcclain',
    'Gregory Pearson',
    'Carlos Whitehead',
],
    'json': {
    'name': 'Thomas Edwards',
    'address': '1817 Wolfe Mission\nWest Vanessa, WA 39916',
},
    'key30588': 'value65902',
    'key56584': 'value74101',
    'key32670': 'value30602',
    'key71726': 'value24181',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Paige Jones',
    'address': '822 Perry Track\nWest Karenton, UT 36213',
    'text': 'Through southern enjoy rather dream spring with. Clearly medical either. Maybe image Mrs degree.\nReflect assume if. See far bed. Machine send growth church treatment though note.',
    'email': 'rstrong@example.com',
    'phone_number': '(744)383-1998x8573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Rebekah Gomez',
    'Tara Chase',
    'Chad Munoz',
    'Donna Mendez',
    'John Austin',
],
    'json': {
    'name': 'Tammy Campbell',
    'address': '70840 Austin Extension Suite 429\nOrtizfurt, KS 22709',
},
    'key6047': 'value15052',
    'key93202': 'value19818',
    'key3020': 'value10150',
    'key36530': 'value79430',
    'key54632': 'value30989',
    'key76551': 'value98745',
    'key61624': 'value59405',
    'key24032': 'value84198',
    'key96648': 'value9285',
    'key10161': 'value81553',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Stephen Lee',
    'address': '784 Gomez Dam Apt. 327\nSouth Kari, NY 34603',
    'text': 'This onto choice yard again or.\nBecause should race also total beat three. Behavior represent act team article floor.\nBed important can language billion forward. Ok agency crime.',
    'email': 'nicolemartin@example.com',
    'phone_number': '001-927-973-3645x23022',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Coleman',
    'Rebecca Foster',
],
    'json': {
    'name': 'Nicole Becker',
    'address': '19071 Ortega Cliffs Suite 212\nZavalaview, MH 18450',
},
    'key17488': 'value1325',
    'key17358': 'value45752',
    'key13981': 'value55571',
    'key10057': 'value11937',
    'key24963': 'value49625',
    'key23182': 'value68756',
    'key6612': 'value71679',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Matthew Reese',
    'address': 'PSC 5943, Box 1848\nAPO AA 78314',
    'text': 'Anything moment rate chance half behavior. Local black produce material role suffer myself.\nRise war impact report program. Cover little century if.',
    'email': 'ykelly@example.com',
    'phone_number': '001-385-617-5960x893',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Donna Castillo',
    'Michelle Jones',
    'Melissa Stone MD',
    'Sarah Bass',
],
    'json': {
    'name': 'Adam Levine',
    'address': '7930 Martin Stravenue Apt. 572\nLopezborough, NC 09462',
},
    'key63899': 'value59053',
    'key43172': 'value64550',
    'key67065': 'value74981',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Susan Phillips',
    'address': '343 Roberts Row\nTammyfort, PR 27143',
    'text': 'No act under record especially society past decision.\nHotel or write brother cover. Level some let rock sure present news. News race later tonight wife.\nInvolve answer cover door boy front.',
    'email': 'douglasfischer@example.com',
    'phone_number': '+1-727-842-5269',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Soto',
    'Darren Cannon',
    'Jesse Garrison',
    'Robin Cox',
    'Christopher Morales',
    'Tonya Mclaughlin',
],
    'json': {
    'name': 'Autumn Perry',
    'address': '77679 Le Bypass Apt. 113\nPort Sandra, NY 72568',
},
    'key82061': 'value67706',
    'key65363': 'value55284',
    'key40195': 'value54450',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Steven Willis',
    'address': '4203 Miller Mission Apt. 174\nThomasfurt, AS 54629',
    'text': 'Mention any wind face. Prepare successful field writer.\nHundred them box film quite response heavy research. Home sing man. Old whatever writer garden free happy leader.',
    'email': 'sanfordlawrence@example.net',
    'phone_number': '7478958380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Horn',
    'Tyler Peterson',
    'Alexis Rosales',
    'Russell Fernandez',
    'Jillian Rogers',
    'Francisco Miller',
    'Valerie Robinson',
],
    'json': {
    'name': 'Vanessa Fitzgerald',
    'address': '619 Shaw Club\nCarterborough, ND 62849',
},
    'key16672': 'value83749',
    'key45487': 'value21042',
    'key82551': 'value89546',
    'key39616': 'value43688',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Benjamin Bennett',
    'address': '09269 William Dale Apt. 715\nNorth Lisaville, IN 39603',
    'text': 'Admit garden draw may. Better majority watch game policy notice.\nYeah building area fight.',
    'email': 'jamesmarshall@example.org',
    'phone_number': '(949)265-3856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Turner',
    'Tamara Hamilton',
    'Sherry Mcgrath',
    'Jeremy Scott',
    'Summer Alvarado',
    'Cassandra Good',
    'Joseph Smith',
    'Lisa Saunders',
    'Aaron Moon',
    'Daniel Cook',
],
    'json': {
    'name': 'Christopher Davis',
    'address': '7601 Joshua Vista Suite 544\nSouth Susanfurt, SC 84399',
},
    'key46580': 'value16925',
    'key91151': 'value22027',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Donna Rowland MD',
    'address': '52826 Regina Meadows Apt. 610\nPort Rodney, ID 84363',
    'text': 'Scene fill later court policy face bed. Billion skill feeling debate stage might.\nEnjoy hour imagine floor week. Senior current bring his team ago rise. This large outside series.',
    'email': 'williamgarcia@example.net',
    'phone_number': '001-290-968-2835x99075',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Espinoza',
    'Erin Bridges',
    'Mark Harris',
    'Jessica Flynn',
    'Susan Ross',
    'Dale Lewis',
    'Amy Medina',
    'Vanessa Lawrence',
    'Bradley Medina',
],
    'json': {
    'name': 'Daniel Webb',
    'address': '2436 Alvin Lights\nDuanefort, MA 73267',
},
    'key66064': 'value70356',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Bradley Anderson',
    'address': 'Unit 5842 Box 3730\nDPO AE 77670',
    'text': 'Soldier situation once wide many push tonight. Listen between ok space activity. Right impact resource hope factor economy bag.',
    'email': 'erichansen@example.org',
    'phone_number': '(209)783-0610x05061',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mary White',
    'Johnny Padilla',
],
    'json': {
    'name': 'Tabitha Rice',
    'address': '113 Nelson Stream\nLake Davidshire, MT 08367',
},
    'key9394': 'value24858',
    'key76174': 'value48500',
    'key27652': 'value54552',
    'key54381': 'value7290',
    'key37670': 'value76020',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Christopher Frank',
    'address': 'PSC 6288, Box 7486\nAPO AA 09429',
    'text': 'Billion nature large travel simply south top.\nThree color level find together police him.\nRealize anyone close yard yourself.',
    'email': 'erinarmstrong@example.com',
    'phone_number': '+1-207-368-0829x896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'William Vang',
    'Joseph Green',
    'Rachel Hickman MD',
],
    'json': {
    'name': 'Eugene Matthews',
    'address': '5790 Mcintyre Trace Suite 459\nRyanport, AL 12858',
},
    'key81079': 'value66916',
    'key88008': 'value84497',
    'key4642': 'value6450',
    'key45424': 'value72513',
    'key35476': 'value12692',
    'key63195': 'value94568',
    'key97805': 'value3421',
    'key65693': 'value69040',
    'key97087': 'value64294',
    'key35016': 'value78674',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Christine Schmitt',
    'address': '58426 Laura Forks\nZacharyfurt, OR 90706',
    'text': 'Reduce firm her debate thank. Support look a indicate speak. Section wish sing new raise.\nNever notice maintain room available rise service bit. Student process share.\nNever plan cut wait cold.',
    'email': 'joseph54@example.net',
    'phone_number': '(283)819-7682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Steven Fry',
    'Collin Stout',
    'Jasmine Tran',
    'Frederick Levine',
    'Dennis Wiggins',
    'Ernest Padilla',
    'Emily Zamora',
    'Mark Price',
],
    'json': {
    'name': 'Brittany Russell',
    'address': '39249 Henderson Expressway\nSouth Autumnburgh, CA 75460',
},
    'key12969': 'value57213',
    'key97444': 'value85226',
    'key10916': 'value10421',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Caitlin Swanson',
    'address': '07585 Duncan Ford\nLake Michelle, VA 88859',
    'text': 'Everyone until rock.\nInternational participant she material production where onto. Sign site even community around after thus. Soldier plant design difference accept one without.',
    'email': 'edward59@example.net',
    'phone_number': '001-223-892-9713x21739',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Olivia Watson',
],
    'json': {
    'name': 'Crystal Miller',
    'address': '0787 Knox Unions\nNorth John, MO 76521',
},
    'key26884': 'value95220',
    'key58348': 'value89511',
    'key69473': 'value82822',
    'key52047': 'value59251',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Andrew Jones',
    'address': 'USNV Graham\nFPO AA 50601',
    'text': 'Democratic among east fight worry sometimes air. Performance level note down trade. System skill thousand possible.',
    'email': 'jordancheryl@example.org',
    'phone_number': '598.504.6758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Diana Martinez',
    'Thomas Reyes',
    'Alexa Gardner',
    'Leslie Garrison',
    'John Collins',
    'Kendra Manning',
    'Rebecca Barnes',
    'Jamie Moran',
],
    'json': {
    'name': 'Ronald Scott',
    'address': '5356 Wayne Ramp\nSouth Joseph, TN 27308',
},
    'key65657': 'value48606',
    'key48092': 'value4253',
    'key99225': 'value25468',
    'key78022': 'value68193',
    'key24522': 'value34296',
    'key59981': 'value30938',
    'key44944': 'value91173',
    'key45874': 'value57004',
    'key54833': 'value46736',
    'key62150': 'value27011',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Mrs. Donna Davis MD',
    'address': '536 Michael Stream Suite 988\nLeeshire, MP 33315',
    'text': 'Without join discuss great degree cell thought only. Current able plan administration exactly energy fall. Institution agency prevent drive hand change.',
    'email': 'sandracabrera@example.com',
    'phone_number': '(986)353-6188x40424',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl Munoz',
    'Samantha Winters',
    'Judith Hooper',
    'Dustin Daniels',
    'Gloria Evans',
    'Alexandria Williams',
    'Mr. Steven Trevino PhD',
    'Catherine Harris',
    'Terry Marshall',
],
    'json': {
    'name': 'Tyler Daugherty',
    'address': '4111 Silva Fort Suite 253\nMarisaberg, SC 54058',
},
    'key37684': 'value6883',
    'key40753': 'value88174',
    'key66830': 'value34568',
    'key12223': 'value2107',
    'key65689': 'value25485',
    'key20067': 'value27984',
    'key93034': 'value39812',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Jonathan Jones',
    'address': '7420 Patrick Dale Apt. 918\nGraymouth, WI 22814',
    'text': 'Seven order page type. From cell section president along.\nTrial night possible. Media impact money hair imagine.',
    'email': 'reginaweeks@example.net',
    'phone_number': '8979760906',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Linda Randall',
    'Dustin Alexander',
    'Brittany Oconnor',
    'Joseph Faulkner',
],
    'json': {
    'name': 'Emily Dixon',
    'address': '926 Owens Trail\nEast Brendatown, RI 36075',
},
    'key56372': 'value61780',
    'key17151': 'value23114',
    'key85114': 'value17203',
    'key38220': 'value22871',
    'key38337': 'value5327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Robert Armstrong',
    'address': 'PSC 4871, Box 9457\nAPO AE 76995',
    'text': 'Its reflect any grow reach significant break. Individual standard understand generation certainly. Official development range already.',
    'email': 'sherrigarcia@example.net',
    'phone_number': '418-512-8014x0892',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Heather Powers',
    'Emily Jacobson',
    'Jacqueline Smith',
    'Charles Nelson',
    'Lindsey Jacobs',
    'Brian Smith',
    'Michael Johnson',
    'Samuel Gonzalez',
],
    'json': {
    'name': 'Deborah Moore',
    'address': '356 Tammy Plain Suite 764\nNealfurt, WA 02490',
},
    'key28742': 'value49617',
    'key3414': 'value79925',
    'key80590': 'value38242',
    'key67697': 'value79221',
    'key67084': 'value56747',
    'key87375': 'value97009',
    'key72848': 'value25575',
    'key63119': 'value9263',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Ricardo Chen',
    'address': '87965 William Haven Apt. 516\nRebekahberg, VT 22118',
    'text': 'Itself right far system drug subject. Open agree view health deep fast do cultural. Name among western mean store per.\nHand agree man usually.',
    'email': 'pjenkins@example.net',
    'phone_number': '2495153040',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tim Bright',
    'Tracy Johnson',
],
    'json': {
    'name': 'Dr. Emma Caldwell DVM',
    'address': '77446 Boyd Walk\nJeremybury, CO 46210',
},
    'key16628': 'value95371',
    'key9417': 'value87854',
    'key91154': 'value90375',
    'key40373': 'value13960',
    'key67969': 'value98249',
    'key62136': 'value21506',
    'key23020': 'value61293',
    'key64556': 'value96955',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Christopher Frazier',
    'address': '133 Ibarra Gardens\nNorth Mark, IL 92353',
    'text': 'Visit type feeling between case military try. War happen activity floor card those. Right father who act community.\nFigure major end must. New commercial bag example.',
    'email': 'deborahjackson@example.com',
    'phone_number': '+1-334-387-3009x70355',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Salazar',
    'Cody Duffy',
],
    'json': {
    'name': 'Tracy Gross',
    'address': 'USCGC Weber\nFPO AP 17924',
},
    'key82213': 'value96301',
    'key48453': 'value32801',
    'key56988': 'value39327',
    'key63091': 'value80215',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Jason Robertson',
    'address': '5695 Douglas Manor Suite 589\nWilliamsstad, FL 01435',
    'text': 'Heart enter get two ahead test now wait. Nature language thing final magazine work. Change sometimes must someone pretty often fear.',
    'email': 'smithdonald@example.com',
    'phone_number': '(266)859-8846x696',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marc Gardner',
    'Robin Kelly',
    'Kathleen Maldonado',
],
    'json': {
    'name': 'Craig Gomez',
    'address': '45607 Hernandez Rue\nPort Renee, IN 66357',
},
    'key39507': 'value82479',
    'key20292': 'value84850',
    'key34488': 'value86387',
    'key29190': 'value82025',
    'key67327': 'value80227',
    'key31462': 'value39667',
    'key80182': 'value61200',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Chelsea Bell',
    'address': '92151 Watts Prairie Suite 546\nPort Carmen, NC 79593',
    'text': 'Congress some program prepare sport any. Benefit see social drop single behavior town evening. Others member fill say. Discussion Mrs current cell several somebody.',
    'email': 'russellchristina@example.net',
    'phone_number': '(223)963-5611x1995',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Adrienne Wu',
    'Lori Bishop',
    'Michelle Brown',
    'Monica Mathews',
    'Linda Hicks',
    'Tiffany Williams',
    'Angela Johnson',
    'James Owen',
    'Johnny Anderson',
    'Christopher Conley',
],
    'json': {
    'name': 'Patricia Lee',
    'address': '6346 Campbell Streets\nScotttown, GA 25288',
},
    'key57633': 'value85733',
    'key701': 'value80967',
    'key85968': 'value55627',
    'key57734': 'value17745',
    'key87674': 'value2705',
    'key31855': 'value18023',
    'key48697': 'value978',
    'key89257': 'value30',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Michael Coffey',
    'address': '13905 Guzman Terrace Apt. 889\nKellermouth, WA 54322',
    'text': 'Really fact capital college. View various test. Force very fire quickly.\nSeek particularly enter glass.\nAppear mother herself chair set deep long. Weight me long most meet.',
    'email': 'russellallen@example.com',
    'phone_number': '290-873-3957',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Green',
    'Autumn Silva',
    'Andrew Burton',
],
    'json': {
    'name': 'Erica Blackwell',
    'address': '4812 Todd Cliff Apt. 224\nLake Manuelfort, PA 84891',
},
    'key13252': 'value99668',
    'key98335': 'value53210',
    'key34473': 'value37598',
    'key64202': 'value72722',
    'key26562': 'value66150',
    'key29521': 'value16263',
    'key91230': 'value63780',
    'key93947': 'value19953',
    'key47427': 'value38351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Craig Le',
    'address': '3222 Krystal Village Suite 436\nMartinborough, IL 88493',
    'text': 'New happy long guess top go. International get vote.\nBox offer western analysis audience know. She myself debate religious sit sure. Stock find of race each put.',
    'email': 'tperez@example.net',
    'phone_number': '+1-751-409-3896x77372',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Rose Hobbs',
    'Robert Clark',
],
    'json': {
    'name': 'Michelle Thompson',
    'address': '537 Valerie Islands\nLake Makayla, LA 08317',
},
    'key72324': 'value35770',
    'key93720': 'value62360',
    'key68714': 'value19404',
    'key31150': 'value35247',
    'key28572': 'value48964',
    'key56836': 'value68200',
    'key65646': 'value65247',
    'key5748': 'value53183',
    'key67242': 'value48094',
    'key45299': 'value83855',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Jessica Johnson',
    'address': '377 Mcfarland Alley\nSmithshire, VT 39394',
    'text': 'Mother network morning brother evidence fill. Pretty full strong type. Share number set serious improve forward.\nThey anyone improve door better. Base high own she.',
    'email': 'cody71@example.net',
    'phone_number': '960-264-4615',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James Taylor',
    'Stephen Jones',
    'Stephanie Andrews',
    'Lauren Campbell',
    'Jeffrey George',
],
    'json': {
    'name': 'Michael Day',
    'address': '375 Daniel Lodge Apt. 243\nMoranview, MA 02973',
},
    'key35536': 'value10449',
    'key48262': 'value2344',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Jason Pittman',
    'address': '7024 Jennifer Ford\nTeresaville, MT 04539',
    'text': 'Develop per difficult environment nearly. Life city everything religious production choice. We service while stuff per. Responsibility deal current should car usually support.',
    'email': 'richard79@example.com',
    'phone_number': '001-263-782-1263x2069',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Macdonald',
    'Nancy Choi',
    'Jessica Ferguson',
    'Justin Donovan',
    'Heather Fox',
    'Tyler Hughes',
    'Erica Marshall',
    'Lauren Huffman',
    'Anthony Frank',
    'David Colon',
],
    'json': {
    'name': 'Bradley Thomas',
    'address': '0367 Miller Locks Apt. 733\nPerkinsland, LA 09902',
},
    'key55235': 'value45537',
    'key41133': 'value13540',
    'key46382': 'value33047',
    'key71554': 'value71269',
    'key12877': 'value30192',
    'key93601': 'value3979',
    'key9774': 'value49369',
    'key58929': 'value19311',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Patricia Waller',
    'address': '62896 Taylor Streets\nPort Timothy, DC 66904',
    'text': 'Bag impact season doctor miss station. Game first kid if heart protect local. Rate maintain baby prove nature.',
    'email': 'schavez@example.net',
    'phone_number': '+1-605-307-2775x57396',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Lee',
    'Cathy Stone',
    'Jonathan Carpenter',
    'Robert Greene',
    'Scott Brown',
],
    'json': {
    'name': 'Jasmine Lambert',
    'address': '84949 Angela Groves Suite 949\nTaylorshire, MT 18852',
},
    'key1979': 'value56506',
    'key57174': 'value85471',
    'key69373': 'value68685',
    'key71552': 'value53117',
    'key34372': 'value35645',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Sydney Brown',
    'address': '93200 Sandy Spur\nMichelleshire, CA 38064',
    'text': 'Behavior newspaper remember wish upon half example consider. Ahead clearly indicate vote.\nCrime evening event again true movie knowledge. Everyone reveal even whom situation service no.',
    'email': 'kimberlymarshall@example.net',
    'phone_number': '(937)776-2416x7580',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Douglas',
    'Vanessa Ramirez',
],
    'json': {
    'name': 'Michael Durham',
    'address': '0112 Shannon Walk\nPort Elizabeth, WI 38696',
},
    'key53987': 'value94089',
    'key54927': 'value61246',
    'key43630': 'value19117',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Ryan Pace',
    'address': '84885 Thornton Passage Apt. 489\nNixonside, GU 29370',
    'text': 'Hit enjoy else together.\nHome series agency anyone. Man type change upon think. Already family memory how leave PM ago work.',
    'email': 'moseschristine@example.org',
    'phone_number': '+1-810-593-5609x37642',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Foster',
    'Christopher Wilson',
    'Nicholas Jordan',
    'Jeffery Meyer',
    'Jesus Hart',
],
    'json': {
    'name': 'Kristin Everett',
    'address': '151 Dakota Corner\nLopezview, DE 87339',
},
    'key51471': 'value70832',
    'key9546': 'value24741',
    'key54716': 'value80879',
    'key280': 'value27842',
    'key61066': 'value22201',
    'key84402': 'value4166',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Jennifer Baker',
    'address': '091 Erickson Pike Suite 911\nSusanmouth, NJ 55818',
    'text': 'Public relate senior short whole picture claim voice. Above build usually however arm professional machine.\nDecision fear here may. Born thus player control.',
    'email': 'guzmantara@example.org',
    'phone_number': '+1-312-865-4709',
    'array_int_dynamic': [
    49336,
],
    'array_varchar_dynamic': [
    'Amy Pearson',
],
    'json': {
    'name': 'Crystal Perry',
    'address': 'Unit 7196 Box 9228\nDPO AE 93875',
},
    'key52492': 'value72682',
    'key95988': 'value94600',
    'key22644': 'value61053',
    'key12244': 'value23997',
    'key71244': 'value76441',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Nicole Martin',
    'address': '614 Campbell Street\nWest Richardchester, IN 83075',
    'text': 'Available to exactly. Minute major case.\nRelationship strategy force voice job. Build people option various something from deep chance.',
    'email': 'wangveronica@example.org',
    'phone_number': '(235)280-5271',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Walters',
    'Barbara Thomas',
    'Catherine Warren',
    'Susan Petty',
    'Alexis Petty',
    'Scott Williams',
    'Robert Franklin',
    'Jose Brown',
],
    'json': {
    'name': 'Jeremy Moore',
    'address': '7678 Branch Mountain\nGuerreromouth, UT 10659',
},
    'key77141': 'value55212',
    'key87981': 'value95076',
    'key13569': 'value90758',
    'key19352': 'value31506',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Melissa Watson',
    'address': '27629 Webb Rapids\nSouth Matthewhaven, WI 75582',
    'text': 'Kid type test grow deep walk. Camera marriage week field through wind deal.',
    'email': 'umartinez@example.net',
    'phone_number': '001-853-317-9036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Frank Martinez',
    'Katherine Walker',
    'Harry Carroll',
    'Kathryn Hayes',
    'David Russo',
    'James Rosales',
    'Margaret Barnett',
],
    'json': {
    'name': 'Andrew Fisher',
    'address': '3946 Jimenez Ramp Apt. 738\nWest Richard, ME 79103',
},
    'key37626': 'value40317',
    'key8018': 'value16190',
    'key53848': 'value7784',
    'key65960': 'value6712',
    'key52538': 'value19460',
    'key15653': 'value80462',
    'key46788': 'value65780',
    'key37026': 'value28032',
    'key76942': 'value57866',
    'key4014': 'value87376',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Sheena Valentine',
    'address': '45151 Marshall Cliff Apt. 555\nNorth Christina, ME 44991',
    'text': 'Site hit official name then media will easy. Face radio voice go.\nAir black low include finish represent. Least a style now explain maybe war somebody. Cell include such assume purpose article.',
    'email': 'leachelizabeth@example.org',
    'phone_number': '278.576.1506x723',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Blackwell',
    'Anthony Frye',
    'Steven Bray',
],
    'json': {
    'name': 'Barbara Bates',
    'address': '1364 Baker Plaza Suite 539\nKristenton, MN 82119',
},
    'key54336': 'value66487',
    'key40125': 'value17221',
    'key18201': 'value39602',
    'key61655': 'value39961',
    'key26726': 'value98483',
    'key52515': 'value84076',
    'key15825': 'value69207',
    'key99603': 'value20748',
    'key7956': 'value12516',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Thomas Vincent',
    'address': '63091 Brendan Knoll Suite 482\nSouth Rickyfurt, MS 04650',
    'text': 'Attorney who buy. Suddenly ok key newspaper.\nPoint popular back kitchen trial. Perform form no story end call with.',
    'email': 'andrew12@example.com',
    'phone_number': '001-634-458-0173',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alisha Cortez',
    'Denise Vazquez',
    'Ronnie Newton',
    'Hannah Davis',
    'Randall Steele',
    'Sherry Murphy',
    'April Martin',
],
    'json': {
    'name': 'Lisa Mathews',
    'address': '162 Nicole Villages Suite 545\nSonyashire, NV 37453',
},
    'key67326': 'value63624',
    'key84509': 'value63502',
    'key50998': 'value27854',
    'key68512': 'value50811',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Sarah York',
    'address': 'PSC 2465, Box 9601\nAPO AP 92132',
    'text': 'Continue father subject director feel many enjoy letter. Wrong culture gun improve heavy southern.\nOur office option recently various future find.\nTree nothing rule. Order civil send sit.',
    'email': 'patricia21@example.net',
    'phone_number': '293-474-9524x363',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Sanders',
    'Melinda Soto',
    'Miranda Kennedy',
    'Nicholas Walton',
    'Lauren Copeland',
    'James Hawkins',
],
    'json': {
    'name': 'Benjamin Richard',
    'address': '52526 Stephen Summit Suite 965\nPort Rebecca, DE 35902',
},
    'key12579': 'value20230',
    'key61450': 'value31346',
    'key16161': 'value35170',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Brandy Gillespie',
    'address': 'USNV Harper\nFPO AA 79085',
    'text': 'Base Congress feel pass between budget. Kitchen goal involve market analysis. Claim government senior defense score her common bed.\nMake listen knowledge car however deal remember.',
    'email': 'zachary60@example.net',
    'phone_number': '854.881.7628x16834',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Holt',
    'Katherine Hobbs',
    'Miss Casey Bryant',
    'Lisa Campos',
],
    'json': {
    'name': 'Summer Caldwell',
    'address': '7889 Cabrera Viaduct Apt. 144\nSharonville, CO 63405',
},
    'key35925': 'value28',
    'key5339': 'value21850',
    'key82623': 'value96301',
    'key56000': 'value80170',
    'key15773': 'value9431',
    'key51517': 'value27170',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Jodi Koch',
    'address': '93235 Camacho Plaza Suite 556\nEast Jessicaport, CA 64254',
    'text': 'Site reflect decision view big forward professor enter. Wide newspaper young baby.\nForget while easy development various fine section public. Senior scientist even. Born test real marriage until.',
    'email': 'hannahjohnson@example.net',
    'phone_number': '518-722-2944',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'William Salazar',
    'Alexis Weaver',
    'Craig Rasmussen',
],
    'json': {
    'name': 'William Levine',
    'address': '459 Justin Orchard Apt. 286\nWest Davidview, IN 69157',
},
    'key12498': 'value43935',
    'key81681': 'value57648',
    'key66447': 'value78033',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Carmen Patton',
    'address': 'USNV Young\nFPO AE 59809',
    'text': 'New security spend just catch any fish. Writer guess leg mother. Century show laugh author network.\nMovie accept surface hotel. Detail wind read TV inside scientist responsibility.',
    'email': 'michelemendez@example.com',
    'phone_number': '001-898-206-7826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Breanna Mcdaniel',
],
    'json': {
    'name': 'Diane Davis',
    'address': '193 Watson Corner\nPort Mariachester, TN 16892',
},
    'key88703': 'value34151',
    'key20045': 'value64780',
    'key48603': 'value34867',
    'key46867': 'value39616',
    'key352': 'value26680',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Mrs. Jessica Keller',
    'address': '87586 Katie Mews Suite 042\nGuerrafurt, MD 08669',
    'text': 'Where choice he rather large event always. Information in pretty plan second professional ahead. Measure development western side fear bad.',
    'email': 'cynthia13@example.com',
    'phone_number': '225.546.4547',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jane Cruz',
    'Katherine Buck',
    'Herbert Glenn',
    'Kevin Dean',
    'Donald Richards',
    'Samantha Rodriguez',
    'Christopher Lambert',
    'Cynthia Garcia',
],
    'json': {
    'name': 'Jon Webb',
    'address': '23265 Alexandra Groves Apt. 029\nNew Charles, MD 95536',
},
    'key93497': 'value31574',
    'key60582': 'value34607',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Bethany Bennett',
    'address': '994 William Circles Apt. 986\nLake Moniquechester, MO 82903',
    'text': 'Brother seven note these tree among marriage. Trouble newspaper goal film at should attack magazine.\nGreen camera sure can become hot sometimes. Paper serious standard. Out trip sense lot.',
    'email': 'landerson@example.net',
    'phone_number': '001-759-955-7737x2881',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kristin Williams',
],
    'json': {
    'name': 'Timothy Perez',
    'address': '002 Emily Fork Apt. 102\nLake Elizabethberg, NY 07512',
},
    'key48073': 'value83300',
    'key55638': 'value9763',
    'key38339': 'value6083',
    'key88995': 'value27999',
    'key17616': 'value51411',
    'key98765': 'value70961',
    'key34394': 'value19730',
    'key79989': 'value13718',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Benjamin Gallagher',
    'address': '13327 Murphy Gardens Apt. 456\nSouth Katherine, MI 77903',
    'text': 'This decade require be forget race case. Assume personal foreign box. Benefit against should.\nOpen voice force painting remember. Do stock art dinner. All drop another weight toward time kid.',
    'email': 'ysanford@example.com',
    'phone_number': '619-496-3877x1750',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dennis Freeman',
    'Joseph Holmes',
    'Paige Berry',
    'Jeffrey Huber',
    'Randy Franco',
    'Deborah Gomez',
    'Patrick Williams',
    'Robert Richard',
],
    'json': {
    'name': 'Victor Smith PhD',
    'address': '805 Bradley Via Apt. 621\nSouth Teresa, KY 47725',
},
    'key29422': 'value55026',
    'key36289': 'value44999',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Colleen Reyes',
    'address': '2695 Phelps Walk Apt. 626\nSarahmouth, IN 00559',
    'text': 'Simply skin according election way. Voice outside across action federal.\nCongress now plan sure together second note. Look support commercial doctor effect.',
    'email': 'lindsey80@example.org',
    'phone_number': '(458)947-6858',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alexandria Snow',
    'Diane Rodriguez',
    'Andrew Gillespie',
    'Eric Mason',
    'Kevin Hines',
],
    'json': {
    'name': 'Mary Hernandez',
    'address': '75781 Bradley Mountains Suite 966\nEast Kennethhaven, MT 32902',
},
    'key63936': 'value84660',
    'key30398': 'value21441',
    'key99517': 'value18708',
    'key91536': 'value5116',
    'key23764': 'value28327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Daisy Kelley',
    'address': '75815 Samantha Junction Suite 743\nBrianburgh, MO 17410',
    'text': 'Party probably growth drug bad music address. Best job standard be. Wrong detail director ability east.\nSuccess get ability until bad. Agent offer significant season per.',
    'email': 'coreylawson@example.com',
    'phone_number': '4152004270',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brian Herman',
    'Dr. Valerie Williamson',
    'Amber Conley',
    'Diana Hopkins',
    'Nathan Gibbs',
    'Alexis Perez',
    'Kelsey Reeves',
    'Jenna Long',
    'Stephen Olson',
],
    'json': {
    'name': 'Mike Miller',
    'address': '9520 Miller Gateway\nEdwinville, MI 92959',
},
    'key234': 'value62649',
    'key61169': 'value60733',
    'key27636': 'value82853',
    'key92547': 'value46397',
    'key77856': 'value28508',
    'key29395': 'value97719',
    'key81287': 'value34673',
    'key8302': 'value39415',
    'key9351': 'value22206',
    'key5000': 'value68077',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Shane Lucero',
    'address': '33003 Wendy Courts Suite 252\nNew Christopherberg, VA 45723',
    'text': 'Key apply summer direction once break. Pay rate option hand. Reality moment born relationship reality.\nCard national include finish task actually project treat. Decide certain certainly treatment.',
    'email': 'virginiagates@example.com',
    'phone_number': '+1-732-528-6431x540',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Paul Hernandez',
    'Brian Grant',
],
    'json': {
    'name': 'Kevin Lee',
    'address': '3895 Angela Oval Suite 802\nPort Richard, OR 76612',
},
    'key88566': 'value97573',
    'key61939': 'value18381',
    'key20246': 'value7314',
    'key97045': 'value49866',
    'key60724': 'value24223',
    'key81222': 'value95957',
    'key43451': 'value2155',
    'key52482': 'value92441',
    'key84883': 'value10051',
    'key38138': 'value86890',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Dennis Bishop',
    'address': '7806 Chris Light Suite 915\nHardyfort, GA 70023',
    'text': 'Laugh win billion accept. Source nation character. Us music others.\nFly project sea pattern final. Church draw or position Congress food. Language laugh interest describe law lose arm.',
    'email': 'thomas55@example.net',
    'phone_number': '001-479-534-8067x3190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Justin Crosby',
    'Anna Hernandez',
    'Katie Campbell',
    'Mary Hudson',
    'Kim Deleon',
    'Dr. George Ryan',
    'Gary Alvarez',
],
    'json': {
    'name': 'William Burgess',
    'address': '6481 Johnson Meadow\nLake Juantown, MP 50299',
},
    'key49700': 'value11326',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Amber Solomon',
    'address': '728 Emma Harbors Suite 894\nSouth Kenneth, MN 15857',
    'text': 'President start or region increase picture night. Explain including themselves high entire that.\nDay way body pick anyone decade begin. Detail fear success stuff offer.',
    'email': 'ngreen@example.net',
    'phone_number': '(569)608-8326x45445',
    'array_int_dynamic': [
    34925,
],
    'array_varchar_dynamic': [
    'Danielle Ward',
    'Terry Davis',
    'Mrs. Kathleen Hernandez DVM',
    'Brett Riddle',
    'Meghan Taylor',
    'Kenneth Dixon',
    'Alan Campbell',
    'David Gonzalez',
    'Jordan Crosby',
    'Stephanie Smith',
],
    'json': {
    'name': 'Bridget Davila',
    'address': '50298 Thomas Parkways Apt. 606\nPort Thomas, AL 64578',
},
    'key20080': 'value46605',
    'key58373': 'value99125',
    'key13934': 'value14176',
    'key29429': 'value29372',
    'key53667': 'value30670',
    'key4837': 'value20409',
    'key12206': 'value64748',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Thomas Smith',
    'address': '710 Wong Well Apt. 606\nAmandaview, VI 22752',
    'text': 'Movie note plan notice seven account well.\nTo color charge charge sometimes per around face. Investment company moment development each hospital art.\nWife anyone consumer tough general.',
    'email': 'leslie95@example.com',
    'phone_number': '+1-284-332-5766x8463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Huerta',
    'Amy Carpenter',
],
    'json': {
    'name': 'Sara Rodriguez',
    'address': '316 Helen Isle Suite 027\nPort Hannah, ND 48811',
},
    'key49698': 'value51651',
    'key47103': 'value96187',
    'key5112': 'value79842',
    'key62126': 'value11322',
    'key90065': 'value87352',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Jennifer Clark',
    'address': '45168 Garcia Gardens\nWandaside, VT 37456',
    'text': 'East research power democratic spring. Seven will camera movement per long. Almost good crime miss leave relate.\nBack adult build author bad two. Anyone indeed sign big affect house me.',
    'email': 'kevin62@example.com',
    'phone_number': '506-656-1067x25934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Olivia Ruiz',
    'Tricia Lee',
    'William Taylor',
    'Beth Clark',
    'Kim Brooks',
    'Kevin Paul',
    'Victoria Blackwell',
],
    'json': {
    'name': 'Amanda Freeman',
    'address': '79080 Erica Park Apt. 355\nDominguezburgh, HI 44179',
},
    'key92937': 'value6741',
    'key69234': 'value18246',
    'key59343': 'value98879',
    'key44363': 'value9849',
    'key22754': 'value67825',
    'key24267': 'value22348',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Andrew Stone',
    'address': '1321 Jason Prairie\nWest Nicholas, NH 54493',
    'text': 'Clear ago pay far. Challenge spend second stand player specific eat.\nMeeting old player artist want concern police. Fear natural threat race occur window. Cover special school kid glass thought.',
    'email': 'benjaminprice@example.com',
    'phone_number': '001-241-550-9407x5538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Sutton',
    'Mr. Gabriel Clark',
    'Charles James',
    'Regina Collins',
    'Ronald Flores',
],
    'json': {
    'name': 'Tara Hernandez',
    'address': '038 Dakota Lock\nWest Michaelside, PW 81848',
},
    'key53984': 'value81069',
    'key99292': 'value50510',
    'key46144': 'value54087',
    'key90205': 'value51054',
    'key97065': 'value10450',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Brittany Jimenez',
    'address': '26075 Rebecca Garden\nPort Teresa, AR 58686',
    'text': 'Pass industry spend president hit per impact animal. Official development so she forget fear. Political more attorney day.',
    'email': 'ygibson@example.com',
    'phone_number': '+1-743-561-3830x233',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Wilson',
    'Paul Orozco',
    'Stephen Barajas',
    'Mark Hernandez',
],
    'json': {
    'name': 'Stephanie Norris',
    'address': '769 Cynthia Pike Apt. 347\nJasonmouth, VI 21745',
},
    'key91794': 'value13535',
    'key64874': 'value42988',
    'key16243': 'value73019',
    'key34322': 'value22252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Diana Green',
    'address': 'Unit 9251 Box 2652\nDPO AP 31191',
    'text': 'Almost about pressure reflect future ahead. Out air brother sure south boy. Task page perhaps community.',
    'email': 'charles91@example.com',
    'phone_number': '(981)882-1110x33071',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Jacobson',
    'Kyle Wong',
    'Jeffrey Marshall',
    'Jessica Brown',
],
    'json': {
    'name': 'Ronald Simmons',
    'address': '7718 Tiffany Parkway Apt. 538\nNew Colleen, WA 71789',
},
    'key27112': 'value79999',
    'key17941': 'value57163',
    'key4572': 'value76326',
    'key13985': 'value68599',
    'key42131': 'value45096',
    'key71391': 'value74085',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Alexander Fowler MD',
    'address': '5610 Newman Radial Suite 942\nPort Eddieside, MA 80393',
    'text': 'Prepare American forward center either. Read above than news. Down particularly act if start society evening.',
    'email': 'oparker@example.com',
    'phone_number': '974.210.6700',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Angela Mccormick',
],
    'json': {
    'name': 'Shane Smith',
    'address': '902 Larson Ridges\nNelsonside, OK 25126',
},
    'key34245': 'value55700',
    'key14130': 'value51956',
    'key23641': 'value46418',
    'key70440': 'value58119',
    'key18337': 'value14915',
    'key87858': 'value96324',
    'key95252': 'value70726',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Tiffany Boyd',
    'address': '894 Corey Motorway\nPort Lisa, NE 58183',
    'text': 'Everyone necessary option. Buy receive this friend fine lot hit agree. Left that why exist.\nEvidence someone over show receive someone. City century play five story most then.',
    'email': 'wilsonalexandria@example.com',
    'phone_number': '(345)911-5248x62462',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Lester',
    'Joel Avila',
    'Angela Nelson',
    'David Harris',
],
    'json': {
    'name': 'Madison Smith',
    'address': '8285 Joseph Street\nBenjaminton, AR 44905',
},
    'key53868': 'value23411',
    'key37532': 'value44751',
    'key8254': 'value25861',
    'key13380': 'value22418',
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
    'RequestId': '967cd372-62ef-11f0-9035-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_39_995246QFxpUaeH',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-100-1]_1752744161.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId3210011752744161Json()
    test.run_tests()
