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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752743875_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752743875.json"
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



class AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulQueryVectorBySdk1752743875Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752743875.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752743875.json"
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
    'RequestId': 'e62a65d6-62ee-11f0-bae5-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_17_44_176106wAiIwJFc',
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
    'RequestId': 'e944cffb-62ee-11f0-a2ed-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_17_44_176106wAiIwJFc',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jeffery Alvarez',
    'address': '4169 Dana Track\nNew Jacobland, MD 89357',
    'text': 'Employee wonder across them everyone amount improve. Learn rather read ok remember treat return. Always put all focus establish single baby.',
    'email': 'hedwards@example.org',
    'phone_number': '+1-263-245-3034',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Riggs PhD',
    'Trevor Hampton',
    'Vanessa Crawford',
],
    'json': {
    'name': 'Crystal Smith',
    'address': '8777 Matthew Circle Suite 097\nWilsonfort, SD 75767',
},
    'key55707': 'value85315',
    'key19501': 'value37162',
    'key42415': 'value1523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Carla Moreno',
    'address': '81863 Mary Garden\nKristineborough, VI 02906',
    'text': 'Have score produce power series mean.\nBorn point person treat pattern onto yes.\nChild cost out paper religious send race. Nation somebody paper rock tell.',
    'email': 'michaeldixon@example.net',
    'phone_number': '4337080189',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Virginia Hill',
    'Jacob Moore',
    'Christine Barnes',
    'Stacie Thomas',
    'Nicholas Ray',
],
    'json': {
    'name': 'Paul Benson',
    'address': '7140 Tim Extension Apt. 612\nNorth Katherine, VI 95302',
},
    'key41979': 'value49556',
    'key57848': 'value41276',
    'key4155': 'value79543',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Lisa Jones',
    'address': '806 May Ridges Apt. 632\nEast Karenshire, AZ 60765',
    'text': 'Sign look commercial conference collection organization action. Short rest run significant prepare central.',
    'email': 'gwilson@example.com',
    'phone_number': '7844748343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Ford',
    'Ryan Davis',
    'Stacey Kelly',
    'Victoria Conner',
    'Derek Duffy',
    'Christian Miranda',
    'Samuel Garcia',
    'Gary Foster',
    'Michelle Moore',
    'Sarah Johnson',
],
    'json': {
    'name': 'Tammy Robinson',
    'address': '097 Katherine Ridge\nMckeeland, MI 51274',
},
    'key84070': 'value85021',
    'key48968': 'value4415',
    'key84519': 'value30928',
    'key21247': 'value89798',
    'key17133': 'value56485',
    'key38001': 'value81167',
    'key68265': 'value16573',
    'key79959': 'value51507',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Christopher Palmer Jr.',
    'address': '65075 Walker Flat Suite 186\nLake Julie, VA 54172',
    'text': 'Few heart physical trial nice nothing. Above little not consider about. Mouth factor writer better baby nice money all. Fine run Republican sense both receive law.',
    'email': 'christopherflynn@example.com',
    'phone_number': '5566356683',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Wilkins',
    'Gina Bell',
    'Kimberly Bennett',
],
    'json': {
    'name': 'Mitchell Kelley',
    'address': '40644 Hill Court\nWilliamsmouth, ND 87150',
},
    'key59461': 'value7900',
    'key62757': 'value70765',
    'key51515': 'value26633',
    'key66720': 'value89970',
    'key29546': 'value67932',
    'key48108': 'value47014',
    'key60191': 'value72266',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Sheri Hansen',
    'address': 'PSC 2359, Box 0164\nAPO AA 89341',
    'text': 'Foreign office interview catch space toward despite. Threat get sense we pass police treatment.\nWait dog lot beat. Interest health night while floor.',
    'email': 'hwilliams@example.net',
    'phone_number': '(606)926-4993x0444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Medina',
    'Paige Conner',
    'John Green',
    'Andre Luna',
],
    'json': {
    'name': 'Thomas Jordan',
    'address': '553 Ayers Mountains Suite 063\nGonzalezside, ID 61495',
},
    'key48928': 'value25377',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'David Stewart',
    'address': '50331 Hood Points Apt. 988\nHawkinshaven, CA 52982',
    'text': 'Yourself situation increase national. Congress music physical throw attention.',
    'email': 'sshea@example.org',
    'phone_number': '7905315375',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Hill',
    'Cameron Bryant',
    'Janice Turner',
    'Taylor Harding',
    'Heather Taylor',
    'Matthew Miller',
    'Randall Ward',
    'Jade Park',
    'Anthony Wright',
],
    'json': {
    'name': 'Michael Oliver',
    'address': '804 Jordan Brook\nSarahside, FL 97809',
},
    'key85684': 'value84128',
    'key94334': 'value75659',
    'key2196': 'value30886',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Mr. Nathan Wallace',
    'address': '40855 Natalie Fords Suite 226\nHullside, VT 93234',
    'text': 'Agent language media eye tend them trial. Style leave sing Mrs pay. Appear change walk contain.',
    'email': 'shane16@example.com',
    'phone_number': '001-472-277-0047x823',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Bailey',
    'Eric Mccarthy',
    'Andrea Page',
    'Melissa White',
    'Crystal Martinez',
    'Luis Marshall',
    'Christine Morris',
],
    'json': {
    'name': 'Kyle Gates',
    'address': '9807 William Parks\nCopelandberg, GU 44548',
},
    'key50107': 'value29136',
    'key96155': 'value99687',
    'key48255': 'value94768',
    'key34706': 'value31305',
    'key28093': 'value9172',
    'key88940': 'value75855',
    'key5961': 'value13343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Gabriel Parker',
    'address': '470 Velasquez Flats Apt. 334\nMartinezland, NV 89824',
    'text': 'Candidate behind democratic. Cup nor listen.\nFour wife generation point whatever movie do wonder. Those meeting entire himself century possible. Role different again southern discover on.',
    'email': 'benjamin63@example.org',
    'phone_number': '001-672-993-4752x755',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lucas Ellis',
    'Zachary Myers',
    'Catherine Medina',
    'Daniel Clements',
    'Shannon Garza',
    'Brittany Garcia',
    'Julia Baker',
],
    'json': {
    'name': 'Jaime Foster',
    'address': '52653 Tina Gateway\nEast Anthony, KY 57895',
},
    'key1879': 'value83460',
    'key13047': 'value19777',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Keith Lewis',
    'address': '8598 Collins Plaza Suite 267\nNorth James, AR 54794',
    'text': 'Cut reach fear I. Decide everybody prepare sea.\nSuffer suffer nearly interest describe brother.\nNo bill significant student particular his. Put officer expert lay save TV.',
    'email': 'zfields@example.com',
    'phone_number': '001-600-424-6801x1643',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Maria Crawford',
    'Warren Larsen',
    'Chad Arnold',
    'Kathryn Nelson',
    'Mallory Benson',
    'Anthony Rios',
    'Jessica Weaver',
    'Kelly Jackson',
    'Nicholas Lewis',
    'Krystal Johnson',
],
    'json': {
    'name': 'Laurie Johnson',
    'address': '3048 Bowers Viaduct\nDavidland, MH 39105',
},
    'key40675': 'value57791',
    'key60510': 'value49100',
    'key2220': 'value50829',
    'key10561': 'value20328',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Zachary Vega',
    'address': '66729 Bonnie Alley\nNew Edward, OR 47889',
    'text': 'Else special behavior sea. Happy activity over safe lay parent. Message tax always work sometimes question.\nReceive shake standard college.',
    'email': 'epruitt@example.com',
    'phone_number': '001-241-689-1966x4841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mark Sloan',
],
    'json': {
    'name': 'Dustin Daniels',
    'address': 'Unit 2230 Box 3434\nDPO AA 06776',
},
    'key66444': 'value20678',
    'key50107': 'value27102',
    'key47980': 'value37956',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Shaun Erickson',
    'address': '48989 Andrew Springs\nLake Olivia, CA 82947',
    'text': 'Inside course laugh possible particularly care community. Hair sort floor wear. Alone statement language any.',
    'email': 'justin41@example.net',
    'phone_number': '001-659-985-5076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Mitchell MD',
    'Kimberly Leonard',
    'Michael Ruiz',
    'Rebekah Stone',
],
    'json': {
    'name': 'Kelli Duncan',
    'address': '87737 Thomas Burg Suite 316\nPowellmouth, NY 32658',
},
    'key36632': 'value40690',
    'key97099': 'value3878',
    'key11568': 'value54333',
    'key38097': 'value62440',
    'key18174': 'value44720',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Marissa Peters',
    'address': '1305 Nunez Walks Apt. 236\nWest Jane, MH 64493',
    'text': 'Let material money everyone now class. Job month under happy worry result together. Provide painting continue mother right cell personal.',
    'email': 'cory09@example.net',
    'phone_number': '(258)556-2144',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Bartlett',
    'Laura Jones',
    'Michael Henry',
    'Andre Thompson',
    'Michelle Torres DVM',
    'Maria Graham',
    'Craig Nguyen',
],
    'json': {
    'name': 'Jessica Wells',
    'address': 'PSC 6182, Box 2965\nAPO AP 07418',
},
    'key19730': 'value72992',
    'key18111': 'value76343',
    'key3762': 'value17980',
    'key34694': 'value52656',
    'key50674': 'value83978',
    'key47601': 'value36892',
    'key89960': 'value29519',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Brandon Wallace',
    'address': '381 Wilson Meadow Suite 269\nDavisside, AR 05137',
    'text': 'Wrong news certain. Line popular break agreement instead contain hair he.\nAudience late which hit when argue get learn. Wonder each water value maintain.',
    'email': 'ecarr@example.com',
    'phone_number': '697.843.1619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Baker',
    'Jennifer Brown',
    'Wayne Johnson',
    'Katie Jacobs',
    'Danielle Mcdaniel',
    'Joan Wise',
    'Elizabeth Chavez',
],
    'json': {
    'name': 'Brenda Adams',
    'address': '193 Pham Loaf\nSouth Robertburgh, FL 60099',
},
    'key51662': 'value8703',
    'key31752': 'value23414',
    'key58641': 'value70760',
    'key15158': 'value95747',
    'key72511': 'value8329',
    'key1538': 'value66764',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Paul Foley',
    'address': '34064 Davis Place Suite 197\nRogerschester, IA 94571',
    'text': 'Science where off business pretty floor road. Mission event local everything.\nBut American kitchen happy. Spring matter hair industry very third blood north.\nRadio often yard recently a read each.',
    'email': 'francisantonio@example.com',
    'phone_number': '001-239-710-1258x64890',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mark Davis',
],
    'json': {
    'name': 'Melissa Price',
    'address': '3478 Ferguson Inlet\nNorth Vanessa, GA 26297',
},
    'key24239': 'value77112',
    'key25463': 'value88569',
    'key36715': 'value40289',
    'key58864': 'value91078',
    'key37298': 'value63069',
    'key59337': 'value81763',
    'key31305': 'value84829',
    'key50709': 'value60992',
    'key84776': 'value54263',
    'key35981': 'value23969',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Cameron Palmer',
    'address': '0936 Amber Dale\nNew Cameron, VT 76531',
    'text': 'List south finish of most. Machine few remain item meeting.\nNearly top police data medical raise situation. Choice impact arm. Provide read black.',
    'email': 'velazqueztristan@example.net',
    'phone_number': '001-385-921-5376x33071',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gina Bennett',
    'Brenda Martin',
    'Blake Harvey',
    'Ashley Allen',
],
    'json': {
    'name': 'Edward Decker',
    'address': '38849 Crawford Stream Apt. 880\nNorth Jenniferton, OH 82471',
},
    'key47657': 'value15979',
    'key8601': 'value26487',
    'key39714': 'value20148',
    'key43527': 'value99806',
    'key50177': 'value51828',
    'key94309': 'value55101',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Catherine Cameron',
    'address': '02351 Jennifer Curve Suite 024\nJenniferbury, VT 82693',
    'text': 'Adult wonder yourself edge inside else fill mind. Foot me nothing. Enjoy though firm week.',
    'email': 'gturner@example.net',
    'phone_number': '001-224-733-5734x29542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Smith',
    'Aaron Fritz',
    'Jamie Bautista',
    'Christopher Hawkins',
],
    'json': {
    'name': 'Jenna Smith',
    'address': 'Unit 5282 Box 9168\nDPO AP 00920',
},
    'key95812': 'value66700',
    'key22643': 'value23312',
    'key73094': 'value40872',
    'key1901': 'value10410',
    'key78164': 'value65719',
    'key54966': 'value43254',
    'key9912': 'value13740',
    'key54749': 'value22290',
    'key83426': 'value25339',
    'key92510': 'value94972',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Jerry West',
    'address': '958 Justin Route\nEast Julie, IN 44143',
    'text': 'Explain hand concern event leader fall. Report indeed wait car allow stop level. Money site different decade or quite.',
    'email': 'uhudson@example.com',
    'phone_number': '001-363-246-3839x375',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Nash',
    'Jordan Rhodes',
    'Sherri Wilson',
    'Molly Rangel',
    'Ian Haas',
],
    'json': {
    'name': 'Paul Mendez',
    'address': '5876 Joseph Crossroad Apt. 147\nMooreburgh, FL 64326',
},
    'key84934': 'value39372',
    'key73882': 'value56076',
    'key20921': 'value67799',
    'key29876': 'value55974',
    'key40967': 'value56641',
    'key16885': 'value30735',
    'key63396': 'value7258',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Jimmy Sheppard',
    'address': '71578 Paul Light Apt. 708\nJonesfort, ME 17180',
    'text': 'Baby image democratic case whom. Doctor space something.\nPoor address program not on worker. International between rule identify matter approach. On miss peace bad.',
    'email': 'foxtara@example.net',
    'phone_number': '483.924.9418x72074',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Harmon',
    'Judith Woods',
    'Tara Salazar',
    'Matthew Morris',
    'Jerry Hill',
    'Carla Garcia',
],
    'json': {
    'name': 'Eric Hernandez',
    'address': '87698 Sally Row Apt. 251\nDavidfort, SC 26072',
},
    'key75359': 'value35771',
    'key3840': 'value55256',
    'key88598': 'value62413',
    'key74390': 'value47540',
    'key83263': 'value80414',
    'key79221': 'value24881',
    'key25058': 'value87398',
    'key23640': 'value63353',
    'key25033': 'value75718',
    'key19010': 'value61845',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Steven Jacobs DDS',
    'address': '8175 Henderson Prairie\nLoveville, NV 14516',
    'text': 'Late activity suggest music discuss. Ball true look voice few.\nTake send economy establish. Win point admit while.\nEvent actually local treat.',
    'email': 'christina03@example.com',
    'phone_number': '702.314.9304x31620',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Cook',
    'Eric Schultz',
    'Michelle Lawrence',
    'David Wagner',
    'Chad Lopez',
    'James Quinn',
    'Charles Walton',
],
    'json': {
    'name': 'Brandy Conner',
    'address': 'PSC 6060, Box 5263\nAPO AA 37863',
},
    'key6718': 'value20066',
    'key17862': 'value39998',
    'key73320': 'value79154',
    'key17717': 'value54059',
    'key32353': 'value56658',
    'key347': 'value53073',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Adrian Johnson',
    'address': '1725 Marie River\nRodriguezmouth, ND 22413',
    'text': 'Individual success someone among study. Then paper address clear cold evening last.',
    'email': 'terryjill@example.com',
    'phone_number': '(935)937-4413x4025',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Williams',
    'Kevin Williams',
    'Stephanie Kirk',
    'Kelly Fuller',
    'Chad Miller',
    'Steven Blevins',
    'Craig Tate',
],
    'json': {
    'name': 'Deborah Hughes',
    'address': '3653 Laura Mountains Apt. 094\nPort Brittany, MS 72297',
},
    'key96666': 'value85651',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Brandon Nguyen',
    'address': '06597 Rollins Coves\nLake Taylorview, IN 22868',
    'text': 'Authority million line know. Sort set short defense medical become game board. Though age a member hand real factor.',
    'email': 'carolyn78@example.com',
    'phone_number': '+1-572-653-8169x288',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Mccoy',
    'Mercedes Smith',
    'Bryan Vaughn',
    'Ashley Martinez',
    'Andrew Simpson',
    'Shelley Fernandez',
    'Stephanie Franklin',
],
    'json': {
    'name': 'Paige Ramsey',
    'address': '83314 Brian Fords Suite 902\nAllenbury, MI 31079',
},
    'key43530': 'value35505',
    'key29671': 'value14509',
    'key26563': 'value27552',
    'key80071': 'value95066',
    'key13569': 'value97840',
    'key279': 'value2894',
    'key16176': 'value75728',
    'key74172': 'value79109',
    'key58714': 'value37548',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Peter Smith MD',
    'address': '57063 Alyssa Stravenue\nLevyland, MH 37428',
    'text': 'Big away interest establish floor often magazine. International drop his theory. Long civil partner air collection policy whose.',
    'email': 'bgeorge@example.org',
    'phone_number': '001-726-635-1994',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Nichols',
],
    'json': {
    'name': 'Tamara Blevins',
    'address': '80837 Duran Brooks\nEast Jenniferville, RI 71716',
},
    'key44248': 'value33516',
    'key16475': 'value53552',
    'key77938': 'value97549',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Lauren Miller',
    'address': '90199 Todd Path\nWest Richardmouth, ID 35882',
    'text': 'Use require determine. Newspaper modern mission only project life.\nImprove instead their cause dream various. With however coach buy picture.',
    'email': 'matthewhuerta@example.org',
    'phone_number': '266-947-3454x3866',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Banks',
    'Brianna Howard',
],
    'json': {
    'name': 'Austin Tyler',
    'address': '2914 Reynolds Estates\nJamiebury, AS 60022',
},
    'key75360': 'value40353',
    'key95845': 'value44564',
    'key60539': 'value2521',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jonathon Evans',
    'address': '44089 Warner Key Apt. 292\nPort Anneton, RI 84293',
    'text': 'Southern single whether old order or. Perform stock often treat security. Into kind special open protect.\nAttack treatment raise bit miss time. It add ask order. Should need quality down writer new.',
    'email': 'mdavis@example.org',
    'phone_number': '(544)209-6320x0856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Shannon',
    'Chad Solomon',
    'April Williams',
    'Alicia Barrett',
    'David Caldwell',
    'Katherine Stewart',
    'Diana Wolfe',
    'Robert Anderson',
],
    'json': {
    'name': 'Joseph Fowler',
    'address': '9482 Todd Plaza Suite 228\nSouth Christina, MD 29238',
},
    'key47377': 'value9491',
    'key95304': 'value38794',
    'key28608': 'value86892',
    'key98041': 'value36225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Lisa Johnson',
    'address': '8588 Charles Valley\nLisaview, VA 47436',
    'text': 'Record there inside maintain course official. Door know newspaper anyone almost.\nImpact speech thus parent decade until read into. Along so explain church attack not arrive share.',
    'email': 'william95@example.org',
    'phone_number': '5189637711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Alan Mullins',
    'Dean Johnson',
    'Lisa Miller',
    'Dr. Renee Mayo DDS',
    'Jacob Cisneros',
    'Shannon Black',
    'Brandi Brown',
    'Rachel Perry',
],
    'json': {
    'name': 'Erika Jackson',
    'address': '50578 Bartlett Run\nLake Erika, MP 94779',
},
    'key33744': 'value39665',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'John Martinez',
    'address': '66193 Craig Ranch\nWebbberg, MH 30240',
    'text': 'Very room read can friend. Top probably away cell camera ability pass.',
    'email': 'waltonjasmine@example.net',
    'phone_number': '655-535-9464x094',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sydney Jensen',
    'Stephanie Mcdonald',
    'Joshua Jackson',
    'Misty Burke',
    'Matthew Serrano',
    'Tyler Molina',
],
    'json': {
    'name': 'Kelly Alvarez',
    'address': '84146 Marks Roads Suite 020\nAyalaside, AK 08897',
},
    'key32962': 'value82156',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Monica White',
    'address': '014 Alexander Bypass\nSouth Jenniferburgh, CT 69913',
    'text': 'History need scientist detail. If whatever many necessary. Billion prepare long happy.\nDescribe under last ok enjoy trouble whether. Economy add always beat heavy. Nor may citizen force in.',
    'email': 'aespinoza@example.org',
    'phone_number': '(764)855-6976x532',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Jensen',
    'Bryan Trevino',
    'James Lara',
    'Jessica Smith',
    'Lance Sims',
    'Lisa Ryan',
    'Edward Chen',
    'Mark Miller',
    'Carlos Mendez',
],
    'json': {
    'name': 'Nicole Collins',
    'address': '49956 Bryant Lane Apt. 313\nWest Diane, MD 22939',
},
    'key87917': 'value88300',
    'key46367': 'value78416',
    'key41645': 'value76716',
    'key5574': 'value870',
    'key10790': 'value19483',
    'key40418': 'value91944',
    'key86302': 'value54829',
    'key89802': 'value82491',
    'key39468': 'value29150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Amy Johnson',
    'address': '27719 Raymond Mountain\nPort Kayla, VA 69175',
    'text': 'Middle suddenly himself claim form matter own. Item let do successful answer. Ask former service charge.',
    'email': 'qwilson@example.org',
    'phone_number': '848.271.6952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Flores',
    'Adam Riggs',
    'Russell Vasquez',
    'Derek Gray',
],
    'json': {
    'name': 'Andrew Contreras',
    'address': '420 Norris Summit Apt. 269\nSouth Susan, CA 33077',
},
    'key73630': 'value99809',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jennifer Miller',
    'address': '42063 Javier Ramp\nWest James, MD 44124',
    'text': 'White event save enough. Environmental everything pay.\nResponsibility ten might do. Treat church skill bad free station.',
    'email': 'kevinsmith@example.net',
    'phone_number': '798.798.0759',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Lara',
    'Nicholas Cooper',
    'Michelle Stark',
    'Eric Gonzalez',
    'Jonathan Carlson',
    'Maria Ramirez',
    'Brianna Arnold',
    'Christopher Russell',
    'Allen Esparza',
],
    'json': {
    'name': 'Jeffrey Moore',
    'address': '390 Garcia Port\nJessebury, IA 77443',
},
    'key34097': 'value13172',
    'key67328': 'value69103',
    'key89627': 'value16712',
    'key7800': 'value69480',
    'key52555': 'value54614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Karen Mcdaniel',
    'address': '629 Velasquez View Suite 477\nTiffanyfort, ID 56059',
    'text': 'Place whether right whatever.\nCommunity travel culture cause. Take pressure simple seek. Various run include smile around. Size describe feeling remember listen.',
    'email': 'nielsendavid@example.com',
    'phone_number': '(497)856-2438x00103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeanette Huynh',
    'Laurie Holt',
    'Alexandra Young',
    'Joshua Gonzalez',
    'Elizabeth Miller',
    'Matthew Little',
],
    'json': {
    'name': 'Elizabeth Rivera',
    'address': '19076 Melissa Lakes Apt. 147\nRyanburgh, LA 29827',
},
    'key13497': 'value37104',
    'key82956': 'value96614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Richard Perez',
    'address': '30636 Stacy Islands Apt. 179\nWest Patriciabury, RI 42674',
    'text': 'Usually you every heart expect. Research always visit trade piece kid yet. Customer bed ten whom image guess.',
    'email': 'jennifer82@example.org',
    'phone_number': '(550)796-0161x1948',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Monica Hill',
    'Jonathan Matthews',
    'Justin Reed',
    'Scott Wagner',
    'David Richardson',
],
    'json': {
    'name': 'Randall Aguilar',
    'address': '49899 Lopez Vista Suite 725\nNew Brendashire, GA 94517',
},
    'key93183': 'value86190',
    'key45224': 'value85804',
    'key52361': 'value70902',
    'key18668': 'value1015',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Lisa Sanders',
    'address': '4701 Stewart Mission Suite 967\nSouth Carolyn, GA 41841',
    'text': 'Stand herself technology onto government. Break involve maybe employee to investment.',
    'email': 'riverawilliam@example.org',
    'phone_number': '+1-758-800-7465x13734',
    'array_int_dynamic': [
    27089,
],
    'array_varchar_dynamic': [
    'Taylor Novak',
    'Tracy Fisher',
    'Christina Palmer',
    'Alexandra Russell',
    'Teresa Anderson',
    'Jillian Edwards',
    'Jack Shepherd',
    'Ashley Barton',
],
    'json': {
    'name': 'Earl Johnson',
    'address': '25562 Whitney Manor Apt. 213\nNorth Katieberg, IN 22050',
},
    'key15961': 'value4946',
    'key10318': 'value82087',
    'key26500': 'value31325',
    'key93113': 'value81090',
    'key81910': 'value29967',
    'key64290': 'value76751',
    'key41222': 'value3413',
    'key18810': 'value3616',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Charles Johns',
    'address': '88908 Adams Inlet\nNew Robertfort, MH 57445',
    'text': 'Ability effect use customer start short. Mrs heart relate its give serve indeed.\nEver beyond question decade but worry out. Truth may provide quite.\nEat American finally writer to fall life.',
    'email': 'brian23@example.net',
    'phone_number': '+1-764-791-9306x602',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Barber',
    'Kimberly Bell',
    'Christopher Brooks',
    'Crystal Graham',
    'Janice Wagner',
    'Brian Smith',
    'Edward Taylor',
    'Shelia Shelton',
],
    'json': {
    'name': 'Heidi Chambers',
    'address': '59169 Thompson Motorway Suite 194\nDukeshire, CO 29988',
},
    'key77146': 'value23023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kathleen Kennedy',
    'address': '5228 Lee Isle Apt. 147\nRalphmouth, GA 87633',
    'text': 'Head stay special reach. Think thank home line.\nEye probably experience. Visit simple environment wear pull entire. Build sound cause your reflect win.',
    'email': 'donnaford@example.net',
    'phone_number': '202-959-2087',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Loretta Wilkerson',
    'Michael Wolfe',
    'Jacqueline Dominguez',
    'Jacob Taylor',
    'Joseph Warren',
    'Jose Reid',
    'Joseph Smith',
],
    'json': {
    'name': 'Grace Fernandez',
    'address': '6949 Hobbs Circles\nSouth Anthony, WA 81008',
},
    'key6742': 'value71549',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Anne Villarreal',
    'address': '656 Colton Ferry Suite 881\nNew Matthewbury, GU 54654',
    'text': 'Poor wish answer reflect boy create. Run particular husband.\nParticularly prepare since role month arrive grow. Various account exactly no represent.',
    'email': 'waltersrobert@example.org',
    'phone_number': '496.662.8619x1987',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robert Rose',
    'Julie Perry',
    'Dr. Sydney Cook',
    'Brandi York',
    'Terry Golden',
    'Deanna Phillips',
    'Jeffrey Thornton',
],
    'json': {
    'name': 'Bryce Pearson',
    'address': '3535 Yang Courts Apt. 022\nMarkchester, IL 73937',
},
    'key62151': 'value14220',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Ruth Owens',
    'address': '9890 Hill Dam\nWuborough, CT 31985',
    'text': 'Much east he evening. Truth every lawyer.\nListen soldier like type travel. Base they letter receive number same. Material if matter upon.',
    'email': 'tpayne@example.net',
    'phone_number': '(423)622-3426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Harmon DVM',
    'Michael Tran',
    'Matthew Torres',
    'Frank Poole',
    'Eric Cook',
    'Michael Larson',
    'Michael Moore',
    'Michelle Phillips',
    'Timothy Melton',
    'Matthew Ross',
],
    'json': {
    'name': 'Ricky Mcintyre',
    'address': '21841 Palmer Skyway Suite 390\nRussellborough, DE 75253',
},
    'key59438': 'value9895',
    'key92799': 'value28359',
    'key11570': 'value637',
    'key43549': 'value59164',
    'key25908': 'value57876',
    'key12871': 'value71342',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Tonya Munoz',
    'address': '21205 Flores Turnpike\nEast Holly, RI 31377',
    'text': 'Society should agree child.\nUsually born since. Career always third concern your tough doctor worry.',
    'email': 'lewisamanda@example.org',
    'phone_number': '(490)376-9260',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gloria Montgomery',
    'Robert Thornton',
    'Victor Daugherty',
    'Michelle Castro',
    'Rebecca Hernandez',
    'Daniel Hogan',
    'Earl Wilkins',
    'Nicole Griffin',
    'Heidi Taylor',
],
    'json': {
    'name': 'Courtney Hill',
    'address': '3044 Lewis Point Apt. 834\nHurstport, FL 42103',
},
    'key63925': 'value91504',
    'key30036': 'value80611',
    'key86386': 'value78124',
    'key13121': 'value79477',
    'key62580': 'value64134',
    'key15519': 'value95070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Felicia Adams',
    'address': '5094 Duncan Circles Apt. 272\nWest Vincentfurt, SC 06884',
    'text': 'Compare pay wear difficult action week analysis. Power create stop others lawyer create environment just.\nBlack fact indicate interesting admit politics.',
    'email': 'courtney42@example.org',
    'phone_number': '983-476-0497x9523',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Carter',
],
    'json': {
    'name': 'Steven Lee',
    'address': '33633 Juan Coves\nHenryland, OH 52285',
},
    'key62048': 'value60209',
    'key71486': 'value10886',
    'key73002': 'value21022',
    'key71478': 'value78511',
    'key5629': 'value8919',
    'key31032': 'value21246',
    'key81006': 'value15228',
    'key66771': 'value7558',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'William Nelson',
    'address': '8283 Wright Green\nEast Gloriashire, PW 73648',
    'text': 'Hold tree station others growth size such. Bar check foreign some.\nBetween home assume enough part artist long. Clearly among tell air time official. Its old anything society catch outside.',
    'email': 'john77@example.com',
    'phone_number': '219.695.5604',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Hannah Chen',
    'Anthony Jones',
    'Dr. Amy Kelly',
],
    'json': {
    'name': 'Jose Wheeler',
    'address': '9991 Scott Green\nLindatown, ID 11523',
},
    'key79396': 'value57',
    'key62506': 'value73933',
    'key72914': 'value11789',
    'key84150': 'value36612',
    'key84273': 'value29027',
    'key66118': 'value19655',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Mrs. Amy Skinner DDS',
    'address': '3358 Jennifer Centers Suite 762\nKellyburgh, MH 59342',
    'text': 'Cup miss least life. Still position main world require.\nBall case pass believe run memory raise. Congress always line defense. Weight out discover second.\nLeg health air.\nSkin care home.',
    'email': 'justingrant@example.org',
    'phone_number': '497-743-7341x33192',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Oscar Parker',
    'Regina Clark',
    'Bill Hubbard',
    'Kimberly Bell',
    'Adrian Gill',
    'Steven Smith',
    'Jill Zimmerman',
],
    'json': {
    'name': 'Michael Miller',
    'address': '4617 Wolfe Springs\nBriannaberg, ND 37342',
},
    'key6454': 'value54618',
    'key84338': 'value3447',
    'key51086': 'value30193',
    'key49880': 'value83784',
    'key30852': 'value52400',
    'key25497': 'value74872',
    'key65208': 'value97357',
    'key33275': 'value72291',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jose Lewis',
    'address': '522 Duncan Route\nNorth Angelica, MS 74375',
    'text': 'Husband easy goal despite to hit. Know artist necessary between should law her.\nIndeed half center their memory former. Phone music vote. With spring expert voice toward partner.',
    'email': 'bnixon@example.com',
    'phone_number': '+1-532-290-6522x2214',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Williams',
],
    'json': {
    'name': 'Jennifer Hancock',
    'address': '03184 Bell Way\nNorth Nancyborough, IA 51918',
},
    'key99115': 'value1772',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Janet Cruz',
    'address': '762 Blanchard Point\nNew Elizabeth, TX 20953',
    'text': 'Director police tell consumer.\nWind consider these effort stuff know. Safe sit per indeed. Score reveal entire long.\nBoy to why get offer I same.',
    'email': 'dunnchristina@example.net',
    'phone_number': '395-389-2227x75343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Thomas',
    'John Haynes',
    'Marc Lewis',
    'Oscar Gardner Jr.',
    'Thomas Mcbride',
    'Edward White',
],
    'json': {
    'name': 'Patricia Brown',
    'address': 'USCGC Day\nFPO AE 72649',
},
    'key48879': 'value15723',
    'key35171': 'value46633',
    'key8682': 'value90575',
    'key57646': 'value41977',
    'key52295': 'value11716',
    'key82642': 'value4643',
    'key32672': 'value47193',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Taylor Clark DVM',
    'address': '992 Eric Loop Suite 013\nEast Alexandrastad, CO 92120',
    'text': 'Account then weight beautiful. Serious make very hold value group dinner little.\nHowever poor participant student bill me. Mouth professor short mean.',
    'email': 'pcummings@example.org',
    'phone_number': '464-418-8253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Yolanda Williams',
    'Amy Davis',
    'Rachel Vance',
    'Mckenzie Martin',
    'Rita Stevens',
    'Darren Jones',
    'Robert Mendez',
    'Ashley Harris',
    'Robert Taylor',
    'Sharon Reeves',
],
    'json': {
    'name': 'Ralph Bradshaw',
    'address': '2871 Bell Centers Suite 971\nNew Neil, SD 62000',
},
    'key78333': 'value74571',
    'key89080': 'value67669',
    'key23431': 'value82890',
    'key50545': 'value16875',
    'key1579': 'value19499',
    'key58288': 'value90892',
    'key45866': 'value25770',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kirk George',
    'address': '82694 Emily Point\nPatriciamouth, LA 80825',
    'text': 'Wonder how decide through natural my. Rule meeting door do list course. Finally suffer whole discover street citizen nature.',
    'email': 'eeaton@example.org',
    'phone_number': '381.329.3871x5436',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Scott James',
    'Stephen Owens',
    'Ryan Adkins',
    'Tara Moore',
    'Anna Wong',
    'Jennifer Vasquez',
    'Mark Ryan',
    'Thomas Thomas',
],
    'json': {
    'name': 'Adam Guzman',
    'address': '5761 John Isle Apt. 679\nColemanmouth, HI 57162',
},
    'key56136': 'value39954',
    'key58683': 'value60344',
    'key65023': 'value14930',
    'key92908': 'value79698',
    'key30549': 'value18074',
    'key28330': 'value46562',
    'key51094': 'value88006',
    'key71127': 'value28784',
    'key30383': 'value10561',
    'key79655': 'value72350',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Joseph Green',
    'address': '53871 Jennifer Mount\nCharlesmouth, DC 94187',
    'text': 'Until morning performance easy most present federal. Yeah behind specific program.\nCharacter some activity food sit head good. Real campaign without risk rock.',
    'email': 'qhunt@example.net',
    'phone_number': '+1-694-742-2369x3308',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Larry Wright',
    'Kelli Bates',
    'Ryan Alexander',
    'Marco Fernandez',
    'Derek Martinez',
    'Logan Holland',
    'Maurice Boyd',
],
    'json': {
    'name': 'John Jones',
    'address': '83044 Teresa Motorway\nEast Kevinchester, WI 27980',
},
    'key19130': 'value31543',
    'key79299': 'value35586',
    'key74925': 'value86719',
    'key49727': 'value19387',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Victoria Miles',
    'address': '249 Patricia Court Suite 927\nEast Cheryl, UT 73441',
    'text': 'Measure possible put share take avoid fact bar. Wall early admit thank type house rich.\nWhole carry sit Mr simply that. Road sort approach machine nearly behind.',
    'email': 'perezmichael@example.org',
    'phone_number': '(513)572-3405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Hayes',
    'Edward Moore',
    'Amanda Brown',
    'Mark Thompson',
    'Nicholas Randolph',
    'Cameron Blair',
    'Julie Jimenez',
    'Jasmin Jackson',
    'Kyle Mccarthy',
],
    'json': {
    'name': 'Alec Hamilton',
    'address': 'USCGC Lewis\nFPO AE 55331',
},
    'key18260': 'value96983',
    'key30037': 'value24919',
    'key73950': 'value26249',
    'key97108': 'value75516',
    'key44389': 'value88150',
    'key64275': 'value37796',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Angela Smith MD',
    'address': '739 Jenny Mountains Apt. 417\nMarkmouth, TN 36438',
    'text': 'Into theory future detail able history. Present page power amount everything serious of.\nSit begin will several quality they. Against several drive their management accept article.',
    'email': 'meganwatson@example.net',
    'phone_number': '268.428.0250',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Mercado',
    'James Robles',
    'Timothy Anderson',
    'Jack Lee',
    'Thomas Johnson',
],
    'json': {
    'name': 'Gabriel Obrien',
    'address': '8291 Flores Plains Apt. 315\nHoganshire, CA 98125',
},
    'key40142': 'value24808',
    'key56750': 'value68852',
    'key87763': 'value56585',
    'key50241': 'value39394',
    'key31028': 'value10187',
    'key83234': 'value14337',
    'key91392': 'value44863',
    'key19335': 'value86128',
    'key80250': 'value15924',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Timothy Goodwin',
    'address': '36988 Jennifer Branch\nSouth Melindaland, PA 60885',
    'text': 'She sell particular investment security experience despite. Future market perhaps heavy.',
    'email': 'dianabrown@example.com',
    'phone_number': '+1-854-264-5577',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Curry',
    'Tanya Dyer',
    'Jennifer Kim',
],
    'json': {
    'name': 'Henry Garrison',
    'address': '6269 Kenneth Squares Suite 064\nMartinezstad, CO 72753',
},
    'key18150': 'value76302',
    'key14842': 'value49500',
    'key20342': 'value38426',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Shane Brown',
    'address': '2860 Chavez Motorway Apt. 149\nGrantland, ID 10106',
    'text': 'Question food thought at consider evidence.\nWhether after reason that movie. Set challenge each.',
    'email': 'princejean@example.org',
    'phone_number': '001-717-603-5842x8042',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Hensley',
    'Aimee Myers',
    'James White',
    'Jonathan Johnson',
    'Anna Gardner',
    'Rachel Williams',
    'Stephanie Parker',
    'Doris Jensen',
],
    'json': {
    'name': 'Emily Jones',
    'address': 'Unit 3777 Box 9897\nDPO AE 26986',
},
    'key53804': 'value49728',
    'key12288': 'value42328',
    'key89930': 'value12022',
    'key65329': 'value53802',
    'key20525': 'value61952',
    'key33872': 'value58914',
    'key32533': 'value87533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Kristina Carr',
    'address': '4541 Barnes Points\nCastillostad, MP 42209',
    'text': 'Same product mind decide its. Tv small military young bank fund into. Clearly quality Democrat long general.\nRequire play company do together. Difference have possible military.',
    'email': 'daniel25@example.com',
    'phone_number': '408-547-4298',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Holmes',
    'Philip Brooks',
    'Howard Tran',
    'Diana Johnson',
    'Jessica King',
    'Susan Mendez',
    'Mary King',
    'Ryan Singleton',
    'Abigail Jacobson',
],
    'json': {
    'name': 'Steven Davis PhD',
    'address': '76498 Brenda Skyway\nPort Andreafurt, MI 27777',
},
    'key33992': 'value55011',
    'key48497': 'value49658',
    'key80435': 'value51667',
    'key66015': 'value59568',
    'key34330': 'value69833',
    'key37953': 'value24374',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Tammy Thompson',
    'address': '73423 Lane River Apt. 116\nNorth Cameron, OK 45139',
    'text': 'Order special you event. Material issue friend shake painting. Available hit clearly candidate finish know generation.',
    'email': 'icampbell@example.com',
    'phone_number': '001-427-922-4118',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Allen Soto',
    'Lauren Bradford',
    'Brandon Bowman',
    'Jennifer Hart',
    'Kathryn Brown',
],
    'json': {
    'name': 'Patrick Phillips',
    'address': '7760 Mendez Meadow\nNorth Laurastad, AS 68457',
},
    'key70561': 'value34261',
    'key4043': 'value35092',
    'key57052': 'value57314',
    'key2977': 'value59732',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kevin Sheppard',
    'address': '981 Underwood Knoll Apt. 950\nPort Emily, KY 93302',
    'text': 'Gas hospital project image center. Per identify ready forward cell teach group player.\nIssue way brother look many sport form property. Herself difficult floor spend.',
    'email': 'nacevedo@example.com',
    'phone_number': '747-355-1740x26908',
    'array_int_dynamic': [
    38067,
],
    'array_varchar_dynamic': [
    'Penny Walker',
    'Natasha Klein',
    'Susan Lara',
    'Julian Snyder',
    'Terri Johnson',
    'Caitlin Taylor',
    'Ralph Crawford',
    'Sean Franklin',
    'Jennifer Moore',
    'Kyle Bell',
],
    'json': {
    'name': 'Stephanie Guerrero',
    'address': 'Unit 2927 Box 0733\nDPO AP 50244',
},
    'key97854': 'value93255',
    'key15586': 'value50939',
    'key70786': 'value82256',
    'key98605': 'value70362',
    'key78230': 'value25544',
    'key58107': 'value24779',
    'key64528': 'value94155',
    'key33301': 'value82508',
    'key83671': 'value4790',
    'key15293': 'value82478',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Laura Dorsey',
    'address': '23054 Charlene Ramp Suite 956\nLake Christopherstad, WY 48594',
    'text': 'Because about down certain clear money. Name machine alone network avoid process figure.',
    'email': 'garciakevin@example.org',
    'phone_number': '(663)237-3926x1316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Eric Fox',
    'Julia Malone',
],
    'json': {
    'name': 'Cassie Fernandez',
    'address': '675 Campbell Row\nRogersbury, MP 72127',
},
    'key39962': 'value52816',
    'key82497': 'value17156',
    'key48572': 'value22618',
    'key54813': 'value47402',
    'key52282': 'value18931',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Ryan Miles',
    'address': '411 Richard Parks Suite 663\nPort Sean, WI 58687',
    'text': 'Statement heavy now. Six science catch data heavy bed will. Take author Congress old design owner interest option.',
    'email': 'williamsmichelle@example.net',
    'phone_number': '227-538-4501',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joy Bailey',
    'Javier Porter',
],
    'json': {
    'name': 'Brianna Davis',
    'address': 'USNV Norris\nFPO AP 84126',
},
    'key50003': 'value63959',
    'key33777': 'value23418',
    'key41379': 'value50926',
    'key34956': 'value74268',
    'key60291': 'value97804',
    'key46015': 'value77276',
    'key43775': 'value95290',
    'key34244': 'value54648',
    'key48128': 'value70382',
    'key54973': 'value44791',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Leslie Charles DDS',
    'address': '26859 Randy Islands\nBeasleymouth, HI 05343',
    'text': 'Project possible often away them build until. Technology laugh generation do.\nMusic letter set hour whom not time. Whose ok road represent room step management.',
    'email': 'jameswebb@example.com',
    'phone_number': '(846)809-8514x8237',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'David Skinner',
],
    'json': {
    'name': 'Emily Lopez',
    'address': '672 Anderson Highway\nWest Sara, ID 96574',
},
    'key82734': 'value77212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Paul Smith',
    'address': '94415 Steven Lane Apt. 188\nWest Dawnton, ME 19690',
    'text': 'College message foot. Share close so stand spend husband.\nSpecial close local source blood take. Describe pressure per model.\nSituation once teacher continue be attorney. Yourself moment wide.',
    'email': 'katherinecarroll@example.net',
    'phone_number': '(884)607-0145x97174',
    'array_int_dynamic': [
    53576,
],
    'array_varchar_dynamic': [
    'Christopher Davenport',
],
    'json': {
    'name': 'Keith Nelson',
    'address': '912 Mandy Mills\nEast Christopher, ND 26177',
},
    'key16142': 'value12029',
    'key10339': 'value11367',
    'key87729': 'value61226',
    'key70703': 'value70966',
    'key69100': 'value2294',
    'key16391': 'value39279',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Melissa Mcgrath',
    'address': 'Unit 2663 Box 2653\nDPO AA 73038',
    'text': 'Treatment majority quickly become effort travel remember. Real role common just sport above anything.\nBoy scientist five best. Simple interest billion memory base tree.',
    'email': 'xfoster@example.com',
    'phone_number': '9526718588',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'George Mcneil',
    'Jennifer Maddox',
    'Michael Hendrix',
    'Nathan White',
    'Steven Cole',
    'Frederick Rich',
    'Stephanie Hines',
    'Heather Barnes',
],
    'json': {
    'name': 'Shirley Burns',
    'address': '2515 Miller Meadows\nLake Joseph, GU 82177',
},
    'key17405': 'value7550',
    'key22958': 'value12814',
    'key65698': 'value91435',
    'key55396': 'value43212',
    'key75503': 'value5193',
    'key19420': 'value86201',
    'key58761': 'value87131',
    'key12733': 'value78158',
    'key60866': 'value8284',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Heather Cardenas',
    'address': '3024 Julian Mountain\nNorth Deanton, LA 47392',
    'text': 'Box magazine people response east agent. With hour company culture certainly consumer.\nTeach read focus. Somebody partner finally reduce possible send.',
    'email': 'meganliu@example.com',
    'phone_number': '724-208-7206x78943',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Emily Pittman',
    'Brett Mack',
    'Tiffany Hood',
    'Heather Becker',
    'Crystal Horton',
    'Patricia Smith',
    'Nicole Cowan',
    'Shawn Goodman',
    'Aaron Brown',
],
    'json': {
    'name': 'David Gonzalez',
    'address': '801 Cook Stream\nBradburgh, MI 09859',
},
    'key12782': 'value41828',
    'key88839': 'value49948',
    'key45127': 'value12866',
    'key45696': 'value11619',
    'key56415': 'value60947',
    'key92750': 'value14668',
    'key46203': 'value42944',
    'key94916': 'value75270',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Timothy Mckinney',
    'address': '58294 Mckay Stravenue\nWaltonfort, MP 77416',
    'text': 'Policy feeling collection quickly affect. Would require structure leader body challenge concern.',
    'email': 'blackburnbrett@example.org',
    'phone_number': '636.712.0443x766',
    'array_int_dynamic': [
    67177,
],
    'array_varchar_dynamic': [
    'Ryan Manning',
    'Emily Sims',
],
    'json': {
    'name': 'Renee Jones',
    'address': '558 Roberto Lakes Suite 667\nStevenside, MO 66637',
},
    'key43876': 'value65846',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Diane Martin',
    'address': '834 Oscar Square\nPort Eric, MP 52285',
    'text': 'Expert win agreement think at others. List realize add simply. Simple key recently share standard.\nLet write dinner produce believe act prove. Service piece near try major. Long left unit.',
    'email': 'elowe@example.org',
    'phone_number': '816.319.5252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Edward Young',
    'Kelly Griffin',
    'Amanda Phillips',
    'Bryan Mckee',
    'Jill Swanson',
],
    'json': {
    'name': 'Gregory Mullins',
    'address': '8791 Joshua Ferry Suite 750\nTownsendport, ID 73751',
},
    'key64460': 'value4940',
    'key11817': 'value99744',
    'key19696': 'value38817',
    'key49999': 'value21770',
    'key23818': 'value58954',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jamie Dodson',
    'address': '79579 Cunningham Street\nLewisland, MA 21991',
    'text': 'Must other reality bit single mouth. Eat eye close member. Less president question.',
    'email': 'margaret61@example.org',
    'phone_number': '+1-515-234-4790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Terrence Kennedy',
],
    'json': {
    'name': 'Katie Stewart PhD',
    'address': '53652 Carrie Isle Apt. 811\nGarciamouth, WA 51686',
},
    'key43452': 'value26838',
    'key77977': 'value72674',
    'key28793': 'value2356',
    'key1176': 'value8555',
    'key11229': 'value87993',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'William Scott',
    'address': '914 Swanson Drive Suite 296\nScottburgh, HI 33368',
    'text': 'Owner eight weight painting for new part. Able parent dream seven usually.\nLarge ok weight listen field manager. More wrong Republican.',
    'email': 'reedlisa@example.net',
    'phone_number': '9039548698',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Patrick',
    'Juan Coffey',
    'Kayla Stuart',
    'Christopher Powell',
    'Michelle Dunn',
    'Sandra Hughes',
    'Adam Thomas',
    'Scott Wilson',
],
    'json': {
    'name': 'Lauren Vega',
    'address': '442 Robert Ranch Suite 359\nSouth Danamouth, MH 00759',
},
    'key47335': 'value27709',
    'key76308': 'value46885',
    'key70585': 'value91508',
    'key74415': 'value29159',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Dominique Cooper',
    'address': 'Unit 1122 Box 2412\nDPO AE 88799',
    'text': 'Allow point morning own where hair. Natural long election.\nTelevision need your reflect measure within chair guess. Inside quality upon offer.',
    'email': 'kimlynch@example.com',
    'phone_number': '(757)808-1929x222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Campos',
    'Erica Yu',
    'Sarah Jackson',
    'Beverly Jimenez',
],
    'json': {
    'name': 'Mckenzie Smith',
    'address': '39516 Ortiz Divide Apt. 219\nLake Rebeccaside, MD 51780',
},
    'key75637': 'value94023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Karen Reynolds',
    'address': '89729 Darrell Village Apt. 212\nLisastad, VA 19075',
    'text': 'Structure executive prove unit hundred. Ever three small call fish late case.\nDefense summer customer stuff tell. Month do paper. Today tough per second.',
    'email': 'ukim@example.org',
    'phone_number': '+1-775-719-3177x704',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Phillip Anderson',
    'Brian Mata',
    'Brenda Hardy',
    'Brenda Jordan',
    'Erin Callahan',
    'Kayla Sparks',
],
    'json': {
    'name': 'Michael Gonzalez',
    'address': '8325 Kimberly Land\nEast Brianshire, MA 61677',
},
    'key31009': 'value68390',
    'key29142': 'value9955',
    'key54514': 'value89453',
    'key19289': 'value2938',
    'key92985': 'value964',
    'key43273': 'value26206',
    'key40475': 'value44019',
    'key10810': 'value91672',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Emily Gregory',
    'address': '699 Kelly Rue Apt. 994\nSouth Tammyland, KY 20724',
    'text': 'Spend local question. Available mean statement compare method where spend. Theory senior assume stop its return.\nTrade professor sea group however edge than. Then again audience.',
    'email': 'samantha38@example.org',
    'phone_number': '6616999563',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Hunter',
],
    'json': {
    'name': 'Debra Marshall',
    'address': '057 Barbara Burg\nBrownton, MS 76174',
},
    'key18663': 'value9101',
    'key43606': 'value31067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Diana Sanchez',
    'address': '617 Harris Ports\nSandovalbury, TN 53680',
    'text': 'Nothing street dog who my happy sure.',
    'email': 'christina84@example.com',
    'phone_number': '329.910.5490',
    'array_int_dynamic': [
    55901,
],
    'array_varchar_dynamic': [
    'Cole Lowe',
    'Michael Rodriguez',
    'Kimberly Anderson',
],
    'json': {
    'name': 'Robert Williams',
    'address': '613 Hoffman Forest Apt. 850\nNorth Olivia, PW 66275',
},
    'key6729': 'value86660',
    'key50910': 'value93047',
    'key29045': 'value27554',
    'key56434': 'value64478',
    'key39837': 'value19469',
    'key70482': 'value65899',
    'key92205': 'value48990',
    'key33809': 'value5961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Amy Armstrong',
    'address': '0380 Brandon Inlet\nWest Matthewside, ID 17881',
    'text': 'Likely hold option center. Religious remember go according grow. Report step no.\nPresident son idea break poor line reveal. Else will article amount.',
    'email': 'james65@example.net',
    'phone_number': '882.309.9814x21638',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Mccormick',
    'John Dixon',
    'Keith Lynch',
    'Cheryl Lewis',
    'Leslie Johnson',
    'Dawn Mcdaniel',
    'Katherine Conner',
],
    'json': {
    'name': 'Heather Brown',
    'address': '6437 Megan Fords Suite 228\nNew Sara, MA 47332',
},
    'key42308': 'value78903',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Ellen Gibson',
    'address': '159 Amanda Ridges\nSouth Shannon, FL 84256',
    'text': 'Manage movement loss majority protect surface him.\nContinue reduce institution wonder behind career form such. Light somebody almost put many charge. Score house draw news step third three blue.',
    'email': 'manuelhines@example.net',
    'phone_number': '706-986-3723x75146',
    'array_int_dynamic': [
    66187,
],
    'array_varchar_dynamic': [
    'Melanie Chambers',
    'Jared Frederick',
    'Mr. Cory Castillo',
    'Michael Sampson',
    'Jennifer Middleton',
    'Alexander George',
],
    'json': {
    'name': 'Kevin Martinez',
    'address': '7899 Williams Canyon Suite 283\nSimpsonchester, AL 26956',
},
    'key73082': 'value93529',
    'key58199': 'value51127',
    'key19934': 'value31708',
    'key44065': 'value91670',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Susan Anderson',
    'address': '653 Moore Corner\nSouth Davidchester, WV 69890',
    'text': 'Whatever television maybe white small. Sell movie catch woman expert.\nHave because theory process side health. Test small tough yet ever theory.',
    'email': 'sperkins@example.com',
    'phone_number': '430.786.5090x8416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alex Harris',
    'Jessica Lewis',
    'Daniel Rodriguez',
    'Mr. William Thomas',
    'Thomas Rodriguez',
    'Jeffrey Wallace',
    'Cody Church',
],
    'json': {
    'name': 'Walter Riggs',
    'address': '040 Brown River Apt. 223\nIsaacville, OH 11445',
},
    'key5766': 'value6182',
    'key87928': 'value56080',
    'key25135': 'value32903',
    'key2150': 'value43230',
    'key92020': 'value3290',
    'key58217': 'value16273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Alex Shepard',
    'address': '1478 Malone Rue Apt. 666\nAmberton, MI 44164',
    'text': 'Radio road why make recent particular. Us we southern prevent.\nWoman team whole.\nLater blue tax fine. Figure sport hand hot.\nBack meet fall bar set.',
    'email': 'wortega@example.org',
    'phone_number': '001-917-842-0191',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mark Ray',
    'Stephanie Boyle',
    'Christopher Taylor',
    'Hannah Reynolds',
],
    'json': {
    'name': 'Amanda West',
    'address': '25169 Danielle Station Suite 927\nPattersonfurt, OH 55965',
},
    'key34475': 'value38338',
    'key22571': 'value22203',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Sharon Rogers',
    'address': '568 Keller Village Apt. 368\nNew Karina, ND 24167',
    'text': 'Staff good a firm old cell. Can reason probably election.\nExpect opportunity determine realize commercial agree shake.\nFinal more oil trouble after fast million. Seven night stand whole later.',
    'email': 'john18@example.net',
    'phone_number': '632-297-1442',
    'array_int_dynamic': [
    17534,
],
    'array_varchar_dynamic': [
    'Rebecca Burns',
    'Samantha Perez',
],
    'json': {
    'name': 'Michael Scott',
    'address': '165 King Court Suite 754\nAshleehaven, VA 75683',
},
    'key45283': 'value11772',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'David Owens',
    'address': '64470 Green Mill Suite 986\nPort Aaronton, MA 16792',
    'text': 'Stay perform occur no million ahead. Onto box happy material upon many.\nMovement dinner fear tax character must fish.',
    'email': 'rodneymedina@example.net',
    'phone_number': '918-668-9128x853',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Diana Hooper',
],
    'json': {
    'name': 'Danielle Brady',
    'address': 'PSC 4809, Box 3778\nAPO AA 86993',
},
    'key82707': 'value42994',
    'key82375': 'value78550',
    'key38379': 'value58505',
    'key63591': 'value68859',
    'key46719': 'value10949',
    'key96983': 'value53452',
    'key41001': 'value72711',
    'key30242': 'value12951',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Donald Burnett',
    'address': '9188 Brian Row\nMicheleborough, SD 44978',
    'text': 'Different town walk discussion report ago back. Raise history industry product hotel collection.\nParent speak radio. How girl strategy consumer office wait carry. Line travel fire whose spring.',
    'email': 'randy44@example.com',
    'phone_number': '+1-919-661-9374x504',
    'array_int_dynamic': [
    4718,
],
    'array_varchar_dynamic': [
    'Tina Powers',
    'Mrs. Katelyn Gonzalez DDS',
    'Diana Moran',
],
    'json': {
    'name': 'Mary Ramirez',
    'address': '449 Hebert Squares\nDavisbury, AS 69498',
},
    'key71337': 'value38842',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Roger Anderson',
    'address': '538 Lindsey Terrace Suite 302\nMilesville, ID 52895',
    'text': 'Method concern soldier say. Lead whether source anything at.\nPersonal rather through determine opportunity model really. Easy relationship form newspaper about wind contain.',
    'email': 'morgannichols@example.net',
    'phone_number': '(483)288-8072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Edwin Smith',
],
    'json': {
    'name': 'Jeffrey Edwards',
    'address': '944 Daugherty Summit\nMartinport, AS 24777',
},
    'key31586': 'value12084',
    'key8562': 'value92826',
    'key6817': 'value72456',
    'key48521': 'value87726',
    'key38581': 'value20324',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'John Thompson',
    'address': '576 Kaiser Ridge\nLake Debbie, PR 93593',
    'text': 'Travel range operation that world. Paper between start.\nWhom difference fire prevent act do. Follow great difficult study find network hard. Thousand member consider well own.',
    'email': 'patricia71@example.com',
    'phone_number': '+1-697-727-6707',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Gilbert',
    'Katherine Peterson',
    'Matthew Sanford',
    'Christopher Kline',
    'Sonya King',
],
    'json': {
    'name': 'Matthew Carpenter',
    'address': '4770 Lee Street Suite 317\nDerekmouth, CA 16321',
},
    'key89201': 'value32938',
    'key33356': 'value27399',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Tony Mcdonald',
    'address': '8424 Richard Run Apt. 622\nWest Brianville, CT 45877',
    'text': 'Exist arm however bit low short. Parent receive agent become nature important.\nFund nature first way quite. Hotel financial half stand call these.\nSport Mr fall bed. Writer rich half human.',
    'email': 'ptaylor@example.net',
    'phone_number': '6613932018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Clayton',
    'Scott Wilson',
    'Erica Lopez',
    'Cassie Hensley',
    'Daniel Valdez',
    'Omar Lin',
    'William Hernandez',
    'Eric Ruiz',
    'Amy Jennings',
],
    'json': {
    'name': 'Eric Robinson',
    'address': '30789 Ruiz Rapid\nRogersville, NE 45499',
},
    'key32907': 'value92500',
    'key89385': 'value84561',
    'key29820': 'value91568',
    'key63463': 'value31491',
    'key25286': 'value78628',
    'key29548': 'value29765',
    'key74955': 'value43339',
    'key5805': 'value84080',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Joseph Parker Jr.',
    'address': '650 Bradshaw Shoals\nSouth Alexmouth, PA 49985',
    'text': 'Next back mind begin stand eye. Industry vote tend picture reveal fall investment.',
    'email': 'breanna29@example.com',
    'phone_number': '5732011603',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sheila Walker',
    'Deborah Campbell',
    'Jason Mcfarland',
    'Deborah Skinner',
    'Deborah Martinez',
],
    'json': {
    'name': 'Jonathan Cole',
    'address': '9742 Tanya Street Apt. 095\nWest Robertside, VI 81145',
},
    'key5495': 'value16313',
    'key20221': 'value89480',
    'key76130': 'value13790',
    'key8308': 'value67845',
    'key16818': 'value37135',
    'key10363': 'value9839',
    'key90676': 'value25737',
    'key8614': 'value49909',
    'key35425': 'value81434',
    'key43003': 'value54049',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Johnny Hill',
    'address': 'USNS Nunez\nFPO AA 50371',
    'text': 'Yet more fire dog safe goal friend there. Summer international media reveal way eye single spring.\nLeg message fight they market. Defense water interview. Matter shake long southern what.',
    'email': 'christopher19@example.com',
    'phone_number': '4852448023',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Cody Howard',
    'Michele Hamilton',
    'George Washington',
    'Larry Charles',
],
    'json': {
    'name': 'Colton Morales',
    'address': '49324 Armstrong Valleys\nDianaton, MH 70742',
},
    'key33124': 'value26974',
    'key41218': 'value41545',
    'key36174': 'value66177',
    'key50726': 'value72120',
    'key2517': 'value21251',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Taylor Robinson',
    'address': 'Unit 7134 Box 0429\nDPO AE 02582',
    'text': 'Southern serious campaign later. Stay different of two serve natural.\nRace foreign including foreign this receive strategy. Respond record leave president.',
    'email': 'robert10@example.net',
    'phone_number': '741-418-9600x553',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Adam Green',
    'Mr. Steven Lopez',
    'Mr. Joseph Hernandez',
    'Matthew Brock',
    'Lori Johnson',
    'Sarah Patterson',
    'Angela Lara',
],
    'json': {
    'name': 'Reginald Horne',
    'address': '582 Shaw Trace\nNew Michael, MA 45481',
},
    'key71063': 'value11817',
    'key58331': 'value96665',
    'key22742': 'value16716',
    'key95451': 'value91157',
    'key56300': 'value30735',
    'key70420': 'value61403',
    'key96188': 'value59047',
    'key52759': 'value113',
    'key6747': 'value90070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Nicole Simmons',
    'address': '7592 Ryan Passage\nBrianville, VA 34233',
    'text': 'Program less manager son feeling nation television. Or staff trip human. Natural evening president land special television.',
    'email': 'jon07@example.net',
    'phone_number': '414-282-8183x79843',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Andre Roberts',
    'Nancy Olson',
    'Megan Duncan',
    'Marc Hernandez',
    'Eric Key',
    'Stephanie Roach',
    'Peter Carrillo',
],
    'json': {
    'name': 'Katelyn Medina',
    'address': '1765 Lewis Fields Apt. 564\nMargarethaven, WY 99254',
},
    'key82286': 'value20248',
    'key19793': 'value75949',
    'key4796': 'value89871',
    'key84082': 'value84820',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Patricia Smith',
    'address': '922 Reynolds Fords Apt. 229\nThomasland, VT 60439',
    'text': 'White light fast provide chance research bed. Fear suddenly treatment speech home region serious cover. Difficult cold service front.',
    'email': 'luis37@example.com',
    'phone_number': '001-336-467-7713x1081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Cardenas',
    'Richard Wright',
    'Cheryl Bradley',
    'Jon Smith',
    'Jonathan Smith',
],
    'json': {
    'name': 'Darrell Travis',
    'address': '502 Herman Stravenue\nWest Amber, VA 38030',
},
    'key99573': 'value29361',
    'key86195': 'value5781',
    'key31962': 'value61142',
    'key99708': 'value62686',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Donna Hernandez',
    'address': '41336 Thomas Crossing Apt. 451\nRiceport, IA 84206',
    'text': 'College side product his member method. Around try rate record parent difficult.\nNotice really reason field live move treat. True life keep.',
    'email': 'hobbsclaudia@example.org',
    'phone_number': '+1-892-911-0700x252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amy Gill',
    'Bianca Castro',
    'Alan Nelson',
    'Michael White',
    'Scott Hanson',
    'Tiffany Clark',
    'Kathleen Smith',
    'Michael Thomas',
],
    'json': {
    'name': 'Shane Martinez',
    'address': '448 Monica Mission\nEast Ruth, MP 16360',
},
    'key97671': 'value33869',
    'key32485': 'value11615',
    'key68714': 'value15944',
    'key29069': 'value10800',
    'key35544': 'value82558',
    'key66535': 'value92048',
    'key36120': 'value89741',
    'key57775': 'value53564',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Bruce Cruz',
    'address': '038 Johnson Shores\nDonaldburgh, WY 45546',
    'text': 'Meeting beyond exist agreement recognize old. During do type one almost what fight.',
    'email': 'marionguyen@example.com',
    'phone_number': '482.904.8544x705',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Rodgers',
    'Shirley Goodwin',
    'Mary Porter',
    'Carolyn Rangel',
    'Mr. Brandon Delacruz',
    'Madison Mcdaniel',
    'Amanda Alvarez',
    'Nicholas Green',
    'Christopher Zhang',
    'Heather Jordan',
],
    'json': {
    'name': 'Christopher Moore',
    'address': '7087 Arnold Ford Apt. 075\nWest Jimmy, GU 96603',
},
    'key61881': 'value44715',
    'key72571': 'value34717',
    'key35816': 'value20177',
    'key95581': 'value32362',
    'key76521': 'value68153',
    'key46578': 'value21713',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Erika Gonzales',
    'address': '7615 Alexis Harbors\nSouth Robertview, HI 05011',
    'text': 'Truth score among industry. North senior open statement.\nTable tree three happen history sea memory. Key time many simply someone four.',
    'email': 'bernardhelen@example.net',
    'phone_number': '796.742.1825x7973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Philip Sanchez',
    'Thomas Guzman',
    'Jeremy Sellers',
    'Carolyn Gilbert',
    'Craig Watts',
],
    'json': {
    'name': 'Brian King',
    'address': '689 Gonzales Land Suite 631\nLeslieland, MS 85063',
},
    'key22448': 'value70774',
    'key91970': 'value94465',
    'key98559': 'value57869',
    'key38129': 'value59909',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Heidi Taylor',
    'address': '9473 Spencer Meadows\nBrownton, WA 46177',
    'text': 'Difficult doctor glass piece. Once become field want book suggest much.\nOpportunity energy measure situation dream event exist.',
    'email': 'martinsarah@example.com',
    'phone_number': '+1-636-455-4853x92244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brian Cameron',
    'Paul Anderson',
    'Dr. Frank White',
    'Jeff Johnson',
    'Wanda Sheppard',
],
    'json': {
    'name': 'Elizabeth Gonzales',
    'address': '704 Gary Glens Suite 785\nCollinsbury, LA 45814',
},
    'key96601': 'value48735',
    'key58435': 'value34700',
    'key8654': 'value1262',
    'key5699': 'value98366',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Sean Cowan',
    'address': '65512 Stephanie Manor Suite 091\nFitzgeraldland, LA 66109',
    'text': 'Effort purpose car size. From speech couple answer school old. First pay rather effort true nor charge.\nClearly since degree. Strong far professor represent reason.',
    'email': 'imartinez@example.org',
    'phone_number': '426.754.9072',
    'array_int_dynamic': [
    45840,
],
    'array_varchar_dynamic': [
    'Samantha Mills',
    'Patrick Melton',
    'Joshua Wilkins',
    'Michael Pierce',
    'Charles Herrera',
    'Robert Mueller',
],
    'json': {
    'name': 'Maria Wilson',
    'address': '0743 Jason Harbor Apt. 612\nKristenhaven, PA 82748',
},
    'key15174': 'value81871',
    'key37048': 'value89679',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Mary Hahn',
    'address': '668 Maldonado Grove\nNew Jeffrey, MN 72869',
    'text': 'Himself these instead approach record trouble modern. Old control story job health recent like.',
    'email': 'kgross@example.com',
    'phone_number': '+1-999-400-8886x104',
    'array_int_dynamic': [
    86653,
],
    'array_varchar_dynamic': [
    'Elizabeth Spencer',
    'Gregory Olson',
    'Jeremy Wheeler',
    'Sharon Douglas',
    'Ebony Hall',
    'Aaron Griffin',
    'Donald Castro',
    'Alyssa Raymond',
    'Christine Serrano',
],
    'json': {
    'name': 'Richard Long',
    'address': '4558 Lawson Mountains Apt. 218\nColetown, IA 95931',
},
    'key97601': 'value75028',
    'key73394': 'value84925',
    'key18565': 'value19479',
    'key46889': 'value85555',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Paul Ross',
    'address': '12551 Kevin Valleys\nPort James, HI 71594',
    'text': 'A art determine control authority old. Among necessary man create camera fly cost night. Indicate interesting pay design establish magazine. Generation particularly lead audience while like until.',
    'email': 'fduffy@example.org',
    'phone_number': '(891)479-7468x51572',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Wong',
    'Lisa Mccoy',
    'Ana Hernandez',
    'Elaine Mathews',
    'Ruben Park',
    'Pamela Chen',
],
    'json': {
    'name': 'Michelle Sullivan',
    'address': '78134 Kevin Road\nPort Katherineland, MS 93963',
},
    'key6709': 'value44724',
    'key86988': 'value67827',
    'key57288': 'value34249',
    'key26326': 'value42223',
    'key98730': 'value54473',
    'key73235': 'value35493',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Alexis Ryan',
    'address': 'USNV Cooley\nFPO AP 30898',
    'text': 'Else board morning wind. Word put town picture happen. Law task local like accept kitchen alone.',
    'email': 'uwheeler@example.com',
    'phone_number': '001-627-481-7621x1391',
    'array_int_dynamic': [
    2820,
],
    'array_varchar_dynamic': [
    'Lisa Marshall',
    'Laurie Hubbard',
    'Kimberly Wilson',
    'Elijah Vang',
],
    'json': {
    'name': 'Jack Williams',
    'address': '32832 Arnold Estates Apt. 691\nSouth Sarastad, GA 02113',
},
    'key82603': 'value38759',
    'key82617': 'value408',
    'key47875': 'value78394',
    'key25383': 'value39062',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Nicole Hall',
    'address': 'USNV Riley\nFPO AE 71254',
    'text': 'Same hold reduce event its. Occur society instead expect treatment whole four available. Remain huge customer bill town. Skill election take important very indeed rise.',
    'email': 'djennings@example.net',
    'phone_number': '711.998.2437x59146',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brian Preston',
    'Lisa Reyes',
    'Kylie Jackson',
    'Alisha Tucker',
    'David Powers',
    'Elizabeth Raymond',
    'Joseph Black',
],
    'json': {
    'name': 'Dr. Gabriella Arnold',
    'address': '71292 Medina Unions\nBurnsstad, AL 04167',
},
    'key76216': 'value34250',
    'key63336': 'value67953',
    'key88058': 'value80645',
    'key30628': 'value61206',
    'key67646': 'value29491',
    'key41773': 'value24975',
    'key56239': 'value44533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Anthony Cooper',
    'address': '32433 Danielle Ridges\nElizabethberg, OH 07015',
    'text': 'A special wait. Response boy term above computer.\nColor event chance. Drop guess relationship enter. Drug seat low information bad condition main.',
    'email': 'vanderson@example.net',
    'phone_number': '+1-989-883-4145x128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Neil King',
    'David Wright',
    'Veronica Hudson',
    'Tiffany Norman',
    'Randall Adams',
    'Holly Boyle',
    'Steve Newton',
    'Shelly Smith',
    'Paul Hall',
    'Elizabeth Escobar',
],
    'json': {
    'name': 'Manuel Alvarez',
    'address': '2908 Jessica Locks Apt. 505\nNicoleland, CA 58681',
},
    'key2417': 'value67487',
    'key15548': 'value77711',
    'key82697': 'value89768',
    'key85794': 'value54812',
    'key59348': 'value59948',
    'key30966': 'value50598',
    'key69856': 'value99219',
    'key95368': 'value63419',
    'key6867': 'value66744',
    'key40119': 'value37560',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Brianna Johnson',
    'address': '55889 Scott Throughway\nPort Leah, VI 53709',
    'text': 'Clearly edge that organization ground political travel marriage. Mr blood herself language treatment style. Among benefit stay sense meet. Traditional trip short fly again reach.',
    'email': 'woodsalisha@example.org',
    'phone_number': '992-689-0746x9790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lacey Archer',
],
    'json': {
    'name': 'David Green III',
    'address': '708 Kelly Trace Suite 402\nNew Bruce, MH 21203',
},
    'key68993': 'value41293',
    'key38046': 'value78624',
    'key44597': 'value65114',
    'key34379': 'value9575',
    'key78723': 'value41080',
    'key50755': 'value51453',
    'key86530': 'value28200',
    'key81811': 'value5482',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Andrew Burnett',
    'address': '7869 Howard Drives\nPort Tylermouth, FL 72794',
    'text': 'About heavy audience guess turn. Assume leg sister staff lot firm. Her commercial report trial grow through.\nAgency hundred for. Movie skill professor issue call manage. But modern recently six area.',
    'email': 'dmcmillan@example.com',
    'phone_number': '568-534-3611x9134',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Brown',
    'Christopher York',
    'John Barnes',
    'Christopher Madden',
    'Joshua Phillips',
    'Johnathan Peters',
    'Kristina Ashley',
    'Devon Johnson',
    'Jeffrey Fox',
],
    'json': {
    'name': 'Brian Hill',
    'address': '617 Reeves Dale Apt. 899\nNew Christopherfort, UT 22874',
},
    'key2605': 'value44190',
    'key81693': 'value30902',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Martha Cook',
    'address': '81925 Adams Prairie Suite 143\nNew Andrew, IL 34659',
    'text': 'Girl job condition middle. Year sort together.\nOrganization able level rest question himself. Laugh democratic less ten arm student.',
    'email': 'norrisroger@example.com',
    'phone_number': '(535)481-4332x01677',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Adkins',
    'Tiffany Patterson',
    'Michael Johnson',
    'William Delgado',
    'Julie Lopez',
    'James Calderon',
    'Kathy Smith',
],
    'json': {
    'name': 'Jenny Li',
    'address': 'Unit 5202 Box 1461\nDPO AA 42945',
},
    'key63121': 'value69233',
    'key46073': 'value76892',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jacqueline Ashley',
    'address': '003 Elizabeth Rapids Suite 909\nSouth Christine, ND 05035',
    'text': 'Finish process care however.\nSouth either professional girl church. Admit performance social career late important control. Phone state size area call.',
    'email': 'swilliams@example.net',
    'phone_number': '(238)929-0836x6800',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Wall',
    'Robert Martin',
    'James Mahoney',
    'Sheila Roberson',
    'Cory Johnson',
],
    'json': {
    'name': 'Carol Strong',
    'address': 'USCGC Abbott\nFPO AE 63947',
},
    'key31541': 'value16341',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Erica Jones',
    'address': '800 Espinoza Lake\nPort Katherine, RI 70759',
    'text': 'Recognize its least stay physical next other. Meet along land practice spring.',
    'email': 'smithandrea@example.org',
    'phone_number': '582.467.0875x46192',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Horton',
    'Ms. Karen Hutchinson DVM',
    'Bonnie Tate',
    'Brittany Pena',
],
    'json': {
    'name': 'Stephanie Ward',
    'address': '320 Guerrero Turnpike Apt. 886\nRebeccamouth, SC 25625',
},
    'key69358': 'value67045',
    'key67586': 'value37591',
    'key84379': 'value50375',
    'key85683': 'value49520',
    'key35699': 'value37174',
    'key74623': 'value6099',
    'key11361': 'value9993',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Christopher Todd',
    'address': '77582 Parker Burgs Apt. 001\nRomerobury, MS 52795',
    'text': 'International together series have. Economy much with service teach.\nMaterial they probably industry your. Up morning force wind exactly allow tax. Relate ahead stay too recent.',
    'email': 'stevenwalter@example.net',
    'phone_number': '370-989-7097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Corey Anderson',
    'Jennifer Davis',
    'Susan Leach',
    'David Preston',
    'Adam Roach',
    'Stephanie Rowe',
    'Michael Harrell',
],
    'json': {
    'name': 'Ronald Keller',
    'address': '1229 Russell Passage Apt. 277\nEdwardsville, WV 98212',
},
    'key25838': 'value50624',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Rachael Anderson',
    'address': '7204 Robert Turnpike\nRamosside, AL 78259',
    'text': 'Per sport this. Art enough leg training everybody.\nNature something boy director type north assume lawyer. Manage computer all simply wall his establish. Bag best term act never likely.',
    'email': 'steven73@example.com',
    'phone_number': '789.555.9812x274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Medina',
],
    'json': {
    'name': 'Adam Cain',
    'address': '26368 Jeff Passage\nWest Justin, ID 22054',
},
    'key71803': 'value78765',
    'key12269': 'value31037',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Rebecca Stokes',
    'address': '224 Karla Hills Suite 183\nWest Erik, AL 15350',
    'text': 'Once despite less take figure rise. Glass so people me.\nWrong way school.\nPlay memory eat whatever each page. Understand this happen traditional full total.',
    'email': 'gloverkatie@example.org',
    'phone_number': '(228)214-1827x0974',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cory Bowman',
    'Tony Park',
],
    'json': {
    'name': 'James Tucker',
    'address': '81665 Duncan Inlet\nLake William, DE 50739',
},
    'key48798': 'value59795',
    'key5817': 'value24000',
    'key61781': 'value74144',
    'key58781': 'value3250',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Cody Brown',
    'address': '1625 Craig Islands Apt. 702\nSouth Jenniferview, VT 70174',
    'text': 'Skin artist option well country. Century large institution sit. Reality crime another stand market.\nStrategy drug challenge recently.\nCenter look example good. Work beyond so that hospital dinner by.',
    'email': 'usmith@example.com',
    'phone_number': '432-501-7086',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Frances Cox',
    'Charles Patterson',
    'Misty Ward',
    'Alexander Anderson',
    'Danny Douglas',
    'Shannon Williams',
    'Julie Johnston',
    'Jeffery Tran',
],
    'json': {
    'name': 'James Brown',
    'address': '90460 Jacobs Summit\nEast Markton, MN 10708',
},
    'key63286': 'value93088',
    'key55758': 'value55909',
    'key97836': 'value62923',
    'key46244': 'value15575',
    'key66503': 'value9739',
    'key95708': 'value35710',
    'key45690': 'value29218',
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
    'RequestId': 'e62a65d6-62ee-11f0-bae5-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_17_44_176106wAiIwJFc',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752743875.json')
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
    test = AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulQueryVectorBySdk1752743875Json()
    test.run_tests()
