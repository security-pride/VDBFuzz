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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestGetVector_test_get_vector_complex[True-False-one]_1752749120_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestGetVector_test_get_vector_complex[True-False-one]_1752749120.json"
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



class AllmilvusLogtestgetvectorTestGetVectorComplexTrueFalseOne1752749120Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestGetVector_test_get_vector_complex[True-False-one]_1752749120.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestGetVector_test_get_vector_complex[True-False-one]_1752749120.json"
        self.test_count = 9  # 测试方法数量
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
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
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
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
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
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
    'data': [
    {
    'id': 17527491156096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Anthony Dalton',
    'address': '677 Davis Crescent\nKimberlyberg, AZ 02486',
    'text': 'Something list happy your worry. Issue carry say treat loss.\nNo type step. Perform close front center measure pay.\nTeach star movement west fly.',
    'email': 'davidsummers@example.com',
    'phone_number': '001-820-746-9836x97337',
    'json': {
    'name': 'Lisa Brewer',
    'address': 'Unit 7969 Box 6174\nDPO AA 36759',
},
    'key14579': 'value69055',
},
    {
    'id': 17527491156113,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Anthony Blair PhD',
    'address': '247 Richard Way\nLuisfort, AS 81459',
    'text': 'Group whole contain. Ready social how recent. Opportunity beyond physical happen discussion meeting.',
    'email': 'haleygarrett@example.com',
    'phone_number': '365.222.5529',
    'json': {
    'name': 'Jason Robles DDS',
    'address': '18545 Lucas Common Suite 378\nGabrielland, MO 98378',
},
    'key40546': 'value12091',
    'key5876': 'value64712',
    'key49688': 'value32877',
    'key65208': 'value66928',
    'key18417': 'value71311',
    'key45639': 'value62408',
    'key7265': 'value8323',
    'key51449': 'value72823',
    'key29579': 'value86783',
},
    {
    'id': 17527491156128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Heather Henry',
    'address': '69977 Perez Hollow\nJuliebury, CO 94034',
    'text': 'Program security politics suggest challenge. House western scene traditional. Capital nation beautiful manager young example television strong.',
    'email': 'graylinda@example.com',
    'phone_number': '001-417-814-3530',
    'json': {
    'name': 'Samantha Myers',
    'address': '8038 Huffman Views Apt. 522\nSuarezchester, NY 81010',
},
    'key57516': 'value72529',
    'key28670': 'value38387',
    'key25294': 'value56359',
    'key14491': 'value15186',
},
    {
    'id': 17527491156142,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Christopher Wright',
    'address': '7843 Johnson Squares Suite 246\nNorth Jennifer, WV 62223',
    'text': 'System again call clearly call grow. Capital why bar education share remember large. Idea role value section power coach mention.',
    'email': 'christopherwilliams@example.net',
    'phone_number': '001-897-277-9226',
    'json': {
    'name': 'Dr. Zachary Figueroa',
    'address': 'Unit 6844 Box 4266\nDPO AP 56102',
},
    'key62226': 'value48974',
    'key13320': 'value84317',
    'key67355': 'value29108',
    'key67484': 'value3626',
    'key839': 'value57590',
    'key48936': 'value84573',
},
    {
    'id': 17527491156152,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Patricia Franklin',
    'address': '7997 Delgado Inlet\nCuevasfurt, NY 32174',
    'text': 'Office reach Democrat like agree customer air. Guess happen seven play for nation here.\nLate must level. Forward many career cup answer scene yet.',
    'email': 'matthewfisher@example.net',
    'phone_number': '392-339-5074x11293',
    'json': {
    'name': 'Matthew Allen',
    'address': 'Unit 5579 Box 8805\nDPO AP 04903',
},
    'key75075': 'value3648',
    'key81944': 'value95009',
    'key75986': 'value74586',
},
    {
    'id': 17527491156164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Julie Donovan',
    'address': '74446 Osborn Route\nDestinyberg, MH 32783',
    'text': 'Girl large new edge front choose more glass. Well international determine official. Modern believe glass sound class. Economy teacher high suffer.',
    'email': 'eileen88@example.org',
    'phone_number': '907-898-4021x0087',
    'json': {
    'name': 'James Mcconnell',
    'address': '3131 Barbara Stream Apt. 701\nJenniferfort, AK 21591',
},
    'key70653': 'value81047',
},
    {
    'id': 17527491156175,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Brandon Carter',
    'address': '07251 Hester Grove\nNorth Wendy, TN 51326',
    'text': 'Billion station teach main. Her individual dog Mrs all. Interest as source song. Century turn training heavy at raise.',
    'email': 'joypadilla@example.net',
    'phone_number': '471-665-8265x370',
    'json': {
    'name': 'Andrew Rodriguez',
    'address': '51435 Cathy Parkway Apt. 841\nPort Marcusberg, KS 23799',
},
    'key77497': 'value15416',
    'key61432': 'value69815',
    'key28720': 'value52596',
    'key1515': 'value23775',
    'key48056': 'value32959',
    'key3525': 'value95237',
    'key88468': 'value10891',
    'key3923': 'value21489',
    'key81604': 'value8547',
},
    {
    'id': 17527491156188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Angel Floyd',
    'address': '876 Andrea River Apt. 467\nSouth Donnashire, NY 15201',
    'text': 'Establish between notice former call fund product machine. Cell least way fast fact culture physical. Large show benefit suggest.\nAnimal that drive.',
    'email': 'michelle56@example.org',
    'phone_number': '322-482-3058',
    'json': {
    'name': 'Jose Moore',
    'address': '3127 Kelly Cove Apt. 547\nNew Danielport, KS 50742',
},
    'key64938': 'value4184',
    'key99508': 'value52253',
},
    {
    'id': 17527491156198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Brian Davis',
    'address': '9449 Anthony Centers Apt. 679\nLake Elizabeth, NC 02359',
    'text': 'Try big dog high defense power rule prevent. Step discussion record deal a. Line data great scene them room.',
    'email': 'mschaefer@example.org',
    'phone_number': '+1-755-214-1113',
    'json': {
    'name': 'Alexandra Barber',
    'address': '4917 Maurice Land Apt. 879\nPort Alan, GU 21817',
},
    'key38142': 'value67160',
    'key34973': 'value30131',
    'key47602': 'value74764',
    'key77373': 'value61554',
    'key11573': 'value8092',
    'key50102': 'value85769',
    'key7328': 'value55646',
    'key13848': 'value82311',
},
    {
    'id': 17527491156208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Mrs. Caitlyn Romero',
    'address': '835 Jon Rest Suite 539\nLaurenmouth, PW 80498',
    'text': 'Agree red deal break picture. Reveal order citizen think best television.',
    'email': 'tyler22@example.com',
    'phone_number': '836-324-0491x5116',
    'json': {
    'name': 'Rachel Thompson',
    'address': '6527 Austin Dale Suite 128\nBennettport, IN 03962',
},
    'key44788': 'value40917',
    'key88968': 'value72633',
    'key11901': 'value42253',
    'key15089': 'value61261',
    'key9946': 'value86556',
    'key50803': 'value16261',
    'key26468': 'value93588',
},
    {
    'id': 17527491156219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Nathan Benitez',
    'address': '7221 Kimberly Passage Apt. 629\nPort Samuelberg, CT 30701',
    'text': 'Me spring option field air with. Water admit see born attack. Ten teach less recently indicate.\nAgent drive how class security network both. Interview three participant within meet.',
    'email': 'isabelgriffin@example.net',
    'phone_number': '333.975.7015x8966',
    'json': {
    'name': 'Nicole Williams',
    'address': '5117 Mccarthy Station\nRaymondbury, MN 64469',
},
    'key67957': 'value66888',
    'key18667': 'value71499',
    'key72787': 'value66674',
    'key24625': 'value24540',
    'key86231': 'value45012',
    'key68665': 'value10218',
},
    {
    'id': 17527491156231,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Antonio Woods PhD',
    'address': '624 Richardson Freeway\nThomasport, AS 18273',
    'text': 'News dark crime security agree student this. Factor up own current decision land. Could fast town baby.',
    'email': 'tgregory@example.org',
    'phone_number': '441-630-9154',
    'json': {
    'name': 'Michelle Martinez',
    'address': '8793 Brown Valley\nNew Erik, WV 50440',
},
    'key48943': 'value90459',
    'key70727': 'value32482',
    'key81256': 'value26717',
    'key82543': 'value38404',
    'key24812': 'value90381',
    'key6276': 'value22032',
    'key47011': 'value97325',
},
    {
    'id': 17527491156242,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Holly Martin',
    'address': 'PSC 1804, Box 2577\nAPO AP 27325',
    'text': 'Fire so now. Travel parent site statement trade maintain.\nWhatever industry box nor member relate. Any reach necessary with order. She effort send store south charge.',
    'email': 'jefferyevans@example.net',
    'phone_number': '001-983-759-8094x148',
    'json': {
    'name': 'John Williams',
    'address': 'Unit 0834 Box 2798\nDPO AP 71844',
},
    'key49973': 'value36732',
    'key55951': 'value46520',
    'key92375': 'value35694',
    'key82055': 'value75568',
    'key89442': 'value88533',
},
    {
    'id': 17527491156249,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Joseph Mosley',
    'address': '017 Fields Greens\nEast Thomasview, FM 27434',
    'text': 'Community full list book executive science outside. Ago edge when option population. House prove wait young speech despite hundred whatever.',
    'email': 'kvasquez@example.com',
    'phone_number': '+1-911-566-1940x361',
    'json': {
    'name': 'Jennifer Stanley',
    'address': '5352 Wright Loaf\nNorth Robertfurt, CO 54407',
},
    'key60915': 'value15578',
    'key95806': 'value92205',
    'key87464': 'value13662',
    'key95037': 'value6680',
    'key94625': 'value6727',
    'key1326': 'value70442',
    'key90205': 'value46186',
    'key26873': 'value30580',
    'key42051': 'value232',
    'key27418': 'value20454',
},
    {
    'id': 17527491156260,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Tanya Singh',
    'address': '5052 Mccoy Squares Suite 184\nPatrickport, MS 43988',
    'text': 'Just raise doctor a past. In significant hotel about reason issue drop. Soon do deal cut because least space deep.',
    'email': 'sarahfuller@example.net',
    'phone_number': '420-961-0802x6109',
    'json': {
    'name': 'William David',
    'address': '1101 Zachary Divide Apt. 461\nShawnshire, ME 12557',
},
    'key88245': 'value71079',
    'key49692': 'value59510',
    'key16724': 'value50234',
    'key42792': 'value3899',
    'key23032': 'value85952',
    'key44115': 'value26888',
    'key77084': 'value36425',
    'key53050': 'value55857',
    'key20744': 'value71507',
    'key70725': 'value395',
},
    {
    'id': 17527491156272,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Brandon Parker',
    'address': '243 Jennifer Union\nCollinsview, WI 61919',
    'text': 'Series act human have writer western why. Fear pressure realize position white nor baby. Not girl total under technology pretty.',
    'email': 'malik31@example.com',
    'phone_number': '+1-867-279-2156',
    'json': {
    'name': 'Melinda Jackson',
    'address': '06030 Thomas Trail Apt. 902\nCrawfordmouth, MP 32550',
},
    'key62373': 'value36808',
    'key23751': 'value10713',
    'key26167': 'value26949',
    'key62590': 'value18470',
    'key35687': 'value6013',
    'key87823': 'value347',
    'key64868': 'value52676',
    'key33227': 'value29756',
    'key31001': 'value93235',
    'key15759': 'value68550',
},
    {
    'id': 17527491156283,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Lawrence Pham',
    'address': '9770 Gerald Cliffs Suite 203\nGrantland, WY 10744',
    'text': 'Man none usually big. Another result shoulder serve mean how theory.\nNew could environmental rest seat. Mission myself future structure PM.',
    'email': 'erin50@example.org',
    'phone_number': '(661)715-6781x86688',
    'json': {
    'name': 'Dean Maldonado',
    'address': 'Unit 7116 Box 0409\nDPO AE 69772',
},
    'key7223': 'value80954',
    'key63365': 'value48448',
    'key17487': 'value67668',
    'key4109': 'value90083',
},
    {
    'id': 17527491156292,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Kendra Smith',
    'address': '6503 Michael Courts Suite 300\nPatrickland, OR 60904',
    'text': 'Happen dinner law off. Our never main heavy bring.\nAccording according debate expect green say put. Fight language reduce control government less offer.',
    'email': 'victoria80@example.org',
    'phone_number': '906.873.9529',
    'json': {
    'name': 'Jessica White',
    'address': '50471 Anita Radial\nSouth Amyville, IL 81425',
},
    'key48495': 'value72670',
    'key76840': 'value99563',
    'key6879': 'value94397',
    'key18271': 'value608',
    'key43999': 'value26958',
    'key10845': 'value18336',
    'key15709': 'value30272',
    'key46886': 'value91902',
},
    {
    'id': 17527491156301,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Dennis Jackson',
    'address': '490 Sandra Meadows Suite 944\nJohnsonview, CA 01687',
    'text': 'People physical method real reach of. Still music minute open look two perhaps drive. Student sound school onto drop administration wide military.',
    'email': 'afrey@example.org',
    'phone_number': '001-801-536-4672x78050',
    'json': {
    'name': 'Martin Schroeder',
    'address': '840 Curtis Garden\nCalvinfurt, UT 24935',
},
    'key84595': 'value74548',
    'key87996': 'value37029',
    'key59782': 'value92088',
    'key51266': 'value23576',
},
    {
    'id': 17527491156312,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jennifer Phillips',
    'address': '435 Lisa Row\nCandaceville, MS 75192',
    'text': 'Cultural because three start walk run town. Charge home value piece. Age fly price.\nHear film agree future family number. Also book phone sort wait trial director.\nSuffer road mission decade detail.',
    'email': 'patricia08@example.net',
    'phone_number': '7406609567',
    'json': {
    'name': 'Sharon Thompson',
    'address': '5526 Scott Summit Apt. 210\nNew Brianna, MN 94209',
},
    'key55094': 'value43807',
    'key5946': 'value20766',
    'key7622': 'value20417',
    'key25037': 'value9453',
},
    {
    'id': 17527491156323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Laura Ramirez',
    'address': '385 Johnny River\nNorth Jennifer, AR 72277',
    'text': 'Perform stage war successful. Such trade knowledge decide safe whether rule end. Bit international live detail put around feel.\nOr while where pass. Free less first.',
    'email': 'kellerelizabeth@example.net',
    'phone_number': '001-408-805-5544x9002',
    'json': {
    'name': 'Andrew Williams',
    'address': '997 Matthew Via\nWaltersville, FM 11800',
},
    'key21251': 'value64151',
    'key67379': 'value39240',
    'key58612': 'value80433',
    'key98366': 'value24766',
    'key7388': 'value42211',
    'key2275': 'value7816',
    'key37439': 'value85778',
    'key33855': 'value19563',
},
    {
    'id': 17527491156335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Sarah Henson',
    'address': '95990 Taylor Summit\nSouth James, AK 20914',
    'text': 'Become fact every outside write entire. Instead doctor probably sort street.\nFeeling piece effort season response. Job inside put production.',
    'email': 'dwright@example.net',
    'phone_number': '820.930.8581x6730',
    'json': {
    'name': 'Timothy Myers',
    'address': '5234 Smith Throughway\nDonovanfort, IA 54189',
},
    'key87431': 'value81432',
    'key19549': 'value3076',
    'key75047': 'value58439',
    'key48754': 'value65796',
},
    {
    'id': 17527491156346,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Barbara Stanley',
    'address': 'USCGC Hobbs\nFPO AE 43460',
    'text': 'Well week similar level perform mission. New model how feeling and learn.\nLetter west little reason.\nAttorney myself law operation. These set social shoulder whole from. Method class wait so.',
    'email': 'katelynwilliams@example.net',
    'phone_number': '+1-705-283-4573',
    'json': {
    'name': 'Bryan Campbell',
    'address': '1834 Flores Knoll Apt. 999\nNew Laurenbury, NM 05632',
},
    'key2394': 'value97602',
    'key93791': 'value6328',
},
    {
    'id': 17527491156357,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Charles Bernard',
    'address': '3266 David Pines\nNorth Richardfort, WA 46172',
    'text': 'Idea thus pretty hold culture her. Finish into term. Various keep so certain beat.\nData realize economy purpose develop throughout thousand. Carry bill sit surface type successful begin enjoy.',
    'email': 'petersdanny@example.org',
    'phone_number': '+1-499-546-0476x0191',
    'json': {
    'name': 'Rebecca Reilly',
    'address': '08117 Torres Harbors\nLake Bryanside, SC 39784',
},
    'key82524': 'value60890',
    'key1404': 'value6554',
},
    {
    'id': 17527491156368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Courtney Hansen',
    'address': 'USCGC Turner\nFPO AE 15224',
    'text': 'Enough clear describe it structure. Rule understand edge night. Without question development no marriage.\nAlmost popular people stock our let expert. Public station similar hand require clear sense.',
    'email': 'barnetttimothy@example.org',
    'phone_number': '865.568.4780x5989',
    'json': {
    'name': 'Gregory Ward',
    'address': '13945 Evans Fort\nLake Donaldbury, GA 38675',
},
    'key31531': 'value33414',
    'key33720': 'value9508',
    'key15296': 'value50273',
    'key14486': 'value20558',
    'key86831': 'value85316',
    'key38515': 'value96348',
},
    {
    'id': 17527491156379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'David Keith',
    'address': '4028 Osborne Valley Suite 609\nNorth Nicholasside, KS 69135',
    'text': 'Send commercial move add moment. Hour skin peace each last write.\nNotice wait hear media three network. Agreement air glass network avoid huge.',
    'email': 'sean44@example.net',
    'phone_number': '(702)205-2440x494',
    'json': {
    'name': 'Jamie Arnold MD',
    'address': 'PSC 8854, Box 5665\nAPO AE 06298',
},
    'key41017': 'value89953',
    'key58004': 'value21920',
    'key72770': 'value6949',
    'key25953': 'value41519',
    'key91308': 'value38935',
    'key30975': 'value31780',
    'key15551': 'value7874',
    'key28749': 'value49534',
},
    {
    'id': 17527491156388,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Aaron Soto',
    'address': '28360 Christopher Stream Suite 230\nAndrewbury, MP 68624',
    'text': 'President list soon spend seat. Security establish the paper new. Movement perform eight parent institution down statement.\nTeach in authority increase resource.',
    'email': 'ronaldanderson@example.org',
    'phone_number': '+1-699-364-4983',
    'json': {
    'name': 'Andrew Young',
    'address': '8690 Madison Trail Apt. 753\nNorth Johnburgh, GA 90081',
},
    'key99627': 'value88705',
    'key93549': 'value38348',
    'key31675': 'value73038',
    'key72947': 'value33507',
    'key77757': 'value4871',
    'key75851': 'value50181',
    'key40563': 'value17780',
},
    {
    'id': 17527491156399,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Brian Wright',
    'address': '5042 Ho Spur Suite 301\nPort Danielshire, NM 29080',
    'text': 'Fall home risk technology. Like under give not.',
    'email': 'bryan18@example.net',
    'phone_number': '642.634.8619x7518',
    'json': {
    'name': 'Brittany Rogers',
    'address': '99064 Joseph River Suite 531\nMyersport, OK 22942',
},
    'key32245': 'value28593',
},
    {
    'id': 17527491156410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Nicholas Marks',
    'address': '5550 Daniels Plains Apt. 066\nDouglasville, CT 37463',
    'text': 'Control plan seven paper spring eight.\nGame market senior.\nRoom player tree medical five. Mention great choose politics window describe western. Sing clear friend remain arm.',
    'email': 'bradleywang@example.net',
    'phone_number': '(580)724-2292',
    'json': {
    'name': 'Kristen Valencia',
    'address': '57873 William Brook\nNew Daniel, KS 65308',
},
    'key94248': 'value73610',
    'key84774': 'value57102',
    'key26065': 'value29003',
    'key45624': 'value86372',
    'key93855': 'value53594',
    'key19391': 'value80707',
    'key77827': 'value65161',
},
    {
    'id': 17527491156422,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Elizabeth Sherman',
    'address': '9324 Melissa Fords\nSouth Jamesfort, OH 67855',
    'text': 'Computer a much despite cell either. Growth parent Mr bill eye. Several firm recent especially. Thing company practice country mission prevent option.',
    'email': 'brett14@example.org',
    'phone_number': '+1-394-447-6500x801',
    'json': {
    'name': 'Benjamin Fuller MD',
    'address': 'USS Taylor\nFPO AE 62692',
},
    'key11135': 'value35193',
    'key3609': 'value17245',
    'key43714': 'value21284',
},
    {
    'id': 17527491156431,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Richard Wagner',
    'address': '360 Johnson Extensions\nEspinozaside, OR 84349',
    'text': 'Analysis which for art accept middle stand beautiful. Worry whatever crime food toward social. Former behind at. Her outside baby condition forget.',
    'email': 'jamieperkins@example.net',
    'phone_number': '588.819.3321x5605',
    'json': {
    'name': 'Daniel Keith',
    'address': 'PSC 2654, Box 5965\nAPO AP 04005',
},
    'key25854': 'value9619',
    'key144': 'value44464',
    'key84834': 'value56575',
    'key24250': 'value8713',
    'key16917': 'value31421',
    'key60031': 'value51611',
    'key22552': 'value12643',
},
    {
    'id': 17527491156441,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Aaron Allen',
    'address': '0637 Jenkins Springs Suite 347\nWest Michaelborough, MO 65152',
    'text': 'Idea paper capital it wait point. Able hope break because enter rather. Their save claim get sing. Beautiful guess develop voice trial full draw culture.',
    'email': 'riverasteven@example.com',
    'phone_number': '001-469-508-4466',
    'json': {
    'name': 'Gary Mcdowell',
    'address': '85847 Shirley Row Apt. 586\nNew Tashaburgh, NV 31235',
},
    'key57198': 'value38623',
    'key54667': 'value72207',
    'key76168': 'value43784',
    'key28764': 'value37439',
    'key1393': 'value24150',
    'key64266': 'value35303',
    'key58501': 'value69608',
},
    {
    'id': 17527491156452,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Carrie Scott',
    'address': '1644 Green Junctions\nYatesport, FM 32630',
    'text': 'Another let one newspaper quite. Music must art I conference.\nCause across now nearly network. If research expect. Month head trouble role hair. Kitchen former yes range rather.',
    'email': 'wilsonwalter@example.org',
    'phone_number': '+1-431-328-4503x09064',
    'json': {
    'name': 'Meredith Ortega',
    'address': '7074 Bradley Heights\nSweeneyton, MD 64654',
},
    'key93861': 'value41169',
    'key94257': 'value97964',
    'key84258': 'value21115',
    'key3971': 'value29768',
    'key71491': 'value53697',
},
    {
    'id': 17527491156464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michael Dennis',
    'address': '088 Gay Extension\nPort Angelamouth, OK 32611',
    'text': 'Join really high. Guy once outside. In trade drug especially lot.\nSince in point. Strong increase deal radio.\nImportant push fish eat. Board measure herself themselves.',
    'email': 'mcdanielryan@example.net',
    'phone_number': '2272494896',
    'json': {
    'name': 'Jeffrey Preston',
    'address': '94267 Melendez Mill Apt. 414\nBaileyland, ME 39997',
},
    'key18176': 'value81202',
    'key10691': 'value2763',
    'key90701': 'value97486',
    'key18178': 'value56331',
    'key11050': 'value77449',
    'key51394': 'value9267',
},
    {
    'id': 17527491156476,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Jessica Palmer',
    'address': '705 King Rapids Apt. 792\nEast Angela, NH 10192',
    'text': 'Word though because very. People thought specific help wonder pattern old. Five second news very three.',
    'email': 'ryansilva@example.net',
    'phone_number': '001-440-508-9175x3742',
    'json': {
    'name': 'Gabriel Smith',
    'address': '364 Sean Cliff\nJonesview, KY 66483',
},
    'key19294': 'value21713',
    'key99044': 'value60141',
    'key26141': 'value43485',
    'key32296': 'value79391',
    'key94364': 'value48539',
},
    {
    'id': 17527491156488,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Richard Herrera',
    'address': '4404 Rich Heights Apt. 875\nLopezmouth, SD 69467',
    'text': 'Statement through almost social apply. Computer beautiful dog agency thank bring Mrs we.\nNote trouble blue. Open really Republican pick.',
    'email': 'colingreen@example.net',
    'phone_number': '001-319-657-3828x9197',
    'json': {
    'name': 'Amy Rosales',
    'address': '37098 Rubio Land\nShanemouth, FM 98504',
},
    'key23273': 'value5332',
    'key73575': 'value46536',
    'key9774': 'value52175',
    'key58643': 'value78478',
    'key87548': 'value94261',
    'key23750': 'value85712',
},
    {
    'id': 17527491156500,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Shannon Cooper',
    'address': '6496 Alexandria Burgs\nCharlotteview, KS 65853',
    'text': 'Various wonder local Mrs. Offer help item head clearly member less purpose. Degree may activity beat wall toward economy six.\nMean three weight accept adult issue hundred. Car pick other hear three.',
    'email': 'ygilmore@example.org',
    'phone_number': '+1-785-916-4478x74184',
    'json': {
    'name': 'Ronald Bradford',
    'address': '17995 Sonya Locks Apt. 426\nButlerton, WY 42445',
},
    'key53358': 'value50749',
    'key80316': 'value70302',
    'key82057': 'value46698',
    'key98527': 'value3477',
    'key63899': 'value78926',
    'key93664': 'value25477',
},
    {
    'id': 17527491156511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Melinda Caldwell',
    'address': '60237 Leslie Flat\nRamosmouth, TN 72537',
    'text': 'Walk keep federal marriage enjoy. Card defense involve forward necessary long investment.',
    'email': 'campbellkimberly@example.com',
    'phone_number': '(226)788-6600x391',
    'json': {
    'name': 'Christopher Morris',
    'address': '3523 Elizabeth Lodge Suite 830\nChristophertown, KS 32968',
},
    'key78197': 'value31786',
    'key26515': 'value48419',
    'key10949': 'value98895',
    'key18945': 'value42740',
    'key59954': 'value62058',
},
    {
    'id': 17527491156522,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Katie Wilson',
    'address': '0412 Garcia Gardens\nEast Sydney, CT 57496',
    'text': 'Culture send stage plant west laugh write. Thing enter will task capital choose.',
    'email': 'jamesphillips@example.com',
    'phone_number': '935-988-6325x712',
    'json': {
    'name': 'Manuel Harmon',
    'address': '18801 Michael Corners\nKeithburgh, MN 45342',
},
    'key41727': 'value17213',
    'key41446': 'value35033',
    'key15939': 'value97370',
    'key59530': 'value23780',
    'key46946': 'value8001',
    'key16722': 'value48163',
    'key70965': 'value30104',
    'key90989': 'value82763',
},
    {
    'id': 17527491156533,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Brandy Choi',
    'address': '42278 Vincent Square Suite 398\nSouth Theresa, WV 31273',
    'text': 'Even serious ten sit trial. Hotel process sing figure process option nor father. Thank after cold.\nAgain issue score style. Deep else notice. Another focus meet.',
    'email': 'schroederbrad@example.org',
    'phone_number': '3675187993',
    'json': {
    'name': 'Diane Walker',
    'address': '695 Underwood Ports Suite 187\nPaynemouth, WI 25799',
},
    'key26870': 'value46404',
    'key72905': 'value44327',
    'key35428': 'value30381',
},
    {
    'id': 17527491156545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Richard Arias',
    'address': 'PSC 7736, Box 8456\nAPO AA 13489',
    'text': 'Final yet leave national. Pass Republican view. Hair prove score name quite born. Way ever bar listen message wear.\nOne exist page picture leave of citizen. Wide member door meet each challenge true.',
    'email': 'jacksonshane@example.net',
    'phone_number': '744-986-7770x8558',
    'json': {
    'name': 'Erin Mayo',
    'address': '51149 Michael Parkway Apt. 797\nCharlesview, AK 83594',
},
    'key43942': 'value18500',
},
    {
    'id': 17527491156555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Arthur Kim',
    'address': '6584 Audrey Parkways Apt. 237\nPort Seth, ID 69820',
    'text': 'Street start part early. Point movement draw of take art quickly maybe.\nMovement cultural world would computer service. Fish economy model deep hour. Themselves grow occur knowledge ready possible.',
    'email': 'duane27@example.net',
    'phone_number': '(583)814-5465x3633',
    'json': {
    'name': 'Cindy Gonzalez',
    'address': '200 Norman Plains\nMaryville, TX 75158',
},
    'key52587': 'value39515',
    'key22922': 'value54512',
    'key51709': 'value14420',
},
    {
    'id': 17527491156565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Kathy Hernandez',
    'address': 'PSC 5235, Box 5679\nAPO AP 33914',
    'text': 'Focus light environmental bit miss. Either learn someone film. Candidate six fine item individual. Newspaper rather wide recent poor type.',
    'email': 'housecody@example.org',
    'phone_number': '(983)453-9214x4680',
    'json': {
    'name': 'Marie Decker',
    'address': '9873 Cardenas Corners Suite 855\nPort Alyssabury, MT 27210',
},
    'key81648': 'value15024',
    'key17085': 'value65391',
    'key49358': 'value7211',
    'key31860': 'value95306',
    'key55979': 'value18702',
    'key12194': 'value75179',
    'key79384': 'value82603',
    'key89612': 'value86550',
    'key49032': 'value89990',
},
    {
    'id': 17527491156575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kimberly Morales',
    'address': '2403 Alejandro Avenue\nGomezmouth, SD 91661',
    'text': 'Inside health trouble skill others family interest. Blue life common involve writer ten. Buy cultural myself race wide. Second weight interesting sound choice but during.',
    'email': 'desireeosborne@example.net',
    'phone_number': '+1-490-431-2470x496',
    'json': {
    'name': 'Beth Gonzales',
    'address': '3501 Tiffany Summit Apt. 807\nWest Crystalside, MP 19569',
},
    'key88071': 'value92921',
    'key94490': 'value10753',
    'key26838': 'value26092',
    'key91989': 'value33680',
    'key58085': 'value95034',
},
    {
    'id': 17527491156586,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Jason Wall',
    'address': '61812 Alexandra Stravenue\nWest Jennifermouth, NC 77883',
    'text': 'Newspaper yeah rest out movement organization many.\nFace work point eight market left get. Baby just news ball miss surface.',
    'email': 'andersonlisa@example.net',
    'phone_number': '298-959-6640',
    'json': {
    'name': 'Adam Horn',
    'address': '87053 Mccullough Lock\nEast Samanthabury, TN 23202',
},
    'key45729': 'value70184',
    'key14363': 'value53404',
    'key73119': 'value49518',
    'key94971': 'value44056',
    'key51100': 'value91616',
},
    {
    'id': 17527491156597,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Steve Villa',
    'address': '3507 Andrea Expressway\nLake Robertstad, SC 19448',
    'text': 'Break issue administration attack summer. Condition both car forward.\nEnjoy as guess very against room.',
    'email': 'jesse63@example.org',
    'phone_number': '825-624-2323x70872',
    'json': {
    'name': 'Barbara Hart',
    'address': '120 Dana Port Apt. 059\nFriedmanstad, AL 89973',
},
    'key38117': 'value40194',
    'key36113': 'value14153',
},
    {
    'id': 17527491156608,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Erin Walker',
    'address': '01637 Robin Fields Suite 566\nZunigaville, OH 80047',
    'text': 'Picture rate wait. Understand remain song wind maintain.\nIncrease wish system particularly continue cost.',
    'email': 'dawn11@example.org',
    'phone_number': '001-456-257-0853',
    'json': {
    'name': 'Larry Hill',
    'address': '5740 Sandra Bypass Apt. 856\nWest Heatherview, PR 25582',
},
    'key79429': 'value54664',
    'key91361': 'value72432',
    'key98142': 'value6436',
    'key738': 'value27562',
    'key34208': 'value79796',
    'key56941': 'value43179',
    'key26428': 'value87255',
    'key20058': 'value19782',
    'key35261': 'value68534',
},
    {
    'id': 17527491156618,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Daniel Brown',
    'address': '5808 Wright Crescent\nLake Rickeyville, SD 64796',
    'text': 'When finally start growth later action. Seven her professional bill beautiful long gun.\nLong traditional what reflect own open deep. Wide style he factor place myself quickly.',
    'email': 'tiffanyclark@example.net',
    'phone_number': '974.491.1804',
    'json': {
    'name': 'Brandy Barton',
    'address': '9282 Turner Island Apt. 860\nNorth Shawn, GU 35958',
},
    'key16909': 'value52520',
    'key79011': 'value10386',
    'key75118': 'value35210',
    'key4016': 'value82033',
    'key34756': 'value32080',
},
    {
    'id': 17527491156630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Melissa Valdez',
    'address': 'PSC 7629, Box 2324\nAPO AA 86847',
    'text': 'Where kitchen laugh yet green central not safe. Prevent attorney build contain adult then.\nStandard stage several politics happy real. Water increase look true memory ahead total.',
    'email': 'nealharry@example.org',
    'phone_number': '(218)219-0058x382',
    'json': {
    'name': 'Melanie Herrera',
    'address': '966 Rodney Canyon\nMirandaville, GA 99071',
},
    'key83868': 'value64537',
    'key62102': 'value79180',
    'key95814': 'value88704',
},
    {
    'id': 17527491156639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Ricky Lindsey',
    'address': '43463 Jackson Square\nChristianview, RI 63717',
    'text': 'Over back help eat color talk. According thought minute father phone similar career. Already environment hear.',
    'email': 'sjohnson@example.org',
    'phone_number': '971-410-9596x5642',
    'json': {
    'name': 'Frank Kelly',
    'address': '6725 Cook Plaza\nWest Laurenfort, TX 82625',
},
    'key96501': 'value60528',
    'key39413': 'value49364',
    'key89060': 'value73815',
    'key71999': 'value12927',
},
    {
    'id': 17527491156650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Natasha Carlson',
    'address': '576 Williams Terrace\nHammondshire, MP 16031',
    'text': 'Response finally only suffer these should agree. Structure red federal for hotel support natural.\nWhom condition recognize reach accept determine very. Hand drug whom authority professional me.',
    'email': 'rojasamanda@example.org',
    'phone_number': '001-495-433-8642x1480',
    'json': {
    'name': 'Leah Fitzgerald',
    'address': '5463 Sharp Burg\nNew Victoriaborough, AL 50244',
},
    'key2663': 'value24856',
    'key55456': 'value65951',
    'key47510': 'value15970',
},
    {
    'id': 17527491156661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kendra Gay',
    'address': '262 Robert Turnpike Apt. 803\nOliviatown, GU 49807',
    'text': 'Letter discussion onto time whatever since enter. Whose how security skin eight prove. Strong property human to memory case then. Property similar attorney true.',
    'email': 'jamesmiller@example.org',
    'phone_number': '(569)935-5014x1930',
    'json': {
    'name': 'Sandra Thomas',
    'address': '885 Taylor Hill\nThomastown, AZ 23207',
},
    'key74249': 'value53749',
    'key80623': 'value21043',
    'key70647': 'value63806',
    'key95101': 'value44831',
    'key5719': 'value78816',
    'key40393': 'value72265',
},
    {
    'id': 17527491156673,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Jennifer Hopkins',
    'address': '776 Amy Heights Suite 764\nRosston, AR 49705',
    'text': 'Statement enjoy relationship security interesting need. Loss bank doctor than may whether safe later. The letter order style.',
    'email': 'samanthafleming@example.com',
    'phone_number': '+1-926-855-7955x68341',
    'json': {
    'name': 'James Lowery',
    'address': '989 Fowler Underpass Apt. 745\nEast Shannonfort, AK 69841',
},
    'key94324': 'value48094',
    'key89069': 'value88630',
    'key92156': 'value84112',
},
    {
    'id': 17527491156685,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Jordan Johnson',
    'address': '20940 Jason Well\nLopezchester, OH 79753',
    'text': 'Suggest law management past they yes view. Soldier attorney never present American despite. Charge claim daughter result simply consumer.',
    'email': 'caldwellwendy@example.org',
    'phone_number': '+1-827-739-3643x46307',
    'json': {
    'name': 'Christopher Salazar',
    'address': '877 Christy Ridges Apt. 283\nSouth Richardville, WV 55785',
},
    'key26944': 'value34674',
},
    {
    'id': 17527491156696,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jacqueline Johnson',
    'address': '0519 Moore Creek\nLiumouth, NV 29121',
    'text': 'Describe into why worker. Get rock sister visit reason. Choose reveal significant weight.\nMr strategy ground that fall. Future enter nor major know time. Describe who no.',
    'email': 'vanessa12@example.com',
    'phone_number': '(310)461-2218x5513',
    'json': {
    'name': 'Jesus Roach',
    'address': '43695 Debra Forest Suite 465\nWest Meghanton, UT 79596',
},
    'key65797': 'value37799',
    'key88078': 'value63097',
    'key31522': 'value14306',
    'key94848': 'value61611',
    'key13564': 'value10361',
    'key52981': 'value55194',
    'key39214': 'value86570',
    'key86965': 'value99557',
    'key33357': 'value47351',
},
    {
    'id': 17527491156707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Margaret Rangel',
    'address': '47936 Tracy Passage\nAmandahaven, HI 59685',
    'text': 'Lot bed money lead. Structure include police. Candidate each available for necessary.\nInside indicate line throughout work unit accept. Become want after party.\nImprove south side top a identify.',
    'email': 'perezmatthew@example.org',
    'phone_number': '295.930.6834x194',
    'json': {
    'name': 'Gabriel Lucas',
    'address': '486 Montgomery Inlet\nGordonville, TX 26407',
},
    'key29706': 'value1446',
    'key77193': 'value8706',
    'key8276': 'value13423',
    'key23402': 'value96200',
    'key32644': 'value91519',
    'key28526': 'value33541',
    'key23896': 'value1485',
    'key19052': 'value69800',
},
    {
    'id': 17527491156719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'John Moore',
    'address': '305 Linda Mill\nCatherineton, NC 66459',
    'text': 'Need huge maintain end amount next color. Author mouth stage.\nModel least current. Color lose stuff rate. Stop with knowledge under require media.',
    'email': 'parksdavid@example.com',
    'phone_number': '(927)765-3692x3138',
    'json': {
    'name': 'Michael Johnson',
    'address': '743 Morales Street\nEast Jaredside, DC 84221',
},
    'key24365': 'value44115',
    'key32627': 'value4976',
    'key82970': 'value18500',
    'key31387': 'value70976',
},
    {
    'id': 17527491156730,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Vincent Murphy',
    'address': '1369 Tate Fords\nBarbaratown, SD 17705',
    'text': 'Less rich property knowledge TV. Budget agency product because son. Build war government treatment cover. Physical defense study under movie.',
    'email': 'ryan48@example.com',
    'phone_number': '443.502.7526x0946',
    'json': {
    'name': 'Jessica Martin',
    'address': '96673 Morton Parkway\nSouth Markfurt, NV 19574',
},
    'key64619': 'value63611',
    'key84508': 'value1837',
},
    {
    'id': 17527491156740,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Todd Bruce',
    'address': '65466 Schneider Port Suite 458\nLake Jeffreychester, MS 12432',
    'text': 'Then hear animal brother he interest. Dog police draw worry crime box number in. Activity lead campaign low trial.\nQuality late individual total respond. Allow doctor simple program.',
    'email': 'xmeyer@example.org',
    'phone_number': '898.547.9764',
    'json': {
    'name': 'Andrew Stephenson',
    'address': 'PSC 5049, Box 1885\nAPO AE 60479',
},
    'key60323': 'value72291',
    'key13546': 'value95448',
    'key44682': 'value90428',
    'key35098': 'value48147',
},
    {
    'id': 17527491156749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Timothy Simpson',
    'address': '4187 Alvarez Estates Suite 195\nSmithland, OK 97432',
    'text': 'Ok large total movement. Seem view follow skin small.\nPast traditional material. Student also series hold service computer TV. Plant certain into bank that. Surface catch group recognize line.',
    'email': 'kgarcia@example.net',
    'phone_number': '(867)563-8224x4811',
    'json': {
    'name': 'Andrew Gray',
    'address': '5903 Lee Glen Suite 004\nDonaldhaven, FM 66950',
},
    'key92239': 'value82984',
    'key68555': 'value24185',
    'key39638': 'value18898',
    'key49391': 'value69796',
    'key75965': 'value73046',
    'key13401': 'value90005',
    'key87210': 'value44815',
},
    {
    'id': 17527491156761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Roger Hester DDS',
    'address': '7430 Julian Forges Apt. 446\nAnthonyhaven, WI 41083',
    'text': 'Air six someone smile east popular thought. Soon company forget as discussion.\nInterview edge some area. Way attack process born.\nPoint offer light political view.',
    'email': 'cooperstacy@example.net',
    'phone_number': '590-966-1529x2195',
    'json': {
    'name': 'Charles Johnston',
    'address': 'USNV Adams\nFPO AE 67590',
},
    'key45837': 'value89114',
    'key7612': 'value80129',
    'key55232': 'value75636',
    'key36817': 'value77446',
    'key2762': 'value50333',
    'key60709': 'value51483',
},
    {
    'id': 17527491156771,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Brianna Thompson',
    'address': '6682 Brian Trail\nHannahmouth, MD 56176',
    'text': 'Less development game system. Anyone picture line entire traditional. Person behavior safe big.\nBegin top street none. Respond approach western forget why foot. Action reason several perhaps money.',
    'email': 'jaime54@example.org',
    'phone_number': '917-607-6587',
    'json': {
    'name': 'Theresa Long',
    'address': '995 Larson Overpass\nWest Steven, NE 61422',
},
    'key33384': 'value53009',
    'key76358': 'value57710',
    'key96986': 'value12260',
    'key60513': 'value90299',
    'key75404': 'value99633',
},
    {
    'id': 17527491156781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Russell Martinez',
    'address': '352 Long Valleys Suite 061\nRyanland, NJ 80530',
    'text': 'Subject usually draw window market official trial. Coach mind behind first when.\nOut treatment participant fact personal a. Idea simply perhaps economic indicate. Scientist answer both he air woman.',
    'email': 'tinagarrett@example.org',
    'phone_number': '001-933-369-9557x6886',
    'json': {
    'name': 'Diamond Allen',
    'address': '2644 David Viaduct\nPetersonton, MH 45136',
},
    'key1168': 'value61724',
    'key76585': 'value45847',
    'key31465': 'value36779',
    'key49834': 'value73689',
    'key6123': 'value25339',
    'key51791': 'value37784',
    'key82533': 'value30766',
    'key92218': 'value58853',
},
    {
    'id': 17527491156793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Madison Maddox',
    'address': 'Unit 2001 Box 6819\nDPO AP 51457',
    'text': 'Pay image husband hot force need. Morning single position story service. Appear poor along less scene station.\nCollege mother who people. Believe top modern four.',
    'email': 'vjones@example.net',
    'phone_number': '2417955792',
    'json': {
    'name': 'Kelli Schmidt',
    'address': '426 Alexandra Lane\nPort Eric, NC 80825',
},
    'key9509': 'value91949',
    'key42501': 'value7611',
    'key23516': 'value17015',
    'key76556': 'value46969',
    'key48456': 'value23000',
    'key98529': 'value32709',
    'key10649': 'value55934',
    'key73': 'value59821',
},
    {
    'id': 17527491156803,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Susan Bailey',
    'address': '2233 Ramirez Bridge\nWellsport, DC 36721',
    'text': 'Strong seek policy music produce. Me trial type.\nAlthough change American table daughter. Democratic compare reality student third catch plant. Must cost fight memory owner data.',
    'email': 'gallen@example.com',
    'phone_number': '(248)878-8689x1945',
    'json': {
    'name': 'Guy Coleman',
    'address': '4743 Washington Centers Apt. 012\nKleinhaven, WA 74389',
},
    'key48712': 'value27090',
    'key33912': 'value44246',
    'key83191': 'value69119',
},
    {
    'id': 17527491156815,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Amanda Campbell',
    'address': 'Unit 8623 Box 6565\nDPO AA 50851',
    'text': 'Vote second article amount matter help white. Environment sense marriage order life instead. Oil throughout if.\nWhich effect former effort international.',
    'email': 'ochoacory@example.com',
    'phone_number': '(449)476-6790x078',
    'json': {
    'name': 'Leslie Schmidt',
    'address': '66145 Hansen Prairie\nNorth Raymond, AR 67153',
},
    'key7469': 'value63736',
    'key87990': 'value11286',
    'key29651': 'value76607',
    'key98121': 'value55530',
    'key94952': 'value80783',
    'key76592': 'value65127',
    'key80931': 'value42010',
},
    {
    'id': 17527491156826,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Teresa Harvey',
    'address': '449 Eric Freeway\nTinaview, TN 88436',
    'text': 'Suddenly keep think turn pressure explain discover. Trade later either bill garden. Throw low our road traditional commercial.\nResource hard history plant. Deal all manager value enough purpose day.',
    'email': 'karenbowers@example.net',
    'phone_number': '(577)857-4035x043',
    'json': {
    'name': 'Julie Smith',
    'address': '49284 Horton View\nWest Jonathan, AR 20764',
},
    'key73657': 'value20441',
    'key81793': 'value88743',
    'key74826': 'value67575',
    'key57552': 'value14575',
    'key51568': 'value78901',
    'key82335': 'value38892',
    'key32598': 'value93549',
    'key28382': 'value10166',
    'key76273': 'value15730',
},
    {
    'id': 17527491156838,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Brenda Reynolds',
    'address': '24700 Robert Causeway Apt. 992\nGreenview, MA 47850',
    'text': 'Statement attack push mean college. Field board but pass report. Carry face number art by.',
    'email': 'john66@example.org',
    'phone_number': '+1-490-478-1072x01876',
    'json': {
    'name': 'Jim Snyder',
    'address': '6750 Crawford Greens Apt. 262\nRiceton, NC 70133',
},
    'key51762': 'value97939',
    'key34425': 'value31603',
    'key70008': 'value53264',
},
    {
    'id': 17527491156850,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Amber Foster',
    'address': '61451 Sanchez Manor\nPort Dawn, LA 92838',
    'text': 'Interesting sure the much. Provide yet resource. Catch threat morning born natural power bring political.\nStrong Mrs though subject dinner. Second board decision create. Past its four plant.',
    'email': 'donaldstrong@example.org',
    'phone_number': '(710)539-1944x06585',
    'json': {
    'name': 'Alan Saunders',
    'address': '91038 Katie Port\nPort Gloriabury, ID 91064',
},
    'key58067': 'value16284',
    'key48607': 'value32583',
    'key21492': 'value15066',
    'key2473': 'value6919',
    'key17653': 'value53980',
    'key6711': 'value64115',
    'key25111': 'value36',
    'key8629': 'value41936',
    'key87198': 'value18260',
},
    {
    'id': 17527491156862,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Robert Ward',
    'address': '192 Daryl Crossing\nNew Robert, PW 48283',
    'text': 'Fill road maybe simply war serious occur. Remember city then. Environmental record heavy hope.\nPurpose since adult just place. Thousand score sit.',
    'email': 'fpatterson@example.com',
    'phone_number': '7356928816',
    'json': {
    'name': 'Shaun Oliver',
    'address': '70810 Williams Tunnel Suite 971\nGlenland, MH 26078',
},
    'key62352': 'value82519',
},
    {
    'id': 17527491156873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Stephanie Franklin',
    'address': '8676 Gavin Corners\nEast Jacob, GU 13377',
    'text': 'Theory team rich defense energy such nor. Outside accept song century. Republican decide reduce friend Congress.\nSkill system heavy another project north. Particularly finally what this.',
    'email': 'andersonkenneth@example.net',
    'phone_number': '+1-991-906-1043x586',
    'json': {
    'name': 'Robert Gonzales',
    'address': '3873 Monica Junction Apt. 973\nWest Tiffanyview, LA 02443',
},
    'key48173': 'value95167',
},
    {
    'id': 17527491156885,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Mrs. Valerie Torres PhD',
    'address': '039 Owen Underpass Apt. 385\nLake Christina, CO 12537',
    'text': 'Ahead responsibility set think open argue authority. Major six feel consider plan science. Commercial others enter charge couple leave tell.\nAvailable toward term seem southern group.',
    'email': 'dturner@example.net',
    'phone_number': '348.266.9481x30431',
    'json': {
    'name': 'Ashley Hart',
    'address': '50714 Reed Track\nVegaport, DE 10009',
},
    'key91823': 'value49758',
    'key40032': 'value87015',
    'key43335': 'value31111',
    'key67683': 'value52956',
    'key26122': 'value43693',
    'key32303': 'value40170',
    'key5153': 'value72570',
    'key80373': 'value70365',
},
    {
    'id': 17527491156897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Madison Wolfe',
    'address': '6857 Williams Spring\nVasquezhaven, MI 51628',
    'text': 'Low PM executive wide account civil. Situation box between control. Movie follow bit top know ball.',
    'email': 'smithanne@example.net',
    'phone_number': '001-929-387-8767x292',
    'json': {
    'name': 'Amanda Hurst',
    'address': '2108 King Views\nSarahchester, IA 08487',
},
    'key239': 'value23849',
    'key71619': 'value6496',
    'key9722': 'value5370',
    'key70267': 'value33993',
},
    {
    'id': 17527491156908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'John Mathis',
    'address': '139 Timothy Highway Suite 029\nBaileymouth, PR 98662',
    'text': 'Have specific campaign measure want weight.\nFollow recent child little sell edge finally. Decade fish nearly. Threat career continue popular success.',
    'email': 'bobbyarnold@example.org',
    'phone_number': '001-484-789-2370',
    'json': {
    'name': 'Kristie Alvarado',
    'address': '0444 Hale Drive\nMicheleport, DC 64818',
},
    'key87182': 'value49419',
    'key26762': 'value81374',
    'key83749': 'value32332',
    'key31833': 'value28820',
    'key88148': 'value36242',
    'key11823': 'value31536',
    'key76621': 'value8686',
    'key35862': 'value39214',
    'key79693': 'value18280',
    'key15502': 'value67825',
},
    {
    'id': 17527491156921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'James Richmond',
    'address': '288 Kevin Glen\nEast James, KS 77872',
    'text': 'Prove high under discussion to. Pass research which reality. Difficult beautiful write subject would.\nForward tend Democrat with rich. Ground hair speech unit. Within day tax weight letter.',
    'email': 'jenniferavery@example.org',
    'phone_number': '708.957.5407x8214',
    'json': {
    'name': 'John Scott',
    'address': '8058 Frederick Unions Suite 854\nPort Ashley, NE 45264',
},
    'key87546': 'value9252',
    'key75611': 'value23940',
    'key51928': 'value62837',
    'key59062': 'value94323',
},
    {
    'id': 17527491156933,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Mary Lopez',
    'address': '906 Jeffrey Fall\nTraciland, SD 70354',
    'text': 'Truth realize election recent. Play rich investment war science place line.\nStory always management national. While simple foreign political. With board trade small.',
    'email': 'lori33@example.org',
    'phone_number': '001-777-265-1788',
    'json': {
    'name': 'Angela Frank',
    'address': '9056 Sanders Ways\nDanielton, IL 45584',
},
    'key38405': 'value96917',
    'key2016': 'value77930',
    'key39545': 'value28521',
    'key17412': 'value48504',
    'key6060': 'value96868',
    'key44543': 'value14055',
    'key28256': 'value75576',
    'key49730': 'value95001',
    'key68296': 'value63542',
},
    {
    'id': 17527491156943,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Blake Johnson',
    'address': '078 Thompson Drives\nWest Ryan, NH 55113',
    'text': 'Position author already. Detail number matter staff him like. Bad tough during left.',
    'email': 'xjackson@example.org',
    'phone_number': '840-802-5100x923',
    'json': {
    'name': 'Austin French IV',
    'address': '89159 Gardner Plaza Suite 747\nLake Zacharyborough, CO 93147',
},
    'key50773': 'value52650',
    'key66265': 'value92529',
    'key90698': 'value69754',
},
    {
    'id': 17527491156954,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Thomas Owens',
    'address': '51124 Christine Locks\nMarkstad, AS 88970',
    'text': 'Film red toward seem become safe clear. Three agreement drug nice eight against. Name modern black. Policy possible cost cultural social choose.',
    'email': 'foliver@example.com',
    'phone_number': '(439)684-0802x56863',
    'json': {
    'name': 'Sarah Barrett DVM',
    'address': '4071 John Canyon\nWest Daniel, MD 33695',
},
    'key94756': 'value21402',
    'key96648': 'value17786',
    'key5961': 'value14268',
    'key37281': 'value12973',
},
    {
    'id': 17527491156965,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Kenneth Owens',
    'address': '988 Michael Square\nGomezhaven, OR 87387',
    'text': 'Dark real thus. Less us pretty strong. Voice per wait.\nShort sister phone dog. Someone factor what painting environment. Quality travel nature indicate address compare option.',
    'email': 'ymiller@example.net',
    'phone_number': '5935242455',
    'json': {
    'name': 'Thomas Jones',
    'address': '3217 Dean Heights\nSouth Stephaniebury, NY 16303',
},
    'key14302': 'value35553',
    'key634': 'value88293',
    'key71124': 'value23641',
    'key80774': 'value23554',
    'key86714': 'value2815',
    'key35937': 'value3122',
    'key64227': 'value44518',
},
    {
    'id': 17527491156976,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Christian Taylor',
    'address': '0501 Jeffery Plain Suite 329\nSouth Andrew, VA 63543',
    'text': 'Talk rise international whatever test. Space say them people factor.\nLook which which if line these fear. Should agreement over size.\nStage play window different.',
    'email': 'qwatson@example.org',
    'phone_number': '(202)434-0093x739',
    'json': {
    'name': 'Eric Cole',
    'address': '4129 Wallace Viaduct\nJaniceberg, WA 73374',
},
    'key87302': 'value36709',
    'key86261': 'value57685',
    'key49625': 'value87068',
    'key62516': 'value95330',
    'key88560': 'value86669',
},
    {
    'id': 17527491156987,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Chelsea Fisher',
    'address': '19959 Kim Groves Apt. 221\nNatalieburgh, MA 84999',
    'text': 'Image audience stand daughter trial president. Billion seem oil be late prevent great.\nMorning personal character. Protect position response research better clear. Bit both smile without economic.',
    'email': 'nicolegalloway@example.net',
    'phone_number': '654.612.8927x16619',
    'json': {
    'name': 'Brooke Jones',
    'address': '11295 Hines Road\nPort Harrymouth, SD 26213',
},
    'key94777': 'value81855',
    'key13451': 'value74076',
    'key12444': 'value67607',
},
    {
    'id': 17527491156998,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'John Dominguez',
    'address': '7659 Wilson Trace\nLorihaven, NV 32370',
    'text': 'Treatment oil once experience huge. Deep discover nor base let. Off left available painting.\nStand issue trip mind lay probably. Want act detail.',
    'email': 'regina50@example.com',
    'phone_number': '001-534-912-0234x249',
    'json': {
    'name': 'Bradley Cervantes',
    'address': '65578 White Way\nStuartport, NV 17305',
},
    'key52727': 'value70285',
},
    {
    'id': 17527491157009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Matthew Cox',
    'address': '772 Michelle Neck Apt. 905\nCoopershire, UT 15716',
    'text': 'West coach life teach cell amount. Child she development condition beyond. Water yeah require business decade ball international.',
    'email': 'kelseymartin@example.org',
    'phone_number': '7639769531',
    'json': {
    'name': 'Elizabeth Harper',
    'address': 'PSC 8683, Box 9712\nAPO AA 57915',
},
    'key12661': 'value38058',
    'key38494': 'value64991',
    'key79835': 'value86055',
    'key6183': 'value66440',
    'key21394': 'value70499',
    'key96306': 'value20606',
    'key11063': 'value34348',
},
    {
    'id': 17527491157019,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Darren Ross',
    'address': '56272 Rodriguez Ford Apt. 592\nHayneschester, ME 15930',
    'text': 'Thank similar become total live high. Approach remain now support process art. Special education others because hour pull none offer.',
    'email': 'danielleallison@example.com',
    'phone_number': '230-770-8919',
    'json': {
    'name': 'Jacob Warren',
    'address': '500 Julie Roads\nJamesfort, PA 36191',
},
    'key13048': 'value14190',
    'key17015': 'value7854',
    'key95067': 'value4525',
    'key35223': 'value75139',
    'key71770': 'value27943',
    'key74114': 'value2251',
    'key98933': 'value9735',
    'key47212': 'value41878',
},
    {
    'id': 17527491157030,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Scott Gonzalez',
    'address': '87911 Taylor Rest\nRobertshaven, WV 41326',
    'text': 'Tax company according relate all thousand claim. Miss as sell they.\nAfter character dream side late technology degree.',
    'email': 'xmurillo@example.net',
    'phone_number': '592.349.4005',
    'json': {
    'name': 'Michael Smith',
    'address': '655 Hill Park\nEast Lisa, WI 69622',
},
    'key32376': 'value47489',
    'key41046': 'value44484',
    'key84469': 'value28527',
    'key77648': 'value84341',
    'key68750': 'value85566',
    'key57098': 'value65415',
},
    {
    'id': 17527491157041,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'April Dickson',
    'address': '0187 Leah Rue\nJohnsonborough, NJ 92473',
    'text': 'Season direction near itself item. Future newspaper draw need good. Stuff level fast government region.\nService popular will arrive live. Through role send car such role prevent receive.',
    'email': 'rileywang@example.com',
    'phone_number': '001-417-856-6303',
    'json': {
    'name': 'Ashley Torres',
    'address': '72835 Little Vista Suite 042\nSuzannebury, AL 94815',
},
    'key20457': 'value79281',
    'key82173': 'value6831',
    'key46483': 'value41799',
    'key18360': 'value94496',
    'key96173': 'value23141',
},
    {
    'id': 17527491157052,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Michael Peters',
    'address': '39123 James Rapids\nMeyertown, AZ 59664',
    'text': 'Stock single company. Site middle skill wife goal.\nPast study task relate. Stand standard usually its memory example area. Agree morning line road.\nExpert wind end deep special win door pass.',
    'email': 'stevensawyer@example.net',
    'phone_number': '395.256.7743x37545',
    'json': {
    'name': 'Anthony Jacobs',
    'address': '158 Kimberly Stream Apt. 784\nSouth Erica, IL 65697',
},
    'key60196': 'value96192',
    'key3376': 'value56620',
    'key92376': 'value68189',
    'key3096': 'value24366',
    'key2425': 'value90885',
    'key38744': 'value18771',
    'key44464': 'value12281',
    'key13678': 'value74976',
},
    {
    'id': 17527491157064,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Bryan Gaines',
    'address': '874 Renee Neck Suite 093\nEast Ellen, PW 81904',
    'text': 'Tonight property rich white increase learn past. Current specific director common TV.\nOut stand simple. Rise state west thus within. Realize real their away.',
    'email': 'scottflores@example.com',
    'phone_number': '(218)383-5583',
    'json': {
    'name': 'Deborah Garcia',
    'address': '0135 Pamela Track\nWest Maria, MS 36545',
},
    'key92130': 'value10204',
    'key14079': 'value88401',
    'key90817': 'value47394',
    'key24643': 'value62503',
    'key38324': 'value92969',
    'key10036': 'value39802',
    'key47226': 'value68215',
    'key59839': 'value20538',
    'key32365': 'value35517',
    'key72264': 'value327',
},
    {
    'id': 17527491157075,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Lisa Jackson',
    'address': '45149 Lauren Squares\nGarciaburgh, WY 67480',
    'text': 'Check investment attack her believe. Million person list matter stage leader alone. Nothing wonder situation thank difficult himself.\nNo yard prepare seek research. Recently move simply form.',
    'email': 'williamsjaime@example.com',
    'phone_number': '001-686-418-7926',
    'json': {
    'name': 'Mary Jennings',
    'address': 'PSC 7017, Box 5233\nAPO AA 45215',
},
    'key45266': 'value57748',
    'key99180': 'value94352',
    'key50226': 'value65031',
},
    {
    'id': 17527491157085,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Donna Nelson',
    'address': '5895 Susan Valleys\nSouth Brittany, GA 35883',
    'text': 'Field coach light. Order job economy century upon my trade want.\nCharacter provide real condition executive any billion truth.',
    'email': 'savannahbrewer@example.net',
    'phone_number': '001-701-850-3035x2012',
    'json': {
    'name': 'Deborah Horn',
    'address': '54038 Walker Estates\nMooreview, TX 44460',
},
    'key89040': 'value26201',
    'key29146': 'value88704',
    'key87644': 'value82285',
    'key96453': 'value91341',
},
    {
    'id': 17527491157096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Robert Shaw',
    'address': '2495 Mcgrath Groves Suite 530\nWebbton, TN 53554',
    'text': 'Candidate natural probably story listen many. Center member building beat.\nBring level American girl about.\nPlan throughout figure message. Us thought his chance result.',
    'email': 'rachael62@example.org',
    'phone_number': '+1-964-768-2213x97701',
    'json': {
    'name': 'Andrea Chavez',
    'address': '5018 Green Hill\nDannyland, WI 45627',
},
    'key3723': 'value95040',
    'key78565': 'value53733',
    'key38785': 'value14721',
    'key59273': 'value41150',
    'key31659': 'value56934',
},
    {
    'id': 17527491157107,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Tabitha Mclaughlin',
    'address': '2116 Cox Locks Apt. 917\nPort Bradborough, IN 90334',
    'text': 'All tend stand end leg write. Decide leg always news see natural car. Relationship bad role add.',
    'email': 'washingtonalexandria@example.com',
    'phone_number': '(254)929-5499x93378',
    'json': {
    'name': 'William Delgado',
    'address': '1939 Deborah Grove\nLamfurt, OR 37274',
},
    'key62191': 'value53990',
    'key40186': 'value53784',
    'key84892': 'value34450',
    'key57419': 'value5766',
    'key37805': 'value36093',
    'key97852': 'value35535',
    'key3049': 'value70409',
    'key17392': 'value46151',
    'key47238': 'value45079',
},
    {
    'id': 17527491157118,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Carrie Ross',
    'address': '2715 Boyd Point\nAlyssamouth, NM 72728',
    'text': 'Consider democratic together about. Garden growth instead indicate two.\nOf sell ball professional onto. Increase produce break certain book say.',
    'email': 'kellysmith@example.net',
    'phone_number': '963.555.6216x76387',
    'json': {
    'name': 'Dale Baker',
    'address': '44806 Barnes Track\nEmilyport, AL 82912',
},
    'key63603': 'value29646',
    'key77479': 'value82673',
    'key83246': 'value50539',
    'key47302': 'value55936',
    'key84850': 'value23251',
    'key71485': 'value3533',
},
    {
    'id': 17527491157130,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Douglas Allen',
    'address': '37093 Dylan Groves\nWest Brianbury, FL 53932',
    'text': 'Water series military receive lawyer. Produce present together once. Development occur writer image away.\nStreet building story court. Work reveal meeting.',
    'email': 'dstokes@example.com',
    'phone_number': '258-879-4390x097',
    'json': {
    'name': 'Tamara Hernandez',
    'address': 'PSC 8183, Box 4677\nAPO AE 03721',
},
    'key25457': 'value84532',
    'key69684': 'value96387',
},
    {
    'id': 17527491157139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Christopher Barnett',
    'address': '925 Jose Loaf Apt. 243\nLake Seanbury, HI 56052',
    'text': 'Simple conference garden join old. Institution southern analysis free cell several determine real.\nRespond how grow give accept. Amount contain whether his.',
    'email': 'blake05@example.org',
    'phone_number': '735.325.9936x594',
    'json': {
    'name': 'David Perez',
    'address': '950 Allen Well Suite 571\nRobertmouth, NV 68832',
},
    'key43060': 'value26757',
    'key98004': 'value7592',
    'key1197': 'value20122',
    'key94553': 'value11001',
    'key89261': 'value2000',
    'key88907': 'value22691',
},
    {
    'id': 17527491157149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'David Long',
    'address': '97322 Tammy Roads\nWellshaven, RI 10738',
    'text': 'Budget grow head because knowledge defense send. Level few season evening company. Environment pay pay soon provide responsibility site.',
    'email': 'nicole69@example.com',
    'phone_number': '926.322.6464x36425',
    'json': {
    'name': 'Destiny Ho',
    'address': '9672 Xavier Island Apt. 916\nRodriguezfurt, CO 05068',
},
    'key27016': 'value8935',
    'key3592': 'value2479',
    'key91835': 'value24739',
    'key96997': 'value61330',
    'key51656': 'value3491',
    'key38893': 'value23037',
    'key54390': 'value5941',
    'key59719': 'value47129',
    'key31752': 'value26671',
},
    {
    'id': 17527491157160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Stephanie Edwards',
    'address': '37673 Brown View Apt. 803\nMichaeltown, SC 86481',
    'text': 'Attention person data white single. Brother ok off do them cold computer source. American human along project glass clearly.',
    'email': 'brianthomas@example.net',
    'phone_number': '(698)382-1501x32382',
    'json': {
    'name': 'Charles Fernandez',
    'address': '47606 Melanie River\nAutumnhaven, MS 86185',
},
    'key36297': 'value97492',
    'key67622': 'value55960',
    'key75874': 'value16584',
    'key27988': 'value94397',
    'key49395': 'value12967',
},
    {
    'id': 17527491157171,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Richard West',
    'address': '85190 Thomas View\nSamanthamouth, LA 66517',
    'text': 'Side maybe education. Think your east fact upon cold ever. Customer compare give.\nLet country performance avoid. Strong subject defense which investment build others quality.',
    'email': 'brownjeffery@example.net',
    'phone_number': '(399)822-5541x600',
    'json': {
    'name': 'Regina Robinson',
    'address': '73605 Arias Islands Apt. 595\nSouth Vincent, KY 94459',
},
    'key12021': 'value51429',
    'key52593': 'value32381',
    'key74950': 'value2955',
    'key62406': 'value28324',
    'key10803': 'value84781',
    'key28230': 'value9473',
    'key66472': 'value96484',
},
    {
    'id': 17527491157183,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Kimberly Andrade',
    'address': '1347 Walters Ranch Suite 131\nSouth Donaldtown, AS 81914',
    'text': 'More establish think catch. Artist record fill black strategy take. Cover affect bring industry individual material.',
    'email': 'huangmichael@example.org',
    'phone_number': '816-371-7900x54042',
    'json': {
    'name': 'Debbie Rodriguez',
    'address': '37098 Jackson Fords Apt. 747\nEast Danielle, OR 81215',
},
    'key45047': 'value36862',
    'key7829': 'value48562',
    'key86448': 'value74228',
    'key86773': 'value25352',
    'key54303': 'value58567',
    'key46762': 'value21959',
    'key90482': 'value17323',
    'key46575': 'value30383',
    'key79348': 'value87323',
    'key70718': 'value81269',
},
    {
    'id': 17527491157195,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Dr. Kimberly Shah',
    'address': '8624 Amanda Station Apt. 088\nMuellerfort, PR 95165',
    'text': 'Myself affect those capital activity tax executive act. Matter right remain list old shake. International today establish amount else cup.',
    'email': 'wilsonkatherine@example.net',
    'phone_number': '+1-516-455-8893x43670',
    'json': {
    'name': 'Deborah Welch',
    'address': '7434 Wright Estates\nSouth Christopher, IL 47420',
},
    'key45101': 'value54808',
    'key58562': 'value9140',
    'key47199': 'value75644',
},
    {
    'id': 17527491157206,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Kristina Scott',
    'address': '65460 Ball Track\nEast Marcus, WA 65147',
    'text': 'Democratic attack and white. Together perhaps when prevent main table.',
    'email': 'albert40@example.net',
    'phone_number': '(876)643-3800',
    'json': {
    'name': 'Stacy Hamilton',
    'address': '3904 Brown Station Apt. 070\nNorth Samantha, OH 08108',
},
    'key45587': 'value38299',
    'key2374': 'value35796',
    'key68104': 'value59164',
    'key71697': 'value25849',
    'key47566': 'value63222',
    'key25085': 'value57630',
},
    {
    'id': 17527491157217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Mary Daniel',
    'address': '46386 Dominique Crossroad Apt. 730\nWest David, SD 42873',
    'text': 'Help star no usually. Key choose throw free. Kid letter before need need again.',
    'email': 'daniel46@example.com',
    'phone_number': '942-870-8098',
    'json': {
    'name': 'Michael Juarez',
    'address': 'Unit 7561 Box 6747\nDPO AP 66264',
},
    'key8398': 'value15493',
    'key42538': 'value84516',
    'key81412': 'value57543',
    'key79565': 'value7401',
    'key3014': 'value61507',
    'key4679': 'value16742',
    'key24548': 'value34197',
    'key63665': 'value60048',
    'key20515': 'value24091',
},
    {
    'id': 17527491157225,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Douglas Nelson',
    'address': 'USS Wolf\nFPO AE 93669',
    'text': 'Tax cold exactly ok quickly will guy. Car perform degree painting require send something.\nAlso medical natural.\nMillion why raise fish shake property. Green guess adult minute type so.',
    'email': 'oochoa@example.com',
    'phone_number': '001-619-940-7854',
    'json': {
    'name': 'Adam Murphy',
    'address': '66736 Barry Cliffs\nNorth Markburgh, WA 29428',
},
    'key1563': 'value8705',
    'key30646': 'value55863',
},
    {
    'id': 17527491157234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Todd Adams',
    'address': 'PSC 3569, Box 4063\nAPO AP 47367',
    'text': 'Tree general west worry authority health garden. All two by home before painting bag.\nProperty service pay American end natural ever. Pass hair nor.',
    'email': 'lisahernandez@example.org',
    'phone_number': '001-885-923-5065x595',
    'json': {
    'name': 'Tina Huerta',
    'address': '22987 Shane Wells\nChristianmouth, NM 29246',
},
    'key24367': 'value87082',
},
    {
    'id': 17527491157244,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'April Hall',
    'address': 'USNV Johnson\nFPO AP 94041',
    'text': 'Morning ahead worry economy traditional. Space range there have hair.\nValue may data nature fact compare consumer model.\nFrom best want else. Decade even staff easy here or rather surface.',
    'email': 'lori54@example.com',
    'phone_number': '450-530-0146',
    'json': {
    'name': 'Keith Armstrong',
    'address': 'PSC 4081, Box 0418\nAPO AA 43859',
},
    'key41636': 'value59627',
    'key81317': 'value16723',
    'key51865': 'value31795',
    'key16739': 'value19229',
    'key28246': 'value57921',
    'key88929': 'value59128',
    'key65701': 'value91306',
    'key5392': 'value30377',
    'key28705': 'value76975',
    'key31523': 'value77880',
},
    {
    'id': 17527491157251,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Taylor Faulkner',
    'address': '84597 Green Shoals Apt. 502\nBeckerton, NY 60505',
    'text': 'Response want popular imagine my. Our discussion expert nice whatever care.\nClaim finish hair again follow.',
    'email': 'reevesreginald@example.org',
    'phone_number': '910.543.2668x83632',
    'json': {
    'name': 'Terri Park',
    'address': 'Unit 0777 Box 7424\nDPO AP 59819',
},
    'key31483': 'value69275',
    'key14974': 'value94475',
    'key86660': 'value18608',
    'key59041': 'value20596',
    'key37217': 'value57585',
    'key89884': 'value80446',
    'key77793': 'value23634',
    'key91755': 'value7106',
},
    {
    'id': 17527491157261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Christopher Orozco',
    'address': '132 Berry Village Suite 576\nKyleville, MP 36502',
    'text': 'Spring cut indeed allow network would. Performance more call control single. Great page push traditional between. Than one dark him indicate become.',
    'email': 'yjohnson@example.com',
    'phone_number': '273.996.0548',
    'json': {
    'name': 'Elizabeth Martinez',
    'address': '676 Judy Bridge Suite 261\nNorth Larryland, DC 36958',
},
    'key21883': 'value3413',
    'key22505': 'value95752',
    'key51893': 'value95952',
    'key97365': 'value48789',
    'key11665': 'value57497',
    'key36089': 'value61051',
    'key89548': 'value55885',
    'key15734': 'value61573',
},
    {
    'id': 17527491157272,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Kevin Hopkins',
    'address': '2192 Ware Mount Suite 419\nNew Erinborough, IA 84700',
    'text': 'Person once create task voice area. This local consumer billion.\nSmile site continue including. Benefit form economy direction discover mouth wall. Science yourself guess could recognize.',
    'email': 'michael31@example.org',
    'phone_number': '001-224-459-9731x069',
    'json': {
    'name': 'Amber Roy',
    'address': '0929 Amanda Spurs Suite 700\nEast Diane, IL 58224',
},
    'key12668': 'value27974',
    'key78105': 'value34072',
    'key38015': 'value63129',
    'key27552': 'value89183',
    'key48472': 'value12473',
    'key89206': 'value17564',
    'key25465': 'value56879',
},
    {
    'id': 17527491157283,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Jose Newman',
    'address': '26665 Colon Mews Suite 542\nCaldwellfort, MS 85200',
    'text': 'World situation participant chair water subject. Both wide bag develop wrong experience seek. Together vote down benefit kitchen second.',
    'email': 'christophermartin@example.com',
    'phone_number': '972-288-5604',
    'json': {
    'name': 'Melissa Savage',
    'address': '17616 Mccoy Forks\nEast Lisa, MO 42553',
},
    'key80205': 'value74104',
    'key78560': 'value14157',
},
    {
    'id': 17527491157295,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Mary Harrison',
    'address': 'PSC 2155, Box 3723\nAPO AP 13510',
    'text': 'Really science prepare news contain purpose.\nOf machine type model beat doctor next. Tv mouth arm life commercial pretty. Same reason pressure budget learn health simple investment.',
    'email': 'hunterscott@example.net',
    'phone_number': '(936)325-1503x66845',
    'json': {
    'name': 'Donna Coleman',
    'address': '9789 Jones Oval Apt. 413\nPort Angelachester, NV 11181',
},
    'key89625': 'value62014',
    'key87328': 'value16234',
    'key17730': 'value88865',
    'key30870': 'value33773',
    'key17890': 'value98491',
},
    {
    'id': 17527491157305,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Jennifer Singh',
    'address': '535 Barry Stravenue\nMartinezchester, ND 94344',
    'text': 'Produce account writer. Bar provide language become score even network tough.\nThrow manager open subject indeed value assume position. Alone room member phone industry account.',
    'email': 'yvettefischer@example.net',
    'phone_number': '001-704-288-7430x5150',
    'json': {
    'name': 'Thomas Miller',
    'address': '5291 Vincent Streets Suite 717\nNorth Wayne, FM 86224',
},
    'key15212': 'value97603',
    'key676': 'value44953',
    'key31141': 'value74390',
    'key21045': 'value39613',
    'key92327': 'value2722',
    'key69837': 'value34797',
    'key51349': 'value85140',
    'key38783': 'value26179',
},
    {
    'id': 17527491157316,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Matthew Johnston',
    'address': '5847 Christopher Overpass Suite 037\nTimothyshire, KS 37663',
    'text': 'End establish author food. Skill ask wide necessary force. Order billion whole describe score alone until. People put off life finally.',
    'email': 'umolina@example.com',
    'phone_number': '(855)922-5493x3738',
    'json': {
    'name': 'Eric Young',
    'address': '256 Arthur Rest\nWest Rachaelside, GU 04735',
},
    'key79052': 'value36389',
    'key79512': 'value15056',
    'key33132': 'value39022',
    'key24900': 'value22149',
},
    {
    'id': 17527491157326,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Stacey Haas',
    'address': '01796 Ramsey Summit Apt. 361\nNew Tracyfurt, MI 12246',
    'text': 'Manage significant factor around art off get anything. Contain much sound necessary us quite. Water economy phone wide entire least attorney Republican.',
    'email': 'andrewstyler@example.com',
    'phone_number': '6337781293',
    'json': {
    'name': 'Kathryn Thomas',
    'address': 'PSC 1072, Box 3861\nAPO AA 49886',
},
    'key96517': 'value56087',
    'key68905': 'value7175',
    'key10590': 'value99686',
    'key46333': 'value68952',
},
    {
    'id': 17527491157335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Justin Williams',
    'address': '4714 Grant Rue\nReedtown, IN 57725',
    'text': 'Agency without street business. Try have beautiful response station year. Eye morning someone me.\nPressure music return raise interesting. Establish impact learn wait region management.',
    'email': 'lisahill@example.com',
    'phone_number': '8535055617',
    'json': {
    'name': 'James Santiago',
    'address': '883 Wilson Alley\nRogersland, MO 99890',
},
    'key25286': 'value67123',
    'key80121': 'value3714',
    'key76662': 'value52739',
},
    {
    'id': 17527491157347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Jamie Tran',
    'address': '506 Reed Ports\nWest Kathryn, NY 38606',
    'text': 'Mrs various science office low like hot look. Quite necessary guy outside.',
    'email': 'jennifer48@example.net',
    'phone_number': '001-477-376-5425x7003',
    'json': {
    'name': 'Tonya Munoz',
    'address': '9836 Brian Course\nNew Madisonberg, IN 04793',
},
    'key38771': 'value58382',
},
    {
    'id': 17527491157357,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'April Ramirez',
    'address': '83937 Scott Viaduct Suite 218\nPort Carl, AS 15907',
    'text': 'System party black walk hotel eight include less. Term decide decision notice cause. Business spend phone series whom hard in.',
    'email': 'youngdaniel@example.org',
    'phone_number': '(200)743-8051',
    'json': {
    'name': 'Stephanie Case',
    'address': 'USCGC Freeman\nFPO AP 72949',
},
    'key27665': 'value64298',
    'key26324': 'value23603',
},
    {
    'id': 17527491157368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Patricia Reynolds',
    'address': '8494 David Inlet\nDonaldmouth, MH 21098',
    'text': 'Rise seat pick back maintain. Wind rate call four buy case.\nEmployee magazine amount name. Upon character whom ball seem.\nHappen tree some article how music. Particular them station responsibility.',
    'email': 'hthompson@example.com',
    'phone_number': '001-870-560-1148',
    'json': {
    'name': 'Janet Fischer',
    'address': '5178 Jade Orchard\nNew Kyle, LA 65415',
},
    'key87034': 'value52370',
    'key53075': 'value89718',
},
    {
    'id': 17527491157378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Sherry Boone',
    'address': '759 Williams Pass\nNorth Melissafort, VI 54217',
    'text': 'Care write follow late college above billion. Begin ten sport. Meeting mouth simple though stay smile me.\nCity plant before man ago million. Into meeting color per.',
    'email': 'eevans@example.net',
    'phone_number': '(372)454-3467x01706',
    'json': {
    'name': 'Ryan Spence',
    'address': '1020 Sarah Court Suite 748\nSouth Tina, NV 46468',
},
    'key68189': 'value89185',
    'key2960': 'value79256',
    'key53852': 'value72993',
    'key75398': 'value12655',
    'key79982': 'value8303',
    'key31222': 'value84488',
    'key42995': 'value62929',
    'key59876': 'value59740',
},
    {
    'id': 17527491157389,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Sheri Gibson',
    'address': 'PSC 7970, Box 8440\nAPO AE 26394',
    'text': 'Partner detail toward strong. Million alone of service.\nBusiness race dark however use set. Pressure bar know general other especially continue eat. Personal teacher mind yeah event.',
    'email': 'msalinas@example.net',
    'phone_number': '642.945.9452x7728',
    'json': {
    'name': 'William Schwartz',
    'address': '1108 Stephanie Village\nPort Michelleburgh, OK 08962',
},
    'key41441': 'value24062',
    'key34536': 'value162',
    'key62423': 'value17848',
    'key92314': 'value30117',
},
    {
    'id': 17527491157398,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Steven Rodriguez',
    'address': '722 Haynes Points\nLake Kevin, MT 52603',
    'text': 'Writer stay especially determine program child. Something hard spend it work rich else. Role cut agreement such report hand.',
    'email': 'paynethomas@example.com',
    'phone_number': '9142397248',
    'json': {
    'name': 'Gabriel Moore',
    'address': '91395 Smith Key Suite 632\nPort Alexandriashire, AS 37419',
},
    'key81595': 'value36928',
    'key44958': 'value67603',
    'key9041': 'value30403',
    'key65033': 'value98971',
    'key77564': 'value41364',
    'key86818': 'value67793',
    'key4074': 'value51217',
    'key90086': 'value23498',
    'key40812': 'value90447',
    'key30087': 'value67904',
},
    {
    'id': 17527491157409,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Connie Keith',
    'address': '02022 Joseph Shores\nWest Jessica, AR 83347',
    'text': 'Order account table. Safe show before road.\nSouthern high southern imagine make to. You ability peace. Officer fill what third.\nEmployee officer author officer team new.',
    'email': 'james62@example.net',
    'phone_number': '264-518-8152x42926',
    'json': {
    'name': 'Heather Welch DVM',
    'address': '270 Green Lodge Apt. 502\nThomasfort, ID 13712',
},
    'key97694': 'value73068',
    'key29028': 'value60659',
    'key20185': 'value90590',
    'key46420': 'value88912',
    'key9274': 'value97691',
    'key93276': 'value52984',
},
    {
    'id': 17527491157420,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Keith Cook',
    'address': '323 Smith Passage\nBruceland, HI 54721',
    'text': 'Rate nearly yard memory employee.\nMorning discover item risk make door. Hope culture worker sense side central.\nSo scene say say. Sometimes maintain story wide fight key up.',
    'email': 'samantha21@example.org',
    'phone_number': '(886)892-0486x1738',
    'json': {
    'name': 'Lindsay Valdez',
    'address': '325 Cooper Walks Apt. 531\nPort Andrea, WY 68250',
},
    'key54861': 'value25972',
    'key57621': 'value56938',
    'key54858': 'value3658',
},
    {
    'id': 17527491157430,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Jacob Valdez',
    'address': '90937 Ward Square Suite 974\nSouth Matthew, NV 79254',
    'text': 'Market eat finish station often.\nProve manage question left. Son side think if mean respond blood.',
    'email': 'miranda63@example.net',
    'phone_number': '565-371-8656x40884',
    'json': {
    'name': 'Jasmine Mcknight',
    'address': '5456 Meyers Skyway Apt. 382\nLake Julieport, WV 56265',
},
    'key48966': 'value29615',
    'key59635': 'value50298',
    'key57112': 'value77305',
    'key48516': 'value41637',
    'key70523': 'value54123',
    'key58354': 'value77105',
    'key75076': 'value32950',
    'key64285': 'value19837',
},
    {
    'id': 17527491157441,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Mitchell Choi',
    'address': 'PSC 2880, Box 9409\nAPO AP 38403',
    'text': 'Rock knowledge final moment finally create same. Mean evidence cut what opportunity bad collection.\nWater them nature beautiful next high. East call send range determine trial father.',
    'email': 'michaeljohnson@example.org',
    'phone_number': '3539226958',
    'json': {
    'name': 'Edward Logan',
    'address': 'PSC 9433, Box 7601\nAPO AE 57576',
},
    'key64591': 'value86126',
    'key25699': 'value70100',
    'key99557': 'value83626',
    'key80719': 'value39743',
    'key21206': 'value74190',
    'key21366': 'value46693',
    'key90224': 'value45952',
    'key94507': 'value66224',
    'key44210': 'value59762',
    'key7525': 'value22462',
},
    {
    'id': 17527491157449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Scott Weaver',
    'address': 'Unit 1936 Box 1812\nDPO AA 79186',
    'text': 'Year also available true provide catch nice our.\nParticipant view offer area clear clearly option. Worry drive use responsibility again. Big church example TV knowledge couple another spend.',
    'email': 'margaret58@example.com',
    'phone_number': '(430)676-1603x01773',
    'json': {
    'name': 'April Velasquez',
    'address': '8530 Nicole Meadow\nMercadoberg, NC 85740',
},
    'key77715': 'value5347',
    'key38234': 'value53537',
},
    {
    'id': 17527491157458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Vanessa Riley',
    'address': '78808 Lee Gardens\nSouth Justin, AK 41610',
    'text': 'Unit miss per. Consider number first consider instead sort. Police program example million.\nFact alone agree wait by toward executive. Human same sell provide study investment.',
    'email': 'jessica98@example.org',
    'phone_number': '403-525-0760x00097',
    'json': {
    'name': 'Mrs. Jessica Cohen',
    'address': '008 Courtney Street Apt. 396\nLake Scott, WA 94119',
},
    'key5844': 'value11560',
    'key37122': 'value55867',
    'key77851': 'value16020',
    'key14737': 'value4587',
    'key89401': 'value42752',
    'key26394': 'value7834',
    'key29209': 'value93940',
    'key270': 'value28806',
},
    {
    'id': 17527491157468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Jacob Clements',
    'address': '5155 Briana Rue Apt. 534\nVasqueztown, UT 35749',
    'text': 'Certainly size town resource. Skin thought always animal design.',
    'email': 'gallaghereric@example.org',
    'phone_number': '3169982393',
    'json': {
    'name': 'Jeffery Bennett',
    'address': '7330 Heidi Cove\nBenjaminburgh, OH 15445',
},
    'key38954': 'value47221',
    'key67687': 'value3457',
    'key9393': 'value53356',
},
    {
    'id': 17527491157480,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Brian Price',
    'address': '5042 Richard Street\nPort Margaret, CT 26548',
    'text': 'Father according Congress. Direction more change moment.\nQuestion policy wonder when blood. Garden PM always structure.',
    'email': 'kristen32@example.org',
    'phone_number': '+1-502-561-1884',
    'json': {
    'name': 'Nicole Bowman',
    'address': '5057 Raymond Rapids\nWilliamshire, MO 29903',
},
    'key60233': 'value9215',
    'key77140': 'value56493',
    'key44880': 'value4794',
    'key48653': 'value10263',
},
    {
    'id': 17527491157490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Patrick Padilla',
    'address': '545 Wilson Alley\nReedland, WY 94493',
    'text': 'Go option after road. Throw other term other.\nBest specific fish floor. Member certainly serve on budget model.\nThan always debate result high life unit. Not receive people issue leg floor.',
    'email': 'davisalvin@example.org',
    'phone_number': '3804171323',
    'json': {
    'name': 'Sarah Simmons',
    'address': '9932 Owens Well Apt. 310\nVictoriamouth, WI 26329',
},
    'key11329': 'value84621',
    'key37788': 'value4992',
    'key64605': 'value15959',
    'key36663': 'value15285',
    'key77692': 'value16421',
},
    {
    'id': 17527491157502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Eric Blackwell PhD',
    'address': 'Unit 1084 Box 5930\nDPO AE 38737',
    'text': 'Congress too accept play. Fear tax themselves inside white food friend. Away long participant federal compare. Loss loss responsibility main pay door theory.',
    'email': 'todd21@example.net',
    'phone_number': '(969)510-1045x88916',
    'json': {
    'name': 'Joel Black',
    'address': '76472 Ana Alley\nDavischester, HI 76946',
},
    'key44242': 'value88664',
    'key73867': 'value91524',
},
    {
    'id': 17527491157510,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'April Turner',
    'address': '0448 Marcus Estates Apt. 205\nLake Jessicaport, ID 85815',
    'text': 'History practice watch present side fly leg. Entire marriage score less again behind morning including. Necessary do else about inside important.',
    'email': 'krobbins@example.net',
    'phone_number': '5296015171',
    'json': {
    'name': 'Crystal Brock',
    'address': '057 Horn Wells Suite 328\nJacksonland, WI 21813',
},
    'key13336': 'value14807',
    'key29841': 'value30807',
    'key37874': 'value2517',
    'key87208': 'value90395',
    'key20946': 'value31015',
    'key99122': 'value48722',
    'key14524': 'value4574',
    'key36787': 'value30292',
},
    {
    'id': 17527491157521,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Rachel Gillespie',
    'address': '3394 Jeff Haven Apt. 261\nEast Ambermouth, IL 28058',
    'text': 'Own provide call. Without deep have wear special agreement some.\nBenefit part model election artist far writer. Unit capital first research.',
    'email': 'kelly49@example.org',
    'phone_number': '960-369-9170x1950',
    'json': {
    'name': 'Dennis Wilson',
    'address': '62005 Victoria Drive Suite 608\nRichardsfort, ID 60024',
},
    'key11299': 'value78138',
    'key57547': 'value46553',
    'key80070': 'value89548',
},
    {
    'id': 17527491157531,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Shannon Freeman',
    'address': '755 Franklin Squares Apt. 416\nNorth Vanessa, LA 82891',
    'text': 'Employee area much meeting either produce especially. A always try approach according scientist positive. She form hotel yourself street country since. Easy measure form owner west begin drop.',
    'email': 'james19@example.org',
    'phone_number': '577-549-0623',
    'json': {
    'name': 'Ashley Miller',
    'address': '934 Tanner View Suite 768\nRhodesmouth, VT 02752',
},
    'key67843': 'value10550',
    'key69501': 'value75867',
    'key95777': 'value14526',
    'key25816': 'value13581',
    'key9729': 'value37219',
    'key41871': 'value25702',
},
    {
    'id': 17527491157542,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Theresa Johnson',
    'address': '41913 Evans Valleys\nRonaldton, NC 18358',
    'text': 'Painting compare partner point goal before inside number. Owner goal if key he follow. Time business open star.\nStaff body degree doctor save civil.',
    'email': 'zachary75@example.com',
    'phone_number': '925.523.6899x202',
    'json': {
    'name': 'Vincent Sutton',
    'address': '63362 Monica Landing Suite 953\nWest Ebony, NM 69324',
},
    'key14897': 'value61889',
    'key3965': 'value61926',
},
    {
    'id': 17527491157552,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Christopher Smith',
    'address': '24804 John Freeway Suite 781\nHartburgh, FL 14961',
    'text': 'Option both artist something term like office. Senior time expert control option who grow she. Follow hard economic manage friend itself next.',
    'email': 'clarkdavid@example.org',
    'phone_number': '001-869-839-5916x505',
    'json': {
    'name': 'Thomas Morton',
    'address': '56857 Klein Stream\nNew Katrinaside, UT 66157',
},
    'key18512': 'value22352',
    'key30008': 'value49678',
    'key19646': 'value16282',
    'key13963': 'value48565',
    'key54903': 'value52112',
    'key38227': 'value82343',
    'key2236': 'value32885',
    'key69427': 'value24725',
    'key38224': 'value73806',
    'key19117': 'value36584',
},
    {
    'id': 17527491157564,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Angela Harper',
    'address': '3847 Murray Keys Apt. 239\nNorth Billystad, WV 19880',
    'text': 'Example find nearly street market type. Before truth nothing quickly everybody fine might Republican.\nStory success call lay response staff citizen. Whatever view care.',
    'email': 'christina39@example.com',
    'phone_number': '777-467-4001',
    'json': {
    'name': 'Kenneth Hines',
    'address': '4952 Kathryn Crossroad Apt. 125\nCookhaven, CO 75723',
},
    'key99220': 'value29848',
    'key11964': 'value91731',
    'key41560': 'value11033',
    'key60494': 'value37252',
    'key29370': 'value82833',
},
    {
    'id': 17527491157575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Frank Miller',
    'address': '912 Juan Vista\nNorth Charles, PR 34701',
    'text': 'Woman thought form information accept candidate. News who read appear.\nSome determine small into crime.',
    'email': 'kpacheco@example.net',
    'phone_number': '001-693-588-3600x0320',
    'json': {
    'name': 'Heather Romero',
    'address': '049 Nelson Square\nLake Andreamouth, NM 01179',
},
    'key69571': 'value22442',
},
    {
    'id': 17527491157585,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Katherine Horn',
    'address': '125 Martinez Wall Apt. 597\nBethanyville, MD 97451',
    'text': 'Say others compare at. Reason I beyond call rise argue. Animal manager pretty measure author animal hair. Save material area lead it act science.',
    'email': 'campbelljoseph@example.org',
    'phone_number': '(609)499-3366',
    'json': {
    'name': 'Becky Harrell',
    'address': '9717 Melissa Station Apt. 114\nEast Mario, MI 67146',
},
    'key60218': 'value30661',
    'key51739': 'value81696',
    'key81868': 'value97169',
    'key42953': 'value17564',
    'key63765': 'value47112',
    'key88005': 'value43997',
    'key5319': 'value36610',
    'key42436': 'value55889',
    'key11369': 'value80432',
},
    {
    'id': 17527491157596,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Beth Sanchez',
    'address': '30815 Timothy Meadows Apt. 975\nSouth Gregory, IA 57819',
    'text': 'Eight me size five yeah. Security well call before.\nTax state more market body. Agent probably rock explain. Sometimes tend whose carry worker travel politics name.',
    'email': 'mhatfield@example.net',
    'phone_number': '7295641791',
    'json': {
    'name': 'Jane Gay',
    'address': '62929 Anita Harbors Suite 386\nWest Josephland, DC 66778',
},
    'key99531': 'value87965',
    'key90653': 'value43513',
    'key76701': 'value14983',
    'key23234': 'value51753',
    'key56489': 'value76874',
    'key80085': 'value5640',
    'key34045': 'value46588',
    'key80514': 'value57941',
},
    {
    'id': 17527491157607,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Jennifer Lewis',
    'address': '2650 Michelle Pike Suite 848\nJessicafort, OR 28960',
    'text': 'Team main reveal treat identify side listen. Well view family magazine.\nIndustry organization condition cost research. Off story somebody operation structure wrong run assume.',
    'email': 'wanderson@example.org',
    'phone_number': '653-206-6222x30785',
    'json': {
    'name': 'Robert Brown',
    'address': '3361 Danielle Wall\nNew Darrellport, DC 11115',
},
    'key31615': 'value53703',
    'key75790': 'value15841',
    'key56238': 'value34640',
    'key22073': 'value38141',
},
    {
    'id': 17527491157618,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Michael Smith',
    'address': '437 Marie Islands\nJaniceborough, TN 81197',
    'text': 'Beautiful plan ok save just. Include heavy throughout certainly half camera movement.\nLarge letter decade personal thus father arm.',
    'email': 'melissacain@example.com',
    'phone_number': '7203279430',
    'json': {
    'name': 'Lori Cooper',
    'address': '926 Elizabeth Unions Apt. 078\nSouth Catherine, NJ 51018',
},
    'key69046': 'value4454',
    'key53244': 'value56795',
    'key25564': 'value91337',
},
    {
    'id': 17527491157629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Alexis Romero',
    'address': '51626 Isabella Crossing\nPort Robert, AK 51070',
    'text': 'Occur whether would maintain hope factor. Water through left build produce yet else.',
    'email': 'gregory99@example.net',
    'phone_number': '455.939.3664x999',
    'json': {
    'name': 'Jeffery Rodriguez',
    'address': '2107 Susan Hills Suite 908\nShafferberg, OK 40976',
},
    'key59077': 'value96445',
    'key82785': 'value19433',
    'key41665': 'value77427',
    'key39343': 'value54952',
    'key47563': 'value71218',
    'key80847': 'value86212',
    'key18246': 'value93164',
    'key45688': 'value53028',
},
    {
    'id': 17527491157639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'David Mitchell',
    'address': '568 Melissa Rest\nDiazstad, HI 01073',
    'text': 'Treat go season gas. Wonder instead rock stand. Draw section break ever.\nPrice who scene long do. Door president say model.',
    'email': 'kenneth19@example.org',
    'phone_number': '001-202-859-9635x65311',
    'json': {
    'name': 'Haley Davies',
    'address': '96156 Abbott Rest Suite 423\nSamuelfurt, OH 32309',
},
    'key55491': 'value97926',
    'key57269': 'value96224',
    'key36587': 'value53540',
    'key53956': 'value63615',
},
    {
    'id': 17527491157650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Jeffrey Anderson',
    'address': '27747 Joshua Extension\nNew Christopherchester, OR 27645',
    'text': 'Home already car any exist marriage recently. Capital response left attention responsibility. Enjoy travel across fight school because collection ahead.',
    'email': 'jennifermacias@example.org',
    'phone_number': '001-663-379-1373x7961',
    'json': {
    'name': 'Paul Andrews',
    'address': '3802 Williams Drive Suite 753\nNorth Tylermouth, NC 85054',
},
    'key47643': 'value750',
    'key82674': 'value28357',
},
    {
    'id': 17527491157661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Emily Blair',
    'address': '903 Dawn Rapids\nNew Lisa, NY 63347',
    'text': 'Senior some successful participant. Act once their game wear goal tax.',
    'email': 'zlivingston@example.org',
    'phone_number': '+1-728-430-8375x009',
    'json': {
    'name': 'Kim Mcclure',
    'address': 'PSC 4635, Box 5003\nAPO AP 99393',
},
    'key81886': 'value79342',
    'key25243': 'value2893',
    'key68332': 'value14893',
    'key7525': 'value39959',
    'key20118': 'value15079',
    'key42834': 'value76455',
    'key26887': 'value39253',
},
    {
    'id': 17527491157669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Norman Drake',
    'address': '68407 Jamie Prairie Apt. 771\nLake Amy, IN 79372',
    'text': 'Boy name herself stay chair body TV. Traditional risk level do feeling seat be. Image system should two expert Congress represent theory. Issue subject which film spend wall space they.',
    'email': 'vduke@example.com',
    'phone_number': '525-969-4713',
    'json': {
    'name': 'Lynn Lopez DDS',
    'address': 'PSC 3664, Box 2948\nAPO AP 90701',
},
    'key78563': 'value7556',
    'key60559': 'value30046',
    'key84496': 'value70263',
    'key67738': 'value74022',
    'key74613': 'value75510',
    'key79901': 'value49432',
},
    {
    'id': 17527491157677,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Jason Snyder',
    'address': '09961 Gonzalez Squares\nLake Patriciaview, PR 55160',
    'text': 'Enough type industry type. Population he through factor sign.\nAgency idea account now pressure game lose. Work start story.',
    'email': 'jowen@example.org',
    'phone_number': '888.432.7706',
    'json': {
    'name': 'Ernest Reyes',
    'address': '2963 Jeff Junctions\nWest Andrewfurt, NE 79510',
},
    'key12678': 'value85453',
    'key30646': 'value2668',
    'key21338': 'value30971',
    'key53865': 'value28803',
    'key80329': 'value22876',
    'key44455': 'value71859',
    'key18355': 'value9307',
    'key56822': 'value45968',
},
    {
    'id': 17527491157688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Deborah Swanson',
    'address': '9185 Johnson Grove Apt. 725\nEast Gregory, MA 71625',
    'text': 'Seven area each point. Sea do room religious. Move mission maybe million see.',
    'email': 'belljoann@example.org',
    'phone_number': '(362)340-2730x2239',
    'json': {
    'name': 'Bryce Mcclain',
    'address': '997 English Street\nTylerborough, AS 18545',
},
    'key93892': 'value33110',
    'key51332': 'value29319',
    'key37111': 'value81072',
    'key1892': 'value38637',
    'key22303': 'value44264',
    'key89636': 'value89484',
},
    {
    'id': 17527491157700,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Amanda Reed',
    'address': 'PSC 3037, Box 1863\nAPO AA 21832',
    'text': 'One truth play to. Set indeed his record mission PM. Simply bag space network mention.\nAway beyond visit campaign kitchen play control want. Recently during forget film head other sea.',
    'email': 'dyoung@example.com',
    'phone_number': '571-822-4945x9250',
    'json': {
    'name': 'Travis Lewis',
    'address': '96853 William Rest\nAprilhaven, KS 35812',
},
    'key88717': 'value44197',
    'key73340': 'value20800',
    'key16157': 'value27156',
    'key9790': 'value13687',
},
    {
    'id': 17527491157708,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Steve Cain',
    'address': '80007 Walter Island\nNew Valerie, CT 03917',
    'text': 'Rise network three media. Edge trial foreign choice word buy.\nMusic still picture food.',
    'email': 'priscillaflores@example.com',
    'phone_number': '687.638.3835x563',
    'json': {
    'name': 'Shirley Smith',
    'address': '15973 Dawn Parkway Apt. 027\nRobinsonhaven, LA 57227',
},
    'key83123': 'value36500',
    'key36783': 'value97701',
},
    {
    'id': 17527491157719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Dustin Frazier',
    'address': '9845 Emily Light Suite 881\nNorth Jesse, GA 17213',
    'text': 'Realize there eye sign consider. Win world no reason both.\nMight increase business catch charge including. Claim field couple level different spend.',
    'email': 'michaelyang@example.net',
    'phone_number': '4106387176',
    'json': {
    'name': 'Mr. Alexander Kelly',
    'address': '10141 Gutierrez Village\nAmyfort, VA 58611',
},
    'key81361': 'value33905',
    'key40289': 'value72913',
    'key92492': 'value1328',
    'key56941': 'value98599',
},
    {
    'id': 17527491157731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Matthew Dodson',
    'address': '44363 Campos Ports Apt. 627\nWalshmouth, GU 36331',
    'text': 'Yourself our baby water life eight floor. Free tend year figure.\nNote theory when word expert memory. Three class free ready. Require coach all perform ball ten.',
    'email': 'douglas86@example.com',
    'phone_number': '361.659.5679x0478',
    'json': {
    'name': 'Lori Snyder',
    'address': '03148 Vasquez Inlet\nNew Sylvia, FL 23202',
},
    'key43161': 'value59916',
    'key81222': 'value71242',
    'key15979': 'value13882',
    'key69110': 'value7459',
    'key72120': 'value21090',
},
    {
    'id': 17527491157742,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Kevin Sampson',
    'address': '7982 Nathan Throughway Apt. 842\nSouth Cheryl, KY 09285',
    'text': 'Media force open. Spring speak material. Coach local receive piece over despite identify work. Able marriage pressure.',
    'email': 'diana98@example.com',
    'phone_number': '311.520.2482',
    'json': {
    'name': 'Samuel Ross',
    'address': '671 Paul Points\nMeganhaven, FM 23679',
},
    'key26142': 'value58798',
    'key99956': 'value74145',
    'key72541': 'value97115',
    'key56002': 'value69970',
    'key77274': 'value8581',
    'key94635': 'value62828',
    'key93795': 'value76081',
    'key71293': 'value79655',
    'key6641': 'value86621',
    'key76191': 'value91088',
},
    {
    'id': 17527491157754,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Matthew Adams',
    'address': '9427 Amanda Fields\nNorth Jessica, IL 47634',
    'text': 'Speech my beat continue nature list. Mean base off music standard receive paper.\nPractice life institution. Three culture significant medical.',
    'email': 'hjackson@example.com',
    'phone_number': '857.269.7895x69161',
    'json': {
    'name': 'Laura Jones',
    'address': '5386 Perez Island\nPort Rebeccafurt, NY 31454',
},
    'key82693': 'value43956',
    'key46412': 'value57730',
    'key33821': 'value92544',
    'key13433': 'value20817',
    'key17299': 'value36013',
    'key39885': 'value13656',
    'key46935': 'value43312',
    'key34619': 'value7406',
},
    {
    'id': 17527491157768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Nicole Reyes',
    'address': '620 Parks Fall Apt. 440\nWest Laura, PW 96226',
    'text': 'Side either station reason process really. Drop carry reason like air board.\nWhite half success behind country nearly way. Ever painting official discover discuss subject individual.',
    'email': 'ahall@example.com',
    'phone_number': '636.311.5876x7721',
    'json': {
    'name': 'Lisa Wilson',
    'address': '61003 Seth Throughway\nNorth Paulton, AK 34831',
},
    'key58874': 'value96547',
    'key91870': 'value82490',
    'key27940': 'value17644',
    'key42283': 'value99866',
    'key56438': 'value41957',
    'key58642': 'value32523',
    'key78410': 'value95595',
    'key96212': 'value82400',
},
    {
    'id': 17527491157781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Kimberly Suarez',
    'address': '696 Stephenson Point Apt. 938\nNew Nicholaschester, AL 46159',
    'text': 'By clear cell who determine. Nature growth hard factor project rise rate well. Western student good our assume arrive.\nInstead require table reach. Store quality run member decision wear send.',
    'email': 'annadunlap@example.com',
    'phone_number': '001-464-463-4578x985',
    'json': {
    'name': 'Antonio Soto',
    'address': '31524 Raymond Track Suite 036\nNorth Mary, PA 05023',
},
    'key5035': 'value55906',
    'key96944': 'value25553',
    'key37259': 'value82992',
},
    {
    'id': 17527491157794,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Dawn Boyd',
    'address': '181 Sanchez Fields\nWest Michael, WY 65608',
    'text': 'Peace Republican whatever watch. Word community individual mention news customer room various. Republican something rate prove accept stock attack green.',
    'email': 'scott09@example.net',
    'phone_number': '(227)795-4318',
    'json': {
    'name': 'Rebecca Cook',
    'address': '95996 Strickland Avenue Apt. 078\nLake Lori, TN 36629',
},
    'key90015': 'value49406',
    'key34326': 'value88068',
    'key12958': 'value28886',
    'key77914': 'value69346',
    'key19546': 'value83221',
},
    {
    'id': 17527491157805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Madison Powell MD',
    'address': '80776 Skinner Path Apt. 355\nOdonnellview, FL 85456',
    'text': 'Buy business ground class color. Second strategy final customer federal then ago.\nDiscussion culture election training style traditional each. Poor television why production open.',
    'email': 'timothy69@example.org',
    'phone_number': '(824)228-5979x590',
    'json': {
    'name': 'Jamie Thompson',
    'address': '7151 Oliver Manors\nNorth Abigailmouth, DC 62702',
},
    'key7377': 'value73315',
    'key93679': 'value90083',
    'key30099': 'value48125',
    'key63485': 'value74200',
    'key50819': 'value98299',
    'key6156': 'value14852',
    'key31561': 'value65955',
    'key6809': 'value31899',
    'key49352': 'value6592',
},
    {
    'id': 17527491157818,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Dr. Donna Davenport',
    'address': '446 Mann Glen Suite 873\nEast Thomasfurt, PW 91344',
    'text': 'Own employee activity wait. Artist future all however summer include.\nWhole house everything you stock. Staff else court claim safe audience. Mean may must letter after.',
    'email': 'robertsonjonathan@example.org',
    'phone_number': '742-282-8314',
    'json': {
    'name': 'Angela Cox',
    'address': '468 Deborah Corners\nSouth Evanmouth, PR 04813',
},
    'key50748': 'value3507',
},
    {
    'id': 17527491157829,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Debra Osborn',
    'address': '560 Weaver Lights\nEast Randyshire, OR 23354',
    'text': 'Edge so but make voice seat. Low amount thank three field term join.\nAny system cover small chair. Score between within. Accept Mrs player.',
    'email': 'cwaller@example.org',
    'phone_number': '+1-604-704-4568x362',
    'json': {
    'name': 'Jason Phillips',
    'address': '32597 William Neck\nSouth Frank, NJ 58714',
},
    'key71037': 'value12260',
    'key66257': 'value79498',
    'key52607': 'value38606',
    'key48774': 'value32569',
    'key23575': 'value8595',
    'key35280': 'value56460',
    'key81542': 'value89150',
    'key76901': 'value57007',
    'key86203': 'value67951',
},
    {
    'id': 17527491157841,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Donald Henson',
    'address': '9750 Jeremy Crossing\nNew Sheri, WI 31056',
    'text': 'Share reason dinner risk democratic.\nHeart sometimes key. Above relate religious evening themselves foreign guy.\nGreat do whatever doctor. Arm product music care heavy.',
    'email': 'jonathanpatterson@example.com',
    'phone_number': '779.751.4990x124',
    'json': {
    'name': 'Lori Brown',
    'address': '5369 Lee Plaza\nPort Patriciaberg, UT 51834',
},
    'key7990': 'value19662',
    'key44180': 'value87677',
    'key23907': 'value7169',
    'key72014': 'value17972',
    'key96438': 'value23690',
},
    {
    'id': 17527491157852,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Barbara Long',
    'address': '35532 Jonathan Turnpike Apt. 852\nWilliamville, WI 89935',
    'text': 'Week say result almost pattern in. Seat go policy city prepare significant walk later.\nPush would course look recent nor. Leave than information across still agreement both.',
    'email': 'michele45@example.net',
    'phone_number': '232-231-5086x34684',
    'json': {
    'name': 'Tina Jacobs',
    'address': '359 Hernandez River\nJamesfort, KY 86863',
},
    'key38579': 'value35263',
    'key58417': 'value97959',
    'key64597': 'value41758',
    'key12894': 'value44976',
    'key6161': 'value58150',
    'key98914': 'value67158',
    'key6333': 'value98485',
    'key29083': 'value90080',
    'key64236': 'value31106',
    'key7325': 'value19659',
},
    {
    'id': 17527491157863,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Douglas Daugherty',
    'address': '6511 Tammy Land\nPort Bruce, NY 60205',
    'text': 'Thus item once reveal difficult reveal care.\nInvestment executive purpose yard fine quite. Interesting learn development surface language company. Call assume play practice watch wait.',
    'email': 'pamela44@example.org',
    'phone_number': '001-724-365-2618x82397',
    'json': {
    'name': 'Amanda Avila',
    'address': '548 Tracy Drive Apt. 478\nPetersenbury, TN 51219',
},
    'key61370': 'value67165',
    'key84567': 'value82082',
},
    {
    'id': 17527491157873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Nathan Rose',
    'address': '5360 Linda Flats\nTylermouth, MD 13149',
    'text': 'Certain mean evening. Fact Republican adult entire hard report others. Scene service election shoulder.\nParticipant pull away notice five this out try. Watch role type have.',
    'email': 'maria40@example.org',
    'phone_number': '344.969.5881x28266',
    'json': {
    'name': 'Alison Henderson',
    'address': '198 Holmes Rue Suite 479\nNew Mary, GA 59579',
},
    'key24455': 'value29676',
    'key4500': 'value38295',
    'key80969': 'value92730',
    'key29906': 'value62323',
    'key58629': 'value52878',
    'key73260': 'value8181',
    'key83123': 'value31005',
    'key29753': 'value58421',
    'key35624': 'value73174',
},
    {
    'id': 17527491157884,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Jonathan Harvey',
    'address': 'USNS Rivers\nFPO AE 93480',
    'text': 'Increase fill huge carry pay magazine rise. Though mind memory likely police school.\nCultural those everyone sign shoulder cultural. Material partner century. Participant democratic nice.',
    'email': 'aduncan@example.net',
    'phone_number': '4028089433',
    'json': {
    'name': 'Amy Jackson',
    'address': '599 Theresa Island Apt. 519\nPort Meghan, NV 93965',
},
    'key60872': 'value36488',
    'key69544': 'value84803',
    'key34257': 'value23140',
    'key72553': 'value45499',
    'key78381': 'value71352',
},
    {
    'id': 17527491157894,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Keith Collins',
    'address': '54326 Samuel Roads\nBlairport, CO 58729',
    'text': 'American dinner over daughter remain our. Around site husband discuss build.\nInstitution defense system. Record central positive old event gas pay. Western eye thousand.',
    'email': 'gregorygarcia@example.org',
    'phone_number': '728.355.1729x061',
    'json': {
    'name': 'William Ross',
    'address': '48948 Lindsey Views Suite 124\nSouth Alexaton, OK 53554',
},
    'key64229': 'value51804',
    'key41824': 'value79733',
    'key72729': 'value63511',
    'key26620': 'value29791',
    'key66555': 'value53101',
    'key56301': 'value28599',
    'key59962': 'value4500',
    'key5993': 'value64387',
    'key60327': 'value69843',
    'key79694': 'value70198',
},
    {
    'id': 17527491157905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Susan Ortega',
    'address': '365 Davis Lodge\nTimothybury, CA 16734',
    'text': 'Story occur attack impact. Issue officer only order develop involve pull. Game staff case poor child meet. Floor get just second and.',
    'email': 'kristy69@example.net',
    'phone_number': '+1-332-488-6528x4001',
    'json': {
    'name': 'Barbara Lee',
    'address': '608 Rodriguez Ridges Suite 909\nEast Laurachester, WY 97446',
},
    'key78436': 'value61985',
    'key67826': 'value27553',
    'key46348': 'value22463',
},
    {
    'id': 17527491157916,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Linda Rodriguez',
    'address': '0068 Mullen Trail\nWagnertown, ID 18075',
    'text': 'Into set chair different outside ball possible leave. Billion democratic admit open artist.\nWhite interest class behavior employee.',
    'email': 'thomas97@example.com',
    'phone_number': '001-885-790-3423x5567',
    'json': {
    'name': 'Michael Martinez',
    'address': '293 Michael Ways Suite 724\nLatoyaberg, MH 56665',
},
    'key17658': 'value60458',
    'key77880': 'value36717',
    'key87996': 'value84058',
    'key73593': 'value82464',
},
    {
    'id': 17527491157927,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Henry Gomez',
    'address': '8323 Davis Parkway Apt. 241\nKellerport, WV 28629',
    'text': 'Artist quality gas here organization. Include oil across fear increase loss cold. Other election development some.',
    'email': 'darylmitchell@example.com',
    'phone_number': '(624)811-4509x22094',
    'json': {
    'name': 'Matthew Acevedo',
    'address': 'Unit 3632 Box 9065\nDPO AP 09086',
},
    'key7665': 'value73358',
    'key86253': 'value55734',
    'key8333': 'value65203',
    'key99332': 'value78170',
    'key41333': 'value40189',
    'key97980': 'value74140',
    'key99116': 'value29845',
    'key67454': 'value38113',
    'key27965': 'value12961',
},
    {
    'id': 17527491157937,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Christopher Smith',
    'address': '4830 Wells Wells Suite 248\nPort Brandon, IN 90172',
    'text': 'Clearly between order begin but treat involve. Size few between government news them.\nPrepare PM then together. Vote team commercial information rest strategy bit science.\nLine music why speak.',
    'email': 'paigegarcia@example.org',
    'phone_number': '+1-667-332-3089x23150',
    'json': {
    'name': 'Scott Lopez',
    'address': '219 Brock Pike Apt. 053\nLarsonhaven, LA 23477',
},
    'key15570': 'value55780',
    'key99559': 'value16510',
    'key84298': 'value54250',
    'key49500': 'value66870',
    'key10418': 'value96635',
    'key14711': 'value80541',
    'key11057': 'value6475',
    'key58742': 'value10224',
},
    {
    'id': 17527491157948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Roberto Gordon',
    'address': '37116 Padilla Mount Suite 606\nNew Jessicaside, KS 19900',
    'text': 'Environmental money central including hair middle. Suggest discover nation sure and usually.\nWorld TV oil catch well house agree. Together important site air floor.',
    'email': 'paulsosa@example.com',
    'phone_number': '667-315-7845x72214',
    'json': {
    'name': 'Lee Johnson',
    'address': '7945 Hill Heights Suite 301\nJenniferfurt, ID 74476',
},
    'key77414': 'value47849',
    'key54354': 'value73552',
    'key10346': 'value28197',
    'key29484': 'value91744',
    'key12759': 'value74326',
    'key31248': 'value80868',
    'key16098': 'value52711',
    'key51617': 'value53950',
    'key3808': 'value36447',
},
    {
    'id': 17527491157960,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Melissa Joyce',
    'address': 'Unit 8972 Box 2663\nDPO AP 69745',
    'text': 'Entire value smile myself television read low most. Five few involve. Today energy pay.',
    'email': 'allison51@example.net',
    'phone_number': '(844)669-5083',
    'json': {
    'name': 'Amanda Spencer MD',
    'address': '69153 David Drive Suite 822\nCynthiafurt, MD 05933',
},
    'key38886': 'value34437',
    'key88089': 'value38223',
    'key1303': 'value51307',
    'key34204': 'value9327',
},
    {
    'id': 17527491157969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Janet Odom',
    'address': '4076 Avery Corners Suite 560\nHeatherchester, PA 31302',
    'text': 'Among lay foreign director up task stuff. Actually experience risk compare stuff itself art Congress.\nFly crime stand. Into want everything cover should save. Experience accept economy never.',
    'email': 'jonathan09@example.org',
    'phone_number': '(909)648-3751x595',
    'json': {
    'name': 'Melissa Washington',
    'address': '1340 Dana Isle Suite 396\nEast Janetmouth, AR 33996',
},
    'key83753': 'value63354',
    'key27487': 'value29745',
    'key96161': 'value47730',
    'key24277': 'value29335',
    'key69427': 'value15752',
    'key89701': 'value48704',
    'key90008': 'value35411',
    'key68610': 'value83852',
    'key6748': 'value38682',
    'key2194': 'value82168',
},
    {
    'id': 17527491157979,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Paul Perez',
    'address': '39703 Taylor Corner\nMclaughlinland, OK 37531',
    'text': 'Billion statement because American produce tell low. Eat early cell similar environment. Their down every might kid her when. Law responsibility assume operation.',
    'email': 'gardnerjustin@example.net',
    'phone_number': '954-502-0258x3195',
    'json': {
    'name': 'Nicole Richardson',
    'address': '8196 Reid Inlet Apt. 539\nNew Jessicafurt, LA 46249',
},
    'key86530': 'value1939',
    'key24302': 'value99748',
    'key54509': 'value44696',
    'key20133': 'value34198',
},
    {
    'id': 17527491157992,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Jason Day',
    'address': '713 Santiago Lakes\nPort Jason, FM 36113',
    'text': 'Girl drop seven use statement pay deal main. Shake market garden control team. Every oil wall later series law well.\nShow line technology continue they ready point. Hotel nation on.',
    'email': 'swilkerson@example.net',
    'phone_number': '+1-355-667-3497x2958',
    'json': {
    'name': 'Rhonda Solomon',
    'address': '727 Cabrera Ports Suite 320\nNorth Melissa, NC 87647',
},
    'key83042': 'value36616',
    'key2709': 'value5064',
    'key57398': 'value59396',
    'key67062': 'value93489',
    'key64178': 'value37159',
    'key83084': 'value636',
    'key12825': 'value58238',
    'key22429': 'value12477',
    'key32783': 'value85355',
},
    {
    'id': 17527491158003,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Heather Ramirez',
    'address': '747 Holland Locks\nRaymouth, FL 64058',
    'text': 'Rise share result. Possible defense standard movie. Challenge base toward low why.\nLife carry common thought.',
    'email': 'david71@example.net',
    'phone_number': '+1-327-361-8022x9390',
    'json': {
    'name': 'Calvin Schmidt',
    'address': '6439 Melissa Bypass Apt. 167\nLake Drew, GA 57428',
},
    'key93954': 'value66960',
    'key84173': 'value41712',
    'key33680': 'value12518',
    'key19130': 'value48646',
    'key37091': 'value90251',
    'key61402': 'value82480',
    'key35843': 'value7901',
},
    {
    'id': 17527491158014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Christopher Davis',
    'address': '5089 Hunter Ranch\nMooretown, MP 16624',
    'text': 'Beat positive player expert box part suggest. Try special next debate.\nAlmost capital look rise. Check measure reason thing administration. Sure event alone remain seat line.',
    'email': 'phamjason@example.com',
    'phone_number': '5425545655',
    'json': {
    'name': 'James Gilbert',
    'address': 'Unit 3220 Box 1507\nDPO AP 53691',
},
    'key26405': 'value49948',
},
    {
    'id': 17527491158023,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Grace Vance',
    'address': '422 Raymond Mountain Apt. 265\nMoranborough, IN 56258',
    'text': 'Situation need pressure government. Per yourself middle change debate. Top scene yeah mouth believe trouble majority.',
    'email': 'browndawn@example.net',
    'phone_number': '+1-409-797-9747x777',
    'json': {
    'name': 'Samuel Johnson',
    'address': '008 Amy Well\nRonaldstad, DC 66785',
},
    'key18717': 'value3417',
    'key95684': 'value88068',
    'key29331': 'value16997',
    'key91557': 'value13158',
    'key92273': 'value55539',
    'key57459': 'value25355',
},
    {
    'id': 17527491158034,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Jesus Beck',
    'address': 'USS Palmer\nFPO AA 63045',
    'text': 'Human early adult space wind. Game security area wait among offer.\nPerhaps than few general bed. Product impact ground seven quality figure.',
    'email': 'nicolemoore@example.com',
    'phone_number': '+1-625-403-5877x3684',
    'json': {
    'name': 'Cheryl Bartlett',
    'address': '5543 George Ways\nEast Amandaside, VI 52913',
},
    'key20502': 'value80359',
    'key10053': 'value65899',
    'key75932': 'value40452',
    'key55828': 'value80550',
    'key93682': 'value57804',
    'key90219': 'value99359',
    'key60324': 'value38867',
    'key87271': 'value31654',
    'key49244': 'value657',
    'key86638': 'value13810',
},
    {
    'id': 17527491158045,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Scott Wilson',
    'address': '18327 Glass Wall Suite 215\nJacobsonside, MH 06493',
    'text': 'Push economy family product fight. Charge management ten find both play never animal.\nTotal government student likely realize this. Rather community seem build security little training.',
    'email': 'tracie02@example.org',
    'phone_number': '(501)318-8860',
    'json': {
    'name': 'Craig White',
    'address': '979 Greene Pine Apt. 754\nKinghaven, ID 79957',
},
    'key28448': 'value80189',
    'key69573': 'value53907',
    'key35449': 'value82786',
},
    {
    'id': 17527491158056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Paul Adams',
    'address': '28671 Justin Lane Apt. 089\nStrongfurt, MP 51995',
    'text': 'Begin see along. Make indeed myself floor why per stuff. At lose executive somebody home election.',
    'email': 'jbarrett@example.net',
    'phone_number': '774.928.5100',
    'json': {
    'name': 'Mrs. Tina Hill',
    'address': '1464 Martinez Forks\nMillsmouth, OH 36459',
},
    'key81768': 'value50289',
},
    {
    'id': 17527491158067,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Steven Stout',
    'address': '637 Smith Prairie\nSouth Christianfurt, CT 23108',
    'text': 'Left investment company lead. Above develop indicate its window cell. Several debate wind deal surface care movie.\nTheory someone job difficult billion machine.',
    'email': 'austin97@example.com',
    'phone_number': '310-231-4162',
    'json': {
    'name': 'Patrick Spears MD',
    'address': '59970 Johnson Spring Suite 944\nLowestad, DC 96855',
},
    'key33999': 'value14276',
    'key53136': 'value25570',
    'key34944': 'value51186',
    'key36593': 'value53003',
    'key52538': 'value10231',
},
    {
    'id': 17527491158078,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Mr. Anthony Travis',
    'address': '2899 Betty Landing\nMichaelmouth, FL 14950',
    'text': 'Quality stand leave throughout focus. Answer cut size. Now happy could need.',
    'email': 'howedaniel@example.com',
    'phone_number': '001-750-305-5973',
    'json': {
    'name': 'Kelly Davis',
    'address': '669 Victor Burgs Apt. 473\nGarciaville, ME 56505',
},
    'key9915': 'value12193',
    'key85751': 'value37070',
    'key51368': 'value2847',
    'key80134': 'value99264',
},
    {
    'id': 17527491158090,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Shannon Mooney',
    'address': '31974 Kelly Way Suite 209\nLake Melissa, NE 98623',
    'text': 'Though same character door need space. First sort week. Less listen raise reach blood control.\nBit film take share if result. Analysis body just down.',
    'email': 'janice71@example.com',
    'phone_number': '276-744-4348x086',
    'json': {
    'name': 'Jessica Richardson',
    'address': '916 Khan Views\nAnthonyhaven, MH 80382',
},
    'key47927': 'value48716',
    'key59083': 'value37273',
    'key88513': 'value98800',
    'key40423': 'value77831',
    'key86627': 'value2898',
},
    {
    'id': 17527491158101,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Jodi Reese',
    'address': 'Unit 4055 Box 4871\nDPO AP 42062',
    'text': 'Word reduce avoid bar large learn. Become wife view everything yeah top experience. White public concern what establish physical argue a.\nAct office rest leave.',
    'email': 'kimsandra@example.net',
    'phone_number': '240-348-9501x6128',
    'json': {
    'name': 'Melanie Wright',
    'address': 'Unit 2516 Box 3320\nDPO AA 22736',
},
    'key9505': 'value11179',
    'key29974': 'value71855',
    'key9664': 'value86982',
},
    {
    'id': 17527491158108,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Andrew Mora',
    'address': '864 Nash Rue Suite 139\nEvansberg, GU 02722',
    'text': 'Sound however soldier under.\nRule significant read international early plant it. Look value artist language man less.\nPolitical cover night reflect much serve determine. Indicate sea figure him with.',
    'email': 'jesserobinson@example.net',
    'phone_number': '001-204-472-5278x64987',
    'json': {
    'name': 'Mary Miller',
    'address': '29949 Mccann Plains Apt. 381\nNorth Amanda, NV 20373',
},
    'key79570': 'value46042',
    'key61348': 'value75946',
},
    {
    'id': 17527491158121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Christie Cook',
    'address': '9336 Joshua Village\nChambersburgh, VA 41913',
    'text': 'Two middle learn one its. Book type important without benefit during. Network song believe.\nCoach people bank every. Student party baby dog protect me. Laugh arrive surface her.',
    'email': 'hmoore@example.net',
    'phone_number': '001-440-445-6031',
    'json': {
    'name': 'Linda Reynolds',
    'address': 'USS Lucas\nFPO AE 73634',
},
    'key42893': 'value42958',
    'key72411': 'value55267',
    'key20978': 'value99199',
    'key91575': 'value17187',
    'key10510': 'value42700',
    'key28176': 'value46304',
},
    {
    'id': 17527491158131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Taylor Gilbert',
    'address': '282 Wagner Mountains\nLake Michael, PR 81435',
    'text': 'Three area across group their help. Season cultural enjoy arrive.\nRecord remember term live region value. Most feel measure red.',
    'email': 'youngfrancisco@example.org',
    'phone_number': '749-391-2793x6718',
    'json': {
    'name': 'Shelly Yang',
    'address': '975 Michelle Manors\nArnoldberg, OR 93325',
},
    'key97875': 'value15697',
    'key52827': 'value5530',
    'key91438': 'value73986',
    'key49451': 'value25610',
    'key1914': 'value28433',
    'key9498': 'value43895',
},
    {
    'id': 17527491158147,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Walter Cabrera',
    'address': '26245 Darrell Flats Suite 631\nSmithborough, HI 27280',
    'text': 'Purpose industry director bad best use difference. Reduce single lose painting argue behind ball. Office political eye bed. Total town hand decade.',
    'email': 'april97@example.com',
    'phone_number': '001-268-805-1159',
    'json': {
    'name': 'Sara Garcia',
    'address': '889 Shawn Inlet Suite 255\nWhitetown, DE 22032',
},
    'key42691': 'value11840',
    'key16815': 'value61810',
    'key55200': 'value50968',
    'key80715': 'value9946',
},
    {
    'id': 17527491158159,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Holly Moses',
    'address': 'PSC 7109, Box 9945\nAPO AE 28529',
    'text': 'Debate close general opportunity season compare. Along prepare hand mother item during onto unit.',
    'email': 'randall84@example.org',
    'phone_number': '+1-733-303-1305',
    'json': {
    'name': 'Monica Frederick',
    'address': '555 David Locks\nClaytonshire, NM 35389',
},
    'key92034': 'value959',
    'key33600': 'value49622',
    'key13171': 'value62432',
    'key78979': 'value32423',
    'key45994': 'value25249',
    'key48816': 'value13882',
    'key61649': 'value80180',
    'key34989': 'value73139',
    'key89785': 'value31123',
    'key72514': 'value2819',
},
    {
    'id': 17527491158167,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Timothy White',
    'address': '7969 Chad Trail Apt. 249\nLake Rachelmouth, AK 03183',
    'text': 'Serve discover move. Yes amount he return eight view beat.\nCommunity kitchen soon hit machine. Agency charge can religious wish. Room visit mind beyond whether.',
    'email': 'adam65@example.net',
    'phone_number': '611.969.1449x6168',
    'json': {
    'name': 'Jeffrey Irwin',
    'address': '421 Russo Roads\nSouth Stephanie, OH 36565',
},
    'key28432': 'value36815',
},
    {
    'id': 17527491158178,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Brenda Duke',
    'address': '3575 David Avenue Suite 416\nPattonberg, MD 18016',
    'text': 'Rich allow game writer attention community. Important smile southern it. Effect fall little suggest service which.\nCareer site sure. Never figure population hundred provide security free.',
    'email': 'amanda35@example.org',
    'phone_number': '892-783-2704x321',
    'json': {
    'name': 'David Nguyen',
    'address': '1766 Cox Circle Apt. 008\nNorth Heather, GA 81436',
},
    'key98828': 'value90789',
    'key8522': 'value99384',
    'key48575': 'value9628',
    'key93410': 'value35041',
    'key74620': 'value10402',
    'key5780': 'value98712',
    'key33673': 'value95714',
    'key54769': 'value91130',
    'key87863': 'value53701',
},
    {
    'id': 17527491158189,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Mark Davis',
    'address': '1171 Morgan Mountain Apt. 897\nNorth Thomas, MH 58934',
    'text': 'Medical billion ago lot Republican bar. Alone music cover game customer serve she. Task maintain attorney edge president material. Road current condition federal now heavy effect.',
    'email': 'martinjoseph@example.net',
    'phone_number': '220.371.7362',
    'json': {
    'name': 'Gary Garcia',
    'address': '1066 Donna Village Apt. 643\nSouth Marcburgh, WA 55850',
},
    'key6884': 'value77584',
    'key20249': 'value31430',
    'key99883': 'value46575',
    'key95988': 'value72005',
    'key53962': 'value77282',
    'key57831': 'value50',
},
    {
    'id': 17527491158200,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Kathryn Hoffman',
    'address': '8107 Robinson Ford\nPort Jennifer, PR 13230',
    'text': 'Hold color control where. Detail watch TV to. Concern analysis recent firm natural.\nManage do music these. Guy generation oil week part number note and. Success say peace current fly.',
    'email': 'hjohns@example.com',
    'phone_number': '871.835.4577x7597',
    'json': {
    'name': 'Debbie Walker',
    'address': '511 Jon Dale\nKimville, CO 35848',
},
    'key51324': 'value68224',
    'key8828': 'value73489',
    'key10138': 'value94788',
    'key79120': 'value23769',
    'key98966': 'value32398',
},
    {
    'id': 17527491158211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Dorothy Wilson',
    'address': '061 Charles Street Suite 388\nNew Erikaborough, PA 52656',
    'text': 'Bad force three. Address hour she will size available.\nWriter community raise nice or mouth interesting. Usually gun with cold.',
    'email': 'tparker@example.com',
    'phone_number': '691-599-5450',
    'json': {
    'name': 'Rhonda Buchanan',
    'address': '32501 David Trail\nNorth Danside, CA 87801',
},
    'key2832': 'value70302',
    'key41592': 'value35337',
    'key43829': 'value90342',
    'key93186': 'value9608',
    'key33806': 'value10479',
    'key87854': 'value76070',
    'key52585': 'value36690',
    'key8534': 'value82869',
},
    {
    'id': 17527491158222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Matthew Cuevas',
    'address': '742 Brooke Extension Suite 238\nHolmestown, SC 73128',
    'text': 'Four station decision garden as president century. Long show work. Receive true yeah boy enter fast wonder choose.\nManager make behind keep. Authority crime moment call wrong.',
    'email': 'piercejeremy@example.net',
    'phone_number': '945-278-9746',
    'json': {
    'name': 'Linda Santiago',
    'address': '902 Dunn Trail Apt. 419\nNorth Kathrynside, GA 08328',
},
    'key96999': 'value78357',
    'key73207': 'value92385',
    'key10096': 'value87968',
},
    {
    'id': 17527491158234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Daniel Robinson',
    'address': '075 William Ports\nPort Seanview, KY 03582',
    'text': 'Look oil program Republican college build. Environment their color adult ok purpose shoulder. Capital family something compare will call music. Partner anything list blood book worker camera.',
    'email': 'waynebailey@example.net',
    'phone_number': '487-638-0142',
    'json': {
    'name': 'Laura Austin',
    'address': '2979 Williams Centers\nSouth Maryborough, AK 27125',
},
    'key9339': 'value81916',
    'key68975': 'value76884',
    'key51716': 'value73405',
    'key43476': 'value15584',
    'key15163': 'value43205',
    'key44710': 'value43090',
    'key81059': 'value68054',
    'key79075': 'value24536',
    'key27023': 'value97136',
},
    {
    'id': 17527491158246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Brooke Black',
    'address': '2667 Richard Dale\nCarterhaven, AK 82590',
    'text': 'Community year book place worry. East see own well it nothing share. Prove door state culture worry.\nYear range role with. Nice use easy attorney.',
    'email': 'wrobbins@example.net',
    'phone_number': '2317996063',
    'json': {
    'name': 'Paula Robinson',
    'address': 'Unit 4453 Box 6192\nDPO AP 54653',
},
    'key30665': 'value6534',
    'key27656': 'value87161',
    'key69106': 'value86572',
},
    {
    'id': 17527491158256,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Rachel Cook',
    'address': '77441 Parker Garden\nWest Stephen, UT 27284',
    'text': 'Leave affect hospital local painting article relationship. Everything president activity federal ground music.\nBank however wear watch toward score. Sit purpose officer oil special.',
    'email': 'phillipsrichard@example.com',
    'phone_number': '001-578-744-8027x320',
    'json': {
    'name': 'Brittney Gill',
    'address': '40975 Michael Skyway\nAdamsview, IA 53092',
},
    'key82860': 'value45462',
    'key75376': 'value61504',
},
    {
    'id': 17527491158267,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Annette Li',
    'address': '372 Castillo Viaduct\nRichardsonton, NM 78408',
    'text': 'Reality policy large director. Everybody scene act travel. Chair growth event also. Power stage share draw eight might executive.',
    'email': 'andrewthornton@example.org',
    'phone_number': '(448)565-9342',
    'json': {
    'name': 'Erica Brown',
    'address': '495 Michael Ferry\nSouth Zacharychester, VI 69388',
},
    'key93442': 'value32034',
    'key80581': 'value9442',
    'key62759': 'value75592',
    'key93209': 'value92400',
    'key64365': 'value86820',
    'key36660': 'value16162',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
    'vector',
    'json',
],
    'filter': 'uid in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199]',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/entities/get"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/get")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/get'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
    'vector',
    'json',
],
    'id': 17527491156096,
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



    def test_request_5(self):
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
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
        """测试请求 7 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
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



    def test_request_8(self):
        """测试请求 8 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '1c1173be-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_09_574424YdlcxPnu',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestGetVector_test_get_vector_complex[True-False-one]_1752749120.json')
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
    test = AllmilvusLogtestgetvectorTestGetVectorComplexTrueFalseOne1752749120Json()
    test.run_tests()
