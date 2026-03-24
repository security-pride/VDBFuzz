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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752748907_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752748907.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid01752748907Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752748907.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752748907.json"
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
    'RequestId': '9c504aa6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_35_238560YwMJuipF',
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
    'RequestId': '9c504aa6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_35_238560YwMJuipF',
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
    'RequestId': '9c504aa6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_35_238560YwMJuipF',
    'data': [
    {
    'id': 17527489012801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Carlos Velazquez',
    'address': 'USNS Cook\nFPO AA 86672',
    'text': 'Democrat near foreign decision if result. Politics industry positive although. Major watch card.',
    'email': 'carteremily@example.com',
    'phone_number': '633.324.2313x44081',
    'json': {
    'name': 'Terry Thomas',
    'address': '038 Kristi Field\nWest Brianchester, MO 93433',
},
    'key6705': 'value67507',
    'key10547': 'value74003',
},
    {
    'id': 17527489012819,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Steven Howard',
    'address': '8099 Key Squares Apt. 215\nEast Tracytown, NM 13711',
    'text': 'Away next whatever never. Something leg behavior through glass forward take. Question possible man gas while blood.',
    'email': 'michaeldavis@example.org',
    'phone_number': '+1-975-687-7379',
    'json': {
    'name': 'Cory Garza',
    'address': '157 Morris Radial\nRhodesmouth, IA 05528',
},
    'key311': 'value7552',
    'key65383': 'value56815',
    'key85933': 'value76184',
    'key10850': 'value67413',
    'key66500': 'value38383',
},
    {
    'id': 17527489012834,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Robert Osborne',
    'address': '868 James Green\nSouth Micheleview, UT 94942',
    'text': 'Remain movie guess discover. Involve common music middle.\nAsk become teach various mention. Friend evidence PM receive total.\nHelp music citizen break.',
    'email': 'bethany48@example.com',
    'phone_number': '272-438-8315',
    'json': {
    'name': 'Maria Rodriguez',
    'address': '23668 Patterson Manor\nNorth Susanberg, SC 86558',
},
    'key35926': 'value93432',
    'key51267': 'value70343',
    'key28761': 'value94197',
    'key72051': 'value45106',
    'key53814': 'value35110',
    'key74250': 'value75442',
    'key70440': 'value26002',
},
    {
    'id': 17527489012847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Kenneth Ortiz',
    'address': '602 Rodriguez Trace\nEast Victorport, NM 04287',
    'text': 'Own side station seem concern dinner expert. Surface drop less responsibility specific put test. Attorney order land professional. Even air ask natural.',
    'email': 'boothdavid@example.com',
    'phone_number': '001-483-662-9391x97742',
    'json': {
    'name': 'Laura Mcknight',
    'address': '620 Felicia Run\nRiveraburgh, CA 13299',
},
    'key25575': 'value34315',
    'key72728': 'value26954',
    'key66921': 'value16598',
    'key63470': 'value64438',
    'key25246': 'value20988',
    'key53536': 'value983',
    'key76910': 'value67545',
    'key45685': 'value13972',
},
    {
    'id': 17527489012862,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'James Callahan',
    'address': '3721 William Inlet\nNew Melissabury, HI 37979',
    'text': 'Thus maintain some book imagine history couple. Why nice cost audience compare product often. His employee huge site hundred.',
    'email': 'thomaszachary@example.net',
    'phone_number': '+1-769-397-3128x585',
    'json': {
    'name': 'Jason Cruz',
    'address': '0098 Johnson Track Apt. 092\nMorrisonmouth, NV 90759',
},
    'key3273': 'value76212',
    'key61108': 'value99721',
    'key78102': 'value64630',
    'key35373': 'value21849',
    'key80997': 'value47055',
    'key84418': 'value12550',
    'key6016': 'value22845',
    'key31445': 'value20925',
    'key2946': 'value9608',
},
    {
    'id': 17527489012876,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Mark Jacobson IV',
    'address': '36153 Morris Stravenue Apt. 456\nKatiechester, OH 05216',
    'text': 'Enter mission base it full suggest. Forward explain which sure anyone agent take.',
    'email': 'melissamorgan@example.org',
    'phone_number': '001-847-796-8595x923',
    'json': {
    'name': 'Jacob Alexander',
    'address': '5641 Melinda Bypass Suite 606\nSummersmouth, IA 91180',
},
    'key16001': 'value18765',
},
    {
    'id': 17527489012890,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Linda Thompson',
    'address': '84057 Ortiz Inlet\nPort Melissa, MI 26575',
    'text': 'For yourself opportunity street item moment. Million camera cost loss play floor.\nAs of type network order research. Single gas heart stop arrive while out grow.',
    'email': 'wcook@example.com',
    'phone_number': '850.283.0387x15279',
    'json': {
    'name': 'Jeremy Walters',
    'address': '104 Michael Roads\nLifurt, LA 62221',
},
    'key82251': 'value58403',
    'key30116': 'value87441',
    'key83970': 'value41786',
    'key89591': 'value14321',
    'key49523': 'value46748',
    'key89508': 'value75912',
    'key85832': 'value62961',
    'key94421': 'value57449',
},
    {
    'id': 17527489012902,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Matthew Hogan',
    'address': '8330 Joseph Meadow\nNew Crystal, OR 80498',
    'text': 'Size company voice wait computer. Technology road lose specific.\nBenefit knowledge year. Contain quite could one game long any.',
    'email': 'wilkersoneric@example.com',
    'phone_number': '(692)526-4103x303',
    'json': {
    'name': 'Tanya Rice',
    'address': '0274 Simpson Stravenue\nLake April, IN 26285',
},
    'key27421': 'value43657',
    'key18729': 'value14154',
    'key58527': 'value91648',
    'key6573': 'value96162',
    'key95438': 'value63381',
    'key35537': 'value75034',
    'key35817': 'value49551',
    'key40231': 'value73852',
    'key54005': 'value13550',
    'key16616': 'value80791',
},
    {
    'id': 17527489012913,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Blake Atkins',
    'address': 'PSC 9900, Box 7450\nAPO AP 98710',
    'text': 'Reduce wear establish instead. Mean issue guy body. May page central across call.\nBrother individual third up. Mr cultural control material six environmental.',
    'email': 'karenmitchell@example.org',
    'phone_number': '820.613.8051',
    'json': {
    'name': 'April Wright',
    'address': '146 Harrison Drives Apt. 621\nKimberlyhaven, WA 68209',
},
    'key25042': 'value13173',
    'key93419': 'value2157',
    'key35000': 'value45379',
    'key46320': 'value65358',
},
    {
    'id': 17527489012923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Lisa Butler',
    'address': '754 Cheryl Burg Apt. 968\nHarrisonshire, ME 71276',
    'text': 'Might resource weight record management service kid. Building western defense catch third however help.',
    'email': 'maldonadotyler@example.com',
    'phone_number': '287-779-7041',
    'json': {
    'name': 'Sonia Mcbride',
    'address': '56183 John Manors\nAlexandriaview, AK 95409',
},
    'key2857': 'value15951',
    'key6626': 'value45454',
    'key18445': 'value56812',
    'key10210': 'value30371',
    'key98157': 'value89283',
    'key12816': 'value92985',
},
    {
    'id': 17527489012934,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Morgan Bailey',
    'address': '36473 Aguirre Roads Suite 064\nPort Kiaraburgh, AZ 84596',
    'text': 'Recently attention because forward cold people relationship. Able specific at trade under politics sort. Candidate stage close final none family. About reveal service economic page may.',
    'email': 'benjaminevans@example.com',
    'phone_number': '244.899.7596x0644',
    'json': {
    'name': 'Matthew Cooper',
    'address': '803 Perry Alley Apt. 058\nHodgeshire, ND 49779',
},
    'key67763': 'value86181',
    'key93754': 'value5515',
    'key70061': 'value99406',
    'key70141': 'value68991',
    'key23124': 'value784',
    'key80684': 'value25147',
    'key57902': 'value63954',
    'key87614': 'value80479',
    'key70138': 'value15491',
},
    {
    'id': 17527489012945,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Dustin King',
    'address': 'USCGC Crawford\nFPO AE 32611',
    'text': 'Land art image TV. Sister show area daughter.\nWho task despite image over degree.\nEconomy many beat turn. Heart show who local. Clear recent have employee all.',
    'email': 'danielibarra@example.net',
    'phone_number': '8019965287',
    'json': {
    'name': 'Diane Jones',
    'address': '45914 Catherine Lights\nBarnettbury, VT 18818',
},
    'key66460': 'value74165',
    'key11182': 'value65272',
    'key21713': 'value30200',
    'key99509': 'value72616',
    'key34256': 'value9995',
    'key40282': 'value35086',
    'key19620': 'value51815',
    'key97552': 'value62338',
    'key75837': 'value99693',
},
    {
    'id': 17527489012956,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Jennifer Rich',
    'address': '806 Sanchez Parkway\nMichelleburgh, WY 25244',
    'text': 'Personal single open cut make deep page. Region she notice behavior maybe yes.\nLarge she want. South pay million feeling in another young. Hundred detail seek.\nBed entire parent trip charge.',
    'email': 'rleonard@example.net',
    'phone_number': '279.850.4954',
    'json': {
    'name': 'Kathleen Hernandez',
    'address': '934 Billy Path Apt. 717\nBrianamouth, WY 16828',
},
    'key75205': 'value85757',
    'key64020': 'value83042',
    'key30514': 'value96912',
},
    {
    'id': 17527489012967,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Justin Perez II',
    'address': '539 Cheryl Fall\nSandovaltown, FM 99288',
    'text': 'Defense according nice south glass glass hospital town. Letter six trouble among. As single long.\nBeyond per live common. Challenge theory return soldier option.',
    'email': 'juliejohnson@example.com',
    'phone_number': '520.428.2873x1472',
    'json': {
    'name': 'James Miller',
    'address': '547 Melissa Circles Apt. 171\nAshleychester, AR 40457',
},
    'key96038': 'value30096',
    'key56827': 'value87357',
},
    {
    'id': 17527489012979,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Matthew Berry',
    'address': 'Unit 4251 Box 0247\nDPO AA 40971',
    'text': 'Tell religious arrive. Family tend movie top perhaps little. Sell break wish participant.\nDrop support garden father career. Market education analysis suddenly hold institution center government.',
    'email': 'xstevens@example.org',
    'phone_number': '(316)520-0923x322',
    'json': {
    'name': 'Emily Rodriguez',
    'address': 'Unit 0895 Box 4751\nDPO AA 21626',
},
    'key56526': 'value15752',
    'key56250': 'value9389',
    'key29995': 'value86890',
    'key25632': 'value83993',
    'key34245': 'value28483',
    'key51899': 'value28274',
    'key9255': 'value89349',
    'key89848': 'value93106',
},
    {
    'id': 17527489012986,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Nicole Mayo',
    'address': '332 Anderson Green\nMorganfort, IL 43707',
    'text': 'Best shake win way everybody card. Single across drive. Rock medical morning without likely computer manager respond.',
    'email': 'autumnmiller@example.org',
    'phone_number': '(911)681-1927',
    'json': {
    'name': 'Mrs. Kristin Campbell',
    'address': '409 Smith Landing Apt. 609\nStephentown, MN 45543',
},
    'key2424': 'value11149',
    'key14478': 'value96934',
    'key71494': 'value68605',
    'key65039': 'value95531',
    'key99990': 'value99705',
},
    {
    'id': 17527489012997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Margaret Thomas',
    'address': '60616 Fox Ramp\nSouth Anthonymouth, NV 62128',
    'text': 'Design bag defense week key stuff. Smile together civil nature else study. Simply cover sound process.',
    'email': 'ojoyce@example.org',
    'phone_number': '+1-660-930-6956',
    'json': {
    'name': 'Jeff Martin',
    'address': '7172 Andrew Route\nPort Monicafurt, MS 68135',
},
    'key63222': 'value5595',
    'key77025': 'value84536',
    'key36944': 'value64529',
    'key76856': 'value82939',
    'key14191': 'value12214',
    'key6799': 'value31603',
},
    {
    'id': 17527489013008,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Tammy Hughes',
    'address': '215 John Unions\nNorth Christine, RI 93688',
    'text': 'Difficult person generation during. Section go author.\nRead one as wish. Fish start too might.',
    'email': 'sydney73@example.org',
    'phone_number': '494-670-9689',
    'json': {
    'name': 'Phyllis Tanner',
    'address': '507 Melinda Loaf\nHeatherside, WY 75106',
},
    'key27264': 'value37154',
},
    {
    'id': 17527489013018,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Anthony Gonzalez',
    'address': '484 Jamie Stravenue Suite 264\nWest Tashaview, NV 49104',
    'text': 'Always believe dream another sing white. Story against across similar foreign letter article.\nStill window yard democratic often to small.',
    'email': 'heather41@example.net',
    'phone_number': '593.407.8504x81443',
    'json': {
    'name': 'Brian Mckee',
    'address': '04804 Mitchell Spur\nSouth John, NH 77669',
},
    'key81208': 'value97167',
},
    {
    'id': 17527489013028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Stephen Novak',
    'address': '89395 Phelps Terrace\nNorth Richardchester, AZ 28390',
    'text': 'Stage administration call floor. Social detail others increase.\nRange rather attorney eat final. Summer ready task.',
    'email': 'schmidttonya@example.net',
    'phone_number': '278-561-1401x3067',
    'json': {
    'name': 'Kayla Tate',
    'address': '40310 Lynch Motorway Suite 377\nAndrewbury, VA 34288',
},
    'key5348': 'value84619',
    'key24435': 'value45389',
    'key90528': 'value44371',
    'key72858': 'value54908',
    'key44654': 'value17778',
    'key85758': 'value78595',
},
    {
    'id': 17527489013040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Amber Brown',
    'address': '04721 Daniel Rest\nPort Michael, ME 36293',
    'text': 'City new seven whatever understand society. Whole yes deep land least us.\nEight evening past top say. Show attorney dream two then.',
    'email': 'juliemartinez@example.org',
    'phone_number': '234.886.1442x537',
    'json': {
    'name': 'Walter Shea',
    'address': '6245 Rice Mission Suite 761\nEast Kenneth, OR 89589',
},
    'key21653': 'value55521',
    'key79041': 'value18619',
    'key55917': 'value38903',
},
    {
    'id': 17527489013051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Alex Hernandez',
    'address': '391 Zachary Drive\nSouth Daniel, GA 35240',
    'text': 'Kind deep bar military vote imagine manage. Ok fine how whether religious. Knowledge speak its only only leave discussion.\nReveal course natural send. Letter sure campaign off.',
    'email': 'millslisa@example.net',
    'phone_number': '+1-324-286-5793x9040',
    'json': {
    'name': 'Todd Stone',
    'address': '67630 Levine Trail\nSouth Kathryn, KS 55973',
},
    'key42827': 'value96742',
},
    {
    'id': 17527489013062,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Lindsey Smith',
    'address': 'USNV Smith\nFPO AE 98356',
    'text': 'Necessary owner community tax certainly environmental baby between. Generation certain five parent sing. Character past wish among land under.\nPersonal role lose wear short.',
    'email': 'barbarawilson@example.net',
    'phone_number': '(638)224-0554x3688',
    'json': {
    'name': 'Jason Soto',
    'address': '2205 Maxwell Burg Suite 602\nRamirezborough, MD 87298',
},
    'key55894': 'value17856',
    'key59072': 'value1391',
},
    {
    'id': 17527489013073,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'William Cooper',
    'address': '51180 Lane Points Suite 140\nKristiville, DE 38665',
    'text': 'Some central nation trade consider example. Effort federal knowledge.\nSuch security include. Blood federal act sense expect.',
    'email': 'johnsonrebecca@example.org',
    'phone_number': '001-627-660-3066x4441',
    'json': {
    'name': 'Kristin Owens',
    'address': '2938 Webb Shoal Suite 244\nEast Jessica, MN 20070',
},
    'key80212': 'value38582',
    'key43771': 'value12657',
    'key38601': 'value20869',
    'key35688': 'value76274',
    'key74424': 'value66283',
    'key5923': 'value56219',
    'key92336': 'value53088',
    'key67281': 'value17564',
},
    {
    'id': 17527489013084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Billy Macdonald',
    'address': 'PSC 4518, Box 7697\nAPO AE 34182',
    'text': 'Since believe through must production player maintain. Already night board natural daughter. Detail news fight perhaps bad.',
    'email': 'jjames@example.net',
    'phone_number': '336-511-4231x83107',
    'json': {
    'name': 'Brandy Williams',
    'address': '0247 Kevin Points\nMosleytown, CO 60773',
},
    'key58667': 'value37019',
    'key16402': 'value16224',
    'key28958': 'value79436',
    'key92861': 'value72026',
    'key14494': 'value1806',
    'key29020': 'value82724',
    'key10758': 'value73409',
    'key65635': 'value2968',
    'key79644': 'value18493',
    'key55368': 'value76992',
},
    {
    'id': 17527489013093,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Jennifer Chandler',
    'address': '0819 Phillips Square Suite 884\nAprilchester, LA 01459',
    'text': 'Boy language growth raise. Here control feel find table. Quickly hope practice information recent.\nContinue heart visit pick. Interest exist pattern.\nCentral animal sit key director turn summer.',
    'email': 'ellen38@example.org',
    'phone_number': '(929)508-7897',
    'json': {
    'name': 'Martha Smith',
    'address': '25648 Eugene Stream Suite 895\nEast Sethmouth, IA 12743',
},
    'key81485': 'value88007',
    'key87616': 'value18755',
    'key86549': 'value32451',
    'key24667': 'value72623',
    'key89314': 'value83234',
    'key4850': 'value26586',
},
    {
    'id': 17527489013104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Catherine Choi',
    'address': '201 Alexis Rapids\nPort Sydney, WV 10333',
    'text': 'Carry remain into happy part age. Hotel team I step born hear among newspaper.\nYear low resource usually red door campaign approach. Improve artist front. Trouble career focus eight.',
    'email': 'matthewmorgan@example.net',
    'phone_number': '344.907.1822x9377',
    'json': {
    'name': 'Stephen Washington',
    'address': '032 Crystal Track\nSouth Alexander, FM 98391',
},
    'key62162': 'value48462',
    'key22880': 'value70674',
    'key74667': 'value95736',
    'key34417': 'value68031',
    'key36354': 'value75401',
    'key69790': 'value94103',
    'key19490': 'value17549',
    'key80426': 'value67924',
    'key27457': 'value84404',
    'key55291': 'value15685',
},
    {
    'id': 17527489013114,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Erika Bell',
    'address': '50628 Oneal Terrace\nWest Amandaview, FL 80951',
    'text': 'Tree often remain at. Figure arm evening clearly another. One late speech staff main.\nWeight lead along suggest generation choose drive traditional. Beat first world race suffer police new.',
    'email': 'melissa31@example.com',
    'phone_number': '+1-923-529-0966x76443',
    'json': {
    'name': 'Sarah Johnson',
    'address': '380 Moore Trail Apt. 681\nPort David, GU 84127',
},
    'key54752': 'value92969',
    'key63802': 'value95583',
    'key44227': 'value60586',
    'key12052': 'value13522',
    'key27234': 'value57191',
},
    {
    'id': 17527489013125,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Christian Mullen',
    'address': '61951 Martin Spring\nAnnton, IA 99643',
    'text': 'Decision keep father system. Check rule nothing positive. Age pull firm local do. While almost realize raise.\nAlone player kitchen old back yeah position fire.',
    'email': 'lopezsergio@example.org',
    'phone_number': '(472)727-1631',
    'json': {
    'name': 'Michelle Strickland',
    'address': '7817 Wendy Gateway Suite 606\nPortermouth, NC 32755',
},
    'key14287': 'value52152',
    'key24451': 'value20412',
    'key2613': 'value1448',
    'key86715': 'value96596',
    'key70046': 'value5099',
},
    {
    'id': 17527489013137,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Heather Reyes',
    'address': '856 Turner Mountains\nPeterton, KY 65315',
    'text': 'Become assume want war use middle manage. So agent opportunity stand chair. Imagine do notice thing capital serve.\nUs school serious crime worry able. Simple bar onto candidate.',
    'email': 'mark98@example.net',
    'phone_number': '(479)461-2778',
    'json': {
    'name': 'Erika Maxwell MD',
    'address': '4744 Austin Summit\nAdamberg, DC 11945',
},
    'key48086': 'value27879',
    'key14438': 'value82942',
    'key38981': 'value54848',
    'key98406': 'value48114',
},
    {
    'id': 17527489013146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Gloria Campbell',
    'address': '76799 Parsons River\nMarkbury, IA 21982',
    'text': 'I camera such price impact price four. Compare attack glass building like.\nLong range test TV best including not. Other administration staff draw poor respond student.',
    'email': 'dpayne@example.com',
    'phone_number': '757-865-6845x4841',
    'json': {
    'name': 'Trevor Sullivan',
    'address': '83151 Sandra Turnpike\nLewisside, KY 90397',
},
    'key65944': 'value41121',
    'key47013': 'value68365',
    'key98867': 'value9675',
    'key59966': 'value51015',
    'key25103': 'value3242',
    'key20176': 'value97749',
    'key28575': 'value87417',
    'key52160': 'value67467',
    'key85285': 'value95007',
    'key9511': 'value54604',
},
    {
    'id': 17527489013157,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Hector Jones',
    'address': '56987 Elliott Keys Apt. 606\nSophiachester, MO 79834',
    'text': 'Recently evening fear lawyer make. Environmental walk good analysis. Its sort head.',
    'email': 'zbarajas@example.net',
    'phone_number': '001-450-841-1792x080',
    'json': {
    'name': 'Jerry Miller',
    'address': 'PSC 5539, Box 5112\nAPO AE 84521',
},
    'key26994': 'value83975',
},
    {
    'id': 17527489013166,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Karl Thompson',
    'address': 'USNV Wilson\nFPO AA 00502',
    'text': 'Put hold prove share. Nice stuff will.\nAdministration professional offer play thousand member. Significant piece leg. Attorney theory class view.',
    'email': 'michaelthomas@example.net',
    'phone_number': '939-844-1579',
    'json': {
    'name': 'Robert Gibbs',
    'address': '0757 Jonathan Way Suite 589\nDavisbury, GA 09095',
},
    'key17591': 'value42838',
    'key45325': 'value97871',
    'key37681': 'value22563',
    'key86685': 'value75525',
},
    {
    'id': 17527489013176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Angela Harris',
    'address': '832 Townsend Turnpike\nChristophermouth, UT 50713',
    'text': 'Start no father. Plan century and. Experience minute bad sound some process put accept.\nNation great door shoulder child medical help. Boy tonight begin.',
    'email': 'hawkinsemily@example.net',
    'phone_number': '493.531.1269',
    'json': {
    'name': 'Jill Graham',
    'address': '87629 Christian Stravenue\nLake Christinefort, WY 06208',
},
    'key77898': 'value81431',
},
    {
    'id': 17527489013188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Wesley Gregory',
    'address': '9330 Max Highway Suite 374\nDavidmouth, AK 89790',
    'text': 'Leave skin doctor probably show language past.\nBeautiful his operation rule alone. Long customer thing together professional.\nRight us return throw consider. Drive foreign general maintain.',
    'email': 'jessicapeters@example.org',
    'phone_number': '525-398-6804x73381',
    'json': {
    'name': 'Lori Garcia',
    'address': '13721 Martin Pass Suite 474\nLake Matthew, NY 19790',
},
    'key27969': 'value22520',
    'key95097': 'value58984',
    'key97016': 'value66531',
    'key83837': 'value34353',
    'key85075': 'value10480',
    'key85435': 'value95888',
    'key83621': 'value93936',
    'key20688': 'value12608',
},
    {
    'id': 17527489013200,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Amy James',
    'address': '4850 Benjamin Unions Suite 182\nLake Andrew, ID 82860',
    'text': 'Safe wrong style effect. After response on. Live practice foreign.\nAdministration local mother often. Good perform ball single. Task real protect school.',
    'email': 'timothyhernandez@example.net',
    'phone_number': '+1-584-280-5874',
    'json': {
    'name': 'Dylan Stephens',
    'address': '88354 Kimberly Passage\nSouth Michelleside, IL 78747',
},
    'key64296': 'value79708',
    'key39128': 'value87541',
    'key12437': 'value37493',
    'key27490': 'value5159',
    'key67619': 'value10833',
    'key13033': 'value793',
    'key31952': 'value43828',
    'key5707': 'value4528',
    'key78126': 'value25830',
    'key85560': 'value47845',
},
    {
    'id': 17527489013211,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Victoria Morris',
    'address': '797 David Summit Suite 565\nNorth Cynthiaburgh, MN 49664',
    'text': 'Grow point need treat.\nRead name end next. Radio cultural ask because.',
    'email': 'johnathancox@example.org',
    'phone_number': '001-853-884-7358x972',
    'json': {
    'name': 'Anna Taylor',
    'address': '180 Elizabeth Underpass Suite 016\nNew Shannonport, PR 67783',
},
    'key66067': 'value60812',
    'key23286': 'value51723',
    'key57977': 'value56013',
    'key58182': 'value29110',
    'key10646': 'value44908',
    'key87498': 'value43577',
},
    {
    'id': 17527489013222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Jennifer Fernandez',
    'address': '61751 Price Mountain Suite 611\nReyeschester, NE 97556',
    'text': 'Water hear just thing. Debate once enough team. Watch town arm free.\nNotice truth item majority name. Money week company bag.\nMr easy personal best.\nLand degree book without.',
    'email': 'kenneth12@example.org',
    'phone_number': '001-358-267-0787',
    'json': {
    'name': 'Jennifer Lane',
    'address': '5739 Gerald Turnpike Suite 687\nAndreberg, WY 20266',
},
    'key59137': 'value90359',
    'key4117': 'value93704',
    'key61719': 'value32648',
    'key4580': 'value6460',
},
    {
    'id': 17527489013233,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Stacy White',
    'address': '51588 Jasmine Track\nSanfordshire, UT 53243',
    'text': 'Be design behind send cover push table. Too environmental either organization.\nSend point star. Occur tonight story happen country voice go.',
    'email': 'roymichelle@example.org',
    'phone_number': '+1-500-395-9679x49534',
    'json': {
    'name': 'Kenneth Shaw',
    'address': '793 Gabrielle Gardens\nNew Juliaview, ID 26333',
},
    'key65528': 'value39038',
    'key90923': 'value28073',
    'key84373': 'value29258',
},
    {
    'id': 17527489013244,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Tonya Serrano',
    'address': '9312 Gary Groves\nLake Kaitlin, UT 51289',
    'text': 'Expect book behind long thus trip serious.\nCould company pretty stock take. Training poor rich. Character vote how alone oil drop believe.',
    'email': 'perezanthony@example.org',
    'phone_number': '6316974661',
    'json': {
    'name': 'Morgan Mendez',
    'address': '085 Martin Camp Apt. 288\nTiffanymouth, GA 63963',
},
    'key18162': 'value81852',
    'key58764': 'value45540',
    'key46539': 'value25748',
    'key75584': 'value57482',
    'key1597': 'value57181',
},
    {
    'id': 17527489013255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Maria Gomez',
    'address': '746 Tony Stravenue Suite 061\nNorth Jeffery, MT 71699',
    'text': 'Shoulder pull drop class often.\nProbably might seat dog. Specific identify oil country.\nOfficial per decision serve Mrs.',
    'email': 'nicholsonwilliam@example.net',
    'phone_number': '253-402-7209',
    'json': {
    'name': 'Edgar Chung',
    'address': '011 Cummings Forges Apt. 475\nGreenshire, VA 67497',
},
    'key92636': 'value55831',
    'key74312': 'value7941',
    'key20295': 'value23093',
},
    {
    'id': 17527489013267,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Michael Moon',
    'address': '30591 Medina Isle Apt. 943\nDaniellestad, CA 83212',
    'text': 'Soldier rise couple ahead feel. Those able cover weight hard analysis sister major. Skill network situation edge take near.',
    'email': 'ronnie50@example.org',
    'phone_number': '506-596-6474x680',
    'json': {
    'name': 'Julian Macdonald',
    'address': '68520 Murray Roads Suite 405\nJosephland, NJ 63151',
},
    'key13905': 'value36357',
    'key39560': 'value13642',
    'key717': 'value16671',
    'key38615': 'value6191',
    'key57072': 'value54991',
    'key90299': 'value49343',
    'key18054': 'value97108',
},
    {
    'id': 17527489013278,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Christopher Stanley',
    'address': '041 Schroeder Dale\nRomanborough, KY 06874',
    'text': 'Tonight somebody try. Improve on cover crime in blue.\nMillion scene improve career movement theory garden. Certain edge today sure purpose rock. Police just section pull animal live.',
    'email': 'josephsnow@example.com',
    'phone_number': '246-351-0392',
    'json': {
    'name': 'Jamie Young',
    'address': '905 Yolanda Loaf\nNorth Ronaldview, MD 26989',
},
    'key29296': 'value71877',
    'key15472': 'value52905',
    'key56185': 'value98408',
    'key14514': 'value72624',
    'key44499': 'value11249',
    'key65903': 'value56543',
    'key87330': 'value72440',
},
    {
    'id': 17527489013290,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Patricia Austin',
    'address': '324 Jeffrey Courts Apt. 457\nDavismouth, RI 57158',
    'text': 'Without hospital east impact hot work. Foreign do push remember stay prevent eight few.',
    'email': 'courtneyreynolds@example.com',
    'phone_number': '716.627.7857',
    'json': {
    'name': 'Isaiah Allen',
    'address': '07770 Rose Cliff Suite 559\nWilsonview, CT 16253',
},
    'key25925': 'value91914',
    'key90363': 'value45339',
    'key72144': 'value8379',
    'key39278': 'value20618',
    'key50302': 'value14665',
    'key65577': 'value41634',
    'key11456': 'value27985',
},
    {
    'id': 17527489013302,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Charles Kim',
    'address': '47499 Burgess Path Apt. 132\nCraigmouth, NE 26042',
    'text': 'Chair color fall medical. Visit these southern them speak open mother line.',
    'email': 'richardsraven@example.org',
    'phone_number': '597.567.3820',
    'json': {
    'name': 'Margaret Hendricks',
    'address': '1153 Nelson Square Apt. 412\nSandersmouth, FL 41857',
},
    'key66663': 'value67692',
    'key73454': 'value67642',
    'key16800': 'value54062',
    'key58056': 'value91963',
    'key58703': 'value18351',
},
    {
    'id': 17527489013314,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'David Perez',
    'address': '2074 Peterson Pines Apt. 638\nNorth Ronald, VI 81672',
    'text': 'Source fill performance walk big foot grow.\nEarly easy specific myself report surface. Fire level itself power note price choice yet.',
    'email': 'jenniferwatts@example.com',
    'phone_number': '392-220-9385',
    'json': {
    'name': 'Daniel Mcintosh MD',
    'address': '895 Brad Station\nTuckerberg, KS 15887',
},
    'key87996': 'value87135',
    'key64891': 'value56648',
    'key46722': 'value59495',
    'key55363': 'value49073',
    'key79394': 'value41877',
    'key94444': 'value40017',
    'key5543': 'value79792',
    'key88670': 'value30195',
    'key25518': 'value27166',
    'key80751': 'value12957',
},
    {
    'id': 17527489013325,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Michelle Humphrey',
    'address': '7695 Blake Points\nEmilyburgh, WI 30129',
    'text': 'You wait off small popular recent. Away memory compare never. Leg couple organization age reflect again.\nCareer everyone address official character involve government. South result staff find crime.',
    'email': 'stephaniele@example.org',
    'phone_number': '+1-358-213-1340x163',
    'json': {
    'name': 'Peggy Carlson',
    'address': '402 Preston Ports\nEast Emilyfort, NE 06720',
},
    'key33758': 'value9434',
    'key21068': 'value63807',
    'key51434': 'value26081',
    'key3815': 'value76797',
    'key73628': 'value32266',
    'key36595': 'value33816',
    'key54091': 'value91803',
    'key71637': 'value82398',
    'key15898': 'value11269',
},
    {
    'id': 17527489013337,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Miranda Sellers',
    'address': 'USS Lynch\nFPO AA 71246',
    'text': 'Million section tell he. Certain thousand himself want across end.\nRole determine reduce customer institution time. Garden produce whom sure either long agreement.',
    'email': 'fbarrett@example.com',
    'phone_number': '754-405-2271',
    'json': {
    'name': 'Kristie Casey',
    'address': '0617 Michael Villages\nClintonshire, AS 83125',
},
    'key59067': 'value15788',
    'key7666': 'value80400',
    'key43541': 'value77662',
    'key6400': 'value4793',
    'key44853': 'value73272',
    'key55750': 'value51338',
    'key16959': 'value35022',
},
    {
    'id': 17527489013346,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Jackie Christensen',
    'address': '81965 Jones Pass\nSanchezberg, CA 78285',
    'text': 'Sometimes agent bank property. Why team nice body expect modern smile.\nPractice wait value remember remember church. Former smile town nation indeed decision. Town during view floor.',
    'email': 'kennethpena@example.com',
    'phone_number': '8254764207',
    'json': {
    'name': 'Carol Cook',
    'address': '2852 Cox Mountains\nLake Matthew, DE 24797',
},
    'key98213': 'value62021',
    'key89531': 'value71571',
    'key53440': 'value23514',
    'key45406': 'value35170',
    'key94399': 'value12434',
},
    {
    'id': 17527489013357,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Michael Giles',
    'address': '219 Kathy Dam\nSouth Melissaburgh, VA 41706',
    'text': 'Career some himself only can bad.\nDesign someone my heart federal. Age unit hand box produce.\nReturn special first not. Coach star thing.',
    'email': 'robertballard@example.net',
    'phone_number': '001-950-646-4772x351',
    'json': {
    'name': 'Melissa Smith',
    'address': '9014 Meagan Turnpike\nNew Cody, MN 26897',
},
    'key95039': 'value24681',
    'key30103': 'value71234',
    'key44155': 'value76318',
},
    {
    'id': 17527489013369,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Timothy Castro',
    'address': '3344 Amanda Prairie\nCharleneborough, GA 71459',
    'text': 'Western economy expect position memory bill. Per state form exist respond later course. Threat also but relate.',
    'email': 'robindavis@example.org',
    'phone_number': '213-496-7133',
    'json': {
    'name': 'Mrs. Julie Lewis',
    'address': '6315 Kendra Rue\nMarquezview, ID 16068',
},
    'key7715': 'value25163',
    'key24406': 'value45397',
    'key58674': 'value83682',
},
    {
    'id': 17527489013379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Greg Moore',
    'address': '054 Courtney Point Apt. 065\nPort Barbara, DE 22958',
    'text': 'Past wonder sound economic present. Dream job economy. Fly front nothing employee.',
    'email': 'martinjennifer@example.net',
    'phone_number': '550.619.7241',
    'json': {
    'name': 'Julie Adams',
    'address': '89549 Grant Forks Apt. 165\nVeronicaport, GA 85103',
},
    'key82769': 'value46886',
    'key53678': 'value40547',
    'key97490': 'value37885',
},
    {
    'id': 17527489013391,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Calvin Lambert',
    'address': '1164 Miller Fall\nAaronstad, PA 75176',
    'text': 'Head agency attorney. Drug out room interview detail poor deal.\nCertainly through statement anything ability thank could.',
    'email': 'allisonburnett@example.net',
    'phone_number': '805.844.9657x591',
    'json': {
    'name': 'John Chavez',
    'address': '2322 Archer Cliffs Suite 380\nLake Ianstad, NV 43356',
},
    'key55574': 'value21936',
    'key44520': 'value66383',
    'key69456': 'value54759',
    'key4426': 'value31189',
    'key46858': 'value8935',
    'key55154': 'value6688',
    'key44937': 'value62783',
    'key4176': 'value18657',
},
    {
    'id': 17527489013403,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'James Avery',
    'address': '6528 David Turnpike\nAnthonystad, AK 04371',
    'text': 'Make ever degree road subject area. Admit young movement past morning past new three.',
    'email': 'kelleyisaiah@example.com',
    'phone_number': '+1-949-767-0756x902',
    'json': {
    'name': 'Derek Lynch',
    'address': '67483 Taylor Club\nSchroederfort, AL 32836',
},
    'key30930': 'value99610',
    'key24795': 'value94187',
},
    {
    'id': 17527489013413,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Ashley Herman',
    'address': '0040 Robert Tunnel\nAndreahaven, DE 18512',
    'text': 'Moment under per reveal above. You parent budget daughter. Quality he simple physical citizen. If small yes standard investment.\nWhose season for leave. Clearly short once able lay worker.',
    'email': 'roberthawkins@example.net',
    'phone_number': '6935810581',
    'json': {
    'name': 'Courtney Garcia',
    'address': '1280 West Locks Apt. 818\nLake Michael, ND 08554',
},
    'key61430': 'value34370',
    'key13689': 'value27632',
    'key87300': 'value22269',
    'key59940': 'value28608',
    'key48145': 'value75862',
    'key44182': 'value17969',
    'key3975': 'value33154',
    'key1513': 'value65286',
    'key98935': 'value24306',
},
    {
    'id': 17527489013425,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Debra Johnston MD',
    'address': '8195 Joseph Via Apt. 103\nRuizburgh, ME 65601',
    'text': 'Subject travel mean daughter information management individual. Catch magazine job goal and often serious.\nPlant heavy bag. Wonder though hospital end step add.',
    'email': 'tony15@example.org',
    'phone_number': '+1-485-807-0005x3476',
    'json': {
    'name': 'Melissa Schmidt',
    'address': '09221 Ryan Ranch\nNew Barbara, VT 94652',
},
    'key90949': 'value14959',
    'key53682': 'value60853',
},
    {
    'id': 17527489013436,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Martha Smith',
    'address': '36897 Contreras Land\nNorth Sandra, PA 75039',
    'text': 'Knowledge wait provide way sound road total. Cover different economy street property lay strong head.\nForeign off feel paper. Writer speak lot often.',
    'email': 'joseph98@example.net',
    'phone_number': '+1-716-747-2280x0276',
    'json': {
    'name': 'Ronald Hickman',
    'address': '605 Aaron Village\nZacharymouth, DE 57867',
},
    'key41978': 'value70785',
    'key99376': 'value279',
    'key31629': 'value96853',
    'key20159': 'value19243',
    'key28830': 'value81342',
},
    {
    'id': 17527489013446,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Cassie Bell',
    'address': '3289 Natalie Common\nJohnsonbury, AR 97325',
    'text': 'Economic crime tough serious focus class difficult. Picture necessary doctor car a affect visit. Item cause environment hot throw yet spend.',
    'email': 'joseph17@example.org',
    'phone_number': '2859862380',
    'json': {
    'name': 'John Allison',
    'address': '69658 Bolton Trace\nSouth Charles, MA 55454',
},
    'key61851': 'value55327',
    'key24100': 'value31705',
    'key56090': 'value53309',
    'key28043': 'value35398',
    'key47713': 'value41578',
    'key34494': 'value44526',
    'key83042': 'value13896',
},
    {
    'id': 17527489013456,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Samuel Rivers',
    'address': '7940 Kelly Motorway Suite 318\nRobinsonmouth, AZ 08878',
    'text': 'Class one decade approach.\nFront campaign from. Agree me season some similar food home. Million onto model risk never.',
    'email': 'nicholsrobert@example.org',
    'phone_number': '(221)542-3152',
    'json': {
    'name': 'Bill Rosales',
    'address': '20838 Deleon Mews Apt. 143\nAngiemouth, NC 92590',
},
    'key51283': 'value33718',
    'key80885': 'value96818',
},
    {
    'id': 17527489013468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Antonio Gaines',
    'address': '66655 Aaron Inlet Suite 019\nLake Christian, PR 88161',
    'text': 'Cup season energy cold for ability stop. Few important effort usually account. Show wish well political specific property.',
    'email': 'martinezterry@example.com',
    'phone_number': '(569)982-1921x4523',
    'json': {
    'name': 'Samantha Roberson',
    'address': '39685 Guzman Wells\nMaryfurt, OR 07393',
},
    'key46859': 'value47181',
    'key66618': 'value61753',
    'key50210': 'value79265',
    'key68135': 'value49710',
    'key46174': 'value49590',
    'key94596': 'value42277',
    'key84095': 'value73763',
},
    {
    'id': 17527489013479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Patricia Collins',
    'address': '91855 Andrea Run Suite 894\nSouth Andrewland, IN 32619',
    'text': 'Unit their away.\nSecurity mother feeling believe course audience accept writer. Republican affect bar campaign.',
    'email': 'stephen67@example.com',
    'phone_number': '(865)352-4529x55759',
    'json': {
    'name': 'Monica Schmidt',
    'address': '184 Brittney Oval\nAngelafort, RI 37842',
},
    'key9278': 'value40207',
},
    {
    'id': 17527489013490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'David Fox',
    'address': '67323 Scott Turnpike Apt. 482\nSusanhaven, NC 20827',
    'text': 'Figure task attack memory go. Pattern either into fly land.\nCentury much person score. Manage who around approach save economy. Really agreement skill since once.',
    'email': 'harriscody@example.com',
    'phone_number': '+1-366-990-3570x064',
    'json': {
    'name': 'Richard Perez',
    'address': '422 John Ville Suite 259\nBenjaminside, LA 88389',
},
    'key70111': 'value98911',
    'key21777': 'value27404',
    'key66981': 'value70239',
    'key55199': 'value96976',
    'key5956': 'value92363',
    'key44520': 'value89264',
    'key97879': 'value25598',
    'key20693': 'value25369',
    'key98798': 'value35701',
    'key35723': 'value49403',
},
    {
    'id': 17527489013501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Victoria Dougherty',
    'address': '23558 Moreno Locks\nEast Katherine, IL 39708',
    'text': 'Important else run agent some successful. Keep physical beautiful civil wind detail.',
    'email': 'rgonzalez@example.com',
    'phone_number': '335-482-9210',
    'json': {
    'name': 'Jordan Francis',
    'address': '7244 Joshua Spur\nAnnashire, TN 43492',
},
    'key88906': 'value11897',
    'key47201': 'value68910',
    'key78756': 'value10393',
    'key527': 'value17865',
    'key58756': 'value53985',
    'key80577': 'value60744',
    'key81075': 'value42715',
    'key2031': 'value63048',
    'key30912': 'value89253',
},
    {
    'id': 17527489013511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Crystal Cooke',
    'address': '76592 Campos Stravenue\nDevonmouth, NH 40553',
    'text': 'Report dinner first different increase main environment. Behavior performance maybe realize guess include day.',
    'email': 'sharon66@example.com',
    'phone_number': '+1-773-346-4891x20471',
    'json': {
    'name': 'Carmen Moyer',
    'address': '05714 Mayo Turnpike Apt. 939\nNorth Zacharyland, AZ 14580',
},
    'key8801': 'value28987',
    'key49962': 'value62872',
    'key11491': 'value22860',
    'key5019': 'value17509',
    'key82031': 'value22846',
    'key79261': 'value82610',
    'key31243': 'value48974',
    'key95452': 'value52765',
    'key82054': 'value48227',
    'key2311': 'value5486',
},
    {
    'id': 17527489013522,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Wesley West',
    'address': '538 Griffin Mountain Apt. 784\nSouth Tara, MI 39475',
    'text': 'Main late research tonight.\nHealth heart foot police. Study language top cell more.',
    'email': 'cannonjonathan@example.com',
    'phone_number': '+1-608-683-9230x8056',
    'json': {
    'name': 'Marie Burgess',
    'address': '7497 Ferrell Estate Suite 174\nAaronmouth, GA 68765',
},
    'key23506': 'value23052',
    'key13452': 'value11496',
    'key74383': 'value76595',
    'key21306': 'value50751',
    'key37643': 'value79723',
    'key50474': 'value79011',
    'key1727': 'value15496',
},
    {
    'id': 17527489013534,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Penny Ortega',
    'address': '4806 Jeremy Bypass Suite 844\nLake Bonniemouth, NY 26311',
    'text': 'Direction politics energy able structure improve. Road by suddenly pretty away for green. Consumer skin another management.',
    'email': 'david46@example.net',
    'phone_number': '647-909-7501',
    'json': {
    'name': 'Andrea Moss',
    'address': '57575 Savannah Meadow Apt. 484\nHernandezstad, NM 34910',
},
    'key56062': 'value45004',
    'key83887': 'value97025',
    'key44743': 'value80016',
    'key7323': 'value73710',
},
    {
    'id': 17527489013544,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Lisa Baker',
    'address': 'PSC 2217, Box 8532\nAPO AE 78311',
    'text': 'Usually behind worry. Specific finally past keep fish.',
    'email': 'xbarnes@example.net',
    'phone_number': '544.258.4051x48083',
    'json': {
    'name': 'James Ramos',
    'address': '76270 Stevenson Valley Apt. 757\nMichaelbury, AR 42765',
},
    'key33201': 'value93577',
    'key60731': 'value74938',
    'key83321': 'value43060',
    'key75919': 'value38341',
    'key69155': 'value43200',
    'key56895': 'value25282',
    'key8885': 'value79364',
    'key8229': 'value98275',
},
    {
    'id': 17527489013553,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'William Smith',
    'address': '03264 Parker Knoll Apt. 348\nPort Jamesmouth, IA 05178',
    'text': 'Man argue help year person. Others detail prove product. Professor on indeed recent.\nSite purpose friend fund pressure. History best remember after less both.',
    'email': 'joshuagross@example.org',
    'phone_number': '(553)595-2177',
    'json': {
    'name': 'Christina Forbes',
    'address': '3862 Williams Fall Apt. 065\nDevonstad, FM 37250',
},
    'key65162': 'value21822',
    'key67936': 'value24466',
},
    {
    'id': 17527489013565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Miss Olivia Ramirez',
    'address': '1669 Patricia Plains\nCannonland, TN 78136',
    'text': 'Time them for with wrong name represent. Along section home. Thought thing produce them program administration pay. Power suddenly civil cell.',
    'email': 'pburns@example.com',
    'phone_number': '543.459.0686',
    'json': {
    'name': 'Haley Williams',
    'address': '170 Martinez Burg Apt. 091\nLeeland, SD 28160',
},
    'key62051': 'value72174',
},
    {
    'id': 17527489013576,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jason Wood IV',
    'address': '79703 Turner Route Apt. 409\nPort Tammiechester, DE 14493',
    'text': 'Expect else should follow south lead. Their ahead development rock forget brother.\nAge many pattern process system. Family past either Republican glass employee.',
    'email': 'rwiley@example.net',
    'phone_number': '(832)409-9728',
    'json': {
    'name': 'Karen Adams',
    'address': '09164 Amanda Fall\nWest David, AK 91357',
},
    'key20309': 'value50812',
    'key54011': 'value57431',
    'key73632': 'value15572',
    'key29349': 'value96965',
    'key37974': 'value70423',
    'key38153': 'value57839',
    'key4679': 'value87006',
    'key12558': 'value5741',
    'key44337': 'value85107',
    'key32012': 'value39953',
},
    {
    'id': 17527489013587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Alejandro Hood',
    'address': '967 Vaughan Plaza Suite 734\nNorth Tamiview, MN 17256',
    'text': 'Level skill sing capital. Child authority region audience. Word rule attorney care. Line billion politics may.',
    'email': 'fstevenson@example.org',
    'phone_number': '001-536-600-7305',
    'json': {
    'name': 'Anna Pierce',
    'address': '9880 Boyer Points\nMichaelview, TN 77935',
},
    'key37814': 'value2763',
    'key53760': 'value63721',
    'key67061': 'value15261',
    'key87098': 'value41748',
    'key29708': 'value22040',
    'key92280': 'value86596',
    'key73716': 'value27420',
    'key22814': 'value5440',
    'key96115': 'value98631',
    'key96160': 'value6346',
},
    {
    'id': 17527489013598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Michael Dennis',
    'address': '4894 James Point Apt. 924\nSouth Lindaberg, CA 04407',
    'text': 'Share open policy current summer. New herself however actually protect just song. Likely like memory give nearly century.',
    'email': 'brianna60@example.com',
    'phone_number': '001-645-867-8370x4730',
    'json': {
    'name': 'Donald Logan',
    'address': '54291 Elizabeth Junction\nLake Shirley, OK 48564',
},
    'key56852': 'value66122',
},
    {
    'id': 17527489013608,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Angela Lutz',
    'address': '58977 Figueroa Mission\nRoweville, DC 56029',
    'text': 'Race part study performance current reality. Need leader visit leader. Young action push my dog one able piece.\nProve treatment feeling sea PM.',
    'email': 'miguel72@example.net',
    'phone_number': '409-418-8415x43945',
    'json': {
    'name': 'Phillip Jones',
    'address': '72740 Samantha Shore Apt. 436\nSouth Alexandraview, VI 65324',
},
    'key51497': 'value23293',
    'key3076': 'value14515',
    'key49420': 'value61035',
    'key72921': 'value68190',
    'key11587': 'value30615',
},
    {
    'id': 17527489013619,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Justin Smith',
    'address': '5465 Boyer Mount\nNorth Vanessa, NJ 82566',
    'text': 'Decade quite base country beyond occur.\nWord ready behavior.\nAppear find each. Smile source safe six. Voice authority they ask. To next note.\nRest pretty find I. Fall page build continue.',
    'email': 'pnichols@example.net',
    'phone_number': '(543)853-3484x497',
    'json': {
    'name': 'Dustin Taylor',
    'address': '55644 Bowers Parkways\nPort Darrellfort, NE 50313',
},
    'key44788': 'value63914',
    'key92960': 'value57368',
    'key28406': 'value10506',
    'key41655': 'value37875',
    'key47860': 'value90170',
    'key39480': 'value19551',
    'key86886': 'value56884',
    'key97756': 'value36618',
    'key94118': 'value76033',
},
    {
    'id': 17527489013630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Leslie Mitchell',
    'address': '9765 Jacob Knoll\nEast Tony, NY 08200',
    'text': 'Pull now challenge explain professional.\nFriend star my. Green occur then hold exactly.',
    'email': 'timothyross@example.com',
    'phone_number': '624-226-3098x675',
    'json': {
    'name': 'Janice Parsons PhD',
    'address': '115 Lynch Port\nSouth Daniel, GU 25284',
},
    'key41040': 'value67212',
    'key78339': 'value87092',
    'key60527': 'value96602',
    'key32814': 'value92046',
    'key42385': 'value32576',
    'key57882': 'value63147',
    'key32707': 'value98711',
    'key961': 'value97572',
    'key76180': 'value800',
    'key3891': 'value82137',
},
    {
    'id': 17527489013642,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Amanda Smith',
    'address': '2521 Rangel Row Apt. 349\nSweeneyberg, KY 69370',
    'text': 'Use contain general where just. Three better campaign ground finally catch.\nIdentify most fact street final crime. Check establish rich want. Move song recent that win trade PM put.',
    'email': 'fordalyssa@example.org',
    'phone_number': '001-509-742-6300x47528',
    'json': {
    'name': 'Lisa Howell',
    'address': '2351 Seth Hollow\nDrakeside, CA 02631',
},
    'key19791': 'value13214',
},
    {
    'id': 17527489013654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Joshua Carpenter',
    'address': '2028 Sparks Loaf\nQuinnshire, NV 45839',
    'text': 'Health market big. Last Republican business. Everything wait upon.\nNational trouble firm minute process compare head. Full dark put finish well recently. Consider growth or would scientist establish.',
    'email': 'connorvazquez@example.com',
    'phone_number': '001-409-336-2796x61435',
    'json': {
    'name': 'Sylvia Taylor',
    'address': '23828 Blake Flat Apt. 263\nAbigailport, AZ 80416',
},
    'key9104': 'value87404',
    'key49358': 'value60088',
    'key41338': 'value26416',
    'key28634': 'value55237',
    'key39964': 'value7707',
    'key36316': 'value27694',
    'key10241': 'value28742',
    'key69381': 'value35818',
    'key6885': 'value76940',
},
    {
    'id': 17527489013665,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Tommy Rich',
    'address': '9090 Douglas Flats Suite 971\nKellymouth, MS 35315',
    'text': 'Mrs would daughter note sing together claim land.\nSubject industry national growth while.',
    'email': 'reevesgregory@example.org',
    'phone_number': '(477)607-0407x2164',
    'json': {
    'name': 'Yesenia Palmer',
    'address': '6955 Perez Ford\nWest Madison, IN 49705',
},
    'key83616': 'value35118',
    'key11578': 'value35949',
    'key54146': 'value83751',
    'key51181': 'value21839',
},
    {
    'id': 17527489013677,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Joe Hurley',
    'address': '6260 Paula Brook\nNorth Stevenland, ME 35880',
    'text': 'Recent reveal computer majority. Agreement kid most author member budget moment surface. Wish participant job guess none. Hand why them southern important into.\nSoon professional forget firm.',
    'email': 'ssalas@example.com',
    'phone_number': '001-824-295-4292',
    'json': {
    'name': 'William Cook',
    'address': '48400 Oneal Spur Suite 006\nPerezland, FM 31627',
},
    'key1607': 'value48925',
    'key18801': 'value35806',
    'key21033': 'value79522',
    'key85994': 'value62063',
    'key78030': 'value30686',
    'key67382': 'value60047',
    'key34164': 'value41685',
},
    {
    'id': 17527489013688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Meghan Lynch',
    'address': '42709 Shaun Lodge Suite 497\nEast Marilynview, SC 47600',
    'text': 'Like art citizen whole since name. Class write instead institution change former.\nOil let interview involve.',
    'email': 'hbright@example.org',
    'phone_number': '+1-658-528-4061x58712',
    'json': {
    'name': 'Mark Kirk',
    'address': '881 Scott Plaza\nEast Michael, KS 66136',
},
    'key23936': 'value29669',
    'key16221': 'value92411',
    'key34485': 'value73697',
    'key6374': 'value82524',
    'key99837': 'value73057',
    'key22245': 'value38231',
    'key41610': 'value87482',
    'key63347': 'value57904',
    'key61032': 'value43871',
    'key53279': 'value40260',
},
    {
    'id': 17527489013699,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Carol Cisneros',
    'address': '675 Contreras Terrace Apt. 946\nHarrisville, VT 18106',
    'text': 'Example imagine explain safe science. Call color control type his.\nDay suffer response second feel blue. Watch policy still another consider owner compare. While explain find likely area.',
    'email': 'sarahwalsh@example.net',
    'phone_number': '380-455-2520x777',
    'json': {
    'name': 'Derek Frederick',
    'address': '6987 Jose Unions Apt. 295\nSouth Tonya, CT 75861',
},
    'key31804': 'value78384',
},
    {
    'id': 17527489013711,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Rachael Patterson',
    'address': '510 Brown Viaduct\nSouth Melodyfurt, KY 69441',
    'text': 'Glass above campaign against camera campaign represent. Level against message throw.\nWindow reason street technology western. Position mother eat star crime magazine.\nCertain story success.',
    'email': 'ereynolds@example.org',
    'phone_number': '765-218-4650',
    'json': {
    'name': 'Jennifer Avery',
    'address': 'Unit 4561 Box 8935\nDPO AA 80084',
},
    'key20977': 'value54719',
    'key59776': 'value10800',
    'key26507': 'value49416',
    'key51643': 'value83353',
},
    {
    'id': 17527489013720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sarah Ross',
    'address': '9892 Carol Glen\nSouth Todd, CA 45003',
    'text': 'Wrong and even sometimes near end. Record maintain popular year create left trial. Finally serious message recognize Congress to edge.',
    'email': 'deborahdavis@example.net',
    'phone_number': '+1-384-790-4809',
    'json': {
    'name': 'Taylor Anderson',
    'address': '0352 Hughes Canyon Suite 846\nNew Jorgeland, MD 87259',
},
    'key66207': 'value26324',
    'key4572': 'value9482',
    'key89168': 'value18378',
    'key98490': 'value26722',
},
    {
    'id': 17527489013731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jonathan Mclean',
    'address': '754 Debra Throughway\nLake Charlesborough, CO 13211',
    'text': 'Friend glass develop if really cultural. Program between especially form them type production. Fine lose staff.\nPick public quickly whom when professional. Man near speech.',
    'email': 'meghanmason@example.com',
    'phone_number': '+1-429-218-7590x55908',
    'json': {
    'name': 'Kimberly Long',
    'address': '7819 Hunter Tunnel\nSouth Troyville, AS 16339',
},
    'key19037': 'value66074',
    'key63202': 'value68302',
    'key8742': 'value31224',
    'key93195': 'value58070',
    'key46660': 'value27826',
    'key13456': 'value86202',
    'key57060': 'value45402',
    'key27817': 'value70761',
},
    {
    'id': 17527489013742,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Manuel Ball',
    'address': '941 Olsen Road\nEast Sandrashire, IN 24315',
    'text': 'Become project administration stop alone. Move use challenge plan technology tell guy. Cut conference art.\nFall card specific deal week marriage. This low magazine hope foreign.',
    'email': 'acostaryan@example.com',
    'phone_number': '+1-776-259-4901',
    'json': {
    'name': 'Ms. Robin Gallegos',
    'address': '4103 Herrera Plain Suite 322\nMedinastad, KS 59170',
},
    'key6957': 'value55558',
    'key81745': 'value18067',
    'key94048': 'value10753',
    'key24197': 'value49230',
    'key89165': 'value32780',
    'key38420': 'value12992',
    'key16543': 'value34431',
    'key7175': 'value64221',
},
    {
    'id': 17527489013754,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Marcus Pierce',
    'address': '930 Hampton Ford\nCoffeymouth, NH 78702',
    'text': 'Own yes strong never music action. Fly whatever each stop. Act order stuff wife.\nBehavior camera present tough. Turn feeling police step look.',
    'email': 'karen52@example.com',
    'phone_number': '327-214-3485x9332',
    'json': {
    'name': 'Jaime Garcia',
    'address': 'USNS Santos\nFPO AA 41597',
},
    'key47256': 'value1832',
    'key75075': 'value99149',
    'key72480': 'value23864',
    'key91972': 'value89127',
    'key75306': 'value9697',
    'key3508': 'value56394',
    'key93053': 'value91614',
    'key56938': 'value8622',
    'key13746': 'value66813',
},
    {
    'id': 17527489013764,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Anne Russell',
    'address': '00646 Megan Knoll\nEast Kevin, FM 34218',
    'text': 'The relationship book law. Event social according hospital give concern. Moment reality relationship add rock military.\nWhen animal pressure senior. Kid exist letter suddenly.',
    'email': 'jillburton@example.com',
    'phone_number': '(311)670-7742x389',
    'json': {
    'name': 'Ann Hodges',
    'address': '0708 Nicholson Circles\nLake Michelle, MS 21777',
},
    'key83503': 'value16425',
    'key94960': 'value61032',
    'key78209': 'value75617',
    'key41884': 'value45208',
},
    {
    'id': 17527489013775,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Kyle Russell',
    'address': '3197 Jesse Mountain\nSimmonsborough, TN 66077',
    'text': 'Task because current impact girl. Think especially herself.\nSerious through story technology every effort service.',
    'email': 'hhall@example.com',
    'phone_number': '407-656-9229',
    'json': {
    'name': 'Erica Bell',
    'address': '9756 Stafford Centers Suite 960\nEast Reginaldchester, NY 02804',
},
    'key15908': 'value84640',
    'key34069': 'value66760',
},
    {
    'id': 17527489013786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Mr. Steven Miller MD',
    'address': '2917 Fields Locks\nFosterstad, CA 13934',
    'text': 'For cause effort spend. Teach argue keep size. Listen operation opportunity form able stop.\nWin surface early foreign color head process quickly. Eat party culture should training left.',
    'email': 'brian57@example.org',
    'phone_number': '947.999.7321',
    'json': {
    'name': 'Kathryn Mason',
    'address': '929 Hughes Lock\nJohnville, MN 90134',
},
    'key258': 'value20009',
    'key85423': 'value35785',
    'key75698': 'value57716',
    'key44944': 'value85329',
    'key1216': 'value79033',
    'key67917': 'value55447',
    'key66072': 'value22103',
    'key12336': 'value4037',
},
    {
    'id': 17527489013797,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Stacy Walker',
    'address': '9306 Wilson Heights\nPort Jameshaven, WV 48454',
    'text': 'Some though study art war reality you wide. Black behind collection drive stuff project. Care really my open.\nSee health be act center method nothing.',
    'email': 'tjacobs@example.com',
    'phone_number': '001-866-838-2204',
    'json': {
    'name': 'Adam Martinez',
    'address': 'Unit 7972 Box 3274\nDPO AE 84649',
},
    'key99235': 'value86300',
    'key81667': 'value12543',
    'key71159': 'value89285',
    'key37661': 'value59548',
    'key78972': 'value33064',
    'key54979': 'value13849',
},
    {
    'id': 17527489013806,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'David Bennett',
    'address': '71790 Cory Springs Apt. 077\nSouth Amy, FL 86010',
    'text': 'Family lawyer third husband because far. Majority attack land system service old.',
    'email': 'ashley62@example.com',
    'phone_number': '891.766.5068x80807',
    'json': {
    'name': 'William Ward',
    'address': '79517 Thomas Fords Apt. 815\nNorth Lynn, NC 71317',
},
    'key50716': 'value91492',
    'key57725': 'value74445',
    'key77198': 'value62039',
    'key98736': 'value36399',
    'key28633': 'value23944',
    'key90733': 'value52027',
    'key31800': 'value93575',
    'key61022': 'value2600',
},
    {
    'id': 17527489013816,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Mark Lewis',
    'address': 'USCGC Welch\nFPO AA 60827',
    'text': 'Indicate throughout method sure environment another feel always. Wife life evening feeling. Area either model shoulder financial music get.',
    'email': 'daryl84@example.com',
    'phone_number': '735-708-4692x74426',
    'json': {
    'name': 'Gregory Gomez',
    'address': '214 Harris Ports\nDianeport, SC 62849',
},
    'key53937': 'value20136',
    'key17878': 'value43115',
    'key50607': 'value43334',
    'key39179': 'value83829',
    'key21630': 'value36015',
    'key46006': 'value64154',
},
    {
    'id': 17527489013825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Eric Potter',
    'address': '3397 Reginald Passage Apt. 731\nJenniferfort, MI 91902',
    'text': 'Letter well society pull school edge hard. Black raise quite eat law stock. Compare indicate face try future others front note.',
    'email': 'robertsjimmy@example.org',
    'phone_number': '(800)455-0273x59926',
    'json': {
    'name': 'Emily Fowler',
    'address': '611 Alex Springs\nToddton, GA 75210',
},
    'key87893': 'value25338',
    'key73767': 'value23132',
    'key36860': 'value14845',
    'key11392': 'value71751',
    'key227': 'value21540',
    'key57959': 'value19210',
    'key95375': 'value79511',
},
    {
    'id': 17527489013836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Renee Torres',
    'address': '6782 Martinez Avenue Apt. 312\nSouth Toddton, CO 52283',
    'text': 'Man effort name authority read eight. Scene unit girl task mother here.\nScientist discover party pay only probably they. Sell produce sense memory hot heavy. Wrong it per between wear probably.',
    'email': 'hollymcknight@example.org',
    'phone_number': '239.456.6818x7225',
    'json': {
    'name': 'Sydney Sanchez',
    'address': '22546 Wendy Land\nCrawfordmouth, RI 23492',
},
    'key37438': 'value66227',
    'key30922': 'value45570',
    'key29789': 'value50289',
    'key56168': 'value69692',
    'key4437': 'value49368',
    'key87887': 'value56571',
    'key91272': 'value81541',
    'key21316': 'value24172',
    'key47227': 'value12781',
    'key9610': 'value66069',
},
    {
    'id': 17527489013847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Mary Robinson',
    'address': '06822 Wood Mill\nNew Maryton, OR 39141',
    'text': 'Population guy run mission course lose room.',
    'email': 'meltonkimberly@example.org',
    'phone_number': '(293)846-7774x073',
    'json': {
    'name': 'James Hardy',
    'address': 'PSC 3965, Box 4065\nAPO AA 27995',
},
    'key53434': 'value32204',
    'key56890': 'value3247',
    'key88247': 'value87657',
    'key27116': 'value25554',
    'key7960': 'value59797',
},
    {
    'id': 17527489013857,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Tracy Carney',
    'address': '8332 Hardin Trail Suite 263\nJessechester, DE 68116',
    'text': 'Go trouble increase blood agreement. Sense drive reach. Word wear forget second rest begin market.\nFight analysis both interview amount. Offer member or total.',
    'email': 'susan19@example.org',
    'phone_number': '8908735737',
    'json': {
    'name': 'Dr. Willie Hernandez MD',
    'address': '9779 James Viaduct\nNorth Richardbury, AR 49722',
},
    'key91700': 'value1706',
    'key14125': 'value78818',
    'key51706': 'value76767',
    'key21728': 'value97927',
    'key31596': 'value26741',
    'key70296': 'value24352',
    'key67506': 'value44781',
    'key67499': 'value24947',
    'key28848': 'value37218',
},
    {
    'id': 17527489013867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Eric Spencer',
    'address': '99069 Nixon Port Apt. 913\nPort Amanda, PA 48114',
    'text': 'Congress son case. Bring pattern our region behind nation.\nSimple necessary manage would let administration figure from. Student production per heavy.',
    'email': 'diana54@example.net',
    'phone_number': '001-203-878-3153x31849',
    'json': {
    'name': 'Samuel Randall',
    'address': '6486 Richards Trace Suite 286\nJoechester, IA 70230',
},
    'key67831': 'value59093',
    'key15338': 'value38805',
    'key84791': 'value2020',
    'key84427': 'value50867',
    'key84403': 'value73736',
    'key1004': 'value86478',
},
    {
    'id': 17527489013878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Patricia Weiss',
    'address': '324 Jackson Plain\nLake Matthewside, RI 54361',
    'text': 'Simply man blue thing whether few four word.\nCollection long between check apply. Avoid section year wife in without example. Feel write effect Mrs reality.\nAlong pick artist mind point child.',
    'email': 'tiffanywarren@example.net',
    'phone_number': '+1-761-210-2102',
    'json': {
    'name': 'Sally Maddox',
    'address': '14814 Carl Alley\nEast Kristinton, IA 46331',
},
    'key44940': 'value65806',
    'key25387': 'value58620',
    'key27701': 'value90024',
    'key69027': 'value3750',
    'key31999': 'value29424',
    'key7539': 'value11868',
    'key47679': 'value10847',
},
    {
    'id': 17527489013889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Isaiah Flores',
    'address': '903 Hatfield Ridge Suite 434\nChristopherton, WY 73267',
    'text': 'Drug left pay until. Treatment baby test perform but it. Describe away bar out.\nArtist cup walk church. Thing city outside technology strong cover.',
    'email': 'cphillips@example.org',
    'phone_number': '582-274-5450x081',
    'json': {
    'name': 'Kristina Smith',
    'address': '551 Rebecca Glen\nNew Jason, GA 79157',
},
    'key70073': 'value87963',
    'key37252': 'value41730',
    'key40088': 'value64612',
},
    {
    'id': 17527489013900,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Betty Jefferson',
    'address': 'USCGC Vang\nFPO AP 78405',
    'text': 'South information future these game mention. Under key prepare defense. Forget spring standard thousand operation above character process.',
    'email': 'gilbertjustin@example.net',
    'phone_number': '(340)416-8727',
    'json': {
    'name': 'Patrick Burns',
    'address': '324 Stephen Ridges\nEast Kevin, MS 29247',
},
    'key63633': 'value66047',
    'key49315': 'value93092',
    'key45195': 'value55635',
    'key32746': 'value47483',
    'key22064': 'value92453',
    'key51250': 'value79959',
    'key36970': 'value45505',
    'key29455': 'value10228',
    'key42459': 'value62386',
    'key48089': 'value42850',
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
    'RequestId': '9c504aa6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_35_238560YwMJuipF',
    'filter': 'uid >= 0',
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
    'RequestId': '9c504aa6-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_35_238560YwMJuipF',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752748907.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid01752748907Json()
    test.run_tests()
