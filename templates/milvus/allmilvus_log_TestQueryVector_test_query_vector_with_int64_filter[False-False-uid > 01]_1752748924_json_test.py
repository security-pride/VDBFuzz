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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 01]_1752748924_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 01]_1752748924.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid011752748924Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 01]_1752748924.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 01]_1752748924.json"
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
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_49_836473TLlZRmWI',
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
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_49_836473TLlZRmWI',
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
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_49_836473TLlZRmWI',
    'data': [
    {
    'id': 17527489158709,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'William West',
    'address': '097 Jennifer Burgs Apt. 627\nOsborneburgh, SD 55985',
    'text': 'Technology current admit build property anyone south toward. Program bed cause deal walk commercial region. Matter loss air though official too traditional.',
    'email': 'thall@example.net',
    'phone_number': '001-793-580-1558x44062',
    'json': {
    'name': 'Joseph Jackson',
    'address': '72267 David Turnpike Apt. 649\nGreenborough, MH 35667',
},
    'key12365': 'value79165',
    'key36977': 'value37565',
    'key35051': 'value31682',
    'key94141': 'value43543',
    'key354': 'value54636',
    'key31115': 'value2349',
    'key21551': 'value75364',
},
    {
    'id': 17527489158730,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Nicholas Carter',
    'address': '301 Stephen Isle Suite 667\nSierraberg, SD 19913',
    'text': 'Interest turn according appear world. Any wife these television no computer.\nWhy improve along in effort mouth let health. System mission management. Consider parent management reach.',
    'email': 'ugarrett@example.org',
    'phone_number': '5287262869',
    'json': {
    'name': 'Timothy Ramirez',
    'address': '7795 Knight Shore Suite 653\nPort Evelynberg, SC 59264',
},
    'key90194': 'value40440',
    'key89695': 'value62185',
    'key48243': 'value57409',
    'key97462': 'value74309',
    'key66356': 'value85285',
},
    {
    'id': 17527489158745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'David Mcgrath',
    'address': '785 Bradley Valley\nSarahstad, AR 76136',
    'text': 'Case community save be. Science change him our never site. Course character must determine room.\nComputer range tax grow. Could ten and father catch physical discussion.',
    'email': 'uholmes@example.net',
    'phone_number': '+1-228-292-4181',
    'json': {
    'name': 'Beverly Williams',
    'address': '739 Nelson Fields Apt. 853\nLake Jonville, NM 29513',
},
    'key94917': 'value15311',
    'key82760': 'value20468',
    'key55016': 'value74310',
    'key3168': 'value97878',
},
    {
    'id': 17527489158759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Stephanie Sandoval',
    'address': 'PSC 6623, Box 8985\nAPO AA 19539',
    'text': 'Save about no rule available. Window cost catch responsibility evidence total.\nScientist police religious.\nTable defense member manage. Economic yet part relationship eye.',
    'email': 'knguyen@example.com',
    'phone_number': '001-974-301-9380x441',
    'json': {
    'name': 'Justin Rivera',
    'address': '44233 Derrick Springs Suite 006\nSouth Sarah, AS 81028',
},
    'key67252': 'value11094',
    'key71752': 'value50749',
    'key81731': 'value36284',
    'key50695': 'value99350',
    'key33450': 'value51069',
},
    {
    'id': 17527489158770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Jaime Williams',
    'address': '20772 Lisa Street Suite 669\nPort Samanthaside, IA 16419',
    'text': 'Sell spend war end. Serve these hotel month.\nDrop moment happen hair read religious movie. All air style them game. Morning rule wife nice as.',
    'email': 'katherine38@example.org',
    'phone_number': '(890)487-6555x612',
    'json': {
    'name': 'Lee Robinson',
    'address': 'PSC 0076, Box 6477\nAPO AA 63336',
},
    'key71788': 'value324',
    'key81608': 'value54980',
    'key55010': 'value88423',
    'key77509': 'value28446',
    'key91020': 'value36106',
},
    {
    'id': 17527489158781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Miranda Gregory',
    'address': '9434 Rose Trail\nEast Jillian, IL 28926',
    'text': 'Kitchen head represent huge company cold lot free. Education top month realize war behind.\nBuilding American too day letter eat. Voice wide camera sister. Get risk half. Million teach yard watch.',
    'email': 'iromero@example.org',
    'phone_number': '(793)605-0414x890',
    'json': {
    'name': 'Cynthia Brooks',
    'address': 'PSC 1265, Box 0259\nAPO AA 71969',
},
    'key52476': 'value57867',
    'key60546': 'value33707',
    'key11339': 'value85793',
},
    {
    'id': 17527489158792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Tony Williams',
    'address': '0286 Smith Avenue\nPort Miguelburgh, MI 41308',
    'text': 'Hair expert rule none want change. Something situation professor. Purpose middle scene pick gas central.',
    'email': 'afriedman@example.org',
    'phone_number': '274.400.5360x341',
    'json': {
    'name': 'John Lewis',
    'address': 'USS Macdonald\nFPO AE 30103',
},
    'key22666': 'value46191',
    'key97435': 'value70273',
    'key86247': 'value68368',
    'key72955': 'value14556',
    'key97677': 'value5493',
    'key89717': 'value37570',
},
    {
    'id': 17527489158803,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Allen Morrow',
    'address': '29059 Travis Stream Apt. 582\nKarenton, OK 24242',
    'text': 'True never this interview pretty prevent reason. They himself low old out special movie. Sit each as five east describe.\nBit rest piece. Office conference commercial view kid. One rock nation should.',
    'email': 'spencershawn@example.com',
    'phone_number': '(672)473-8595x2140',
    'json': {
    'name': 'Juan Baker',
    'address': '8510 Warren Valleys\nEast Joshua, CA 56674',
},
    'key90191': 'value95178',
    'key26990': 'value93006',
    'key39637': 'value69864',
    'key7063': 'value92771',
},
    {
    'id': 17527489158815,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Lorraine Sanders',
    'address': '226 Jennifer Fields Suite 476\nMejiatown, AS 16391',
    'text': 'Protect entire lose. Chance carry authority discussion. Bar stage difference first customer hold discussion.',
    'email': 'stephanie47@example.com',
    'phone_number': '532.350.4339x516',
    'json': {
    'name': 'Joanna Forbes',
    'address': '460 Rogers Center\nNorth Jeff, NH 68163',
},
    'key13453': 'value6231',
    'key91010': 'value87627',
    'key82526': 'value57876',
    'key84593': 'value28244',
    'key74949': 'value62857',
    'key17294': 'value76297',
    'key84993': 'value13658',
    'key69773': 'value27578',
    'key88457': 'value2865',
},
    {
    'id': 17527489158826,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Brendan Mccoy',
    'address': '6062 Christine Course Suite 756\nNew Ronnieshire, ID 71089',
    'text': 'Rather difference medical team leave. Whole almost exist human strategy article attack.\nThrow alone official assume including put just. Western guess condition put do pressure.',
    'email': 'wileypenny@example.com',
    'phone_number': '972-456-1200x662',
    'json': {
    'name': 'Vincent Robertson',
    'address': '75911 Patrick Brooks\nJasonport, NC 00834',
},
    'key41501': 'value4915',
    'key55153': 'value94247',
    'key96705': 'value17793',
    'key22160': 'value54225',
    'key15131': 'value50064',
},
    {
    'id': 17527489158837,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Jeff Garrett',
    'address': '5926 Cole Trail Suite 884\nSouth Kaylamouth, DC 66066',
    'text': 'Large recognize girl. Say amount opportunity whether weight. Toward myself chance policy red work these.\nOver federal investment arm. Civil across know enjoy everything remember.',
    'email': 'ashley33@example.net',
    'phone_number': '+1-324-376-4498x9599',
    'json': {
    'name': 'Brad Rodriguez',
    'address': '795 Brenda Haven Apt. 293\nEast Mikefurt, IA 78078',
},
    'key66480': 'value32132',
    'key2963': 'value95938',
    'key39912': 'value43699',
    'key91039': 'value28762',
    'key53034': 'value47123',
    'key27480': 'value30656',
    'key7203': 'value57248',
},
    {
    'id': 17527489158848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Shawn Lopez',
    'address': '832 Lisa Groves Suite 293\nWatsonton, PA 54792',
    'text': 'Time person second wear go.\nVote realize amount something. No economy design try.\nChurch military hour raise amount born. Reduce skin treatment special. Morning plan big score.',
    'email': 'scott97@example.com',
    'phone_number': '747.879.2509x897',
    'json': {
    'name': 'Steve Hawkins',
    'address': '811 Edward Lock\nWest Nicholashaven, WV 21281',
},
    'key11380': 'value38806',
    'key87050': 'value98199',
    'key64752': 'value95194',
    'key51829': 'value97764',
    'key43616': 'value65347',
    'key54084': 'value18572',
    'key31192': 'value68277',
    'key93435': 'value84312',
},
    {
    'id': 17527489158859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Roger Oliver',
    'address': '033 Perez Burgs\nNorth Kellistad, HI 78126',
    'text': 'Walk during blood occur traditional woman easy. Expert today feeling paper understand. Science surface second table teacher office majority.',
    'email': 'juangraham@example.net',
    'phone_number': '001-487-730-8585x07006',
    'json': {
    'name': 'Thomas Berry',
    'address': 'USNS Anderson\nFPO AE 46712',
},
    'key3545': 'value70247',
},
    {
    'id': 17527489158869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Crystal Patterson',
    'address': '178 Valerie Curve\nJoanshire, KY 32310',
    'text': 'Parent local opportunity owner media activity month. Exist seem think into during figure form.',
    'email': 'robertolong@example.com',
    'phone_number': '001-971-545-5334',
    'json': {
    'name': 'Kristin Donaldson',
    'address': '10540 Roberts Curve Suite 598\nJohnbury, FL 79036',
},
    'key55895': 'value8293',
    'key59543': 'value44407',
    'key99348': 'value14799',
    'key73925': 'value34501',
    'key20476': 'value14211',
    'key40031': 'value50969',
    'key9950': 'value73403',
},
    {
    'id': 17527489158880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jason Johnson',
    'address': '448 Tiffany Drive Suite 103\nIanshire, NC 92552',
    'text': 'Trouble memory head general new south safe board. Note word kid already scene control. Day believe foot southern baby particularly.',
    'email': 'james08@example.org',
    'phone_number': '(975)812-9250',
    'json': {
    'name': 'Anne Campbell',
    'address': '28821 Erica Underpass Apt. 250\nEast Jennifermouth, WA 26804',
},
    'key65995': 'value32352',
    'key11924': 'value1124',
    'key29170': 'value18258',
},
    {
    'id': 17527489158890,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Amber Williams',
    'address': '205 Parker Well Apt. 162\nGreenebury, LA 65061',
    'text': 'Available coach family behind consumer product stand natural. Major person among garden last pull loss. Start most brother fear.',
    'email': 'thomaskennedy@example.net',
    'phone_number': '001-496-987-9088',
    'json': {
    'name': 'Margaret Mercado',
    'address': '720 Cortez Lake Suite 152\nCalebhaven, AL 26788',
},
    'key82106': 'value4452',
    'key77801': 'value24881',
    'key22424': 'value87090',
    'key83396': 'value97403',
    'key98597': 'value39275',
    'key66490': 'value19870',
    'key86873': 'value64829',
    'key6830': 'value43570',
    'key49258': 'value79562',
},
    {
    'id': 17527489158902,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'James Mckinney',
    'address': '37764 Bradley Knolls Apt. 039\nNorth Scottland, ND 99928',
    'text': 'Early argue use mission opportunity.\nWhose third turn minute.\nHead say art type look. Military record though give any.',
    'email': 'bethany67@example.com',
    'phone_number': '(729)399-2764',
    'json': {
    'name': 'Ryan Franco',
    'address': '02030 Flores Ports Apt. 153\nPort Bailey, NC 84692',
},
    'key75804': 'value46492',
    'key2548': 'value72554',
    'key48650': 'value93186',
    'key5233': 'value74884',
    'key72058': 'value69100',
},
    {
    'id': 17527489158913,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Gina Johnson MD',
    'address': '01026 Grant Gardens Suite 226\nBarnettfurt, MO 15850',
    'text': 'Thing thank guy raise partner whom meeting. Because citizen walk production memory rock body.',
    'email': 'dthompson@example.com',
    'phone_number': '925.240.8113x641',
    'json': {
    'name': 'Mr. Johnny Ramos',
    'address': '0207 Willie Well\nPort Austinland, MN 58592',
},
    'key53444': 'value9192',
    'key38607': 'value33719',
    'key18960': 'value19709',
},
    {
    'id': 17527489158924,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Phillip Ford',
    'address': '88353 Jasmine Drives\nScotttown, AL 17706',
    'text': 'Price land moment ability option phone matter. Try leave society sort finally race street.',
    'email': 'colemanfrank@example.org',
    'phone_number': '+1-857-808-4271x7422',
    'json': {
    'name': 'Gregory Mason',
    'address': '1991 Julie Plaza Apt. 310\nValentinebury, SC 54001',
},
    'key68864': 'value25523',
    'key951': 'value99873',
    'key65172': 'value37812',
    'key55182': 'value65996',
},
    {
    'id': 17527489158935,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jeffrey Lawrence',
    'address': '95913 Velasquez Gardens\nVegabury, TX 63945',
    'text': 'Work toward again not party PM out. Buy everything likely course hour chance those. President else third hair.',
    'email': 'zmarquez@example.com',
    'phone_number': '001-853-441-4332x0396',
    'json': {
    'name': 'Paul Watson',
    'address': '693 Cordova Rapid\nNew Patrickshire, NJ 64740',
},
    'key89163': 'value41245',
    'key14488': 'value83199',
    'key85406': 'value62752',
    'key29258': 'value34671',
    'key15747': 'value40447',
    'key8623': 'value17388',
},
    {
    'id': 17527489158947,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Timothy Nguyen',
    'address': '3932 Jerry Knolls\nLake Jessicaland, PA 03442',
    'text': 'Capital father interview name fall seem hold. Couple bag health upon stop. Money reduce none sea enough put.',
    'email': 'danielschristine@example.org',
    'phone_number': '001-645-760-3004x52038',
    'json': {
    'name': 'Ralph Goodwin',
    'address': '8727 Sanchez Streets Suite 194\nRyanfurt, MS 59828',
},
    'key78011': 'value48344',
    'key98313': 'value32600',
    'key78753': 'value62647',
    'key12708': 'value62323',
    'key20037': 'value90288',
    'key30528': 'value47807',
    'key1948': 'value51323',
    'key82748': 'value22230',
    'key59605': 'value98381',
},
    {
    'id': 17527489158958,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Angie Ward',
    'address': '6452 Miguel Circles Suite 173\nLake Michael, VI 75028',
    'text': 'Mention between yourself much because two understand. Hour house suggest think arrive. These ever recognize tree tell.',
    'email': 'enash@example.org',
    'phone_number': '+1-960-472-9920x15892',
    'json': {
    'name': 'Marcus Hill',
    'address': '3213 Katrina Parkways\nEast Russell, NH 45217',
},
    'key6272': 'value35256',
    'key33432': 'value73079',
    'key22878': 'value70311',
    'key13539': 'value65737',
    'key14466': 'value73972',
    'key83692': 'value26514',
    'key60944': 'value44455',
    'key48661': 'value18040',
    'key5315': 'value72056',
},
    {
    'id': 17527489158969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Ryan Davis',
    'address': 'USNV Evans\nFPO AA 11557',
    'text': 'All chair agent message reason book. Everyone type note worker a unit PM.\nDinner direction consumer concern page face. Father station range always some look. Man manager year teach.',
    'email': 'kurt85@example.com',
    'phone_number': '(618)764-3311x5373',
    'json': {
    'name': 'Krystal Howell DVM',
    'address': '8753 Nicholson Street\nSouth Richard, PA 87649',
},
    'key4287': 'value9741',
    'key78762': 'value46246',
},
    {
    'id': 17527489158978,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jaime Michael',
    'address': '50030 Collins Shore Apt. 426\nWeberport, HI 11142',
    'text': 'Move thought ready participant environmental relate west. Deep account fund including price particular. Past dream half effort sing table.\nNatural system young play wife. Study month price various.',
    'email': 'justinkeller@example.net',
    'phone_number': '+1-323-510-7841x8800',
    'json': {
    'name': 'Patricia Colon',
    'address': '42474 Brown Rapids Apt. 371\nAllisonshire, MN 17787',
},
    'key43804': 'value43408',
    'key87684': 'value39297',
    'key97858': 'value20985',
    'key66142': 'value13239',
    'key36747': 'value24029',
    'key34204': 'value94917',
    'key9081': 'value89529',
},
    {
    'id': 17527489158990,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Michael Tran',
    'address': '65557 Thomas Lodge Suite 392\nLisachester, AZ 11653',
    'text': 'Resource year memory dream into prepare. Choose technology every. Part interest toward choose candidate true. Product skin write model.\nHot himself contain only. School edge blood yard.',
    'email': 'williamskathleen@example.org',
    'phone_number': '222.755.7433',
    'json': {
    'name': 'Anna Grimes',
    'address': '70281 Parsons Mountain\nWest Brianchester, ID 01698',
},
    'key72934': 'value88210',
    'key81971': 'value81286',
    'key28558': 'value54027',
    'key59670': 'value6838',
    'key27957': 'value29677',
    'key50084': 'value22212',
    'key67152': 'value28838',
    'key40279': 'value15037',
    'key68837': 'value25618',
    'key50762': 'value79788',
},
    {
    'id': 17527489159002,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Sean Ellis PhD',
    'address': '4716 Trujillo Forks Apt. 557\nLake Aliciatown, NV 96315',
    'text': 'Social left simply. Why nor drive only Republican pick today. Space among quite chance.\nAccount amount change back. Different Congress edge here discuss people develop.',
    'email': 'morriseric@example.com',
    'phone_number': '+1-898-712-2716',
    'json': {
    'name': 'Norman Davis',
    'address': '1834 Anthony Pines\nGlassmouth, NH 50020',
},
    'key119': 'value80810',
    'key82619': 'value83068',
    'key15408': 'value49363',
    'key32781': 'value90467',
    'key67658': 'value34309',
    'key68686': 'value44134',
    'key58508': 'value88371',
    'key40721': 'value63970',
},
    {
    'id': 17527489159013,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Brandon Callahan',
    'address': '895 Koch Canyon\nRobertsburgh, RI 10464',
    'text': 'Reduce fund language. Summer always article its purpose voice.\nAttorney century dog response watch. Support from eye unit.',
    'email': 'mackenzieholmes@example.com',
    'phone_number': '576-571-8616',
    'json': {
    'name': 'Margaret Webster',
    'address': '642 Reynolds Ford\nPowersville, CO 87214',
},
    'key54286': 'value84178',
    'key83109': 'value22536',
    'key40163': 'value10872',
    'key45184': 'value62425',
},
    {
    'id': 17527489159025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'John Higgins',
    'address': '87882 Evans Plaza\nJeffreyberg, DE 21826',
    'text': 'Find deal before after final. Program out trip.\nForce personal middle shake exist campaign. Star paper policy or pretty situation amount available. Star ago book these fight eat.',
    'email': 'rpayne@example.org',
    'phone_number': '952-459-6566x3116',
    'json': {
    'name': 'Dr. Paula Nelson PhD',
    'address': '75140 Jonathan Groves\nNorth Jerome, NM 07813',
},
    'key21752': 'value74290',
    'key93056': 'value28989',
    'key56233': 'value24298',
    'key43907': 'value59980',
    'key6347': 'value45508',
    'key87790': 'value31334',
    'key21638': 'value19556',
},
    {
    'id': 17527489159037,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Kevin Hernandez',
    'address': '674 Russell Freeway Apt. 284\nTaylorbury, SC 55949',
    'text': 'Concern pass here. Without within eye receive quality.\nYoung actually area radio Mrs. Risk suffer activity suddenly order mean. Go consumer true actually off.',
    'email': 'owatson@example.net',
    'phone_number': '+1-427-411-4358x97404',
    'json': {
    'name': 'Kayla Moyer',
    'address': '98602 Bray Gardens\nNew Elizabethmouth, UT 47710',
},
    'key86905': 'value70592',
    'key20072': 'value12863',
    'key75706': 'value56679',
},
    {
    'id': 17527489159048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Kimberly Payne',
    'address': '24343 Elliott Flats Suite 175\nHerreraland, RI 76331',
    'text': 'Past ready American fear. Present five something interest total father.\nBad take lot bit deep military. Quickly prevent case vote defense real fire employee.',
    'email': 'hannahbrooks@example.net',
    'phone_number': '001-427-703-4423',
    'json': {
    'name': 'Danielle Kennedy',
    'address': '674 Garcia Summit\nPort Anne, HI 60447',
},
    'key63841': 'value19627',
    'key9549': 'value22951',
    'key77614': 'value80802',
},
    {
    'id': 17527489159060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Nancy Eaton',
    'address': '20659 Michael Ridge Suite 295\nPort Hollymouth, MN 29338',
    'text': 'Strategy hair church enjoy church. Language floor run.\nScore way big.\nCustomer huge century.',
    'email': 'chenrobert@example.org',
    'phone_number': '001-415-800-2543',
    'json': {
    'name': 'Jose Walker',
    'address': '675 Williams Spring Suite 041\nVazquezburgh, FM 03165',
},
    'key79398': 'value7388',
    'key35587': 'value4411',
    'key66719': 'value18659',
    'key45177': 'value72340',
    'key91260': 'value88517',
    'key67121': 'value46590',
    'key25104': 'value17586',
},
    {
    'id': 17527489159072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Angela Jones',
    'address': '65716 Brown Orchard\nNew Jeremyshire, MN 31257',
    'text': 'Actually right cell these. Sense hold role public.\nIt among central left family. Threat fall free prove. Our long fight traditional indicate author two anything.',
    'email': 'hogangregory@example.net',
    'phone_number': '001-420-646-5876x235',
    'json': {
    'name': 'Tracy Williams',
    'address': '23056 Harrington Mountains\nWest Wandachester, KS 05448',
},
    'key6253': 'value22336',
    'key35768': 'value67519',
},
    {
    'id': 17527489159084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Connie Blevins',
    'address': '812 Ann Lodge Apt. 019\nNorth Joshua, IA 36218',
    'text': 'Range ground participant former school art. Activity decision trade brother her.',
    'email': 'karlamartinez@example.com',
    'phone_number': '+1-802-954-8239',
    'json': {
    'name': 'Ronald Morris',
    'address': '211 Charles Mountains Apt. 538\nMurraymouth, VI 82415',
},
    'key71871': 'value82870',
    'key50021': 'value35040',
    'key66164': 'value7375',
    'key66386': 'value19362',
},
    {
    'id': 17527489159095,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michelle Hodges',
    'address': '37593 Linda Lodge\nNew Johnport, UT 37734',
    'text': 'Ground wide lawyer organization hear anything it. Animal off management parent strategy job. Citizen blood century give item.',
    'email': 'gregorygabrielle@example.org',
    'phone_number': '001-328-508-5616x2857',
    'json': {
    'name': 'Lance York',
    'address': '798 Mcclure Grove\nNorth Caleb, WA 15847',
},
    'key13692': 'value36141',
    'key78649': 'value22946',
    'key72703': 'value44771',
    'key79999': 'value10307',
    'key57228': 'value78003',
    'key23272': 'value51014',
    'key46602': 'value29161',
    'key45917': 'value75060',
},
    {
    'id': 17527489159106,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Nicholas Marsh',
    'address': '95984 Hernandez Village Apt. 020\nSouth Jeffreyland, DC 09132',
    'text': 'Down point news heavy. Listen he real quality tree should central. Do hospital when movement everything general. Shake about management assume act sign.',
    'email': 'rshaffer@example.com',
    'phone_number': '(387)739-4796',
    'json': {
    'name': 'Cameron Harris',
    'address': '86454 Brandon View\nBradstad, MO 69338',
},
    'key13012': 'value71715',
    'key43799': 'value65471',
    'key99638': 'value65549',
    'key95364': 'value82709',
    'key38226': 'value96896',
    'key167': 'value87285',
    'key38284': 'value39126',
    'key23058': 'value44716',
    'key74648': 'value59959',
    'key39165': 'value45744',
},
    {
    'id': 17527489159117,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jeffrey Stevens',
    'address': '612 Angela Estates Suite 232\nMorrismouth, MP 92221',
    'text': 'Option manage need father. Of officer break later.\nNewspaper however smile personal effort. Person successful serve truth however.',
    'email': 'heather79@example.org',
    'phone_number': '989-392-5910x569',
    'json': {
    'name': 'Patricia Bowman',
    'address': '866 Brent Pike\nStevenberg, TX 54157',
},
    'key8780': 'value63311',
    'key4538': 'value70499',
    'key64931': 'value12531',
    'key99531': 'value8892',
    'key59864': 'value42882',
    'key35105': 'value51222',
},
    {
    'id': 17527489159128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Melissa Goodman',
    'address': '1812 Wall Oval Suite 866\nLake Michael, TX 27197',
    'text': 'Special bar executive rate reality paper ahead. Success stage popular American. Do well street blue administration.\nUp that realize. Not star like attack. Message take dark suggest debate heart.',
    'email': 'perezkristin@example.org',
    'phone_number': '412-833-1851',
    'json': {
    'name': 'Amy Rowland',
    'address': '00030 Mary Turnpike\nMelissaview, TX 53357',
},
    'key31607': 'value58877',
    'key42584': 'value55441',
},
    {
    'id': 17527489159139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Kelly Smith',
    'address': '41205 Adam Cliffs Suite 187\nNorth Staceyborough, LA 84524',
    'text': 'Expert carry certainly expect every in chair. Rest box finally although. Its like technology safe political term particularly. Training raise late foot prepare upon tree.',
    'email': 'hernandezangela@example.org',
    'phone_number': '(815)781-2524',
    'json': {
    'name': 'Ms. Ashley Stewart',
    'address': '5540 Kimberly Radial\nEast Kayla, WY 40337',
},
    'key13414': 'value85087',
    'key97971': 'value25058',
},
    {
    'id': 17527489159151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Joshua Thompson',
    'address': '58962 Welch Ports Suite 589\nSouth Marcusmouth, DC 02897',
    'text': 'Born reality green prepare. Feeling read prepare. Where father size economic tend report phone.\nKind oil important work. The thing decade pressure carry. Better throughout group since too.',
    'email': 'catherine68@example.com',
    'phone_number': '(351)889-6636x186',
    'json': {
    'name': 'Dustin Moore',
    'address': '86273 Jessica Forge\nPort Kristinamouth, AS 31228',
},
    'key75593': 'value73342',
    'key75995': 'value96716',
    'key20740': 'value6006',
    'key63652': 'value56414',
    'key21324': 'value57267',
    'key15309': 'value89001',
    'key43442': 'value9938',
    'key84622': 'value74947',
    'key17982': 'value22535',
    'key13474': 'value3931',
},
    {
    'id': 17527489159162,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Darryl Palmer',
    'address': '27733 Stephanie River Apt. 887\nSouth Josephberg, VA 76934',
    'text': 'Country stock future stage partner fact bank. Human thing pick learn ability race.\nMatter tax responsibility treat. Store weight after.',
    'email': 'bsanders@example.com',
    'phone_number': '326.448.3204x38222',
    'json': {
    'name': 'Kayla Schneider',
    'address': '47686 Goodman Cape\nNew John, WI 78752',
},
    'key40539': 'value40199',
    'key82940': 'value6451',
    'key13532': 'value66899',
    'key89637': 'value93646',
},
    {
    'id': 17527489159173,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Erica Harris',
    'address': 'PSC 6572, Box 5931\nAPO AA 96717',
    'text': 'Sea national wait goal that yard. Attorney relate while three money inside market. Amount idea born man yet offer including.',
    'email': 'courtneyrobertson@example.net',
    'phone_number': '+1-403-468-0010x347',
    'json': {
    'name': 'Susan Fox',
    'address': 'PSC 7757, Box 2824\nAPO AA 47515',
},
    'key81192': 'value89531',
    'key78411': 'value76482',
    'key79329': 'value42073',
    'key36642': 'value27806',
    'key89579': 'value82103',
    'key43373': 'value96028',
    'key56605': 'value70710',
},
    {
    'id': 17527489159180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Wendy Nelson',
    'address': '400 Susan Groves\nNorth Loretta, NH 53212',
    'text': 'Region find within take half system benefit this. Kitchen during movie heart red occur seven. Push cultural case citizen into.',
    'email': 'samuelsmith@example.net',
    'phone_number': '+1-531-288-1631',
    'json': {
    'name': 'Megan Fry',
    'address': '20880 Alan Fort\nNorth Mark, MT 60538',
},
    'key57798': 'value30541',
    'key68855': 'value41626',
    'key57521': 'value92717',
    'key57472': 'value57862',
    'key57142': 'value96263',
    'key46064': 'value96665',
    'key64494': 'value65636',
    'key35329': 'value25450',
    'key47422': 'value49817',
    'key55990': 'value52038',
},
    {
    'id': 17527489159191,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Mark Martinez',
    'address': 'PSC 4860, Box 2271\nAPO AP 62430',
    'text': 'Its prove rise little have scene under. Collection during once share per door.\nWest believe experience specific art black once. Gun cultural show at. Front break could class tonight nation seven.',
    'email': 'kwalker@example.org',
    'phone_number': '(900)843-7186x989',
    'json': {
    'name': 'Michael Allen',
    'address': '372 Hall Flats\nBrookemouth, AL 11253',
},
    'key406': 'value90951',
    'key89678': 'value87094',
    'key26592': 'value45163',
    'key48701': 'value48978',
    'key14626': 'value28814',
    'key15446': 'value31730',
},
    {
    'id': 17527489159201,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Matthew Ryan',
    'address': '4277 Gibbs Locks\nMendozaborough, NY 06338',
    'text': 'Foot popular much whether mouth young. Will sound plant hold leave throw. Final letter cell education nation opportunity.',
    'email': 'rallison@example.org',
    'phone_number': '2914380972',
    'json': {
    'name': 'Katherine Allen',
    'address': '58532 Thomas Pass Apt. 573\nWoodsfurt, VA 31957',
},
    'key71960': 'value76607',
    'key50202': 'value47263',
    'key99374': 'value94603',
    'key31166': 'value79317',
},
    {
    'id': 17527489159212,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Daniel Duncan',
    'address': '858 Joseph Track\nLake Katrinaberg, IL 41452',
    'text': 'Evening teacher art blood relationship listen quality. Air society attention involve.',
    'email': 'clewis@example.com',
    'phone_number': '545.975.7698x96060',
    'json': {
    'name': 'Nicole Wilson',
    'address': '95186 Charles Garden\nPattersonfurt, MA 24581',
},
    'key62583': 'value44625',
    'key38496': 'value63853',
    'key65791': 'value81282',
    'key8052': 'value56110',
    'key31022': 'value81358',
    'key49194': 'value42367',
    'key49886': 'value31641',
    'key25475': 'value74587',
    'key48734': 'value11272',
    'key94779': 'value81471',
},
    {
    'id': 17527489159223,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Hannah Montgomery',
    'address': '5286 Burton Haven Apt. 318\nLake Nicholas, ME 29632',
    'text': 'Civil everybody machine beyond before visit impact. Cup check agree fast.',
    'email': 'mahoneybrandi@example.org',
    'phone_number': '(737)988-3531',
    'json': {
    'name': 'Ryan Saunders',
    'address': '4635 Parks Island\nWest Thomasmouth, KY 92796',
},
    'key5950': 'value37229',
    'key75423': 'value97346',
    'key89647': 'value52292',
    'key63014': 'value68854',
    'key57164': 'value47351',
    'key30578': 'value18421',
},
    {
    'id': 17527489159235,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Mark Marquez',
    'address': '8692 Whitney Mission Suite 250\nPort Amandatown, MI 85649',
    'text': 'Surface hospital these since herself movement professional. Station owner return daughter structure watch. Nearly whatever between.',
    'email': 'josephrhonda@example.org',
    'phone_number': '859-863-7029x5593',
    'json': {
    'name': 'Madeline Simpson',
    'address': '17093 Richardson Path Apt. 987\nWilliamstown, NC 08918',
},
    'key6252': 'value46442',
    'key29877': 'value16388',
    'key20421': 'value7608',
    'key58183': 'value46782',
    'key82385': 'value11444',
    'key98325': 'value32784',
},
    {
    'id': 17527489159247,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Edward Burke',
    'address': 'USNV Berry\nFPO AP 35118',
    'text': 'Likely loss food environmental father. Protect exactly stay edge husband fine. Need process worry program strong idea identify.\nExpect goal watch rise lawyer health.',
    'email': 'carpentersamantha@example.com',
    'phone_number': '423-588-1405x36635',
    'json': {
    'name': 'Barbara Cain',
    'address': '28313 Orozco Mount Suite 813\nPort Mark, LA 18976',
},
    'key31002': 'value2057',
    'key80774': 'value10144',
},
    {
    'id': 17527489159258,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Lisa Perry',
    'address': '9250 Donald Shoal Apt. 060\nLewisville, AL 36170',
    'text': 'Change nothing brother her. Marriage than boy move former interesting cause.\nAnswer size century save. Throughout myself house name myself plant free. Wait machine anyone seem.',
    'email': 'wendy19@example.com',
    'phone_number': '+1-700-690-4298x699',
    'json': {
    'name': 'James Brown',
    'address': 'Unit 5453 Box 4137\nDPO AE 97252',
},
    'key71050': 'value67186',
    'key84079': 'value60738',
    'key88385': 'value86944',
    'key14251': 'value81628',
},
    {
    'id': 17527489159266,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Jorge Bailey',
    'address': '54878 Huff Center Suite 123\nPort Andrewville, AZ 71159',
    'text': 'Threat part send television. Teach stay east travel. Return enter manage say watch want large leave.',
    'email': 'paynealexis@example.com',
    'phone_number': '635-414-4861x2051',
    'json': {
    'name': 'Charles Hensley',
    'address': '856 Collins Ville\nPort Jodi, SD 65721',
},
    'key95664': 'value93297',
    'key9896': 'value59234',
},
    {
    'id': 17527489159278,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Dan Smith',
    'address': '24621 Nicholas Inlet Suite 872\nNorth Jayfort, VA 23342',
    'text': 'We more me imagine move support short. They total generation song why leg agreement.\nDegree movement here officer address. Reveal because serious story director weight good.',
    'email': 'tnelson@example.net',
    'phone_number': '928-279-7280',
    'json': {
    'name': 'Matthew Daniel',
    'address': '771 Wilson Turnpike Suite 635\nKimberlymouth, MT 74479',
},
    'key6962': 'value69966',
},
    {
    'id': 17527489159289,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Dr. Scott Hall',
    'address': '19844 Daniel Rapids\nWest Gina, IA 36255',
    'text': 'Hot activity much sit area week smile. Participant attorney shoulder people skin sort.\nFilm cell fire yourself much. Simple anything picture me. Along record hit middle attack system worry.',
    'email': 'fgutierrez@example.com',
    'phone_number': '+1-559-443-1480x2577',
    'json': {
    'name': 'Kathryn Jefferson',
    'address': '45656 Brenda Spurs Apt. 322\nWest Matthew, MO 99349',
},
    'key1246': 'value42379',
    'key40340': 'value85996',
    'key85016': 'value71174',
    'key68848': 'value77499',
    'key23945': 'value9480',
    'key32229': 'value78236',
    'key78792': 'value20741',
    'key30897': 'value89608',
    'key55225': 'value17755',
},
    {
    'id': 17527489159300,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Frances Duncan MD',
    'address': '45100 Perry Plaza\nDeanstad, MI 42339',
    'text': 'Certainly bar father that. Summer scene PM their.\nPolicy call call wall. To drop include grow seem.',
    'email': 'danielrodriguez@example.org',
    'phone_number': '(583)539-8339x1669',
    'json': {
    'name': 'Seth Woods',
    'address': '68279 Valerie Plain\nBakerport, ID 28326',
},
    'key50446': 'value20799',
    'key67880': 'value17441',
    'key75395': 'value47920',
    'key57787': 'value97478',
    'key98801': 'value77464',
    'key13483': 'value60703',
    'key61429': 'value46854',
    'key26072': 'value7103',
},
    {
    'id': 17527489159311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Kevin Daniel',
    'address': '976 Rodriguez Burg Suite 923\nRobertville, GU 38620',
    'text': 'World finish meeting kitchen four car future. Away board pressure entire enjoy in close. Force last town perform return.',
    'email': 'ellismiranda@example.org',
    'phone_number': '512-570-3978',
    'json': {
    'name': 'Nathaniel Chang',
    'address': '671 Barnes Ways Suite 166\nJerryhaven, MT 10823',
},
    'key93417': 'value32429',
    'key47312': 'value29184',
    'key7643': 'value53370',
    'key56283': 'value88606',
    'key96029': 'value62716',
    'key84918': 'value25695',
    'key7692': 'value13366',
},
    {
    'id': 17527489159323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Daniel Davis',
    'address': '322 Buck Common\nEast Leechester, KY 59071',
    'text': 'Player interesting president. Either reach magazine record son behind.\nShoulder shoulder worry although.',
    'email': 'swolf@example.net',
    'phone_number': '618-453-4687',
    'json': {
    'name': 'Alexis Lopez',
    'address': '911 Richardson Roads\nTimothyburgh, WY 53521',
},
    'key87724': 'value47560',
    'key56462': 'value95786',
    'key53177': 'value13633',
    'key11573': 'value95903',
    'key25540': 'value28970',
    'key5413': 'value1144',
    'key62538': 'value41585',
    'key57364': 'value65064',
    'key62028': 'value83001',
    'key94189': 'value38192',
},
    {
    'id': 17527489159334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jacob Hobbs',
    'address': '21120 Debbie Parkway Apt. 715\nJohnton, ME 32816',
    'text': 'Her crime guess southern pressure.\nRead paper enjoy season choose. Rather put raise major agent. Different ask officer tend.',
    'email': 'rreed@example.com',
    'phone_number': '(856)603-9086',
    'json': {
    'name': 'Mallory Guerrero DDS',
    'address': 'PSC 8508, Box 5002\nAPO AE 13536',
},
    'key18012': 'value80789',
    'key18211': 'value53136',
    'key9475': 'value14706',
    'key76798': 'value82585',
    'key71769': 'value49738',
    'key12691': 'value90840',
    'key18710': 'value91177',
    'key39401': 'value35805',
    'key98233': 'value90804',
},
    {
    'id': 17527489159343,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Vickie Ross',
    'address': '972 Blackburn Spur Apt. 367\nTimothyberg, ID 87546',
    'text': 'Certain level sell as including out. Born hope cold among onto figure. Animal collection admit.',
    'email': 'williamssteven@example.com',
    'phone_number': '6377419077',
    'json': {
    'name': 'Christina Jackson',
    'address': '985 Anthony Heights\nGarciastad, PR 66268',
},
    'key19883': 'value55728',
    'key56': 'value45099',
},
    {
    'id': 17527489159354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Kristina Hernandez',
    'address': '19951 Adams Grove Suite 273\nPort Brandyburgh, MT 22171',
    'text': 'High significant risk out. Medical owner now can. Together move item should quite decision head.\nMan reach have almost exist poor. Tax region thought note American evening treatment.',
    'email': 'danielnguyen@example.net',
    'phone_number': '789.802.0128x6018',
    'json': {
    'name': 'Andre Morris',
    'address': '93647 Jones Rapid\nEast Christopherhaven, NM 01244',
},
    'key85481': 'value21791',
    'key99081': 'value57551',
    'key82894': 'value54618',
},
    {
    'id': 17527489159366,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'David Davis',
    'address': '0653 Barajas Burgs Suite 070\nMcconnellville, LA 46849',
    'text': 'Any dark cause success across. Politics tell bring whole.\nHerself the necessary people.\nSpecial seven even least long increase. Interview fly car style.',
    'email': 'rcardenas@example.com',
    'phone_number': '571.722.6586x1104',
    'json': {
    'name': 'Brittney Graham',
    'address': '401 Patel Roads\nPamelaland, TX 27764',
},
    'key26485': 'value62544',
    'key36260': 'value93735',
    'key95786': 'value85133',
    'key40870': 'value74376',
    'key30213': 'value13867',
    'key19909': 'value2944',
    'key3225': 'value86309',
},
    {
    'id': 17527489159377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Kathleen Rogers',
    'address': '7416 Mendez Isle Apt. 705\nAndrewberg, AS 34659',
    'text': 'All process heavy moment participant maintain although.\nBelieve Mrs machine. At between high arrive quickly trade.',
    'email': 'jonathonjohnson@example.net',
    'phone_number': '315.401.2750',
    'json': {
    'name': 'Whitney Adams',
    'address': 'USNS Knox\nFPO AP 78115',
},
    'key17939': 'value10115',
    'key36021': 'value33121',
    'key79184': 'value98607',
    'key5412': 'value73189',
    'key80012': 'value1813',
},
    {
    'id': 17527489159388,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Paul Jackson DDS',
    'address': '4780 Brendan Park Apt. 546\nWendyburgh, NC 93828',
    'text': 'Thousand yet whose. Board detail collection sense first enough improve.\nRange then sure must produce book production knowledge. Note value remember event. Rest next care.',
    'email': 'greenbridget@example.net',
    'phone_number': '434.221.4574x411',
    'json': {
    'name': 'Amy Medina',
    'address': '621 Ferguson Trail Suite 077\nCantrellmouth, KY 24243',
},
    'key10716': 'value99454',
    'key17823': 'value19490',
    'key73295': 'value43607',
    'key62309': 'value68662',
    'key57560': 'value85052',
},
    {
    'id': 17527489159400,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'George Patterson',
    'address': '6385 Jeremy Pike\nJuliefort, OR 33957',
    'text': 'South paper magazine may important smile. Such play determine news back guy would. Compare set right both available onto.\nCell owner around debate treatment last realize. Sell player system consumer.',
    'email': 'vanessamiller@example.com',
    'phone_number': '303-382-3499x28443',
    'json': {
    'name': 'Peter Singh',
    'address': '03167 Jose Causeway Suite 545\nReyesmouth, FM 17617',
},
    'key48056': 'value71215',
    'key16723': 'value53764',
    'key27783': 'value85882',
    'key44214': 'value36744',
    'key38499': 'value88405',
    'key83884': 'value87246',
    'key3274': 'value67687',
},
    {
    'id': 17527489159411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Joseph Stewart',
    'address': '2873 Wood Junctions Suite 353\nJessicabury, IA 56911',
    'text': 'Material work level enough between interview.\nSummer thousand recent late easy challenge catch. Southern than company century away find.',
    'email': 'armstrongderrick@example.com',
    'phone_number': '356.761.2197x1706',
    'json': {
    'name': 'Madison Young',
    'address': '63729 Kathleen Neck Apt. 194\nJenniferburgh, AS 91083',
},
    'key74003': 'value64628',
    'key73105': 'value36605',
    'key1790': 'value6531',
    'key83828': 'value86363',
    'key88311': 'value75484',
    'key25952': 'value35987',
    'key72796': 'value17926',
},
    {
    'id': 17527489159423,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Aaron Blackburn',
    'address': '715 Adams Brook\nSouth Vickieport, FL 22152',
    'text': 'Paper main girl court example approach cost. Institution room enter data best prepare many.\nDiscussion find tonight lay see TV exist hotel. Cultural on group day training.',
    'email': 'nnolan@example.com',
    'phone_number': '(650)259-0994',
    'json': {
    'name': 'Candice Jensen',
    'address': '30485 Long Trafficway\nHansonhaven, NH 59457',
},
    'key54860': 'value6941',
    'key2478': 'value53121',
    'key69064': 'value83484',
    'key50504': 'value58728',
    'key30783': 'value77916',
    'key90819': 'value88130',
},
    {
    'id': 17527489159434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Toni Rogers',
    'address': '652 Johnson Harbors Apt. 056\nClairestad, SC 58307',
    'text': 'Ball property fear why head require. Father rate may speech not successful.\nTruth she main. Travel let water well which. Data continue boy. Central five establish beat wind phone.',
    'email': 'amy36@example.org',
    'phone_number': '(663)358-6633',
    'json': {
    'name': 'Lisa Bentley',
    'address': '57529 Roy Parkway Suite 626\nTaylorburgh, GA 45971',
},
    'key83317': 'value17591',
    'key16416': 'value68176',
    'key84791': 'value58338',
    'key38738': 'value27413',
    'key20633': 'value57137',
    'key10760': 'value6437',
    'key1848': 'value25109',
    'key41482': 'value49541',
},
    {
    'id': 17527489159445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Joel Sutton',
    'address': '78348 Mary Island\nTrujilloburgh, IA 92317',
    'text': 'Mind prove administration popular floor. Billion as somebody against us official. Real several arm old national institution. Letter remain allow even record.',
    'email': 'hmcintosh@example.net',
    'phone_number': '(280)258-7214x16585',
    'json': {
    'name': 'Adam Snyder',
    'address': '214 Sims Meadows\nHillport, ID 53212',
},
    'key91434': 'value20419',
    'key84978': 'value99190',
    'key83043': 'value9123',
    'key93063': 'value34694',
    'key63273': 'value36990',
},
    {
    'id': 17527489159456,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Brittany Allen',
    'address': 'PSC 5608, Box 6287\nAPO AA 95529',
    'text': 'Style hard card at others across foreign listen. Person strategy wife home.',
    'email': 'angela94@example.org',
    'phone_number': '+1-297-648-3470',
    'json': {
    'name': 'Christopher Strickland',
    'address': 'USCGC Rodgers\nFPO AE 16620',
},
    'key96311': 'value76791',
    'key66241': 'value75074',
    'key50641': 'value93893',
    'key92404': 'value85069',
    'key6634': 'value13367',
},
    {
    'id': 17527489159464,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Laura Jones',
    'address': '57325 Michael Overpass\nShannonborough, AK 83084',
    'text': 'Part black Republican forget join range. Condition enough public office.\nAt matter management what region more book.\nBeat expect among who yourself investment all. Friend take group word.',
    'email': 'chad98@example.com',
    'phone_number': '689-905-1355x2519',
    'json': {
    'name': 'Charles Glover',
    'address': '757 Thomas Crest Suite 871\nRobinsonfurt, AL 50550',
},
    'key7493': 'value65069',
    'key90736': 'value92371',
    'key87931': 'value66408',
    'key27099': 'value13227',
    'key27169': 'value65286',
    'key57663': 'value69566',
    'key96046': 'value66510',
    'key13636': 'value31096',
},
    {
    'id': 17527489159474,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Ms. Tara Munoz',
    'address': 'Unit 3547 Box 4490\nDPO AE 94072',
    'text': 'Sport yeah election memory now decide federal.\nFear plan exactly such. Himself pull common its bill hold meet outside. Simple somebody suddenly financial despite line.',
    'email': 'erik69@example.com',
    'phone_number': '518-874-9588x7688',
    'json': {
    'name': 'Michele Wilson',
    'address': '189 Robinson Walk Suite 895\nWest Maryborough, RI 09794',
},
    'key22603': 'value45048',
    'key45144': 'value45819',
    'key50455': 'value2174',
    'key63319': 'value25682',
},
    {
    'id': 17527489159483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Kenneth Pope',
    'address': 'Unit 2118 Box 2845\nDPO AE 04123',
    'text': 'Local rate piece leave his name hot. Board eight become tend. Send lay enjoy treat.\nShe Republican everything into nation. Knowledge leg couple consider. Benefit indicate speak happy.',
    'email': 'joshuamoore@example.com',
    'phone_number': '997.979.3029x9564',
    'json': {
    'name': 'Lynn Armstrong',
    'address': 'USCGC Ramirez\nFPO AP 69916',
},
    'key55309': 'value59191',
    'key94549': 'value1595',
    'key90639': 'value45053',
    'key97894': 'value23456',
    'key85454': 'value30462',
    'key61331': 'value42361',
    'key15758': 'value96189',
    'key40255': 'value78252',
},
    {
    'id': 17527489159492,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Antonio King',
    'address': '7796 Jacqueline Street\nBakerchester, SD 80184',
    'text': 'Happy couple tend movie almost various raise already. Teach someone recognize suggest husband control side.',
    'email': 'martinezalex@example.org',
    'phone_number': '7536380069',
    'json': {
    'name': 'Francisco Fleming',
    'address': '31273 Weiss Land\nRaymondburgh, CT 44656',
},
    'key64344': 'value50464',
    'key68261': 'value26859',
    'key50735': 'value44270',
    'key81633': 'value8662',
    'key34152': 'value68013',
    'key13292': 'value81829',
},
    {
    'id': 17527489159503,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Angelica Hamilton',
    'address': '1098 Brianna Summit Suite 093\nEast Keith, AK 61997',
    'text': 'Style film staff general. Position stock start argue enjoy. Generation which man century third prevent ability.',
    'email': 'ruthdavis@example.net',
    'phone_number': '560-922-0417x9635',
    'json': {
    'name': 'Mr. Stephen Guerra',
    'address': '792 Marks Loaf Suite 873\nSamuelhaven, NH 02356',
},
    'key85047': 'value24560',
    'key58179': 'value81892',
},
    {
    'id': 17527489159515,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Tyler Romero',
    'address': '09513 Caldwell Ridges Suite 251\nHollymouth, WA 34784',
    'text': 'Ground more relationship system organization face.\nTable report decision have get actually weight. Hear the history girl begin change any. Professional strong their painting identify outside my more.',
    'email': 'tjohnson@example.com',
    'phone_number': '+1-845-475-1739',
    'json': {
    'name': 'Courtney Dean',
    'address': '6975 Rose Causeway\nMoonburgh, MT 11708',
},
    'key55122': 'value1857',
    'key82598': 'value90427',
    'key46927': 'value59426',
    'key84473': 'value20664',
    'key69463': 'value31997',
    'key23519': 'value46412',
    'key51161': 'value72355',
    'key59967': 'value38596',
    'key42102': 'value76290',
    'key27674': 'value25088',
},
    {
    'id': 17527489159526,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Lisa Johnson',
    'address': '96889 Christina Rapids Apt. 921\nPort Erica, AZ 81134',
    'text': 'Stock market during leg. Majority trade be nothing treat.\nMission society ground public. Difference manage music increase above interesting.',
    'email': 'fburke@example.com',
    'phone_number': '001-849-566-7806',
    'json': {
    'name': 'Jenna Nelson DVM',
    'address': '2695 Mathews Loaf\nWest Jessica, CO 04796',
},
    'key43505': 'value10128',
    'key82246': 'value72108',
    'key45984': 'value33308',
    'key67362': 'value47573',
    'key85259': 'value43070',
    'key55040': 'value27353',
    'key64452': 'value83422',
    'key80931': 'value76635',
    'key60534': 'value27005',
    'key41060': 'value83929',
},
    {
    'id': 17527489159537,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Tonya King',
    'address': '626 Kathryn Track Suite 680\nLake Paul, ME 49984',
    'text': 'Phone game attention economy. Trouble fund world close can executive still.',
    'email': 'carolmitchell@example.org',
    'phone_number': '+1-825-841-8042x740',
    'json': {
    'name': 'Erin Hernandez',
    'address': '5123 Richard Wall\nSouth Rebeccaside, MA 09938',
},
    'key65328': 'value47155',
},
    {
    'id': 17527489159549,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Elizabeth Mcclure',
    'address': '6351 Rebecca Views\nEast Hannahstad, WY 71816',
    'text': 'Rather area but forward. Society point foot have range interest.',
    'email': 'tarawilliams@example.org',
    'phone_number': '+1-334-893-2389x1965',
    'json': {
    'name': 'Stephanie Hobbs',
    'address': '81970 Avila Valley Apt. 202\nFitzgeraldport, NM 27581',
},
    'key28179': 'value82148',
    'key46838': 'value45866',
    'key97689': 'value11482',
    'key75182': 'value88132',
    'key48122': 'value50407',
    'key10573': 'value78025',
    'key18177': 'value30790',
    'key88061': 'value58577',
    'key7252': 'value39495',
},
    {
    'id': 17527489159560,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Joseph Pham',
    'address': '754 Charles Fall Suite 744\nRobinbury, NH 57587',
    'text': 'East performance think high half hair bring. Over reality sport lose debate hour. Have level traditional reveal institution.\nCourt thing either address its special third.',
    'email': 'rturner@example.net',
    'phone_number': '(377)857-6975x21519',
    'json': {
    'name': 'Donald Lindsey',
    'address': '024 Calvin Avenue Apt. 149\nTimothyview, DE 10722',
},
    'key71232': 'value375',
    'key46998': 'value25964',
},
    {
    'id': 17527489159571,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Angela Gonzales',
    'address': '008 Collins Freeway\nJasonberg, MN 65605',
    'text': 'Play space goal use model. Certainly school remain huge.\nYou scientist life figure line by indeed. Above effect land worker until. Eye spring rest hour.',
    'email': 'ashleegeorge@example.net',
    'phone_number': '+1-420-898-1469x99933',
    'json': {
    'name': 'Patricia Parker',
    'address': '329 Barton Roads Apt. 075\nNorth Davidbury, OK 41445',
},
    'key1166': 'value49505',
    'key11944': 'value86946',
    'key22780': 'value75828',
},
    {
    'id': 17527489159583,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Angela Stafford',
    'address': '65563 Rebecca Neck\nPenningtonville, DE 31844',
    'text': 'Off scene camera avoid especially safe. Know country Mr nice happen. Institution record play rise mind wait world.\nAmong reflect language fear music benefit scientist. Top policy wide answer.',
    'email': 'mmiller@example.com',
    'phone_number': '643-304-1213',
    'json': {
    'name': 'Susan Russell',
    'address': '60572 Suzanne Branch\nSchroederfort, MA 25437',
},
    'key75217': 'value98640',
    'key71002': 'value40844',
},
    {
    'id': 17527489159595,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Timothy Fisher',
    'address': '986 Colon Knoll Suite 353\nKochshire, NM 26077',
    'text': 'Speech choose success third.\nFilm five oil population field matter. Grow culture mother seem culture.\nConsider course notice end moment set fish. Day month brother laugh affect later according.',
    'email': 'williamsjohn@example.net',
    'phone_number': '549.753.9389x19488',
    'json': {
    'name': 'Jason Banks',
    'address': '56240 Eric Mount\nWisefurt, OH 01922',
},
    'key70347': 'value32548',
    'key20603': 'value6399',
    'key64339': 'value7415',
},
    {
    'id': 17527489159608,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'William Rice',
    'address': '66306 Day Parkway\nPearsonborough, VA 80970',
    'text': 'West claim work city various.\nLanguage challenge create. Much here local attorney. Decide prevent major current.',
    'email': 'regina43@example.org',
    'phone_number': '001-900-460-6606x125',
    'json': {
    'name': 'Charles Miller',
    'address': '5399 David Neck Apt. 003\nEast Christopherberg, IN 81263',
},
    'key54850': 'value19141',
    'key44208': 'value52654',
    'key17694': 'value21841',
    'key94416': 'value72225',
    'key32934': 'value71273',
    'key51303': 'value23049',
    'key97583': 'value56002',
},
    {
    'id': 17527489159620,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Margaret Davis',
    'address': '299 Amber Circle\nJonesfurt, ND 76655',
    'text': 'Upon son base far stage manager. Ten worry explain same send between memory. Grow so clearly item always of resource kitchen.',
    'email': 'cdavidson@example.com',
    'phone_number': '860-870-5105x736',
    'json': {
    'name': 'William Mcdonald',
    'address': 'PSC 1150, Box 8387\nAPO AE 50753',
},
    'key54384': 'value78280',
    'key3885': 'value43464',
    'key45997': 'value9477',
    'key27293': 'value83499',
    'key40605': 'value90641',
    'key47006': 'value12990',
    'key71591': 'value18707',
},
    {
    'id': 17527489159630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Ruth Pierce',
    'address': 'PSC 9410, Box 4816\nAPO AA 73742',
    'text': 'Teach listen second couple commercial strong wait deep. Foot family and only major trial several weight.',
    'email': 'amy69@example.com',
    'phone_number': '368-504-5666x2961',
    'json': {
    'name': 'Rebecca Perry',
    'address': '52990 Christine Ranch\nCunninghamborough, WI 20715',
},
    'key55181': 'value24640',
    'key51357': 'value21479',
    'key53179': 'value32081',
    'key94606': 'value47234',
    'key73341': 'value66227',
    'key47313': 'value61178',
    'key27327': 'value63738',
    'key48911': 'value49654',
},
    {
    'id': 17527489159640,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Cheryl Nash',
    'address': '494 Jeremy Roads Apt. 337\nBoydstad, NM 91025',
    'text': 'Last sure sign none us of learn change. Enough will face development. Response middle sell degree management enter. Population rule trial decade product article.',
    'email': 'laurie60@example.net',
    'phone_number': '(740)359-7246x3459',
    'json': {
    'name': 'Kristin Fuller',
    'address': '41043 Toni Light\nNorth Christopher, IL 43362',
},
    'key14346': 'value48948',
    'key32541': 'value8043',
    'key58320': 'value15611',
    'key58558': 'value14315',
    'key28133': 'value87476',
},
    {
    'id': 17527489159651,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'John Walters',
    'address': '03274 Mann Harbors Suite 388\nLake Lauren, VI 36969',
    'text': 'Pay phone most though. Southern case push forget drug one worry.\nSafe score tend begin majority thought idea.\nSister letter company soldier history surface.',
    'email': 'alyssasalazar@example.net',
    'phone_number': '326.362.3480x201',
    'json': {
    'name': 'Natasha Finley',
    'address': '7253 Denise Via Apt. 963\nNorth Brandon, NY 94271',
},
    'key27413': 'value61933',
    'key68624': 'value7166',
    'key13675': 'value6253',
    'key68668': 'value65564',
    'key17401': 'value51953',
    'key85295': 'value86856',
    'key11241': 'value75634',
    'key95939': 'value85333',
},
    {
    'id': 17527489159664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Michele Soto',
    'address': '7881 Johnson Lights\nNew Tonyview, FM 93967',
    'text': 'Any eye treat tend. Free fly tonight Congress third. Drive project card level.\nAround these firm television building. Might training event couple close model go drug.',
    'email': 'michaelmullins@example.org',
    'phone_number': '(650)275-3447',
    'json': {
    'name': 'Thomas Davis',
    'address': 'Unit 4414 Box 8564\nDPO AE 14610',
},
    'key69715': 'value62978',
    'key12777': 'value28298',
    'key12488': 'value24817',
    'key97046': 'value4997',
    'key56655': 'value67752',
    'key29930': 'value18409',
    'key3041': 'value50038',
    'key89599': 'value35569',
    'key85931': 'value81991',
},
    {
    'id': 17527489159674,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Justin Nunez',
    'address': '7298 Foster Turnpike\nSamanthafort, KS 40869',
    'text': 'Fight home few move region. Your strong no couple order. Attorney enjoy certain.\nSound decade thought appear bad yes. Director school suddenly the property born. Gun hour kitchen.',
    'email': 'daniel94@example.net',
    'phone_number': '+1-584-291-6767x859',
    'json': {
    'name': 'Dr. Stacy Wade MD',
    'address': '9824 Tracy Dale Suite 105\nThompsonmouth, UT 28775',
},
    'key17233': 'value93697',
    'key16342': 'value64722',
},
    {
    'id': 17527489159684,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Susan Harrington',
    'address': '3099 Stacey Station Suite 643\nKingborough, NY 15664',
    'text': 'Experience money receive production old particular. Follow fight rather near bring different write.\nMiss indicate learn goal cut five. Charge state direction anything two society perhaps.',
    'email': 'christine05@example.com',
    'phone_number': '(444)268-5980x38841',
    'json': {
    'name': 'Ashlee Morton',
    'address': '72449 Garcia Villages Apt. 415\nSouth Shellyland, CT 66937',
},
    'key32329': 'value68807',
},
    {
    'id': 17527489159695,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Michael Hutchinson',
    'address': '389 Steele Squares\nNew Marcus, HI 55000',
    'text': 'Offer prevent college possible partner. Again finally size nor throughout song century trade. Local win nation street generation rule ago.\nAttack hotel true. Skin key local by.',
    'email': 'adamhoward@example.com',
    'phone_number': '608-502-8185',
    'json': {
    'name': 'Brittney Richardson',
    'address': '99779 Williams Loaf Apt. 178\nEast Sandra, MS 46484',
},
    'key63000': 'value4880',
    'key58454': 'value8585',
    'key10179': 'value10049',
    'key2104': 'value46476',
    'key8013': 'value52927',
    'key9855': 'value40606',
},
    {
    'id': 17527489159706,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Linda Flores',
    'address': '6222 Dunn Center\nGreeneborough, NV 05007',
    'text': 'Court message sister theory. Candidate ground catch he clear lose create lay.\nDetermine individual remember source seek term. Than page local easy eight.',
    'email': 'wrightkathryn@example.com',
    'phone_number': '(422)940-1731',
    'json': {
    'name': 'Joseph Lara',
    'address': '670 Jason Way Apt. 402\nMitchellhaven, TX 29057',
},
    'key74575': 'value78490',
    'key23647': 'value21591',
    'key58846': 'value1436',
    'key2019': 'value64767',
    'key49681': 'value61711',
    'key35608': 'value97507',
    'key68174': 'value76932',
},
    {
    'id': 17527489159718,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Alexandra Holloway',
    'address': '90063 Melissa Plaza Suite 531\nNew Debbiehaven, MS 27224',
    'text': 'Game hot between law show. Ok reality way authority agreement partner.\nManager old current international feel. Return wall use consider own dark be.\nCare mean go house big.\nAll seem foot.',
    'email': 'amy84@example.com',
    'phone_number': '897.651.7916x437',
    'json': {
    'name': 'Carolyn Wilson',
    'address': '8674 Morris Oval\nNorth Leonard, UT 68992',
},
    'key53987': 'value48092',
    'key38922': 'value78601',
    'key70255': 'value19906',
    'key16088': 'value31907',
    'key59043': 'value96809',
    'key67394': 'value40858',
    'key33997': 'value87154',
},
    {
    'id': 17527489159729,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Heather Jones',
    'address': '5850 Leslie Shoals Apt. 370\nSouth Jennifermouth, TN 44954',
    'text': 'Home management agreement. Newspaper color study speak work. Deal couple could.\nArea clearly water threat anything. Rest media two down lay. Win may media major have area.',
    'email': 'timothyhodge@example.net',
    'phone_number': '+1-840-923-6449x551',
    'json': {
    'name': 'Caroline Hawkins',
    'address': 'USS Robinson\nFPO AE 66186',
},
    'key33629': 'value37805',
    'key70188': 'value78503',
    'key958': 'value54857',
    'key95731': 'value19514',
    'key14797': 'value73743',
},
    {
    'id': 17527489159740,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Laura Stark',
    'address': '80304 Thomas Wall Suite 357\nDesireehaven, VA 30610',
    'text': 'Page father threat change. Brother report no food itself out trip. Woman sort bag star specific huge door. White fast really letter system charge foot.',
    'email': 'ggreer@example.org',
    'phone_number': '756-858-4430x28320',
    'json': {
    'name': 'Pamela Franklin',
    'address': '9551 Anna Keys\nLake Scott, NJ 58473',
},
    'key69215': 'value4870',
    'key67860': 'value63959',
    'key59803': 'value51356',
    'key22404': 'value38006',
    'key21070': 'value68857',
    'key43849': 'value98694',
},
    {
    'id': 17527489159750,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Mary Tran',
    'address': '32597 Singleton Summit\nCarlsonborough, GU 52782',
    'text': 'Experience sister cup indicate. People how eight establish town possible.\nCatch until among toward Republican force. They without at sing child prepare. Answer local day home commercial couple.',
    'email': 'gtucker@example.com',
    'phone_number': '669-277-5761',
    'json': {
    'name': 'Allison Reyes',
    'address': '2565 Evans Port\nRyanhaven, AR 16452',
},
    'key9326': 'value71919',
    'key97644': 'value44285',
    'key716': 'value86464',
    'key53297': 'value92151',
    'key79897': 'value83982',
    'key75431': 'value86748',
    'key84330': 'value66108',
    'key45008': 'value97815',
},
    {
    'id': 17527489159762,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Joshua Jones',
    'address': '9637 Margaret Ford Suite 665\nBradyborough, OK 32865',
    'text': 'Medical discuss room wife clearly. Grow worker move role. Marriage east history front serious.',
    'email': 'sarah24@example.net',
    'phone_number': '(548)716-7554',
    'json': {
    'name': 'Laura Clark',
    'address': 'PSC 3921, Box 0337\nAPO AP 79601',
},
    'key42152': 'value26550',
    'key7625': 'value68238',
},
    {
    'id': 17527489159770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Jamie Rodriguez',
    'address': '08627 Robert Isle\nNew Staceyfort, VA 38541',
    'text': 'Good from investment story left write. Apply you prepare final break hand everyone. Popular parent your who.\nAt pretty break include theory run garden. Sort only again his agreement compare natural.',
    'email': 'christophersmith@example.com',
    'phone_number': '001-674-876-4964x8753',
    'json': {
    'name': 'Joshua Malone',
    'address': '26600 Martin Inlet Apt. 409\nEast Christianbury, CT 77556',
},
    'key82658': 'value61905',
    'key21550': 'value71293',
    'key42715': 'value30261',
    'key55480': 'value62314',
    'key50502': 'value81267',
    'key5207': 'value27688',
    'key6170': 'value44312',
    'key78223': 'value97623',
},
    {
    'id': 17527489159782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Patricia Bell',
    'address': '13981 Logan Ridge\nPort Ethanville, GU 50856',
    'text': 'Morning worry middle one. Discuss activity include well.\nLikely site evening wrong buy agree. Commercial series laugh bit.',
    'email': 'qshelton@example.net',
    'phone_number': '(354)214-5148x01955',
    'json': {
    'name': 'Adam Larson',
    'address': 'PSC 5514, Box 9278\nAPO AE 12245',
},
    'key1269': 'value55434',
    'key78913': 'value71033',
    'key66242': 'value60014',
    'key1586': 'value43259',
    'key7686': 'value99238',
    'key73528': 'value36149',
    'key47298': 'value6448',
    'key92715': 'value64004',
},
    {
    'id': 17527489159791,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Ronald Perry',
    'address': '022 Chang Bridge\nWest Timothyfort, SD 53937',
    'text': 'Sell tonight finally late. Bed four place space political. Manage film Mr individual field step claim.',
    'email': 'hughesdylan@example.com',
    'phone_number': '001-354-928-4489x0309',
    'json': {
    'name': 'Taylor Stewart',
    'address': '03965 Sherry Fork Apt. 485\nPort John, OK 11491',
},
    'key23748': 'value61879',
    'key83671': 'value91410',
    'key6532': 'value78383',
    'key43127': 'value93651',
    'key83367': 'value61695',
    'key63608': 'value49017',
    'key74994': 'value17673',
    'key10399': 'value2289',
    'key60555': 'value15030',
    'key29946': 'value69596',
},
    {
    'id': 17527489159802,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Kevin Johnson',
    'address': '0030 Cohen Extensions\nSouth Elizabeth, TX 01065',
    'text': 'Our budget town place tax. Writer benefit water produce speech.\nRun office course affect billion his common. Be share its land. We phone then return tend mission.',
    'email': 'lfowler@example.net',
    'phone_number': '(207)404-4468x8523',
    'json': {
    'name': 'Bobby Compton',
    'address': '818 Hanson Turnpike Suite 588\nKennethchester, FL 25375',
},
    'key12145': 'value59383',
    'key72536': 'value56498',
    'key37183': 'value4988',
},
    {
    'id': 17527489159813,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Crystal Mcdaniel',
    'address': '530 Diana Terrace Apt. 875\nKaylaville, PA 41552',
    'text': 'Magazine memory subject career draw. Other east another season teacher age. Challenge long score against during decade line lose.',
    'email': 'pbishop@example.net',
    'phone_number': '001-911-574-3205x8465',
    'json': {
    'name': 'Jennifer Schmidt',
    'address': '3965 Julie Plain Suite 945\nWilsonland, DC 54342',
},
    'key92665': 'value15036',
    'key21657': 'value13759',
    'key45021': 'value8225',
    'key22546': 'value50674',
    'key75768': 'value5588',
    'key90895': 'value43200',
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
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_49_836473TLlZRmWI',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
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
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_49_836473TLlZRmWI',
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
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_49_836473TLlZRmWI',
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
    'RequestId': 'a503b796-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_49_836473TLlZRmWI',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 01]_1752748924.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid011752748924Json()
    test.run_tests()
