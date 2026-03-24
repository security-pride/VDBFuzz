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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752744954_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752744954.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrue1020Uid20301752744954Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752744954.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752744954.json"
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
    'RequestId': '67e82a59-62f1-11f0-a3ec-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_40_839314FrFbeQbf',
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
    'RequestId': '6b0511a2-62f1-11f0-82c6-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_40_839314FrFbeQbf',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Erin Huber',
    'address': '0121 Jessica Trail Suite 379\nGallaghertown, AS 29490',
    'text': 'Six full organization heart without place for. Color sit design owner.\nInteresting once usually employee allow leader. Into question loss agency say.',
    'email': 'sarahwilliams@example.org',
    'phone_number': '(924)352-9105x35057',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Arthur Horton',
],
    'json': {
    'name': 'Valerie Flores',
    'address': '5875 Kathleen Shoals\nFosterland, ID 06347',
},
    'key22962': 'value90892',
    'key38273': 'value96755',
    'key74774': 'value59480',
    'key77242': 'value7099',
    'key78632': 'value20327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Wayne Wagner',
    'address': '49114 Smith Rue Suite 985\nAndreahaven, SD 31822',
    'text': 'Meet learn road per move through. Catch appear white will claim resource million.\nProperty follow resource down bank. Left single woman international method ahead. Heavy where become to.',
    'email': 'torresrachel@example.net',
    'phone_number': '+1-245-255-5960x459',
    'array_int_dynamic': [
    92465,
],
    'array_varchar_dynamic': [
    'Christian Frank',
    'Christopher Randall',
    'Lori Avery',
    'Lee Bates',
    'Shannon Jackson',
    'Linda Reed',
    'Morgan Castro',
    'Thomas Garza',
],
    'json': {
    'name': 'Allen Hogan',
    'address': '7623 Robert Vista\nReneeborough, FL 92162',
},
    'key66868': 'value12304',
    'key69478': 'value5793',
    'key20805': 'value94143',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jordan Clark',
    'address': '2922 Ruiz Hill\nNew Michael, MN 22997',
    'text': 'Attorney fast section say be kid especially. Use easy knowledge appear fear.\nFinish name chance.',
    'email': 'ryan12@example.com',
    'phone_number': '(616)622-3835x58584',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Silva',
    'Mia Harrison',
    'Katrina Lee',
    'Diana Massey',
    'Lisa Herrera',
    'Antonio Greene',
],
    'json': {
    'name': 'Amanda Miller',
    'address': '99247 Brown Villages\nNavarroborough, IA 40806',
},
    'key96322': 'value43292',
    'key36257': 'value4018',
    'key46643': 'value99161',
    'key70247': 'value80657',
    'key30555': 'value76898',
    'key84924': 'value41628',
    'key82612': 'value40273',
    'key33369': 'value67858',
    'key59918': 'value42966',
    'key26418': 'value33088',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Ryan Li',
    'address': '62438 Lindsey Ports Suite 207\nEast Tanyaview, WV 48353',
    'text': 'Know behavior fall pick big. Go appear under south professional.\nSign keep stuff wonder each. Provide meeting nothing visit material hit tree. Sport religious current food detail.',
    'email': 'chrisbrown@example.net',
    'phone_number': '7866150195',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Johnson',
    'Edward Pierce',
],
    'json': {
    'name': 'Eric Pham',
    'address': '393 Mark Ports Apt. 455\nThomaston, SD 51024',
},
    'key42089': 'value69697',
    'key99728': 'value442',
    'key65950': 'value72539',
    'key91388': 'value24703',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Michael Allen',
    'address': '22018 Lori Path Suite 353\nAtkinsonmouth, FL 59965',
    'text': 'Someone real main increase majority power information. Course thus direction offer not all.\nNote her alone. Sound describe pretty smile consumer crime bar. Alone drug game across free.',
    'email': 'collinsthomas@example.net',
    'phone_number': '+1-838-531-6117x230',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Anderson',
    'Stephen Stephens',
    'Christina Hughes',
    'Craig Porter',
    'Nicholas Haynes',
    'Shannon Mitchell',
    'Terry Lynch',
    'Anthony Buck',
    'Lauren Brown',
    'Martin Washington',
],
    'json': {
    'name': 'Charles Shaw',
    'address': '35594 Tyler Roads\nNew Christophershire, LA 08690',
},
    'key76347': 'value94926',
    'key4031': 'value22150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Joseph Green',
    'address': '5302 Danielle Ferry\nAllenfort, VT 08212',
    'text': 'Choose all beyond maybe. Air call blood five while travel amount.\nShow start tell agent gun size. Animal yard knowledge finish thing lay young.',
    'email': 'xwilson@example.com',
    'phone_number': '313-530-4026x02950',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kara Richardson',
    'Michael Evans',
    'Heather Hudson',
    'Jacob Nelson',
    'David Rocha',
    'Jaime Dennis',
],
    'json': {
    'name': 'Virginia Gonzales',
    'address': '659 Myers Summit\nAndrewmouth, AL 11236',
},
    'key78024': 'value33242',
    'key92013': 'value96510',
    'key54870': 'value55973',
    'key34090': 'value11314',
    'key95594': 'value85705',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Richard Brown',
    'address': '157 Powell Harbors Apt. 073\nCarterfort, AR 95555',
    'text': 'If force conference certainly edge join red explain. Cold southern together reveal writer. Would behind possible remember thank.',
    'email': 'bbolton@example.net',
    'phone_number': '352.622.6422x157',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amy Johnson',
    'Samantha Gentry',
    'Christine Perry',
    'Amy Wheeler',
],
    'json': {
    'name': 'Misty Meyer',
    'address': '542 Finley Shores Suite 154\nChambersburgh, VT 02128',
},
    'key20530': 'value58853',
    'key23675': 'value64992',
    'key79305': 'value79088',
    'key2861': 'value58933',
    'key5804': 'value98197',
    'key99757': 'value54704',
    'key56261': 'value97596',
    'key27496': 'value51843',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Susan James',
    'address': 'USS Buckley\nFPO AE 83972',
    'text': 'Which available technology or listen dinner half. Enjoy including car election. Cause top act line line.',
    'email': 'medinadonna@example.org',
    'phone_number': '6233437344',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Anna Bell',
],
    'json': {
    'name': 'Brian Lawrence',
    'address': '7560 Dixon Valleys Apt. 506\nEast Michael, MN 44558',
},
    'key80798': 'value50098',
    'key38617': 'value3234',
    'key54488': 'value31749',
    'key10237': 'value93371',
    'key91465': 'value49265',
    'key69581': 'value49976',
    'key78882': 'value99873',
    'key12692': 'value91760',
    'key12513': 'value81559',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Brad Wiley',
    'address': '03882 Matthew Rue\nEast Charlenefort, MP 68100',
    'text': 'Analysis sense actually. Kitchen decide beautiful military attention. Stay south current personal PM loss.\nControl old present apply improve total.',
    'email': 'imatthews@example.org',
    'phone_number': '001-755-736-7018x196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Greg Ryan',
    'Keith Stark DVM',
    'Jessica Frazier',
],
    'json': {
    'name': 'Kimberly Bowman',
    'address': '846 Garcia Course\nPhillipstown, GU 73088',
},
    'key46764': 'value13441',
    'key53453': 'value62462',
    'key57367': 'value84927',
    'key12888': 'value35616',
    'key56180': 'value98038',
    'key14349': 'value25389',
    'key84167': 'value96944',
    'key86996': 'value86488',
    'key15281': 'value69386',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Victoria Cobb',
    'address': '41015 Lee Parkway\nNorth Donaldchester, MH 87289',
    'text': 'Price serve deal. The allow speak effort. Allow free year TV.\nFigure past movie federal on smile movement. Cut land enough produce pressure.',
    'email': 'jamieanderson@example.com',
    'phone_number': '281.922.0170x464',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Pierce',
    'Carolyn Garcia',
    'David Francis',
    'Shane Gonzalez',
    'Tara Graham',
    'Charlene Rhodes',
],
    'json': {
    'name': 'Megan Barnett',
    'address': '6511 Ashley Rest\nNelsonshire, WI 16991',
},
    'key75956': 'value97935',
    'key14714': 'value13177',
    'key86498': 'value71755',
    'key91097': 'value79019',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Ann Jones',
    'address': '7489 Evans Shoal\nHernandezfort, KS 03297',
    'text': 'Operation few show let performance risk. Laugh show minute chair loss. Training product short line kind would.\nSouthern produce western health. Scene bed beautiful.',
    'email': 'powellcrystal@example.net',
    'phone_number': '746.289.1784x5007',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Willie Hawkins',
    'Matthew Woodard',
    'Brittany Schmidt',
    'Todd Brooks',
    'Michelle Butler',
    'John Stewart',
    'Cassandra Powell',
],
    'json': {
    'name': 'Andrew Jones',
    'address': '8139 Schmidt Dam Suite 726\nPort Joshuamouth, DE 07639',
},
    'key83687': 'value99067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Patricia Glenn',
    'address': '45489 Dustin Ramp Suite 393\nNorth Cameronchester, MH 20154',
    'text': 'Space trouble play. Kid exist significant technology. Generation why science suggest. Final good contain already everything.',
    'email': 'mtaylor@example.org',
    'phone_number': '851.629.0227x409',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Brown',
    'Michael Castillo',
    'Ebony Juarez',
    'Frank Hall MD',
    'Summer Hamilton',
],
    'json': {
    'name': 'Daniel Brown',
    'address': '024 Daniel Burg\nEast Sarah, IN 51673',
},
    'key74665': 'value20581',
    'key30922': 'value63059',
    'key39154': 'value29723',
    'key82680': 'value91616',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Elizabeth Richardson',
    'address': '34857 Kemp Port\nWalkermouth, GU 45327',
    'text': 'Cultural turn hold American population fire. Wind prevent talk require woman camera day.\nToward research lawyer. Dinner likely or goal performance.',
    'email': 'fordedward@example.net',
    'phone_number': '606-619-3763',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Stokes',
    'Kelly Kent',
    'Taylor Ware',
    'Logan Mendoza',
    'Ryan Garcia',
    'Joseph Hammond',
    'Ashley Miller',
    'Bradley Rogers',
    'David Bowers',
],
    'json': {
    'name': 'William Ross',
    'address': '3411 Lewis Drive Apt. 676\nNew Beth, NY 34730',
},
    'key90183': 'value4779',
    'key19905': 'value63505',
    'key98586': 'value80261',
    'key28669': 'value65872',
    'key18157': 'value31132',
    'key9250': 'value63339',
    'key82751': 'value20459',
    'key88206': 'value49753',
    'key76265': 'value23739',
    'key24978': 'value93507',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Daniel Santos',
    'address': 'Unit 5188 Box 5502\nDPO AP 59458',
    'text': 'Clearly remember field create director score alone. Yeah little responsibility pretty yeah Republican heavy choice.',
    'email': 'thomas94@example.com',
    'phone_number': '001-425-783-3231x149',
    'array_int_dynamic': [
    22188,
],
    'array_varchar_dynamic': [
    'Robert Cooper',
    'Robert Roth',
    'Sandra Meyer',
    'Brad Baker',
    'Richard Webb',
    'Elizabeth Vaughan',
    'Jerry Zimmerman',
    'Sara Vasquez',
    'Michael Rangel',
],
    'json': {
    'name': 'Stephanie Lopez',
    'address': '65365 Powell Field Suite 265\nDavidberg, CT 99836',
},
    'key86708': 'value34377',
    'key28378': 'value19535',
    'key76050': 'value12878',
    'key82889': 'value76875',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jose Bennett',
    'address': 'USNS Case\nFPO AA 02023',
    'text': 'Move of cause land drop street. Commercial cut attorney ground dream space.\nOption really example hospital prepare recent best. Strong take official hour specific community stuff.',
    'email': 'marksoto@example.org',
    'phone_number': '001-399-956-0475x368',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Melton',
    'Kristen Perry DDS',
    'Tina Harper',
    'Christopher Norman',
    'Sharon Mcgrath',
],
    'json': {
    'name': 'Donald Williams',
    'address': '6239 Brittney Route Suite 428\nLake James, FM 70320',
},
    'key62100': 'value67849',
    'key8460': 'value36092',
    'key54181': 'value31695',
    'key63361': 'value72735',
    'key9847': 'value73786',
    'key47618': 'value42327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Sherri Gonzales',
    'address': '735 Renee Road Apt. 947\nNew Christieville, OH 08848',
    'text': 'Around wear young affect car. Sometimes suddenly guy million reveal interest bad.\nFly everything avoid worker across. Leg modern Democrat whom.',
    'email': 'thompsontammy@example.org',
    'phone_number': '284-819-8630',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christine Wagner',
    'Andrew Scott',
    'Holly Elliott',
    'Alfred Johnson',
    'William Jones',
    'Robert Evans',
    'Terry Wallace',
    'Wanda Lopez',
    'Jeffrey Velasquez',
],
    'json': {
    'name': 'Martha Le',
    'address': 'Unit 9888 Box 7489\nDPO AA 93668',
},
    'key67373': 'value28467',
    'key54585': 'value35266',
    'key90945': 'value46606',
    'key94625': 'value34459',
    'key24868': 'value47144',
    'key79547': 'value26302',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Michael Ortiz',
    'address': '4695 Davis Hill\nBrittanyfort, OR 90442',
    'text': 'Especially mention hotel become. Catch high environment human nothing.\nAnything when happen sort paper past along work. Meet or entire turn Congress house blue. His school father house seat speech.',
    'email': 'gloriaward@example.org',
    'phone_number': '284-529-9037',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'David Stark',
],
    'json': {
    'name': 'Christopher Chavez',
    'address': '880 Mark Springs Suite 199\nEdwardsberg, TN 43259',
},
    'key60676': 'value47043',
    'key24404': 'value10218',
    'key48033': 'value68085',
    'key90674': 'value70886',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Shari Thompson',
    'address': '89141 Morgan Roads\nNew Anne, IL 96088',
    'text': 'Himself professor quality door you ability later. Artist may serve dog personal. However tough operation place keep the traditional speak.\nLanguage during nice eye impact get day.',
    'email': 'miguel01@example.net',
    'phone_number': '001-978-254-1819x2925',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Carmen Vance',
    'Renee Davidson',
    'Catherine Martinez MD',
    'Angel Sparks',
],
    'json': {
    'name': 'Mrs. Kelly Blair MD',
    'address': '89880 Chapman Forest Suite 474\nSmithville, CT 12258',
},
    'key47861': 'value4386',
    'key70449': 'value7634',
    'key67899': 'value50491',
    'key44747': 'value35017',
    'key78018': 'value10049',
    'key37000': 'value56089',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Daniel Holloway',
    'address': '168 Melissa Motorway\nSmithberg, WY 34169',
    'text': 'Let fill eight. Include enter big walk couple tree. Argue yard or around share.\nChoose probably statement major early ball test suddenly. Service worker series house unit.',
    'email': 'simsteresa@example.net',
    'phone_number': '(604)855-5050x9577',
    'array_int_dynamic': [
    62701,
],
    'array_varchar_dynamic': [
    'John Rodriguez',
],
    'json': {
    'name': 'Clayton Pearson',
    'address': '88623 Jimenez Fort\nMarilynview, IL 40295',
},
    'key51389': 'value86155',
    'key3386': 'value39017',
    'key34896': 'value65859',
    'key84660': 'value33735',
    'key48942': 'value5421',
    'key87079': 'value37853',
    'key93996': 'value64838',
    'key78767': 'value9333',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Monica Browning',
    'address': '898 Carlos Land\nJulialand, WI 32023',
    'text': 'Work guess according trade. Human movie court far place. Station lay support.\nYourself general degree gas decide. Opportunity side behind. Hotel and than arm marriage. Number simply baby.',
    'email': 'michael27@example.net',
    'phone_number': '567-773-3172x92273',
    'array_int_dynamic': [
    46420,
],
    'array_varchar_dynamic': [
    'Christian Davis',
    'Johnny Meyers',
],
    'json': {
    'name': 'Donald Butler',
    'address': '01225 Long Causeway Apt. 606\nBrittanyland, PR 52148',
},
    'key20326': 'value82112',
    'key18667': 'value29855',
    'key44830': 'value94662',
    'key90809': 'value82395',
    'key20903': 'value65923',
    'key51612': 'value72434',
    'key50008': 'value96821',
    'key4552': 'value9912',
    'key72110': 'value53912',
    'key14421': 'value9975',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Linda Walters',
    'address': '6499 Anthony Heights\nEast Faith, AR 35351',
    'text': 'Likely scene analysis.\nTax foot she man party radio. Somebody mean black sit.',
    'email': 'rvazquez@example.net',
    'phone_number': '748-871-7663',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Horton',
    'Jose Harvey',
    'Patricia Riddle',
    'Charles Burns',
    'Kevin Brewer',
    'Cathy Hawkins',
    'Michael Beck',
],
    'json': {
    'name': 'Jasmine Walton',
    'address': '4069 Johnson Isle\nSmithfurt, AZ 94220',
},
    'key7495': 'value2046',
    'key47011': 'value43749',
    'key98021': 'value57471',
    'key46392': 'value80635',
    'key87787': 'value95728',
    'key49851': 'value73391',
    'key42546': 'value92104',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Evan Barton',
    'address': 'USCGC Jenkins\nFPO AA 28940',
    'text': 'Local stay even newspaper. Stand yet run.\nLose use both care former management tell. Long study difficult. Always where mention whose. List sign away feeling course quickly hospital.',
    'email': 'vaguilar@example.net',
    'phone_number': '499.512.5763x057',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Laura Wilson',
    'Russell Wheeler',
    'David Santiago',
    'Robert Baker',
    'Tina Gonzalez',
    'Jennifer Dixon',
    'Brian Huff',
    'Walter Stevens',
    'Meagan Smith',
],
    'json': {
    'name': 'Brandi Bryant DDS',
    'address': '5442 Evans Ferry\nSouth Ginamouth, SD 47892',
},
    'key95977': 'value8870',
    'key46898': 'value42677',
    'key91829': 'value44010',
    'key23894': 'value7975',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Laura Gallegos',
    'address': '2737 William Crest\nPort Meghanhaven, FM 45132',
    'text': 'Feeling strong both wide race. For citizen member daughter art.\nHome improve outside media loss common. Office leader he industry pass light. Wide design might seek.',
    'email': 'wayneaguilar@example.net',
    'phone_number': '(739)605-9703x2886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Erica Tucker',
    'Dwayne Alvarado',
    'Carl Davis',
    'Kristin Gilmore',
    'Lori Haley',
],
    'json': {
    'name': 'Allen Sullivan',
    'address': '996 King Locks Suite 369\nLake Rebecca, OR 91958',
},
    'key43235': 'value44237',
    'key72416': 'value76324',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Taylor Willis',
    'address': '4915 John Orchard\nDixonberg, MS 02575',
    'text': 'View population morning relate easy center practice. Everybody take religious level necessary very.\nConsumer economic claim rule purpose including. Fast job former pressure letter since.',
    'email': 'henrypierce@example.net',
    'phone_number': '726.593.7368x90593',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brian Gilmore',
    'Michelle Campbell',
    'Thomas Williams',
    'Travis Martinez',
    'Melvin Winters',
    'Patrick Hale',
    'Carl Gates',
    'Yvette Rhodes',
],
    'json': {
    'name': 'Sara Wilcox',
    'address': '388 George Plain Apt. 130\nJacksonmouth, WI 52501',
},
    'key52731': 'value19662',
    'key40118': 'value20674',
    'key48429': 'value97932',
    'key24740': 'value43348',
    'key40414': 'value28928',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Matthew Clark',
    'address': 'Unit 5290 Box 0236\nDPO AE 08558',
    'text': 'Suddenly management few total stay. Tell view next open both music feel system.\nEvidence usually forward machine paper play share everyone. Trouble nation try perform everybody trial financial.',
    'email': 'melissagibson@example.net',
    'phone_number': '001-699-891-1193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Williams',
    'Morgan Davis',
    'Paul Ibarra',
    'Charles Barker',
    'Adriana Watts',
    'Kathleen Mitchell',
    'Todd Taylor',
    'Nicholas Hines',
],
    'json': {
    'name': 'Helen Barnes',
    'address': '66879 Patterson Throughway Suite 395\nNorth Amanda, UT 66893',
},
    'key11449': 'value89924',
    'key13694': 'value40843',
    'key63324': 'value91682',
    'key89720': 'value86652',
    'key24234': 'value7988',
    'key19292': 'value80560',
    'key28446': 'value37119',
    'key4433': 'value48276',
    'key41739': 'value56177',
    'key17847': 'value58804',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Suzanne Chen',
    'address': '8219 Nicholas River Suite 582\nKimchester, NY 20714',
    'text': 'Continue young teach great. Issue blue will design establish suffer member seem. Particularly central here security day.',
    'email': 'terricabrera@example.com',
    'phone_number': '+1-245-809-4560',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tonya Edwards',
    'Nathan Collins',
    'Blake Morris',
    'Jason Nichols',
    'Michele Wall',
    'Mason Alvarez',
    'Robert Sherman',
    'Cynthia Perez',
    'Jane Shaffer',
    'Stanley Jackson',
],
    'json': {
    'name': 'Patrick James',
    'address': '85643 Kyle Viaduct Suite 670\nPort Davidview, HI 47696',
},
    'key64564': 'value56602',
    'key59712': 'value77280',
    'key97822': 'value40062',
    'key85759': 'value65069',
    'key76363': 'value2751',
    'key49705': 'value82661',
    'key97916': 'value43173',
    'key1681': 'value70958',
    'key89739': 'value71879',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Theodore Lewis',
    'address': '5288 Flores Courts\nEast Danielview, KS 95829',
    'text': 'Letter partner loss health parent early. Capital specific picture image.\nWord nothing compare financial important. Ok nature benefit painting development call next. See tax any choose success should.',
    'email': 'xmunoz@example.com',
    'phone_number': '(473)331-6072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Paul Nash DDS',
    'Christina Mason',
    'Matthew Clayton',
    'Michelle Calhoun',
    'Michael Jones',
    'Kelly Wilson',
    'Eric Beasley',
],
    'json': {
    'name': 'Eric Walker',
    'address': '76754 Joe Loaf Suite 226\nNicoleland, NM 82480',
},
    'key93913': 'value76814',
    'key29938': 'value15162',
    'key34483': 'value99507',
    'key45970': 'value39296',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Edward Smith',
    'address': '2603 Catherine Park\nNorth Michaelview, KY 14060',
    'text': 'Than director help recent worry sell. Raise assume seek foreign. Oil white word image.\nGreen office cold born government. Notice simple one. History age feeling media.',
    'email': 'matthew50@example.com',
    'phone_number': '(600)793-0797',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Joyce',
    'Larry Evans',
    'Ashley Nichols',
    'April Vargas',
    'Matthew Mcbride',
],
    'json': {
    'name': 'Miguel Cruz',
    'address': '960 Taylor Spring\nRayburgh, MS 97506',
},
    'key94555': 'value7908',
    'key1670': 'value98116',
    'key88448': 'value74908',
    'key46914': 'value60557',
    'key93683': 'value99762',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Dawn Pittman',
    'address': '782 James Union Suite 460\nLake Gregory, DE 33276',
    'text': 'Material stock experience onto. Time figure out deep glass improve have.\nModel bag hand decade heart most. Look on federal always marriage.',
    'email': 'paul43@example.com',
    'phone_number': '001-852-562-8811x875',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Abigail Wilkerson',
    'Michelle Wang',
    'Katherine White',
    'Sara West',
    'Amanda Powers',
    'Tyler Thompson MD',
    'Christopher Callahan',
],
    'json': {
    'name': 'Richard Collins',
    'address': 'PSC 0887, Box 3384\nAPO AE 17669',
},
    'key34254': 'value67054',
    'key89447': 'value24821',
    'key26407': 'value69124',
    'key92654': 'value24735',
    'key33533': 'value7056',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'George Nichols',
    'address': '512 Fox Roads\nWest Michelle, SC 87996',
    'text': 'Such nation research huge. Green however kitchen light policy.\nEconomic hit deal government sport citizen energy.',
    'email': 'cortezbrett@example.net',
    'phone_number': '(375)950-9897',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Olivia Taylor',
    'Jeanette Coleman',
    'Kimberly Maldonado',
    'Joshua Jenkins',
    'Holly Davis',
    'George Phelps',
],
    'json': {
    'name': 'Frank Deleon',
    'address': '4662 Tanya Keys Suite 302\nKathyport, WI 98360',
},
    'key78174': 'value49893',
    'key9065': 'value90373',
    'key49734': 'value32095',
    'key87999': 'value25066',
    'key93315': 'value36141',
    'key52278': 'value82695',
    'key73104': 'value90045',
    'key26230': 'value44406',
    'key2953': 'value14120',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Perry Hanna',
    'address': '31296 Melendez Shore Apt. 427\nCannonbury, PR 30469',
    'text': 'Serve thousand pretty concern smile social good. Participant heavy job station simply become defense bit.\nSeries computer better. Discover medical live smile low energy pressure act.',
    'email': 'ashleedelacruz@example.org',
    'phone_number': '(907)327-4236',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jill Williams',
    'Rebecca Collier',
    'Hailey White',
],
    'json': {
    'name': 'Amy Hicks',
    'address': '265 Brenda Hollow Apt. 918\nJoseview, AS 13410',
},
    'key65671': 'value33525',
    'key96853': 'value4027',
    'key37186': 'value56714',
    'key9714': 'value70932',
    'key61886': 'value20534',
    'key7068': 'value6335',
    'key95962': 'value60837',
    'key53825': 'value96265',
    'key47529': 'value27389',
    'key33622': 'value25387',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'William Daniel',
    'address': '5401 Jonathon Rapids Suite 302\nNew Elizabeth, KS 81499',
    'text': 'Nearly song wonder ago onto.\nConference machine drug smile interview smile PM keep. Protect rate hit herself. Accept friend dark.',
    'email': 'robinsonlisa@example.net',
    'phone_number': '689.751.7072x600',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Hall',
    'Annette Flores',
    'Melissa Kelly',
    'Tammy Zimmerman',
    'Alexis Martin',
    'Carrie Miller',
    'Christy Wilkinson',
    'Austin Roberts',
],
    'json': {
    'name': 'Julia Warren',
    'address': '90649 Edwards Ford Apt. 448\nCarolchester, PW 29940',
},
    'key34669': 'value19120',
    'key80549': 'value26937',
    'key8430': 'value81782',
    'key98964': 'value59240',
    'key73195': 'value36223',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Brandi Nelson',
    'address': '537 Edwards Falls\nEast Melanieview, DC 29842',
    'text': 'South expect young assume threat accept beat. Second business company first million hand.',
    'email': 'beckybell@example.org',
    'phone_number': '001-536-977-2440x0827',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Erica Caldwell',
    'Russell Ferguson',
    'Laura Lane',
    'Erica Singleton',
    'Christopher Morton',
    'Kurt Murphy',
    'Mr. Nathan Lee',
    'Robert West',
    'Donna Tucker',
],
    'json': {
    'name': 'Alexandria Rivera',
    'address': '8546 Monica Cape Suite 780\nLake Jonbury, MI 96355',
},
    'key93650': 'value35448',
    'key55184': 'value74171',
    'key75846': 'value25435',
    'key37441': 'value87709',
    'key25262': 'value17179',
    'key40318': 'value67043',
    'key36350': 'value38636',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Eric Cole',
    'address': '96086 Hall Stream Suite 783\nWest Donald, MA 74479',
    'text': 'Newspaper think agree yes people. Once break far second hour against really. System professional change make report design.',
    'email': 'stewartheather@example.org',
    'phone_number': '559-533-8362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mark Newman',
    'Thomas Tapia',
    'Alexandria Gates',
    'Gloria Stokes',
    'Colleen Rich',
    'Joseph Shelton',
],
    'json': {
    'name': 'Amy Warner',
    'address': '0265 Sarah Manor Apt. 439\nJuliabury, KS 46785',
},
    'key50681': 'value21909',
    'key24870': 'value70160',
    'key24300': 'value75718',
    'key50916': 'value85758',
    'key93652': 'value93083',
    'key54105': 'value76406',
    'key6178': 'value23883',
    'key54723': 'value79095',
    'key25979': 'value13529',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Mark Huff',
    'address': '6631 Michelle Plains Apt. 516\nPort Christopherburgh, KS 38668',
    'text': 'Change many cell pick energy significant carry. Investment forward state factor. Pretty law measure action instead mouth marriage number.',
    'email': 'kanesusan@example.org',
    'phone_number': '001-966-313-9878x33643',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Terry Serrano',
    'Brent Davis',
    'Robert Jones',
    'Nina Foster',
    'Denise Banks',
    'Charles Martin',
    'Tamara Sanchez',
    'Roy Weaver',
    'Denise Lang',
],
    'json': {
    'name': 'Keith Crawford',
    'address': '8770 Amber Lights Apt. 497\nNew Lindabury, NM 35453',
},
    'key66794': 'value15725',
    'key67480': 'value57957',
    'key44594': 'value87986',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'James Hatfield',
    'address': '26286 Rowe Brooks\nSouth Karenshire, TX 44243',
    'text': 'New can theory own hand charge Mr within. Firm thank lot this.\nExpert challenge personal indeed. Scientist image him news area.',
    'email': 'jerry68@example.net',
    'phone_number': '001-986-498-6278',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Perez III',
    'Daniel Peters',
    'Katherine Fisher',
    'Jason Miller',
    'Derek Fitzgerald',
],
    'json': {
    'name': 'Robin Martin',
    'address': '61035 Moore Hills\nMadisonchester, DE 56690',
},
    'key28811': 'value76647',
    'key46351': 'value44136',
    'key58957': 'value20898',
    'key35456': 'value10202',
    'key65576': 'value44444',
    'key6126': 'value19962',
    'key16270': 'value56032',
    'key15694': 'value79552',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Nathan Russo',
    'address': '61680 Weber Corner\nWest Thomas, NV 55235',
    'text': 'Rule magazine me black respond. Able hold group subject hospital avoid blood discussion. Entire study really anything memory program too.',
    'email': 'vmorris@example.net',
    'phone_number': '+1-291-548-1282x37399',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Jones',
    'Michelle Warren',
    'Scott Bright',
    'Carrie Brown',
    'Marcus Armstrong',
    'Sheryl Cooper',
],
    'json': {
    'name': 'Tiffany Simmons',
    'address': 'PSC 3693, Box 2146\nAPO AA 55740',
},
    'key15179': 'value68445',
    'key742': 'value40107',
    'key35855': 'value5543',
    'key53075': 'value5424',
    'key86020': 'value35136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Eddie Holmes',
    'address': '77404 Amber Pike Suite 348\nJesusshire, CT 66313',
    'text': 'Little point not tree. Mention through point relationship media catch.\nAgreement organization Congress business indicate reach game. Parent after because affect economic own.',
    'email': 'rstone@example.net',
    'phone_number': '(348)582-7761x1270',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Misty Saunders',
    'Ernest Bishop',
    'Maria Anderson',
    'Mr. Joshua Garcia',
    'Sharon Carr',
    'Cheryl Mitchell',
    'Nicole Pacheco',
],
    'json': {
    'name': 'Stephen Mcknight',
    'address': '0455 Munoz Land Apt. 313\nWest Maria, MS 22742',
},
    'key29085': 'value77927',
    'key18517': 'value40436',
    'key68120': 'value97462',
    'key60512': 'value67506',
    'key21740': 'value68657',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Renee Smith',
    'address': '00410 Alvarez Junction\nSouth Susanview, OR 24498',
    'text': 'Continue yeah mention example case. Various really smile whatever.\nYet bed they inside fish visit conference. Statement interview gas itself author. Remain door argue head.',
    'email': 'krista03@example.org',
    'phone_number': '415-730-8546x780',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Allison Ponce',
    'David Hampton',
],
    'json': {
    'name': 'Melanie Graham',
    'address': '25994 Holder Forge Apt. 641\nCastilloport, ME 19433',
},
    'key47866': 'value87188',
    'key80599': 'value85425',
    'key69772': 'value56419',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Heather Walters',
    'address': '21300 Kaitlin Bypass\nDeniseville, CA 24891',
    'text': 'Hand parent the fast one college. Cultural nation future strong table.\nFigure simple technology none.\nMean or defense you member similar. President into fear require nice.',
    'email': 'richard01@example.com',
    'phone_number': '2354883494',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Mays',
    'Daniel Gomez',
    'Amy Thompson',
    'Trevor Snyder',
    'Michael Wilson',
    'Thomas Ross',
],
    'json': {
    'name': 'James Schmidt',
    'address': '464 Johnston Common Apt. 570\nLake Amyfort, MT 83483',
},
    'key4689': 'value59958',
    'key53220': 'value1338',
    'key58296': 'value37657',
    'key46448': 'value17139',
    'key59692': 'value32875',
    'key66719': 'value14214',
    'key25748': 'value97112',
    'key67528': 'value84',
    'key66000': 'value67875',
    'key71622': 'value42552',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Anthony Malone',
    'address': '1963 John Pine\nNew Karen, GU 14634',
    'text': 'Back clearly executive away most impact. Wide lead detail seat.\nBest reduce why improve catch set although best. Computer painting quality generation option.',
    'email': 'smccormick@example.com',
    'phone_number': '001-345-440-0846x90772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christina Ross',
],
    'json': {
    'name': 'John Hartman',
    'address': '652 Erik Shoal\nJohnsonshire, NY 35089',
},
    'key67610': 'value87407',
    'key646': 'value85029',
    'key50998': 'value91967',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Beth Price',
    'address': '48743 Trevino Drive\nNorth Kyleport, NV 81152',
    'text': 'Million when final concern play your. Least race season to recognize upon try. Letter send leg wide true low. Will truth discover.',
    'email': 'salexander@example.com',
    'phone_number': '8462027210',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Parker',
    'Nathan Morris',
    'Kelli Williams',
    'Christopher Silva',
    'Michael Bruce',
    'Lauren Smith',
    'Kimberly Harris',
    'Gregory Bailey',
],
    'json': {
    'name': 'Maria Fox',
    'address': '76837 Kimberly Manor\nBrownport, MP 12769',
},
    'key71556': 'value25587',
    'key68966': 'value21539',
    'key39844': 'value40122',
    'key44238': 'value34879',
    'key90739': 'value66316',
    'key80639': 'value54348',
    'key41719': 'value30835',
    'key14787': 'value81492',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Christine Park',
    'address': '4972 Candace Circle\nAnnfurt, AS 69528',
    'text': 'Face thought teacher tend agree similar.\nTo consider though month church business company. Prepare four husband know card difficult. Beautiful late role state need.',
    'email': 'michaelscott@example.com',
    'phone_number': '+1-941-212-9519x634',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kristina Jones',
    'Jeremy Williams',
    'Alicia Young',
    'Robin Aguilar',
    'Erin Walker',
    'Melissa Herman',
    'Martha Skinner',
],
    'json': {
    'name': 'Edward Allen',
    'address': '2429 Travis Cliff\nLake Jacksonburgh, AZ 80039',
},
    'key39037': 'value92989',
    'key41826': 'value64616',
    'key45847': 'value26478',
    'key74169': 'value43881',
    'key88322': 'value71757',
    'key58531': 'value52126',
    'key50623': 'value88523',
    'key53900': 'value59468',
    'key79592': 'value53088',
    'key77065': 'value68739',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Stephanie Anderson',
    'address': '585 Silva Field\nSouth Melissashire, PA 83031',
    'text': 'I responsibility stock staff. Pretty somebody natural.\nMajor entire dark because. Billion explain develop experience that business. Its magazine machine grow role instead heavy common.',
    'email': 'matthew86@example.com',
    'phone_number': '(791)777-0384',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Peter Mcguire',
    'William Williams',
    'Angela Knight',
],
    'json': {
    'name': 'Amy Porter',
    'address': '0429 Cody Track\nLake Anthony, CA 48867',
},
    'key52989': 'value64512',
    'key34048': 'value50950',
    'key19984': 'value13280',
    'key27232': 'value10395',
    'key96056': 'value56794',
    'key47205': 'value7821',
    'key34457': 'value19208',
    'key92810': 'value11508',
    'key80766': 'value10234',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Christopher Higgins',
    'address': '947 Gary Burgs\nWest Jasonside, FL 56036',
    'text': 'Wear knowledge house vote probably think.\nThemselves until we for bad. Newspaper purpose speech law area positive again.',
    'email': 'paulluna@example.net',
    'phone_number': '001-917-595-8010x723',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Walter Olsen',
],
    'json': {
    'name': 'David Lester',
    'address': '6376 Victor Gardens Apt. 640\nLindseyview, OH 91374',
},
    'key62713': 'value70260',
    'key45963': 'value10626',
    'key23401': 'value81628',
    'key10320': 'value4440',
    'key98176': 'value1164',
    'key91506': 'value29399',
    'key26903': 'value26423',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'James Bridges',
    'address': '49010 Hill Overpass\nMadelineview, FL 74960',
    'text': 'Finish others type about. Send religious teach surface ball movie buy.\nArea lot send less. President go soon third. Return still two either pick bring move.',
    'email': 'scott35@example.org',
    'phone_number': '+1-343-455-3457x498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Rogers',
    'Veronica Phillips',
    'John Johnson',
    'Valerie Williams',
    'Jackson Oconnor',
    'Barbara Morris',
    'Monica Robinson',
    'Brittany Camacho',
],
    'json': {
    'name': 'Marcus Davis',
    'address': '421 Hicks Fields Suite 653\nLake Brendamouth, UT 14996',
},
    'key11560': 'value3868',
    'key14394': 'value67423',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Wanda Scott',
    'address': '59559 Emily Inlet\nMartinmouth, HI 85099',
    'text': 'Education even plan performance public room early. Act expect big.\nCouple happy number those north. Page sit choose oil morning toward whatever.',
    'email': 'davislarry@example.net',
    'phone_number': '+1-598-839-3329x16553',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Graham',
    'Matthew Raymond',
    'Matthew White',
],
    'json': {
    'name': 'Sabrina Hamilton',
    'address': '97284 Terrell Passage Apt. 682\nNew Courtneyfurt, MA 07238',
},
    'key35855': 'value2864',
    'key2292': 'value67631',
    'key18518': 'value12138',
    'key71858': 'value86419',
    'key13253': 'value18417',
    'key71192': 'value42411',
    'key55933': 'value77871',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Amanda Lester',
    'address': '71172 Brown Tunnel\nKaribury, ND 26915',
    'text': 'Think left friend. List training fast parent rule consider whom.\nHimself account science free inside hold religious. Course surface car foot.',
    'email': 'jamescarter@example.net',
    'phone_number': '(760)696-5226x63360',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Mcdonald',
    'Kristopher Grimes',
],
    'json': {
    'name': 'Tiffany Golden',
    'address': '65428 Carter Lake\nAndrewschester, MH 94092',
},
    'key58221': 'value3562',
    'key40290': 'value77771',
    'key68560': 'value39028',
    'key85261': 'value42823',
    'key35760': 'value3673',
    'key8152': 'value81927',
    'key92033': 'value16066',
    'key64291': 'value89277',
    'key73419': 'value42176',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Christine Morales',
    'address': '83183 Ramirez Corners Apt. 866\nKennethmouth, NY 12404',
    'text': 'Itself lawyer receive short interest. Job science recognize human.\nReal interesting audience watch. Forward size name area memory arrive write charge.',
    'email': 'kathrynstevenson@example.org',
    'phone_number': '680.716.7375',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl Allen',
    'Alexis Bennett',
    'Christopher York',
    'Jody Lewis',
    'Thomas Smith',
    'Jerry White',
    'Michael Reeves PhD',
    'Albert Williams',
    'David Mclaughlin',
],
    'json': {
    'name': 'Kayla Cox',
    'address': '36133 Pedro Estates Suite 582\nJeffreyhaven, AZ 86175',
},
    'key91614': 'value74412',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Brady Martinez',
    'address': '958 Jose Plains Suite 597\nNorth Heather, KY 57551',
    'text': 'Until pull nothing data central lawyer environmental. Black subject check south southern else. Contain news sell behind.\nNo south agent mention floor read modern. End when sometimes record face.',
    'email': 'brooke79@example.com',
    'phone_number': '902.806.2038x176',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gary Fields',
    'Debbie Patton',
    'Sylvia Jones',
    'Kyle Kennedy',
],
    'json': {
    'name': 'Kevin Lopez',
    'address': '57466 Lee Springs\nKathleenside, WV 40820',
},
    'key23512': 'value70854',
    'key12696': 'value36407',
    'key61041': 'value79395',
    'key54348': 'value42965',
    'key98347': 'value35827',
    'key26875': 'value97457',
    'key22773': 'value93097',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Heidi Benton',
    'address': 'PSC 9912, Box 5450\nAPO AA 47995',
    'text': 'Option interest discover prove. Movement force community million. Generation close discover hundred field it.',
    'email': 'matthew88@example.org',
    'phone_number': '558-575-2182x2823',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Maxwell Davis',
    'William Black',
],
    'json': {
    'name': 'Lisa Clark',
    'address': '878 Nelson Keys Suite 934\nWest Sheilatown, VT 58457',
},
    'key47085': 'value79236',
    'key5506': 'value43041',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Nicholas Boyle',
    'address': '29782 Matthew Ford\nPort Kristen, VT 70985',
    'text': 'Game others suffer everything Democrat usually idea. Job president certain. Well themselves eight generation.',
    'email': 'williamscody@example.net',
    'phone_number': '+1-383-694-1291x374',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Williams',
    'Gina Thomas',
    'Crystal Jones',
],
    'json': {
    'name': 'Ronald Williams',
    'address': '454 Zachary Port Suite 809\nSouth Jessicashire, NV 94363',
},
    'key3710': 'value10498',
    'key85186': 'value70977',
    'key60710': 'value7888',
    'key71008': 'value78891',
    'key19481': 'value33928',
    'key20688': 'value42594',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'James James',
    'address': 'PSC 3526, Box 5385\nAPO AA 49075',
    'text': 'Perform conference week year best heart to. Thing religious moment our. Position pretty gas. Significant institution decide floor.\nSpeak threat bar race.',
    'email': 'gutierrezadam@example.org',
    'phone_number': '(413)879-7784x84664',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Dickson',
],
    'json': {
    'name': 'Kelsey Colon',
    'address': '8679 Joseph Ferry\nHardyburgh, OH 69652',
},
    'key28591': 'value71972',
    'key43319': 'value46293',
    'key20592': 'value83387',
    'key15194': 'value98394',
    'key6525': 'value99249',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Teresa Molina',
    'address': '15523 Ashley Loaf Suite 021\nWebbstad, IA 25704',
    'text': 'Water tough little town large.\nCommercial debate behind require source now. Determine civil such compare notice over common. Participant claim wonder student cover lawyer better.',
    'email': 'johncowan@example.com',
    'phone_number': '(954)436-7231x5984',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Angela Lara',
    'Christopher Coleman',
    'Douglas Ray',
    'Leslie Perez',
    'Lori Sullivan',
],
    'json': {
    'name': 'Taylor Schroeder',
    'address': '41010 Richardson Fields\nPort Gary, PR 65605',
},
    'key75379': 'value37122',
    'key99064': 'value62731',
    'key10151': 'value87994',
    'key74845': 'value19163',
    'key50038': 'value13019',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jaclyn George',
    'address': '53288 Lauren Trail\nNew Latashastad, UT 36729',
    'text': 'Herself knowledge stuff mouth hold. Hold baby respond election take.\nSeveral amount popular office. Raise act information argue lose rather seek.',
    'email': 'jameslee@example.com',
    'phone_number': '001-779-484-8992x9667',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kim Rodriguez',
    'Debbie Hamilton',
    'Kevin Moss',
    'Misty Colon',
    'Monica Ward',
    'Candice Jones',
    'Nathan Barker',
    'Charles Acosta',
    'Taylor Simon',
],
    'json': {
    'name': 'Tyler Conner',
    'address': 'Unit 8676 Box 7193\nDPO AP 49916',
},
    'key18453': 'value14454',
    'key13950': 'value83501',
    'key79577': 'value95652',
    'key32172': 'value91027',
    'key29887': 'value49164',
    'key51782': 'value93990',
    'key10890': 'value26158',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Dennis Davis',
    'address': '3487 Christy Centers Apt. 220\nGuerreromouth, WI 08698',
    'text': 'About road several office list raise high. How huge report see because.\nStrategy continue factor claim. Look beat use either floor. Manager fill say analysis trouble green already.',
    'email': 'justin00@example.com',
    'phone_number': '001-741-949-8073x72277',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Edwards',
    'Heidi Martinez',
    'Sierra Smith',
    'Lori Bautista',
    'Katrina Clark',
    'Chris Thomas',
    'Bradley Weeks',
    'Charles Griffin',
    'Brandy Velasquez',
],
    'json': {
    'name': 'James Preston',
    'address': '3910 George Lane Apt. 761\nNorth Johnhaven, MO 96533',
},
    'key88539': 'value1843',
    'key18060': 'value37069',
    'key71100': 'value50128',
    'key44455': 'value83417',
    'key65249': 'value32851',
    'key46576': 'value46469',
    'key18965': 'value86011',
    'key96132': 'value16161',
    'key24222': 'value9054',
    'key68136': 'value65698',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Mrs. Hailey Turner',
    'address': '7950 Alyssa Walk Apt. 382\nWest Adam, CT 71775',
    'text': 'Production building relate the house. Book me teacher tend box move.\nRelationship coach need occur partner about. Mean body across. Why level list individual industry director.',
    'email': 'tammy32@example.net',
    'phone_number': '552-493-9264',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Johnson',
    'Scott Solomon',
],
    'json': {
    'name': 'Jennifer Willis',
    'address': '798 Smith Common\nJosephview, KS 95286',
},
    'key61420': 'value99330',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Eric Romero',
    'address': '641 Ruiz Green Suite 999\nWalkerfort, KY 33386',
    'text': 'Order animal return standard human other while. Dinner when live fall pressure commercial. Early white ready day series.',
    'email': 'nmathis@example.com',
    'phone_number': '(200)608-8738x563',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Kelley',
    'John Simmons',
],
    'json': {
    'name': 'Alexandra Allen',
    'address': '118 Corey Route Apt. 379\nDannyberg, ID 76262',
},
    'key67933': 'value26289',
    'key66268': 'value16993',
    'key34422': 'value47175',
    'key27075': 'value42003',
    'key46749': 'value32991',
    'key91428': 'value30310',
    'key66800': 'value89337',
    'key9735': 'value66828',
    'key5573': 'value62780',
    'key93242': 'value30179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jonathan West',
    'address': 'Unit 3688 Box 3174\nDPO AP 52243',
    'text': 'Institution operation public agent. Lead thing industry statement economic fill air. How across science identify culture red our.\nReach suffer third your why begin sit.',
    'email': 'jherrera@example.org',
    'phone_number': '(968)464-7513',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Crosby',
],
    'json': {
    'name': 'Elizabeth Jenkins',
    'address': '10050 David Turnpike Suite 788\nMcphersonmouth, KY 14165',
},
    'key23656': 'value9875',
    'key60941': 'value36328',
    'key13779': 'value33848',
    'key48994': 'value79850',
    'key61179': 'value42398',
    'key96168': 'value87895',
    'key15989': 'value77819',
    'key13102': 'value74047',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'John Keller',
    'address': '7821 Short Divide Suite 394\nPort Dennisfort, VA 25008',
    'text': 'Voice than why before board newspaper. Economy behavior outside involve include. Condition even well ask different TV offer.',
    'email': 'drodriguez@example.com',
    'phone_number': '994.528.3484x80515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Griffin',
    'Kristin Perez',
    'Adam Evans DDS',
    'Russell Gentry',
    'Kelly Wilson',
    'Angel Martin',
],
    'json': {
    'name': 'Eric Anderson',
    'address': '76187 Tyler Forge\nDavisstad, IA 74048',
},
    'key51407': 'value53601',
    'key65097': 'value62238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Robert Booker',
    'address': '5679 Luna Extension\nNew Michele, MO 35123',
    'text': 'Service operation model tax not decision white. Run other town cut TV include people. Material write want manager beautiful class.',
    'email': 'millschristopher@example.org',
    'phone_number': '6092713737',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Grant',
    'Michael Payne',
    'Paul Rogers',
    'Nicholas West',
    'Jesus Phillips DVM',
    'Michael Lin',
],
    'json': {
    'name': 'Rodney Jones',
    'address': '522 Victoria Summit\nRochabury, PR 30266',
},
    'key25063': 'value15632',
    'key66638': 'value91088',
    'key38444': 'value33850',
    'key59942': 'value37752',
    'key29442': 'value93417',
    'key139': 'value69691',
    'key90471': 'value23775',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Elizabeth Swanson',
    'address': '2826 Knapp Shoals Apt. 317\nJosephland, GA 02176',
    'text': 'Ago over discover social.\nUntil everybody force. Feeling college customer second individual clearly.\nFinish every join unit son return. Teach number challenge end despite in. Name young use fund.',
    'email': 'elizabeth01@example.net',
    'phone_number': '771.430.3869x53763',
    'array_int_dynamic': [
    60161,
],
    'array_varchar_dynamic': [
    'Renee White',
    'Krystal Ross',
    'Jonathan Lewis',
    'David Santos',
    'Timothy Mcbride',
],
    'json': {
    'name': 'Nichole Conner',
    'address': '0243 Rebecca Corner\nLake Elizabethview, MI 26149',
},
    'key9657': 'value84111',
    'key18258': 'value59534',
    'key78708': 'value45487',
    'key94995': 'value69945',
    'key4708': 'value33104',
    'key8211': 'value94708',
    'key50583': 'value2571',
    'key74293': 'value58244',
    'key73119': 'value54494',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Brian Price',
    'address': '4609 Teresa Forges Apt. 103\nLake Crystal, NJ 18613',
    'text': 'Design right choose official. Wear mean character senior eat save all. Beat sit have happen citizen whole food.\nPerformance second imagine sit economy fall. Laugh law single however.',
    'email': 'ashleybyrd@example.org',
    'phone_number': '6014134971',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Patel',
    'Chelsea Stewart',
    'Jamie Brooks',
],
    'json': {
    'name': 'Justin Medina',
    'address': '51574 Samantha Plain\nEast Hunter, ND 78033',
},
    'key83058': 'value80286',
    'key46796': 'value97583',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Alan Ayers',
    'address': '6555 Stephen Highway\nKiarafurt, KS 82933',
    'text': 'Rather method radio show house then.\nCold miss notice might national Mr usually. Seem small down. Success official agency right treat.\nTeach business rule good some day. Still cup fall exactly.',
    'email': 'htran@example.org',
    'phone_number': '001-752-988-8507x3660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'James Rodriguez',
    'Emily Benson',
    'Charles Davis',
    'Sherry Contreras',
    'Sylvia Lamb',
    'Gary Fitzgerald',
    'Carl Horton',
    'Gregory Silva',
],
    'json': {
    'name': 'Robin Reese',
    'address': '721 Patel Valleys Apt. 510\nLake Luisview, MD 74580',
},
    'key78136': 'value1965',
    'key25682': 'value48197',
    'key62103': 'value91215',
    'key43551': 'value37156',
    'key86848': 'value31684',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Lisa Sanchez',
    'address': '3883 Holland Avenue\nMeganbury, SD 51743',
    'text': 'Play offer new use hospital political. Military size tough water rich father public.',
    'email': 'stevenstewart@example.com',
    'phone_number': '9383562146',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Reginald Clark',
    'Ryan Brady',
],
    'json': {
    'name': 'Paul Hardin',
    'address': '362 Cox Trafficway Apt. 273\nLake April, HI 01537',
},
    'key36047': 'value35549',
    'key72428': 'value33835',
    'key28117': 'value7345',
    'key24347': 'value94388',
    'key71033': 'value44469',
    'key41836': 'value63184',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Sydney Rivera',
    'address': 'USNV Oliver\nFPO AE 34216',
    'text': 'Picture deal role suddenly building price. Kitchen and score something great. Success outside professional exist success base.',
    'email': 'kimberlybradley@example.com',
    'phone_number': '200-309-4626x051',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Gill',
    'Norman Martinez',
    'Desiree Burns',
    'Gavin Schneider',
    'Kyle Berry',
    'Mary Johnson',
    'Gary Stephens',
    'Kristie Hensley',
    'Jeffrey Benson',
],
    'json': {
    'name': 'Jack Taylor',
    'address': '81309 Heather Light\nRobertchester, LA 69329',
},
    'key96995': 'value44979',
    'key84255': 'value38680',
    'key68361': 'value70679',
    'key93700': 'value19006',
    'key68263': 'value98047',
    'key18467': 'value48696',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kristin Herring',
    'address': '133 Cruz Ridge\nWest Traci, CA 12091',
    'text': 'Later set front ok social radio. This network year think. Up get white different future. Apply store important interview out finish.\nThe development easy writer score.',
    'email': 'karen93@example.net',
    'phone_number': '466-723-1255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Loretta Weaver',
],
    'json': {
    'name': 'Michael Ramirez',
    'address': '127 Tammy Glen Apt. 152\nHayesburgh, VT 09224',
},
    'key79269': 'value64441',
    'key96706': 'value36481',
    'key51597': 'value44677',
    'key26957': 'value26054',
    'key5419': 'value71568',
    'key42606': 'value60027',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Kathryn Horn',
    'address': '595 Christopher Loop Apt. 204\nLake David, KY 97596',
    'text': 'Board during none kind its. Reduce after key cup fight then. Game economy box themselves.',
    'email': 'ubartlett@example.net',
    'phone_number': '001-577-599-0784x0770',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Barrett',
    'Jeremy Hardin',
    'Marissa Adams',
    'Jeff Gross',
    'Christine Gentry',
    'Jason Oliver',
    'Rita Miller',
    'Amber Hutchinson',
],
    'json': {
    'name': 'Matthew Gallegos',
    'address': '639 Brandon Keys\nAndrewfurt, PW 84356',
},
    'key96089': 'value88763',
    'key12937': 'value5488',
    'key86510': 'value5324',
    'key75352': 'value51288',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Matthew Jacobson',
    'address': 'PSC 7257, Box 3349\nAPO AP 87277',
    'text': 'Mrs spend put institution. Choose level rest fill.\nLeg fund involve own apply school century. Yard house produce sea.\nLikely think blood stop. Chair town peace theory.',
    'email': 'sdominguez@example.net',
    'phone_number': '001-643-478-6668x011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Perry',
    'Charlotte Nicholson',
    'Linda Watson',
],
    'json': {
    'name': 'Mr. Cole Lopez',
    'address': '7914 Parker Haven Suite 828\nMckinneyfort, ND 98751',
},
    'key32960': 'value77245',
    'key65082': 'value19504',
    'key2254': 'value60713',
    'key8131': 'value95501',
    'key8163': 'value84359',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Tracy Mendoza',
    'address': '782 Mary Ville\nWest Meredithfort, NC 91635',
    'text': 'Prepare example general next himself might. Smile stock join citizen. Bill summer campaign machine. Over forward so attack college standard into.',
    'email': 'bstrong@example.org',
    'phone_number': '6767559330',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Barnett',
    'William Hall',
],
    'json': {
    'name': 'Ellen Crawford',
    'address': '857 Carey Islands\nLake Tamaraview, KS 66679',
},
    'key66163': 'value88207',
    'key88977': 'value32489',
    'key88343': 'value55320',
    'key66075': 'value37058',
    'key72760': 'value4291',
    'key19498': 'value89375',
    'key24143': 'value82244',
    'key40613': 'value3558',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jessica Baker',
    'address': '63614 William Viaduct\nLake James, NH 20361',
    'text': 'Interesting interest table site chair. Use rock save recognize level western city. Maintain rule respond future protect.',
    'email': 'joannegarcia@example.net',
    'phone_number': '6873792656',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Charles Richards',
    'Shannon Little',
    'Amy Williams',
    'Kayla Lee',
    'Michael Fleming',
    'Michael Harris',
    'Jeremy Smith',
    'Margaret Willis',
    'Dana Keller',
],
    'json': {
    'name': 'Aaron Stevens',
    'address': '08177 Sharon Point\nNorth Christophershire, NE 93956',
},
    'key77585': 'value66289',
    'key25618': 'value86599',
    'key88656': 'value83748',
    'key74766': 'value50389',
    'key30779': 'value6969',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Valerie Fitzgerald',
    'address': '78403 Christine Mount Suite 257\nRobertside, AZ 93205',
    'text': 'Guy card own condition quality either visit more. Determine hundred far interesting. Oil draw movie general them control.',
    'email': 'aconrad@example.net',
    'phone_number': '+1-306-589-2136x17447',
    'array_int_dynamic': [
    19161,
],
    'array_varchar_dynamic': [
    'Alicia Lawson',
    'Brad Walker',
    'Pamela Chandler',
    'Lisa Garcia',
    'Melissa Perry',
    'Eddie Allen',
    'Jeanette Ferrell',
    'Mark Cooper',
],
    'json': {
    'name': 'Luis Jones',
    'address': '10461 Washington Harbors Apt. 226\nNorth Richard, ND 47910',
},
    'key17566': 'value59577',
    'key6121': 'value76209',
    'key23337': 'value31472',
    'key54455': 'value52563',
    'key57857': 'value25806',
    'key91943': 'value50177',
    'key41815': 'value35529',
    'key84695': 'value13320',
    'key98211': 'value81907',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Amanda Pena',
    'address': 'Unit 5740 Box 7315\nDPO AE 13913',
    'text': 'Material specific sign recent body. Miss wonder military use indeed environmental as.\nContinue exist woman two vote power. Exist it hot.\nInto personal check option. Wonder budget talk whether friend.',
    'email': 'qmiller@example.org',
    'phone_number': '+1-840-960-8939',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Santiago',
    'Jean Brock',
    'Eric Rogers',
    'Timothy Jackson',
    'Daniel Camacho',
    'Kara Stafford',
    'Sharon Wood',
],
    'json': {
    'name': 'Stephanie Lin',
    'address': '4622 Mary Coves\nNew Stefanieshire, CA 29560',
},
    'key64109': 'value56597',
    'key73025': 'value51229',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Travis Miller',
    'address': 'Unit 1916 Box 2555\nDPO AE 79179',
    'text': 'Break low expect rest cut. Old since newspaper later amount at. In heart ever administration.',
    'email': 'oliviayoung@example.com',
    'phone_number': '+1-863-396-0739x27244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Page',
    'Jennifer Le',
    'Donna Frazier',
    'Erika Alexander',
    'Beth Lucero',
    'Tammy Scott',
    'Brett Wise',
],
    'json': {
    'name': 'Edward Kramer',
    'address': '38173 Victoria Brooks\nGibsonton, OK 97175',
},
    'key80110': 'value38782',
    'key39386': 'value85911',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Sheila Warren',
    'address': '972 Jeremy Extension Suite 090\nRonaldburgh, NC 25905',
    'text': 'Everybody every role free. But serious plant for.\nMove toward either wrong better stand which. Section every conference industry serve.',
    'email': 'jaythomas@example.org',
    'phone_number': '001-926-636-7359x91861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Gina Valencia',
    'Greg Bolton',
    'Gary Bryant',
    'Laura Richards',
],
    'json': {
    'name': 'Terri Morris',
    'address': '96204 John Fork\nEast Courtneyburgh, GA 89230',
},
    'key57530': 'value35899',
    'key39114': 'value77078',
    'key30905': 'value23199',
    'key64159': 'value34458',
    'key26796': 'value70402',
    'key76715': 'value15432',
    'key41764': 'value63403',
    'key26757': 'value95418',
    'key67271': 'value77064',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Chad Newton',
    'address': '645 Chang Ville\nKylieberg, OK 94929',
    'text': 'Attorney responsibility white officer identify. Go run window street.\nBig teach chair success. Moment rest million commercial movement paper set.\nDecision try they senior condition life.',
    'email': 'christina58@example.net',
    'phone_number': '706-374-2431x3632',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amy Allen',
    'Traci West',
],
    'json': {
    'name': 'John Ayala',
    'address': '06214 Edward Spur Apt. 373\nJordanberg, WA 86946',
},
    'key78936': 'value26929',
    'key14642': 'value49293',
    'key40589': 'value19075',
    'key36557': 'value47568',
    'key86432': 'value10960',
    'key94': 'value19918',
    'key77308': 'value11631',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Christopher Sanchez',
    'address': '95293 Stephanie Court Apt. 354\nPort Barbaraberg, TN 09703',
    'text': 'Camera hold deep wife expert. Fly nation pay push road room good.\nUntil guess amount wear significant.',
    'email': 'catherinebrown@example.org',
    'phone_number': '(281)277-3752x327',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Mann',
    'Joseph Solomon',
    'Oscar Conrad',
    'Brett Lucas',
    'Erin Allen',
],
    'json': {
    'name': 'Tanya Carroll',
    'address': '54416 Galloway Rapids Suite 027\nPort Kevintown, GU 02418',
},
    'key54826': 'value20843',
    'key87255': 'value11273',
    'key15042': 'value73733',
    'key8656': 'value40586',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Andrea Morton',
    'address': 'PSC 2785, Box 9889\nAPO AP 57848',
    'text': 'Choose wall task trip move seven green. Window trade system amount.\nSituation than former sing mention early another.',
    'email': 'mariogomez@example.org',
    'phone_number': '398-815-1604x2972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Maria Summers',
    'Renee Christian',
    'Emily Ward',
    'Michelle Price',
    'Elizabeth Johnson',
    'Donald Cooke',
    'Paula Carter',
    'Cheryl Smith',
    'Jasmine Oneal',
],
    'json': {
    'name': 'William Garcia',
    'address': '3530 Newton Corner\nThomaschester, WV 83223',
},
    'key38065': 'value14330',
    'key60126': 'value9031',
    'key16038': 'value87824',
    'key29244': 'value41982',
    'key2050': 'value5777',
    'key40731': 'value80717',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Emily Contreras',
    'address': '0954 James Islands\nWest Kristenstad, MO 31378',
    'text': 'Serious rest method specific dog I yet. Live face morning nice within happy.\nTell next choice home similar. Matter those maintain him full military. Never dog now prove remember prevent number.',
    'email': 'nwallace@example.net',
    'phone_number': '974-662-1265x52962',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alexis Ballard',
    'Tyler Dawson',
    'Bobby Davis',
    'Jonathan Ayala',
    'Tanya Moore',
    'Taylor Williams',
    'Lisa Martin',
    'Gregory English',
    'Melissa Daniels',
],
    'json': {
    'name': 'Michelle Cox',
    'address': '123 Barton Ferry\nPadillastad, PA 17078',
},
    'key3390': 'value4757',
    'key62889': 'value27071',
    'key88331': 'value78303',
    'key84306': 'value48123',
    'key43374': 'value71443',
    'key18208': 'value90011',
    'key67682': 'value59442',
    'key41974': 'value89736',
    'key70075': 'value74165',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Crystal Thomas',
    'address': '4414 Morgan Cape Apt. 269\nCarriehaven, TN 54326',
    'text': 'Nation cut feeling. Century employee arrive parent. Part meet offer consumer put adult call.',
    'email': 'bowmankimberly@example.net',
    'phone_number': '+1-348-752-8171x66471',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Todd Fritz',
    'Ashlee White',
    'William Watts',
    'Angela Watson',
    'John Williams',
    'Bradley Frank',
    'Benjamin Price',
],
    'json': {
    'name': 'Briana Miles',
    'address': 'PSC 8660, Box 4284\nAPO AA 62512',
},
    'key65871': 'value98690',
    'key93576': 'value35883',
    'key40072': 'value58008',
    'key79740': 'value82038',
    'key262': 'value48536',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Mark Woodward',
    'address': '851 Nicholas Alley\nZacharyview, VA 59464',
    'text': 'His past drug two course world so into. Middle why American citizen voice change name a. Seem may job.',
    'email': 'rodneyramirez@example.org',
    'phone_number': '(959)929-0717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mariah Hart',
    'John Salinas',
    'Robert Clark',
    'Kylie Guzman',
    'Michael Martinez',
    'Vanessa Moore',
    'Joshua Durham',
    'Theresa Vaughn',
    'Robert Bell',
],
    'json': {
    'name': 'Brenda Martinez',
    'address': '86544 Cooper Mall\nAmandafurt, MN 02838',
},
    'key82625': 'value55832',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Mr. Colin Munoz',
    'address': '6055 Davis Summit\nNorth Alisonside, MH 65005',
    'text': 'Evening reality light task. Little treat today serious size themselves peace. Need network product trouble language.',
    'email': 'wnorris@example.net',
    'phone_number': '+1-996-581-3439',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mariah Williams',
    'Tammy Glenn',
    'Linda Hensley',
    'Amy Owens',
    'Jeanette Johnson',
],
    'json': {
    'name': 'Michael Cline',
    'address': '4092 Fred Isle\nClaytonbury, NE 85972',
},
    'key13920': 'value30886',
    'key74677': 'value8961',
    'key7750': 'value5754',
    'key14649': 'value712',
    'key38719': 'value27186',
    'key6114': 'value61970',
    'key87672': 'value61302',
    'key3581': 'value7592',
    'key68531': 'value63647',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Lauren Hatfield',
    'address': '60064 Gary Mountains\nHarveyhaven, RI 39736',
    'text': 'Whether mother vote loss card give. Prove break debate computer discover box alone win.\nWar imagine sport must. Television owner region.',
    'email': 'erojas@example.org',
    'phone_number': '694.491.0888',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Weaver',
    'Amy Pratt',
    'Nicole James',
    'Priscilla Collins',
    'Gina Barnett',
    'Amy Lucas',
    'Chad Liu',
    'Joshua Gray',
    'Lisa Nelson',
],
    'json': {
    'name': 'Monica Morales',
    'address': '9965 Alvarez Route Suite 445\nPort Zachary, AZ 88964',
},
    'key2291': 'value59508',
    'key2049': 'value967',
    'key23410': 'value7512',
    'key82754': 'value49143',
    'key2121': 'value42415',
    'key64138': 'value43638',
    'key22758': 'value41378',
    'key12504': 'value70268',
    'key5208': 'value34520',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Sean Hill',
    'address': '61951 Freeman Turnpike Suite 550\nPort Christinahaven, CO 87783',
    'text': 'Agreement keep small claim keep husband above itself. Against inside whole then. Response main key we talk there tree. Rise relate risk senior.',
    'email': 'terrellryan@example.org',
    'phone_number': '001-652-670-2901x92696',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Kelly',
    'Dr. Karen Ortega',
    'Barbara Hopkins',
    'Vickie Daniels',
],
    'json': {
    'name': 'Melissa Barrett',
    'address': '54147 Crawford Glen\nWest Robertshire, WI 83634',
},
    'key11190': 'value52553',
    'key64023': 'value94319',
    'key27466': 'value76827',
    'key71453': 'value63013',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Sheila Villanueva',
    'address': '6224 Angela Orchard Apt. 203\nKruegertown, AZ 88375',
    'text': 'Where much TV responsibility staff hand majority. Team since world without others party.',
    'email': 'griffinshannon@example.net',
    'phone_number': '(605)436-5548',
    'array_int_dynamic': [
    84168,
],
    'array_varchar_dynamic': [
    'Tamara Gray',
],
    'json': {
    'name': 'Rhonda Kirby',
    'address': '8219 Henry Station Apt. 650\nWest Teresafort, AK 57740',
},
    'key63351': 'value1419',
    'key10213': 'value61504',
    'key29903': 'value77552',
    'key82804': 'value74351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Julie Jackson',
    'address': '9640 Jodi Drive Suite 353\nMelaniefurt, ME 22725',
    'text': 'Hand beautiful number trial leg. Financial necessary protect.\nReflect the want study. Approach turn garden college today now. Hear thought reveal interesting. Defense skill other company.',
    'email': 'shirley66@example.net',
    'phone_number': '995-904-5462x8736',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Andrews',
    'Christy Taylor',
    'Emily White',
    'Sabrina Nicholson',
    'Abigail Brewer',
],
    'json': {
    'name': 'Virginia Willis',
    'address': '344 Stacey Brook Apt. 948\nRussomouth, VI 43071',
},
    'key93011': 'value15386',
    'key11790': 'value22819',
    'key68734': 'value13132',
    'key7973': 'value13356',
    'key12009': 'value97559',
    'key17457': 'value57050',
    'key17220': 'value87007',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Timothy Morrow',
    'address': '52386 Cathy Isle Apt. 967\nLaurashire, VI 45688',
    'text': 'Others today letter during off. Despite computer partner special nature build sport senior. Space follow under individual couple run.',
    'email': 'danawilkerson@example.com',
    'phone_number': '834.972.7455x2429',
    'array_int_dynamic': [
    78213,
],
    'array_varchar_dynamic': [
    'Nicole Davis',
],
    'json': {
    'name': 'Dr. Kyle Sanchez',
    'address': '415 Taylor Mill Apt. 762\nJohnborough, MT 34862',
},
    'key76850': 'value63264',
    'key64543': 'value7467',
    'key95295': 'value7069',
    'key2453': 'value75424',
    'key97118': 'value81173',
    'key40945': 'value65472',
    'key45315': 'value33793',
    'key48328': 'value98298',
    'key39107': 'value46089',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Christopher Kelly',
    'address': '75778 William Streets\nLozanoside, FM 65101',
    'text': 'How inside information popular near claim four.\nCut example claim agreement expert food ball. Just information soldier attack summer evidence source. Chance notice task rock heart try because north.',
    'email': 'daniellegonzalez@example.org',
    'phone_number': '685-338-4114',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Cox',
    'Charles Cruz',
    'Sara Galvan',
    'Caitlin Reeves',
    'Christina Bray DVM',
    'Brad Barrett',
    'April Long',
    'Anna Carrillo',
    'Leslie Jacobson',
    'Duane Johnson',
],
    'json': {
    'name': 'Lindsey Larson',
    'address': 'USNV Decker\nFPO AP 16088',
},
    'key21775': 'value69176',
    'key25103': 'value40741',
    'key37755': 'value49062',
    'key46297': 'value42029',
    'key8121': 'value57774',
    'key38463': 'value26842',
    'key37940': 'value42441',
    'key53936': 'value25935',
    'key91082': 'value37870',
    'key83990': 'value50789',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Luke Sweeney',
    'address': '6622 Michael Ridge Apt. 759\nEast Sabrina, CO 37933',
    'text': 'Follow year enter. Ball both next good owner leg support.\nLow including worry. Per east friend whole hot no. Adult foot state because space close prevent.',
    'email': 'waltonelizabeth@example.net',
    'phone_number': '224.395.2823x386',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Oneal',
    'Bradley Hernandez',
    'Fernando Ayers',
    'Jamie Rose',
    'Benjamin Dawson',
    'Natasha Allison',
    'Mike Williamson',
],
    'json': {
    'name': 'Daniel Martinez',
    'address': '4038 Tammy Fields Suite 668\nMillerview, TX 48229',
},
    'key24715': 'value87827',
    'key80096': 'value60119',
    'key19224': 'value98005',
    'key30956': 'value93992',
    'key97321': 'value25264',
    'key24435': 'value81663',
    'key56658': 'value81599',
    'key90809': 'value67921',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Richard Alexander',
    'address': '200 Anna Inlet Suite 532\nNorth Josephstad, MT 17811',
    'text': 'Several hair during. Her sound when east put personal cover. Remember subject husband series know support.',
    'email': 'kprice@example.com',
    'phone_number': '001-567-326-6334x41858',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Mendoza',
    'Megan Nash',
    'Dean Calhoun',
    'Curtis Nguyen',
    'Anthony Bailey',
    'Carlos Jackson',
    'David Williams',
    'Courtney Medina',
],
    'json': {
    'name': 'Seth Smith',
    'address': '92677 Thornton Pines Suite 839\nNorth Patrickview, KS 00782',
},
    'key88475': 'value65691',
    'key85106': 'value89789',
    'key98912': 'value92739',
    'key2344': 'value4185',
    'key81711': 'value27467',
    'key16594': 'value43593',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Brian Cooper',
    'address': '35196 Webb Lodge\nEast Ronaldchester, MP 21822',
    'text': 'Event sing total industry matter bar. Piece Congress address American dream. Course third suffer its kind lawyer pull.\nRace be baby often clearly.',
    'email': 'michael41@example.org',
    'phone_number': '001-892-699-5262',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Dorsey',
    'Alexander Brown',
    'Joann Baker MD',
],
    'json': {
    'name': 'Walter Scott',
    'address': '9492 Beth Stravenue\nRosston, WV 06786',
},
    'key30189': 'value19969',
    'key9862': 'value670',
    'key64803': 'value38901',
    'key64159': 'value46175',
    'key87273': 'value24274',
    'key13753': 'value34566',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Leah Ballard',
    'address': '5192 Alan Highway Apt. 054\nNunezfort, MT 75391',
    'text': 'Four Republican money suddenly own society real possible. Care class born condition order.\nCoach speech guy. Same year card mission surface least relate.',
    'email': 'brenda43@example.org',
    'phone_number': '(809)547-1048x8219',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mallory Reid',
    'Brett Keller',
    'Elizabeth Hardy',
],
    'json': {
    'name': 'Tiffany Quinn',
    'address': '37855 Jackson Valleys\nPort Johnnyland, NH 74003',
},
    'key90033': 'value84005',
    'key96589': 'value34354',
    'key7997': 'value84193',
    'key5733': 'value73831',
    'key8084': 'value22025',
    'key89258': 'value50153',
    'key54828': 'value29317',
    'key17278': 'value96950',
    'key21964': 'value14451',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Maria Thompson',
    'address': '374 Travis Avenue Apt. 434\nPort Martin, WY 26472',
    'text': 'Culture picture couple off.\nSing son would out contain where wear head. Media paper when. First total Mr example.',
    'email': 'darlenesullivan@example.com',
    'phone_number': '254.484.0304x809',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Hanson',
    'Victoria Kelly',
    'Monica Wilson',
    'Michael Weaver',
    'Chase Duncan',
    'Angel Murphy',
    'Anne Bell',
],
    'json': {
    'name': 'Scott Koch',
    'address': '7957 Bradford Ridge Suite 475\nDunntown, AZ 35915',
},
    'key52108': 'value17469',
    'key38866': 'value67912',
    'key84541': 'value64314',
    'key68662': 'value32046',
    'key1890': 'value62853',
    'key31264': 'value84288',
    'key20403': 'value94171',
    'key40724': 'value3292',
    'key7059': 'value40836',
    'key79614': 'value23589',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Crystal Smith',
    'address': '10451 Whitney Port\nLake Micheleland, NJ 25820',
    'text': 'Very stand last industry until. Book audience me measure manage against wind.',
    'email': 'scott41@example.org',
    'phone_number': '(686)562-1504x84452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Yvonne Foster',
    'Derrick Mahoney',
    'Donna Howard',
],
    'json': {
    'name': 'Dustin Yates',
    'address': '9117 Rachel Inlet Apt. 777\nTaylorburgh, ND 17829',
},
    'key22479': 'value97025',
    'key49388': 'value16585',
    'key78426': 'value63457',
    'key55978': 'value68419',
    'key20107': 'value83017',
    'key53730': 'value63049',
    'key52775': 'value71538',
    'key19855': 'value59351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Lauren Porter',
    'address': '0304 Elizabeth Crest Apt. 072\nEast Jason, IA 15405',
    'text': 'Water religious maybe yet. Example art some discussion. Partner successful book table these.\nOpportunity them century bit already. Industry share rock particular.',
    'email': 'bowensheila@example.com',
    'phone_number': '463-679-5970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Ball',
    'Melissa Harris',
],
    'json': {
    'name': 'Taylor Russo',
    'address': '7582 Jared Lodge\nColemanberg, VA 49327',
},
    'key21781': 'value3621',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Chelsea Warren',
    'address': '9052 Smith Crossroad Suite 467\nRobertburgh, NJ 70158',
    'text': 'Hand possible interest fish while you already.\nTrip message likely national father. Lay including huge smile. Happen stay light true.',
    'email': 'stevenschristine@example.com',
    'phone_number': '807-356-3693x9363',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Martinez',
    'James Morris',
    'Dylan Smith',
    'Jacob Levy',
    'Joanne Lopez',
    'Dr. Brittney Lee',
    'Kelly Stout',
    'Robin Reyes',
    'John Wheeler',
],
    'json': {
    'name': 'Andrew Mckenzie',
    'address': '2277 Taylor Dam\nFeliciaborough, AK 94382',
},
    'key50277': 'value72097',
    'key59787': 'value59987',
    'key99437': 'value74451',
    'key38690': 'value62161',
    'key58450': 'value34446',
    'key84463': 'value4875',
    'key44151': 'value17678',
    'key26936': 'value13191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'David Mccullough',
    'address': '5412 Santiago Divide\nCarlosbury, OK 96074',
    'text': 'Just success remain wife interview. Hundred daughter debate final within affect method all. Me edge rock begin blood national much movie.',
    'email': 'tmiller@example.com',
    'phone_number': '(442)735-8343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Diaz',
    'Catherine Hill',
    'Alyssa Sanders',
    'Andrea Miller',
    'Crystal Harris',
    'Stanley Jones',
    'Andrea Powers',
    'Elizabeth Tran',
],
    'json': {
    'name': 'Edwin Johnson',
    'address': '4413 Angela Station Suite 350\nGrantview, LA 30662',
},
    'key16419': 'value89013',
    'key21779': 'value57821',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Kathleen Jones',
    'address': '531 Sean Plaza\nScottmouth, MT 41218',
    'text': 'With sport practice generation friend vote. Computer buy teach week lay third.\nEven question threat billion my. Fast wait fight officer approach. Option by quite.',
    'email': 'cantrellmichael@example.org',
    'phone_number': '621.508.3835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jack Martin',
],
    'json': {
    'name': 'Samantha Wilson',
    'address': '560 Stewart Drive\nStephenland, AR 82354',
},
    'key79710': 'value49399',
    'key81909': 'value91842',
    'key83812': 'value1491',
    'key98057': 'value24650',
    'key64817': 'value5971',
    'key25726': 'value72856',
    'key62402': 'value26842',
    'key115': 'value27809',
    'key26102': 'value21493',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Sherry Krueger',
    'address': '730 Nicholas Mall Apt. 277\nJennifertown, FL 69106',
    'text': 'Fact call own action together hour yard. Back person decision garden. Catch training outside simple technology change staff.\nFirst statement mind series writer me.',
    'email': 'jessicayoung@example.org',
    'phone_number': '001-423-510-8787',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Paige Howard PhD',
    'Kelly Leach',
],
    'json': {
    'name': 'Carla Williams DDS',
    'address': '767 Robert Rue\nNorriston, MN 12907',
},
    'key4499': 'value63791',
    'key72867': 'value71231',
    'key61552': 'value75868',
    'key89790': 'value69599',
    'key95038': 'value78276',
    'key88282': 'value45123',
    'key31515': 'value33196',
    'key42067': 'value81984',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'David Oneal',
    'address': '34804 Watkins Port\nYvettetown, WV 35289',
    'text': 'Edge which family available. Show cause home strong per group.\nMeet nearly management act bit season open. Miss wait that maintain ahead.\nEight begin tell small. Particularly well become.',
    'email': 'vballard@example.com',
    'phone_number': '+1-687-353-0176x707',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Paul Cochran',
],
    'json': {
    'name': 'Alyssa Whitehead',
    'address': '85809 Kathryn Course\nWest Michaelstad, NV 24060',
},
    'key26671': 'value25335',
    'key78778': 'value57893',
    'key78812': 'value24826',
    'key94812': 'value86437',
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
    'RequestId': '6e9ee4f8-62f1-11f0-a0ec-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_40_839314FrFbeQbf',
    'filter': '10+20 <= uid < 20+30',
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
    'RequestId': '6f3e5874-62f1-11f0-ba63-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_40_839314FrFbeQbf',
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
    'RequestId': '67e82a59-62f1-11f0-a3ec-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_35_40_839314FrFbeQbf',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-10+20 <= uid < 20+30]_1752744954.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrue1020Uid20301752744954Json()
    test.run_tests()
