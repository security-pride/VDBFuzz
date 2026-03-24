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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_simple_payload[IP]_1752747996_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[IP]_1752747996.json"
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithSimplePayloadIp1752747996Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[IP]_1752747996.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[IP]_1752747996.json"
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
    'RequestId': '8039acd8-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_29_121919PjphZfXB',
    'dimension': 128,
    'metricType': 'IP',
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
    'RequestId': '8039acd8-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_29_121919PjphZfXB',
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
    'RequestId': '8039acd8-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_29_121919PjphZfXB',
    'data': [
    {
    'id': 17527479951596,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Robert Brown',
    'address': '9115 Mary Course\nBradleyburgh, PW 47944',
    'text': 'Enough blood idea design. Guy time song would international attack. East then generation day.',
    'email': 'iweaver@example.net',
    'phone_number': '(235)464-8620',
    'json': {
    'name': 'David Scott',
    'address': '24216 Proctor Village\nBakerburgh, ME 34449',
},
    'key89847': 'value9529',
    'key79777': 'value62702',
    'key12268': 'value93668',
},
    {
    'id': 17527479951634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Michael Carlson',
    'address': '511 Andre Rest Suite 186\nWest Jeremyside, AR 77024',
    'text': 'Win put shake down. Close prevent least glass.\nCarry open difference must sport call design. People blue create between fight. Majority both country position know method.',
    'email': 'barbarawilliams@example.org',
    'phone_number': '001-803-788-0568x18379',
    'json': {
    'name': 'Laura Steele',
    'address': '429 Garcia Green\nNew Dennisbury, MA 64342',
},
    'key42665': 'value6751',
    'key96013': 'value44618',
    'key46398': 'value74098',
},
    {
    'id': 17527479951649,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jordan Moody',
    'address': '010 Joshua Forest\nNorth Kylehaven, MI 32184',
    'text': 'Prevent claim develop forward.\nMaybe open carry quickly. Amount service enough anyone ball fact prove method.',
    'email': 'reginasosa@example.com',
    'phone_number': '967-637-0236x8784',
    'json': {
    'name': 'Benjamin Mccarty',
    'address': '6582 Thomas Viaduct\nHarrisfurt, VI 56886',
},
    'key91204': 'value83040',
    'key68138': 'value28429',
    'key20805': 'value4339',
},
    {
    'id': 17527479951663,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Anthony Briggs',
    'address': '012 Chen Parkways\nWest Jacqueline, PA 56474',
    'text': 'Mr suddenly recognize maybe pull meeting however design. Friend station protect do never develop maybe.',
    'email': 'bentleykatie@example.org',
    'phone_number': '321.664.3414x895',
    'json': {
    'name': 'Edward Molina',
    'address': '27527 Luke Drive\nDanielmouth, FL 83305',
},
    'key31702': 'value45456',
    'key7585': 'value53129',
    'key70383': 'value78700',
    'key15364': 'value10108',
    'key85022': 'value91814',
    'key88162': 'value96045',
},
    {
    'id': 17527479951676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'William Mckay',
    'address': '85144 Dakota Islands\nNew Karenfort, IA 61323',
    'text': 'Skill national fine administration. Bag develop energy sister bed Democrat military. Local sister likely answer attorney.',
    'email': 'spencerbolton@example.net',
    'phone_number': '701.364.5320x48707',
    'json': {
    'name': 'Michael Romero',
    'address': '0923 Whitney Manor Apt. 941\nMartinhaven, MO 14655',
},
    'key16415': 'value20146',
    'key13250': 'value4904',
    'key15386': 'value95479',
    'key45064': 'value77983',
},
    {
    'id': 17527479951690,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Stephanie Thomas',
    'address': '497 Walker Row Suite 066\nLake Matthew, ND 18331',
    'text': 'Head song pattern major. May church everybody material fly. Couple increase medical source majority.\nRun doctor protect mother report. Film difficult bad look short. Live former pressure compare.',
    'email': 'bianca80@example.com',
    'phone_number': '728-470-1333x9456',
    'json': {
    'name': 'Shawn Griffith',
    'address': '8426 Simmons Stravenue\nKarabury, GU 13754',
},
    'key32693': 'value93662',
    'key59288': 'value32666',
    'key95769': 'value32283',
    'key88816': 'value80314',
    'key75916': 'value40639',
    'key75235': 'value57062',
    'key7064': 'value39691',
    'key94948': 'value39575',
},
    {
    'id': 17527479951703,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Dorothy Jones',
    'address': '30781 Jones Circles Apt. 226\nTinafurt, TX 19245',
    'text': 'Carry visit rate radio talk leave. Every six those eye our.\nMission country key mother where more half. Many ask military necessary summer yourself. She out only government.',
    'email': 'ashley18@example.com',
    'phone_number': '847.739.4298x09049',
    'json': {
    'name': 'Kelli Martin',
    'address': '4970 Alexandra Meadows Apt. 064\nWilliamsview, RI 36817',
},
    'key54708': 'value83686',
    'key28081': 'value92762',
    'key81482': 'value84665',
    'key37982': 'value42189',
    'key84207': 'value3019',
    'key48504': 'value65720',
    'key53055': 'value8386',
    'key77836': 'value90551',
    'key12712': 'value97944',
    'key550': 'value89661',
},
    {
    'id': 17527479951716,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Melissa Taylor',
    'address': '7614 Wendy Fall\nDeleonland, PR 91198',
    'text': 'Conference identify bring exist production few. Watch past major hotel reach green base.\nStatement foreign wait trade ahead. Sell business father sense.',
    'email': 'brandon81@example.org',
    'phone_number': '001-654-701-4963',
    'json': {
    'name': 'Nichole Harvey',
    'address': '67906 Theresa Springs\nNicolehaven, NM 58394',
},
    'key37057': 'value53569',
    'key78106': 'value81231',
    'key88952': 'value53210',
},
    {
    'id': 17527479951727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Deanna Little',
    'address': 'PSC 9346, Box 0608\nAPO AA 32000',
    'text': 'Pressure century likely. Game thus own reason under bring fast.\nToward defense its free. Language out Mr risk television process. President east father wish which hold buy.',
    'email': 'veronica08@example.net',
    'phone_number': '001-273-461-3099',
    'json': {
    'name': 'Robert Adams',
    'address': '166 Julia Brook Apt. 180\nBurnshaven, OR 75268',
},
    'key5141': 'value88466',
    'key14835': 'value65783',
    'key41223': 'value79639',
    'key8645': 'value6770',
    'key75646': 'value21630',
    'key14618': 'value18131',
    'key1617': 'value63469',
    'key72169': 'value63890',
},
    {
    'id': 17527479951737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Laura Tanner',
    'address': '9159 Alex Key Apt. 218\nEast Audrey, MI 43962',
    'text': 'Painting center short Congress painting. Standard commercial truth name safe in. Democratic manager group expect school wind Mrs. Hotel worry wonder.\nSupport certain quickly very or prepare.',
    'email': 'davidallen@example.com',
    'phone_number': '(683)809-0650x52965',
    'json': {
    'name': 'Michael Wilkinson',
    'address': '6630 Lane Via Suite 502\nFernandezport, KS 69544',
},
    'key940': 'value77125',
    'key51663': 'value13647',
    'key80777': 'value4828',
    'key1986': 'value59871',
    'key53269': 'value85584',
    'key9381': 'value33223',
    'key56225': 'value69962',
    'key9641': 'value23670',
    'key41655': 'value420',
    'key49192': 'value57635',
},
    {
    'id': 17527479951750,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Megan Wagner',
    'address': '72435 Amber Freeway Suite 711\nSmithburgh, GA 45694',
    'text': 'Employee change evidence away. Onto care year present.\nOff behind tree to six affect. Especially fight today science business.',
    'email': 'elizabeth46@example.org',
    'phone_number': '834.307.6233x27320',
    'json': {
    'name': 'Michael Price',
    'address': '929 Robert Parkways Suite 492\nLopezfort, MA 71820',
},
    'key98702': 'value7393',
},
    {
    'id': 17527479951762,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Eric Adams',
    'address': '169 Bryan Islands\nPort Christian, KY 94310',
    'text': 'Among after dog onto similar improve break. Race oil successful focus also resource should. Phone member husband prevent simply college piece traditional.',
    'email': 'christinamitchell@example.com',
    'phone_number': '835.591.8089x4570',
    'json': {
    'name': 'Daniel Christensen',
    'address': '41879 Collins Street\nMartinezside, SC 56531',
},
    'key66344': 'value81671',
    'key67374': 'value44942',
    'key83411': 'value71448',
    'key72196': 'value6292',
    'key31591': 'value75386',
    'key43806': 'value57695',
    'key17486': 'value81426',
    'key79533': 'value4432',
},
    {
    'id': 17527479951775,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Judy Murphy',
    'address': 'USCGC Johnson\nFPO AA 01828',
    'text': 'Available nor purpose toward half detail. Site from machine less north name relationship pick.',
    'email': 'oboyd@example.net',
    'phone_number': '761.379.1339',
    'json': {
    'name': 'Scott Villa',
    'address': '280 Robin Inlet Suite 806\nAnnetteborough, NM 82203',
},
    'key54080': 'value17895',
    'key96349': 'value88161',
    'key40438': 'value89692',
    'key5134': 'value10944',
    'key85962': 'value37197',
    'key9298': 'value91501',
    'key6702': 'value24353',
    'key43961': 'value75657',
    'key16492': 'value18967',
    'key77246': 'value15385',
},
    {
    'id': 17527479951785,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Bridget Velasquez',
    'address': 'Unit 0010 Box 3987\nDPO AE 78600',
    'text': 'Everything quality list reveal option. Air animal describe site nor. Morning military follow writer arrive.\nStay own build after which. Gun media or customer player camera.',
    'email': 'vincentphillips@example.org',
    'phone_number': '642-245-5416x33245',
    'json': {
    'name': 'Thomas Castillo',
    'address': '5359 Smith Underpass\nNorth Zacharyfurt, PA 81888',
},
    'key15373': 'value11836',
    'key65997': 'value91062',
    'key59750': 'value86678',
    'key43086': 'value29319',
    'key15866': 'value36904',
},
    {
    'id': 17527479951797,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jennifer Murray',
    'address': '58188 Peter Hills\nMarcostad, WV 25515',
    'text': 'Crime rate lead front. Sell site truth wonder attention law decision together. Determine industry mouth discuss get character. Tax health court trade population meeting.',
    'email': 'mayjames@example.net',
    'phone_number': '738-577-7087',
    'json': {
    'name': 'Michele Massey',
    'address': '61206 Hoover Oval Suite 310\nLake Daniel, LA 34231',
},
    'key76070': 'value30834',
    'key32474': 'value47146',
    'key96084': 'value66920',
},
    {
    'id': 17527479951809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Christopher Rodriguez',
    'address': '8127 Vanessa Pike\nCalvinport, ME 42365',
    'text': 'Action make standard. Apply include woman property training. Including country factor election attention fund.',
    'email': 'whitejacqueline@example.org',
    'phone_number': '(790)282-5693x515',
    'json': {
    'name': 'Randy Marshall',
    'address': '1018 Jody Rapid Suite 381\nCantuport, OH 83373',
},
    'key7527': 'value97523',
},
    {
    'id': 17527479951821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Timothy Lang',
    'address': '7144 Mcintyre Pike Apt. 549\nNew Kimberlymouth, WI 86726',
    'text': 'Method hit manage take detail ability college. Center want detail become large plant state. Tend direction public choose.',
    'email': 'thomas92@example.com',
    'phone_number': '+1-271-851-6614x3552',
    'json': {
    'name': 'Phillip Garcia',
    'address': '52628 Jones Keys Apt. 145\nEricside, HI 26153',
},
    'key4802': 'value53233',
    'key1493': 'value10784',
},
    {
    'id': 17527479951832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'James Kim',
    'address': '641 Kenneth Crest\nSouth Anthony, UT 76730',
    'text': 'Price tree turn share. Partner there skill us bill thousand place firm. However car public develop economy law. Owner near into successful.',
    'email': 'smithtammy@example.com',
    'phone_number': '001-692-226-2490',
    'json': {
    'name': 'Rebecca Hill',
    'address': '17887 Derek Island\nPort Ivan, VA 58095',
},
    'key50151': 'value80181',
},
    {
    'id': 17527479951844,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Laurie Garcia',
    'address': '27453 Stacey Fall\nJeffreymouth, NE 97249',
    'text': 'Reach skin production moment group. Five suddenly organization page provide maintain.',
    'email': 'zmaddox@example.com',
    'phone_number': '6345221064',
    'json': {
    'name': 'Dylan Haynes',
    'address': '46434 Andrea Corner Apt. 713\nHowardstad, NC 49035',
},
    'key85218': 'value19374',
    'key23163': 'value46271',
    'key32255': 'value57100',
    'key11416': 'value25913',
    'key42841': 'value23532',
},
    {
    'id': 17527479951855,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Nathan Harrison',
    'address': '52579 James Key Suite 339\nPort Davidville, PR 89009',
    'text': 'Can difference maintain. Day word task near per impact politics. That population over image. Tonight cost education large population.',
    'email': 'loganrichard@example.net',
    'phone_number': '961-342-4020x60685',
    'json': {
    'name': 'Latoya Johnson',
    'address': '224 Jeremy Prairie\nTiffanymouth, MD 64537',
},
    'key88763': 'value62174',
    'key32894': 'value49222',
    'key46579': 'value57366',
    'key84582': 'value72836',
    'key78201': 'value82584',
    'key74344': 'value42972',
    'key1467': 'value91635',
    'key70876': 'value39380',
},
    {
    'id': 17527479951867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Harold Crawford',
    'address': '90640 Martinez Hills Suite 582\nLake Mary, NY 21202',
    'text': 'Wonder performance population support since free then phone. Baby another interesting key keep memory. Kid about power arm never attention style. Total box large machine source either.',
    'email': 'nelsonjoseph@example.com',
    'phone_number': '257-803-7223x483',
    'json': {
    'name': 'Kathryn Tran',
    'address': '00907 Patel Plains\nNorth Brian, PW 82252',
},
    'key2807': 'value63141',
    'key62440': 'value6499',
    'key68255': 'value73880',
    'key58039': 'value31969',
    'key21201': 'value94403',
},
    {
    'id': 17527479951879,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Patricia Stone',
    'address': 'Unit 4469 Box 4293\nDPO AP 79180',
    'text': 'Environmental class change consider. Sign decide office low event. Become cultural oil friend sometimes.\nDay total woman. Idea training turn minute administration. Guess few off treatment.',
    'email': 'ustein@example.com',
    'phone_number': '+1-628-638-1220x427',
    'json': {
    'name': 'Mr. John Wolf',
    'address': '8266 Jackson Vista\nCurtismouth, AS 77592',
},
    'key848': 'value44384',
    'key15100': 'value70405',
    'key5840': 'value64448',
    'key4642': 'value72433',
    'key77449': 'value83090',
    'key65500': 'value40966',
    'key85599': 'value54680',
    'key67808': 'value39206',
},
    {
    'id': 17527479951889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Kristin Munoz',
    'address': '094 Brewer Harbors Apt. 238\nNew Jocelynberg, ND 20937',
    'text': 'Music lead item section course. Focus feeling me military bit.',
    'email': 'katrina10@example.org',
    'phone_number': '(385)387-0319',
    'json': {
    'name': 'Tracy Wilkinson',
    'address': '6490 Caldwell Summit\nChristychester, KS 43898',
},
    'key96041': 'value99477',
    'key76255': 'value98389',
    'key76718': 'value22918',
    'key77143': 'value41622',
    'key28764': 'value62581',
    'key15807': 'value10632',
    'key54382': 'value96057',
    'key2513': 'value72118',
    'key30136': 'value23777',
    'key50808': 'value2105',
},
    {
    'id': 17527479951899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Ariana Smith',
    'address': '235 Wilson Locks Suite 633\nNorth Alexander, TN 89229',
    'text': 'Necessary employee traditional full job notice yet. Since street perhaps decide face treatment. Upon wonder kind resource better.',
    'email': 'anthony74@example.net',
    'phone_number': '001-703-729-6527x209',
    'json': {
    'name': 'Justin Wise',
    'address': '0539 Zachary Manors Apt. 937\nBrownport, IN 19231',
},
    'key9091': 'value70606',
    'key26500': 'value99716',
    'key85461': 'value45643',
    'key29591': 'value28728',
    'key16473': 'value6112',
},
    {
    'id': 17527479951910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Jasmine Bates',
    'address': '48667 Charles Branch Apt. 994\nJeffreymouth, MT 99466',
    'text': 'Share road specific spend trouble goal. Bed us painting job simple quite notice.',
    'email': 'raven99@example.com',
    'phone_number': '496.679.7981x919',
    'json': {
    'name': 'Paula Livingston',
    'address': '154 Rios Pike\nWest Justinborough, WA 15350',
},
    'key18712': 'value86063',
    'key87183': 'value80175',
},
    {
    'id': 17527479951920,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Amanda Perez',
    'address': 'Unit 5812 Box 9378\nDPO AE 63253',
    'text': 'Resource generation stage sound over tree. Soldier step herself appear government. Brother resource short foreign small church.',
    'email': 'andersenscott@example.com',
    'phone_number': '+1-860-927-7748x672',
    'json': {
    'name': 'Nicole Lewis',
    'address': '29950 John Ferry Suite 435\nWillismouth, LA 33099',
},
    'key48621': 'value4774',
    'key56023': 'value16562',
    'key25744': 'value21953',
    'key28789': 'value90380',
    'key34240': 'value13669',
    'key73886': 'value42367',
    'key29556': 'value35037',
    'key78381': 'value89691',
},
    {
    'id': 17527479951930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Emily Mccoy',
    'address': '5411 Tara Branch\nSouth Davidshire, SD 17400',
    'text': 'Indicate generation again whatever southern animal guy. Concern dinner parent feel trial character tree.\nMoment song type front for line. Share really subject language parent data example.',
    'email': 'phillipsjustin@example.com',
    'phone_number': '001-376-506-9947x0765',
    'json': {
    'name': 'Michael Wilkinson',
    'address': '5448 Gail Point Suite 913\nNew Matthew, OR 43145',
},
    'key36041': 'value29889',
    'key51110': 'value10628',
    'key96752': 'value35885',
    'key48361': 'value31300',
    'key29265': 'value76239',
    'key1165': 'value22894',
    'key21116': 'value12332',
    'key96481': 'value9105',
    'key56768': 'value74497',
},
    {
    'id': 17527479951940,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Austin Smith',
    'address': '471 Watson Manor\nPort Jonathan, MA 18764',
    'text': 'Bad billion this deal former about. You understand white series.\nPolicy anyone performance western reach doctor. Before name matter over until still animal.',
    'email': 'leonardjasmin@example.com',
    'phone_number': '434.307.4379',
    'json': {
    'name': 'Michelle Reyes',
    'address': '4263 Simmons Spur Apt. 723\nMorganberg, WA 80573',
},
    'key40064': 'value52623',
    'key81502': 'value80535',
    'key87316': 'value61958',
    'key44717': 'value13618',
    'key26492': 'value59394',
    'key44913': 'value13580',
    'key86000': 'value97127',
    'key36407': 'value59421',
    'key68535': 'value20148',
    'key95960': 'value96464',
},
    {
    'id': 17527479951952,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Hailey Newman',
    'address': 'USCGC Miller\nFPO AA 86011',
    'text': 'Carry go friend make to central school.\nWhy enjoy along return others store. Ten particularly site fund medical.',
    'email': 'carrillocarrie@example.com',
    'phone_number': '9268778564',
    'json': {
    'name': 'Jason Harris',
    'address': '89622 Allison Lock\nRobinsonmouth, PW 72744',
},
    'key9122': 'value41927',
    'key58623': 'value3198',
    'key49033': 'value57857',
    'key16029': 'value98486',
    'key49785': 'value81339',
    'key71693': 'value76730',
    'key45922': 'value20640',
    'key76663': 'value25612',
    'key82932': 'value41838',
},
    {
    'id': 17527479951963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Michelle White',
    'address': 'PSC 5214, Box 0817\nAPO AE 82904',
    'text': 'See store fight address. Face degree media market recent arrive help.\nPerform evidence station degree. Same actually other gas gun sing large. New read out great available.',
    'email': 'brendasimmons@example.com',
    'phone_number': '389-824-1620',
    'json': {
    'name': 'Christina Maxwell',
    'address': '9302 Melody Estates Apt. 566\nSouth James, AZ 17901',
},
    'key89003': 'value13890',
    'key32590': 'value98678',
    'key19310': 'value5528',
    'key25433': 'value13802',
},
    {
    'id': 17527479951972,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Kim White',
    'address': '52413 John Isle\nSouth Kathleen, VI 56051',
    'text': 'Purpose use later camera may. Hospital thank eat.\nRequire actually trouble him everybody practice. Door through surface four woman speak compare.',
    'email': 'ggamble@example.net',
    'phone_number': '001-481-493-0366x933',
    'json': {
    'name': 'Catherine Rivers',
    'address': '8418 Brown Highway\nChavezborough, NC 37183',
},
    'key68144': 'value75155',
    'key39461': 'value65134',
    'key76284': 'value53080',
    'key70770': 'value45373',
    'key33779': 'value71890',
    'key54261': 'value29689',
},
    {
    'id': 17527479951983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Anthony Kim',
    'address': '74614 Serrano Streets\nFordside, NM 24965',
    'text': 'Toward sometimes while again some. Help painting also determine system under president.\nNo must into present traditional after ground. Bad attorney soldier understand describe method yeah.',
    'email': 'kristinhubbard@example.net',
    'phone_number': '001-508-353-1264',
    'json': {
    'name': 'Jacob Mooney',
    'address': '6174 Fletcher Keys\nPort Allison, OK 65665',
},
    'key65327': 'value19861',
    'key88060': 'value3993',
},
    {
    'id': 17527479951994,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Heather Webb',
    'address': '191 Campos Cliffs\nSouth Ashleyfort, IA 78126',
    'text': 'Court art create detail project whatever carry. Center hope reflect middle trade one building apply. Rich measure moment try key much always.',
    'email': 'navarrovictoria@example.net',
    'phone_number': '7602232402',
    'json': {
    'name': 'Melanie Schroeder',
    'address': '548 Julia Street\nPort Robert, NY 06825',
},
    'key20814': 'value52457',
    'key54': 'value25597',
    'key78490': 'value69911',
},
    {
    'id': 17527479952006,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Heather Murphy',
    'address': '8168 Thompson Branch\nNorth Robertville, NE 32488',
    'text': 'Budget campaign you. Establish answer miss color a.\nMention respond identify change give side. Shake win operation will central should find.\nMedical expect owner animal. Word sense eye somebody.',
    'email': 'vargaslori@example.net',
    'phone_number': '560.681.8147',
    'json': {
    'name': 'Kimberly Shepherd',
    'address': '6572 Moore Extensions Apt. 386\nReedburgh, MD 00691',
},
    'key23454': 'value19104',
    'key39809': 'value65035',
    'key35121': 'value61750',
    'key38905': 'value25534',
    'key10692': 'value21774',
    'key21276': 'value76838',
    'key92052': 'value37189',
},
    {
    'id': 17527479952018,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Mary Cook',
    'address': '26995 Thomas Knolls\nSouth Ronaldtown, WY 40412',
    'text': 'Tough direction mean support set. East act himself six wear key.\nQuite city edge charge line. Project send stop free. Attorney bring little body field.',
    'email': 'levinesharon@example.org',
    'phone_number': '548-849-3507',
    'json': {
    'name': 'Stephanie Hernandez',
    'address': '94563 Marcus Plains Apt. 359\nSouth Kyleport, CO 84994',
},
    'key79423': 'value23141',
},
    {
    'id': 17527479952029,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'John Jones',
    'address': '050 Barber Route Apt. 273\nJamesview, AK 96382',
    'text': 'Matter beyond total change sometimes investment beyond go. Receive compare moment accept form.',
    'email': 'charlesandrade@example.net',
    'phone_number': '583.962.4694x9827',
    'json': {
    'name': 'Donna Lopez',
    'address': '65721 Tracy Ridges Suite 437\nNew Tylerberg, PR 69792',
},
    'key49475': 'value4146',
    'key8094': 'value57738',
    'key18561': 'value11893',
},
    {
    'id': 17527479952041,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Vanessa Patrick',
    'address': '350 Lowe Fork Apt. 703\nLake Emilyfort, MS 45503',
    'text': 'Forward radio four staff. Goal threat suggest kind. Enough surface important.\nData federal maintain personal subject. How bed sea to reach expect.',
    'email': 'bdyer@example.net',
    'phone_number': '+1-865-704-2214x94833',
    'json': {
    'name': 'Brandon Munoz',
    'address': '5971 Gary Stravenue Suite 581\nKristaport, NV 97199',
},
    'key81615': 'value30016',
    'key8399': 'value85586',
    'key61557': 'value77746',
    'key17110': 'value29396',
    'key17460': 'value19196',
    'key31547': 'value16368',
    'key91498': 'value84438',
    'key34386': 'value52198',
    'key8883': 'value49467',
    'key85701': 'value37727',
},
    {
    'id': 17527479952052,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Jose Murphy',
    'address': '60735 Howard Ville Suite 417\nNorth Angela, WY 47720',
    'text': 'Girl main almost people central account. Letter receive move oil in stop through.\nMaterial reduce decision tax yes. Safe activity matter structure. Take service old challenge not lead.',
    'email': 'thomassamantha@example.net',
    'phone_number': '(351)805-1797x82711',
    'json': {
    'name': 'Eric West',
    'address': '8306 Christine Cape\nStephanieberg, WY 92533',
},
    'key68317': 'value89383',
},
    {
    'id': 17527479952063,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Mrs. Pamela Hall DDS',
    'address': '367 Hunter Valleys\nWest Samantha, ND 16107',
    'text': 'Off blood marriage away world. Mouth building activity knowledge night. Activity school time half.',
    'email': 'fmaxwell@example.org',
    'phone_number': '001-799-961-0385x6648',
    'json': {
    'name': 'Kelly Gonzalez',
    'address': 'PSC 1058, Box 9614\nAPO AP 63911',
},
    'key62024': 'value49898',
},
    {
    'id': 17527479952072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Colin Smith',
    'address': '36231 Smith Gardens\nChadton, CT 64252',
    'text': 'Whose another short. Throughout perform beat TV structure land.\nBuy learn according guess will measure. Eye matter evening most.',
    'email': 'raymondjackson@example.org',
    'phone_number': '277-761-1385',
    'json': {
    'name': 'Craig Rodriguez',
    'address': '82334 Bishop Mountain Apt. 645\nNew Sarah, NM 77237',
},
    'key45609': 'value89390',
    'key75667': 'value87293',
    'key2170': 'value52913',
    'key81403': 'value47242',
    'key93281': 'value75947',
    'key29213': 'value22060',
    'key2258': 'value65238',
    'key71798': 'value77650',
    'key16684': 'value78263',
    'key30884': 'value5419',
},
    {
    'id': 17527479952084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Richard Ramirez',
    'address': '94774 Jared Rest\nLake Jademouth, CA 41394',
    'text': 'And nice author approach heavy. Director whether play describe alone without natural visit. Loss spring bed end. Response interesting notice civil.',
    'email': 'lauriesims@example.org',
    'phone_number': '001-454-214-1242',
    'json': {
    'name': 'Michael Evans',
    'address': '30796 Brian Shore\nNorth Hailey, WV 18301',
},
    'key96125': 'value51356',
    'key74150': 'value21485',
    'key98835': 'value70181',
    'key5376': 'value76803',
    'key93455': 'value73268',
    'key18641': 'value70942',
    'key64836': 'value18380',
    'key53164': 'value4199',
    'key2417': 'value86612',
},
    {
    'id': 17527479952094,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Judith Ramirez',
    'address': '19889 Anderson Keys Suite 184\nGlennstad, FL 17051',
    'text': 'Radio hour as account animal.\nOnce surface speech. Others into opportunity fly activity. Discuss voice grow walk join trade.\nPopulation issue adult key. Cause east site dinner hit everybody.',
    'email': 'angela04@example.org',
    'phone_number': '+1-938-712-5060x684',
    'json': {
    'name': 'Carolyn Miller',
    'address': '771 Brandon Station\nNorth Jasonstad, DE 97597',
},
    'key55946': 'value18294',
    'key77866': 'value68900',
    'key68211': 'value92385',
    'key15741': 'value76212',
    'key89778': 'value39106',
    'key49601': 'value87267',
    'key11244': 'value14445',
    'key4313': 'value36278',
},
    {
    'id': 17527479952105,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Marvin Ramirez',
    'address': '95220 Schwartz Trail Suite 311\nNew Charleston, OR 85512',
    'text': 'Garden decade character quality guy then. Give rather hit trade accept put hair view.',
    'email': 'garciaalexander@example.net',
    'phone_number': '001-740-529-4621x0771',
    'json': {
    'name': 'Hannah Gonzalez',
    'address': 'PSC 8230, Box 9015\nAPO AE 29158',
},
    'key16049': 'value97424',
    'key62611': 'value31640',
    'key87282': 'value80555',
},
    {
    'id': 17527479952115,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kimberly Davis',
    'address': '677 Johnson Highway Suite 712\nDonnachester, MT 29308',
    'text': 'Study use road population own human.\nAdult fact wrong might situation west also. Generation so fill magazine there apply. Cup wonder tough letter. Hot manage on international similar sound task.',
    'email': 'dianacrawford@example.com',
    'phone_number': '+1-816-755-3814x4358',
    'json': {
    'name': 'Lisa Hartman',
    'address': '4731 Sylvia Pine\nHartmanshire, NC 03358',
},
    'key38571': 'value87453',
    'key91349': 'value92682',
    'key95940': 'value10681',
    'key78536': 'value88112',
    'key21765': 'value66040',
    'key82463': 'value4381',
    'key9312': 'value49359',
},
    {
    'id': 17527479952126,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Cameron Wright',
    'address': '518 Owens Crossing\nGreerfort, CT 74191',
    'text': 'Enjoy have light. Upon yes anything safe claim against. Season girl wind practice federal stock.\nScience activity discuss early director leave on. Several oil mind sort actually care student us.',
    'email': 'sarah40@example.net',
    'phone_number': '7637793257',
    'json': {
    'name': 'Judith Richardson',
    'address': '14646 Morgan Junction Suite 748\nTylerchester, RI 72307',
},
    'key19635': 'value95977',
    'key18123': 'value53041',
    'key62540': 'value30786',
    'key83270': 'value6293',
    'key89736': 'value89956',
    'key66477': 'value21061',
    'key13134': 'value57224',
    'key63295': 'value1575',
},
    {
    'id': 17527479952137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Travis York',
    'address': '8478 Robbins Meadow Suite 716\nPort Debbieborough, AS 68615',
    'text': 'Word resource close fly them live. Discussion mention may idea both pretty. Ball study also south.\nOld example teach off total order drug ever. Police stock hundred capital generation.',
    'email': 'rebeccamiller@example.org',
    'phone_number': '855-793-2209x841',
    'json': {
    'name': 'Anthony Wiley',
    'address': '74927 Michelle Cape Apt. 685\nBrianville, KS 41221',
},
    'key32383': 'value83926',
    'key4403': 'value89260',
},
    {
    'id': 17527479952149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Lisa Mckenzie',
    'address': '40308 Wilkinson Grove\nBrownview, OR 46487',
    'text': 'Several term car real nation. Push population type rather with meet.\nMention would eight challenge. Perform push throw impact compare over.',
    'email': 'kenneth88@example.net',
    'phone_number': '(543)647-4731x167',
    'json': {
    'name': 'Tiffany Shannon',
    'address': '33904 Alex Manor\nJofurt, NY 65115',
},
    'key89310': 'value35489',
    'key38193': 'value3',
    'key22695': 'value41622',
    'key80313': 'value49910',
},
    {
    'id': 17527479952159,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Taylor Farrell',
    'address': '22705 Perez Road Suite 917\nAlexandraburgh, MO 68507',
    'text': 'Behavior field candidate education. Chair door own wait affect language beautiful.',
    'email': 'janderson@example.com',
    'phone_number': '+1-437-769-7090',
    'json': {
    'name': 'Paul Hunter',
    'address': 'USNV Johnson\nFPO AP 32687',
},
    'key66394': 'value37628',
    'key40476': 'value47725',
    'key30535': 'value35570',
},
    {
    'id': 17527479952169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Emily Thompson',
    'address': '573 Elizabeth Stream Apt. 012\nJacobberg, GU 55887',
    'text': 'Million hot first fund miss current. Might race floor tax resource high less.\nGuy economy fire data other plan pattern whom. Every floor chair suggest we wonder. Small money Mrs animal.',
    'email': 'brocktabitha@example.org',
    'phone_number': '+1-495-281-0191x02922',
    'json': {
    'name': 'Emily Jackson',
    'address': '678 Jenna Stream Apt. 137\nNew Jamesfurt, HI 62197',
},
    'key36570': 'value26116',
    'key48763': 'value78739',
    'key98126': 'value45488',
    'key52219': 'value86827',
},
    {
    'id': 17527479952180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Stacey Rice',
    'address': '079 Tim Walk Apt. 122\nNorth Jonathonside, NC 25156',
    'text': 'Writer turn radio character reason deep task. Possible be without them off month. When usually employee recognize.',
    'email': 'gary13@example.com',
    'phone_number': '001-404-934-7814x3503',
    'json': {
    'name': 'Sherry Martinez',
    'address': '23903 Brown Mall Suite 129\nBlairburgh, MD 43301',
},
    'key42977': 'value61252',
    'key79463': 'value5533',
    'key290': 'value57348',
    'key60820': 'value8285',
    'key51728': 'value2329',
    'key3586': 'value79671',
    'key16452': 'value36220',
},
    {
    'id': 17527479952190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Ebony Weber',
    'address': '69871 Gary Manor\nPort Frank, MP 15484',
    'text': 'Traditional left southern president argue population. Dog none wide phone goal middle despite. Loss part identify beyond trip peace.\nUnderstand imagine cut believe think type government.',
    'email': 'juliasmith@example.com',
    'phone_number': '716.455.2229',
    'json': {
    'name': 'David Long',
    'address': '86128 Lisa View Apt. 841\nNorth Allisonview, IA 55844',
},
    'key31573': 'value61724',
    'key52003': 'value95926',
    'key53400': 'value68067',
    'key19408': 'value62110',
    'key14956': 'value33918',
    'key86591': 'value16475',
},
    {
    'id': 17527479952202,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Vanessa Conner',
    'address': '5011 Sandra Crossroad Apt. 009\nNicholsside, NV 61096',
    'text': 'Smile teach world theory six. Near try director group feel foreign thousand he. Southern as hand find choose small prevent.',
    'email': 'garciadiana@example.com',
    'phone_number': '206.709.3160',
    'json': {
    'name': 'Morgan Davis',
    'address': '04776 Everett Cove Suite 876\nAndrewbury, AZ 57033',
},
    'key18440': 'value5596',
},
    {
    'id': 17527479952213,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Mackenzie Doyle',
    'address': '65062 Christine Rapids\nWest Caitlinstad, VA 65908',
    'text': 'Floor seat second they beyond wall TV realize. Power citizen outside. Ready imagine practice among claim.\nWorker time into industry day. Indeed manage he. Action turn cut sell option medical report.',
    'email': 'christopher56@example.com',
    'phone_number': '+1-388-381-0528',
    'json': {
    'name': 'Daniel Melton',
    'address': '022 Peters Ville Suite 729\nWashingtonstad, NV 50459',
},
    'key21839': 'value78024',
    'key4355': 'value12466',
    'key13547': 'value30845',
    'key70848': 'value87614',
    'key25814': 'value90850',
    'key83075': 'value45464',
    'key42764': 'value26410',
},
    {
    'id': 17527479952224,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Sarah Welch',
    'address': '0371 Michael Lakes\nLake Nancystad, MD 11345',
    'text': 'New memory long animal role most. Each instead own add voice indeed.\nThreat avoid PM analysis wonder culture event suffer. Activity alone sing use head mean.\nItem product away west hear mouth.',
    'email': 'coffeyjohn@example.org',
    'phone_number': '(728)656-6718x0719',
    'json': {
    'name': 'Thomas Jefferson',
    'address': 'Unit 2472 Box 3037\nDPO AE 65082',
},
    'key30489': 'value80110',
    'key32116': 'value47592',
    'key93504': 'value63458',
    'key80641': 'value89068',
    'key1202': 'value23349',
    'key91719': 'value54125',
    'key63803': 'value62300',
},
    {
    'id': 17527479952234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Austin Kane',
    'address': '888 Johnson Squares Apt. 020\nNew Oscar, MA 36991',
    'text': 'Glass I young decide build individual success. Care though better chance.\nEducation much resource be easy bag bar. Type parent source start perform exactly first election.',
    'email': 'william49@example.com',
    'phone_number': '844.761.5579',
    'json': {
    'name': 'Donna Rocha',
    'address': '94624 Wood Hollow\nMccoyside, WY 49492',
},
    'key96024': 'value70514',
    'key54723': 'value21612',
    'key27313': 'value66351',
},
    {
    'id': 17527479952244,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Sarah Lee',
    'address': '983 Mcdaniel Road Apt. 425\nJonesburgh, FL 28288',
    'text': 'Beautiful every doctor child. Agent executive structure author.\nRemain man letter spring century. Fall no cultural anyone environment member event where.\nPush issue build city.',
    'email': 'srivas@example.net',
    'phone_number': '413.514.2048',
    'json': {
    'name': 'William Dickson',
    'address': '28166 Nicole Mill\nEast Jennifer, CA 70370',
},
    'key3555': 'value62425',
    'key81067': 'value16205',
},
    {
    'id': 17527479952255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Anthony Williams',
    'address': '99506 Lori Loaf\nPort Alicia, AZ 47410',
    'text': 'Yourself her attention scene. Technology detail management hair. Western test walk.\nMove theory recently speak likely open. War strong page several. Skill director party gun positive.',
    'email': 'michael69@example.net',
    'phone_number': '(515)990-1972',
    'json': {
    'name': 'Lisa Delgado',
    'address': '988 Taylor Brooks\nSouth Catherinechester, WV 32433',
},
    'key3761': 'value43768',
    'key59476': 'value2780',
    'key77699': 'value50644',
    'key46487': 'value64666',
    'key89630': 'value37425',
    'key42060': 'value20372',
    'key7743': 'value51712',
    'key9730': 'value2169',
},
    {
    'id': 17527479952265,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'William Allison',
    'address': '70620 Patricia Walk\nNew Amandaside, PR 48337',
    'text': 'Large three sense hope daughter ago gas. Born make last team law like. Religious wrong quickly which both source. Future keep thing change.',
    'email': 'rebeccabradford@example.org',
    'phone_number': '264-935-6744x235',
    'json': {
    'name': 'Jessica Baker',
    'address': '408 Justin Walks Suite 034\nAnthonyville, MD 79417',
},
    'key75351': 'value13307',
    'key66373': 'value63554',
    'key82585': 'value31339',
    'key64864': 'value47759',
    'key77378': 'value68984',
    'key8380': 'value66464',
    'key76528': 'value23082',
    'key96816': 'value85354',
    'key56868': 'value35769',
    'key44758': 'value98658',
},
    {
    'id': 17527479952276,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Chad Elliott',
    'address': '13061 Mckinney Forks\nTammieview, PA 47915',
    'text': 'Garden fly heavy forward believe pressure. Vote arm same room measure.',
    'email': 'mitchellraymond@example.net',
    'phone_number': '001-853-346-7545x56002',
    'json': {
    'name': 'Jesse Dickerson PhD',
    'address': '190 Victoria Garden\nPhillipsfort, KY 38414',
},
    'key76505': 'value67196',
    'key12090': 'value77417',
    'key17919': 'value54176',
    'key5645': 'value19543',
    'key14191': 'value26607',
    'key72295': 'value96930',
    'key83690': 'value94435',
    'key11045': 'value78942',
    'key49033': 'value16074',
    'key94160': 'value83158',
},
    {
    'id': 17527479952288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Michelle Williams',
    'address': '25940 Harris Bypass\nNortonfurt, WA 41118',
    'text': 'Once threat great way. Thank far carry hand institution. Once begin hundred series.\nGoal again result condition. Collection behavior Mrs occur care partner by.',
    'email': 'ortegaryan@example.com',
    'phone_number': '(643)909-1569x633',
    'json': {
    'name': 'Bradley Lane',
    'address': '08062 Kevin Springs\nSarahbury, SC 90217',
},
    'key10796': 'value9932',
    'key97177': 'value896',
    'key75304': 'value87431',
    'key22681': 'value27905',
    'key94803': 'value30820',
},
    {
    'id': 17527479952299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Donna Guerra',
    'address': '9912 Erin Common Suite 612\nPort Joanville, PA 97551',
    'text': 'Drop brother sound financial poor others. Candidate instead total. Beautiful even international mother investment.\nReason factor guy onto cold seat dog. Pay question hotel. Man woman edge few.',
    'email': 'veronica67@example.com',
    'phone_number': '7357958646',
    'json': {
    'name': 'Keith Wilkinson',
    'address': '91456 Steven Via\nWesleybury, OR 62223',
},
    'key33580': 'value34915',
    'key78572': 'value88147',
    'key21420': 'value87997',
    'key70043': 'value50048',
    'key48286': 'value61591',
    'key81546': 'value10645',
    'key93238': 'value64443',
    'key72106': 'value80747',
    'key89642': 'value4868',
},
    {
    'id': 17527479952310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Nichole Brown',
    'address': 'Unit 0000 Box 0372\nDPO AE 60720',
    'text': 'Record blue despite serve. Audience admit strong future hand necessary manage. Central reflect how sister.',
    'email': 'meganjohnson@example.org',
    'phone_number': '001-953-971-6841',
    'json': {
    'name': 'Michelle Barron',
    'address': '54927 Cox Prairie Apt. 402\nWilliamton, MD 54609',
},
    'key9334': 'value20358',
    'key43063': 'value71192',
    'key6148': 'value364',
    'key10572': 'value39721',
    'key71071': 'value27316',
    'key1862': 'value66732',
    'key92883': 'value88851',
    'key17580': 'value52205',
},
    {
    'id': 17527479952319,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Jessica Shelton',
    'address': '54793 Perez Ports\nPort Codyfurt, MP 90545',
    'text': 'Cut stop first serious human six want. A accept size arrive husband Democrat.\nSuddenly break city leave talk build. Less person wish reality.',
    'email': 'daniel62@example.net',
    'phone_number': '373-650-3087',
    'json': {
    'name': 'Jordan Lam',
    'address': '88951 King Circle\nSouth Leslieville, KS 82802',
},
    'key43199': 'value10482',
    'key84379': 'value45668',
    'key60821': 'value99283',
    'key42784': 'value92852',
},
    {
    'id': 17527479952330,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Kimberly Schaefer',
    'address': '616 Samantha Pines Suite 349\nWest Patricktown, MA 56735',
    'text': 'Hair region evidence time.\nInternational chance everyone reason arm ask well. Kitchen factor voice some decade democratic.\nLeave also maintain life really. Such future start hospital.',
    'email': 'sandrablankenship@example.com',
    'phone_number': '001-857-798-6501x6131',
    'json': {
    'name': 'Tracey Estrada',
    'address': '72088 Castro Cliff Apt. 894\nSchultzmouth, TX 57034',
},
    'key3945': 'value71827',
    'key80779': 'value60807',
},
    {
    'id': 17527479952341,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Nancy Kane',
    'address': '0357 Cain Ville Apt. 502\nPort Chadshire, GU 87261',
    'text': 'Nation fear bag top open truth consider. Gas left long such management possible.\nOwn wait somebody hold. Behavior song senior itself like civil. Back figure quite lay director.',
    'email': 'greenbrent@example.net',
    'phone_number': '+1-602-612-4682x181',
    'json': {
    'name': 'Sara Barnes MD',
    'address': 'PSC 3248, Box 2406\nAPO AP 52388',
},
    'key75565': 'value59823',
    'key28217': 'value95510',
    'key88579': 'value51062',
    'key9008': 'value7728',
    'key53268': 'value51855',
    'key17521': 'value55385',
},
    {
    'id': 17527479952351,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Diana Rojas',
    'address': '66218 Christopher Court Suite 458\nNew Zachary, NV 73418',
    'text': 'Concern kid give agreement piece own. Information true determine in particularly stand.',
    'email': 'lisa36@example.net',
    'phone_number': '(516)667-2382',
    'json': {
    'name': 'Jo Bailey',
    'address': '37328 Danielle Valley\nCarlsonshire, KS 62045',
},
    'key35783': 'value32942',
    'key18998': 'value20668',
    'key9975': 'value21804',
    'key7663': 'value22848',
    'key26674': 'value26388',
    'key5679': 'value93189',
    'key64569': 'value10972',
    'key27691': 'value30225',
    'key78613': 'value32853',
},
    {
    'id': 17527479952362,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Melanie Carlson',
    'address': '6580 Miles Springs Apt. 160\nVeronicamouth, SC 63711',
    'text': 'Degree expect discover body could free personal. Step perform surface throw capital already. Benefit address notice manage fire. Nor admit themselves model some young.',
    'email': 'tammyacosta@example.com',
    'phone_number': '001-768-898-5581',
    'json': {
    'name': 'James Buck',
    'address': '0583 Flores Island Suite 301\nNelsonburgh, AL 15193',
},
    'key84239': 'value29042',
    'key19180': 'value65764',
    'key11817': 'value45848',
    'key2204': 'value5470',
    'key9243': 'value166',
    'key77490': 'value98300',
    'key74925': 'value62804',
    'key80126': 'value61995',
},
    {
    'id': 17527479952374,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Carol Wright',
    'address': '23106 Michael Fort Apt. 796\nSouth Adam, CT 58784',
    'text': 'Positive allow card pretty start. Join group together modern effort process. Single sense necessary race.\nThreat I low song baby development. Since idea see usually.',
    'email': 'deborah23@example.net',
    'phone_number': '376.477.9189x931',
    'json': {
    'name': 'Laura Mccann',
    'address': '417 Conley Bridge Apt. 361\nPort Deannamouth, AZ 82016',
},
    'key70232': 'value87533',
    'key35886': 'value22928',
    'key99370': 'value52864',
    'key15447': 'value83770',
    'key98866': 'value27374',
    'key29784': 'value60313',
    'key69365': 'value38621',
    'key23168': 'value32940',
},
    {
    'id': 17527479952384,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Billy Smith',
    'address': '49612 Yu Plaza Apt. 289\nGomeztown, GA 92544',
    'text': 'Future onto listen sit forget. Red physical commercial moment. Three hot black high cultural.',
    'email': 'nicholas58@example.net',
    'phone_number': '+1-454-758-6269x5037',
    'json': {
    'name': 'Jacqueline Burnett',
    'address': '2243 Patricia Loaf\nFlemingbury, NJ 17712',
},
    'key94540': 'value39413',
    'key51653': 'value26719',
    'key87194': 'value81538',
    'key3605': 'value44289',
    'key18236': 'value77137',
},
    {
    'id': 17527479952395,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Lance Blankenship',
    'address': '542 Christine Plain Apt. 585\nPort Brittany, HI 96574',
    'text': 'Little year account its compare difference. Side all list all. Less reality prove.',
    'email': 'rachelpeterson@example.org',
    'phone_number': '001-563-356-8525',
    'json': {
    'name': 'Mrs. Mary Sosa',
    'address': '219 Juan Islands\nWest Samanthamouth, UT 30860',
},
    'key68813': 'value49333',
    'key41241': 'value45974',
    'key83414': 'value59638',
    'key27672': 'value49730',
    'key91436': 'value34584',
    'key955': 'value67599',
    'key85099': 'value85549',
    'key10756': 'value86190',
    'key11549': 'value91174',
},
    {
    'id': 17527479952406,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jo Harrison',
    'address': '0356 Christopher Mission Suite 125\nPort Bradley, OR 49131',
    'text': 'Religious just woman foot Congress themselves community. Age change certainly personal most explain. Nature local rather remain.',
    'email': 'sheltonjohn@example.org',
    'phone_number': '4854093618',
    'json': {
    'name': 'Elizabeth Doyle',
    'address': 'Unit 4538 Box 5973\nDPO AA 65601',
},
    'key10372': 'value32521',
    'key43326': 'value91925',
    'key22821': 'value23811',
    'key58095': 'value65760',
    'key13956': 'value50334',
    'key76517': 'value33188',
    'key47858': 'value39792',
},
    {
    'id': 17527479952416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Martin Rose',
    'address': '22998 Lance Field\nNorth Joannbury, WV 67628',
    'text': 'Lead ago simple. Build laugh feel condition pressure. Wrong north improve such meet.\nWith home activity account mind. Win herself such. Success continue recent manager hold last evidence.',
    'email': 'jenniferrice@example.org',
    'phone_number': '+1-900-573-5687',
    'json': {
    'name': 'David Roth',
    'address': '8610 Stacey Extensions Apt. 550\nBauertown, AZ 20760',
},
    'key54203': 'value73354',
    'key7026': 'value34302',
},
    {
    'id': 17527479952426,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Joseph Parks',
    'address': '131 Kathleen Terrace\nGrantmouth, MI 48539',
    'text': 'That let while democratic. Beautiful marriage sister natural audience church. Chance however list professional.\nLeg material prove world. Better bring go feeling stop.',
    'email': 'jessicahenderson@example.net',
    'phone_number': '+1-678-502-9636x703',
    'json': {
    'name': 'Lori Bennett',
    'address': 'Unit 8617 Box 8118\nDPO AE 24823',
},
    'key44663': 'value57487',
    'key91076': 'value63899',
    'key10904': 'value37282',
    'key74756': 'value83935',
    'key16926': 'value58443',
    'key30200': 'value33629',
    'key50477': 'value89189',
},
    {
    'id': 17527479952436,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Kelly Richards',
    'address': '146 Roberts Underpass\nPort Steven, ND 87602',
    'text': 'Media easy those eight good fast care. State life blood citizen red maybe. Artist kind million candidate note commercial. Two much positive majority wall model doctor behavior.',
    'email': 'fullerjoshua@example.net',
    'phone_number': '882.429.5423x0679',
    'json': {
    'name': 'Julie Jones',
    'address': '362 Perez Lodge\nSouth Donna, FM 11514',
},
    'key27096': 'value12094',
},
    {
    'id': 17527479952447,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Tammy Davis',
    'address': 'PSC 4011, Box 4152\nAPO AE 48994',
    'text': 'Hold determine a happen break standard environment inside. Young TV ever act give significant.',
    'email': 'taylorbobby@example.org',
    'phone_number': '+1-274-744-2252x82903',
    'json': {
    'name': 'Ryan Long Jr.',
    'address': '401 Peck Prairie Suite 156\nCarterchester, FM 30528',
},
    'key2967': 'value62531',
    'key52795': 'value75339',
    'key44599': 'value58395',
    'key10385': 'value92074',
    'key82202': 'value97831',
},
    {
    'id': 17527479952457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Christopher Long',
    'address': '19185 Lewis Track Suite 064\nHeatherville, CO 88023',
    'text': 'She common current back drug certainly season. Southern oil return green design.\nIts media improve care lead gun personal.\nWalk affect civil sport seek usually. Deep area important to.',
    'email': 'parkerjulie@example.com',
    'phone_number': '457.926.3310x1120',
    'json': {
    'name': 'Terry Garcia',
    'address': '0477 Logan Route Suite 291\nSouth Wandaside, AR 54959',
},
    'key73943': 'value26692',
    'key29507': 'value89138',
},
    {
    'id': 17527479952468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Michael Ramos',
    'address': '244 Jared Parks\nNorth Shelly, AL 09428',
    'text': 'Sport good reflect least think source sing. Almost hair them win attorney.\nSet ball summer ability goal.\nFederal improve animal your state same state. Simply hour cell radio right total believe.',
    'email': 'nataliekim@example.net',
    'phone_number': '+1-646-839-0384x24417',
    'json': {
    'name': 'Natasha Harmon',
    'address': '998 Mills Plains\nBriannastad, AR 05017',
},
    'key16923': 'value5858',
    'key33760': 'value49737',
    'key77822': 'value52077',
    'key44981': 'value83538',
},
    {
    'id': 17527479952480,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Michael Cooper',
    'address': '973 Harris Haven Suite 226\nAlexandrachester, NH 73954',
    'text': 'Section fine everyone total phone whether. Safe manage likely herself drive church me.\nInto young possible. Our public read cultural memory. Himself popular soldier popular would example personal.',
    'email': 'brookemorales@example.org',
    'phone_number': '001-793-983-0358x591',
    'json': {
    'name': 'Heather Wright',
    'address': '450 Daniel Bypass Suite 246\nEmilystad, NE 31596',
},
    'key81549': 'value25055',
    'key59410': 'value50357',
    'key90845': 'value87586',
    'key96365': 'value46233',
    'key1019': 'value13870',
    'key76911': 'value72786',
    'key27989': 'value11180',
    'key83517': 'value34302',
},
    {
    'id': 17527479952491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Joshua Hill DDS',
    'address': '6663 Richard Villages\nEast Ashley, UT 65461',
    'text': 'Best again girl record her build nice reflect. Relationship subject bring second risk church range. Raise expert usually husband left.',
    'email': 'katieoconnor@example.org',
    'phone_number': '001-261-817-3833',
    'json': {
    'name': 'Daniel Nguyen',
    'address': '2319 Angela Ranch\nJohnbury, NM 34439',
},
    'key74089': 'value77861',
    'key918': 'value7004',
    'key90828': 'value23346',
    'key90694': 'value8688',
    'key10477': 'value18112',
    'key2388': 'value70661',
    'key62664': 'value72333',
},
    {
    'id': 17527479952502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Gary Hernandez',
    'address': '76025 Torres Lock\nLake Heatherborough, PR 25464',
    'text': 'Memory hard activity provide defense. Interview inside skill discussion television family foreign.\nSoon true similar. Medical push tax team specific.\nSong certain feel art miss name social.',
    'email': 'lynnlopez@example.net',
    'phone_number': '393-211-6798x871',
    'json': {
    'name': 'Nicholas Stevens',
    'address': 'USNS Mays\nFPO AE 79202',
},
    'key51136': 'value30097',
    'key50049': 'value42482',
    'key40828': 'value94509',
    'key21034': 'value58036',
    'key37808': 'value86388',
    'key62832': 'value62324',
    'key65984': 'value70409',
},
    {
    'id': 17527479952513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Gloria Donovan',
    'address': '798 Smith Turnpike Suite 949\nTammychester, RI 73334',
    'text': 'Its push opportunity never. Mouth however play cut group day so hair.\nDecide land agent century cup feeling black. Loss information it wait buy like. Government short majority expect.',
    'email': 'christopher10@example.org',
    'phone_number': '+1-711-683-8704x62485',
    'json': {
    'name': 'Jacqueline Flores',
    'address': '37758 Foster Avenue Suite 029\nStevenfort, NV 44425',
},
    'key79065': 'value38353',
},
    {
    'id': 17527479952524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Laura May',
    'address': '88144 Brandon Cape Apt. 544\nLake Samantha, MP 54786',
    'text': 'Explain protect into body throughout light. Stand management unit impact story may. There life film car rock science available.\nAvoid ready gas break eight quickly. Close investment prevent.',
    'email': 'patrickshannon@example.com',
    'phone_number': '(456)814-2514x2063',
    'json': {
    'name': 'Thomas Miller',
    'address': '3126 Nathaniel Rest\nPatriciabury, CA 26904',
},
    'key71182': 'value6430',
    'key46963': 'value22963',
    'key9828': 'value90654',
    'key61021': 'value82945',
    'key59726': 'value64077',
    'key15526': 'value15147',
    'key60988': 'value65900',
},
    {
    'id': 17527479952535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Joshua Stevens',
    'address': 'Unit 1736 Box 9027\nDPO AE 83713',
    'text': 'Participant big billion once million increase. Article public south admit quality news word. Admit city something tough mention so.',
    'email': 'joycepreston@example.com',
    'phone_number': '(615)358-1683x326',
    'json': {
    'name': 'Carolyn Hamilton',
    'address': '507 Tommy Court\nParrishberg, IL 96563',
},
    'key46324': 'value97771',
    'key55482': 'value46447',
    'key54874': 'value46463',
    'key40842': 'value51499',
    'key4424': 'value7291',
    'key85648': 'value112',
    'key80455': 'value24978',
},
    {
    'id': 17527479952545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jessica Gordon',
    'address': '6131 Lowe Plaza Suite 175\nSheliachester, IL 09552',
    'text': 'Should knowledge today nearly. Responsibility alone eight significant. Lay game main fact.',
    'email': 'wendyhernandez@example.org',
    'phone_number': '9755965410',
    'json': {
    'name': 'Jacqueline Miller',
    'address': '36457 Laura Falls\nWesleyberg, NC 95304',
},
    'key93080': 'value67974',
},
    {
    'id': 17527479952555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Meagan Patel',
    'address': '408 Andrea Well\nNew Brianland, OR 99073',
    'text': 'Whom maintain production and natural beautiful. Say training listen money. Listen theory community your only.\nCan where wait public science evidence travel.',
    'email': 'albert39@example.com',
    'phone_number': '5379342577',
    'json': {
    'name': 'Nicholas Graham',
    'address': '820 Brown Street\nGibbsville, PR 95559',
},
    'key63087': 'value81332',
    'key14637': 'value19971',
    'key83908': 'value69682',
    'key58417': 'value12875',
    'key5953': 'value82196',
},
    {
    'id': 17527479952566,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Laura Anderson',
    'address': '12494 Reed Stravenue Suite 316\nMckayland, OH 73299',
    'text': 'Positive sense student exist between evidence require. Report attack stand Republican. Success role type environment. Phone per daughter high.',
    'email': 'john76@example.com',
    'phone_number': '(514)937-0406',
    'json': {
    'name': 'Jessica Bennett',
    'address': 'Unit 9794 Box 9933\nDPO AE 26155',
},
    'key41199': 'value31309',
    'key97136': 'value67222',
    'key33438': 'value16505',
    'key5837': 'value76765',
    'key1995': 'value54155',
},
    {
    'id': 17527479952575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Rachel Ward',
    'address': 'PSC 6093, Box 4463\nAPO AE 01156',
    'text': 'Air fast form today. Two involve trial employee serve Democrat.\nReceive sign exactly different. Despite democratic report just concern statement subject sign. Agent feeling then sit.',
    'email': 'harriskathleen@example.com',
    'phone_number': '582-672-3713',
    'json': {
    'name': 'Cynthia Lynch',
    'address': '6659 Bobby Drives\nSteventown, IA 67033',
},
    'key34713': 'value74355',
},
    {
    'id': 17527479952584,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Mrs. Elizabeth Cunningham',
    'address': '633 Chelsea Extensions\nWest Christopherport, CA 02152',
    'text': 'Break teacher join few. Care begin almost history blue visit.\nInto court individual. Language vote admit measure low cause idea.',
    'email': 'cherrymichael@example.net',
    'phone_number': '(637)650-6382x9747',
    'json': {
    'name': 'Jessica Martinez',
    'address': '29008 Carpenter Spur\nPowellville, VI 86509',
},
    'key39129': 'value16037',
    'key15519': 'value88012',
    'key30749': 'value6398',
    'key18223': 'value57451',
    'key49449': 'value29607',
    'key95506': 'value33547',
    'key30643': 'value33642',
    'key60732': 'value90373',
    'key18013': 'value77172',
    'key2287': 'value14848',
},
    {
    'id': 17527479952596,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Marcus Downs',
    'address': '8450 Cox Hills Suite 412\nMillerhaven, MI 78760',
    'text': 'Would ahead production. Drug usually design across from without I happy.\nClaim say film provide. Travel either experience image dog family worry sometimes.',
    'email': 'romantina@example.com',
    'phone_number': '(697)724-1827',
    'json': {
    'name': 'Mary Castro',
    'address': '415 Rhonda Mount\nDaniellefurt, TN 46155',
},
    'key11567': 'value12748',
    'key28050': 'value37209',
    'key76520': 'value51261',
},
    {
    'id': 17527479952607,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Lindsay Thomas DVM',
    'address': '327 Jones Oval\nMitchellside, TX 79250',
    'text': 'Camera attention show know. Purpose thing budget probably bank war thought. Visit price color new determine entire.',
    'email': 'brandonstevens@example.net',
    'phone_number': '610-429-3216x39736',
    'json': {
    'name': 'Michael Smith',
    'address': '318 Renee Loaf Suite 236\nEast Karenmouth, MI 37865',
},
    'key62014': 'value97698',
    'key81010': 'value59061',
    'key60452': 'value31966',
    'key29963': 'value52104',
    'key97665': 'value50414',
    'key95411': 'value90617',
},
    {
    'id': 17527479952619,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Rachel Mosley',
    'address': 'USNV Freeman\nFPO AA 71324',
    'text': 'Night catch huge network exactly something. These speech simply boy indicate do indeed. Social employee either management.\nOld always group production model. Professor check meeting.',
    'email': 'reyesmeghan@example.net',
    'phone_number': '001-516-934-0273',
    'json': {
    'name': 'Brandon Young',
    'address': '837 Lisa Avenue\nRodriguezbury, MS 24543',
},
    'key39162': 'value15714',
    'key23254': 'value60039',
    'key67592': 'value79320',
    'key31344': 'value41633',
    'key14295': 'value32419',
},
    {
    'id': 17527479952629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Brian Wagner',
    'address': 'USS Chapman\nFPO AE 98234',
    'text': 'All alone treatment old agree perhaps. Administration end vote theory project reach. Fish whom open fact firm on than.\nAlready throughout degree skin individual. Try something soon every.',
    'email': 'keithcastro@example.org',
    'phone_number': '348-565-3642x4925',
    'json': {
    'name': 'Jade James',
    'address': '373 Jacobs Meadows\nMyersbury, ID 91862',
},
    'key49583': 'value21907',
    'key36812': 'value15228',
    'key92830': 'value91086',
    'key40008': 'value6787',
    'key23041': 'value44478',
    'key67240': 'value77702',
},
    {
    'id': 17527479952639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Timothy Gibson',
    'address': 'USS Mccoy\nFPO AE 33777',
    'text': 'Dinner approach may very. Among answer those security least air system.\nLight I because that available out kind. Meeting under edge cup.',
    'email': 'montgomerydenise@example.net',
    'phone_number': '(924)272-3831x6206',
    'json': {
    'name': 'Katherine Miles',
    'address': '019 Alex Key Suite 619\nElliottside, RI 22095',
},
    'key71681': 'value14194',
    'key27519': 'value59880',
    'key82087': 'value97996',
    'key51809': 'value61546',
},
    {
    'id': 17527479952650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kimberly Garrison',
    'address': '3210 William Avenue\nBergtown, CO 70367',
    'text': 'Trouble direction save grow. Notice pretty fall benefit unit.\nFocus kid see near lose. Too white type stage. Past our federal your several.',
    'email': 'zjohnson@example.com',
    'phone_number': '336.450.6157x9340',
    'json': {
    'name': 'Ronald Ho',
    'address': '583 Chandler Ports\nAlvarezstad, WY 62800',
},
    'key53381': 'value72253',
},
    {
    'id': 17527479952661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Julie Lee',
    'address': '7006 Hanson Rest\nStaffordberg, WA 32198',
    'text': 'Assume idea fire card film paper. Senior language throughout education game last. Fish through order explain policy upon.',
    'email': 'rodriguezjonathan@example.org',
    'phone_number': '+1-306-844-4321x83033',
    'json': {
    'name': 'Derrick Graham',
    'address': '82854 Smith Pass\nRachelfurt, IA 94452',
},
    'key34215': 'value54265',
    'key70350': 'value33013',
    'key17887': 'value20777',
    'key53613': 'value41869',
    'key74530': 'value71866',
    'key3268': 'value28097',
    'key60794': 'value12138',
    'key96684': 'value73611',
},
    {
    'id': 17527479952672,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Aaron Rose',
    'address': '721 Mcdaniel Haven\nTracistad, MT 24758',
    'text': 'Realize community wrong citizen read structure western. Most security book soldier mind. All air challenge.\nFace maybe provide activity suggest order institution. Spend modern keep audience provide.',
    'email': 'powellmark@example.net',
    'phone_number': '+1-911-700-5434x70540',
    'json': {
    'name': 'Kurt Walls',
    'address': '3230 Crane Haven\nLake Jeremy, CT 91075',
},
    'key32457': 'value74260',
    'key48010': 'value96184',
    'key26497': 'value95975',
    'key42549': 'value50530',
},
    {
    'id': 17527479952684,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Jesse Hall',
    'address': '906 Cunningham Stravenue Apt. 748\nBrowningborough, AL 73825',
    'text': 'Claim sport official by community these. Accept most order teacher.\nOrganization camera evening might set newspaper memory. Claim study nation.',
    'email': 'owalker@example.org',
    'phone_number': '291-477-9445x772',
    'json': {
    'name': 'Amanda Carey',
    'address': '391 Smith Pine Apt. 468\nNew Melissa, MT 39385',
},
    'key56055': 'value96815',
    'key78435': 'value54143',
    'key92482': 'value37705',
},
    {
    'id': 17527479952696,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Steven Miller',
    'address': '91481 Doyle Isle Apt. 214\nKevinchester, IL 74117',
    'text': 'Daughter charge glass instead wear consider. Same serve seek manager economy affect. Common different at us activity could account. Economy black character born.',
    'email': 'mwallace@example.com',
    'phone_number': '+1-469-931-3059x490',
    'json': {
    'name': 'Daniel Hughes',
    'address': '89584 Russell Via Suite 122\nSouth Garyview, OK 14903',
},
    'key13178': 'value54570',
    'key93975': 'value27462',
    'key473': 'value58626',
    'key41722': 'value17098',
    'key79486': 'value49639',
    'key72422': 'value82519',
    'key63643': 'value48204',
    'key55522': 'value99358',
    'key21932': 'value55063',
},
    {
    'id': 17527479952706,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'William White',
    'address': '20412 Zamora Parkways Suite 554\nMilesbury, AZ 44120',
    'text': 'Join owner off soon remember sometimes boy. Professional end art general only. Adult analysis stop several half firm person.',
    'email': 'millschristina@example.net',
    'phone_number': '8202357252',
    'json': {
    'name': 'Matthew Hartman',
    'address': '565 Steele Crossing Apt. 461\nBallfort, WA 15370',
},
    'key89432': 'value80396',
    'key53255': 'value34776',
    'key58867': 'value65270',
    'key1193': 'value43295',
    'key29040': 'value39038',
    'key35163': 'value24777',
    'key63279': 'value25655',
    'key94754': 'value99218',
    'key65626': 'value40022',
},
    {
    'id': 17527479952719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jessica Coleman',
    'address': '774 Sara Ferry Suite 213\nSouth Lisafort, TX 69169',
    'text': 'Maintain clearly food wonder word enjoy. Present on analysis red quickly throw drive. Ago million at.\nDescribe into also main culture. Choose during miss name meeting lay rest.',
    'email': 'daniel50@example.org',
    'phone_number': '335-228-0008x856',
    'json': {
    'name': 'Heather Fernandez',
    'address': '9880 Tina Turnpike\nWoodshire, VI 89649',
},
    'key65889': 'value55768',
    'key66997': 'value24192',
    'key48294': 'value50775',
    'key55889': 'value47655',
    'key43806': 'value79364',
    'key77351': 'value63343',
    'key79758': 'value32074',
    'key63577': 'value3062',
    'key93727': 'value73672',
    'key28093': 'value77470',
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
    'RequestId': '8039acd8-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_29_121919PjphZfXB',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '8039acd8-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_29_121919PjphZfXB',
    'dimension': 128,
    'metricType': 'IP',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[IP]_1752747996.json')
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
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithSimplePayloadIp1752747996Json()
    test.run_tests()
