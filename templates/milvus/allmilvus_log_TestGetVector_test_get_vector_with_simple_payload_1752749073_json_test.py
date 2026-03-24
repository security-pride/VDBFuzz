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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestGetVector_test_get_vector_with_simple_payload_1752749073_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752749073.json"
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



class AllmilvusLogtestgetvectorTestGetVectorWithSimplePayload1752749073Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752749073.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752749073.json"
        self.test_count = 6  # 测试方法数量
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
    'RequestId': '01478992-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_24_630363BOmpJEGK',
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
    'RequestId': '01478992-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_24_630363BOmpJEGK',
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
    'RequestId': '01478992-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_24_630363BOmpJEGK',
    'data': [
    {
    'id': 17527490706692,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Amy Phillips',
    'address': '6566 Long Place Apt. 247\nNorth Zacharyview, MD 20687',
    'text': 'Run thing talk behind him natural. Human political fish major list. Clear eye sometimes television.',
    'email': 'garciadaniel@example.net',
    'phone_number': '884-215-7360x02520',
    'json': {
    'name': 'Kathleen Montgomery',
    'address': '576 Donna Pine Apt. 628\nNorth Williambury, NV 98841',
},
    'key68642': 'value48832',
    'key33701': 'value68209',
    'key98236': 'value9722',
    'key58451': 'value35671',
},
    {
    'id': 17527490706709,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Billy Leon',
    'address': '9981 Johnson Corner Suite 955\nAnthonychester, OR 62960',
    'text': 'Sister hour rise. Particular person firm area learn on. Theory operation sit drug.',
    'email': 'trevormayer@example.org',
    'phone_number': '(490)526-8597',
    'json': {
    'name': 'Paul King',
    'address': '199 Angela River\nAnthonyfort, PR 37777',
},
    'key26956': 'value614',
    'key112': 'value39696',
},
    {
    'id': 17527490706722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Christopher Johnson',
    'address': '1575 Johnson Curve Apt. 214\nNorth Julie, HI 69270',
    'text': 'Hear after hotel effort fine candidate. Company great option note.\nAlways discussion fish responsibility game receive task.\nLine perform coach wait from. Three ahead use fill.',
    'email': 'sjohnson@example.net',
    'phone_number': '3374398945',
    'json': {
    'name': 'Briana Hamilton',
    'address': '446 Murray Green Apt. 482\nDonnaville, MP 80456',
},
    'key21860': 'value16568',
    'key62003': 'value31675',
    'key19565': 'value68964',
    'key43215': 'value51483',
    'key24635': 'value868',
},
    {
    'id': 17527490706735,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Zachary Olsen',
    'address': '9256 Hernandez Wells Apt. 429\nWest Walterport, WA 37398',
    'text': 'Still once personal home chair organization necessary Mr. Movement night strong present myself design between.\nReally to such wind join visit. Very develop type special order once.',
    'email': 'shawn65@example.com',
    'phone_number': '512-782-7224',
    'json': {
    'name': 'Mary Miller',
    'address': '7104 Hickman Cape Suite 293\nAshleyland, AS 48411',
},
    'key69805': 'value53206',
    'key62475': 'value73699',
},
    {
    'id': 17527490706747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Peter Smith',
    'address': '57180 Riley Stream Apt. 661\nAlejandrofort, AR 60145',
    'text': 'Benefit value among include sure. Area teacher including offer. Than painting glass place federal people.',
    'email': 'melinda62@example.org',
    'phone_number': '347-630-6667',
    'json': {
    'name': 'Richard Rose',
    'address': '9042 Huynh Parkway\nPort Michaela, PW 74710',
},
    'key34419': 'value59800',
    'key81808': 'value56242',
    'key68638': 'value47039',
},
    {
    'id': 17527490706758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Brandon Graham',
    'address': '55919 Hicks Flat Apt. 603\nEast Tiffany, WV 22300',
    'text': 'Enjoy because determine beautiful admit painting bring. Generation environmental hotel land level peace. Staff already lot most which.',
    'email': 'hawkinskevin@example.com',
    'phone_number': '(945)395-2841x8110',
    'json': {
    'name': 'Danielle Norris',
    'address': '217 Gabriel Extensions Apt. 815\nAlexchester, AR 46595',
},
    'key82530': 'value92747',
    'key99640': 'value8025',
    'key19343': 'value41748',
},
    {
    'id': 17527490706770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Emily Ortega',
    'address': '957 Sutton Manors\nLake Anthony, TX 38735',
    'text': 'Skin never eat TV grow ten finish.\nIf history our hundred. Fly whatever bill leg listen understand Democrat way. American generation senior recognize. If guy still important provide candidate.',
    'email': 'kimcarter@example.org',
    'phone_number': '(245)499-8957x2899',
    'json': {
    'name': 'Briana Garner',
    'address': '761 Jones Route Suite 992\nNorth Wendyside, SC 40180',
},
    'key44755': 'value49861',
    'key25485': 'value49852',
    'key75961': 'value28985',
    'key3744': 'value88906',
    'key66640': 'value2550',
    'key92053': 'value78467',
    'key7087': 'value11127',
    'key86595': 'value84587',
    'key65743': 'value66065',
    'key36721': 'value19247',
},
    {
    'id': 17527490706782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Shelly Butler',
    'address': '39317 Karen Viaduct Apt. 886\nDanielleburgh, DC 75211',
    'text': 'Pretty card imagine agree. That evening mention reduce clear. Program never defense. Expert health various main ten.',
    'email': 'akemp@example.org',
    'phone_number': '+1-723-988-3081',
    'json': {
    'name': 'Kaitlyn Turner',
    'address': '504 Connor Lights Apt. 232\nDawnville, TX 61342',
},
    'key31630': 'value93945',
    'key75449': 'value1866',
    'key58013': 'value70836',
},
    {
    'id': 17527490706793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jessica Beck',
    'address': '55059 Jackson Wall\nLake Cindy, OK 87303',
    'text': 'So deep south raise management century value discuss. Information matter education pass cover present general join. Suggest on theory attention activity center.',
    'email': 'bonnie59@example.net',
    'phone_number': '(600)462-9176x870',
    'json': {
    'name': 'James Rice',
    'address': 'PSC 2810, Box 6404\nAPO AA 30333',
},
    'key6086': 'value76843',
    'key90310': 'value96449',
    'key86579': 'value84937',
    'key37763': 'value95752',
    'key76391': 'value23430',
    'key24259': 'value26467',
},
    {
    'id': 17527490706802,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'James Doyle MD',
    'address': '16233 Maria Drives Suite 898\nHectorland, MI 73091',
    'text': 'Meeting least lay simply myself concern pay sit. Billion man yard cultural. Race quickly particular study clear ball suffer quality.\nForget care word. Line race effect build truth possible.',
    'email': 'sbailey@example.org',
    'phone_number': '399-598-8564',
    'json': {
    'name': 'Jennifer Reed',
    'address': '6011 Krause Ramp Apt. 424\nWest Christian, OR 33554',
},
    'key54222': 'value85700',
    'key79443': 'value58505',
    'key71544': 'value19713',
    'key78820': 'value82589',
    'key54075': 'value77716',
    'key81816': 'value79229',
    'key8526': 'value30670',
    'key55048': 'value2723',
    'key58395': 'value42931',
},
    {
    'id': 17527490706813,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Angel Johnson',
    'address': '0171 Breanna Lock\nMorrisonhaven, IN 06184',
    'text': 'Tough the positive discuss guy. Sing low rest today least. Rather him could your.\nIssue door compare industry build when change. Push situation set mention simple line and. Agree certain answer four.',
    'email': 'dramirez@example.com',
    'phone_number': '(989)640-5432x84622',
    'json': {
    'name': 'Devin Richards',
    'address': '05392 David Trafficway\nEast Barbara, OH 17574',
},
    'key29352': 'value97046',
    'key58699': 'value78461',
    'key75714': 'value45466',
    'key39129': 'value38395',
    'key50426': 'value35704',
},
    {
    'id': 17527490706824,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Isabella Barnes',
    'address': '8849 Rachael Pines Apt. 286\nJacquelineville, DE 73310',
    'text': 'Work enough executive office white poor wall public. Into heavy ask drug why the. Stock concern possible.\nGreat you general national.',
    'email': 'christinawilliams@example.net',
    'phone_number': '581-422-7706',
    'json': {
    'name': 'Hunter Ford',
    'address': '44318 Michele Roads\nPort Paultown, KY 96571',
},
    'key45560': 'value74259',
    'key83624': 'value33970',
    'key79125': 'value7761',
    'key51635': 'value13116',
    'key97465': 'value26424',
    'key77499': 'value54528',
},
    {
    'id': 17527490706836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Jeff Fisher',
    'address': '253 Corey Common Suite 216\nWest Courtney, DE 38044',
    'text': 'Research language executive debate phone suggest product. Now hard because others suffer. Believe special figure indeed black.',
    'email': 'brownnoah@example.com',
    'phone_number': '363-685-4091x141',
    'json': {
    'name': 'David Rivas',
    'address': '6637 Fletcher Glens\nKingtown, MP 69025',
},
    'key84635': 'value47684',
    'key20417': 'value17071',
    'key31314': 'value24557',
    'key8845': 'value41880',
    'key85483': 'value18380',
},
    {
    'id': 17527490706847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jill Hensley',
    'address': '88948 Diaz Circles Apt. 759\nIvanfurt, OH 42829',
    'text': 'Force must agency stage couple prepare loss may. Half return bill current.\nWho next attack approach. My discuss in reveal best. Teach once produce feeling ability.',
    'email': 'bevans@example.net',
    'phone_number': '642.889.4547',
    'json': {
    'name': 'Valerie Robinson',
    'address': '12755 Laura Prairie Suite 026\nBarnesmouth, MN 64987',
},
    'key55704': 'value60740',
    'key72981': 'value62378',
    'key16636': 'value9765',
    'key97443': 'value90878',
    'key98835': 'value35234',
    'key4443': 'value95168',
    'key9873': 'value95744',
    'key52923': 'value97160',
    'key13412': 'value25030',
},
    {
    'id': 17527490706859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Destiny Jacobs',
    'address': '6528 Sanchez Ways\nBradleyfurt, ID 88789',
    'text': 'Single hit manager art letter property. Here employee painting few admit.\nInternational something institution other. Design girl almost leader. Political hope front from training article fast human.',
    'email': 'xfernandez@example.org',
    'phone_number': '+1-608-766-9610x4754',
    'json': {
    'name': 'Alan Larson',
    'address': '587 Rivas Coves\nKathleenton, MT 84893',
},
    'key95976': 'value58876',
    'key82660': 'value34465',
},
    {
    'id': 17527490706869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'John Conner',
    'address': '2902 Perry Freeway Apt. 285\nCandaceport, NJ 11001',
    'text': 'Page me several big sign design necessary. Yes class mind final.\nHome quality career. Look especially service. Technology nice some school the contain. Toward open health military.',
    'email': 'cynthia70@example.com',
    'phone_number': '5096157122',
    'json': {
    'name': 'Dr. Lindsey Cox',
    'address': '3536 Amber Bypass Apt. 186\nLake Rebeccahaven, PA 34786',
},
    'key79107': 'value7307',
    'key57389': 'value26784',
    'key93010': 'value64225',
    'key23390': 'value40056',
    'key23334': 'value9151',
},
    {
    'id': 17527490706880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Bruce Cross DVM',
    'address': '80287 Michael Corner Apt. 166\nSouth Benjaminview, MS 62350',
    'text': 'Boy capital fact beat something. It though develop should.\nTell coach television red wonder film his. President attention low financial. Pressure star find she.',
    'email': 'garciachristine@example.com',
    'phone_number': '357.238.3174x67137',
    'json': {
    'name': 'Ashley Lewis',
    'address': '9488 April Glen\nJohnstad, WV 27202',
},
    'key31349': 'value37790',
    'key30614': 'value21165',
    'key58417': 'value85402',
    'key28763': 'value96533',
},
    {
    'id': 17527490706892,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Donald Holt',
    'address': '4349 Julie Mountain\nJamesfort, CA 66589',
    'text': 'Blood inside might meeting talk far. Share while yes series goal soon under. Religious section suddenly require nation.',
    'email': 'gfarmer@example.net',
    'phone_number': '649.324.1083x636',
    'json': {
    'name': 'Jimmy Myers',
    'address': '326 Roberto Divide\nChristineland, RI 02258',
},
    'key84660': 'value47969',
    'key77143': 'value94575',
    'key49844': 'value59993',
    'key99513': 'value82044',
    'key42526': 'value56426',
    'key99874': 'value47912',
    'key59683': 'value56367',
},
    {
    'id': 17527490706901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Michelle Fox',
    'address': '0543 Johnson Mountains\nSouth Michaelview, VI 03392',
    'text': 'Manage eat whatever offer upon. Message wish generation us special. Parent defense which style should.\nManager food class least. Perhaps simply identify what read hit learn American.',
    'email': 'samantha57@example.net',
    'phone_number': '001-329-677-3274x08755',
    'json': {
    'name': 'Mitchell Harris',
    'address': '20807 Michael Mews Apt. 520\nPort Douglasview, TN 09758',
},
    'key4584': 'value43769',
    'key49411': 'value1249',
    'key66172': 'value80437',
    'key74742': 'value98764',
    'key54193': 'value95617',
    'key78277': 'value90390',
    'key41492': 'value55687',
    'key25540': 'value77120',
},
    {
    'id': 17527490706912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jesus Wang',
    'address': '990 Brittany Ranch\nNorth Gabrielville, IL 95708',
    'text': 'Author station kind effect. Matter against white yard arm entire.\nCommon season its none seek sister difference.',
    'email': 'thomasmorgan@example.org',
    'phone_number': '001-605-431-5909x5272',
    'json': {
    'name': 'Tiffany Jensen',
    'address': '84334 Amber Spring Suite 602\nWest Jaime, WI 85231',
},
    'key66643': 'value84434',
    'key32394': 'value95752',
    'key88918': 'value44085',
    'key33318': 'value25176',
    'key70286': 'value9156',
    'key48039': 'value62700',
    'key73669': 'value85264',
},
    {
    'id': 17527490706923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Jeanne Jacobs',
    'address': '0438 Leroy Well Apt. 059\nNew Jessica, NJ 68982',
    'text': 'Degree rich may election without. Officer the agent meeting executive chair.\nConsider than same right its try. Thing know do deep. Picture attorney seat traditional might.',
    'email': 'smithjerome@example.com',
    'phone_number': '+1-410-249-3832x281',
    'json': {
    'name': 'Lisa Williams',
    'address': '261 Rachel Parkway\nMasonville, OH 22247',
},
    'key54033': 'value67474',
    'key46018': 'value92031',
    'key58773': 'value14837',
    'key21446': 'value36386',
    'key18534': 'value73953',
},
    {
    'id': 17527490706934,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Scott Ellison',
    'address': '555 Kline Skyway Apt. 782\nWest Sabrinaport, GU 84437',
    'text': 'Two store team girl lose economy person feeling. Instead coach ball room. Data film population speech fear choice agent.\nProduction help send our laugh. Lot act bill recently drug national bad.',
    'email': 'nancy33@example.net',
    'phone_number': '001-501-644-1012x983',
    'json': {
    'name': 'Dr. Lauren Hall',
    'address': '534 Mark Junctions\nNew Yvonneport, NC 38578',
},
    'key27792': 'value46942',
    'key11588': 'value5500',
    'key67055': 'value22701',
    'key22616': 'value1433',
    'key5393': 'value36636',
},
    {
    'id': 17527490706945,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Tricia Valdez',
    'address': 'PSC 2296, Box 3529\nAPO AP 14288',
    'text': 'Pressure agreement night author. Place if time security itself crime answer.\nWithin early politics study group style improve. Lose interest scene scientist. Factor goal hand scene behind after.',
    'email': 'vwu@example.net',
    'phone_number': '622.260.9452x920',
    'json': {
    'name': 'Bradley Taylor',
    'address': 'PSC 1676, Box 3208\nAPO AE 55245',
},
    'key47184': 'value94389',
    'key22921': 'value56812',
},
    {
    'id': 17527490706952,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Brent Richardson',
    'address': '0958 Martin Rue Suite 209\nClarkstad, FM 07807',
    'text': 'Stand raise recent place firm head. Since that high accept beat.\nResearch hand time nation quite certainly. Natural become push argue professor. Name support worry none since should expert.',
    'email': 'wayne00@example.org',
    'phone_number': '262-664-6962x77121',
    'json': {
    'name': 'Rose Holt',
    'address': '7128 Christine Hill Apt. 751\nSouth Cassidyland, TN 07861',
},
    'key23364': 'value91399',
},
    {
    'id': 17527490706963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Summer Barton',
    'address': 'USS Solis\nFPO AA 52800',
    'text': 'Challenge note establish health. Plant thought talk protect.',
    'email': 'briana72@example.net',
    'phone_number': '257.619.8725x8481',
    'json': {
    'name': 'Andrea Holmes',
    'address': '41973 Joseph Stream Suite 680\nNew Courtney, IL 73939',
},
    'key79581': 'value14787',
    'key44389': 'value527',
    'key93665': 'value52644',
    'key67717': 'value12315',
},
    {
    'id': 17527490706973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Ronald Harris',
    'address': '9021 Roberts Burg\nSamanthaville, CA 29027',
    'text': 'Nature year him generation event time well. Agency bar wear name sport. Learn away door budget trade attorney little. Exactly decade get feel.',
    'email': 'david70@example.com',
    'phone_number': '001-512-988-2213x048',
    'json': {
    'name': 'Justin Sawyer',
    'address': '82226 Mills Avenue\nSharpshire, OH 39181',
},
    'key28324': 'value15618',
},
    {
    'id': 17527490706983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Dana Morgan',
    'address': '86145 Garcia Junction\nNew Joseph, OK 37135',
    'text': 'Forward question buy newspaper during send because. Foreign fight voice miss money eight. Necessary however success.\nVery field foot old lawyer service. Each dog life. Consumer point play together.',
    'email': 'samanthanoble@example.com',
    'phone_number': '(652)463-7622x63761',
    'json': {
    'name': 'Gavin Evans',
    'address': '99317 Macdonald Way\nAnnabury, AS 36525',
},
    'key76484': 'value25393',
    'key50156': 'value29023',
    'key77913': 'value36973',
},
    {
    'id': 17527490706995,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Mark Myers',
    'address': '2381 Osborne Turnpike\nJohnsonmouth, AK 74823',
    'text': 'Person room help beautiful thought event amount. Court listen often any job white. Research car green foreign old commercial.\nBehavior enough visit dinner black involve. State fire night.',
    'email': 'jbrown@example.org',
    'phone_number': '001-839-690-3362',
    'json': {
    'name': 'Taylor Moore',
    'address': '6222 Michael Villages Apt. 377\nHigginsborough, VI 81214',
},
    'key91020': 'value25687',
    'key21146': 'value13769',
    'key60479': 'value69848',
    'key41428': 'value65214',
    'key39808': 'value73599',
    'key93566': 'value13238',
    'key75324': 'value86188',
    'key9330': 'value79436',
},
    {
    'id': 17527490707006,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Mitchell Thomas DVM',
    'address': '38055 Makayla Crest Apt. 732\nAllisonview, NJ 99220',
    'text': 'Eat relate community movement. Age let official research upon same herself.',
    'email': 'mbarker@example.net',
    'phone_number': '408.719.5422x3946',
    'json': {
    'name': 'Maria Petersen',
    'address': '1682 Smith Burgs\nLake Mariaview, VT 09030',
},
    'key60778': 'value76608',
    'key42460': 'value46137',
    'key76857': 'value88659',
    'key8401': 'value182',
    'key27750': 'value35780',
    'key5933': 'value28370',
    'key67774': 'value39551',
    'key26001': 'value37980',
    'key50974': 'value78793',
},
    {
    'id': 17527490707017,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Sherri Carr',
    'address': '81734 Rebecca Keys\nJameston, ND 89839',
    'text': 'Experience shake sign bring candidate. Maybe according politics hit voice. Data along country.',
    'email': 'qjensen@example.org',
    'phone_number': '565.982.7072',
    'json': {
    'name': 'Jill Mcintyre',
    'address': '52196 Edwin Junctions\nSouth Taylorhaven, SD 02966',
},
    'key26525': 'value41854',
    'key75565': 'value60289',
    'key31980': 'value93497',
    'key50697': 'value80705',
    'key48488': 'value17488',
    'key44490': 'value98989',
    'key79501': 'value97397',
    'key47823': 'value66541',
},
    {
    'id': 17527490707028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Brian Hayes',
    'address': '1413 Theresa Viaduct Suite 417\nMirandamouth, NE 10224',
    'text': 'Real theory western bill your like. Anything travel behind fear local lead movement. Piece contain despite usually ground art very.',
    'email': 'douglasbenitez@example.com',
    'phone_number': '(583)509-4049x9739',
    'json': {
    'name': 'Ashley Anderson',
    'address': '6411 Donaldson Keys\nWest Jenniferborough, NJ 31472',
},
    'key68360': 'value47694',
    'key11305': 'value73369',
},
    {
    'id': 17527490707040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Tammy Collins',
    'address': '05072 Vargas Path\nCooperton, MS 15769',
    'text': 'Factor front account turn own. Wait forward choose official. Race few force.',
    'email': 'christian65@example.net',
    'phone_number': '001-882-877-2417x25292',
    'json': {
    'name': 'Jordan Short',
    'address': '30003 Stone Knoll\nNancytown, IN 98830',
},
    'key36967': 'value98863',
    'key43779': 'value7299',
    'key51015': 'value73698',
    'key10155': 'value80345',
    'key3369': 'value72775',
    'key21735': 'value1250',
},
    {
    'id': 17527490707051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Monica Walker',
    'address': '552 Barbara Throughway Apt. 002\nEast Andre, KS 95600',
    'text': 'Myself include operation minute. Voice series machine enjoy. Season fact government.\nBusiness yeah floor show clearly firm. Strong father during live fund look. Alone glass let writer he.',
    'email': 'phillipseric@example.net',
    'phone_number': '938.799.7734x419',
    'json': {
    'name': 'Jonathan Lee',
    'address': '417 Turner Club\nNew Alisonchester, NC 66546',
},
    'key62089': 'value72992',
    'key68832': 'value32304',
    'key18715': 'value49447',
    'key27218': 'value25418',
    'key95595': 'value53747',
    'key63882': 'value77118',
    'key61369': 'value26303',
},
    {
    'id': 17527490707062,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Caitlin Farmer',
    'address': '6616 Jessica Hill Apt. 021\nWest Veronica, DE 01993',
    'text': 'Spend live until theory perhaps address how. Drop game truth budget under idea.\nExpert different between soldier. Its daughter wear music drop. Pass leave career difficult.',
    'email': 'david03@example.org',
    'phone_number': '001-251-531-2326x8054',
    'json': {
    'name': 'Tony Chapman',
    'address': '1153 Suarez Crescent\nLongville, NY 11976',
},
    'key67340': 'value3715',
    'key68914': 'value27235',
},
    {
    'id': 17527490707073,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Janet Cook',
    'address': '43171 Buckley Union\nNew Grant, NH 18897',
    'text': 'Specific wrong stock design decision. Democrat learn dark group front. Establish member thing.',
    'email': 'joseph88@example.net',
    'phone_number': '001-909-916-9644x86684',
    'json': {
    'name': 'Angela Hood',
    'address': '70551 Rivera Points Apt. 007\nLake Angela, WA 22648',
},
    'key80412': 'value81196',
    'key13191': 'value26770',
    'key64392': 'value87983',
    'key67453': 'value63340',
    'key32373': 'value2913',
    'key20997': 'value60091',
    'key69813': 'value40028',
    'key13074': 'value86453',
    'key46606': 'value2946',
    'key11770': 'value84202',
},
    {
    'id': 17527490707084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Ashley Robinson',
    'address': 'USNS Gaines\nFPO AE 48776',
    'text': 'Bank prepare wait arm town risk relate. Raise coach concern man.\nBorn crime total. Light investment again bank star challenge there. Team protect cost popular maybe possible dog smile.',
    'email': 'glamb@example.com',
    'phone_number': '+1-759-491-9395x698',
    'json': {
    'name': 'Kimberly Miller',
    'address': '04141 Hartman Mill Suite 339\nWest Justin, GA 16857',
},
    'key62577': 'value27483',
    'key99012': 'value30946',
    'key29231': 'value15781',
    'key27556': 'value38624',
    'key97645': 'value35146',
    'key90653': 'value74289',
    'key43748': 'value71515',
    'key85148': 'value25430',
    'key48389': 'value86195',
    'key71363': 'value52563',
},
    {
    'id': 17527490707095,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Audrey Peck',
    'address': '1842 Young Mall\nPort Jeffreyview, CO 88507',
    'text': 'Eight play to new friend scientist think. Score form head think. Approach floor indeed line any.\nWife also only wrong. Employee different visit. Letter actually black.',
    'email': 'juliepalmer@example.net',
    'phone_number': '520-347-9343x4544',
    'json': {
    'name': 'Joshua Randall Jr.',
    'address': '572 Sylvia Passage\nPort Richard, SC 67057',
},
    'key53672': 'value88097',
},
    {
    'id': 17527490707106,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Derrick Williams',
    'address': '406 Nash Forest Apt. 601\nWest Susanmouth, NE 48273',
    'text': 'Voice appear full another money firm. Open assume south matter.\nLanguage clear radio allow glass maintain nation.',
    'email': 'thomasscott@example.com',
    'phone_number': '(921)503-6067',
    'json': {
    'name': 'Erika Odom',
    'address': '28277 Simmons Mills Suite 962\nJillianport, UT 89850',
},
    'key47622': 'value45811',
    'key55832': 'value45067',
    'key67071': 'value33368',
    'key30808': 'value68038',
    'key55459': 'value45377',
    'key63180': 'value57226',
    'key38650': 'value12153',
},
    {
    'id': 17527490707118,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Amanda Suarez',
    'address': '93564 Alexander Stream Suite 576\nPhillipsfort, DC 00765',
    'text': 'Religious when husband garden. Figure treat direction else rule. Result news a gas ball require within.\nGirl project series writer. Likely space see trade.',
    'email': 'mary67@example.net',
    'phone_number': '(340)930-4905',
    'json': {
    'name': 'Isabella Harper',
    'address': 'PSC 2999, Box 8731\nAPO AA 89782',
},
    'key36346': 'value65975',
    'key12170': 'value15733',
    'key64563': 'value93102',
    'key38469': 'value66542',
    'key86013': 'value55937',
    'key8744': 'value41303',
    'key39243': 'value81755',
    'key39114': 'value50557',
    'key68239': 'value37607',
    'key59334': 'value42241',
},
    {
    'id': 17527490707127,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Keith Brown',
    'address': '32049 Derek Roads Apt. 614\nNew Ericton, VA 48815',
    'text': 'Contain what opportunity. Reality create year.\nCertainly north movie computer begin. Movement task pay such.',
    'email': 'rodriguezvirginia@example.org',
    'phone_number': '629-755-6442x694',
    'json': {
    'name': 'Andrew Greer',
    'address': '72996 Mark Cliffs Apt. 327\nPaulmouth, MP 41897',
},
    'key53465': 'value51398',
    'key83295': 'value51653',
    'key34445': 'value84100',
    'key46593': 'value79573',
    'key68745': 'value23360',
    'key73675': 'value66930',
    'key24543': 'value32489',
},
    {
    'id': 17527490707138,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Brittney Gonzalez',
    'address': '1329 Katherine Row\nArnoldburgh, GA 93143',
    'text': 'Yet new audience usually interview. Detail child thing strategy policy partner fact. New surface relationship trial education pressure.',
    'email': 'opeterson@example.net',
    'phone_number': '444.550.7209x031',
    'json': {
    'name': 'Blake Cameron',
    'address': '1411 Wright Keys Apt. 423\nLake Brittney, CA 44618',
},
    'key79107': 'value35268',
    'key70925': 'value83693',
    'key55192': 'value94547',
    'key46224': 'value36697',
    'key28319': 'value15315',
    'key56527': 'value82155',
    'key87300': 'value99012',
    'key25027': 'value70579',
    'key25999': 'value4461',
    'key37278': 'value28386',
},
    {
    'id': 17527490707149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Tonya Jenkins',
    'address': '2439 Cole Island\nJosephmouth, CA 47482',
    'text': 'Purpose radio if a every several may candidate. Security young nor talk song time western. Represent agent statement.\nElection while scientist easy. Agent response writer close cultural.',
    'email': 'youngpamela@example.com',
    'phone_number': '001-299-687-4224x1929',
    'json': {
    'name': 'Blake Hale',
    'address': '2171 Evan Cliff\nLake Adrienneberg, MT 69582',
},
    'key54620': 'value16014',
    'key67792': 'value67539',
    'key99112': 'value37458',
    'key71204': 'value46381',
    'key13396': 'value70461',
    'key72618': 'value71273',
    'key53669': 'value28639',
    'key40503': 'value32282',
    'key55713': 'value38151',
},
    {
    'id': 17527490707160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Cassandra Palmer',
    'address': 'PSC 7559, Box 1749\nAPO AE 37236',
    'text': 'Between meet half imagine return. Politics middle society necessary. Return national trip person key.',
    'email': 'dana55@example.org',
    'phone_number': '(867)822-7569x26996',
    'json': {
    'name': 'Theodore Hamilton',
    'address': '1649 Mitchell Cliff\nLake John, CT 92485',
},
    'key31482': 'value88057',
    'key68081': 'value82446',
    'key8733': 'value70567',
    'key55702': 'value79136',
    'key59003': 'value2885',
    'key2404': 'value22421',
    'key296': 'value6462',
    'key24927': 'value2073',
    'key91234': 'value84389',
},
    {
    'id': 17527490707169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Olivia Campbell',
    'address': '9228 Jerry Fields\nWest Tammyburgh, LA 38423',
    'text': 'Of enter picture. Whole think ten case space blue wear. Claim buy Mrs can offer spring.\nImpact everyone good lead visit employee. Pretty power friend paper worry deal management.',
    'email': 'jgutierrez@example.com',
    'phone_number': '(269)244-7662',
    'json': {
    'name': 'John Cantrell',
    'address': '69804 Mackenzie Summit\nWest Mary, GU 37153',
},
    'key49353': 'value44997',
    'key7660': 'value1141',
    'key24834': 'value46567',
    'key59255': 'value3676',
    'key91191': 'value16228',
    'key18042': 'value58278',
    'key81267': 'value30543',
    'key18569': 'value34595',
},
    {
    'id': 17527490707179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Ronald Kim',
    'address': '25774 Kevin Mountain Suite 890\nJaredtown, NC 85660',
    'text': 'Pm exist high explain strong democratic population. Southern apply despite democratic radio ready plan. Matter and those enough usually.',
    'email': 'poneill@example.net',
    'phone_number': '774.482.3362',
    'json': {
    'name': 'Roberta Smith',
    'address': '47700 Colleen Shore\nNew Brianberg, OH 53107',
},
    'key64344': 'value5241',
    'key56005': 'value50233',
    'key21509': 'value1312',
    'key15226': 'value76238',
    'key31452': 'value50869',
    'key86144': 'value21132',
    'key38701': 'value45815',
},
    {
    'id': 17527490707190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Alexis Daniels',
    'address': 'PSC 5503, Box 4780\nAPO AE 63804',
    'text': 'Dream citizen say. Owner resource education fish imagine yeah that see. Might field total.\nLet money child quality walk beyond. Certainly ready truth easy book east.',
    'email': 'sanderskenneth@example.com',
    'phone_number': '+1-620-458-4872x236',
    'json': {
    'name': 'Beth Robertson',
    'address': 'Unit 4102 Box 8891\nDPO AE 81349',
},
    'key15973': 'value58674',
},
    {
    'id': 17527490707197,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Andrea Collins',
    'address': '24081 Fowler Mission\nSouth Nathaniel, FL 75803',
    'text': 'Industry picture today form wrong leave watch those. Wonder current not most site. Major goal thing everything design avoid husband.',
    'email': 'erika98@example.net',
    'phone_number': '667-490-6852',
    'json': {
    'name': 'Mary Johns',
    'address': '987 Ryan Avenue Suite 006\nNew Cynthiahaven, AL 69024',
},
    'key69469': 'value88479',
    'key8268': 'value39306',
    'key84466': 'value79226',
    'key36549': 'value73002',
    'key74002': 'value45857',
    'key84310': 'value97547',
    'key14014': 'value60971',
    'key78894': 'value21640',
    'key82783': 'value2045',
    'key70399': 'value84949',
},
    {
    'id': 17527490707208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Michael Knight',
    'address': '089 Miller Ranch Suite 228\nNorth Walter, AZ 72316',
    'text': 'Get bar hot affect window machine ten. Run reason part against race.',
    'email': 'tina52@example.org',
    'phone_number': '8434513828',
    'json': {
    'name': 'Olivia Lee',
    'address': '67188 Darrell Locks\nMichaelberg, IN 53089',
},
    'key89179': 'value50924',
    'key11625': 'value16453',
},
    {
    'id': 17527490707219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Daniel Fischer',
    'address': '9479 Michelle Motorway\nJesusburgh, VA 04521',
    'text': 'Level give each than. Example new moment this walk. Seat local audience easy good. Attack fall light measure fear morning.\nBorn remain adult hundred become cover. Continue tend religious.',
    'email': 'joneslindsey@example.net',
    'phone_number': '(665)657-5396',
    'json': {
    'name': 'Jennifer Hendricks',
    'address': '60564 Anne Crossing\nWest Theresachester, WI 92359',
},
    'key66852': 'value57046',
    'key30393': 'value91788',
    'key21354': 'value55027',
    'key61022': 'value71371',
},
    {
    'id': 17527490707230,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Heather Santos',
    'address': '7348 Bryant Glens\nJennystad, NH 35915',
    'text': 'Policy defense deal different mind key. Street theory best whose edge property.\nFar score security young two. Performance direction skin street and. Ask can work fill price.',
    'email': 'tsimpson@example.net',
    'phone_number': '+1-215-529-8039x837',
    'json': {
    'name': 'Brian Adams',
    'address': '6066 Tanya Vista Apt. 164\nNorth Joelborough, MA 33101',
},
    'key52993': 'value35783',
},
    {
    'id': 17527490707241,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Jennifer Ferrell',
    'address': '06999 Michael Pine Suite 259\nEast Heatherberg, HI 31936',
    'text': 'Management whole spring goal. His president article amount little suggest share western.',
    'email': 'david02@example.org',
    'phone_number': '645-584-2622x5492',
    'json': {
    'name': 'Michelle Clayton',
    'address': '4542 Bill Bridge Apt. 019\nNorth Devin, NM 01911',
},
    'key86545': 'value96982',
},
    {
    'id': 17527490707251,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Brian Lynn Jr.',
    'address': '11215 Megan Spur Suite 300\nEast Davidview, OH 91756',
    'text': 'Summer skin give their. Write alone full trial help.\nCentral song market glass reflect.',
    'email': 'davismarvin@example.net',
    'phone_number': '001-793-516-9869x510',
    'json': {
    'name': 'Adam Miller',
    'address': '9674 Ronald Circles Apt. 807\nBushland, CT 94506',
},
    'key60338': 'value9403',
    'key34004': 'value21826',
    'key75312': 'value6383',
    'key83522': 'value39633',
    'key108': 'value15256',
},
    {
    'id': 17527490707262,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Mary Long',
    'address': '388 Eric Grove Suite 258\nNorth Katiechester, DC 57352',
    'text': 'Recognize of side.',
    'email': 'denise59@example.org',
    'phone_number': '001-667-673-1268',
    'json': {
    'name': 'Jessica Padilla',
    'address': '8382 Brent Lights\nWest Danielside, OK 47534',
},
    'key49390': 'value79175',
    'key32383': 'value49275',
    'key85033': 'value56049',
    'key36722': 'value35178',
},
    {
    'id': 17527490707272,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Tiffany Carlson',
    'address': '38098 Sheila Plains\nWest Geraldfort, MP 65579',
    'text': 'Fish fund glass within.\nFact trip establish account live special. Arm go Mrs home decision with break. Soldier particularly have build.\nBlack religious face garden. Eat front Congress ahead west.',
    'email': 'xgarza@example.org',
    'phone_number': '+1-435-753-2892',
    'json': {
    'name': 'Brittany Austin',
    'address': '313 Lisa Dale\nNorth Heatherfurt, AR 54896',
},
    'key92253': 'value79567',
    'key30833': 'value93160',
    'key61151': 'value3419',
    'key75811': 'value16316',
    'key47559': 'value20503',
    'key98102': 'value18971',
    'key3875': 'value54312',
    'key4259': 'value48814',
    'key88628': 'value86448',
},
    {
    'id': 17527490707282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Monica Hall',
    'address': '61075 Richard Track\nLake Joshua, ID 24316',
    'text': 'As store conference performance. Really either expert start information move spend rate. Cold officer statement drug.',
    'email': 'kyle45@example.net',
    'phone_number': '200-261-0721',
    'json': {
    'name': 'James Weiss',
    'address': '62007 Tran Field Apt. 080\nSouth Theresa, PW 67162',
},
    'key98557': 'value60863',
    'key29564': 'value69603',
    'key77901': 'value40240',
    'key83543': 'value65090',
    'key38423': 'value43595',
    'key91867': 'value75529',
},
    {
    'id': 17527490707292,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Pamela Mills',
    'address': 'PSC 1477, Box 1815\nAPO AP 77889',
    'text': 'Where stand quite marriage myself.\nMove right record prepare finish ask tax. Leader return computer suddenly.',
    'email': 'amanda51@example.org',
    'phone_number': '(238)814-8271x133',
    'json': {
    'name': 'Lisa Holder',
    'address': '583 Smith Lodge Apt. 364\nBrianchester, SD 26632',
},
    'key69845': 'value75857',
},
    {
    'id': 17527490707301,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Tony Weber',
    'address': '24454 Ayala Loaf Suite 652\nLarsontown, CT 46357',
    'text': 'North director quickly wish race home social.\nOption team kid on available recent law. Particularly how hour write shoulder feel.',
    'email': 'katie87@example.net',
    'phone_number': '498-906-2477x174',
    'json': {
    'name': 'Gregory Fleming',
    'address': '160 Desiree Hills\nNew Mary, MO 46977',
},
    'key12506': 'value37122',
    'key61496': 'value46679',
    'key6573': 'value35311',
    'key30733': 'value4996',
    'key35738': 'value56444',
    'key12531': 'value13077',
    'key52790': 'value4519',
    'key57481': 'value12315',
},
    {
    'id': 17527490707311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Angela Moore',
    'address': '6585 Kayla Manor\nPattersontown, OK 81561',
    'text': 'Deal church style one. Wish woman end painting world especially example certainly. Fly I account whether full decade.',
    'email': 'hernandezdavid@example.net',
    'phone_number': '(553)537-7843x636',
    'json': {
    'name': 'Jason Cummings',
    'address': '065 Bailey Lakes\nJonesbury, CA 84711',
},
    'key19708': 'value47940',
},
    {
    'id': 17527490707323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jason Patel',
    'address': '91694 Marcus Falls\nTimothyport, AS 72617',
    'text': 'Morning stop never focus reduce. Reach customer church executive gun low west her. Property everything community for quite our reveal.',
    'email': 'rogersimmons@example.org',
    'phone_number': '(966)465-5924x822',
    'json': {
    'name': 'Lori Brown',
    'address': '03602 Victor Parkway Apt. 575\nNorth Jorgefurt, UT 33305',
},
    'key62816': 'value89504',
    'key72510': 'value80304',
    'key93603': 'value19910',
    'key54833': 'value79293',
    'key76121': 'value82986',
    'key12309': 'value97586',
    'key88269': 'value36967',
},
    {
    'id': 17527490707334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Joseph Johnson',
    'address': '415 Silva Harbor Apt. 981\nEast Jamesport, VI 78813',
    'text': 'But push speak. Parent imagine build point. Down staff operation way environment doctor.\nAlthough expert own list. Against prepare matter red long door. Let claim though.',
    'email': 'aaron66@example.org',
    'phone_number': '878-805-2822x4191',
    'json': {
    'name': 'Brian Williams',
    'address': '06003 Donald Curve\nBraunstad, PA 94259',
},
    'key10713': 'value2097',
    'key62843': 'value22097',
    'key53003': 'value12050',
    'key69751': 'value61547',
    'key85023': 'value85750',
    'key1000': 'value39676',
    'key49672': 'value7025',
    'key84778': 'value42704',
    'key51923': 'value71879',
},
    {
    'id': 17527490707345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Mr. Gerald Lewis',
    'address': '5629 Antonio Walks Apt. 125\nHoldenville, FL 14447',
    'text': 'Your employee prepare. Six central another place item. Information cut although.\nMeasure past firm society or be by religious. Store leg behavior heart.',
    'email': 'charlesmcmillan@example.net',
    'phone_number': '348.406.5868x9963',
    'json': {
    'name': 'Julie Gonzalez',
    'address': '89167 Vickie Lane\nLake Peter, VA 91205',
},
    'key88924': 'value75896',
    'key142': 'value49115',
},
    {
    'id': 17527490707357,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Gary Harrison',
    'address': 'PSC 6207, Box 3003\nAPO AA 30232',
    'text': 'Size theory hand teach. Message analysis factor way stay rule home computer.\nAppear style direction. Concern sit sign college scientist.',
    'email': 'brandon99@example.com',
    'phone_number': '(582)718-2122',
    'json': {
    'name': 'Shelly Carney',
    'address': '53413 Rangel Parks\nPort Michelle, MO 52348',
},
    'key82245': 'value8862',
    'key48574': 'value15539',
    'key1388': 'value69351',
    'key69372': 'value59977',
    'key33973': 'value78254',
    'key93404': 'value68444',
    'key39553': 'value77536',
    'key20155': 'value62384',
    'key46556': 'value41812',
    'key38840': 'value30622',
},
    {
    'id': 17527490707366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Brent Smith',
    'address': '959 Campbell Square\nNew Shirley, MT 07913',
    'text': 'Care teacher education never remain. Choice until style stand those response partner.\nHot window herself thank blue huge clear. Her once professional.',
    'email': 'justinmiller@example.net',
    'phone_number': '9494096689',
    'json': {
    'name': 'Mary Sanchez',
    'address': '974 Whitney Crossing Apt. 471\nNew Kaitlin, ID 27548',
},
    'key68035': 'value33133',
    'key66397': 'value69923',
    'key42555': 'value20782',
    'key60355': 'value36084',
    'key31417': 'value98299',
    'key30162': 'value81164',
    'key6617': 'value83960',
    'key2503': 'value43066',
},
    {
    'id': 17527490707377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Lisa Strickland',
    'address': '75531 Ian Turnpike Apt. 001\nNorth Robert, OK 24691',
    'text': 'Doctor five range entire world first. Happen home generation people remember hard success show. Fish generation leave man kind.\nElection section discover free price fill.',
    'email': 'andrewsamanda@example.org',
    'phone_number': '719-632-6835x2536',
    'json': {
    'name': 'Amanda Woods',
    'address': '2032 Monroe Forge Apt. 714\nEdwardsville, KY 54685',
},
    'key81413': 'value92438',
    'key16898': 'value84837',
    'key98467': 'value68352',
    'key71871': 'value9503',
    'key33140': 'value64008',
    'key81246': 'value1382',
    'key12925': 'value10007',
    'key89658': 'value78305',
    'key36123': 'value98402',
},
    {
    'id': 17527490707389,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Ashley Sloan',
    'address': '660 Lane Point\nRamosfort, OR 03604',
    'text': 'Whose who my career before account only. Him grow live. Without question response edge throw foreign western present.',
    'email': 'lori82@example.net',
    'phone_number': '+1-300-538-1733',
    'json': {
    'name': 'Billy Gallagher',
    'address': '964 Johnson Mountains\nLake Leroybury, MS 78019',
},
    'key75835': 'value11904',
    'key45397': 'value41184',
    'key62985': 'value76073',
    'key33105': 'value5074',
    'key20598': 'value89338',
    'key1512': 'value42265',
    'key44002': 'value60898',
},
    {
    'id': 17527490707400,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Paul Davis',
    'address': '95451 Linda Brooks\nBrockview, GA 51546',
    'text': 'Him treatment site piece writer.\nChange word finally letter table. Hospital national describe blue possible. Plan purpose even fund. Radio thus speak education explain.',
    'email': 'hpearson@example.org',
    'phone_number': '(299)680-4541x54314',
    'json': {
    'name': 'Cheryl Curtis',
    'address': '71746 Nelson Points Suite 909\nNorth Laurenhaven, CT 22696',
},
    'key25858': 'value5809',
},
    {
    'id': 17527490707411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kathleen Lopez',
    'address': '9549 Wallace Station\nJonesside, MT 56645',
    'text': 'Language daughter live executive executive western. Yourself region able wish. Dog produce environmental sometimes clear view here. Job painting choose law.',
    'email': 'james91@example.net',
    'phone_number': '560-565-0773x35766',
    'json': {
    'name': 'Kimberly Figueroa',
    'address': '2406 Pamela Garden\nPort Markville, NM 07006',
},
    'key2001': 'value19389',
    'key23398': 'value16133',
    'key95490': 'value81636',
},
    {
    'id': 17527490707421,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'David Ford',
    'address': '3260 Joshua Stravenue\nDanielborough, NH 50193',
    'text': 'Left purpose stand talk. Structure they left.\nPrevent let order indeed whom.\nSection bank true hope charge into energy. Live present risk she pull during protect few.',
    'email': 'harrisadam@example.net',
    'phone_number': '750-620-4395',
    'json': {
    'name': 'Christopher Campbell',
    'address': 'USNS Griffith\nFPO AA 29664',
},
    'key66402': 'value47780',
    'key46214': 'value78925',
    'key52872': 'value71277',
    'key88124': 'value25492',
},
    {
    'id': 17527490707432,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Victoria Powell',
    'address': '543 Sheila Neck Suite 774\nLake Billy, WV 47997',
    'text': 'Read research design type its its she. Huge walk design thing rather lay. Might machine anyone.\nAround agreement clear find. Guy lose establish knowledge structure. Air manage summer most so.',
    'email': 'cdiaz@example.net',
    'phone_number': '441-276-2182x0694',
    'json': {
    'name': 'Linda Rangel',
    'address': '915 Dunn Course\nFishermouth, KS 20556',
},
    'key99721': 'value70999',
    'key6558': 'value76916',
    'key80116': 'value46341',
    'key2906': 'value97059',
    'key97499': 'value59143',
    'key93059': 'value91403',
    'key35572': 'value11925',
},
    {
    'id': 17527490707442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Benjamin Deleon',
    'address': '9566 Joshua Stravenue\nNew Kenneth, MA 27447',
    'text': 'Buy design stop break present. Little laugh light miss.\nOff hard drive majority trip share. Candidate day structure affect painting.',
    'email': 'omejia@example.com',
    'phone_number': '257-620-6559',
    'json': {
    'name': 'Michelle Johnson',
    'address': '80664 Leon Views\nWest Micheal, DE 31623',
},
    'key52256': 'value51971',
    'key82564': 'value92120',
    'key60211': 'value32394',
    'key79352': 'value67015',
    'key19614': 'value78599',
    'key64555': 'value86003',
},
    {
    'id': 17527490707453,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Karen Mills',
    'address': '064 Weaver Causeway Suite 214\nNew Heidi, WV 74464',
    'text': 'Different player recognize live. Occur move recognize send defense right. Particular factor admit structure teach white public science.',
    'email': 'ykelly@example.org',
    'phone_number': '+1-815-462-3449',
    'json': {
    'name': 'Alicia Howe',
    'address': '80104 Luis Harbor\nWest Christina, KS 02279',
},
    'key45151': 'value57611',
    'key34368': 'value88527',
},
    {
    'id': 17527490707464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Scott Gonzales',
    'address': '4909 Henry Mountains\nGordontown, MH 09720',
    'text': 'Someone second company nor couple all suffer. Number certainly modern always measure power with.\nLay example see fish boy assume draw. Green maybe nothing wrong whole. Again kind night stage.',
    'email': 'estradacorey@example.org',
    'phone_number': '(697)553-4823x6443',
    'json': {
    'name': 'Travis Castro',
    'address': '8848 Mason Roads\nPort Timothy, OH 61251',
},
    'key86026': 'value40809',
    'key8836': 'value17626',
    'key98620': 'value96776',
    'key39': 'value62564',
    'key93231': 'value31684',
    'key47996': 'value94958',
    'key8871': 'value5735',
    'key53510': 'value62127',
},
    {
    'id': 17527490707475,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Stephen Barry',
    'address': '252 Bernard Port Apt. 460\nStewartland, DC 99100',
    'text': 'Statement catch discover section. Road could owner stuff but.\nSeek lead growth section religious my.',
    'email': 'garciatony@example.com',
    'phone_number': '+1-566-775-9208x3321',
    'json': {
    'name': 'Michael Davis',
    'address': '9774 Michael Ports\nCarrilloland, WV 42296',
},
    'key51050': 'value62838',
    'key88493': 'value98659',
    'key1897': 'value24210',
    'key84653': 'value30775',
    'key62352': 'value64507',
    'key12004': 'value82683',
    'key12724': 'value33583',
    'key36592': 'value85328',
    'key80629': 'value33071',
    'key45817': 'value18523',
},
    {
    'id': 17527490707487,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Adam White',
    'address': '558 Schneider Extensions\nEast Carriefort, IA 65537',
    'text': 'Money long interest professor development. Rise idea five book water wonder so. Policy leg right field child game.',
    'email': 'mbrown@example.org',
    'phone_number': '958.870.6479',
    'json': {
    'name': 'Tyler Hill',
    'address': '670 Davis Stravenue\nSouth Stephanieborough, MA 26264',
},
    'key62765': 'value81198',
    'key56224': 'value22893',
    'key40867': 'value30314',
    'key22230': 'value24600',
    'key72040': 'value22422',
    'key76495': 'value12529',
    'key70281': 'value6666',
    'key67805': 'value87454',
    'key77476': 'value30815',
},
    {
    'id': 17527490707498,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Tracey Parsons',
    'address': 'Unit 8104 Box 1130\nDPO AP 73866',
    'text': 'Military discover later require that. Table after way whether weight build fire wait. Pick stay organization.\nGroup training between animal media whom water. Know charge month.',
    'email': 'kathleen14@example.com',
    'phone_number': '868-661-3842x0414',
    'json': {
    'name': 'Jesse Glover',
    'address': '92462 Jacqueline Spur\nEast Amberberg, MT 49013',
},
    'key92528': 'value96427',
    'key3575': 'value85547',
    'key52651': 'value74464',
    'key29933': 'value90367',
},
    {
    'id': 17527490707507,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Lauren Ward',
    'address': '9276 Mark Points\nWebsterbury, NE 51755',
    'text': 'Region operation stand she imagine wind. Eat art fast dark could.\nResource others account treat which give interest. Officer improve step room middle pressure you. Quite help within hospital.',
    'email': 'award@example.net',
    'phone_number': '260.680.4642x910',
    'json': {
    'name': 'Mrs. Rebecca Duran',
    'address': '128 Nelson Branch\nWendyhaven, TX 08751',
},
    'key42115': 'value28853',
    'key4460': 'value65911',
    'key58995': 'value72536',
},
    {
    'id': 17527490707517,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Gavin Fernandez',
    'address': '943 Thompson Court Apt. 029\nWest Roberttown, MS 20729',
    'text': 'Book this gun us want support. Condition rock themselves knowledge during nor.\nReport simple blue model partner weight personal. Series house add artist market wind. Office through leg create page.',
    'email': 'ronald94@example.org',
    'phone_number': '308.703.0413x69736',
    'json': {
    'name': 'Michael Wilson',
    'address': '03859 Karen Trace Suite 097\nBrownfurt, ME 34258',
},
    'key52073': 'value84632',
    'key3617': 'value45092',
    'key40519': 'value78814',
},
    {
    'id': 17527490707528,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Colleen Harris',
    'address': '641 Abigail Station\nNorth Robertside, WY 72428',
    'text': 'Senior goal piece upon year say option Congress. Alone likely surface none country lay.\nTwo per clear amount next operation. Home natural health. Recent well describe at science positive.',
    'email': 'michaelbailey@example.com',
    'phone_number': '+1-236-320-7701x8426',
    'json': {
    'name': 'Haley Hamilton',
    'address': '68649 Valerie Square Apt. 829\nMillerfort, WA 64698',
},
    'key93795': 'value80532',
    'key33314': 'value83198',
    'key36436': 'value3344',
    'key58241': 'value80911',
},
    {
    'id': 17527490707540,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Rebekah Perry',
    'address': '2901 Jason Fords Apt. 848\nSarahstad, WI 85185',
    'text': 'Daughter street believe plan upon side simple. Other catch edge must assume. Art support chance eye add trip. American wonder spend everything travel.',
    'email': 'chris40@example.com',
    'phone_number': '238.427.5870',
    'json': {
    'name': 'Amy Ortiz',
    'address': '475 Emily Light\nEast Marybury, KS 71872',
},
    'key74507': 'value92265',
    'key45912': 'value49812',
    'key74295': 'value96112',
    'key7584': 'value43351',
    'key63070': 'value66772',
    'key68995': 'value46374',
    'key27486': 'value20247',
    'key92821': 'value62352',
    'key92734': 'value2643',
},
    {
    'id': 17527490707550,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Shawna Morgan',
    'address': '4831 Hernandez Oval\nEast Coltonview, OH 40454',
    'text': 'Could party deal. Blood impact easy yes behavior fund turn. Movement owner kitchen center few. Data physical toward sometimes whole modern.',
    'email': 'brian30@example.com',
    'phone_number': '4377800539',
    'json': {
    'name': 'Victor Bradford',
    'address': '559 Bauer Radial\nWest Josestad, DC 83087',
},
    'key17821': 'value5723',
    'key20815': 'value16579',
},
    {
    'id': 17527490707560,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Joseph Harmon',
    'address': '7513 John Branch\nKimberlyport, VI 72716',
    'text': 'Seat case idea role.\nMillion miss deep early seek people. Peace better test both. Explain cost story particularly nation lay.',
    'email': 'drogers@example.net',
    'phone_number': '3925441809',
    'json': {
    'name': 'Joseph Logan',
    'address': '7240 Christopher Course Suite 521\nNorth Jennifer, UT 46372',
},
    'key35376': 'value34905',
    'key31524': 'value66887',
},
    {
    'id': 17527490707570,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Amber Brown',
    'address': '718 Melody Circles\nAndrewfurt, ID 06746',
    'text': 'Drug office population present strong have behind. They share play across agreement character believe service. Never small represent officer similar whom us.',
    'email': 'nramirez@example.net',
    'phone_number': '(432)949-9251x495',
    'json': {
    'name': 'Elizabeth Graham',
    'address': '4619 Levy Crossing\nMcculloughfort, WI 72664',
},
    'key27462': 'value91341',
    'key56033': 'value69166',
    'key79364': 'value40544',
},
    {
    'id': 17527490707580,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Jodi Sheppard',
    'address': '92901 Shannon Squares\nNew Joseph, WA 45098',
    'text': 'Relate activity same maintain else teach work born. Protect company away.\nWind and instead list power. Could shake result page. Without all training region certainly believe pretty.',
    'email': 'audreyharper@example.org',
    'phone_number': '291-958-8908x328',
    'json': {
    'name': 'Robert Smith',
    'address': '4615 Erin Terrace\nEast Scott, TN 88104',
},
    'key62194': 'value92053',
    'key56423': 'value68832',
    'key96129': 'value51948',
    'key30771': 'value9534',
    'key9819': 'value34838',
    'key19615': 'value11415',
},
    {
    'id': 17527490707591,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Paul Burgess',
    'address': 'USNV Krause\nFPO AP 78405',
    'text': 'Join provide view hit find fish. There wish thing community summer garden.',
    'email': 'silvaeric@example.net',
    'phone_number': '368.857.4861x72504',
    'json': {
    'name': 'Heather Davis',
    'address': '2263 Chang Mill\nBondland, GA 45523',
},
    'key68042': 'value62869',
    'key29878': 'value30146',
    'key86878': 'value97612',
},
    {
    'id': 17527490707601,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Lauren Washington',
    'address': '423 Robert Pines Suite 528\nRickyfort, ID 86759',
    'text': 'Open attorney training partner order word onto. Book customer sea industry note.\nEffort peace trip machine single. Practice move they recognize.',
    'email': 'brenda28@example.com',
    'phone_number': '(845)907-8098x67963',
    'json': {
    'name': 'Jennifer Johnson',
    'address': 'PSC 3939, Box 2519\nAPO AA 99592',
},
    'key19724': 'value63518',
    'key56053': 'value14660',
    'key68688': 'value55662',
    'key46334': 'value22389',
    'key98895': 'value37836',
    'key54671': 'value83916',
    'key19352': 'value5112',
    'key85925': 'value43836',
    'key93620': 'value56914',
    'key61234': 'value50124',
},
    {
    'id': 17527490707610,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Christian Glass',
    'address': 'USNV Morgan\nFPO AA 19669',
    'text': 'Expert third until build. Piece forget catch American meeting. Rich send from.\nBecome offer research culture.',
    'email': 'alexandergonzales@example.com',
    'phone_number': '(935)563-6154x34460',
    'json': {
    'name': 'Michael Fisher',
    'address': '264 Courtney Crescent Suite 860\nEast Jon, GA 52822',
},
    'key33292': 'value39384',
    'key36706': 'value63128',
    'key16315': 'value53700',
    'key17548': 'value58478',
    'key37929': 'value34151',
    'key34099': 'value98826',
    'key8674': 'value34560',
    'key53540': 'value89865',
    'key9103': 'value83626',
},
    {
    'id': 17527490707620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Ann Smith',
    'address': '08066 Chavez Mall\nNorth Anthony, GU 66404',
    'text': 'Them reality easy player arrive trial appear. Line five company. Can bed brother range major. Present agency child mean fact.\nBenefit check every better mission. Treat southern edge trip include.',
    'email': 'pittsdiana@example.org',
    'phone_number': '(346)477-3196',
    'json': {
    'name': 'Jessica Leonard',
    'address': '55808 Bryan Flat\nNew Sandra, MD 88356',
},
    'key63159': 'value16227',
    'key78625': 'value73675',
},
    {
    'id': 17527490707632,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Lori Klein',
    'address': 'USNV Weaver\nFPO AE 76130',
    'text': 'South job standard seek five high. Past simple source where station place.\nClear institution discover. Just follow wear up. Painting break similar imagine mother discussion receive.',
    'email': 'smithmark@example.com',
    'phone_number': '587.432.7261',
    'json': {
    'name': 'Melissa Marshall MD',
    'address': '8833 Bradford Club\nNorth Nichole, AR 94578',
},
    'key96544': 'value74256',
    'key70141': 'value11072',
    'key13298': 'value20992',
    'key42438': 'value40734',
    'key56406': 'value57285',
    'key36400': 'value83587',
    'key47390': 'value13389',
    'key73663': 'value95712',
},
    {
    'id': 17527490707643,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Daniel Phelps',
    'address': '6931 Brandon Rapid Apt. 927\nTheresaport, ID 03479',
    'text': 'Word financial high sing. Feeling street evening work audience data again. Skin doctor think character. Simple catch outside management professor prove same.',
    'email': 'samantharivera@example.org',
    'phone_number': '3783175327',
    'json': {
    'name': 'Sheri Pearson',
    'address': '492 Robert Junction\nNorth Kimberly, WY 18128',
},
    'key64448': 'value71581',
    'key18898': 'value14423',
    'key43516': 'value34739',
    'key54110': 'value74395',
    'key12872': 'value47513',
    'key79950': 'value88048',
    'key54731': 'value91515',
    'key93187': 'value25204',
},
    {
    'id': 17527490707654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Kristina Weber',
    'address': '7087 Jessica Isle\nJonesville, PW 86512',
    'text': 'Recognize ago toward meet rather either. Free account idea. Might usually answer two.\nThere low several cold. Admit seek list pretty star happen.',
    'email': 'gknight@example.org',
    'phone_number': '(651)783-1904',
    'json': {
    'name': 'Patrick Mclean',
    'address': '49897 Sarah Skyway\nWhitehaven, CT 13088',
},
    'key73455': 'value57056',
    'key48226': 'value20305',
},
    {
    'id': 17527490707665,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'William Price',
    'address': '00707 Wilson Forest Apt. 636\nNicoletown, RI 30280',
    'text': 'Fish religious report around again might respond method. Ahead anything out far food.\nRecent specific sign say front.',
    'email': 'esaunders@example.net',
    'phone_number': '001-539-266-9522x72372',
    'json': {
    'name': 'Evan Rodriguez',
    'address': 'USNV Rodriguez\nFPO AA 05218',
},
    'key2881': 'value5190',
    'key30461': 'value14677',
    'key18235': 'value60892',
    'key55958': 'value67333',
    'key33604': 'value55734',
},
    {
    'id': 17527490707675,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Timothy Thompson',
    'address': '3386 Huerta Mountains\nJohnland, AZ 31429',
    'text': 'Girl chair able effort develop per cold. Budget side star live process.\nDecide white large would policy. Foot dog voice network.',
    'email': 'isaac94@example.com',
    'phone_number': '(851)535-9910x24303',
    'json': {
    'name': 'Luke Day',
    'address': 'PSC 0944, Box 6549\nAPO AA 87750',
},
    'key23854': 'value41059',
    'key96262': 'value10824',
    'key26223': 'value67336',
    'key78976': 'value95720',
    'key62932': 'value5459',
    'key78255': 'value88708',
    'key42793': 'value63140',
    'key53650': 'value97201',
},
    {
    'id': 17527490707684,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Lisa Kirk',
    'address': '0953 Patrick Junctions Suite 483\nWest Nicoleview, IL 11615',
    'text': 'Together town dog market.\nReligious walk perform today nor eat base add. Away represent hair significant.',
    'email': 'mayermichael@example.org',
    'phone_number': '(665)281-0354',
    'json': {
    'name': 'Sharon Miller',
    'address': 'USCGC Baker\nFPO AE 01358',
},
    'key3879': 'value22420',
    'key40249': 'value63518',
    'key83669': 'value31987',
    'key15044': 'value65226',
    'key73816': 'value64565',
    'key11993': 'value52435',
    'key17002': 'value22510',
    'key78382': 'value19400',
},
    {
    'id': 17527490707694,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Lauren Perkins',
    'address': '9002 Donald Prairie Apt. 450\nWaltonstad, AS 02008',
    'text': 'Beyond section organization rich continue himself movement. Happen outside consumer week performance rather modern majority.\nHit listen recent begin opportunity speak. Tv them none right.',
    'email': 'tiffany96@example.org',
    'phone_number': '857.234.5514',
    'json': {
    'name': 'Crystal Bridges',
    'address': '3700 Walton Estates\nLake Anneburgh, KY 89803',
},
    'key78519': 'value59825',
    'key94065': 'value22768',
    'key15681': 'value97161',
},
    {
    'id': 17527490707704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Stephen Lee',
    'address': '65024 Karen Garden\nEast Isabella, MI 19223',
    'text': 'Deep pay scene play left face amount. Receive detail realize include.\nSpace pass toward here tax and popular interesting. Contain guess behind marriage matter accept.',
    'email': 'davidgentry@example.org',
    'phone_number': '542.846.9524x533',
    'json': {
    'name': 'Colin Martinez',
    'address': '7170 Jacob Avenue\nSouth Henrytown, MA 70514',
},
    'key48301': 'value11704',
},
    {
    'id': 17527490707715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Richard Kennedy',
    'address': 'PSC 5346, Box 6456\nAPO AA 48324',
    'text': 'Administration water bad young world.\nRadio again live condition attention.\nMrs democratic huge law individual image. President next piece. Compare true type enjoy character degree.',
    'email': 'jill62@example.com',
    'phone_number': '+1-815-808-2709x66915',
    'json': {
    'name': 'Debbie Kelly',
    'address': 'Unit 8102 Box 7807\nDPO AP 70305',
},
    'key17114': 'value37263',
    'key84878': 'value89930',
    'key70528': 'value83954',
    'key55240': 'value41098',
    'key85575': 'value5046',
    'key83466': 'value96175',
    'key89805': 'value14686',
    'key75529': 'value46529',
},
    {
    'id': 17527490707722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Laura Sanchez',
    'address': '1749 Paul Stream\nPort Jasmine, CA 17417',
    'text': 'Create president me significant speech race. Parent what none his activity ten enough education.\nThink station often oil. Military concern right successful walk.',
    'email': 'elizabeth77@example.org',
    'phone_number': '+1-454-373-8174x118',
    'json': {
    'name': 'Jack Lucas',
    'address': '08634 Patrick Dale\nBakerborough, VI 06651',
},
    'key91292': 'value62749',
    'key9097': 'value76829',
    'key79150': 'value76731',
    'key79424': 'value73805',
    'key40824': 'value86028',
    'key87818': 'value75368',
    'key68544': 'value47917',
    'key86844': 'value41934',
    'key48486': 'value60658',
},
    {
    'id': 17527490707732,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Lauren Davis',
    'address': '991 Calhoun Lodge Apt. 685\nLake Crystalport, MP 62727',
    'text': 'Fast recent herself thing collection.\nResult involve party finally great sound social. Physical anything perform fast.',
    'email': 'walterchapman@example.com',
    'phone_number': '870.479.3067',
    'json': {
    'name': 'Sheryl Cox',
    'address': '9820 Malone Lodge Suite 975\nObrienmouth, NE 60620',
},
    'key80534': 'value96292',
    'key36384': 'value52851',
    'key16619': 'value37828',
    'key30206': 'value81819',
    'key72851': 'value78641',
    'key57883': 'value25570',
    'key24476': 'value15401',
    'key9139': 'value7403',
    'key85787': 'value44850',
},
    {
    'id': 17527490707745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Todd Nguyen',
    'address': '3737 Harris Cliffs\nLake Lisamouth, KY 45904',
    'text': 'Official these son computer raise wait realize realize. Blue over family under film treatment.\nAccount woman treatment research.',
    'email': 'brian55@example.com',
    'phone_number': '510-837-0598x79986',
    'json': {
    'name': 'Benjamin Johnson',
    'address': '529 David Circles\nSouth Dawn, WI 30104',
},
    'key22871': 'value5638',
    'key74830': 'value65457',
},
    {
    'id': 17527490707755,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Brandon Daniel',
    'address': '315 Jackson Wall\nEast Briannaberg, WI 31024',
    'text': 'Generation film nothing would anything several hot. Agree respond school road country.\nStructure leg certainly term sport see reflect. Resource trade inside week store.',
    'email': 'mwilliams@example.com',
    'phone_number': '416-904-8317x727',
    'json': {
    'name': 'Chloe Johnson',
    'address': '27376 Morgan Flats Suite 226\nNorth Justin, SD 22750',
},
    'key24149': 'value83363',
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
    'RequestId': '01478992-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_24_630363BOmpJEGK',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/entities/get"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/get")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/get'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '01478992-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_24_630363BOmpJEGK',
    'outputFields': [
    '*',
],
    'id': 17527490706782,
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
        """测试请求 5 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '01478992-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_24_630363BOmpJEGK',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestGetVector_test_get_vector_with_simple_payload_1752749073.json')
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
    test = AllmilvusLogtestgetvectorTestGetVectorWithSimplePayload1752749073Json()
    test.run_tests()
