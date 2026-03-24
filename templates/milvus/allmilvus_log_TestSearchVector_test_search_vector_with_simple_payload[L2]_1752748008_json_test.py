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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_simple_payload[L2]_1752748008_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[L2]_1752748008.json"
VDB_TYPE = "milvus"


def send_request(content, request_type="POST", url_path="http://172.17.0.5:23210/v2/vectordb/collections/create", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"POST"
        url_path: URL路径，默认为"http://172.17.0.5:23210/v2/vectordb/collections/create"
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithSimplePayloadL21752748008Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[L2]_1752748008.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[L2]_1752748008.json"
        self.test_count = 8  # 测试方法数量
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
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_38_769242sAuSmufu',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://172.17.0.5:23210/v2/vectordb/collections/describe"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/describe")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/describe'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_38_769242sAuSmufu',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v2/vectordb/entities/insert"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/insert")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/insert'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_38_769242sAuSmufu',
    'data': [
    {
    'id': 17527480048216,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Bryce Mills',
    'address': '71513 Stephens Mill\nLake Marie, MP 98641',
    'text': 'Including trial should. Section third ok today. General sign smile dark.\nForm president run up. Respond gas could decide. War chance body.',
    'email': 'kentkaitlyn@example.org',
    'phone_number': '668-478-2845',
    'json': {
    'name': 'Robert Baxter',
    'address': '234 Angela Forks Suite 617\nEast Justin, PW 44417',
},
    'key77999': 'value82280',
    'key51543': 'value92585',
    'key56989': 'value32700',
    'key81099': 'value43172',
    'key58503': 'value86342',
    'key77942': 'value57028',
    'key36359': 'value63600',
    'key60778': 'value37322',
    'key50606': 'value83578',
    'key40998': 'value7802',
},
    {
    'id': 17527480048231,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Austin Robles',
    'address': '872 Thompson Lane\nPort Roberto, DE 75158',
    'text': 'Nearly yet very environmental believe future involve. Quickly pattern fill second name.\nPhone traditional activity sound. Fear maybe indeed defense.',
    'email': 'jose35@example.com',
    'phone_number': '001-597-549-3880x22673',
    'json': {
    'name': 'Michael Nguyen',
    'address': '306 Ricky Union Suite 708\nStephanieside, RI 18650',
},
    'key65675': 'value74742',
    'key19297': 'value5959',
    'key6820': 'value61163',
    'key53247': 'value54885',
    'key16444': 'value592',
    'key46422': 'value61100',
    'key58715': 'value48329',
    'key94659': 'value45127',
    'key86333': 'value57995',
    'key14148': 'value54515',
},
    {
    'id': 17527480048244,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Dr. Melanie Boyer',
    'address': '700 Park Lodge\nSouth Candace, MO 01630',
    'text': 'Cell source wall return. Ever those interview degree line we.\nMeeting player remember do. Concern soldier none firm.',
    'email': 'nichole39@example.com',
    'phone_number': '999.802.5501',
    'json': {
    'name': 'Pamela Bennett',
    'address': '444 Andrews Station Apt. 193\nSouth Stephanie, HI 64986',
},
    'key70681': 'value74712',
    'key37923': 'value43810',
    'key60885': 'value82706',
},
    {
    'id': 17527480048256,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Daniel Garner',
    'address': '5905 Jeff Turnpike\nMendozaton, MH 68721',
    'text': 'Bit edge job bring style man movement. Design possible source series increase no.\nThank box single police audience. Result executive guy finish. Sure thought reveal term.',
    'email': 'derek25@example.org',
    'phone_number': '992.200.4451',
    'json': {
    'name': 'Erica Williams',
    'address': '7045 Crystal Forges Suite 281\nPort Patriciahaven, PA 11579',
},
    'key50777': 'value35638',
    'key89897': 'value54610',
    'key83056': 'value71225',
    'key59505': 'value92000',
    'key65289': 'value43630',
    'key87201': 'value74404',
},
    {
    'id': 17527480048268,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Kurt White',
    'address': '610 Carter Drive\nBeckview, HI 29213',
    'text': 'Attorney tax amount million. Huge mission difficult lose poor. Defense leg admit meet.\nMajority ago beyond.',
    'email': 'smithleslie@example.com',
    'phone_number': '867.447.6937',
    'json': {
    'name': 'Logan Smith',
    'address': '395 Fleming Extensions\nPort Tom, IA 18291',
},
    'key56656': 'value35243',
    'key55609': 'value42504',
    'key19730': 'value38676',
    'key23314': 'value69814',
    'key89162': 'value61900',
    'key83950': 'value12875',
    'key84001': 'value87071',
    'key70165': 'value3256',
},
    {
    'id': 17527480048282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Bryan Rhodes',
    'address': '69343 Jeffrey Oval Apt. 756\nMatthewfurt, GU 02224',
    'text': 'Idea pass western idea speech. Call idea experience money management toward edge want. Reach always ok cover everything explain manager.',
    'email': 'shawsheena@example.org',
    'phone_number': '8055218470',
    'json': {
    'name': 'Lawrence Jacobs',
    'address': '59383 Peterson Run Suite 920\nDawnfort, GA 99540',
},
    'key2980': 'value66621',
    'key30987': 'value77119',
    'key38043': 'value91476',
    'key56969': 'value37890',
},
    {
    'id': 17527480048294,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Paula Gordon',
    'address': '02516 Silva Courts Apt. 535\nEast Gabriel, TX 42072',
    'text': 'Would over author building take decision role. Page attorney agreement leg interview. Where arm speech investment.',
    'email': 'andersonsteven@example.com',
    'phone_number': '001-554-439-4592x353',
    'json': {
    'name': 'Peter Moore',
    'address': 'Unit 0533 Box 3858\nDPO AA 18780',
},
    'key22561': 'value59487',
    'key93631': 'value94006',
    'key44491': 'value32967',
    'key71527': 'value45156',
},
    {
    'id': 17527480048305,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Janice Dodson',
    'address': '761 Benjamin Wells Suite 105\nWest Lonnie, MO 75305',
    'text': 'Low whom reduce all. Sing its able others name wall.\nMember western just. Risk face task. Character too movie force. Politics country person tell up.',
    'email': 'dawn40@example.net',
    'phone_number': '(791)207-7657',
    'json': {
    'name': 'George Ramirez',
    'address': '40978 Marshall Loop\nNorth Chelseaville, ME 85397',
},
    'key13996': 'value20493',
    'key42916': 'value62461',
    'key320': 'value1929',
    'key16699': 'value13551',
    'key79936': 'value24659',
    'key3430': 'value53158',
    'key60458': 'value13836',
    'key84808': 'value19834',
    'key5549': 'value89145',
},
    {
    'id': 17527480048317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Miss Daisy Shaffer DVM',
    'address': '91284 Zimmerman Falls Suite 384\nDuarteside, AS 88248',
    'text': 'Mission chair speech conference mean. Future nor couple around less grow outside. Arm without ever situation she maybe too cost.',
    'email': 'paul49@example.com',
    'phone_number': '(855)899-1786x83137',
    'json': {
    'name': 'David King',
    'address': '0105 Tanner Park\nLake Tiffany, GA 09464',
},
    'key55676': 'value38518',
    'key68679': 'value59115',
    'key13861': 'value36487',
},
    {
    'id': 17527480048329,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'James Hopkins',
    'address': '8217 Garcia Fall Suite 573\nRowlandton, KY 14127',
    'text': 'Institution research international energy. Relationship teach across size.\nHard him often fear expert. Seven national point effort under poor building card. Establish understand he.',
    'email': 'amanda14@example.org',
    'phone_number': '001-634-345-4108x31128',
    'json': {
    'name': 'Maria Brown',
    'address': '7033 Jonathan Common\nCherylborough, AS 95541',
},
    'key6289': 'value45861',
    'key13744': 'value23739',
    'key52149': 'value73981',
    'key36073': 'value45604',
    'key78393': 'value23371',
    'key93961': 'value38785',
    'key61595': 'value74260',
    'key95293': 'value27429',
    'key46652': 'value1609',
},
    {
    'id': 17527480048341,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Christopher Douglas',
    'address': '47352 Wallace Lights Apt. 299\nAndrewland, OK 32954',
    'text': 'Like particular dinner crime action chair. Character condition admit use property research each.',
    'email': 'ericwilson@example.org',
    'phone_number': '708-772-0468x32442',
    'json': {
    'name': 'Jacqueline Klein',
    'address': 'Unit 2414 Box 8214\nDPO AP 17656',
},
    'key50084': 'value16143',
},
    {
    'id': 17527480048352,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Karen Hicks',
    'address': '22886 Timothy Ville Suite 694\nAllenhaven, MT 57481',
    'text': 'Put dinner station different finally within wide. No water sister.\nHeart level quality market. Charge hit movie shake store.',
    'email': 'shelly15@example.com',
    'phone_number': '(737)404-4264x579',
    'json': {
    'name': 'Melissa Mccormick',
    'address': '525 Michael Meadows Suite 641\nChristophershire, AZ 17153',
},
    'key3366': 'value16579',
    'key80211': 'value31124',
    'key61590': 'value58528',
    'key43483': 'value48907',
},
    {
    'id': 17527480048364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Lori Duncan',
    'address': '625 Jackie Burg Suite 518\nEast Andres, AL 81494',
    'text': 'Skill help list leader tree. Any great meet scientist several government. Second eye organization.\nPlan environment thus five resource. Network always huge. Company a number save.',
    'email': 'michelle12@example.com',
    'phone_number': '+1-433-266-4573x635',
    'json': {
    'name': 'Nicholas Manning',
    'address': 'USCGC Dunn\nFPO AE 63931',
},
    'key8104': 'value97630',
    'key16050': 'value97475',
    'key27824': 'value8776',
    'key17790': 'value65479',
    'key64286': 'value39502',
},
    {
    'id': 17527480048374,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jessica Smith',
    'address': '90739 Tiffany Mountain\nBrownshire, AZ 09035',
    'text': 'Quality paper outside until agreement staff listen. Enjoy meeting million collection group.\nProcess senior standard religious. Ahead learn strategy professor share.',
    'email': 'kayla90@example.com',
    'phone_number': '567.236.4699',
    'json': {
    'name': 'Anthony York',
    'address': '359 Amanda Highway Suite 202\nSouth Daisystad, MD 04632',
},
    'key87381': 'value77337',
    'key610': 'value49597',
    'key84200': 'value91377',
    'key4802': 'value85087',
},
    {
    'id': 17527480048386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jason Myers',
    'address': '672 Jacob Harbors Apt. 639\nFletcherfort, NJ 29607',
    'text': 'We matter call activity ready. Summer suggest we two Republican much. Society real now wear mother use building.',
    'email': 'grahamlinda@example.com',
    'phone_number': '694-641-6598',
    'json': {
    'name': 'Charles Molina',
    'address': '2054 Tran Street Apt. 177\nEast Bradleyview, WV 42648',
},
    'key72381': 'value50108',
    'key21086': 'value63368',
    'key10831': 'value19373',
    'key15309': 'value1078',
    'key81429': 'value58522',
    'key82978': 'value85361',
    'key62583': 'value76557',
    'key63682': 'value2018',
},
    {
    'id': 17527480048398,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Kathy Guzman',
    'address': '3574 Barron Spring Apt. 330\nAndersonberg, IL 40404',
    'text': 'Thank pay visit box little she. Concern land what institution become within realize.\nWrong can everyone account upon son couple. Soldier day health service produce institution car.',
    'email': 'bcarr@example.com',
    'phone_number': '+1-640-664-7834x56388',
    'json': {
    'name': 'Debra Barry',
    'address': '4399 Garcia Port Apt. 545\nWendyfurt, PR 46343',
},
    'key57035': 'value9287',
    'key28046': 'value86800',
    'key1407': 'value40828',
    'key8471': 'value86553',
},
    {
    'id': 17527480048411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Amanda Dalton',
    'address': 'Unit 1833 Box 2575\nDPO AP 85686',
    'text': 'Simple effort reality third Democrat. Effect throw professor never look decide send.\nReflect young although crime big western. Opportunity grow region particularly often.',
    'email': 'kenneth32@example.net',
    'phone_number': '(854)902-0692',
    'json': {
    'name': 'Maria Michael',
    'address': 'Unit 2015 Box 0901\nDPO AE 85963',
},
    'key22513': 'value88933',
    'key43960': 'value4178',
    'key9465': 'value73231',
    'key17151': 'value9304',
    'key50284': 'value49486',
    'key27028': 'value67164',
    'key25585': 'value65684',
    'key18680': 'value17512',
},
    {
    'id': 17527480048418,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Brandon Morris',
    'address': '49969 Dodson Keys\nWest Brian, ME 25765',
    'text': 'Special fill Congress present really century. Federal fish whatever north. Card yet drug speak themselves add author job.\nGo once police. Phone company college expert sit.',
    'email': 'nathan94@example.org',
    'phone_number': '2384184765',
    'json': {
    'name': 'Erica Summers',
    'address': '588 James Road\nLake Sarahshire, MI 53244',
},
    'key16130': 'value36224',
    'key53347': 'value5990',
    'key55270': 'value52537',
    'key10603': 'value10829',
    'key3072': 'value25279',
    'key94222': 'value48742',
    'key14495': 'value77353',
    'key11764': 'value78326',
},
    {
    'id': 17527480048430,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Deborah Jordan',
    'address': 'PSC 4571, Box 5971\nAPO AP 84606',
    'text': 'Become important account. Born happen throughout red ten offer ask. Question grow almost deal husband. Stand check speak action fear base usually attention.',
    'email': 'desireeanderson@example.com',
    'phone_number': '(970)652-4336',
    'json': {
    'name': 'Russell Harris',
    'address': '77988 Wilkinson Motorway Apt. 587\nCruzfurt, MH 02694',
},
    'key85137': 'value37949',
},
    {
    'id': 17527480048440,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Lisa Adams',
    'address': '376 Katie Corner\nHillville, AR 01455',
    'text': 'Even view use perhaps nature stand. Eat until agent one point experience every. Factor a affect describe perhaps something.',
    'email': 'geoffreylane@example.net',
    'phone_number': '001-215-463-5791x654',
    'json': {
    'name': 'Erica Guzman',
    'address': '132 Andrews Corners Suite 782\nValeriemouth, TX 38798',
},
    'key96414': 'value84839',
    'key75000': 'value86303',
    'key46046': 'value61844',
    'key60375': 'value36679',
    'key4983': 'value95910',
    'key92909': 'value96046',
},
    {
    'id': 17527480048452,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Kim Dyer',
    'address': '44880 Reyes Street Apt. 547\nNew Charles, MD 51209',
    'text': 'Suffer long fact soldier vote set term project. Carry especially artist effect board.',
    'email': 'holly16@example.net',
    'phone_number': '001-280-491-9206x4391',
    'json': {
    'name': 'Lauren Robles',
    'address': '93691 Jeremy Skyway Suite 207\nSouth Richardmouth, WY 44588',
},
    'key21289': 'value51091',
    'key93291': 'value69607',
    'key24032': 'value92317',
    'key95881': 'value31081',
    'key14319': 'value81420',
    'key52917': 'value82422',
},
    {
    'id': 17527480048463,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Holly Thompson',
    'address': '845 Fisher Lock Apt. 912\nTammybury, NY 67877',
    'text': 'Such century recently shake million. Together will success brother leader step both.\nBetter hold any sister. Foreign change area perhaps.',
    'email': 'james47@example.org',
    'phone_number': '587.329.3461',
    'json': {
    'name': 'Monica Mccarthy',
    'address': '5884 Roberts Crescent\nNorth Aaron, MP 55815',
},
    'key9636': 'value73453',
},
    {
    'id': 17527480048474,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'James Bryant',
    'address': '38816 Nichole Valley\nNorth Spencerside, HI 45345',
    'text': 'Outside song across then.\nSon image glass clear. Explain car agree three lead. Option war agree stay rule happy.\nLawyer garden behind wonder prevent past. He science action wear garden.',
    'email': 'kimberlywall@example.org',
    'phone_number': '+1-580-526-2741x66529',
    'json': {
    'name': 'Kyle Harris',
    'address': '388 Callahan Overpass\nNorth David, FL 22784',
},
    'key96248': 'value31215',
    'key34277': 'value13295',
    'key12178': 'value82196',
    'key43200': 'value14763',
    'key45487': 'value13618',
    'key6628': 'value72402',
    'key56417': 'value31237',
},
    {
    'id': 17527480048486,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Pamela Hernandez',
    'address': '34991 Terrell Drive\nRodgersville, SD 43207',
    'text': 'Also reduce couple structure. Describe early factor official others education special. Kitchen strategy door we call discussion sort I.',
    'email': 'mcconnellmarco@example.net',
    'phone_number': '2909956399',
    'json': {
    'name': 'Sandra Carney',
    'address': '906 Gross Cove\nNunezville, OR 31219',
},
    'key33217': 'value46490',
},
    {
    'id': 17527480048497,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Christina Garcia',
    'address': '38181 Michelle Valleys Suite 736\nSherrymouth, CO 29011',
    'text': 'Move dark person body bring these rich. According common while game understand order.\nParty break visit. Run exist purpose us.',
    'email': 'andrew38@example.net',
    'phone_number': '457.916.7139x132',
    'json': {
    'name': 'Joe Smith',
    'address': '77537 Cantu Cape Suite 102\nNew Justinmouth, MD 68718',
},
    'key34077': 'value73318',
    'key62108': 'value23810',
    'key24433': 'value5797',
    'key77262': 'value6647',
    'key36023': 'value14751',
    'key51983': 'value97379',
},
    {
    'id': 17527480048508,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Joshua Parker',
    'address': '0503 Lynch Mall\nDavisville, PR 73884',
    'text': 'Side walk table improve. Training close two ground step catch. Hundred hour difficult soon possible window research.\nRun agent same her. Onto cover himself chance.',
    'email': 'kennethburnett@example.org',
    'phone_number': '456.339.1339x0882',
    'json': {
    'name': 'Andrea Simpson',
    'address': '0901 Mark Lodge\nRobertland, NC 55634',
},
    'key69557': 'value69750',
    'key18199': 'value95051',
    'key58976': 'value29770',
    'key27785': 'value55483',
},
    {
    'id': 17527480048520,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Bryce Chavez',
    'address': '679 Ross Overpass\nEast Roy, MD 70572',
    'text': 'Machine fly better. Yourself common professor small compare. Suffer fast ago chair try.\nPower interview time treatment she sometimes experience.',
    'email': 'craig90@example.org',
    'phone_number': '+1-873-732-8689x46126',
    'json': {
    'name': 'Melissa Lewis',
    'address': '426 Nancy Estates\nClarkemouth, NM 29830',
},
    'key76648': 'value48560',
    'key32300': 'value77812',
    'key74758': 'value59764',
    'key67512': 'value98256',
    'key43892': 'value47617',
    'key88946': 'value30107',
    'key13030': 'value90508',
    'key64204': 'value70370',
},
    {
    'id': 17527480048530,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Matthew Davis',
    'address': '0003 Destiny Mill\nWest Michaelland, WV 46158',
    'text': 'I Republican over environment thought. Analysis moment loss whose pattern. Join college want hundred. Across information western third.',
    'email': 'zluna@example.com',
    'phone_number': '5122852792',
    'json': {
    'name': 'Lisa Sanchez',
    'address': '8602 Pamela Radial\nWest Cheryl, FL 21466',
},
    'key63515': 'value24785',
},
    {
    'id': 17527480048541,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Stephanie Kramer',
    'address': '7976 Rodriguez Place Apt. 393\nEast Ambermouth, PR 25942',
    'text': 'Glass law official listen already smile. Ask son capital nothing total environmental. Example necessary professor fear move save.',
    'email': 'velezrussell@example.com',
    'phone_number': '(873)370-2598',
    'json': {
    'name': 'Lisa Rasmussen',
    'address': '31529 Camacho Curve Apt. 710\nHollowayview, GA 68203',
},
    'key4240': 'value56458',
    'key98896': 'value39183',
    'key76139': 'value57394',
    'key78195': 'value45363',
    'key53918': 'value98095',
    'key48615': 'value20484',
    'key32247': 'value7981',
},
    {
    'id': 17527480048553,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Sean Simmons',
    'address': '808 Randy Coves\nWest Carlview, WI 75146',
    'text': 'Teacher fish kind system natural. Certain four across throw table stand. Ask a raise similar.\nWrong experience expect. Tonight course turn son stock. Own particular place sort operation.',
    'email': 'erin40@example.net',
    'phone_number': '9298806340',
    'json': {
    'name': 'Leslie May',
    'address': 'Unit 1643 Box 7630\nDPO AE 70056',
},
    'key14163': 'value5919',
    'key22056': 'value50980',
},
    {
    'id': 17527480048561,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Randall White',
    'address': '900 Sandra Row\nBowersport, NE 36396',
    'text': 'Behind impact always number. Medical yet see. Beyond mother section trouble religious.\nDay statement movement memory. Money choose head finally laugh believe life.',
    'email': 'madelinemyers@example.org',
    'phone_number': '001-347-595-1700x233',
    'json': {
    'name': 'Amanda Craig',
    'address': '499 Stephanie Ridges\nDustinburgh, NJ 65721',
},
    'key57948': 'value31161',
    'key27460': 'value26895',
    'key24339': 'value87536',
    'key74775': 'value55859',
    'key5480': 'value83740',
    'key93472': 'value73964',
},
    {
    'id': 17527480048572,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Rachel Cobb',
    'address': '023 Jasmine Street\nGeraldmouth, AR 50591',
    'text': 'War his understand deep. Pretty property tough. Throw beat perform stock month.\nMore drug why provide. Large team gas read. Learn miss cultural three rest seem him.',
    'email': 'joseph66@example.net',
    'phone_number': '(230)476-2226x390',
    'json': {
    'name': 'Ethan Castaneda',
    'address': '1139 Wyatt Summit\nPort Alexandershire, IA 80447',
},
    'key46519': 'value24569',
    'key46168': 'value27225',
},
    {
    'id': 17527480048582,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Christopher Taylor',
    'address': '3007 Alison Square Apt. 158\nBrauntown, VI 06436',
    'text': 'Different arm too here. Despite month everything final drug science guy. Especially term wrong budget wind hot movie institution.',
    'email': 'hallashley@example.org',
    'phone_number': '001-928-961-5281x60315',
    'json': {
    'name': 'Jeffrey Collier',
    'address': '3749 Long Passage\nWest Miguelburgh, NE 63709',
},
    'key5735': 'value61926',
},
    {
    'id': 17527480048593,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jonathan Lawson',
    'address': 'PSC 5618, Box 6847\nAPO AA 58003',
    'text': 'Thank chance student grow town. Since bad design control.\nMajority think local although raise. Coach subject environmental enjoy about.',
    'email': 'jamesgreen@example.org',
    'phone_number': '772.866.0171x6714',
    'json': {
    'name': 'Steven Charles',
    'address': '4350 Cruz Square\nAngelaview, NJ 17769',
},
    'key79607': 'value1879',
    'key13699': 'value24312',
    'key53374': 'value44704',
    'key72679': 'value13840',
    'key35836': 'value35504',
    'key83751': 'value11',
},
    {
    'id': 17527480048603,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Samuel Mason',
    'address': '87490 Marshall Oval\nNorth Stephen, AR 57155',
    'text': 'Live necessary treat sound common. Know consider car sort billion mouth law. Enjoy economic later yet.\nContinue any affect bit challenge. Less whose southern remember pass.',
    'email': 'ogutierrez@example.net',
    'phone_number': '480-580-2828x07537',
    'json': {
    'name': 'Brian Washington',
    'address': '325 Sharon Ferry\nNorth Christine, MN 46732',
},
    'key96647': 'value72196',
    'key81585': 'value96367',
    'key1489': 'value54184',
    'key62244': 'value85891',
    'key57430': 'value52719',
    'key86406': 'value92318',
    'key79511': 'value66235',
    'key20403': 'value50931',
    'key13734': 'value47711',
    'key85412': 'value3224',
},
    {
    'id': 17527480048613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Nicholas Lowe',
    'address': '72375 Clark Valley Suite 351\nMeganfort, NY 92451',
    'text': 'Market group this military. Industry tonight claim lead everybody character. Job mention soldier.\nWithout yeah song enough particular wind employee feeling.',
    'email': 'todd92@example.net',
    'phone_number': '3783657090',
    'json': {
    'name': 'Brian Cummings',
    'address': '558 Scott Estates\nLake Jill, MA 65372',
},
    'key23287': 'value74714',
    'key80597': 'value50191',
    'key74325': 'value15388',
    'key8771': 'value6068',
    'key20681': 'value83852',
    'key27418': 'value91460',
    'key25990': 'value65647',
    'key85351': 'value70414',
    'key12059': 'value23361',
},
    {
    'id': 17527480048624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Sandy Carter',
    'address': '8527 Ellison Plaza\nRiceshire, TN 64790',
    'text': 'Young change tell goal occur space air. Join there hope author hear hot.\nTelevision get analysis he least standard concern church. Section office administration hard black.',
    'email': 'angela13@example.com',
    'phone_number': '001-371-864-0790x179',
    'json': {
    'name': 'Larry Ward',
    'address': '7039 Johnson Expressway Apt. 389\nAlejandraside, IA 58417',
},
    'key57712': 'value6431',
    'key65864': 'value49701',
    'key71883': 'value49150',
    'key31526': 'value74923',
    'key77339': 'value71884',
    'key26767': 'value60686',
    'key29627': 'value55857',
},
    {
    'id': 17527480048635,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Joseph Schmidt',
    'address': 'Unit 3511 Box 8162\nDPO AP 60342',
    'text': 'Hour present floor. Effect least time save total administration executive.\nOff risk indeed what. Do economic current pretty throw himself total. Put under collection heart.',
    'email': 'andersonmark@example.com',
    'phone_number': '+1-949-854-8822',
    'json': {
    'name': 'Jennifer Tucker',
    'address': '815 Bradley Island Suite 260\nNew Meganbury, KS 65229',
},
    'key32322': 'value67649',
    'key4517': 'value6289',
    'key21998': 'value32961',
},
    {
    'id': 17527480048644,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Lisa Jenkins',
    'address': '23118 Dalton Isle\nSouth Melissa, MT 73232',
    'text': 'Decide get concern cold world offer product use. Stock fine grow particularly. Gas only receive computer important food community. Age should foreign.',
    'email': 'michaelscott@example.com',
    'phone_number': '516-573-2435',
    'json': {
    'name': 'Richard Smith',
    'address': '1417 Moss Curve\nEast Johnhaven, AR 92218',
},
    'key17387': 'value89528',
    'key41534': 'value22712',
    'key46361': 'value59891',
    'key13669': 'value14457',
    'key8898': 'value86909',
    'key98052': 'value61778',
    'key48320': 'value9852',
},
    {
    'id': 17527480048655,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Thomas Barnes',
    'address': '165 Christina Roads\nLake Donaldfurt, PA 59076',
    'text': 'Catch several effect power enter mother. Still attorney along course. Make respond create page interview example. Score break first seven fine myself.',
    'email': 'johnathan07@example.com',
    'phone_number': '904-968-1571x203',
    'json': {
    'name': 'Tamara Hunt',
    'address': 'PSC 7856, Box 8937\nAPO AA 75315',
},
    'key71854': 'value77171',
    'key96472': 'value15631',
    'key81639': 'value31913',
    'key44405': 'value66319',
    'key48628': 'value31203',
    'key61933': 'value57950',
},
    {
    'id': 17527480048663,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Theresa Martinez',
    'address': '78819 Anthony Meadows Suite 080\nLake Lindastad, IN 60227',
    'text': 'Information bill push kind. Political real herself authority at if explain hand.',
    'email': 'kylieroberts@example.org',
    'phone_number': '309.885.5535',
    'json': {
    'name': 'Aaron Vang',
    'address': '1061 Steven Viaduct\nNew Kimberly, AL 05260',
},
    'key99059': 'value63401',
    'key93881': 'value9524',
    'key1422': 'value86999',
    'key10108': 'value83239',
    'key5409': 'value2081',
},
    {
    'id': 17527480048674,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Isaiah Lopez',
    'address': '86701 Bowman Gardens Apt. 214\nLake Rose, OH 45772',
    'text': 'Team operation stock suffer concern necessary fish where. Current discover bit. Economy right treat treatment take office.',
    'email': 'wrightkenneth@example.org',
    'phone_number': '+1-490-765-6673',
    'json': {
    'name': 'Carl Brown',
    'address': '8722 Joel Roads\nAudreychester, NE 31877',
},
    'key46963': 'value50184',
    'key28197': 'value92033',
    'key66360': 'value33055',
    'key97612': 'value79222',
    'key74492': 'value79899',
    'key53141': 'value54776',
    'key55848': 'value46182',
},
    {
    'id': 17527480048685,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Nancy Evans',
    'address': '348 Fitzgerald Summit Suite 160\nHuntburgh, AL 81515',
    'text': 'Room media hand memory hotel quality what. Thought anyone listen join. Against account shake learn production.\nImprove TV still partner economic production amount. Table people physical worry.',
    'email': 'huangjeffrey@example.com',
    'phone_number': '545-277-4540',
    'json': {
    'name': 'Sean Vazquez',
    'address': '0945 Morales Track\nWest Tinaton, WV 86347',
},
    'key20479': 'value34878',
    'key87139': 'value58158',
    'key85771': 'value80751',
    'key93087': 'value30224',
    'key52229': 'value44438',
    'key40107': 'value32587',
    'key70625': 'value34210',
    'key66737': 'value92587',
    'key70990': 'value56054',
},
    {
    'id': 17527480048697,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Brittany Porter',
    'address': '6074 Figueroa Harbors\nAndrewchester, MN 37776',
    'text': 'Hot thousand environment Democrat impact require. Media newspaper begin vote. Give break development race that material.',
    'email': 'shannonemily@example.com',
    'phone_number': '9529919502',
    'json': {
    'name': 'Jennifer Cox',
    'address': '1383 Peter Ridge\nHuffmanburgh, WV 83004',
},
    'key54876': 'value4105',
    'key38337': 'value45372',
    'key87735': 'value98855',
    'key13484': 'value52',
    'key39261': 'value53949',
    'key21230': 'value89984',
},
    {
    'id': 17527480048709,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Leslie Mcknight',
    'address': '37963 Phillips Radial\nDavidmouth, OH 19185',
    'text': 'Talk summer build hold also laugh on. Save small start bank wind. Concern information line sort travel.\nAllow case may citizen. Increase candidate however population opportunity hold environmental.',
    'email': 'yhernandez@example.org',
    'phone_number': '001-770-673-9479x409',
    'json': {
    'name': 'Lauren Macdonald',
    'address': '30600 Nichols Mission\nPort Julie, SD 01124',
},
    'key17283': 'value71117',
    'key25183': 'value29490',
},
    {
    'id': 17527480048720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Matthew Parsons PhD',
    'address': '3171 Corey Pass Apt. 438\nRobersonside, PR 01136',
    'text': 'Author while involve from instead soldier customer. Whole various few direction look three spring.\nDemocrat fill no character.',
    'email': 'cbrown@example.org',
    'phone_number': '2726279309',
    'json': {
    'name': 'Deborah Stewart',
    'address': '86435 Snyder Crossing Suite 548\nAmandaport, PW 20550',
},
    'key87294': 'value86575',
    'key79139': 'value5602',
},
    {
    'id': 17527480048731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'David Burns',
    'address': '910 Pamela Junction\nSouth Cynthia, ME 82733',
    'text': 'Space hot hotel key. Social baby describe food.\nLocal him continue tough. Beyond in cost outside.\nInteresting add score into reflect condition. Long alone everything someone social.',
    'email': 'david04@example.org',
    'phone_number': '001-915-483-8066',
    'json': {
    'name': 'Carol Swanson',
    'address': '39128 Elizabeth Fort\nKelleyborough, FM 39577',
},
    'key1617': 'value25270',
    'key56309': 'value65864',
},
    {
    'id': 17527480048741,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Kristy Evans',
    'address': '6084 Anderson Drives Apt. 968\nEricfort, WA 06253',
    'text': 'Executive thank fine best. She matter oil bring read listen. Go per time challenge thus big leg. Late else move drop stand scene.',
    'email': 'james00@example.net',
    'phone_number': '+1-361-264-9815x153',
    'json': {
    'name': 'Megan Gutierrez',
    'address': 'Unit 5286 Box 3906\nDPO AP 22312',
},
    'key28086': 'value90253',
    'key71703': 'value7963',
    'key46844': 'value48490',
    'key55713': 'value89095',
},
    {
    'id': 17527480048750,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Elizabeth Andersen',
    'address': '24258 Amanda Center\nSouth Patricialand, CO 03125',
    'text': 'Well miss seat sure up movie stuff information. His professional short blue business summer finish long.',
    'email': 'dpeterson@example.net',
    'phone_number': '(295)736-7440x35091',
    'json': {
    'name': 'Tracy Williams',
    'address': '231 James Avenue Apt. 807\nSmithview, MI 20798',
},
    'key13973': 'value59620',
    'key86189': 'value5126',
    'key15660': 'value79747',
},
    {
    'id': 17527480048760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Joseph Parker',
    'address': '169 Ashley Springs\nNorth Ernest, AZ 21811',
    'text': 'Especially administration lay somebody. Space campaign identify section tonight ground. Middle director specific together.',
    'email': 'scott44@example.com',
    'phone_number': '(732)659-3495',
    'json': {
    'name': 'Richard Holmes',
    'address': '15131 Bullock Common\nPaulatown, MT 94943',
},
    'key76473': 'value83158',
    'key64505': 'value58525',
},
    {
    'id': 17527480048770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Elizabeth Gonzalez',
    'address': '4620 David Drives Suite 234\nEast Elainebury, CT 79625',
    'text': 'Cost available within time. Company once sing girl. Consumer a back as past.\nWho debate easy miss administration live. Make three scene born.',
    'email': 'tylerwatson@example.net',
    'phone_number': '(913)798-9737',
    'json': {
    'name': 'Gregory Peterson',
    'address': '766 Miller Inlet Suite 963\nAliceburgh, ND 51298',
},
    'key74513': 'value42033',
    'key36622': 'value46634',
    'key62982': 'value94624',
    'key3078': 'value98674',
    'key96226': 'value66742',
    'key7841': 'value858',
    'key98884': 'value28508',
},
    {
    'id': 17527480048781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Jessica Williamson',
    'address': '6181 Lindsey Creek Suite 393\nHuffshire, WI 94005',
    'text': 'Probably very specific cultural. Now represent prepare matter remember. So material size follow strategy style.\nDespite what mind know do reach.',
    'email': 'ericgonzalez@example.org',
    'phone_number': '871.489.5367',
    'json': {
    'name': 'Megan Campbell',
    'address': '347 Burns Brooks Suite 608\nLake Kayleemouth, PW 91313',
},
    'key85430': 'value50718',
    'key61349': 'value71404',
    'key42094': 'value44641',
    'key4529': 'value71973',
},
    {
    'id': 17527480048793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Adrian Yoder',
    'address': '40143 Lang Spurs\nNew Amanda, NM 66132',
    'text': 'Far include city beyond establish sport win. Wear fly positive strategy why her.\nDemocrat plant cut my free. Next head computer describe keep.',
    'email': 'udorsey@example.org',
    'phone_number': '001-580-554-5822',
    'json': {
    'name': 'Linda Farmer',
    'address': '28462 Megan Alley Suite 421\nThomasfurt, SD 72220',
},
    'key42442': 'value93104',
    'key23478': 'value38604',
    'key70035': 'value29571',
    'key26824': 'value97924',
    'key42998': 'value45416',
},
    {
    'id': 17527480048806,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Eric Hughes',
    'address': '6806 Manuel Islands Apt. 136\nBobbymouth, NY 08819',
    'text': 'Center rate couple along increase.\nArt upon above certainly drive. Family everyone walk hour month. Air foot prevent.\nWhat less down somebody beyond so stuff. Least follow manager investment table.',
    'email': 'amberlynch@example.org',
    'phone_number': '658.944.2899x306',
    'json': {
    'name': 'Calvin Vaughn',
    'address': '072 Jensen Harbors\nPalmerport, FL 64069',
},
    'key97213': 'value93962',
},
    {
    'id': 17527480048820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Leslie Mendez',
    'address': '382 Day Station Suite 517\nVeronicabury, DC 69181',
    'text': 'Star truth value ask free society can. Majority test order entire.\nCause once plant. Cold despite middle far Republican method by.',
    'email': 'watsonkathleen@example.com',
    'phone_number': '001-700-827-3129x578',
    'json': {
    'name': 'Douglas Lee',
    'address': '52211 Joe Terrace\nVictoriaborough, ND 81705',
},
    'key35852': 'value13327',
    'key68609': 'value77893',
    'key93257': 'value502',
    'key6889': 'value86794',
    'key29618': 'value75952',
    'key475': 'value24220',
    'key81316': 'value62708',
    'key79750': 'value52771',
    'key20649': 'value50813',
    'key23939': 'value6769',
},
    {
    'id': 17527480048835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Philip Mathews',
    'address': '974 Smith Passage\nAdrianton, MD 96425',
    'text': 'Environment today catch house amount station dinner reason. Protect while reality health when north go entire. Nation factor score left yourself.\nPrevent support without program. Time himself card.',
    'email': 'alexis30@example.com',
    'phone_number': '(845)770-1788x8324',
    'json': {
    'name': 'Patricia Beck',
    'address': '5037 Justin Expressway\nChristopherton, ID 17928',
},
    'key32334': 'value64538',
    'key54335': 'value49381',
    'key62267': 'value24536',
    'key56470': 'value25647',
},
    {
    'id': 17527480048848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Casey Gentry',
    'address': '50571 James Walks\nGrayland, TN 36633',
    'text': 'Institution door environment me community no. Join off senior court woman.\nFree like save woman. Everybody operation message.\nWhere allow write game food manage. Rather such thus trial significant.',
    'email': 'porterjody@example.org',
    'phone_number': '263.431.6333',
    'json': {
    'name': 'Mr. Nathaniel Garner',
    'address': '274 Russell Isle Apt. 610\nLake Brandy, MT 18498',
},
    'key97722': 'value86584',
    'key45175': 'value34969',
    'key65583': 'value56093',
    'key96646': 'value57400',
},
    {
    'id': 17527480048862,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Brittany Wilson',
    'address': '1901 Mcdonald Club Suite 066\nWest Angelaville, DE 03847',
    'text': 'Kind name too no station if receive.\nDuring such accept grow. Daughter serious political. Reach sort of set main rule history.',
    'email': 'michellehale@example.net',
    'phone_number': '001-204-379-3969x5900',
    'json': {
    'name': 'Adam Meyers',
    'address': 'PSC 0594, Box 5823\nAPO AA 79778',
},
    'key80171': 'value63319',
    'key8302': 'value54605',
    'key20799': 'value3923',
    'key82252': 'value43918',
},
    {
    'id': 17527480048874,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Matthew Everett',
    'address': '779 Tanner Vista Apt. 647\nNew Brandonmouth, MO 30675',
    'text': 'Charge Congress lay space. Degree moment spend compare off significant. Good from alone enough.\nSister conference again. Study around middle street drive. Read car true evening.',
    'email': 'nancy85@example.com',
    'phone_number': '+1-667-504-7179x3140',
    'json': {
    'name': 'Gregory Brooks',
    'address': '992 George Turnpike Suite 101\nWest Scottchester, SD 59552',
},
    'key87402': 'value14958',
    'key45286': 'value59629',
    'key98798': 'value57476',
    'key58776': 'value47480',
    'key68939': 'value81390',
    'key49933': 'value72046',
    'key57577': 'value92031',
    'key95175': 'value21683',
    'key96980': 'value35533',
},
    {
    'id': 17527480048887,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Sergio Austin',
    'address': '727 Garza Shore Suite 539\nLake Kyleport, GU 43757',
    'text': 'Game carry possible some however sure. Huge ball tree effort some. Both certain water face those now. Suddenly mean kid involve up.',
    'email': 'darlene99@example.com',
    'phone_number': '397-938-1089x07840',
    'json': {
    'name': 'Jessica Anderson',
    'address': '0660 Anita Neck\nKellybury, MN 36005',
},
    'key96119': 'value40692',
},
    {
    'id': 17527480048899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Heather Hernandez',
    'address': 'USS Curtis\nFPO AE 70823',
    'text': 'Radio truth many direction major help central school. Off security from with with.\nInvestment take plant environmental father state stage. Where cover remember. Couple movie certain view two.',
    'email': 'josemccann@example.net',
    'phone_number': '001-560-250-7629x1516',
    'json': {
    'name': 'Jenna Wolfe',
    'address': '736 Saunders Village\nJohnton, FM 92753',
},
    'key44657': 'value91137',
    'key37306': 'value73169',
    'key34424': 'value52848',
    'key86978': 'value2428',
    'key93053': 'value71894',
    'key41719': 'value2867',
    'key24138': 'value68977',
    'key63762': 'value33685',
    'key53495': 'value53006',
    'key74262': 'value64896',
},
    {
    'id': 17527480048910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Matthew Flynn',
    'address': '51042 Joshua Light\nNorth Alejandrostad, WY 52400',
    'text': 'Put standard with kid use toward daughter. Door Congress she share score policy. Defense message number.',
    'email': 'whart@example.com',
    'phone_number': '+1-423-916-0601x9440',
    'json': {
    'name': 'Duane Harding',
    'address': '75921 Caitlin Alley\nCruzville, AR 72143',
},
    'key40635': 'value29586',
},
    {
    'id': 17527480048922,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Veronica Cooper',
    'address': '358 Bowen Neck Apt. 006\nByrdmouth, MN 02841',
    'text': 'Institution institution degree should protect spend. Laugh benefit popular mouth. Magazine create head radio event thought.',
    'email': 'brenda04@example.com',
    'phone_number': '(645)961-2551x6475',
    'json': {
    'name': 'Robert Hill',
    'address': '1053 Smith Glens\nEast Jasonfort, VI 78496',
},
    'key55259': 'value45440',
    'key82972': 'value91148',
    'key94835': 'value48656',
    'key26768': 'value93009',
    'key69868': 'value94684',
    'key10560': 'value85037',
    'key45546': 'value66201',
    'key31018': 'value86056',
    'key63534': 'value28927',
    'key12932': 'value64685',
},
    {
    'id': 17527480048934,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Casey Turner',
    'address': 'USCGC Ferguson\nFPO AP 41381',
    'text': 'Contain enter ask friend business. Responsibility risk go thing yourself politics.',
    'email': 'john74@example.net',
    'phone_number': '001-765-487-3129x20454',
    'json': {
    'name': 'Valerie Hayes',
    'address': '526 Steve Club\nSouth Juanfurt, AZ 25932',
},
    'key68648': 'value75622',
    'key3697': 'value42530',
    'key58378': 'value14274',
    'key25686': 'value43295',
    'key8367': 'value32211',
    'key82416': 'value2608',
    'key95550': 'value90958',
    'key6566': 'value58956',
    'key13830': 'value88220',
},
    {
    'id': 17527480048944,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Patrick Paul',
    'address': '4029 Valerie Ridge Suite 929\nOwensville, CO 27364',
    'text': 'Ground usually city various technology list medical parent. Discussion century discuss agreement yard. Already work process method morning population whatever.',
    'email': 'troy39@example.org',
    'phone_number': '+1-451-929-0568x5714',
    'json': {
    'name': 'Michael Martin',
    'address': '1734 Maria Forges\nAmandafurt, MH 91679',
},
    'key99885': 'value92651',
    'key2597': 'value61686',
    'key11068': 'value2722',
    'key60830': 'value99717',
    'key29494': 'value32018',
    'key79516': 'value6852',
    'key41035': 'value85061',
    'key27304': 'value84526',
},
    {
    'id': 17527480048955,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Ryan Davis',
    'address': '45063 Lucas Flat\nNorth Candicemouth, NY 49488',
    'text': 'Finish your heavy large. Town coach garden type lay have imagine question. Sell fill say interesting sort south.',
    'email': 'tina93@example.net',
    'phone_number': '+1-282-809-7346x42842',
    'json': {
    'name': 'Amy Molina',
    'address': '52300 Vincent Hill\nNorth Francesville, CT 01237',
},
    'key44143': 'value74218',
},
    {
    'id': 17527480048966,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Patricia Miller',
    'address': '211 Nicole Corners\nNew Lisamouth, TN 27794',
    'text': 'Difference worry exist happen prove improve. Method they view both quite oil. Day piece century knowledge.\nNetwork own direction head forget professor author.',
    'email': 'cameronshannon@example.net',
    'phone_number': '001-966-726-9336',
    'json': {
    'name': 'Diane Mcdaniel',
    'address': '3790 Evans Brook\nJohnbury, DC 39731',
},
    'key25127': 'value35958',
},
    {
    'id': 17527480048977,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jeremy Thomas',
    'address': '606 Brown Crest\nMeganstad, SC 65981',
    'text': 'Order difficult possible middle play environmental. Too government herself. During return operation stop relate but.',
    'email': 'jasmine71@example.org',
    'phone_number': '343.283.2626x44702',
    'json': {
    'name': 'Ray Williams',
    'address': '70449 Jeffrey Orchard\nSouth Thomasfort, MO 99013',
},
    'key13191': 'value74951',
    'key15241': 'value56639',
},
    {
    'id': 17527480048988,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Lori Castro',
    'address': '20009 Reginald Shore Apt. 910\nPort Kimberlyton, OR 26522',
    'text': 'Table eat administration than enter. Top certain resource example become. Rich source he avoid later sign.\nResource share story now audience share his. Week build probably mind.',
    'email': 'harveysteven@example.org',
    'phone_number': '256.494.4598x28947',
    'json': {
    'name': 'Amy Miller',
    'address': '608 Tara Radial\nPort Sandraburgh, MO 82673',
},
    'key22744': 'value39145',
    'key71355': 'value83810',
    'key9183': 'value89758',
    'key23206': 'value70321',
    'key44434': 'value11323',
    'key64639': 'value63126',
    'key74205': 'value39745',
    'key36968': 'value18053',
    'key40384': 'value78230',
    'key8997': 'value98652',
},
    {
    'id': 17527480049000,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Brent Booker',
    'address': '3272 Kenneth Cape\nLake Kyleshire, NY 34198',
    'text': 'Bank later read join dark finally foot. Consider be simply choice sing. Thought street window join weight police take bank.',
    'email': 'njames@example.net',
    'phone_number': '001-925-431-3403x850',
    'json': {
    'name': 'Zachary Chen',
    'address': '5242 Dawn Crossroad Apt. 284\nGregoryview, DC 58824',
},
    'key99120': 'value42405',
    'key56341': 'value14703',
    'key94033': 'value43113',
    'key53456': 'value65887',
},
    {
    'id': 17527480049011,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Susan Davis',
    'address': '438 Johnson Creek\nLake Shelly, ID 24528',
    'text': 'Pull understand process home take. See speak technology reveal news. Stay method century catch guy.\nPeople exactly attention any deal. Including receive career surface.',
    'email': 'uoconnor@example.com',
    'phone_number': '(229)251-6030x893',
    'json': {
    'name': 'Brett Burke',
    'address': '6927 Richards Valleys\nEast Carol, GU 96004',
},
    'key64881': 'value78194',
    'key23150': 'value29923',
    'key8208': 'value16027',
    'key37470': 'value72648',
    'key65933': 'value36876',
    'key4192': 'value96914',
},
    {
    'id': 17527480049022,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Theresa Barker',
    'address': '381 Jessica Plain Apt. 303\nKevinmouth, WV 60461',
    'text': 'Attorney choose thus film process enter. Level radio hope meeting.\nWe increase drop good family already itself material. Wide check who plant tell.',
    'email': 'pam45@example.com',
    'phone_number': '459.751.1289',
    'json': {
    'name': 'Michael Phillips',
    'address': '4097 James Place\nDavidside, SC 13446',
},
    'key60176': 'value46904',
    'key80818': 'value62427',
    'key52978': 'value71402',
    'key96008': 'value86182',
    'key1297': 'value98705',
    'key24722': 'value7020',
    'key829': 'value26301',
    'key16697': 'value24255',
    'key17400': 'value12652',
},
    {
    'id': 17527480049032,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Debra Miller',
    'address': '566 Mitchell Fork\nAguirrebury, WA 61954',
    'text': 'Life bed late. General design let hour indicate.\nEdge national as head. Among bring against only. Maybe our condition anything wait.\nGirl it seat laugh human. Serious building official lawyer.',
    'email': 'lnorris@example.com',
    'phone_number': '+1-974-841-8813x9580',
    'json': {
    'name': 'Matthew Schmidt',
    'address': '995 Michael Islands Apt. 272\nOlsenmouth, AS 62505',
},
    'key73543': 'value69140',
    'key75116': 'value96748',
    'key5311': 'value26723',
    'key61920': 'value94203',
    'key85162': 'value62243',
},
    {
    'id': 17527480049044,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Tammy Matthews',
    'address': '350 Hanson Spurs Apt. 640\nJordanfort, CO 99478',
    'text': 'Audience east town response where prove again. Plant recognize get relate find work pass south. Cover effort factor maintain represent white about.',
    'email': 'brianturner@example.org',
    'phone_number': '742.677.8516',
    'json': {
    'name': 'Charles Bryan',
    'address': '6448 Grant Motorway\nSherylstad, TX 92804',
},
    'key86938': 'value83337',
    'key90774': 'value25626',
    'key65335': 'value44764',
},
    {
    'id': 17527480049056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jasmine Perkins',
    'address': '65696 Mckay Plains\nPort Jeffrey, MS 83487',
    'text': 'Month area thousand toward. Present career collection up article into affect.',
    'email': 'srivas@example.net',
    'phone_number': '452-390-9943x55697',
    'json': {
    'name': 'Laurie Jennings',
    'address': 'PSC 3423, Box 0848\nAPO AE 37471',
},
    'key54624': 'value43089',
    'key29632': 'value79019',
    'key80266': 'value47649',
    'key53953': 'value41022',
    'key81222': 'value93059',
    'key92903': 'value79758',
    'key85144': 'value55074',
    'key49258': 'value68972',
    'key28366': 'value38482',
},
    {
    'id': 17527480049065,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Calvin Lee',
    'address': '93111 Campos Highway Suite 003\nKristenberg, MA 97725',
    'text': 'Result president create throw better surface not whom. Development lose son show. Test husband nature her audience deal.',
    'email': 'david41@example.org',
    'phone_number': '339-494-9333x2387',
    'json': {
    'name': 'Robin Maxwell',
    'address': '7837 David Square\nLaurabury, IN 74004',
},
    'key1500': 'value83001',
    'key19024': 'value95482',
},
    {
    'id': 17527480049074,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Shelley Thompson',
    'address': '490 Cody Ramp\nWest Judybury, MS 39841',
    'text': 'Head heart camera. Dog evidence least authority whom night sit. They open different send many. Wait everybody half we age you firm.',
    'email': 'brandon11@example.org',
    'phone_number': '(284)857-4482x43466',
    'json': {
    'name': 'Stephanie Burton',
    'address': '759 Laura Club\nSouth Jill, MD 23876',
},
    'key98168': 'value35547',
    'key49451': 'value98195',
    'key55523': 'value84788',
    'key19258': 'value35548',
    'key78046': 'value72634',
},
    {
    'id': 17527480049084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Michael Kennedy',
    'address': '536 Wood Walks Suite 117\nPort Robin, MS 64841',
    'text': 'Sound again sing adult recognize part. Wife choose performance. Indeed center he already professional anyone meet arm. Response near compare save.',
    'email': 'ashleyjohnson@example.net',
    'phone_number': '001-406-401-9296x5401',
    'json': {
    'name': 'Erin Smith',
    'address': '41675 Miller Canyon Suite 182\nNorth Heatherport, MN 81113',
},
    'key52585': 'value53546',
    'key88224': 'value65789',
    'key24802': 'value33969',
    'key29563': 'value9119',
    'key45165': 'value90299',
    'key60064': 'value79488',
    'key55342': 'value76548',
    'key81453': 'value10921',
},
    {
    'id': 17527480049096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Cynthia Roth',
    'address': '59387 Hannah Pass\nNelsontown, WI 33594',
    'text': 'Heavy most shoulder. Building hand receive. Oil whom artist three.\nState picture coach. Situation conference none stay Democrat leave. Especially type rich.',
    'email': 'hoaaron@example.org',
    'phone_number': '+1-599-865-7153x36855',
    'json': {
    'name': 'Lance Davis',
    'address': '57735 Parsons Forges\nNew Howard, PW 91607',
},
    'key74472': 'value30521',
    'key44283': 'value24846',
    'key52967': 'value22441',
    'key60302': 'value94395',
    'key10211': 'value93984',
    'key57550': 'value78083',
    'key79748': 'value56901',
    'key3164': 'value51996',
    'key51187': 'value6309',
    'key52890': 'value44566',
},
    {
    'id': 17527480049107,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Leslie Lopez',
    'address': '560 Lewis Manors\nWest Pamelamouth, MO 54330',
    'text': 'Recent million big great claim president budget. Couple admit structure point experience perform.\nDegree former blood officer consider may debate. No kind produce respond.',
    'email': 'douglasrobbins@example.net',
    'phone_number': '868-565-4748x533',
    'json': {
    'name': 'Howard Gray',
    'address': '07564 Jacob Overpass\nNew Ryanstad, FL 95091',
},
    'key68676': 'value54145',
    'key77373': 'value54629',
    'key73201': 'value7160',
    'key56426': 'value75576',
    'key47489': 'value14593',
},
    {
    'id': 17527480049119,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Matthew Hooper',
    'address': '77957 Vickie Station Suite 047\nPort Jennifer, MS 95982',
    'text': 'Structure read instead part traditional during.\nIssue market thus standard in range. North occur every benefit community. Model offer town person allow whom eat.',
    'email': 'tranryan@example.org',
    'phone_number': '342.976.3172x2753',
    'json': {
    'name': 'Caitlin Meza',
    'address': '71217 Blanchard Ridges Apt. 460\nMeyerfurt, MT 94435',
},
    'key91100': 'value1332',
    'key70631': 'value46021',
    'key85019': 'value15217',
    'key17506': 'value34121',
    'key3380': 'value94885',
    'key90861': 'value4683',
    'key71588': 'value54951',
    'key21312': 'value23803',
},
    {
    'id': 17527480049132,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Christopher Smith',
    'address': '262 Reynolds Estate Suite 945\nWest Allison, DC 25970',
    'text': 'Receive personal in scene.\nTen source red water hit statement collection store. Economy Congress player beautiful occur stay.',
    'email': 'simslindsey@example.com',
    'phone_number': '+1-323-430-1323x771',
    'json': {
    'name': 'Peggy Rivera',
    'address': '2056 Stephanie Park\nThompsonhaven, KS 68498',
},
    'key27386': 'value16282',
    'key90274': 'value56803',
    'key15873': 'value78190',
    'key9351': 'value7234',
    'key95010': 'value61775',
},
    {
    'id': 17527480049144,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'David Robinson',
    'address': 'USNS Ortiz\nFPO AE 34156',
    'text': 'Task bank cut person sport north. Office community audience. Plant may church must.\nWrong much close election.\nUpon quite wide reality. Now summer ask front kid air hour phone.',
    'email': 'hornecraig@example.net',
    'phone_number': '(800)888-8652x370',
    'json': {
    'name': 'Michael Cordova',
    'address': '847 Curtis Station Suite 828\nJamesbury, FM 60594',
},
    'key80371': 'value72226',
},
    {
    'id': 17527480049154,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Joshua Wilkins DVM',
    'address': '0221 Leon Tunnel\nFosterfort, IN 51381',
    'text': 'Development power able capital million job say of. Radio mention current most someone watch hot. Skin during standard wrong source full at.',
    'email': 'trevorvasquez@example.com',
    'phone_number': '(625)898-9507',
    'json': {
    'name': 'James Whitney',
    'address': '63711 Angela Plain Suite 229\nWest Jamesland, AZ 47131',
},
    'key29649': 'value76553',
    'key76149': 'value2525',
    'key96465': 'value52881',
    'key34364': 'value89461',
},
    {
    'id': 17527480049166,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Sandra Swanson',
    'address': '9864 Christopher Avenue Suite 127\nChenland, DC 01667',
    'text': 'Bank particularly trip religious. Himself month language attorney guy. Kitchen teacher indeed attorney go.',
    'email': 'carlameyer@example.org',
    'phone_number': '001-292-732-5244x47355',
    'json': {
    'name': 'Nicholas Hanson',
    'address': '23968 Gonzalez Rue\nNew Chad, ME 98354',
},
    'key72617': 'value44960',
    'key98721': 'value32318',
},
    {
    'id': 17527480049178,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Dean Huff',
    'address': '085 Hamilton Hollow\nWest Donna, TX 04711',
    'text': 'Should try marriage task pass. Our purpose future benefit short total make quickly. Enough great short surface time investment.',
    'email': 'parkercharles@example.org',
    'phone_number': '001-345-308-1267x63961',
    'json': {
    'name': 'Brandon White',
    'address': '99054 Velasquez Mall Apt. 764\nSmithview, WI 99613',
},
    'key89553': 'value75784',
    'key55680': 'value94813',
    'key69676': 'value81225',
},
    {
    'id': 17527480049189,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Lori Hooper',
    'address': '5483 Rodriguez Estates Apt. 056\nWest Jillside, IL 53591',
    'text': 'Without character result certain artist recognize marriage. Court couple social benefit. Participant young finish herself.\nKitchen sound charge them.',
    'email': 'isaiahhanson@example.net',
    'phone_number': '(770)576-9037x1990',
    'json': {
    'name': 'Nicholas Lewis',
    'address': '1857 Brandon Way Suite 165\nYoungside, OH 26362',
},
    'key20170': 'value84596',
    'key88772': 'value73587',
    'key60364': 'value44627',
    'key33299': 'value31397',
    'key25500': 'value87025',
    'key82517': 'value63056',
    'key47725': 'value85454',
    'key2212': 'value30111',
    'key90399': 'value94981',
    'key12983': 'value70195',
},
    {
    'id': 17527480049201,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Jose Gibson',
    'address': 'Unit 2640 Box 6648\nDPO AP 75713',
    'text': 'Bit pressure executive check person. If back identify no. Recent sense expert certain series actually anyone.\nAdd mind manager traditional look factor peace. Material participant fact.',
    'email': 'sandraduran@example.net',
    'phone_number': '690-362-4610',
    'json': {
    'name': 'Joanna Bullock',
    'address': '546 Bruce Centers Apt. 075\nKennethfurt, AZ 96808',
},
    'key85399': 'value82788',
},
    {
    'id': 17527480049211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Sara Williams',
    'address': '63065 Edward Junction Apt. 876\nNew Melissa, ID 62378',
    'text': 'Month lead audience easy. Travel carry tough dog eight remember thus. Would word quality.',
    'email': 'rachelcoleman@example.com',
    'phone_number': '217.296.4245',
    'json': {
    'name': 'David Abbott',
    'address': 'USNV Burns\nFPO AE 34453',
},
    'key24124': 'value86957',
    'key71309': 'value42074',
    'key15334': 'value53759',
    'key29241': 'value52117',
    'key94834': 'value61495',
    'key45618': 'value12477',
    'key40946': 'value55150',
    'key89725': 'value67884',
    'key94269': 'value41894',
    'key31251': 'value8172',
},
    {
    'id': 17527480049221,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Daniel Jones',
    'address': '65478 Ibarra Stream Apt. 290\nNew Jordanstad, SD 21019',
    'text': 'Him store feel financial. Least plant above budget message point none.\nPaper cold fight. Economic between process. Go rise treatment arrive.',
    'email': 'shawn83@example.com',
    'phone_number': '001-575-618-4828x18569',
    'json': {
    'name': 'Anthony Cain',
    'address': '88686 Taylor Dam\nWoodsmouth, SC 65213',
},
    'key43972': 'value4089',
    'key41605': 'value74305',
    'key1673': 'value55297',
    'key19508': 'value52828',
    'key20291': 'value14755',
},
    {
    'id': 17527480049232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Brittney Williams',
    'address': '16239 Joshua Landing Suite 559\nJacksonview, SD 06422',
    'text': 'Hit loss education save. Western network plant window pay develop strategy throughout.\nSocial also citizen. Data look assume rest test true eye seat. Present friend next media law scientist.',
    'email': 'diazlaura@example.org',
    'phone_number': '8953055994',
    'json': {
    'name': 'George King',
    'address': 'USCGC Diaz\nFPO AA 96443',
},
    'key84484': 'value66018',
    'key69705': 'value1931',
    'key42360': 'value44055',
    'key90061': 'value30980',
    'key23226': 'value49545',
    'key55016': 'value97895',
    'key39364': 'value96808',
    'key39585': 'value12596',
    'key58320': 'value16874',
    'key10952': 'value22069',
},
    {
    'id': 17527480049243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Amanda Dickerson',
    'address': '937 Petty Trace\nSouth Craig, WY 28530',
    'text': 'Beautiful trouble language certain detail everything.\nWorld rate call pretty do buy mention. But road drug rise TV others. Subject tell since day.',
    'email': 'emendoza@example.org',
    'phone_number': '702-594-4956x053',
    'json': {
    'name': 'Marie Durham',
    'address': '455 Bryant Tunnel Suite 142\nJeffreyland, OH 92886',
},
    'key94245': 'value27583',
    'key40113': 'value53556',
    'key3176': 'value19495',
    'key88550': 'value11548',
    'key97038': 'value41130',
    'key62580': 'value39479',
    'key99608': 'value44422',
    'key28': 'value24211',
    'key88188': 'value38451',
},
    {
    'id': 17527480049254,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Joel Smith',
    'address': '858 Johnson Path\nNew Colleenland, MS 14342',
    'text': 'Home study per high future change environmental. Forget whole population matter recognize the green.',
    'email': 'anthonystephen@example.com',
    'phone_number': '971.611.0838x95317',
    'json': {
    'name': 'Amy Hickman',
    'address': 'PSC 9013, Box 5005\nAPO AA 83034',
},
    'key23555': 'value63033',
    'key32906': 'value27207',
    'key81583': 'value63038',
    'key92080': 'value45489',
    'key35830': 'value94471',
    'key32124': 'value60031',
    'key54403': 'value69641',
    'key53414': 'value31198',
    'key78127': 'value43234',
    'key23097': 'value91717',
},
    {
    'id': 17527480049264,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kevin Wright',
    'address': '621 Smith Road Suite 027\nMichelleton, VI 08275',
    'text': 'Reduce continue here which force sure bank. Check forget bill help close grow billion. Recent factor front participant art value.',
    'email': 'vasquezandrea@example.com',
    'phone_number': '(467)693-8585x9872',
    'json': {
    'name': 'Catherine Johnston',
    'address': '741 Robertson Springs\nBoydfort, AK 85736',
},
    'key78039': 'value98488',
    'key69912': 'value51176',
    'key85854': 'value22105',
    'key21752': 'value28483',
},
    {
    'id': 17527480049277,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Billy Robertson',
    'address': '604 Mitchell Prairie\nBonnieberg, IA 19673',
    'text': 'Between throw cold which miss. Fly career leg number.\nArgue whether understand another science single discuss. The such include conference.',
    'email': 'kenneth48@example.net',
    'phone_number': '514-264-7704x84876',
    'json': {
    'name': 'Nichole Thompson',
    'address': '61344 Bennett Burgs Suite 790\nCarloschester, IN 88204',
},
    'key17123': 'value27744',
    'key22550': 'value99612',
    'key74474': 'value78777',
    'key92209': 'value50329',
    'key28324': 'value57952',
    'key73935': 'value42016',
},
    {
    'id': 17527480049288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Heather Walker',
    'address': 'PSC 5099, Box 8604\nAPO AE 89185',
    'text': 'Industry tonight staff. Phone he certain church most describe.\nSend recent executive space. Difference door relate when share. Activity trade those out.',
    'email': 'jorgecastillo@example.org',
    'phone_number': '(513)704-7406',
    'json': {
    'name': 'Felicia Ho',
    'address': 'Unit 2267 Box 2692\nDPO AE 62200',
},
    'key34153': 'value43488',
    'key36139': 'value10772',
    'key67329': 'value17977',
    'key98398': 'value36269',
    'key95545': 'value75465',
},
    {
    'id': 17527480049297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Kathryn Farley',
    'address': '947 Christina Center Suite 893\nLake Stevenbury, KY 66700',
    'text': 'Able when look anyone discover other. Mind close however ability return big.\nSave car board recent. Station site measure force. Admit research admit form relate writer.',
    'email': 'andrea33@example.com',
    'phone_number': '405-290-0193',
    'json': {
    'name': 'Joel Rasmussen',
    'address': '741 Jeffrey Court Suite 867\nMaryfurt, TN 95469',
},
    'key66341': 'value71280',
    'key3332': 'value90352',
    'key64006': 'value2726',
    'key30504': 'value59561',
    'key99457': 'value90264',
    'key80656': 'value45827',
    'key46887': 'value33107',
},
    {
    'id': 17527480049307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Corey Scott',
    'address': '401 Rogers Dam\nNew Andrew, MO 72489',
    'text': 'Charge process probably describe foreign upon. Only hundred difference hand loss century. Cause image couple church seat threat particularly. Build training of structure analysis ago drive.',
    'email': 'michelle38@example.org',
    'phone_number': '(380)438-3389',
    'json': {
    'name': 'Joseph Lawrence',
    'address': '206 Elizabeth Highway Apt. 686\nMichelleshire, VA 89363',
},
    'key12580': 'value21283',
    'key77675': 'value56998',
    'key62281': 'value10199',
    'key10892': 'value4945',
    'key90652': 'value64416',
    'key60381': 'value55446',
    'key77052': 'value60947',
    'key69876': 'value3574',
    'key7083': 'value69456',
},
    {
    'id': 17527480049318,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Samantha Mcclure',
    'address': '738 Joshua Square Suite 036\nChristinaport, PA 26832',
    'text': 'Level research career physical big adult.\nCall return pressure appear agency. Modern several state drop. Perform establish police father.\nThrough seem if long. Face do main.',
    'email': 'william29@example.com',
    'phone_number': '403.407.6506',
    'json': {
    'name': 'Marcus Vance',
    'address': '5722 Anna Stravenue Apt. 829\nChristopherfurt, UT 99264',
},
    'key10034': 'value27576',
    'key31719': 'value46219',
},
    {
    'id': 17527480049329,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Kevin Moore',
    'address': '86166 Trujillo Cliff Apt. 958\nHurleyside, CA 06014',
    'text': 'Finally catch father myself. Poor rich me speak similar.\nTry provide science scene while lead first. Will cause mouth.',
    'email': 'ramossamantha@example.net',
    'phone_number': '001-775-501-2056x9948',
    'json': {
    'name': 'Charles Bartlett',
    'address': '9031 Barrett Point Suite 456\nSouth Johnfort, IL 22196',
},
    'key29427': 'value34786',
    'key59222': 'value84178',
    'key79177': 'value19478',
    'key6251': 'value98409',
    'key9847': 'value76908',
    'key94917': 'value25323',
    'key25529': 'value54763',
    'key56950': 'value64689',
    'key48725': 'value63734',
    'key93282': 'value11302',
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



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_38_769242sAuSmufu',
    'data': self.mutator.generate_float_array(dimension=128, normalized=True),
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = 'null'
        
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



    def test_request_5(self):
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_38_769242sAuSmufu',
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_38_769242sAuSmufu',
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



    def test_request_7(self):
        """测试请求 7 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '85fa07d0-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_38_769242sAuSmufu',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[L2]_1752748008.json')
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
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithSimplePayloadL21752748008Json()
    test.run_tests()
