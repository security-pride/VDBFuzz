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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-2]_1752744174_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-2]_1752744174.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl3210021752744174Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-2]_1752744174.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-2]_1752744174.json"
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
    'RequestId': '9e2ef628-62ef-11f0-bcf2-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_52_906772ZrPxLgqT',
    'dimension': 32,
    'primaryField': 'url',
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
    'RequestId': '9e51548d-62ef-11f0-bbe6-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_52_906772ZrPxLgqT',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Jennifer Miller',
    'address': '782 Walton Cliff\nEast Michael, MP 60175',
    'text': 'Accept cold network front while foot. White question blue.\nAppear trouble rule room right. Laugh measure military hope fund.',
    'email': 'dfields@example.org',
    'phone_number': '294-422-9072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Miranda',
    'Benjamin Bonilla',
],
    'json': {
    'name': 'Samuel Russell',
    'address': '78540 Patrick Groves\nDylanborough, MT 74305',
},
    'key94411': 'value54193',
    'key38249': 'value20745',
    'key71289': 'value75756',
    'key44429': 'value44509',
    'key51294': 'value48081',
    'key80357': 'value67435',
    'key43655': 'value13150',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Tony Hill',
    'address': '075 Christine Extension\nTaylormouth, AS 61684',
    'text': 'Must deal candidate include. Star minute where side ten allow.\nName street big know themselves head. Phone approach improve size Republican. Option television believe relate hot.',
    'email': 'turnertiffany@example.com',
    'phone_number': '363.553.4104x0155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Bennett',
    'Wendy Reid',
    'Carolyn Barr',
    'Jonathan Clark',
],
    'json': {
    'name': 'Ashley Nelson',
    'address': 'PSC 0221, Box 2359\nAPO AP 90360',
},
    'key22626': 'value34068',
    'key87429': 'value77158',
    'key4332': 'value66372',
    'key41663': 'value17594',
    'key36837': 'value1552',
    'key16218': 'value91069',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Jennifer Barton',
    'address': '31424 Bond Grove Suite 750\nWest Stephanie, AZ 23614',
    'text': 'Respond recent somebody several contain child scene. Apply it continue road she woman.\nRealize can kid himself kid but. Air power national suggest development cup.',
    'email': 'dhodges@example.com',
    'phone_number': '660.280.4814x5983',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Thompson',
    'Wesley Lara',
    'Joyce Dougherty',
    'Barbara Jennings',
    'Benjamin Williams',
    'Janice Mccoy',
    'Brooke Taylor',
],
    'json': {
    'name': 'Brett Carrillo',
    'address': '015 Ross Bypass Suite 889\nKylemouth, VA 14518',
},
    'key80092': 'value37165',
    'key68402': 'value18858',
    'key89279': 'value75721',
    'key35004': 'value5016',
    'key42629': 'value18165',
    'key2746': 'value8456',
    'key18215': 'value18540',
    'key55585': 'value95638',
    'key84594': 'value23424',
    'key49483': 'value9163',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Catherine Reynolds',
    'address': '86775 Claire Curve\nCarterhaven, SC 31838',
    'text': 'Building pretty dark. Manager on western crime. Land cultural sell letter purpose.',
    'email': 'benjaminrowe@example.com',
    'phone_number': '001-611-382-2925x202',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Karen Freeman',
    'Michelle Williams',
    'Tyler Manning',
    'Teresa Serrano',
],
    'json': {
    'name': 'Kevin Krause',
    'address': '88305 Parker Lakes Apt. 511\nLake Zachary, AS 20687',
},
    'key23581': 'value90066',
    'key30800': 'value79776',
    'key28914': 'value46338',
    'key65331': 'value10796',
    'key35309': 'value13735',
    'key85435': 'value39834',
    'key50176': 'value30387',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Randall Dixon',
    'address': '2460 Fleming Pike\nLake Susanmouth, PA 79600',
    'text': 'Whole interest thing. Person support today. Wind standard plant edge.\nAlways education conference network organization director hospital meet. Environmental six man lot.',
    'email': 'imelton@example.com',
    'phone_number': '460.209.8587x656',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Chase Rivera',
    'Daniel Brennan',
    'Tony Weaver',
    'Michael Mitchell',
    'Alison Brooks',
    'Benjamin Jones',
    'Christie Parrish',
    'Nathan Jenkins',
    'Lance Clark',
],
    'json': {
    'name': 'Charles Terry',
    'address': 'PSC 0517, Box 6902\nAPO AE 49181',
},
    'key62021': 'value88955',
    'key86740': 'value54149',
    'key97791': 'value85741',
    'key28201': 'value18885',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Douglas Holloway',
    'address': '84260 Phillips Forks Suite 182\nGarciahaven, OR 76630',
    'text': 'Source often and capital. Or wrong language marriage. Dinner ago drug mission surface. Growth early coach young.',
    'email': 'wsmith@example.com',
    'phone_number': '(367)201-9612',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Carol Roy',
    'Amanda Brown',
    'Peter Morgan',
    'Jennifer Reid',
    'Nathan Miller',
    'Joseph Bell',
    'Steven Diaz',
    'Dr. Brandon Charles MD',
    'Brandon Sweeney',
    'Samuel Hughes',
],
    'json': {
    'name': 'Frank Curry',
    'address': '033 Timothy Grove Apt. 941\nMcguirefort, AK 66272',
},
    'key76683': 'value83209',
    'key68879': 'value16294',
    'key42774': 'value96519',
    'key6927': 'value89584',
    'key48496': 'value16729',
    'key21934': 'value29886',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'John Randolph',
    'address': '178 Christopher Spring Suite 918\nGreggfurt, VA 04228',
    'text': 'Less key alone better peace student light. Suggest beat choice ready program almost. Run institution teacher top ahead fund school board.',
    'email': 'joshua36@example.net',
    'phone_number': '+1-647-542-0562x33578',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Welch',
    'Jasmine Poole',
],
    'json': {
    'name': 'Loretta Sosa',
    'address': 'USCGC Johnston\nFPO AE 64412',
},
    'key46014': 'value60723',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Shannon Bonilla',
    'address': '1188 Jennifer Motorway Apt. 929\nMorrisonfurt, HI 05926',
    'text': 'Write according despite public need. Almost low even deep. Somebody some organization head more issue.\nAmong prepare third try relationship cause.',
    'email': 'osmith@example.net',
    'phone_number': '(543)579-3591x8918',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Brown',
    'Courtney Hart',
    'Tanya Owen',
    'Jessica Sullivan',
    'Stephanie Prince',
    'Sean Hughes',
    'Cole Fleming',
],
    'json': {
    'name': 'Jessica Duffy',
    'address': '055 Gabriel Burgs\nEast Danielhaven, ME 77484',
},
    'key83957': 'value69611',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Taylor Elliott',
    'address': '836 Richard Courts\nPort Kevinfurt, IA 12832',
    'text': 'Maybe much before it myself. Article manage seat pick decision prove consider. Under every hour market.\nStudy him want wear need only. See drop determine bed military. We local opportunity second.',
    'email': 'ashley30@example.net',
    'phone_number': '533-955-8415x0414',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amy Davis',
    'Oscar Gray',
    'Michelle Gonzalez',
    'Kristina Hall',
    'Victoria Montes',
],
    'json': {
    'name': 'Amanda Shaw',
    'address': '467 Amy Points Apt. 990\nBretttown, SD 20991',
},
    'key50537': 'value21156',
    'key74113': 'value22085',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Joann Shaw',
    'address': '4727 Brandy Center Suite 416\nEast Jillian, AR 36953',
    'text': 'Beyond environment down describe no family perhaps. Mission old include fund.',
    'email': 'greeneholly@example.org',
    'phone_number': '652.691.5782x11773',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Shane Weaver',
    'Erin Thompson',
    'Manuel Brown',
    'Monique Johnson',
    'Tonya Marquez',
    'Patrick Knight',
    'Richard Daniel',
    'Steven Mathis',
    'David Salinas',
    'Monica Harris',
],
    'json': {
    'name': 'George Zimmerman',
    'address': '877 Heather Neck Apt. 131\nMaryfort, NY 68217',
},
    'key9061': 'value79333',
    'key48200': 'value92741',
    'key54495': 'value50774',
    'key5577': 'value59948',
    'key61584': 'value11918',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Henry Hall',
    'address': 'USS Skinner\nFPO AE 91174',
    'text': 'Community serve why. Worker citizen child want. Sit deep practice goal pretty.\nBack more your record agent spend card. Former cup world stand number own.',
    'email': 'eric17@example.org',
    'phone_number': '001-838-738-7662x364',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Derek Craig',
    'Micheal White',
    'Brandon Jones',
    'David Wilson',
    'Kimberly Cordova',
    'Troy Rogers',
],
    'json': {
    'name': 'Vickie Mayer',
    'address': '10567 Ward Mews\nNorth Kelseyhaven, IN 97609',
},
    'key24064': 'value31368',
    'key12842': 'value60444',
    'key59671': 'value23556',
    'key83683': 'value10704',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Mark Bishop',
    'address': '64216 James Station Apt. 683\nNguyenside, CA 91956',
    'text': 'Money statement effort few different somebody candidate. On above small throw.\nSkill hot or subject. Someone executive my prevent marriage nice know. Travel soon themselves high.',
    'email': 'etaylor@example.com',
    'phone_number': '666.547.5897x529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Cunningham',
    'Valerie Buckley',
    'Gail Vazquez',
    'Julie Murphy',
    'Martha Castillo',
    'Robert Williams',
    'Paul Ramirez',
    'Keith Davis',
    'Daniel Banks',
],
    'json': {
    'name': 'Maurice Morton',
    'address': 'USCGC Norton\nFPO AE 64145',
},
    'key26227': 'value78913',
    'key22953': 'value8721',
    'key21348': 'value18427',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Marie Roberts',
    'address': '796 Wells Port Apt. 802\nMorrisbury, CO 51943',
    'text': 'If art north pick. Base fill country relationship parent.\nCenter network mention increase quickly his. Street light now.',
    'email': 'susanmelendez@example.com',
    'phone_number': '895-558-4771x2476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Lin',
    'April Smith',
    'Bryan Grant',
    'Jennifer Roth',
    'Michelle Foster',
    'Jennifer Lee DDS',
    'Maria Cuevas',
    'Jeffrey Dominguez',
    'Jason Pacheco',
    'Brenda Walker',
],
    'json': {
    'name': 'Peggy Solis',
    'address': '770 Trevor Brooks Suite 431\nNew Christina, PA 96213',
},
    'key7206': 'value38486',
    'key91080': 'value65003',
    'key74394': 'value37566',
    'key99367': 'value88826',
    'key77453': 'value90789',
    'key51305': 'value38228',
    'key15622': 'value35545',
    'key58411': 'value85020',
    'key64298': 'value338',
    'key68523': 'value41311',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Levi Shaffer',
    'address': '9400 Alexandra Ramp Apt. 355\nNorth Amber, MA 36193',
    'text': 'Return them partner foreign else raise. Million remain Republican evidence.\nProject machine until southern face.',
    'email': 'jenniferhill@example.org',
    'phone_number': '(670)422-4557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jason Olson',
    'Angela Cook',
    'Judy Short',
    'Andrea Shah',
    'Austin Smith',
    'Lawrence Gallagher',
    'Cheryl Hamilton',
    'Tracy Edwards',
    'Samuel Shea',
],
    'json': {
    'name': 'Dylan Davis',
    'address': '2308 Willis Landing\nJodibury, NV 72481',
},
    'key24275': 'value20897',
    'key36607': 'value980',
    'key79973': 'value94110',
    'key28943': 'value30296',
    'key78677': 'value1032',
    'key1156': 'value16189',
    'key34516': 'value24104',
    'key27844': 'value56339',
    'key97863': 'value52654',
    'key43343': 'value63041',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Katie Sims',
    'address': '426 Daniel Prairie Apt. 332\nWest Melissaland, WY 62939',
    'text': 'Ok line along which hard. Card relate goal change process already nature which.\nAmerican hope whether after reflect fall. Coach send present likely. Remember success against doctor.',
    'email': 'jeremylawson@example.com',
    'phone_number': '(467)262-1023x292',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tamara Williams',
    'Heidi Bates',
],
    'json': {
    'name': 'Mary Schwartz',
    'address': 'PSC 9303, Box 0394\nAPO AA 45388',
},
    'key58390': 'value4216',
    'key79818': 'value81081',
    'key79506': 'value53149',
    'key42599': 'value61405',
    'key47587': 'value22065',
    'key68140': 'value61609',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Heather Smith',
    'address': '59483 Massey Shore Suite 898\nRobynport, MN 42749',
    'text': 'Five notice she by party trial. Agree section no American.\nElse plant short fish where class. Hold inside similar painting.\nBetter talk weight worker southern. Require good trial collection worker.',
    'email': 'perryrobin@example.net',
    'phone_number': '001-553-955-8356',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Eric Rogers',
    'Christopher Guerrero',
    'Megan Patterson',
    'Charles Anderson',
    'Dillon Collins',
    'Anthony Black',
],
    'json': {
    'name': 'Curtis Williams',
    'address': '6806 Theresa Tunnel Suite 322\nJamesport, VA 31428',
},
    'key81650': 'value7878',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Vincent Pierce',
    'address': '9554 Elizabeth Island Apt. 599\nWattstown, MI 89107',
    'text': 'However throughout whatever information agree smile view. Between special send herself dark budget food. Western business main.',
    'email': 'jenningsthomas@example.org',
    'phone_number': '001-545-733-8348',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Adams',
    'Edward Romero',
],
    'json': {
    'name': 'Garrett Johnson',
    'address': '49005 Williams Junctions\nPort Jacobhaven, SC 65405',
},
    'key84711': 'value56573',
    'key18962': 'value71105',
    'key31778': 'value80655',
    'key56657': 'value90457',
    'key21049': 'value29516',
    'key95768': 'value88571',
    'key58848': 'value1784',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Tanya Powell',
    'address': '99052 Bennett Crossing Apt. 245\nSeanstad, NY 09746',
    'text': 'Week air society be hotel store billion. Perhaps million wall song American wrong finish. Growth let record dinner. Security range ball six.\nAgree quickly parent inside final.',
    'email': 'adam73@example.net',
    'phone_number': '+1-330-665-8607x196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Turner',
    'Jasmine Barnett',
    'Larry Padilla',
    'Kim Sims',
    'Melissa Andersen',
],
    'json': {
    'name': 'Jose Lindsey',
    'address': '1331 Colleen Harbors\nSouth Saraton, CO 45779',
},
    'key25952': 'value22572',
    'key15325': 'value77536',
    'key1627': 'value62552',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Katrina Mcdonald',
    'address': '591 Tony Springs Apt. 674\nWest Alanmouth, VA 85265',
    'text': 'Agent language fly language parent. Drop beat run attorney both time heart.',
    'email': 'paul24@example.net',
    'phone_number': '503.997.6697x1836',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ian Alexander',
    'David Lopez',
],
    'json': {
    'name': 'Lori Martinez',
    'address': '2310 Johnson Walk Apt. 206\nLoriville, ND 67225',
},
    'key75087': 'value86207',
    'key9373': 'value76815',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Casey Anderson',
    'address': '513 Adams Fords\nLake Alicia, TX 53585',
    'text': 'Sign too bag health understand behavior try. Beyond culture structure. Improve forward note answer.\nYes child film apply room.',
    'email': 'lucas04@example.com',
    'phone_number': '249.997.4599',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kaitlyn Kemp',
],
    'json': {
    'name': 'Michael Graham',
    'address': '9933 Hopkins Curve\nLake Meredith, CT 52216',
},
    'key24997': 'value64542',
    'key34225': 'value99454',
    'key3208': 'value61677',
    'key69087': 'value54660',
    'key55563': 'value43714',
    'key90845': 'value99403',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Kathryn Morgan',
    'address': '92364 Eric Harbors Apt. 614\nCarolyntown, NJ 41630',
    'text': 'Stop friend product show adult. Involve factor billion control over same individual. Per a which growth relate to eye. Security support wife factor.',
    'email': 'pagekeith@example.net',
    'phone_number': '001-228-584-5346x7085',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Eric Oneill',
    'Barbara Neal',
    'Christine Stephens',
    'Daniel Ortega',
    'David Carr',
    'Linda Johnston',
    'Clinton Jackson',
    'Brandon Rogers',
],
    'json': {
    'name': 'Ann Wright',
    'address': '914 Michael Points\nWest Emily, MP 23431',
},
    'key20896': 'value7765',
    'key4632': 'value79472',
    'key65165': 'value22782',
    'key17831': 'value53944',
    'key5369': 'value83398',
    'key41741': 'value407',
    'key69107': 'value48279',
    'key48229': 'value71578',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Debbie Johnson',
    'address': '771 Daniel Park\nRogersside, MP 51726',
    'text': 'His particular American especially. Live personal source various. Allow several them next court wish kitchen radio.\nBudget politics drug kid argue professional through.',
    'email': 'traceybrown@example.com',
    'phone_number': '704.964.0336x9560',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Norman Werner',
    'John Crane',
    'Courtney Morgan',
    'Peter Adams',
    'Rhonda Torres',
    'James Bridges',
    'Taylor Martinez',
    'David White',
],
    'json': {
    'name': 'Greg Gonzalez',
    'address': '285 Steven Village Suite 495\nSouth Michelefort, FM 02675',
},
    'key33137': 'value45550',
    'key48438': 'value71875',
    'key78439': 'value83557',
    'key24': 'value19189',
    'key58590': 'value71356',
    'key38734': 'value46827',
    'key75882': 'value10354',
    'key98765': 'value11142',
    'key5235': 'value35282',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Joseph Glover',
    'address': '84911 Thomas Drives Suite 387\nBryantfort, OH 94484',
    'text': 'Chair reason series quite daughter.\nBecause say their. Performance result be attention something Democrat ten.\nEffort central help hand court anyone southern. Stand radio together final cultural.',
    'email': 'williamsontravis@example.org',
    'phone_number': '7016614031',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Mccormick',
    'Sarah Vasquez',
    'Matthew Mccarthy',
    'Sara Jones',
    'Angela Diaz',
    'Zachary Fritz',
    'David Hawkins',
    'Crystal Russo',
    'Elizabeth Garrett',
],
    'json': {
    'name': 'Diane Villa',
    'address': '74936 Aguilar Centers\nAprilhaven, ND 20827',
},
    'key15740': 'value4715',
    'key42455': 'value21721',
    'key60148': 'value67588',
    'key6675': 'value98955',
    'key44442': 'value46744',
    'key99735': 'value3402',
    'key34442': 'value99471',
    'key16652': 'value29169',
    'key99694': 'value69918',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Leonard Mitchell',
    'address': '447 Mitchell Ford Suite 338\nLawsonbury, OR 55122',
    'text': 'Others investment decide heavy. Your rule industry address.\nLong democratic traditional up. Seek series door smile. Help early cell.',
    'email': 'tgordon@example.net',
    'phone_number': '(561)431-6458x796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Derek Carey',
    'Mark Jordan',
    'Richard Carpenter',
],
    'json': {
    'name': 'Ronnie King',
    'address': '266 Parker Field Apt. 276\nPrattshire, GU 26806',
},
    'key39150': 'value84447',
    'key69339': 'value8857',
    'key35541': 'value34317',
    'key44068': 'value5201',
    'key36062': 'value23924',
    'key10879': 'value46921',
    'key56693': 'value20887',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Shelley Espinoza',
    'address': '170 Todd Ridge Apt. 365\nChristianmouth, AZ 48550',
    'text': 'Age institution population apply after approach size.\nOperation guess teach become stock throughout. Try sure another development.',
    'email': 'chad43@example.com',
    'phone_number': '985-468-9405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jillian Dixon',
    'Jacob Barajas',
    'Rachel Richardson',
    'Mr. Joseph Cox',
    'Holly Rogers',
    'James Clements',
    'Brianna Robinson',
    'Ann Atkinson',
    'Ethan Perry',
    'Tammy Ross',
],
    'json': {
    'name': 'Alexis Mendoza',
    'address': '975 Christina Mission\nNorth Bryan, NY 75014',
},
    'key43585': 'value80700',
    'key94012': 'value23015',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Patricia Schwartz',
    'address': '769 Leonard Walks Apt. 730\nPort Eric, NV 02587',
    'text': 'Agreement sort detail other concern media and. Anything city since big. Letter mean state believe wonder president may.\nCourt media card. Win modern cultural particularly share.',
    'email': 'samanthacantu@example.com',
    'phone_number': '+1-397-627-7203x98594',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brendan Reyes',
    'Michele Williams',
    'Gary Smith',
    'Dwayne Hawkins',
    'Nicholas Willis',
    'Tara Flynn',
],
    'json': {
    'name': 'Christopher Phillips',
    'address': '5187 Samantha Creek Suite 115\nSouth Cody, OK 89213',
},
    'key63513': 'value29645',
    'key76677': 'value3343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Robert Meyer PhD',
    'address': '45659 Collins Crest\nNew Sabrinachester, IN 17187',
    'text': 'Game current thing serve anyone. Kid idea paper deal push center.\nFormer power happen. Capital likely staff no find week. Wide allow history so.',
    'email': 'joneslinda@example.com',
    'phone_number': '(751)665-9168',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Martinez',
    'Wendy Schneider',
    'Amy Taylor',
],
    'json': {
    'name': 'Kathleen Alvarez',
    'address': '176 Jordan Mill Apt. 360\nPort Katherine, WI 96907',
},
    'key44607': 'value92745',
    'key3732': 'value68675',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Michael Black',
    'address': '55177 Wallace Lodge Suite 834\nEast Christinamouth, TN 46465',
    'text': 'Everybody red just sometimes especially push best. Building market series wind. Over scene future huge its.',
    'email': 'dcox@example.com',
    'phone_number': '468.601.7002',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Whitney Howard MD',
    'Olivia Hale',
    'Spencer Chavez',
    'David Ramsey',
    'Joshua Blake',
    'Michael Abbott',
],
    'json': {
    'name': 'Catherine Bennett',
    'address': '480 Karen Locks Apt. 329\nNew Karen, MS 73430',
},
    'key18626': 'value66441',
    'key88112': 'value82352',
    'key60490': 'value309',
    'key75770': 'value44025',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Chelsea Little',
    'address': '607 Charles Streets\nSantosfurt, AK 86134',
    'text': 'Capital star upon network information. Goal everything cultural way situation small news table. State need employee across.',
    'email': 'sherri45@example.com',
    'phone_number': '001-427-661-4843x23725',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Eddie Ingram',
    'Bryce White',
    'April Perez',
    'James Williams',
    'Deborah Harris',
    'Brett Garcia',
    'Joshua Hall',
    'Rachel Kelley',
    'Lori Lynch',
    'Steven Fisher',
],
    'json': {
    'name': 'Robert Ford',
    'address': '94266 Whitaker Parkways\nMichaelton, PA 23403',
},
    'key68906': 'value43704',
    'key36625': 'value66096',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Patricia Smith',
    'address': '367 Derrick Shores Apt. 022\nChristianchester, TX 71634',
    'text': 'Once country just detail. But sell unit care.\nSingle share field get. Drop talk girl six wonder.\nSame what person until Republican author recently before. Source page hundred way rule bed manager.',
    'email': 'xcaldwell@example.org',
    'phone_number': '346-718-8445x4450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Jill Arroyo',
    'Kathleen Riddle',
    'Xavier Lopez',
    'Lisa Warren',
    'Gina Davis',
    'Sara Black DDS',
    'Mary Davis',
    'Eric Bishop',
    'Richard Hanson',
    'Benjamin Parker',
],
    'json': {
    'name': 'Joseph Davis',
    'address': '426 Kimberly Ferry\nSouth Christopherland, LA 07530',
},
    'key81603': 'value35303',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Alicia Roberts',
    'address': '2634 Mallory Hollow Suite 089\nRoseton, MA 72574',
    'text': 'Opportunity your ever decade score field. Nearly how move than series student want.\nFive successful her term size particularly page bar. Step what add. Anything dark scientist.',
    'email': 'andersondana@example.com',
    'phone_number': '(412)478-6268x599',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'David Harris',
    'Jennifer Francis',
    'Anna Adams',
    'Howard Moon',
    'John Montoya',
    'John Garrett',
    'Sherry Larsen',
    'Vicki Jordan',
],
    'json': {
    'name': 'Reginald Rodriguez',
    'address': '75202 Mary Way\nChambersshire, ND 42393',
},
    'key86644': 'value84371',
    'key22466': 'value29007',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Seth Hensley',
    'address': '711 Anna Island\nMendozashire, DE 41892',
    'text': 'Learn beyond record them see. Four purpose could owner.\nPoor cut yet floor always able. That federal better event out nearly.\nClear far recognize group age across area. Go chance star responsibility.',
    'email': 'acevedolaura@example.org',
    'phone_number': '596.449.9350x27721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'William Snow',
    'Samantha Stevenson',
    'Jennifer Pitts',
    'Karen Ochoa',
    'Katelyn Little',
],
    'json': {
    'name': 'Mark Moore',
    'address': 'PSC 3226, Box 3595\nAPO AE 49430',
},
    'key19726': 'value70265',
    'key42166': 'value96182',
    'key89514': 'value42340',
    'key59920': 'value77498',
    'key63807': 'value40896',
    'key64556': 'value43947',
    'key64301': 'value40134',
    'key47111': 'value18120',
    'key12431': 'value51722',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Samuel Huynh',
    'address': '28087 Tran Cape Suite 096\nPort Kathleen, SC 48369',
    'text': 'Leg tree spring society hundred. Act difficult concern listen without certain finally. Painting national officer me you your.\nAlone more assume action human. Woman all economy fact enter measure.',
    'email': 'sarahholt@example.com',
    'phone_number': '762-659-6300',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Reynolds',
],
    'json': {
    'name': 'Lisa Robertson',
    'address': '487 Taylor Islands Apt. 460\nGutierrezton, FL 02732',
},
    'key16664': 'value17841',
    'key28316': 'value51285',
    'key7410': 'value18074',
    'key65524': 'value23998',
    'key88222': 'value23162',
    'key67400': 'value54763',
    'key18753': 'value31055',
    'key62116': 'value73897',
    'key83713': 'value17741',
    'key79132': 'value66806',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Alan Ramos',
    'address': 'PSC 6125, Box 1353\nAPO AP 94479',
    'text': 'Score religious light develop. Walk recognize positive table benefit car music.\nScore election stage pay. Office statement certain food together scientist.',
    'email': 'gregoryanderson@example.com',
    'phone_number': '290.851.2260x7138',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Hurst',
    'Corey Black',
    'Thomas Kelley',
],
    'json': {
    'name': 'Colleen Bradley',
    'address': '9384 Bruce Well Suite 705\nManningtown, MN 80137',
},
    'key56437': 'value12772',
    'key57047': 'value37716',
    'key23693': 'value42523',
    'key65423': 'value75659',
    'key78712': 'value70301',
    'key32501': 'value34481',
    'key27255': 'value50758',
    'key73286': 'value64430',
    'key17583': 'value91884',
    'key77457': 'value7275',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Blake Reid',
    'address': '4023 Williams Vista\nSanchezport, WA 84683',
    'text': 'Stay product music challenge such I box. Weight modern reveal so. Could agent natural attack.\nResearch statement any take road. Movement design every. Form democratic main hard stay somebody.',
    'email': 'bradleymary@example.net',
    'phone_number': '683.759.4309',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Shane Hicks',
    'Jacob Bush',
    'Ariana Meyer',
    'Christopher Crawford',
    'Jennifer Farmer',
    'Grace Mccann',
    'Melanie Nelson',
    'Dominic Lucas',
],
    'json': {
    'name': 'Kristina Alexander',
    'address': '19078 Eric Fort\nAmyton, WY 15967',
},
    'key71556': 'value7724',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Kelli Clark',
    'address': '09066 Miller Cove Suite 117\nEast Brandy, MI 78300',
    'text': 'Able quality natural glass. Actually pull draw consumer.\nStand see society me everyone. Old special wait never man grow system. Sense certainly affect simply peace account.',
    'email': 'morganjessica@example.org',
    'phone_number': '938.900.9727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Richard Mitchell',
    'Cory Macias',
    'Caleb Myers',
    'Melissa Miller',
    'Patricia Mcfarland',
    'Roberto Kennedy',
    'Brenda Ho',
    'Shaun Woodard',
    'Cheyenne Kelly',
    'Gerald Thompson',
],
    'json': {
    'name': 'Reginald George',
    'address': 'PSC 3262, Box 1383\nAPO AA 71099',
},
    'key73977': 'value19745',
    'key43684': 'value75381',
    'key14777': 'value45977',
    'key9006': 'value45518',
    'key25694': 'value48233',
    'key30501': 'value86623',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Matthew Stewart',
    'address': 'Unit 6849 Box 6439\nDPO AA 37186',
    'text': 'Song west film lead. Success they already hot region thought. By really on young believe certainly voice important.\nFirst consider bill adult us. Prevent law option learn.',
    'email': 'kendrajuarez@example.net',
    'phone_number': '+1-892-740-5976x74007',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Terry Barry',
    'Steven Hopkins',
    'Phillip Crane',
    'Jeffery Bond',
    'Vicki Richards',
    'Matthew Johnson',
    'Helen Tran',
    'Mary Gonzales',
    'Karen Garcia',
],
    'json': {
    'name': 'Marcus Lee',
    'address': 'PSC 3934, Box 5499\nAPO AA 61131',
},
    'key58549': 'value16445',
    'key81077': 'value85172',
    'key38696': 'value78079',
    'key57945': 'value2048',
    'key27694': 'value11914',
    'key43619': 'value46025',
    'key24421': 'value68023',
    'key67183': 'value73161',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Edward Burns',
    'address': '0154 Silva Junction\nFloydside, NM 92790',
    'text': 'Art sport Congress action scene describe. Factor street over size employee also. Special rule short somebody time.',
    'email': 'vbutler@example.org',
    'phone_number': '4567872920',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Charles Ochoa',
    'Amanda Santiago',
    'Eric Tate',
    'Tammy Pierce',
    'Jon Chase',
    'Paul Greene',
    'Ms. Susan Reed',
    'Adam West',
    'Tiffany Gutierrez',
],
    'json': {
    'name': 'Marvin Henson',
    'address': '79207 Timothy Grove Apt. 518\nEast Kimberly, MS 92844',
},
    'key75577': 'value90013',
    'key17995': 'value23216',
    'key10224': 'value41658',
    'key31086': 'value85691',
    'key11556': 'value42838',
    'key33463': 'value65125',
    'key84557': 'value55893',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Michael Hunt',
    'address': '1081 Stewart Walk\nScottmouth, CT 56572',
    'text': 'Area thank security street under.\nCatch democratic relationship pull. Low north compare watch successful big seek. Eight expert hair per.',
    'email': 'wrightsonya@example.com',
    'phone_number': '+1-514-898-5362x6754',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Young',
    'Ronald Martinez',
    'John Mejia',
    'Randy Villa',
],
    'json': {
    'name': 'Lynn Brown',
    'address': 'PSC 0753, Box 7956\nAPO AP 78017',
},
    'key65768': 'value66671',
    'key6047': 'value62410',
    'key37913': 'value67753',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Shannon Woods',
    'address': '743 Patrick Summit\nWest Timothy, NE 64379',
    'text': 'Quite exist employee affect produce identify he. Plan soldier cut cause company. Teacher movie alone about than fill yes lay. Several ever level open gas increase action officer.',
    'email': 'xcox@example.com',
    'phone_number': '324-786-3866',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Walker',
    'Jonathan Bates',
    'Brooke Jones',
    'Emma Thompson',
    'Veronica Osborn',
    'Rita Hill',
    'Shane Higgins',
],
    'json': {
    'name': 'Megan Williamson',
    'address': '3312 Melanie Course Apt. 219\nNorth Brittanychester, HI 85263',
},
    'key9101': 'value93890',
    'key41591': 'value47642',
    'key81886': 'value66052',
    'key12356': 'value94697',
    'key66558': 'value93393',
    'key90196': 'value41296',
    'key13580': 'value65455',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Paul Parker',
    'address': '818 Karen Knoll Suite 033\nNew Brittany, WV 04620',
    'text': 'Other care speak well up occur. Defense create art cup. Pretty enter exactly music wife responsibility offer coach.\nStreet expect notice while national. Few cause church throughout.',
    'email': 'erica76@example.org',
    'phone_number': '717-355-2546',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brenda Olsen',
    'Aaron Clark',
    'Sarah Schwartz',
    'Janet Meyer',
],
    'json': {
    'name': 'Jorge Byrd',
    'address': '03236 Downs Street Apt. 620\nBrownside, ID 67064',
},
    'key86371': 'value79434',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Ashley Martinez',
    'address': '7153 Brandy Motorway Suite 596\nSouth Margaretland, RI 89529',
    'text': 'Daughter others behind economy realize hour. Social source growth more operation. Night discover bit country.',
    'email': 'migueldelgado@example.net',
    'phone_number': '906.875.7581x2036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Barnes',
    'Billy Whitney',
    'Ronald Wood',
    'Jeff Hernandez',
],
    'json': {
    'name': 'Christine Hunt',
    'address': '19132 Shields Mill\nLake Michael, NM 98640',
},
    'key97455': 'value36555',
    'key73424': 'value12037',
    'key36232': 'value71957',
    'key19290': 'value993',
    'key13174': 'value1585',
    'key4803': 'value58946',
    'key80467': 'value8164',
    'key60231': 'value78960',
    'key11597': 'value73778',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Aaron Wolfe',
    'address': 'USS Johnson\nFPO AP 68709',
    'text': 'Change such pretty may. Than worry article when.\nMagazine suddenly cold million theory consumer. Form federal set arm ahead factor author language.',
    'email': 'curtisjohn@example.net',
    'phone_number': '001-566-631-4192',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Mckenzie',
    'Dr. Renee Chavez',
    'Dr. Elizabeth Romero',
    'Dr. Daniel Miller',
    'Kathryn Booth',
    'Erica Koch',
],
    'json': {
    'name': 'Adrian Martin',
    'address': '447 Laura Park\nJustinchester, HI 33102',
},
    'key66625': 'value8441',
    'key58429': 'value89602',
    'key50686': 'value84028',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Reginald Ortiz',
    'address': '23233 Jamie Port Apt. 243\nSouth Dennis, VI 44254',
    'text': 'School pressure close media figure response sister. Produce bank eat important she century surface cultural. Skill kind bit story personal rate.',
    'email': 'wesley51@example.net',
    'phone_number': '001-280-239-3733x441',
    'array_int_dynamic': [
    1519,
],
    'array_varchar_dynamic': [
    'Andrea Williamson',
    'Michael Moran',
    'Daniel Evans',
    'Jonathan Hanson',
],
    'json': {
    'name': 'Katie Bullock',
    'address': '8291 Joseph Springs\nFergusonland, RI 90035',
},
    'key37014': 'value83622',
    'key20917': 'value19870',
    'key7602': 'value85291',
    'key4485': 'value73783',
    'key43007': 'value63249',
    'key94448': 'value56210',
    'key3877': 'value23897',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Roy Williams',
    'address': '5340 Jay Lock Apt. 332\nSouth Carlatown, GU 25573',
    'text': 'Local hospital yeah everyone save if claim. View adult exist nothing page letter.\nAlways anyone candidate work imagine. Certainly career opportunity trial.',
    'email': 'alewis@example.net',
    'phone_number': '952-815-6541x8273',
    'array_int_dynamic': [
    55641,
],
    'array_varchar_dynamic': [
    'Alison Williams',
],
    'json': {
    'name': 'Evan Scott',
    'address': '758 Carter Cape\nRodriguezberg, SC 77812',
},
    'key81385': 'value48821',
    'key68175': 'value9570',
    'key94787': 'value34259',
    'key10193': 'value9170',
    'key17068': 'value90598',
    'key32841': 'value82451',
    'key29053': 'value37719',
    'key72056': 'value56172',
    'key80581': 'value2566',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Raymond Montgomery',
    'address': '3390 Miranda Points\nRamirezbury, NC 69534',
    'text': 'News night quality my. Against capital ok at.\nNor great project real. Girl sound main. Watch hot soldier follow despite plan cold policy. Mention catch imagine stay degree.',
    'email': 'brownlucas@example.net',
    'phone_number': '316.516.3347x973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Olson',
],
    'json': {
    'name': 'Carol Evans',
    'address': '5630 Waller Lock Apt. 809\nFeliciastad, DC 29407',
},
    'key89871': 'value19077',
    'key68257': 'value47602',
    'key33710': 'value92148',
    'key14625': 'value17370',
    'key61507': 'value8150',
    'key65213': 'value23111',
    'key65964': 'value82437',
    'key9278': 'value11147',
    'key82336': 'value55020',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Nancy Turner',
    'address': 'Unit 0958 Box 8243\nDPO AE 19613',
    'text': 'Offer recognize group then health serious but. Pm cell company.\nFocus power possible follow push raise. Including company instead southern operation.',
    'email': 'rkelly@example.org',
    'phone_number': '836-629-8715',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Martin Smith',
    'Denise Long',
],
    'json': {
    'name': 'Robert Wells',
    'address': '40796 Jason Knoll\nLake Kevin, WY 89570',
},
    'key21472': 'value7323',
    'key51984': 'value2383',
    'key17886': 'value98588',
    'key45430': 'value87721',
    'key86951': 'value8255',
    'key20377': 'value67585',
    'key42310': 'value10516',
    'key65265': 'value98142',
    'key99066': 'value505',
    'key7954': 'value3469',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Lisa Solis',
    'address': 'USS Black\nFPO AA 19540',
    'text': 'Condition today executive possible. Attention force market student operation political. Which ground entire concern visit chance require. Anyone successful player far safe.',
    'email': 'jmiller@example.net',
    'phone_number': '+1-433-241-9767x92414',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Chad Moore',
    'Jillian Moore',
    'Mary Garrett',
    'Joseph Mccormick',
    'Meghan Berry',
    'Tammy Casey',
    'Jerry Sweeney',
    'Allison Jones',
    'William Jackson',
],
    'json': {
    'name': 'James Bell',
    'address': '93719 Kenneth Streets\nWest Brianborough, WV 05790',
},
    'key39679': 'value66444',
    'key97332': 'value67420',
    'key54162': 'value45124',
    'key6016': 'value97142',
    'key50893': 'value61502',
    'key90534': 'value73965',
    'key31534': 'value71317',
    'key85043': 'value41550',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Jacob Reynolds',
    'address': '02094 Michael Harbors\nNorth Laurahaven, OK 88126',
    'text': 'Over occur white. No improve represent near marriage. Education recent million house difficult. Single fire six sea.',
    'email': 'jnorman@example.net',
    'phone_number': '(829)326-6173',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alec Sanders',
],
    'json': {
    'name': 'Robert Knight',
    'address': '4702 Wong Wells\nJonmouth, ME 21134',
},
    'key59135': 'value80739',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Jacob Valencia',
    'address': '502 Susan Islands\nNorth Mark, SC 70021',
    'text': 'Attention money miss child movement range. Industry technology than gun call actually small better.',
    'email': 'emilysanders@example.org',
    'phone_number': '5922857271',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Phelps',
    'Frank Taylor',
],
    'json': {
    'name': 'Jeffrey Brock',
    'address': '22502 Eaton Fort Suite 191\nWest Teresahaven, VT 36848',
},
    'key28650': 'value46061',
    'key21657': 'value87814',
    'key82137': 'value75665',
    'key13279': 'value44379',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Michael Hicks',
    'address': '5530 Sarah Heights Apt. 351\nSmithtown, MA 80709',
    'text': 'Conference federal threat happen ability particularly mission. Experience family anything after away three enough. Rock part yard institution.\nSeek single staff something agreement city.',
    'email': 'hannahturner@example.com',
    'phone_number': '(719)506-9257x773',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Paul Cunningham',
    'Wayne Sanchez',
    'Patricia Smith',
    'Kenneth Wright',
    'Christine Bowen',
    'Lorraine Harvey',
    'Mark Norris',
    'Jenna White',
    'Robert Garcia',
],
    'json': {
    'name': 'Jordan Becker',
    'address': '254 Blanchard Mission Apt. 849\nEast Susan, TN 86703',
},
    'key82741': 'value96556',
    'key5463': 'value87955',
    'key19571': 'value49957',
    'key94947': 'value84691',
    'key43074': 'value85403',
    'key27443': 'value47204',
    'key26480': 'value44228',
    'key21088': 'value80394',
    'key92943': 'value29446',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Jennifer Grimes',
    'address': '0602 Hector Turnpike Suite 725\nPort Michelle, AK 27874',
    'text': 'Discussion rise hair drop. Far season relate as. Write space either.\nTest message ability write. Star behind early meet fund language argue. Film method house area single again long discover.',
    'email': 'anthonyadams@example.org',
    'phone_number': '+1-594-301-3053x407',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Terrell',
],
    'json': {
    'name': 'Alexa West',
    'address': '5762 Stephens Hollow\nAngelaberg, AR 43130',
},
    'key63742': 'value93660',
    'key5582': 'value31081',
    'key35532': 'value50611',
    'key56049': 'value33815',
    'key43496': 'value93654',
    'key34820': 'value8583',
    'key56220': 'value22295',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Brittany Marshall',
    'address': '8716 Lisa Pine\nLake Donald, NE 28880',
    'text': 'Water source to order per respond understand. Prevent everything value music.\nImprove set spend material bad. Open source painting finally.',
    'email': 'ellenjackson@example.net',
    'phone_number': '600-476-4309x87804',
    'array_int_dynamic': [
    24985,
],
    'array_varchar_dynamic': [
    'Christine Dennis',
    'Bonnie Johnson',
    'Carol Perez',
    'Dale Mccoy',
    'Casey Roberts',
    'Elizabeth Ford',
],
    'json': {
    'name': 'Toni Graham',
    'address': '2059 Washington Harbor Apt. 015\nGuerreromouth, IN 74492',
},
    'key19564': 'value70590',
    'key53304': 'value82225',
    'key35151': 'value68424',
    'key46204': 'value279',
    'key84433': 'value3775',
    'key65699': 'value95805',
    'key43341': 'value43844',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Michael Arias',
    'address': '49217 Carter Shoal\nLake Meredith, NM 63491',
    'text': 'Difficult significant win five remain. Never if church floor real none. Future magazine hear interest style.',
    'email': 'andersonbrian@example.net',
    'phone_number': '276-354-5634x3869',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Emily Cook',
    'David Miller',
],
    'json': {
    'name': 'Kenneth Bullock',
    'address': '9742 Anthony Centers Suite 981\nGreeneside, WA 19250',
},
    'key18534': 'value43617',
    'key19645': 'value41487',
    'key9954': 'value80731',
    'key78676': 'value62348',
    'key75648': 'value58869',
    'key56764': 'value37836',
    'key73734': 'value71304',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Stacey Martin',
    'address': '7854 Patrick Island Suite 374\nGreenchester, VA 37071',
    'text': 'Style who tend reflect get later. Small century explain various suggest policy very beat. Beyond among provide movie behind.\nSecurity newspaper lose loss interview month. Budget from run hour.',
    'email': 'marisa38@example.net',
    'phone_number': '+1-597-974-1086x397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Shields',
    'Dawn Fox',
    'Alyssa Bailey',
    'Tara Graham',
    'Edward Adams',
    'Shannon Jimenez',
],
    'json': {
    'name': 'Darin Davis',
    'address': 'PSC 2564, Box 8455\nAPO AE 34937',
},
    'key64991': 'value67163',
    'key72320': 'value82195',
    'key33716': 'value57459',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Veronica Lane',
    'address': '494 Bailey Mountain Apt. 522\nChristopherview, FL 96400',
    'text': 'Manager natural no officer. Most full chair show produce figure himself color.\nThese during black. Idea see administration season may change fish.',
    'email': 'kimberly63@example.net',
    'phone_number': '453-740-1286',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Natalie Dudley',
    'Kevin Hicks',
    'Seth Flores',
    'Nicolas Wilson',
],
    'json': {
    'name': 'Michael Wang',
    'address': '550 Harper Springs Suite 177\nPort Laurenfurt, MP 78688',
},
    'key87166': 'value36468',
    'key40205': 'value88064',
    'key99278': 'value23694',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Dwayne Edwards',
    'address': '832 Angela Ports Apt. 634\nRobertland, IL 51206',
    'text': 'Friend its animal.\nGeneral laugh exactly top. Person teach power charge born. One trouble tree money occur church field kid.',
    'email': 'mary45@example.net',
    'phone_number': '(701)627-9686x18739',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jane Woods',
    'Jessica Patel DVM',
    'Jessica Rowe',
    'Nicole Figueroa',
    'Frank Wheeler',
    'Michael Johnson',
],
    'json': {
    'name': 'Rodney Perry',
    'address': '044 Frank Squares Suite 053\nPamelahaven, DC 75387',
},
    'key92120': 'value88606',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Jack Curry',
    'address': '747 Elizabeth Drive Apt. 165\nTheresahaven, LA 67065',
    'text': 'Who history and respond keep technology degree life. Central local necessary reality agree suggest war. Most few against here how.',
    'email': 'stefanie93@example.com',
    'phone_number': '+1-732-686-8479',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Duane Anderson',
    'Steven Roberts',
    'Kayla Oneill',
    'Susan Acosta',
    'Lisa Rush',
    'Debbie Butler',
    'Sharon Shah',
    'Christopher Mcintosh',
    'Alexis Vaughn',
    'Joshua Farrell',
],
    'json': {
    'name': 'Amy Lopez',
    'address': '5211 Jesus Road\nKelleymouth, NH 65811',
},
    'key78793': 'value79718',
    'key27075': 'value92728',
    'key53372': 'value6321',
    'key32898': 'value52271',
    'key10449': 'value85946',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Mitchell Cox',
    'address': '5789 Robert Drive Suite 824\nNew Katherine, PW 22913',
    'text': 'Yet audience after cell leave line. Little eye cultural wait well.\nTonight lot century garden role affect must. Process low let hair next bring. Fish generation campaign grow nothing out.',
    'email': 'heatherbautista@example.net',
    'phone_number': '781.910.3634x3616',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Arellano',
    'Gregory Hernandez',
    'Adam Clark',
    'Kim Foster',
    'Raymond Johnson',
    'Stephanie Wiley',
    'Kristi Brown',
    'Crystal Hughes',
],
    'json': {
    'name': 'Shannon Rodriguez',
    'address': '878 Kelly Isle Suite 648\nThomaschester, ME 73895',
},
    'key66158': 'value10068',
    'key1325': 'value37881',
    'key4003': 'value55527',
    'key6072': 'value54135',
    'key74336': 'value96503',
    'key59878': 'value14252',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'James Allen',
    'address': '203 Sherry Locks Suite 983\nSouth Michael, ND 88992',
    'text': 'Although write discover true certain pass animal inside. Well history forget social professional. World short any party paper across.',
    'email': 'nunezjohnny@example.com',
    'phone_number': '(406)606-7119x389',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Clark',
    'Michael Adams',
    'Barbara Becker',
    'Jason Schmidt',
    'Melanie Woods',
    'Nicholas Stanley',
    'Anna Garcia',
],
    'json': {
    'name': 'Sally Fuentes',
    'address': '587 Cristina Turnpike\nSouth Peggyport, NV 57679',
},
    'key96433': 'value13630',
    'key17506': 'value62391',
    'key50393': 'value85228',
    'key51763': 'value37180',
    'key37487': 'value98226',
    'key10061': 'value15198',
    'key23074': 'value42515',
    'key50194': 'value42957',
    'key92476': 'value88561',
    'key47353': 'value89352',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Victoria Rodriguez',
    'address': '451 Clark Heights\nFostershire, IN 69840',
    'text': 'Low morning local do benefit during. Certain should find make then. Theory military human machine.\nDevelop computer allow writer because wonder. Support than detail make every human hotel if.',
    'email': 'hansonmegan@example.org',
    'phone_number': '508.763.1942x1069',
    'array_int_dynamic': [
    16750,
],
    'array_varchar_dynamic': [
    'Corey White',
    'Fred Ramirez',
    'Erica Howard',
    'James Holmes',
    'James Fox',
    'Isaiah Johnson',
    'Nicole Boone',
],
    'json': {
    'name': 'Bobby Boyd',
    'address': '48251 Jefferson Mount Apt. 568\nEast Josephchester, WY 37077',
},
    'key57311': 'value59826',
    'key44350': 'value52932',
    'key90298': 'value52569',
    'key65165': 'value27698',
    'key20361': 'value42387',
    'key89003': 'value91472',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Jennifer Diaz',
    'address': '03340 Gary Gardens\nNorth Davidshire, NV 29682',
    'text': 'Financial thousand board law pay community. Trip next another feeling history carry. Different system degree allow especially.',
    'email': 'ericdavis@example.com',
    'phone_number': '3782916368',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Reed',
    'Nathaniel Nguyen',
    'Jennifer Kaiser',
    'Misty Huang',
    'Vincent Farrell',
    'Elizabeth White',
    'Ashlee Cantu',
    'Kelly Robinson',
],
    'json': {
    'name': 'Scott Chambers',
    'address': '54022 Amanda Lock\nNorth Jennifer, ND 90037',
},
    'key46922': 'value86000',
    'key35953': 'value9873',
    'key96764': 'value370',
    'key36049': 'value675',
    'key1157': 'value15291',
    'key54780': 'value52963',
    'key48601': 'value66977',
    'key47543': 'value71729',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Katherine Maxwell',
    'address': '4524 James Ridge\nNew Jeffreybury, CA 03956',
    'text': 'Material better heavy pretty down. Land bring clearly cultural dinner.\nThrow wind generation although tax dark offer purpose. Less week situation food.',
    'email': 'brandon52@example.net',
    'phone_number': '(950)430-9539',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Daisy Armstrong',
    'Mark Alvarez',
    'Jennifer Turner',
    'Benjamin Leonard',
    'Lisa Duran',
],
    'json': {
    'name': 'Elizabeth Cuevas',
    'address': 'PSC 1108, Box 6234\nAPO AE 54086',
},
    'key51066': 'value95655',
    'key94741': 'value19973',
    'key1901': 'value62557',
    'key36408': 'value1485',
    'key74296': 'value60180',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Daniel Gonzalez',
    'address': '56424 Strickland Flats\nNorth Jeremy, SC 43639',
    'text': 'Heart project accept sister if kid three risk. Send usually art push factor.\nOption research blue put billion mouth. Difference daughter wide nothing agreement dinner. Consider miss trial soldier.',
    'email': 'cmurray@example.com',
    'phone_number': '+1-850-818-7276x84221',
    'array_int_dynamic': [
    32633,
],
    'array_varchar_dynamic': [
    'Alexis Roach',
    'Karen Harris',
    'John Lucero',
    'Scott Myers',
    'Maria Gates',
    'Julie Ryan',
    'Mark Gonzalez',
    'Stacy Carpenter',
],
    'json': {
    'name': 'Robin Savage',
    'address': '8808 Rollins Club Suite 434\nNorth Kimshire, KY 05206',
},
    'key78125': 'value59052',
    'key30823': 'value22607',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Megan Rios',
    'address': '45569 Duran Point\nSamanthabury, MT 61976',
    'text': 'Development case respond cold against positive. Offer season him rock itself bit. Budget success hotel much give.\nFour TV dog loss cut. Market usually now better however pay.',
    'email': 'katelyntodd@example.com',
    'phone_number': '+1-873-557-7740x0207',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Lopez',
    'Troy Wilson',
    'Haley Chapman',
    'Kenneth Vazquez',
    'Matthew Andrews',
    'Carrie Smith',
    'David Hobbs',
    'Dawn Powell',
],
    'json': {
    'name': 'Brittany Richards',
    'address': '18877 Davis Tunnel\nLindamouth, PA 62185',
},
    'key5881': 'value42226',
    'key15834': 'value14725',
    'key93130': 'value2452',
    'key8542': 'value98838',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Crystal Lara',
    'address': '83248 Mullins Courts Suite 910\nEast Martinburgh, AK 25232',
    'text': 'Probably pass option technology approach baby field. Official need yourself blood role.\nStyle whose score too year hot.',
    'email': 'michael07@example.net',
    'phone_number': '905.705.5674x3990',
    'array_int_dynamic': [
    9879,
],
    'array_varchar_dynamic': [
    'Jose Thomas',
    'Lisa Williams',
    'Austin Little',
    'Brittany Graham',
    'Amanda Barker',
    'Stephanie Carrillo',
    'Michael Peterson',
    'Tina Reed',
],
    'json': {
    'name': 'Michael Peck',
    'address': '9130 Chapman Point Suite 291\nLake Christopher, TN 28741',
},
    'key96974': 'value9646',
    'key70686': 'value43064',
    'key90576': 'value6000',
    'key13874': 'value80674',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Hailey Glover',
    'address': '076 Gray Rue\nSouth Jillmouth, AR 52477',
    'text': 'Move method officer market. None response bank all feeling.\nMind treat court region natural week whom. Direction under couple tell. Perform nothing compare company agreement full sense see.',
    'email': 'johnsonjames@example.org',
    'phone_number': '960-447-4931x613',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Ramirez',
    'Warren Bailey',
    'Christian Rose',
    'Daisy Young',
    'Stephen Espinoza',
],
    'json': {
    'name': 'Robert Alvarez',
    'address': '7608 Dominique Track Apt. 951\nMartinstad, FL 18052',
},
    'key96966': 'value26875',
    'key31422': 'value34507',
    'key10574': 'value47422',
    'key57211': 'value96970',
    'key76230': 'value85874',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Erin Smith',
    'address': '64851 Payne Extension\nWest Denise, NC 98718',
    'text': 'He suggest site throw order benefit role do. Situation himself wonder live. Offer green hear however lay every quickly.\nScore budget often president television create.',
    'email': 'hjohnson@example.com',
    'phone_number': '871.649.6688',
    'array_int_dynamic': [
    25004,
],
    'array_varchar_dynamic': [
    'Shawn Warren',
    'Kristin English',
    'Katherine Martin',
    'Shawn Valdez',
    'Jacob Gonzalez',
    'Keith Clark DDS',
],
    'json': {
    'name': 'Edward Russell',
    'address': '75176 Jill Pines Suite 377\nKaylamouth, MT 37193',
},
    'key22835': 'value34221',
    'key69166': 'value713',
    'key74664': 'value6025',
    'key29044': 'value6137',
    'key45851': 'value11091',
    'key92483': 'value39263',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Laura Grant',
    'address': '243 Brian Plaza Apt. 223\nJenniferstad, CT 57373',
    'text': 'Art sort according do. Arrive father seven contain.\nTo discuss must energy.\nPerhaps plant low cell middle century majority. Blue military instead sit serve star cold. Wait five herself sense.',
    'email': 'marie57@example.org',
    'phone_number': '456.476.6858x0027',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Russell White',
    'Joshua Roberts',
    'Patricia Robinson',
    'Tracy Berry',
    'Matthew Estrada',
    'Daniel Davis',
    'Brian Rodriguez',
],
    'json': {
    'name': 'John Navarro',
    'address': 'Unit 1081 Box 9548\nDPO AA 84359',
},
    'key47963': 'value59466',
    'key44312': 'value69815',
    'key84991': 'value57347',
    'key68711': 'value71291',
    'key52074': 'value45600',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Gabriella Cobb',
    'address': 'Unit 6874 Box 4423\nDPO AA 65987',
    'text': 'Improve second bank office nothing. Rise particular computer effort left.',
    'email': 'william15@example.net',
    'phone_number': '+1-941-862-5267x9844',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Clark',
    'Lisa Preston',
],
    'json': {
    'name': 'Charles Franklin',
    'address': 'Unit 1597 Box 7332\nDPO AP 26735',
},
    'key87767': 'value11550',
    'key83860': 'value3173',
    'key78359': 'value3157',
    'key85660': 'value38345',
    'key57973': 'value37603',
    'key90425': 'value75927',
    'key21245': 'value9655',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Andrea Ferguson',
    'address': '45502 Chase Avenue Apt. 081\nNashstad, TX 68445',
    'text': 'Head collection certain oil business. Identify full take.\nHead green religious education particular too international. The economy evening hospital. Thought ask letter blood.',
    'email': 'timothy31@example.com',
    'phone_number': '(212)828-1720',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Michael Andrade',
    'Rachel Parker',
    'Carlos Hunt',
    'Courtney Diaz',
    'Hannah Fields',
],
    'json': {
    'name': 'Carl Smith',
    'address': '0634 Evans View Suite 841\nPort Billyton, CA 71425',
},
    'key19346': 'value86261',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Brandi Everett',
    'address': 'PSC 5577, Box 7133\nAPO AE 14370',
    'text': 'Child positive appear treat. Southern attack less will identify office. Be quickly nation such.',
    'email': 'terrirollins@example.com',
    'phone_number': '878.316.7984x2712',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl Barrera',
    'Carolyn Johnson',
    'Connor Rivers',
    'Christian Nichols',
],
    'json': {
    'name': 'Brittany Olson',
    'address': '8764 Kimberly Harbor\nLake Fernando, OH 80154',
},
    'key19632': 'value46121',
    'key36512': 'value10907',
    'key79645': 'value30800',
    'key5054': 'value80950',
    'key67007': 'value1154',
    'key97229': 'value81966',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Hannah Novak',
    'address': '2131 Walsh Turnpike\nEast Stevenville, GA 44380',
    'text': 'Put clearly and condition employee big investment. Value common back attack. Situation force look affect.',
    'email': 'kristibutler@example.org',
    'phone_number': '933-289-4873',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tony Gilbert',
    'Heather Smith',
],
    'json': {
    'name': 'Brianna Shaw',
    'address': '8337 Jonathan Walk Suite 204\nWest Mark, AK 74459',
},
    'key78180': 'value61604',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Deborah Hamilton',
    'address': 'Unit 7672 Box 7585\nDPO AE 28431',
    'text': 'Commercial seat forget shake whom program goal. Phone them rate concern house.\nRelationship sister commercial machine. Case leg discuss. Through campaign one toward interview president.',
    'email': 'psingleton@example.org',
    'phone_number': '+1-397-342-1110x719',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Carter',
    'Christina Baker',
    'Matthew Benitez',
    'Patricia Kim',
    'Michael Hernandez',
    'Megan Thomas',
    'Colleen Stevens',
],
    'json': {
    'name': 'Timothy Anderson',
    'address': '908 Brian Walks\nSouth Tina, AZ 34237',
},
    'key76941': 'value25604',
    'key44598': 'value86076',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'William Phillips',
    'address': 'USS Fields\nFPO AP 97413',
    'text': 'Rate very could difficult think blood. Receive several too.\nIdentify record school fear. Pm worker guy.\nEight structure water move character entire. More unit commercial stand whose boy seem social.',
    'email': 'marcus30@example.com',
    'phone_number': '001-627-247-2789x50073',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Phillips',
    'Daniel Wong',
    'Crystal Ward',
    'Melissa Parks',
    'Tara Galvan',
    'Maria Scott',
],
    'json': {
    'name': 'Jessica Simmons',
    'address': '1218 Smith Cliff\nJosephport, CO 98174',
},
    'key62324': 'value56949',
    'key22066': 'value45559',
    'key41517': 'value71241',
    'key4022': 'value66968',
    'key26489': 'value49430',
    'key10139': 'value45106',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Brian Farmer PhD',
    'address': '7779 Barker Summit Apt. 271\nAmbermouth, VA 48370',
    'text': 'Every wall natural manage. Large decision expert example. So hold according station dark data.\nSouthern voice cost medical wind mention arrive. Into beautiful property run education production.',
    'email': 'heather43@example.net',
    'phone_number': '+1-469-450-4663x738',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Karen Dougherty',
    'Cheryl Mercado',
    'Jason Harper',
],
    'json': {
    'name': 'Jennifer Mclaughlin',
    'address': '449 Williamson Terrace Suite 814\nWest Mariah, NC 84749',
},
    'key39846': 'value95031',
    'key12795': 'value31859',
    'key36749': 'value46502',
    'key9841': 'value47814',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Bryan Hampton',
    'address': '13496 Deborah Overpass Apt. 877\nLake Vanessafort, MA 51154',
    'text': 'Billion dream culture discover add most carry. Baby hold think might. Look sort over race real thank.',
    'email': 'justin52@example.net',
    'phone_number': '001-570-934-3977x750',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Wilson',
    'Kristen Long',
],
    'json': {
    'name': 'Barbara Stevens',
    'address': '726 Gonzales Trail Suite 193\nAnthonyton, IN 23813',
},
    'key42273': 'value49053',
    'key58383': 'value33804',
    'key99911': 'value66403',
    'key17163': 'value44170',
    'key98050': 'value62000',
    'key94384': 'value9889',
    'key40032': 'value32058',
    'key68034': 'value54609',
    'key58975': 'value43685',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Andrew Coleman',
    'address': '2340 Villa Camp\nChambersburgh, WY 76132',
    'text': 'Matter rather physical trade spend. They collection American conference parent. Energy popular analysis environmental opportunity onto.',
    'email': 'andreakemp@example.net',
    'phone_number': '583.295.3784x96228',
    'array_int_dynamic': [
    90580,
],
    'array_varchar_dynamic': [
    'James Brown',
    'Tracy Sanchez',
    'Laura Wade',
    'David Peterson',
    'Jeremy Gutierrez',
    'William Donaldson',
],
    'json': {
    'name': 'Mckenzie Mitchell',
    'address': '07094 Colleen Skyway Apt. 948\nCalebville, DC 54939',
},
    'key80816': 'value9625',
    'key21097': 'value10909',
    'key46521': 'value32829',
    'key45848': 'value89190',
    'key99731': 'value67597',
    'key15272': 'value74993',
    'key86047': 'value23580',
    'key99280': 'value19202',
    'key92341': 'value21875',
    'key36251': 'value27777',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Heather Wang',
    'address': '89956 Ellis Alley\nJustinburgh, AK 39714',
    'text': 'Rate picture guess agree. Walk occur sure. Total speech method here nearly.\nRange color authority until range. It together smile live increase.',
    'email': 'jeffrey18@example.com',
    'phone_number': '997-378-3075x92210',
    'array_int_dynamic': [
    77383,
],
    'array_varchar_dynamic': [
    'Keith Douglas',
    'Renee Bowers',
    'Scott Smith',
    'Timothy Potts',
    'Teresa Miller',
],
    'json': {
    'name': 'Barry Chapman',
    'address': '95061 Hector Union Apt. 392\nLake Kellyfurt, OH 44722',
},
    'key49340': 'value32427',
    'key21189': 'value26180',
    'key76002': 'value60077',
    'key67830': 'value34488',
    'key9903': 'value20192',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Scott Manning',
    'address': '443 Isaac Walk\nNorth Michaelview, IL 50625',
    'text': 'Individual black build college card himself work. Player challenge test break big develop.\nPm could direction realize score. Market worry along under as card also.',
    'email': 'jacqueline64@example.net',
    'phone_number': '831.993.6505x909',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Schwartz',
    'Joshua Watkins',
    'Shaun Clayton',
],
    'json': {
    'name': 'Ashley Webster',
    'address': '4453 Jared Spur\nReynoldsville, FL 30572',
},
    'key40220': 'value41304',
    'key20819': 'value83806',
    'key90976': 'value60027',
    'key85719': 'value78196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Lisa Sutton',
    'address': '780 Parsons Lake Suite 303\nNew Kim, VA 30322',
    'text': 'Others walk number himself develop southern. Tax dinner rate such real.\nAuthority thus step leader gas research. Truth large fear boy.',
    'email': 'jamescosta@example.com',
    'phone_number': '809.947.0743',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Cantu',
    'Shannon Anderson',
],
    'json': {
    'name': 'Jessica Randall',
    'address': '94036 Donald Summit Suite 738\nTurnerside, PA 99180',
},
    'key28812': 'value24083',
    'key40920': 'value31368',
    'key91009': 'value6564',
    'key37506': 'value56497',
    'key91388': 'value25466',
    'key74917': 'value26190',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Ryan Smith',
    'address': '9527 Ramos Street Suite 979\nJamieton, AR 20274',
    'text': 'Past available town else image. Born however especially up. Low class any onto. Law bank investment common news move benefit.',
    'email': 'potterpatrick@example.net',
    'phone_number': '277-503-4640x9130',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Raymond Ferguson',
    'Jonathan Smith',
],
    'json': {
    'name': 'Karen Johnson',
    'address': '6906 Allen River Suite 210\nAaronport, TN 88536',
},
    'key69840': 'value43710',
    'key91776': 'value67242',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Mike Matthews MD',
    'address': '95236 Michael Islands Suite 651\nJenniferstad, PR 92751',
    'text': 'Send record know.\nTeacher popular science. Plant trouble always name.\nVote service threat both particularly meeting. Lawyer space rock enter. Network who music green.',
    'email': 'davislisa@example.com',
    'phone_number': '592.322.8516',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Jennifer Smith',
    'Annette Meadows',
    'Richard Hamilton',
    'Jennifer Kelly',
    'Cynthia Tucker',
    'William Scott',
],
    'json': {
    'name': 'Daniel Sutton Jr.',
    'address': '911 Gonzalez Club\nKaylamouth, PW 34831',
},
    'key17534': 'value46150',
    'key69829': 'value4668',
    'key32017': 'value21752',
    'key36701': 'value92657',
    'key53577': 'value76301',
    'key62334': 'value14783',
    'key18845': 'value66987',
    'key41643': 'value88700',
    'key9199': 'value73239',
    'key33895': 'value12642',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Jennifer Mcclure',
    'address': '289 Morgan Forks Apt. 136\nNew Steven, ND 91902',
    'text': 'Night push lose suggest scientist food thus. Stock dream last white woman month. Worry power both owner and after tough future.\nSimple hair part always challenge. Set food suffer.',
    'email': 'justin82@example.com',
    'phone_number': '(500)875-3333x96358',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Cameron',
    'Nancy Aguilar',
    'Martin Lewis',
    'Brent Adkins',
    'Anthony Hunter',
    'Amy Ramsey',
    'Debra Ortega',
    'Justin Ochoa',
],
    'json': {
    'name': 'Steven Hughes',
    'address': '36578 Amy Mount\nRebeccafort, AK 88819',
},
    'key22831': 'value87414',
    'key44857': 'value27798',
    'key91214': 'value52280',
    'key6982': 'value71688',
    'key33435': 'value33819',
    'key83151': 'value5666',
    'key31833': 'value30492',
    'key74981': 'value67023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Nicholas Murray',
    'address': '578 Kayla Spring\nNorth Taylormouth, NE 36420',
    'text': 'Between movie full cut car data pay necessary. Serious former probably report too check. Two gun room news. Factor agency use.\nThose analysis full word. One thousand wish pass.',
    'email': 'zochoa@example.com',
    'phone_number': '5253198994',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brenda Griffin',
    'Amber Armstrong',
    'James Ferrell',
    'Kimberly Jones',
    'Patricia Simon',
    'Pamela Robinson',
    'Stephanie Avila',
    'Ann Erickson',
    'Karen Travis',
    'Seth Williams',
],
    'json': {
    'name': 'Donna Beltran',
    'address': '151 Morris Forks Apt. 539\nSouth Tina, CO 94914',
},
    'key40621': 'value13915',
    'key7437': 'value86472',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Tammy Robertson',
    'address': '599 Scott Prairie Suite 281\nNew Michael, MN 41416',
    'text': 'Picture writer between heavy style cause side. Miss television not news throughout break term.\nFew put election section represent beyond range. Where whether country system forward.',
    'email': 'qdavis@example.com',
    'phone_number': '(434)348-2717x7516',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'James Osborn',
    'Justin Davis',
    'James Kim',
],
    'json': {
    'name': 'Darrell Prince',
    'address': '764 Dougherty Estate\nNorth John, MI 58778',
},
    'key72580': 'value84182',
    'key65069': 'value47840',
    'key79639': 'value6688',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Sandra Henry',
    'address': '8639 Katelyn Coves Apt. 062\nGarciaville, IN 64670',
    'text': 'Some media imagine news serious. Two you at owner visit energy.\nWrite carry from budget. Size coach type lead instead top interesting final. Ahead establish indeed heart world true many adult.',
    'email': 'hlewis@example.com',
    'phone_number': '4448694761',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Gonzalez',
    'Jerome Clark',
    'Sean Bryant',
    'Connor Williams DVM',
    'Sean Watkins',
    'Walter Bennett',
    'Christopher Burgess',
    'Kevin Singleton',
    'Dr. Amber Jordan',
    'Jessica Castillo',
],
    'json': {
    'name': 'Barbara Fernandez',
    'address': '4648 Martinez Drive Apt. 639\nSharonside, UT 14729',
},
    'key78537': 'value23922',
    'key17802': 'value68253',
    'key63410': 'value55078',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Ashley King',
    'address': '88927 Heather Path\nPerezside, IL 53952',
    'text': 'Page degree professor peace. Too knowledge involve remain. Space maybe yes true mother newspaper.',
    'email': 'victoria84@example.org',
    'phone_number': '595.817.0862x458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Turner',
    'Dr. Taylor Duran',
],
    'json': {
    'name': 'Jeffrey Perez',
    'address': 'Unit 1717 Box 2247\nDPO AA 97434',
},
    'key68057': 'value18453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Kimberly Thomas',
    'address': '334 Cantu Ridge Suite 921\nWest William, KY 10751',
    'text': 'Page outside she cut adult daughter kid. Off article sister us entire wonder.\nSit answer enter almost full bad. Strategy then group write last skin.',
    'email': 'alexismanning@example.net',
    'phone_number': '(867)838-4053x74020',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jill Carter',
    'Cassandra Lopez',
    'Randy Johnson',
    'Michael Paul',
    'Rebekah Pruitt',
],
    'json': {
    'name': 'Cynthia Brown',
    'address': '970 Williams Estate Apt. 994\nPort Valerie, PW 26193',
},
    'key35485': 'value16411',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Brandon Long',
    'address': '329 Thomas Mountains\nCombsshire, NC 45240',
    'text': 'Look act population look kind part. Organization local maintain beyond. Attack hit apply six season their perhaps tonight.',
    'email': 'thomas88@example.net',
    'phone_number': '540.749.3154x049',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Johnson',
    'Deborah Palmer',
    'Kathryn Hill',
    'Yvette Martin',
    'Lisa Malone',
    'David Williams',
    'Kelli Scott',
    'Ronald Thompson',
    'Jennifer Blackwell',
],
    'json': {
    'name': 'Anita Nichols',
    'address': '3933 Williams Center\nNew Jasonport, HI 71855',
},
    'key19234': 'value92436',
    'key2490': 'value38123',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Andrew Cook',
    'address': '51468 Thompson Corner\nEast Melissastad, MN 92561',
    'text': 'Owner impact inside play down. Send hold economic degree concern others at.\nTrouble exactly call idea true customer. Strategy center measure range tonight dog.',
    'email': 'stevensjohn@example.org',
    'phone_number': '(864)980-1375',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Evans',
    'Ronald Burton',
    'Jared Andrews',
    'Ronald Petersen',
    'David Lee',
    'Shelley Santiago',
    'Brandi Wright',
    'William Williams',
    'Maria Mcmahon',
    'Emily Espinoza',
],
    'json': {
    'name': 'Elizabeth Obrien',
    'address': '69619 Debra Center\nTonyview, NV 39423',
},
    'key23593': 'value71284',
    'key8396': 'value69063',
    'key58208': 'value55584',
    'key57862': 'value61813',
    'key99821': 'value41424',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Karen Ray',
    'address': '2073 Kelly Mill\nLarryview, NC 33859',
    'text': 'Example owner leave kind hospital line huge. Tax will upon but. Best model onto.\nRealize born crime. Nature lose read right nearly reflect piece.\nAppear raise decide call federal. Nor cup effort.',
    'email': 'russelljohn@example.org',
    'phone_number': '275.373.4923x4208',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Howard',
    'James Miller',
    'Jessica Patterson',
],
    'json': {
    'name': 'Glenda Avila',
    'address': '325 David Lights Apt. 334\nLake Trevorville, IA 20028',
},
    'key54957': 'value13277',
    'key21654': 'value7356',
    'key2359': 'value41380',
    'key24802': 'value34908',
    'key66856': 'value53890',
    'key87738': 'value85691',
    'key33574': 'value65211',
    'key60669': 'value5627',
    'key60210': 'value90473',
    'key18332': 'value48370',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Kristy Mays',
    'address': '02796 Gilmore Grove Suite 906\nLake Luke, VI 80336',
    'text': 'Likely town perform argue manager or. First defense main difficult sense.\nTeacher little four billion couple area from. Reduce American that easy continue figure third.',
    'email': 'christopherwalker@example.com',
    'phone_number': '(939)343-0291x47131',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Reese',
    'David Moreno',
    'Sara Briggs DDS',
    'Elizabeth Stone',
    'Tonya Brown',
    'James Waters',
],
    'json': {
    'name': 'Robert Fleming',
    'address': 'PSC 0384, Box 6035\nAPO AP 31815',
},
    'key49925': 'value85506',
    'key34588': 'value43289',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Linda James',
    'address': 'Unit 6826 Box 6308\nDPO AP 20080',
    'text': 'Third onto identify wide he total.\nTax process north reality often better. Both work speech. Visit new also different nature father the which.\nSystem edge car. Agency month foot great.',
    'email': 'christinamoran@example.net',
    'phone_number': '(993)750-8265x1350',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ann Doyle',
    'Briana Davidson',
    'Monica Strong',
    'Rachel Mahoney',
    'Amanda Martinez',
],
    'json': {
    'name': 'Thomas Cole',
    'address': '431 Anderson Estate\nLake Oliviaside, MH 02679',
},
    'key86471': 'value97785',
    'key11338': 'value74516',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Kevin Lutz',
    'address': '88797 Matthew Ferry Apt. 340\nWest Crystal, NC 73767',
    'text': 'Year black find. Me check kind provide tree in. Behind gun paper film prove serious blood.\nCurrent continue man collection parent writer just control. Life center among member true us.',
    'email': 'joshuaarroyo@example.com',
    'phone_number': '9016043297',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Palmer',
    'Theresa Smith',
    'Laura Fisher',
    'Michael Randall',
    'Kristen Krueger',
    'John Brown',
    'Jose Noble',
    'Rick Smith',
    'Rhonda Bonilla',
],
    'json': {
    'name': 'Cynthia Gibson',
    'address': '072 Keith Divide\nLaurenberg, KS 68604',
},
    'key21065': 'value6805',
    'key58918': 'value80804',
    'key29830': 'value59180',
    'key78833': 'value29910',
    'key22311': 'value98558',
    'key99362': 'value21582',
    'key68775': 'value88274',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Terry Howard',
    'address': '01090 Juarez Wells Apt. 672\nDylanport, GU 99549',
    'text': 'Mention market relationship. When scene institution finish. Fall camera matter community newspaper.',
    'email': 'nicolearnold@example.com',
    'phone_number': '+1-480-548-1867',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn May',
    'Bobby Grimes',
    'Alison Knapp',
    'Julie Cole',
    'Mia Ingram',
    'Michael Haney',
    'Miss Robin Osborn DVM',
    'Diane Warner',
],
    'json': {
    'name': 'William Jenkins',
    'address': '9166 Peters Ports Apt. 233\nGreentown, AK 90384',
},
    'key61126': 'value48685',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Robert Dalton',
    'address': '665 Warren Square\nPort Patrickshire, MD 24960',
    'text': 'Behind apply nice commercial significant stop through trial. So ahead well network. Why media develop notice.',
    'email': 'david78@example.net',
    'phone_number': '5692903566',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Randall Kirk',
    'Mrs. Michelle Snyder DVM',
    'Kimberly Clark',
    'Amy Yang',
    'Miss Kaitlyn Hall',
    'Joseph Frazier',
    'Eugene Shaffer',
    'Melissa Johnson',
    'Luke Cummings',
],
    'json': {
    'name': 'Ashley Burke',
    'address': '4321 Long Stravenue\nPort Ashley, AK 09461',
},
    'key22354': 'value9790',
    'key72008': 'value33108',
    'key80500': 'value15687',
    'key43492': 'value13042',
    'key92811': 'value29881',
    'key96895': 'value29221',
    'key19196': 'value63361',
    'key86392': 'value9696',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Erin Rivera',
    'address': '4303 Leslie Glens\nWebbtown, VT 54106',
    'text': 'Brother no test people property particularly. Thank west find before effect. Line close expert go cultural office reality.',
    'email': 'linda22@example.com',
    'phone_number': '287-306-8816x276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Gilbert Brown',
    'Matthew Garrett',
    'Jack Ford',
    'Jennifer Green',
    'Amanda Bradley',
    'Katie Patrick',
    'Stephanie Jackson',
],
    'json': {
    'name': 'Laura Wheeler',
    'address': 'USS Miranda\nFPO AA 95916',
},
    'key58222': 'value96201',
    'key66905': 'value16155',
    'key94548': 'value39417',
    'key4868': 'value10365',
    'key23708': 'value28813',
    'key28115': 'value33586',
    'key65075': 'value80006',
    'key9863': 'value41014',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Lisa Richardson',
    'address': '69284 Johnson Meadows\nShermanville, FL 52829',
    'text': 'Enter firm half tell it. City of guess worry benefit heart president who.\nProfessional thank economic enter leader necessary. Congress brother play.\nLocal person mission door natural this section.',
    'email': 'fordjacqueline@example.org',
    'phone_number': '+1-855-759-0937x342',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Wilson',
    'Keith Smith',
    'Patrick Chapman',
    'Linda White',
    'David Chan',
    'Christopher Torres',
    'Joshua Valdez',
    'Lawrence Walls',
    'Stephanie Hall',
    'Karen Davies',
],
    'json': {
    'name': 'Kelly Harris',
    'address': '129 Austin Loaf Apt. 988\nRobertburgh, WI 60753',
},
    'key79669': 'value48089',
    'key22788': 'value18297',
    'key23646': 'value71960',
    'key7049': 'value80817',
    'key79748': 'value93686',
    'key15276': 'value14446',
    'key62760': 'value99375',
    'key34783': 'value1293',
    'key82639': 'value1682',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Sandra Schmidt',
    'address': '3339 Matthew Ridge Apt. 794\nWest Emmamouth, IN 88811',
    'text': 'Party term president democratic standard total. Citizen generation professional rather protect beat history. Learn past race wonder which kid.',
    'email': 'grayerin@example.net',
    'phone_number': '395.492.5322',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Paul Gross',
    'Mr. Thomas Garza',
    'Fernando Stephens',
    'Jennifer Chapman',
    'Steven Ochoa',
    'David Baker',
    'Patricia Reyes',
    'Leslie Brewer',
    'Melvin Fowler',
    'Audrey Lawrence',
],
    'json': {
    'name': 'Shawna Reed',
    'address': '920 Jordan Coves Suite 000\nEast Leefurt, IA 06274',
},
    'key75285': 'value31902',
    'key76940': 'value74784',
    'key28880': 'value58760',
    'key85366': 'value70303',
    'key26316': 'value52178',
    'key86189': 'value71082',
    'key23513': 'value1048',
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
    'RequestId': '9e2ef628-62ef-11f0-bcf2-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_52_906772ZrPxLgqT',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-2]_1752744174.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl3210021752744174Json()
    test.run_tests()
