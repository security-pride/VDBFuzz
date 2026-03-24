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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 00]_1752748717_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 00]_1752748717.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid001752748717Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 00]_1752748717.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 00]_1752748717.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '2b290c00-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_25_398290jasuLLTL',
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
    'RequestId': '2b290c00-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_25_398290jasuLLTL',
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
    'RequestId': '2b290c00-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_25_398290jasuLLTL',
    'data': [
    {
    'id': 17527487114468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Amy Mora',
    'address': '257 Abigail Terrace\nWest Patriciamouth, MO 74971',
    'text': 'Improve social away ready. Clearly their discover author trade suddenly lead.\nGas clear also hold threat. These last the blood card she. Including result politics similar new brother help.',
    'email': 'shariharris@example.org',
    'phone_number': '473.997.6711',
    'json': {
    'name': 'Jacob Barton',
    'address': '4912 Jesus Burg Suite 588\nFletcherport, FL 83755',
},
    'key63971': 'value77204',
    'key44075': 'value12442',
    'key72960': 'value60204',
    'key65568': 'value34585',
    'key76505': 'value15974',
},
    {
    'id': 17527487114483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Craig Chandler',
    'address': 'Unit 3488 Box 1593\nDPO AA 25889',
    'text': 'Despite office turn plant. Today amount writer. Human everything thing.',
    'email': 'alexanderbates@example.com',
    'phone_number': '240-254-2265x0964',
    'json': {
    'name': 'Justin Lowery',
    'address': '171 Jones Harbor\nLake Elizabeth, WY 93369',
},
    'key87546': 'value38432',
    'key85843': 'value88972',
    'key97632': 'value3905',
    'key40592': 'value8448',
},
    {
    'id': 17527487114493,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Zachary Page',
    'address': '6503 Brittany Manor\nThompsonbury, MH 12335',
    'text': 'Us she wind continue. Around Mrs military. Strong me plan get state live.\nFocus cover to parent raise claim. Rise health not military see may. Class soldier break skill.',
    'email': 'crystal51@example.net',
    'phone_number': '(205)563-8377',
    'json': {
    'name': 'Craig Bailey',
    'address': 'USS Horn\nFPO AA 95800',
},
    'key81535': 'value95762',
},
    {
    'id': 17527487114503,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Lori Harmon',
    'address': '104 Manuel Estate Suite 435\nMelanieberg, PA 74088',
    'text': 'Walk book indeed have. Pass store happen. Contain despite son wish let.\nStop light similar our mother finally. Should discover just born remember.',
    'email': 'hollandchristina@example.com',
    'phone_number': '+1-222-415-5970x33140',
    'json': {
    'name': 'Christopher Li',
    'address': '9383 Perry Tunnel Apt. 084\nNew John, MI 49861',
},
    'key98935': 'value16898',
    'key85676': 'value97359',
    'key28517': 'value6735',
    'key34110': 'value57187',
},
    {
    'id': 17527487114514,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Tracy Weaver',
    'address': '400 Maxwell Mountains\nNorth Andrew, GU 57798',
    'text': 'Picture compare set recent street second. Tonight development cultural reason tell free. Community positive experience record.',
    'email': 'scott91@example.net',
    'phone_number': '001-908-804-0676',
    'json': {
    'name': 'Kathryn Parks',
    'address': '9608 Brent Brook\nEast Steven, GU 62970',
},
    'key70962': 'value24161',
    'key69551': 'value98495',
    'key53107': 'value14154',
    'key43563': 'value35413',
    'key53647': 'value25466',
    'key81632': 'value13532',
    'key56512': 'value10751',
    'key13969': 'value56106',
    'key68484': 'value39534',
},
    {
    'id': 17527487114524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Matthew Rhodes',
    'address': '8793 Brandon Harbor\nWest Jonberg, IN 72452',
    'text': 'Art either lot find camera specific. South play turn me person.\nSix chair wide science make. Wrong view situation thought.',
    'email': 'tamararivera@example.net',
    'phone_number': '(254)605-8667x83259',
    'json': {
    'name': 'Hannah Reynolds',
    'address': '1097 Tyler Keys\nDustinhaven, WA 10242',
},
    'key413': 'value98543',
    'key12955': 'value61853',
    'key89417': 'value65353',
    'key21592': 'value12211',
    'key79682': 'value48975',
    'key41289': 'value54551',
},
    {
    'id': 17527487114535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Amanda Powell MD',
    'address': '5453 Stephen Grove Apt. 118\nAshleyborough, PW 63073',
    'text': 'Election task police when case. Choose line some plant anything. Ball according probably scene break. Home spring issue appear.',
    'email': 'peterssarah@example.com',
    'phone_number': '805.309.0786x0750',
    'json': {
    'name': 'Adam Navarro',
    'address': '9936 Hebert Extension Apt. 562\nNorth Kristen, MP 50634',
},
    'key61583': 'value43070',
    'key85379': 'value86428',
    'key72197': 'value61220',
    'key38453': 'value7066',
    'key98261': 'value4773',
    'key78427': 'value31700',
    'key90535': 'value6507',
},
    {
    'id': 17527487114547,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Kimberly Holland',
    'address': '591 Sarah Trafficway\nSouth Brooke, NY 71486',
    'text': 'By house international central crime general middle.\nBase stop cup learn should. Subject Republican base keep we trip. Notice dream personal page.',
    'email': 'walkermatthew@example.net',
    'phone_number': '314-798-0833',
    'json': {
    'name': 'Joseph Navarro',
    'address': '4437 John Drive Apt. 310\nSandrashire, GA 95287',
},
    'key2920': 'value60481',
    'key9262': 'value74853',
    'key55069': 'value83959',
    'key33501': 'value8003',
    'key11038': 'value65968',
},
    {
    'id': 17527487114558,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Wanda Ray',
    'address': 'Unit 6138 Box 6783\nDPO AA 78980',
    'text': 'Away bed participant daughter ago short billion. Ready Republican beyond. Fast project eat price attorney watch situation policy.',
    'email': 'william16@example.org',
    'phone_number': '233-377-2146',
    'json': {
    'name': 'Stanley Bradshaw',
    'address': '7008 Lee Hill Suite 034\nAshleyhaven, MD 28362',
},
    'key35594': 'value15273',
    'key37821': 'value41985',
},
    {
    'id': 17527487114566,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Debra Lewis',
    'address': '08543 Walker Cove Apt. 143\nSouth Erik, TX 13216',
    'text': 'Stop imagine instead. Bill though but speak catch their. Situation former single law win miss. Bank media eight it.',
    'email': 'bwilliams@example.com',
    'phone_number': '(852)229-5790x195',
    'json': {
    'name': 'Michele Moyer',
    'address': '502 Connie Lake Suite 694\nNew Alexandraside, ME 47528',
},
    'key54694': 'value55381',
    'key56487': 'value75531',
    'key36983': 'value79733',
    'key87963': 'value63909',
},
    {
    'id': 17527487114577,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Linda Diaz',
    'address': 'USNS Garza\nFPO AA 45666',
    'text': 'Recent early herself base book court east. Carry example note behind low hard. Son break challenge enough choice somebody source win.',
    'email': 'jonathan66@example.com',
    'phone_number': '+1-351-950-6474x9106',
    'json': {
    'name': 'Carmen Matthews',
    'address': '178 Marshall Via\nEast Joyport, FL 85630',
},
    'key56504': 'value67958',
},
    {
    'id': 17527487114587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'John Williams',
    'address': '795 Gallagher Plaza Apt. 833\nSouth Heather, RI 01086',
    'text': 'Anyone know draw speech. Condition bed blood newspaper movement serve painting. Modern candidate herself let.\nEight town save who point enjoy full.',
    'email': 'sharpkevin@example.org',
    'phone_number': '(476)476-4173x35665',
    'json': {
    'name': 'Alexis Ball',
    'address': '4326 Nathan Neck\nLake Ryanstad, VT 82620',
},
    'key38897': 'value37715',
    'key17503': 'value86469',
    'key41337': 'value60987',
    'key6346': 'value42448',
    'key90484': 'value53041',
    'key77071': 'value73811',
    'key35822': 'value19378',
},
    {
    'id': 17527487114598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Morgan Lewis',
    'address': '11414 Sanford Ports\nNorth Abigail, VA 51911',
    'text': 'Though from girl rise director particular. A measure fast billion try appear value.\nCup matter these machine. Improve bag ever pass there.',
    'email': 'harry44@example.com',
    'phone_number': '001-435-866-4008x6715',
    'json': {
    'name': 'Elizabeth Arnold',
    'address': '869 Jo Field\nDavisshire, MD 38557',
},
    'key34487': 'value22039',
    'key83642': 'value58165',
    'key77514': 'value35309',
    'key15089': 'value20927',
    'key89070': 'value53562',
    'key64954': 'value90152',
    'key25967': 'value13105',
},
    {
    'id': 17527487114610,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Heather Best',
    'address': '99363 Leonard Skyway\nNew William, KY 35452',
    'text': 'Lay positive rise quickly subject back produce. Employee her up exactly president notice.\nBudget other push. Community or far from rise senior yard increase. Dog will heavy over human.',
    'email': 'angel78@example.org',
    'phone_number': '(688)255-0599x73289',
    'json': {
    'name': 'Raymond Leonard',
    'address': '5381 Short Turnpike Apt. 629\nSouth Samuelside, FM 98950',
},
    'key83267': 'value25930',
    'key69596': 'value52561',
    'key81029': 'value41809',
    'key2039': 'value41804',
},
    {
    'id': 17527487114624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Justin Benjamin',
    'address': '9761 Phillips Ways\nBrittanyfort, TX 61169',
    'text': 'East receive data those mouth. Argue inside artist line send allow.\nLater seem represent purpose window southern country.',
    'email': 'cummingsjoseph@example.net',
    'phone_number': '001-975-351-2689',
    'json': {
    'name': 'Jennifer Mullen',
    'address': '759 Lee Passage\nEast Ana, ND 00835',
},
    'key92345': 'value22597',
    'key3154': 'value83514',
    'key34821': 'value3754',
    'key54181': 'value43508',
    'key26850': 'value94768',
    'key17098': 'value40285',
    'key45436': 'value97218',
    'key39808': 'value72968',
    'key94221': 'value68302',
    'key76684': 'value56138',
},
    {
    'id': 17527487114637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Adrienne Martinez',
    'address': '4049 Smith Stream Suite 784\nThompsonbury, RI 88059',
    'text': 'Responsibility sometimes customer perform state. Knowledge commercial too prevent. Have drive fire response.',
    'email': 'mlopez@example.org',
    'phone_number': '(635)973-9057x2384',
    'json': {
    'name': 'Alexander Jordan',
    'address': '9029 Silva Heights\nChristopherchester, VI 83649',
},
    'key93996': 'value34382',
    'key61594': 'value54517',
    'key51650': 'value55169',
    'key88971': 'value13428',
    'key92620': 'value31942',
},
    {
    'id': 17527487114648,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Madison Thomas',
    'address': '509 Patricia Pine Suite 783\nPort Tamichester, MT 90687',
    'text': 'Create claim environment front make none. Day benefit phone. Must keep bit while rather into. West administration partner still party.',
    'email': 'xgriffith@example.com',
    'phone_number': '+1-789-319-1246x344',
    'json': {
    'name': 'Danielle White',
    'address': '2908 Sean Village\nTammyburgh, WV 09780',
},
    'key66009': 'value48052',
    'key38591': 'value82881',
    'key64114': 'value48473',
    'key79194': 'value65559',
    'key75333': 'value22890',
    'key84821': 'value61384',
    'key90825': 'value98784',
    'key97760': 'value55345',
    'key443': 'value17123',
    'key42294': 'value40877',
},
    {
    'id': 17527487114659,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Natasha Dean',
    'address': '5700 Lyons Knoll\nSarahmouth, SD 63710',
    'text': 'Move fear kid first study main produce friend. Front provide forget information. Cut near remember family include strong.',
    'email': 'stevenkennedy@example.com',
    'phone_number': '(449)732-1048x80491',
    'json': {
    'name': 'Amber Diaz',
    'address': '11714 Foster Gardens Suite 040\nSouth Curtisview, LA 52141',
},
    'key55224': 'value58235',
    'key24297': 'value77396',
    'key70399': 'value63399',
    'key11668': 'value67082',
    'key62504': 'value91773',
    'key27703': 'value63341',
    'key13080': 'value28928',
    'key64531': 'value84968',
    'key93322': 'value1378',
    'key32326': 'value95620',
},
    {
    'id': 17527487114671,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Michael Scott',
    'address': '2737 Christopher Overpass\nNorth Kelsey, WV 33508',
    'text': 'Student indeed ball thank term story. Another later those benefit success tax someone.\nOrganization course market home ten. Environment upon that chance yes walk.',
    'email': 'spencerpaul@example.net',
    'phone_number': '492-276-8804x69559',
    'json': {
    'name': 'Jamie Nolan',
    'address': '400 Jennifer Station\nAdamsland, NE 83291',
},
    'key73413': 'value36942',
    'key76065': 'value60432',
    'key87377': 'value25869',
    'key63414': 'value79835',
    'key26341': 'value79321',
    'key84760': 'value19931',
    'key88792': 'value44506',
    'key27559': 'value77830',
},
    {
    'id': 17527487114683,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Rachel Rivera',
    'address': '2216 Brooks Circles Suite 371\nLloydport, MH 82850',
    'text': 'Provide price wind head consumer. Pick not animal fast.\nOne scientist voice social late real myself. Among suddenly use seek education notice.',
    'email': 'knightjeremy@example.com',
    'phone_number': '484-903-6304x4167',
    'json': {
    'name': 'Joseph Lynch',
    'address': '0935 Ashley Knoll\nPort Shannon, CA 66211',
},
    'key34746': 'value15620',
    'key43050': 'value52103',
},
    {
    'id': 17527487114695,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Stacey Tucker',
    'address': '685 Deanna Stravenue\nNew Kevinside, PA 52374',
    'text': 'Affect fire yard onto interest Republican reduce. A direction school police prevent water. Could against year least tend fall involve.\nCoach daughter building.',
    'email': 'hollyryan@example.com',
    'phone_number': '456-539-2410',
    'json': {
    'name': 'Joshua Manning',
    'address': '57659 Long Extensions Suite 942\nRobinsonport, OR 80503',
},
    'key3959': 'value88353',
    'key70144': 'value70795',
    'key51809': 'value97881',
    'key41174': 'value43999',
    'key10493': 'value89929',
    'key49015': 'value35229',
    'key45356': 'value78230',
    'key61212': 'value25025',
    'key84982': 'value85019',
},
    {
    'id': 17527487114707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jason Robinson',
    'address': '786 Ho Island Apt. 489\nValenzuelaburgh, TN 12075',
    'text': 'Right wish us simply call. Method beyond attorney front my.\nBar thing too sort watch education bad. Family detail about rock light size research pattern.',
    'email': 'torresjames@example.org',
    'phone_number': '824.243.5803x1402',
    'json': {
    'name': 'Hannah Sherman',
    'address': '744 Moody Village Apt. 896\nLake Mark, DC 19069',
},
    'key27371': 'value62569',
    'key90845': 'value72374',
},
    {
    'id': 17527487114719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Nathan Spencer',
    'address': 'PSC 8618, Box 5658\nAPO AA 30026',
    'text': 'Wide doctor box compare military tough amount. Speech today public probably finally he service.\nThrow claim order nice them. Smile baby too finally least cell central.',
    'email': 'anna61@example.org',
    'phone_number': '+1-375-258-3198x043',
    'json': {
    'name': 'Stacy Cochran',
    'address': '8750 Church Lane\nRonaldside, VT 09786',
},
    'key7534': 'value67734',
    'key92350': 'value93342',
},
    {
    'id': 17527487114727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Anita Stokes',
    'address': '886 Mcintyre Harbors Apt. 189\nLake Kenneth, KY 75828',
    'text': 'Notice million American wide. Operation on late couple.\nBank apply particular yet. Second finish way.',
    'email': 'davidchavez@example.com',
    'phone_number': '(418)301-2344',
    'json': {
    'name': 'Vanessa Hernandez',
    'address': '90332 Elizabeth Extension\nNorth Christy, PA 67702',
},
    'key67049': 'value97711',
    'key32370': 'value1794',
    'key63662': 'value18429',
    'key97669': 'value48716',
},
    {
    'id': 17527487114738,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Andrew Douglas',
    'address': '48132 Cantu Streets\nSarahburgh, IA 81415',
    'text': 'Record tend movie performance while. Paper analysis summer nor. Stage general option officer.\nOption loss must. Brother interesting ever.',
    'email': 'clinton75@example.net',
    'phone_number': '679.713.4486x757',
    'json': {
    'name': 'Natalie Dominguez',
    'address': '114 Ramos Court Suite 344\nPort Kennethborough, MT 50701',
},
    'key16594': 'value75807',
    'key48055': 'value25676',
    'key13968': 'value39598',
},
    {
    'id': 17527487114749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Angela Campos',
    'address': '4881 Tony Fort Apt. 333\nPatriciatown, AK 92001',
    'text': 'Big participant plant direction child. Well heavy group society kid.\nThese social watch claim school democratic. Back coach agree policy resource natural.',
    'email': 'dawnsimon@example.com',
    'phone_number': '(912)675-7312x81976',
    'json': {
    'name': 'Dana Brown',
    'address': '971 James Meadow Suite 665\nBryanbury, MI 52813',
},
    'key32559': 'value69386',
    'key74284': 'value55868',
    'key40343': 'value58458',
},
    {
    'id': 17527487114761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Donald Summers',
    'address': '34747 Williams Spurs\nNew Patricia, AS 41149',
    'text': 'Together traditional wonder stand street. Federal possible Congress this quite number save. True can approach product note instead.',
    'email': 'james31@example.com',
    'phone_number': '801.813.2018x5532',
    'json': {
    'name': 'Tami Woods',
    'address': '81097 Bryan Glen\nColemanhaven, AR 39548',
},
    'key60830': 'value96586',
    'key9017': 'value12993',
    'key33655': 'value41010',
    'key38354': 'value7184',
    'key38250': 'value32125',
    'key60003': 'value87207',
    'key74136': 'value93101',
},
    {
    'id': 17527487114771,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Stephen Neal',
    'address': '66216 Palmer Forest\nTiffanyton, HI 92129',
    'text': 'Buy rest over. By adult indicate their wind. Direction economic want go.\nTheory range us. Society with today benefit course avoid step.',
    'email': 'wmedina@example.net',
    'phone_number': '602.890.0632x5717',
    'json': {
    'name': 'Lori Hernandez',
    'address': '2746 Elizabeth Isle Suite 740\nEast Seanton, MN 69031',
},
    'key34298': 'value66090',
    'key47758': 'value82430',
    'key11054': 'value15404',
    'key88835': 'value68880',
    'key57148': 'value95201',
    'key39731': 'value17741',
    'key61573': 'value3391',
    'key88967': 'value36713',
},
    {
    'id': 17527487114782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'John Ritter',
    'address': '2967 Mills Extensions\nSarahbury, MD 76225',
    'text': 'Event beyond usually. Seem report its relationship close. Store oil week operation cup. Feeling lose late turn democratic.',
    'email': 'harrisbrenda@example.net',
    'phone_number': '001-370-576-0509x9407',
    'json': {
    'name': 'Rachael Bauer',
    'address': '8432 Jones Mall\nSouth Christinamouth, MN 59537',
},
    'key94879': 'value62055',
    'key9852': 'value62918',
    'key79078': 'value16685',
    'key57683': 'value29902',
    'key35344': 'value39071',
    'key99109': 'value37144',
    'key45474': 'value28520',
    'key61376': 'value76878',
},
    {
    'id': 17527487114794,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Cynthia Randall',
    'address': 'PSC 0964, Box 9531\nAPO AE 50577',
    'text': 'Stand choice avoid street above always. Spring pick better just agent worry oil maintain.',
    'email': 'eric06@example.org',
    'phone_number': '001-465-859-1423x80315',
    'json': {
    'name': 'Sarah Willis',
    'address': '76153 Newman Light\nNorth Kellyview, MA 09035',
},
    'key12869': 'value37248',
    'key16272': 'value82455',
    'key28093': 'value3051',
    'key38320': 'value54904',
},
    {
    'id': 17527487114803,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Crystal Hickman',
    'address': '5166 Olson Inlet Suite 008\nBrittanyhaven, OK 20899',
    'text': 'Throughout all he dream floor class. Role board thank method learn race able. Media central state various response.\nPass economy happy east. Real need reveal bar drug final choose marriage.',
    'email': 'gainesdana@example.com',
    'phone_number': '7495225027',
    'json': {
    'name': 'Ronald Davis',
    'address': '6112 Nelson Station Suite 024\nWest Anneborough, MP 32293',
},
    'key85442': 'value34291',
    'key27525': 'value40018',
    'key9528': 'value35194',
},
    {
    'id': 17527487114814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Deanna Williams',
    'address': '84507 Jacob View Suite 360\nVictormouth, AS 23045',
    'text': 'Health office school sport. Fish sell analysis lay name foreign. Age moment bit factor statement perform meeting. Bring hear hair try society course.\nWhere move reality road expect very grow.',
    'email': 'rayallen@example.net',
    'phone_number': '(916)958-2039',
    'json': {
    'name': 'Elizabeth Miller',
    'address': '7834 Maria Island Suite 223\nScotthaven, DC 09215',
},
    'key45108': 'value88228',
},
    {
    'id': 17527487114826,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Angel Stevens',
    'address': '744 Lewis Flat\nDavisfurt, IL 31250',
    'text': 'Sister within yeah sell claim event far. Window heavy born daughter finish.\nPast administration performance important. Step health situation try bank determine large after.',
    'email': 'paulmurphy@example.net',
    'phone_number': '+1-860-441-5255x9351',
    'json': {
    'name': 'Curtis Mcdonald',
    'address': '01793 Price Wall Suite 264\nWest Christopherfurt, OH 88009',
},
    'key80434': 'value93840',
    'key3033': 'value84271',
    'key46972': 'value3596',
    'key54838': 'value18799',
},
    {
    'id': 17527487114837,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Adam Crawford',
    'address': '27494 Anthony Avenue\nSmithfurt, WI 11766',
    'text': 'Quality member PM culture. Us lose trip democratic member. Development owner case father fast.\nExpert daughter easy career edge job. Option different buy guy concern career.',
    'email': 'awilliams@example.com',
    'phone_number': '317.621.3392',
    'json': {
    'name': 'Brittany Ward',
    'address': '74066 Michael Camp\nNorth Miashire, NH 90823',
},
    'key63878': 'value65772',
},
    {
    'id': 17527487114848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Devon Singleton',
    'address': '3633 Carrie Mission Suite 353\nEast Ashleychester, ID 87980',
    'text': 'Prove beyond heart machine total hour fire. Fine produce bad tax continue direction impact drop.',
    'email': 'dustinnguyen@example.net',
    'phone_number': '202-270-7447x318',
    'json': {
    'name': 'Angela Jones',
    'address': '006 Chelsea Lock\nWilliamport, AZ 11230',
},
    'key39545': 'value32747',
},
    {
    'id': 17527487114859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Dr. Breanna Olsen MD',
    'address': 'Unit 0140 Box 2453\nDPO AE 94482',
    'text': 'Pull green time hit source. Enough site thank provide suddenly ready. Age oil that these laugh ten dark.\nClose daughter popular white sit worry.',
    'email': 'dawnwhitaker@example.net',
    'phone_number': '713-919-5376x89448',
    'json': {
    'name': 'Lisa Clark',
    'address': '914 Bryan Street\nNorth Travisstad, NH 00810',
},
    'key19994': 'value69302',
    'key48741': 'value23618',
    'key15847': 'value25254',
    'key70863': 'value32529',
    'key90174': 'value78022',
    'key26791': 'value48345',
    'key91025': 'value45137',
},
    {
    'id': 17527487114869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Mr. Jack Rice V',
    'address': '308 Fritz Spurs Suite 590\nEast Jamesberg, PW 06631',
    'text': 'Same number fight bag. Serve gas understand actually near. Agreement direction there lot. Mind American state clearly.',
    'email': 'catherine61@example.org',
    'phone_number': '(719)981-9886x615',
    'json': {
    'name': 'Alyssa Ferrell',
    'address': 'USNV Martin\nFPO AE 84883',
},
    'key65840': 'value16851',
    'key6217': 'value81750',
    'key45171': 'value91011',
    'key63509': 'value79798',
    'key58676': 'value88220',
    'key39162': 'value67893',
},
    {
    'id': 17527487114880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Andre Allen',
    'address': '2701 Chambers Harbor\nSouth Brookeville, WY 35633',
    'text': 'Various floor size rest however partner. Day available letter until court. Benefit a TV upon about.',
    'email': 'stephanie82@example.net',
    'phone_number': '665.811.9161x6909',
    'json': {
    'name': 'Carol Edwards',
    'address': '123 Samantha Orchard Suite 985\nShannonberg, IN 40279',
},
    'key59912': 'value81223',
    'key68595': 'value27020',
    'key39938': 'value40005',
    'key48278': 'value57864',
},
    {
    'id': 17527487114890,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Todd Gardner',
    'address': '61942 Robert Falls Apt. 834\nSandersberg, TX 61664',
    'text': 'He same others crime own information again. Hot part who staff add. Although change teacher away. Economic his put community goal.\nHead individual these win. Should cup loss field plan pull truth.',
    'email': 'dylanlewis@example.org',
    'phone_number': '945.966.6554',
    'json': {
    'name': 'Kari Roberson',
    'address': '35079 Rhodes Ferry Apt. 537\nSouth Mariashire, KY 82553',
},
    'key26038': 'value36478',
    'key51406': 'value85222',
    'key40860': 'value55472',
},
    {
    'id': 17527487114902,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jeremy Ortiz',
    'address': '647 Perez Junction Apt. 103\nKristinburgh, GA 72751',
    'text': 'Door both lead hope rest own community prepare. Customer recent material age civil. Determine ask response role decision event.\nAnything score research focus. Show eat book threat.',
    'email': 'andrewyoung@example.org',
    'phone_number': '001-798-921-0683x1229',
    'json': {
    'name': 'Nancy Bartlett',
    'address': '10177 Jacqueline Park\nPaulside, AL 66097',
},
    'key64504': 'value54994',
    'key43834': 'value32391',
    'key4480': 'value89123',
    'key7069': 'value55467',
},
    {
    'id': 17527487114914,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Danielle Mills',
    'address': 'USNS Wright\nFPO AA 74081',
    'text': 'Myself good at four like sense. Task do discover various fire wrong us. Room thank film care point management east.\nNear four again choice. Way unit growth boy.',
    'email': 'teresa58@example.net',
    'phone_number': '001-210-558-1674',
    'json': {
    'name': 'Jeffrey Norris',
    'address': '5773 Webb Ford Suite 470\nHuffmanside, MS 43644',
},
    'key3635': 'value34755',
    'key44328': 'value57266',
    'key44921': 'value2575',
},
    {
    'id': 17527487114924,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jodi Patel',
    'address': '779 Macias Trail Apt. 841\nFrancismouth, GU 95763',
    'text': 'Mr really know ground safe plant develop. Fear until reveal can perhaps want little. Simply maintain live knowledge she read.',
    'email': 'herreradebra@example.org',
    'phone_number': '214-504-1221',
    'json': {
    'name': 'Lindsay Barnes',
    'address': '7062 Joseph Dam\nNicoleburgh, DC 19420',
},
    'key23916': 'value71493',
    'key44678': 'value663',
    'key38106': 'value29479',
    'key46070': 'value87791',
    'key15619': 'value41056',
},
    {
    'id': 17527487114935,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Jennifer Edwards',
    'address': '5949 Danielle Valley\nLake Russellburgh, CT 97348',
    'text': 'Action weight lot history performance degree executive. Pattern order identify trouble section.',
    'email': 'williamsglenda@example.net',
    'phone_number': '5679741557',
    'json': {
    'name': 'Vicki Garcia',
    'address': '84692 Montgomery Branch\nChristopherside, MT 80722',
},
    'key29746': 'value98458',
    'key54594': 'value9712',
    'key50378': 'value57575',
    'key17011': 'value87223',
    'key50221': 'value63683',
    'key69107': 'value58750',
    'key65631': 'value97989',
    'key31904': 'value52368',
    'key86694': 'value97330',
},
    {
    'id': 17527487114946,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Deborah Smith',
    'address': '94339 John Via Apt. 970\nWest Lori, SD 95444',
    'text': 'Baby pattern president teacher. Address news listen particularly four senior military. Network wall it send stock consumer black.',
    'email': 'jmartin@example.net',
    'phone_number': '238-844-6659x6317',
    'json': {
    'name': 'Cassandra Edwards',
    'address': '97552 Taylor Ville\nNew Joshuamouth, CO 91626',
},
    'key7892': 'value17277',
    'key4575': 'value49999',
    'key15003': 'value65536',
    'key74234': 'value18117',
},
    {
    'id': 17527487114957,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Benjamin Joyce',
    'address': '13336 Smith Courts\nNorth Timothy, VA 78190',
    'text': 'Decide quality try itself structure key claim. Design growth put recognize.\nWear wear trial. Be door prepare turn federal.',
    'email': 'thompsonarthur@example.net',
    'phone_number': '467-450-1293',
    'json': {
    'name': 'David Gaines',
    'address': '528 Nixon Cove\nPort Shaun, MS 76400',
},
    'key19180': 'value29653',
    'key74754': 'value49490',
    'key29458': 'value15485',
    'key9481': 'value76023',
    'key59369': 'value947',
},
    {
    'id': 17527487114969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Mackenzie Estrada',
    'address': '0109 Sherri Mews Suite 993\nJaneville, AS 97403',
    'text': 'Us system side enter. Child understand mind property beat consumer Congress as. Decision send mean theory. Reflect possible citizen not.\nMake various least reduce.',
    'email': 'atodd@example.net',
    'phone_number': '001-295-700-4846x0186',
    'json': {
    'name': 'Angelica Jimenez',
    'address': '05476 Ryan Stream\nHahnhaven, FM 35490',
},
    'key58083': 'value4820',
    'key69720': 'value74376',
    'key17239': 'value19103',
    'key53681': 'value72246',
},
    {
    'id': 17527487114979,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Jessica Phelps',
    'address': '153 Nichols Club Suite 486\nVelazquezborough, MI 85527',
    'text': 'Explain scientist tell push why although very next. Plant look last unit including raise. Financial sound alone medical. East pretty we around product.',
    'email': 'cole64@example.com',
    'phone_number': '445.874.9762x02213',
    'json': {
    'name': 'Melissa Bishop',
    'address': '186 Prince Mills Suite 747\nJohnton, WY 40811',
},
    'key7541': 'value14383',
    'key13697': 'value31796',
    'key61615': 'value5914',
    'key8046': 'value11988',
    'key94909': 'value43407',
    'key14221': 'value64602',
    'key44958': 'value91244',
    'key14782': 'value87543',
    'key22654': 'value18471',
},
    {
    'id': 17527487114991,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'David Stuart',
    'address': '6368 Connie Mission Apt. 653\nSouth Steven, WA 97320',
    'text': 'Kitchen food send room affect end. Middle citizen argue plan body agent seek free.\nTen firm rich century tree hope head three.\nCentral carry black make no than. Meet piece without give peace.',
    'email': 'joanna52@example.com',
    'phone_number': '3897120459',
    'json': {
    'name': 'Vincent Gilbert',
    'address': '46198 Myers Inlet\nNew Michael, ND 31727',
},
    'key32468': 'value69423',
    'key18156': 'value67207',
    'key78995': 'value23220',
    'key24601': 'value71141',
    'key73451': 'value30211',
    'key9231': 'value40900',
},
    {
    'id': 17527487115002,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Thomas West',
    'address': '3202 Ramirez Squares\nSouth Stephen, NC 70740',
    'text': 'Blue national process chance outside music. According test she avoid catch. Child fact appear hold.\nBillion buy attorney safe candidate. Pass plant west bag fear behavior such.',
    'email': 'adam07@example.com',
    'phone_number': '5837052338',
    'json': {
    'name': 'Gregory White',
    'address': 'Unit 7158 Box 7773\nDPO AA 42246',
},
    'key43603': 'value13590',
    'key23246': 'value99631',
    'key24208': 'value50317',
    'key89063': 'value99077',
    'key31516': 'value14367',
    'key52621': 'value21778',
    'key57183': 'value37915',
    'key93639': 'value80250',
    'key3889': 'value21233',
},
    {
    'id': 17527487115013,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Ashley Cook',
    'address': '6775 Kenneth Trace Suite 952\nWest Brianport, PA 12864',
    'text': 'Spring wrong this focus read class take. Free simple age appear popular wish.\nCare he mention into include property. Important matter under spend customer.',
    'email': 'sjensen@example.org',
    'phone_number': '270.932.0086x8718',
    'json': {
    'name': 'William Floyd',
    'address': '35282 Stephanie Fork\nFrybury, FM 59556',
},
    'key34478': 'value69741',
},
    {
    'id': 17527487115026,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Hunter Ramos',
    'address': '2937 Rebecca Drive Apt. 644\nKevinfurt, MD 68053',
    'text': 'As easy role base human small which. Mrs if provide natural whole act newspaper cause.\nImagine theory like drug able great begin myself. Idea read grow author history.',
    'email': 'zjoseph@example.org',
    'phone_number': '729.236.9542x579',
    'json': {
    'name': 'Kimberly Yang',
    'address': '15094 Patterson Ridge Apt. 831\nAmberhaven, SD 08433',
},
    'key53350': 'value46655',
    'key65109': 'value59324',
    'key23146': 'value53802',
    'key52993': 'value87616',
    'key82023': 'value96425',
    'key44889': 'value50962',
    'key17160': 'value42070',
},
    {
    'id': 17527487115038,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Sean Reid',
    'address': '485 Connor Garden\nSouth Charles, FM 19826',
    'text': 'Music us success fish possible. Add person choose example outside back difference. Meet blood help read economic main.\nTwo suggest executive. Federal mission responsibility toward.',
    'email': 'ryansnyder@example.com',
    'phone_number': '401-241-3159',
    'json': {
    'name': 'Alexander Dunn',
    'address': '2090 Nicholas Rapid Suite 045\nBarrettberg, OR 89440',
},
    'key2653': 'value39606',
    'key95259': 'value41104',
    'key19983': 'value45474',
    'key17988': 'value29976',
    'key96685': 'value21730',
    'key51716': 'value1378',
},
    {
    'id': 17527487115052,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Dr. Richard Nelson',
    'address': '509 Garcia Cliff\nEast Evelynfurt, FL 95148',
    'text': 'Analysis production drug foot. Behind agency notice end decision teacher. Watch nature claim medical.\nThink red stuff some force. Participant dream case new feeling property well.',
    'email': 'maryrich@example.org',
    'phone_number': '579.312.7339',
    'json': {
    'name': 'Steven Crane',
    'address': '41481 Joseph Shoals\nLake Amanda, TX 26626',
},
    'key38507': 'value19912',
    'key47109': 'value84422',
    'key17924': 'value59540',
    'key43077': 'value10759',
    'key215': 'value71164',
    'key87324': 'value12221',
    'key99723': 'value5789',
},
    {
    'id': 17527487115066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Daniel Hall',
    'address': '83745 Patrick Rapids\nEast Katie, SD 75024',
    'text': 'Individual own begin no high edge.\nPresent view meet perhaps be cover defense. Break end theory wear project community move. Cost yes carry away.',
    'email': 'tiffanyavila@example.net',
    'phone_number': '(639)895-3874x16151',
    'json': {
    'name': 'Stephen Burke',
    'address': '3567 Harmon Flats\nPort Selena, AK 32591',
},
    'key75617': 'value97763',
    'key51419': 'value2290',
    'key16750': 'value73990',
    'key48651': 'value19376',
    'key86774': 'value98315',
    'key57112': 'value51304',
    'key30736': 'value88047',
    'key81898': 'value81460',
    'key7780': 'value83567',
    'key77790': 'value48655',
},
    {
    'id': 17527487115080,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Matthew Rodriguez',
    'address': '857 Christopher Falls\nPort Ryanport, CA 78640',
    'text': 'Reality evening partner financial share staff. Reach majority wind his others find. Own nearly hear heavy.\nBuild occur region when fight. Buy statement analysis movement.',
    'email': 'gerald96@example.net',
    'phone_number': '+1-231-577-8817x169',
    'json': {
    'name': 'Richard Tyler',
    'address': '0174 Norris Via Apt. 865\nJameston, MP 24416',
},
    'key63082': 'value73918',
    'key29820': 'value41953',
    'key99189': 'value99030',
    'key25784': 'value15127',
    'key63626': 'value35253',
    'key84603': 'value73427',
},
    {
    'id': 17527487115093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Mr. Michael Mckenzie',
    'address': '467 Jennifer Branch Suite 248\nRamirezhaven, VI 44661',
    'text': 'While sort condition common. Occur condition material ok. Society large nor not stop think.\nCentury thousand likely billion task. Read fill mission.',
    'email': 'xschultz@example.org',
    'phone_number': '702-492-1745',
    'json': {
    'name': 'Barbara Kim',
    'address': '05355 David Locks\nSmithside, MS 45085',
},
    'key8915': 'value86821',
    'key60346': 'value72261',
    'key9258': 'value65503',
    'key97968': 'value47681',
    'key63660': 'value20082',
    'key6189': 'value25660',
    'key85670': 'value84870',
    'key98312': 'value87819',
    'key85102': 'value63856',
},
    {
    'id': 17527487115105,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Joseph Fuller',
    'address': '25430 Thompson Cliffs\nLake Alexisborough, WV 01890',
    'text': 'Account condition wish something include black. Professional fund benefit.',
    'email': 'sanchezaaron@example.net',
    'phone_number': '989.772.9997x410',
    'json': {
    'name': 'Jeff Owen',
    'address': '376 Karen Trail\nKingport, TX 39037',
},
    'key41296': 'value72096',
    'key14395': 'value25662',
    'key68865': 'value94401',
    'key6153': 'value6614',
    'key81335': 'value59491',
    'key52719': 'value62903',
    'key19345': 'value11154',
},
    {
    'id': 17527487115117,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Lauren Mercer',
    'address': '120 Kayla Plaza\nWest Jason, MT 39893',
    'text': 'Federal side get chair. Watch seat another notice. Low benefit light certainly but whatever.',
    'email': 'qkelly@example.org',
    'phone_number': '(517)815-0633x089',
    'json': {
    'name': 'Joanne Jones',
    'address': '20397 Alexander Heights Suite 242\nEast Markside, NE 86599',
},
    'key457': 'value57908',
    'key30969': 'value80080',
    'key50594': 'value95380',
    'key1298': 'value35764',
    'key22349': 'value55663',
    'key97791': 'value29178',
    'key88871': 'value39404',
    'key79577': 'value11633',
},
    {
    'id': 17527487115128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Timothy Quinn',
    'address': '483 Bobby Course Suite 555\nGabrielaborough, WI 32916',
    'text': 'Relationship bit film certain per. Group loss build I.\nNothing what morning line himself management she. Pattern order school American develop. Worker around without maybe medical.',
    'email': 'michaelhess@example.org',
    'phone_number': '322.620.6427x263',
    'json': {
    'name': 'Jared Hoffman',
    'address': 'USCGC Lopez\nFPO AE 68955',
},
    'key73679': 'value32704',
    'key4971': 'value49993',
    'key47578': 'value16946',
},
    {
    'id': 17527487115139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Brittany Gay',
    'address': '9385 Alvarez Wells Apt. 226\nSouth Michaelport, AS 40095',
    'text': 'Everything wonder yet visit unit happy remain.\nContinue need difference save standard five medical. Task executive science walk now identify red. Stay walk never once moment site threat purpose.',
    'email': 'shannonmccall@example.org',
    'phone_number': '(338)582-1425x778',
    'json': {
    'name': 'Emily Graham',
    'address': 'PSC 7501, Box 8613\nAPO AA 19210',
},
    'key23786': 'value50360',
},
    {
    'id': 17527487115149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Sherri Williams',
    'address': '8161 Ruiz Streets\nTylerville, IN 59142',
    'text': 'Stop care maintain dream family music article. Experience image require. Across program record yes member necessary.\nWater together answer scientist response.',
    'email': 'gcharles@example.org',
    'phone_number': '001-224-429-0180x73332',
    'json': {
    'name': 'Jeremy Gibson',
    'address': 'USNS Davis\nFPO AP 86669',
},
    'key72798': 'value76420',
    'key65107': 'value94853',
    'key28751': 'value17517',
    'key43990': 'value24242',
    'key64496': 'value83440',
    'key11375': 'value77781',
    'key92943': 'value97241',
},
    {
    'id': 17527487115160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Kevin Carter',
    'address': '87992 Max Village\nWallsmouth, MI 90323',
    'text': 'Evening second here certain institution among right thousand. Next approach wear very. Wear attorney occur along figure against.\nFind picture owner each. Bed never guess hair.',
    'email': 'edwardmyers@example.com',
    'phone_number': '796.416.8769x9489',
    'json': {
    'name': 'Alexandria Johnson',
    'address': '251 Heather Square\nNew Cherylview, AS 04627',
},
    'key86753': 'value55363',
    'key24235': 'value79577',
    'key99548': 'value65104',
    'key92473': 'value77990',
    'key896': 'value67579',
    'key8689': 'value1097',
    'key81490': 'value45063',
    'key99210': 'value26439',
    'key31330': 'value65317',
    'key32305': 'value74985',
},
    {
    'id': 17527487115172,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Paul Nelson',
    'address': '5894 Williams Green\nEricksonside, TN 53872',
    'text': 'Still begin station necessary ask walk.\nSpeech guess by business training. Against can wife.\nAge him effort care make option past. Ten plant wear meeting no born model. Draw station else none child.',
    'email': 'yfernandez@example.com',
    'phone_number': '615-522-1051x1728',
    'json': {
    'name': 'Susan Vance',
    'address': '571 Faulkner Shore\nDonbury, GU 63316',
},
    'key16561': 'value94720',
    'key82228': 'value90718',
    'key71771': 'value62406',
    'key94607': 'value15698',
    'key85799': 'value61926',
    'key19843': 'value91389',
},
    {
    'id': 17527487115184,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Shannon Vega',
    'address': '152 Ray Mission\nSouth Crystalshire, ND 19735',
    'text': 'Commercial evidence education movement bank fine world. Whatever turn write specific blood quickly first. Guess whom his TV.\nEffort anyone beautiful.\nMaterial tree interview world.',
    'email': 'sdavid@example.net',
    'phone_number': '975.988.5434',
    'json': {
    'name': 'Ann Cobb',
    'address': '89727 Sherri Knolls Suite 652\nNorth Alexis, WV 34192',
},
    'key65965': 'value27030',
    'key61906': 'value71179',
    'key11031': 'value37771',
    'key62243': 'value91390',
    'key29772': 'value74326',
    'key62230': 'value16529',
    'key68619': 'value3218',
    'key79197': 'value69788',
    'key22226': 'value28738',
},
    {
    'id': 17527487115195,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Mrs. Kelly Anderson MD',
    'address': '6040 Elliott Cliff Apt. 258\nSouth Emilymouth, NC 63511',
    'text': 'Man describe moment west near court. Test wind several.\nProcess rich animal dark. A anyone environment realize service wind every. Kitchen mission protect have carry.',
    'email': 'barberamy@example.net',
    'phone_number': '708-576-6062x5956',
    'json': {
    'name': 'Denise Beck',
    'address': '641 Frederick Shores\nNorth Eric, OK 20322',
},
    'key79102': 'value12968',
    'key80035': 'value62118',
    'key24507': 'value65063',
},
    {
    'id': 17527487115209,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Nicholas Cook',
    'address': '63967 Lopez Wells\nChristopherside, MI 87498',
    'text': 'Country whom so financial mention child. Task easy sound leave culture learn find heavy. View discover trouble mention career establish daughter.',
    'email': 'henryjasmin@example.org',
    'phone_number': '(783)702-9604x61553',
    'json': {
    'name': 'Courtney Rowe',
    'address': '805 Brown Haven\nRussellshire, CA 74652',
},
    'key29354': 'value7067',
},
    {
    'id': 17527487115222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Michael Hernandez',
    'address': '7899 Kelly Vista Apt. 474\nZhangmouth, ID 73531',
    'text': 'Light care cultural positive role push. Others sure its heart sort speech. Modern describe assume same as give.',
    'email': 'justin24@example.com',
    'phone_number': '001-462-495-6873x5593',
    'json': {
    'name': 'Dr. Lisa Williams',
    'address': '322 Bell Spur\nEast Harold, IN 15236',
},
    'key5475': 'value10276',
},
    {
    'id': 17527487115236,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Marvin Fisher',
    'address': '735 Nelson Junctions Suite 107\nRichardchester, ME 69967',
    'text': 'Around possible weight market. Will head movement military.\nThousand fine dinner audience trouble.\nExecutive discover author understand because second. Follow financial specific because thing.',
    'email': 'jessicahoward@example.com',
    'phone_number': '(915)437-7109',
    'json': {
    'name': 'Kyle Smith',
    'address': '0119 Sims Burgs\nLake Matthew, IL 44237',
},
    'key43882': 'value30127',
    'key3322': 'value74542',
    'key79427': 'value55073',
    'key93897': 'value92277',
},
    {
    'id': 17527487115250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Jill Barnett',
    'address': '92249 Phillip Path Suite 602\nMorganborough, HI 32473',
    'text': 'Hundred method want around one admit senior. Oil total box general. Peace crime big adult future laugh follow.\nCold even edge us political establish listen. Suffer decide hundred wife south.',
    'email': 'echristensen@example.net',
    'phone_number': '6832470921',
    'json': {
    'name': 'Christopher Roberts',
    'address': '6470 John Terrace\nEast Ryanchester, NV 47193',
},
    'key32126': 'value6378',
    'key60775': 'value77225',
    'key53154': 'value61298',
    'key66554': 'value13003',
    'key32836': 'value31086',
    'key17365': 'value28666',
    'key8211': 'value36290',
    'key95420': 'value39375',
},
    {
    'id': 17527487115263,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jonathan Miller',
    'address': '719 Simpson Highway\nNorth Alexland, IL 94782',
    'text': 'Tv reality end method resource already. Enjoy go doctor heart beat face.\nChild marriage across. Manage word pay daughter include.',
    'email': 'sethhernandez@example.net',
    'phone_number': '206-866-4799',
    'json': {
    'name': 'Ryan Levine',
    'address': '17802 Page Parks\nDonaldport, MA 53078',
},
    'key21711': 'value60992',
    'key49147': 'value93616',
    'key46629': 'value12771',
},
    {
    'id': 17527487115276,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Danny Chapman',
    'address': '42084 Macias Prairie Suite 963\nDerekview, TN 36124',
    'text': 'Nor customer wind past. Bed forget shake generation certain subject.\nRadio chance war story physical machine produce.\nInclude then trip far may sing. Sea break oil however today.',
    'email': 'samanthafritz@example.org',
    'phone_number': '881.757.9751',
    'json': {
    'name': 'Maxwell Clay',
    'address': 'Unit 9261 Box 9892\nDPO AP 14492',
},
    'key58342': 'value92243',
    'key46947': 'value11478',
    'key23371': 'value96201',
},
    {
    'id': 17527487115288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Michelle Hall',
    'address': 'Unit 5411 Box 9443\nDPO AA 33190',
    'text': 'Score suffer figure play war. Player traditional then in local thousand when. Maybe condition condition upon civil history plan specific.',
    'email': 'davidfernandez@example.org',
    'phone_number': '001-886-833-1001x616',
    'json': {
    'name': 'Samuel Diaz',
    'address': '9796 Elizabeth Mill\nKendrachester, IA 68342',
},
    'key13819': 'value2793',
    'key91227': 'value78378',
    'key93737': 'value35623',
    'key84650': 'value24386',
    'key93595': 'value10876',
    'key98493': 'value6963',
    'key75067': 'value76083',
    'key57398': 'value70228',
    'key79704': 'value47952',
    'key9420': 'value49594',
},
    {
    'id': 17527487115300,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Jill Thompson',
    'address': '536 Megan Way\nNorth Elizabethburgh, MS 44132',
    'text': 'Represent already go. Relate century ok data. Rule thousand live guy.\nMiss discussion especially although save service.\nStore box activity. House politics ask sound.',
    'email': 'kennedyblake@example.net',
    'phone_number': '(746)715-9618',
    'json': {
    'name': 'Morgan Williams',
    'address': '808 David Shoals Suite 306\nKlinechester, DE 83120',
},
    'key56502': 'value46306',
    'key92477': 'value208',
    'key57835': 'value89908',
    'key78613': 'value68726',
    'key87155': 'value75999',
    'key79923': 'value9865',
},
    {
    'id': 17527487115314,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jerome Montes',
    'address': '68802 Misty Cliff Suite 606\nEast Michelle, VI 31188',
    'text': 'Skill party step their. Market bit network image.\nBorn value condition generation hit up. Body answer three business watch.\nWorry help building budget college.',
    'email': 'fergusontravis@example.net',
    'phone_number': '001-737-909-5262',
    'json': {
    'name': 'Timothy Guzman',
    'address': 'Unit 5809 Box 3597\nDPO AP 71398',
},
    'key26769': 'value78940',
    'key86378': 'value21851',
    'key52076': 'value14840',
    'key76328': 'value44912',
    'key44975': 'value78369',
    'key82666': 'value21723',
    'key51421': 'value46011',
    'key67601': 'value62325',
},
    {
    'id': 17527487115326,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Cathy Myers',
    'address': '743 Mooney Green\nEast David, LA 60279',
    'text': 'Road small likely democratic. Positive soldier past scientist sense admit claim. Behind PM he bar skin. Player next hear your.',
    'email': 'saunderssarah@example.net',
    'phone_number': '(402)202-2353',
    'json': {
    'name': 'Stephen Ruiz',
    'address': '30506 Richards Point\nEdwinside, KY 32374',
},
    'key61622': 'value12881',
    'key11013': 'value4181',
},
    {
    'id': 17527487115340,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Cindy Strickland',
    'address': '410 Rhonda Circles Apt. 226\nLake Matthewstad, KY 81259',
    'text': 'Item its can raise fight news reduce majority. Name professor wide do property learn item. Single value suddenly need best charge. Fish skill which themselves detail model hard.',
    'email': 'erinrobinson@example.org',
    'phone_number': '319-656-2049',
    'json': {
    'name': 'Brian Cobb',
    'address': '3738 Jeremy Rue Suite 251\nNorth Mary, KS 37122',
},
    'key26691': 'value15305',
    'key49934': 'value21575',
},
    {
    'id': 17527487115352,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Maria King',
    'address': '87091 Bray Passage\nNorth Alyssabury, SC 44227',
    'text': 'White chair country cell blood do less. Statement citizen need pressure. Woman recognize show.\nEnd account which cold item ok.',
    'email': 'bryan65@example.net',
    'phone_number': '+1-277-776-8285x870',
    'json': {
    'name': 'Ryan Castillo',
    'address': '6891 Miller Burg Apt. 667\nMartinview, NY 50862',
},
    'key13275': 'value61588',
    'key60233': 'value63537',
    'key79259': 'value63447',
    'key53304': 'value4703',
    'key50644': 'value50772',
    'key32196': 'value75521',
},
    {
    'id': 17527487115364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Abigail Bailey DVM',
    'address': '82263 Dean Mountains Apt. 958\nEricville, WI 47319',
    'text': 'Rather lose since keep look. Right staff effort act reason.\nDrive manage could money military. Born hotel unit meeting ability suddenly. Player property usually. Give guy lot activity coach.',
    'email': 'treeves@example.com',
    'phone_number': '489.481.7984x9371',
    'json': {
    'name': 'Anita Sheppard',
    'address': '236 Tucker Viaduct Apt. 868\nPort Jessicaton, MP 05079',
},
    'key89004': 'value90806',
    'key67456': 'value55670',
    'key84789': 'value48000',
    'key23752': 'value41924',
    'key29983': 'value12660',
    'key41620': 'value65187',
    'key17165': 'value6437',
    'key64852': 'value17612',
    'key59870': 'value52956',
    'key31236': 'value24612',
},
    {
    'id': 17527487115375,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Mary Andrade',
    'address': '0008 Martin Views Suite 054\nLake Shelleyview, CA 24819',
    'text': 'Recently event likely nice great. Choice certain simple statement rise. Wall voice us bill tree produce find.',
    'email': 'jbush@example.com',
    'phone_number': '279.773.5396x0422',
    'json': {
    'name': 'Kimberly Lucas',
    'address': '9177 Morgan Springs\nWalkerville, NJ 24259',
},
    'key64586': 'value49270',
    'key43598': 'value17496',
    'key72356': 'value84161',
    'key86761': 'value43719',
    'key94889': 'value30862',
    'key15348': 'value80521',
    'key42590': 'value98817',
    'key76372': 'value21435',
},
    {
    'id': 17527487115386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Michael Pitts',
    'address': '5764 Jackson Mountain\nNeilburgh, KY 41322',
    'text': 'Reach financial no building.\nToo hour again appear own word see. Ago onto skin mention.',
    'email': 'amanda74@example.com',
    'phone_number': '612.623.1064',
    'json': {
    'name': 'Adam Grant',
    'address': '64238 Kimberly Dam Apt. 739\nNorth Deborahside, NJ 94238',
},
    'key92274': 'value95599',
    'key48470': 'value79852',
    'key50839': 'value45710',
    'key9947': 'value8838',
    'key2529': 'value96460',
    'key88174': 'value40936',
},
    {
    'id': 17527487115399,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Robin Martinez',
    'address': '093 John Brooks Suite 574\nNorth Christina, OR 83896',
    'text': 'Them often put responsibility. Conference significant since. Hard service face option key reduce about.\nAdult together nature improve top. Water get worry same shake dog.',
    'email': 'carolynstein@example.com',
    'phone_number': '(783)546-7354x6215',
    'json': {
    'name': 'Monica Scott',
    'address': '986 Cory Brooks\nNew Brittany, OK 61677',
},
    'key29522': 'value15810',
    'key72201': 'value80925',
    'key29': 'value29390',
    'key56422': 'value34480',
    'key96755': 'value3481',
},
    {
    'id': 17527487115412,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Brooke Thompson',
    'address': '315 Rogers Hills\nEast Donald, NE 57543',
    'text': 'Whole instead toward perhaps. Take accept feeling threat rather organization phone various.\nLikely point prepare PM economy goal. Environmental some bar recently.',
    'email': 'laura28@example.net',
    'phone_number': '930.892.0120',
    'json': {
    'name': 'Chelsea Figueroa',
    'address': '859 Mcmahon Road Apt. 949\nNew Kevinton, IA 37711',
},
    'key64729': 'value21224',
    'key11757': 'value71725',
    'key78226': 'value95255',
    'key52924': 'value78933',
    'key43982': 'value49751',
    'key84891': 'value765',
    'key53477': 'value73536',
},
    {
    'id': 17527487115425,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Amanda Scott',
    'address': '303 Robert Stravenue\nJamieland, DC 72936',
    'text': 'Cause could visit gun. Human toward no here.\nShoulder onto person Congress process though result deep. Nice business staff against affect price main.',
    'email': 'gavery@example.com',
    'phone_number': '553.391.7542x7064',
    'json': {
    'name': 'Johnny Mason',
    'address': '76312 Crystal Wells Apt. 586\nWest Eduardoberg, PR 60161',
},
    'key77059': 'value14469',
    'key956': 'value86058',
    'key39425': 'value60105',
    'key38353': 'value93496',
    'key56138': 'value27781',
    'key7341': 'value60350',
},
    {
    'id': 17527487115438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Tammy Ramos',
    'address': '673 Short Lights\nMacdonaldshire, AL 49879',
    'text': 'Occur college your against per present memory. Lay wait employee travel drive.',
    'email': 'holderchad@example.com',
    'phone_number': '686.852.5907x5567',
    'json': {
    'name': 'Aaron Reed',
    'address': '90893 Schmidt Hills\nKennethchester, KY 25570',
},
    'key65883': 'value34905',
    'key36453': 'value32690',
    'key10094': 'value70459',
    'key85250': 'value73577',
    'key8422': 'value37120',
    'key82187': 'value73543',
},
    {
    'id': 17527487115452,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Tammy Campbell',
    'address': '73261 Lori Island Apt. 359\nShelbybury, NV 52304',
    'text': 'Wrong girl find medical produce better west. Western especially good admit bad social hair.\nAdd customer relationship yes mission thus. Instead air must it key majority quite.',
    'email': 'coreyjohnson@example.com',
    'phone_number': '233-993-5761',
    'json': {
    'name': 'Susan Mitchell',
    'address': '345 Strong Brooks Apt. 025\nNew Johnshire, NJ 57725',
},
    'key93579': 'value69032',
    'key99794': 'value51897',
    'key51317': 'value66930',
    'key57562': 'value91985',
    'key38717': 'value90246',
    'key43508': 'value40042',
},
    {
    'id': 17527487115466,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Mary Hurst',
    'address': 'USS Walker\nFPO AA 89923',
    'text': 'Product free success manage. Rise scene big. Job store should start. Travel heavy across born girl listen hand rise.\nFinancial worker international drop rock line.',
    'email': 'rjohnson@example.net',
    'phone_number': '702.460.2453',
    'json': {
    'name': 'Brandy Spence',
    'address': 'USNV Miller\nFPO AP 43601',
},
    'key40491': 'value31305',
    'key40131': 'value35578',
    'key9305': 'value76849',
    'key31939': 'value4253',
    'key95203': 'value46588',
    'key84437': 'value76309',
    'key17872': 'value79422',
    'key51658': 'value4082',
},
    {
    'id': 17527487115477,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Taylor Carlson',
    'address': '91109 Andrea Plaza Suite 375\nNorth Mary, NC 00936',
    'text': 'Realize evidence minute watch open. Its great his player cell knowledge everybody much.\nTheory impact lose design.\nLaw alone benefit fill person policy. Sister author only positive cut ok keep girl.',
    'email': 'robertfernandez@example.org',
    'phone_number': '647.888.0995',
    'json': {
    'name': 'Eric Morse',
    'address': '98056 Chloe Path\nSouth Jesse, AS 13559',
},
    'key26804': 'value17895',
    'key79895': 'value71056',
    'key5248': 'value32158',
    'key9273': 'value72273',
    'key26408': 'value72928',
    'key35989': 'value92308',
    'key96183': 'value66003',
    'key8792': 'value62391',
    'key32090': 'value47011',
},
    {
    'id': 17527487115490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Kimberly Rios',
    'address': '919 Timothy Hills Suite 541\nLake Christopherchester, NV 30934',
    'text': 'State under whom contain color care. Shoulder beautiful force difference. Out sit write never.',
    'email': 'elizabethbaker@example.com',
    'phone_number': '+1-235-604-5184x8433',
    'json': {
    'name': 'Susan Hines',
    'address': '0295 Vincent Stream Suite 328\nNew Timothyside, WI 65966',
},
    'key74729': 'value44836',
    'key54798': 'value15419',
    'key75322': 'value2246',
},
    {
    'id': 17527487115502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Deborah Long',
    'address': '01900 Ronald Hollow\nOrtizside, AR 04527',
    'text': 'Cost central positive billion admit. Threat piece order treat fish hair. Rule again century. Prepare official avoid attack life arrive example.',
    'email': 'ismith@example.com',
    'phone_number': '+1-986-291-6458x326',
    'json': {
    'name': 'Jessica Taylor',
    'address': 'PSC 8116, Box 7626\nAPO AE 47651',
},
    'key59169': 'value36538',
    'key41223': 'value90967',
    'key24625': 'value8071',
    'key65799': 'value37261',
    'key87863': 'value26404',
    'key86555': 'value85912',
    'key99487': 'value63924',
    'key533': 'value26427',
},
    {
    'id': 17527487115511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Timothy Martin III',
    'address': '36446 Richard Ridge Suite 962\nAndersonside, AS 21129',
    'text': 'Candidate history reason senior discuss charge. Third key future city lay. Memory community including thousand total mouth.\nOver side end as occur. Watch sort protect eight your.',
    'email': 'umoran@example.net',
    'phone_number': '+1-979-789-6098x34037',
    'json': {
    'name': 'Stephanie Thornton',
    'address': '0434 Gomez Springs Suite 656\nCookville, SD 77351',
},
    'key19216': 'value68202',
    'key47238': 'value32050',
},
    {
    'id': 17527487115522,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Brianna Donovan',
    'address': '036 Scott Plains Suite 113\nMartinezfort, IL 58395',
    'text': 'Myself case out still next participant young. Help measure must blood. Likely save trouble since whole.\nRoad feel company. Less prepare seven control speak wife while where.',
    'email': 'josestewart@example.com',
    'phone_number': '+1-239-575-0964x4136',
    'json': {
    'name': 'Connie Pennington',
    'address': '265 Natalie Islands\nHodgesville, AZ 21004',
},
    'key41247': 'value69745',
    'key44819': 'value91190',
    'key25770': 'value36148',
    'key47589': 'value19746',
    'key50731': 'value90297',
    'key88009': 'value59029',
    'key34317': 'value17738',
},
    {
    'id': 17527487115535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'John Lopez',
    'address': '021 Walker Villages\nBradyburgh, OH 70019',
    'text': 'Threat remember middle almost pick financial hair. Spring maintain blue interview way base. Finish including improve foreign step teacher.',
    'email': 'jensentimothy@example.org',
    'phone_number': '361.334.8827x455',
    'json': {
    'name': 'Robert Murray',
    'address': '7692 Brittney Place Suite 698\nGibbsfort, MN 92590',
},
    'key2949': 'value9845',
    'key87914': 'value47631',
    'key85739': 'value60544',
    'key67095': 'value84172',
    'key15839': 'value3117',
    'key1165': 'value17490',
},
    {
    'id': 17527487115548,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Carol Walsh',
    'address': '23990 Cook Plaza\nCharleston, MT 61141',
    'text': 'Soon member situation everyone year structure. Range that result hard voice.\nAnother reason majority teacher contain course produce century. Cost rock shake although.',
    'email': 'marcuslambert@example.org',
    'phone_number': '766.249.4579',
    'json': {
    'name': 'Hayley Wilson',
    'address': '569 Aaron Road Suite 576\nWest Brandonmouth, FM 72243',
},
    'key98349': 'value72384',
    'key99919': 'value62996',
},
    {
    'id': 17527487115560,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Leslie Riley',
    'address': '3825 Lang Cove Apt. 029\nNorth Huntertown, NC 33032',
    'text': 'Mouth reveal magazine section resource manager general. Good indicate pressure project son cup nature. Writer employee its course senior stage expect. Common movement their us current care.',
    'email': 'james86@example.net',
    'phone_number': '801.715.5551x267',
    'json': {
    'name': 'William Cobb',
    'address': '3615 Kaitlyn Mills Apt. 396\nSouth Brendaburgh, AZ 85281',
},
    'key6186': 'value89272',
    'key11126': 'value14050',
    'key39054': 'value50910',
    'key72219': 'value7049',
},
    {
    'id': 17527487115572,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Michael Calhoun',
    'address': '694 Christopher Terrace\nNew Teresahaven, UT 67995',
    'text': 'Another word design school pressure government. Environment draw hundred material scientist hour. Whom present goal reach friend responsibility.',
    'email': 'turnerjohn@example.org',
    'phone_number': '(501)952-2393x9711',
    'json': {
    'name': 'Lawrence Andrews',
    'address': 'USCGC Williams\nFPO AA 04986',
},
    'key33443': 'value45039',
},
    {
    'id': 17527487115584,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Donald Jackson',
    'address': '107 Silva Junctions Suite 302\nCampostown, IL 44101',
    'text': 'Citizen better sea.\nQuite energy fact very serious. High arrive all market for south board force.\nDrop how defense once. While concern green seven floor drive TV. Cut bill stock take officer.',
    'email': 'adamdurham@example.net',
    'phone_number': '+1-760-754-0376x58326',
    'json': {
    'name': 'Sally Mccoy',
    'address': '7378 Michael Bypass Suite 711\nWaynechester, MI 62651',
},
    'key43010': 'value38065',
    'key81308': 'value86273',
    'key65762': 'value67153',
    'key89671': 'value53445',
    'key44442': 'value24947',
    'key4109': 'value93696',
    'key40601': 'value8032',
    'key57461': 'value10127',
},
    {
    'id': 17527487115599,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Lisa Alexander',
    'address': '00306 Nichols Forks Apt. 636\nHendricksmouth, DE 84809',
    'text': 'Thing guy once street course. Action possible parent put street. Recognize sound argue feeling.\nUp choose for up wind. Guess source receive institution nor life carry.',
    'email': 'ubridges@example.net',
    'phone_number': '(515)652-0492',
    'json': {
    'name': 'Shaun Alexander',
    'address': '662 Benson Port\nWatersport, MO 81052',
},
    'key55651': 'value96350',
    'key26017': 'value81780',
    'key69886': 'value61220',
},
    {
    'id': 17527487115612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Adriana Molina',
    'address': '31523 Smith Orchard\nStephanieside, OH 33379',
    'text': 'Drop radio human break any. Home executive national Mrs sell. Ground everyone any project social.',
    'email': 'castilloamanda@example.net',
    'phone_number': '001-391-714-7397x4419',
    'json': {
    'name': 'Howard Reid',
    'address': '03533 Francis Trail\nLaurahaven, KS 37305',
},
    'key87042': 'value73922',
    'key72241': 'value72390',
    'key23900': 'value85828',
    'key96147': 'value89285',
    'key30779': 'value79109',
},
    {
    'id': 17527487115626,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Ashley Caldwell',
    'address': '93200 Jessica Shores\nAdamstown, NC 97115',
    'text': 'Detail front ahead. With clearly real physical. Top drop behind may significant finish.\nThat soon itself in. Open hot condition tend forget mention marriage. Service long after receive land sound.',
    'email': 'robbinstanya@example.org',
    'phone_number': '568.832.1648',
    'json': {
    'name': 'Yolanda Sanders',
    'address': '851 Mcclain Falls\nLake Amanda, KS 75277',
},
    'key69236': 'value47539',
    'key92341': 'value70543',
    'key82667': 'value75509',
    'key33513': 'value46164',
    'key24797': 'value9429',
    'key28378': 'value25404',
    'key81688': 'value97196',
    'key45334': 'value68338',
    'key94142': 'value27593',
},
    {
    'id': 17527487115640,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Olivia Miller',
    'address': '518 Matthew Burg Apt. 391\nPort Steven, KY 68634',
    'text': 'Performance four future suffer. On admit official better. Within middle man letter response.\nAgency crime very service. Song live life cup upon start arrive.',
    'email': 'tracysmith@example.net',
    'phone_number': '568-711-4483x270',
    'json': {
    'name': 'Thomas Rogers',
    'address': '093 Huff Motorway Apt. 621\nLake Brianview, PR 25491',
},
    'key22775': 'value29359',
    'key17779': 'value50163',
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
    'RequestId': '2b290c00-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_25_398290jasuLLTL',
    'filter': 'uid > 0',
    'limit': 100,
    'offset': 0,
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '2b290c00-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_25_398290jasuLLTL',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 00]_1752748717.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid001752748717Json()
    test.run_tests()
