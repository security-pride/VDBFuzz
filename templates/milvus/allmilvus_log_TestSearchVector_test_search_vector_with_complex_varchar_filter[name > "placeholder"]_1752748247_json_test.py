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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_complex_varchar_filter[name > "placeholder"]_1752748247_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name > "placeholder"]_1752748247.json"
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithComplexVarcharFilterNamePlaceholder1752748247Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name > "placeholder"]_1752748247.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name > "placeholder"]_1752748247.json"
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_38_236022EgyVgppL',
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_38_236022EgyVgppL',
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_38_236022EgyVgppL',
    'data': [
    {
    'id': 17527482442717,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jessica Jones',
    'address': '77727 Cox Locks Suite 282\nWest Kimberly, LA 43961',
    'text': 'Whether history heavy agent total standard fight. Better natural business produce. Authority amount describe black science son realize.',
    'email': 'izimmerman@example.net',
    'phone_number': '838.435.8794',
    'json': {
    'name': 'Valerie Brown',
    'address': 'PSC 4525, Box 8360\nAPO AE 37900',
},
    'key960': 'value62235',
},
    {
    'id': 17527482442732,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Christina Martin',
    'address': '80995 Timothy Courts Apt. 663\nChristinastad, TN 28476',
    'text': 'Such hope catch top pass purpose offer. Cultural something help fish attention paper. Nothing southern thought fast star trouble agreement. Business trip friend together course share eye.',
    'email': 'william16@example.net',
    'phone_number': '478.453.5164',
    'json': {
    'name': 'Paul Anderson',
    'address': '818 Thomas Via Apt. 823\nMarybury, GA 22632',
},
    'key95249': 'value59690',
    'key47300': 'value33994',
    'key98194': 'value2383',
    'key56481': 'value54596',
    'key75445': 'value79986',
    'key23096': 'value98050',
    'key17782': 'value80225',
    'key15578': 'value96546',
},
    {
    'id': 17527482442745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Timothy Gillespie',
    'address': '53504 Tiffany Common Suite 411\nCraigshire, ND 83140',
    'text': 'Yes ago half four why movement get. Former involve professional box forget television week. Year according fly until.\nToward record model single. Medical crime range mean.',
    'email': 'courtney46@example.com',
    'phone_number': '339-927-4470x930',
    'json': {
    'name': 'Emily Robinson',
    'address': '7290 Anderson Forge Apt. 445\nWest Melissa, WA 61184',
},
    'key88200': 'value79619',
    'key91501': 'value41579',
    'key96258': 'value96475',
    'key393': 'value74514',
    'key26556': 'value75166',
    'key30682': 'value78932',
    'key18518': 'value15884',
    'key54794': 'value5102',
    'key57776': 'value33406',
    'key21927': 'value66786',
},
    {
    'id': 17527482442759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Todd Stevens',
    'address': '59931 Gordon Pine Suite 538\nGaryburgh, TN 83089',
    'text': 'One some computer. Attorney late ask.\nLow late minute guy discover. According accept wind. Support thought anyone maybe.\nDiscussion by expert hold my. Seven wait American science fire require find.',
    'email': 'flemingkristie@example.org',
    'phone_number': '632.828.3741x3802',
    'json': {
    'name': 'Joseph Smith',
    'address': '52932 Kathryn Estate Apt. 618\nNew Sylviafort, IL 05345',
},
    'key95247': 'value82186',
    'key77125': 'value60203',
    'key18718': 'value45798',
    'key79852': 'value16765',
    'key40689': 'value39889',
    'key66635': 'value34866',
},
    {
    'id': 17527482442773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Tara Fry',
    'address': '10132 Schmidt Forge\nWilliamland, NE 94330',
    'text': 'Thus their today effect lead certainly. Green both sort run key. Participant music expect central month end.\nScore benefit international politics grow into. Believe item give drive another event top.',
    'email': 'seandougherty@example.net',
    'phone_number': '(660)939-9145x24078',
    'json': {
    'name': 'Yolanda Brown',
    'address': '6220 Susan Turnpike Suite 096\nNew Dillon, MH 58459',
},
    'key31376': 'value1359',
    'key41741': 'value77590',
    'key83365': 'value9059',
},
    {
    'id': 17527482442787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jamie Perry',
    'address': '995 Jonathan Club\nWoodstown, NY 75102',
    'text': 'It century field.\nEast commercial own special million. Within debate style product nation.\nAway approach take participant which market part.\nPay election smile book stuff task chance.',
    'email': 'hstevenson@example.org',
    'phone_number': '323-232-6773x9662',
    'json': {
    'name': 'Gwendolyn Ryan',
    'address': '460 Ashley Stravenue Suite 851\nEast Teresaberg, LA 70435',
},
    'key33018': 'value45736',
    'key86409': 'value21727',
    'key56191': 'value83855',
    'key74583': 'value37909',
    'key78658': 'value44459',
    'key80998': 'value99860',
    'key52928': 'value47348',
},
    {
    'id': 17527482442801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Nathan Hughes',
    'address': '91000 Cannon Court Suite 471\nSouth Nicole, MT 37981',
    'text': 'Sense professor sell piece position meeting. True mouth full maintain smile.\nDefense on even serve order. Listen fall compare give especially compare.\nParticular policy eight usually can him stay.',
    'email': 'laurenosborne@example.net',
    'phone_number': '+1-834-403-4852',
    'json': {
    'name': 'Shawn Gonzalez',
    'address': '62488 Henry Mill\nSmithport, PA 18129',
},
    'key75760': 'value27531',
    'key54735': 'value59126',
    'key98084': 'value30017',
    'key29764': 'value77399',
    'key17490': 'value63885',
    'key11866': 'value55183',
    'key78878': 'value84439',
},
    {
    'id': 17527482442814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Andrew Stevens',
    'address': '31127 Kaylee Underpass Apt. 180\nChristymouth, MI 76331',
    'text': 'See true get positive let mission. Wall describe born local. See follow do high. Any conference agent seven.\nCrime try service resource. Onto carry figure car size. Else money college.',
    'email': 'xandrews@example.org',
    'phone_number': '565-349-7899',
    'json': {
    'name': 'Matthew Hampton',
    'address': '5409 Watkins Mount Suite 982\nKyleton, AZ 75445',
},
    'key32168': 'value74150',
    'key42026': 'value33812',
    'key39569': 'value93777',
    'key52980': 'value2063',
    'key37603': 'value56879',
    'key41166': 'value37480',
    'key3708': 'value27091',
    'key70687': 'value89486',
    'key85831': 'value99411',
},
    {
    'id': 17527482442826,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Matthew Lee',
    'address': '835 Daniel Extension\nNataliestad, KY 62503',
    'text': 'Task cost prepare social black. Response sign trip against language billion point. Very collection grow view support.',
    'email': 'susansullivan@example.org',
    'phone_number': '237.460.5876x9940',
    'json': {
    'name': 'Edward Santiago',
    'address': '481 Wallace Centers Apt. 710\nRamirezberg, TN 56751',
},
    'key76882': 'value57516',
    'key64848': 'value76333',
    'key71971': 'value50263',
    'key98800': 'value91181',
    'key18366': 'value9859',
},
    {
    'id': 17527482442838,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Lisa Moreno',
    'address': '787 Johnson Park Suite 079\nShannonfort, LA 59671',
    'text': 'Plan participant identify hit Mr. Whom room rule.\nCut represent mind face determine into enough. Address majority authority box issue letter effort. Work half son science arm claim event.',
    'email': 'ericmoore@example.net',
    'phone_number': '(304)923-2104',
    'json': {
    'name': 'Matthew Fitzgerald',
    'address': '39217 Fisher Common Suite 564\nSouth William, AK 23452',
},
    'key28803': 'value89353',
},
    {
    'id': 17527482442850,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Lisa Smith',
    'address': 'USCGC Yoder\nFPO AE 30998',
    'text': 'Remember represent picture market. Have drug effort every. Open former probably end edge.\nWhile deep far they use.',
    'email': 'heather87@example.com',
    'phone_number': '(402)859-1863',
    'json': {
    'name': 'John Ballard',
    'address': '3030 Herrera Forges Suite 236\nChristianmouth, IL 47965',
},
    'key46039': 'value43320',
},
    {
    'id': 17527482442861,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Kevin Taylor',
    'address': 'USS Walters\nFPO AP 46358',
    'text': 'Focus particularly likely face price. When economic that majority direction beat picture.',
    'email': 'owright@example.org',
    'phone_number': '(970)610-0844',
    'json': {
    'name': 'Angela Ray',
    'address': '056 Nixon Trail Suite 554\nNorth Jennyland, WA 80675',
},
    'key66598': 'value72155',
    'key25320': 'value61029',
    'key47032': 'value84439',
    'key48955': 'value58593',
    'key68640': 'value3947',
},
    {
    'id': 17527482442871,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Sandra Parker',
    'address': '4104 Mayo Freeway Suite 427\nNorth Allison, OR 71638',
    'text': 'Spring draw scene her far world budget. Civil usually heavy oil fly ahead attorney.\nDiscussion both act stock history TV mind. Teacher serve continue buy commercial school.',
    'email': 'brandon45@example.net',
    'phone_number': '001-858-660-7448x526',
    'json': {
    'name': 'Kimberly Perez',
    'address': '13958 Jessica Square Apt. 460\nNew Brandon, NM 18294',
},
    'key34953': 'value74206',
    'key99723': 'value40299',
    'key88674': 'value28039',
    'key81729': 'value52129',
    'key61643': 'value28489',
    'key93928': 'value61332',
    'key67540': 'value31757',
    'key79060': 'value98952',
    'key60262': 'value49829',
    'key18034': 'value3621',
},
    {
    'id': 17527482442882,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Mark Nunez',
    'address': '1200 Heather Isle\nNew Emilyburgh, IL 26702',
    'text': 'Author sit staff side important offer probably. Bring so source culture system should point attack. Evening figure hope important space.',
    'email': 'vtran@example.com',
    'phone_number': '001-715-832-3559x245',
    'json': {
    'name': 'Michelle Ramirez',
    'address': 'USNS Nixon\nFPO AP 26411',
},
    'key6073': 'value597',
},
    {
    'id': 17527482442892,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Ronald Townsend',
    'address': '4351 Diaz Prairie\nWest Elizabeth, NE 08748',
    'text': 'She fish hospital. Close tonight expect travel movie. Area financial medical name would baby. Production receive national dream you line actually opportunity.',
    'email': 'ibrandt@example.com',
    'phone_number': '+1-305-489-4167x53802',
    'json': {
    'name': 'Jennifer Knight',
    'address': '739 Lester Plaza\nSusanborough, PA 02482',
},
    'key90113': 'value3359',
    'key57800': 'value61728',
    'key25000': 'value92553',
    'key73200': 'value10069',
    'key54698': 'value36290',
},
    {
    'id': 17527482442902,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Anthony Robinson',
    'address': '152 Joshua Alley Suite 151\nSouth Ricardohaven, HI 48205',
    'text': 'Center hold must speech little. Next why capital act.\nArm reality contain. Month onto and though authority. Four compare American car heavy above open.',
    'email': 'chelsea19@example.com',
    'phone_number': '001-293-503-6132',
    'json': {
    'name': 'Glenn Webster',
    'address': '8669 Mary Union Apt. 328\nPort Olivialand, KY 09114',
},
    'key3981': 'value28419',
    'key32541': 'value27923',
    'key26216': 'value38095',
    'key56523': 'value56341',
    'key52075': 'value93637',
    'key94871': 'value43879',
    'key48934': 'value84481',
    'key76416': 'value9644',
    'key27024': 'value20067',
},
    {
    'id': 17527482442912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Michael Daniels',
    'address': '925 Stone Run\nRobinsonmouth, HI 28683',
    'text': 'Its prove watch thousand remember give pay. Tv charge century friend ever front. Last accept time plant which generation turn.\nRed if tell home little our size. Anyone young could design lay.',
    'email': 'bellpenny@example.org',
    'phone_number': '741.281.0648',
    'json': {
    'name': 'Jason Williams',
    'address': '68252 Wade Extensions Suite 992\nSouth James, TN 58124',
},
    'key3383': 'value8351',
    'key62180': 'value52908',
    'key13720': 'value5636',
    'key44655': 'value90989',
    'key54828': 'value13928',
    'key97071': 'value53289',
    'key85600': 'value12178',
    'key44345': 'value28194',
    'key31543': 'value34546',
    'key19524': 'value26512',
},
    {
    'id': 17527482442923,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'William Glenn',
    'address': '8947 Rodriguez Lane\nLake Don, ME 05692',
    'text': 'Suggest drug check. Community responsibility inside attention too.\nSomeone service myself production challenge. Nothing rather make yet price be baby. Strategy like land tell between production.',
    'email': 'emily72@example.net',
    'phone_number': '+1-424-753-5166',
    'json': {
    'name': 'Christopher Stone',
    'address': '79892 Bell Divide\nNew Bryanfort, ID 05289',
},
    'key74723': 'value7038',
    'key8364': 'value49375',
    'key19476': 'value54929',
    'key39152': 'value92126',
    'key61494': 'value70170',
    'key66363': 'value78274',
    'key95779': 'value42504',
},
    {
    'id': 17527482442934,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Christina Doyle',
    'address': '22750 Neal Common\nWest Angela, TN 43599',
    'text': 'Heavy color him position support TV. Course young war talk common Republican center anything. According military into feeling rest.\nKnowledge thought half. A another summer site sense.',
    'email': 'kristin56@example.org',
    'phone_number': '9615125124',
    'json': {
    'name': 'Joseph Hampton',
    'address': '8478 Angela Valleys Suite 764\nScottchester, WV 70491',
},
    'key26611': 'value56806',
    'key33273': 'value63423',
    'key7010': 'value46583',
    'key29403': 'value79108',
    'key26211': 'value16403',
},
    {
    'id': 17527482442945,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Andre Rice',
    'address': '358 Gary Forest\nNorth James, PW 02546',
    'text': 'Green might pull a success than. Leg sort town able source.\nEach push probably keep would including deal. Serious home cost country control art design.',
    'email': 'deborah37@example.com',
    'phone_number': '(204)866-2640x93946',
    'json': {
    'name': 'Dennis Bridges',
    'address': 'PSC 6651, Box 2308\nAPO AE 93454',
},
    'key19219': 'value26766',
    'key15611': 'value11266',
    'key77343': 'value82298',
    'key14476': 'value21575',
    'key53705': 'value42642',
    'key81301': 'value82165',
    'key60910': 'value26520',
    'key52257': 'value59383',
    'key4056': 'value34618',
    'key76151': 'value85834',
},
    {
    'id': 17527482442953,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Matthew Scott',
    'address': '156 Rodriguez Hills Apt. 870\nSouth Melindatown, MN 28733',
    'text': 'Want our entire southern. Indicate station his with.\nChurch special look successful.\nGarden police speak watch back onto. Body level popular current something exactly word yourself.',
    'email': 'nmathews@example.com',
    'phone_number': '+1-943-821-1965x12928',
    'json': {
    'name': 'Jennifer Stuart',
    'address': '9539 Christine Plains Apt. 266\nEast Joshuaberg, NJ 15811',
},
    'key8598': 'value32874',
    'key89442': 'value16248',
    'key33082': 'value92487',
    'key46064': 'value4547',
    'key20957': 'value87898',
    'key38895': 'value67167',
    'key63037': 'value74701',
    'key44504': 'value55036',
    'key26921': 'value16951',
},
    {
    'id': 17527482442964,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Micheal Mitchell',
    'address': '3503 Warner Isle Suite 767\nNew Dalehaven, OR 00681',
    'text': 'Loss bad politics member could. Alone decide hard spring still per.\nAcross sense American white size common itself themselves. Way several past ground top year discover. Development tree reason red.',
    'email': 'nathanielbrown@example.org',
    'phone_number': '(903)646-9626x91634',
    'json': {
    'name': 'Robert Vasquez',
    'address': '9332 Michael Walks Apt. 424\nWangville, CA 56910',
},
    'key12608': 'value58437',
    'key22258': 'value48951',
    'key64468': 'value78476',
    'key58060': 'value5801',
    'key86741': 'value38063',
    'key83842': 'value52251',
    'key99968': 'value22071',
},
    {
    'id': 17527482442976,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'James Romero',
    'address': '0156 Wallace Parkway\nAshleyborough, ND 61832',
    'text': 'Bring surface grow always. Defense success southern show different garden way.\nBeyond point because free Democrat part issue. Decide likely chance subject or perform health.',
    'email': 'annbarrett@example.org',
    'phone_number': '+1-798-643-2935x115',
    'json': {
    'name': 'Kurt Myers',
    'address': '99993 Rollins Plains\nHernandezstad, RI 74564',
},
    'key32235': 'value60496',
},
    {
    'id': 17527482442988,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Alex Manning',
    'address': '46020 Miller Mountain Apt. 536\nNorth Brian, OH 08815',
    'text': 'Catch necessary five tree house former. Property player recognize. Indicate bank arm response beautiful.\nGround arm forget truth red purpose another teach. Chance him amount serious.',
    'email': 'ubrown@example.org',
    'phone_number': '+1-755-606-3886',
    'json': {
    'name': 'James Dalton',
    'address': '731 Mallory Ferry\nEast Danielside, FL 26544',
},
    'key46080': 'value4639',
    'key60649': 'value27770',
},
    {
    'id': 17527482443000,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'John Fernandez',
    'address': 'PSC 0590, Box 1405\nAPO AE 57776',
    'text': 'Education campaign range watch strategy. Open camera training mind become education instead. Interesting lead weight success apply.',
    'email': 'kpalmer@example.com',
    'phone_number': '483.467.0335x377',
    'json': {
    'name': 'Tracy Delgado',
    'address': '688 Reynolds Falls\nLake Gary, KS 92381',
},
    'key71440': 'value54900',
    'key22922': 'value96912',
    'key31466': 'value6222',
    'key977': 'value22402',
    'key89353': 'value93547',
    'key45419': 'value38052',
    'key85281': 'value26696',
},
    {
    'id': 17527482443009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Mark Wilson',
    'address': '940 Norman Burg\nBryceburgh, MI 91363',
    'text': 'During weight against season young. Structure senior there big real.\nSpeak sit whom main production especially thing suddenly.',
    'email': 'cmurphy@example.org',
    'phone_number': '9118951761',
    'json': {
    'name': 'Lori Hahn',
    'address': '42781 Ortiz Fall Suite 965\nNew Sarah, PA 07874',
},
    'key98913': 'value83544',
    'key13210': 'value80256',
    'key86855': 'value56376',
    'key70568': 'value13896',
    'key10804': 'value12057',
    'key63057': 'value3961',
    'key55283': 'value98885',
},
    {
    'id': 17527482443019,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Brianna Sanchez',
    'address': '51880 Roger Path Suite 412\nRobertfurt, SD 10038',
    'text': 'Serve benefit player government. Morning wide often according right public.\nShe raise physical seek list. Attention doctor wife.\nUp several fall information light growth. Parent include across hot.',
    'email': 'alexanderjones@example.com',
    'phone_number': '850.564.1253',
    'json': {
    'name': 'Nicole Ramirez',
    'address': '0498 Michael Street\nNorth Denise, CO 20936',
},
    'key73031': 'value61950',
    'key16724': 'value33078',
    'key40508': 'value58780',
},
    {
    'id': 17527482443031,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Thomas Vargas',
    'address': '705 Farrell Shores Apt. 805\nGreerside, PW 23825',
    'text': 'Appear trip test according seat yourself. Study lawyer help smile reveal. Middle clearly while one.\nTotal lawyer last idea. Soldier discuss magazine.',
    'email': 'xpreston@example.org',
    'phone_number': '001-244-202-6917x190',
    'json': {
    'name': 'Pam Thompson',
    'address': '9544 Evan Haven Suite 399\nRebeccamouth, WY 73297',
},
    'key98476': 'value89188',
    'key60641': 'value17854',
    'key14079': 'value83651',
    'key83548': 'value73983',
    'key8577': 'value81256',
},
    {
    'id': 17527482443042,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Peter Ramos',
    'address': 'USNV Burton\nFPO AP 17888',
    'text': 'Here forward everyone successful both drive teach. Southern rule middle energy indeed yourself.\nHouse it still. Husband born environment tax suffer whether. Through tell few how employee heart.',
    'email': 'david70@example.com',
    'phone_number': '249-864-9738x29274',
    'json': {
    'name': 'John Moore',
    'address': '034 Gonzalez Road Suite 958\nEast Tami, PW 57528',
},
    'key74105': 'value67893',
    'key47230': 'value57930',
    'key91482': 'value20852',
    'key60241': 'value46987',
    'key44968': 'value27705',
    'key50218': 'value63668',
    'key32971': 'value26780',
},
    {
    'id': 17527482443051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Alicia Leach',
    'address': '150 Bryan Branch\nWest Dawnburgh, GA 01871',
    'text': 'Activity feel conference believe base. Keep ask half foot pull happy student. During nation although future life.',
    'email': 'eric92@example.org',
    'phone_number': '390.474.6856x5660',
    'json': {
    'name': 'Vincent Martinez',
    'address': '24320 Bell Mountain\nWest Christineberg, FL 11966',
},
    'key35549': 'value77212',
    'key32937': 'value60303',
},
    {
    'id': 17527482443061,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Gary Phillips',
    'address': '186 Timothy Way\nRogersland, VT 47400',
    'text': 'Call debate might. Help him memory study.\nI fund old develop vote against. Realize list east again year.\nSuccessful campaign technology group sign price. Future hear article nice clear.',
    'email': 'kramermatthew@example.org',
    'phone_number': '001-948-544-2778',
    'json': {
    'name': 'Peggy Hodges DDS',
    'address': '34040 Diane Villages Suite 410\nRussellview, VA 11013',
},
    'key34344': 'value81946',
    'key4900': 'value64388',
    'key37510': 'value27467',
    'key34504': 'value92452',
    'key28160': 'value48416',
},
    {
    'id': 17527482443073,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Daniel George',
    'address': 'USCGC Adams\nFPO AP 97492',
    'text': 'Chair strategy sell might form good part. Participant past any development break could see last.\nDegree huge item nearly step name wind.',
    'email': 'glenntoni@example.net',
    'phone_number': '224.689.6734',
    'json': {
    'name': 'Steven Page',
    'address': '69958 Davidson Islands Suite 215\nLake Lauratown, NM 03184',
},
    'key80004': 'value65465',
    'key81033': 'value24443',
    'key90437': 'value13978',
    'key73578': 'value62726',
    'key17548': 'value72335',
    'key12436': 'value44585',
    'key35464': 'value42263',
    'key87495': 'value62371',
},
    {
    'id': 17527482443084,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Melissa Miller',
    'address': '70713 Ortiz Way\nLake Kennethland, TN 59358',
    'text': 'Recent relate bill central. Attorney medical military president science.\nNature check cup new attorney fact. Bad manage little serious.',
    'email': 'ogordon@example.net',
    'phone_number': '2152514400',
    'json': {
    'name': 'Deborah Thomas',
    'address': '131 Sharon Courts\nSouth Brandonchester, AL 12122',
},
    'key31689': 'value49027',
    'key6800': 'value96217',
    'key62764': 'value51276',
    'key47247': 'value13152',
    'key3235': 'value11939',
    'key36774': 'value3501',
    'key9568': 'value54825',
    'key40389': 'value83458',
    'key99801': 'value61454',
},
    {
    'id': 17527482443096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Peter Beard',
    'address': '069 Robert Avenue Suite 596\nNorth Rachel, KS 96692',
    'text': 'Star reflect reduce kid. Full professional cup lawyer leg.\nView establish wish rich. News less real help billion word.',
    'email': 'hmoreno@example.com',
    'phone_number': '(307)727-9505',
    'json': {
    'name': 'Andrew Wolf',
    'address': '007 Desiree Drives\nOrtizview, KY 23596',
},
    'key30793': 'value78667',
    'key86060': 'value63345',
    'key11096': 'value74190',
    'key24475': 'value54451',
    'key88449': 'value88458',
    'key6742': 'value92855',
    'key28216': 'value62868',
},
    {
    'id': 17527482443107,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Ernest Grant',
    'address': '66699 Cross Shores Apt. 181\nFaulknerside, VA 24280',
    'text': 'Worker well particularly ahead kid building. Everybody join take increase force.',
    'email': 'ronaldclark@example.com',
    'phone_number': '390.633.3489',
    'json': {
    'name': 'Vanessa Petersen',
    'address': 'PSC 9340, Box 6772\nAPO AA 94045',
},
    'key95740': 'value4621',
    'key29406': 'value25507',
    'key8707': 'value76178',
    'key74134': 'value95784',
    'key58799': 'value37030',
    'key30982': 'value97809',
},
    {
    'id': 17527482443116,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Todd Herring',
    'address': '6886 Smith Place\nWest Mary, PA 34678',
    'text': 'Church join culture red. Significant next realize five participant.\nNice sure interesting either common successful all. Field citizen bar nation little about. Trip economy ok research new remain.',
    'email': 'adamscrystal@example.com',
    'phone_number': '(378)712-9124x355',
    'json': {
    'name': 'Kyle Ibarra',
    'address': '8799 Welch River Suite 131\nPort Briana, AL 65977',
},
    'key10836': 'value61424',
    'key22051': 'value85925',
    'key15259': 'value34640',
    'key4377': 'value72476',
    'key72433': 'value68654',
    'key24915': 'value93442',
    'key61226': 'value39420',
    'key16495': 'value37563',
},
    {
    'id': 17527482443128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Christine Douglas',
    'address': '233 John Curve Apt. 195\nNew Maryborough, NY 06203',
    'text': 'Stand home few partner. Purpose black represent media trouble.\nTreat those total amount. Public likely better audience sing. Certainly whatever international whose part. Beyond out wind people.',
    'email': 'gary84@example.com',
    'phone_number': '647-757-5292',
    'json': {
    'name': 'Rebecca Davis',
    'address': '73464 Stephanie Junction\nWest John, MP 18002',
},
    'key15067': 'value20439',
    'key58900': 'value26060',
    'key67497': 'value12663',
    'key26913': 'value93153',
},
    {
    'id': 17527482443139,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Judy Myers',
    'address': '0640 Kimberly Ports\nRobertside, AZ 10790',
    'text': 'Debate too speech alone. System person knowledge.\nPlayer place exist end. Walk cut cell themselves nearly travel our. Buy term floor serious compare throw drive Republican.',
    'email': 'herbertdavis@example.org',
    'phone_number': '+1-280-371-5067',
    'json': {
    'name': 'Jamie Cummings MD',
    'address': '381 Lutz Tunnel Suite 783\nLake Karen, RI 03305',
},
    'key65742': 'value66785',
    'key25395': 'value4177',
    'key76610': 'value35422',
    'key48524': 'value56095',
    'key95220': 'value94563',
},
    {
    'id': 17527482443149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Morgan Jacobs',
    'address': '8317 Moore Bypass\nHartstad, RI 30379',
    'text': 'Resource black season give teacher result. Best west everybody in. Media this agency past range go believe.\nThrough coach write tonight effect then.',
    'email': 'alexander65@example.net',
    'phone_number': '(474)869-4320',
    'json': {
    'name': 'Jose Mcdonald',
    'address': '8458 Ward Ways\nEast Jamesville, AZ 12467',
},
    'key22168': 'value73601',
    'key6410': 'value89299',
    'key73484': 'value91703',
    'key49476': 'value95288',
    'key57692': 'value78414',
},
    {
    'id': 17527482443160,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Brian Douglas',
    'address': 'Unit 4704 Box 5764\nDPO AP 54143',
    'text': 'City represent camera eight major page. Tonight evening figure business itself society.\nSay enough firm beat early.',
    'email': 'uhamilton@example.org',
    'phone_number': '955-500-2545',
    'json': {
    'name': 'Sharon Macdonald',
    'address': '199 Levine Knolls Suite 558\nNorth Josephview, MI 12406',
},
    'key17263': 'value35959',
    'key89584': 'value93780',
    'key81916': 'value58132',
    'key22103': 'value31692',
    'key27277': 'value98399',
    'key28088': 'value89032',
    'key28457': 'value20704',
    'key16206': 'value75176',
    'key61460': 'value38463',
    'key48438': 'value10731',
},
    {
    'id': 17527482443169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Victor Collins',
    'address': '34439 Vasquez Squares\nJoshuahaven, CT 80129',
    'text': 'Month near street series do road. Let whatever worker mean trial remember price area.',
    'email': 'reidwendy@example.net',
    'phone_number': '+1-386-748-6256',
    'json': {
    'name': 'Ryan Cervantes',
    'address': '654 Rose Knolls Suite 318\nWest David, SD 58602',
},
    'key26724': 'value55500',
    'key43206': 'value6122',
    'key18647': 'value58979',
    'key82807': 'value19723',
    'key21747': 'value38660',
    'key78233': 'value67510',
    'key55547': 'value6215',
    'key41838': 'value18836',
    'key1002': 'value19507',
},
    {
    'id': 17527482443180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Charles Rogers',
    'address': '47918 Cameron Hollow Apt. 884\nHamiltonborough, IA 54313',
    'text': 'Garden else forward yet. Feeling put father stop partner ground peace.',
    'email': 'calexander@example.net',
    'phone_number': '(574)233-9982x478',
    'json': {
    'name': 'Robin Todd',
    'address': '251 Katherine Park Apt. 493\nJacquelineborough, PA 01969',
},
    'key70656': 'value27481',
    'key44801': 'value34426',
},
    {
    'id': 17527482443191,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Leslie Quinn',
    'address': '223 Price Spur\nWest Amandamouth, CA 08956',
    'text': 'Carry wide doctor bed relationship window seem center. Wrong together many need back present.',
    'email': 'ruizjay@example.net',
    'phone_number': '993.634.9724',
    'json': {
    'name': 'Richard Summers',
    'address': '4689 Pope Ways\nChristopherport, MO 56684',
},
    'key38338': 'value70358',
    'key48681': 'value19246',
},
    {
    'id': 17527482443203,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Sarah Gallagher',
    'address': '57978 Kathy Hills Apt. 486\nWest Cassandra, PR 06372',
    'text': 'Chair record this condition wife. Option back president opportunity off lay pass.',
    'email': 'adamdougherty@example.com',
    'phone_number': '+1-957-996-0416x6452',
    'json': {
    'name': 'Samantha Little',
    'address': '3677 Jeff Turnpike Apt. 674\nLake Amanda, KS 05440',
},
    'key38604': 'value49278',
    'key16496': 'value27241',
    'key48613': 'value55927',
    'key43915': 'value78266',
    'key99957': 'value93965',
    'key1924': 'value69513',
},
    {
    'id': 17527482443214,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Matthew Collier',
    'address': 'USS Murphy\nFPO AP 35121',
    'text': 'Its music cost space piece whose. Certain student woman fact nearly cup kind view.',
    'email': 'kayla54@example.net',
    'phone_number': '+1-256-656-7945x04886',
    'json': {
    'name': 'Tony Ryan',
    'address': '628 Dalton Point Suite 116\nRamirezview, WI 49894',
},
    'key19187': 'value37188',
    'key6613': 'value28079',
    'key70380': 'value31431',
    'key72672': 'value34130',
    'key47322': 'value55472',
    'key15928': 'value81951',
    'key40522': 'value47258',
    'key63849': 'value45132',
    'key75359': 'value8778',
    'key88642': 'value1630',
},
    {
    'id': 17527482443224,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Madison Young',
    'address': '198 Castro Freeway\nEast Crystalbury, SD 02573',
    'text': 'Discover technology defense to all establish threat respond. Above fill pretty throw mention air give. Mrs record if rather compare share.',
    'email': 'zking@example.net',
    'phone_number': '394.523.8770x537',
    'json': {
    'name': 'Robert Rodriguez',
    'address': '08119 Kristin Valleys Suite 725\nDavidburgh, SD 04417',
},
    'key3782': 'value93815',
    'key70597': 'value46828',
    'key52714': 'value54885',
},
    {
    'id': 17527482443234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Daniel Andrews',
    'address': 'Unit 2953 Box 9064\nDPO AE 75532',
    'text': 'Best view by personal board protect door. Industry enjoy place miss. Give tell wide practice.\nCard your sport make. Majority training government party maintain.',
    'email': 'odomrebecca@example.org',
    'phone_number': '846-599-8799x1686',
    'json': {
    'name': 'Samuel Ryan',
    'address': '557 Sarah Way\nPort Carolinemouth, MI 41391',
},
    'key80458': 'value56242',
    'key6900': 'value89840',
    'key42194': 'value91918',
    'key39157': 'value96757',
    'key8560': 'value60403',
},
    {
    'id': 17527482443243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Vanessa Franklin',
    'address': '491 Hart Cliff\nLeeberg, NE 04432',
    'text': 'Too among event yourself TV line shake. Analysis why tonight herself group goal. Deep somebody cover grow woman.',
    'email': 'hunterchristopher@example.org',
    'phone_number': '(218)978-7277',
    'json': {
    'name': 'Dorothy Silva',
    'address': '99097 Nguyen Fields Apt. 514\nSouth Christopherhaven, AL 45568',
},
    'key61524': 'value8394',
    'key52065': 'value88455',
    'key39924': 'value15152',
    'key64728': 'value71261',
    'key16177': 'value57777',
    'key77210': 'value64458',
    'key66134': 'value84447',
    'key26897': 'value56779',
},
    {
    'id': 17527482443255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Adam Reyes',
    'address': '822 Edward Manors Suite 897\nMichellemouth, TN 85652',
    'text': 'Four major draw TV foot trial hit. School best door describe. Ask ball I yet tough.',
    'email': 'andersonjames@example.com',
    'phone_number': '001-935-345-2955x80208',
    'json': {
    'name': 'Barbara Anderson',
    'address': 'PSC 7928, Box 6268\nAPO AP 31627',
},
    'key58378': 'value47125',
    'key84150': 'value42458',
    'key95161': 'value67861',
    'key97568': 'value26705',
    'key65355': 'value90634',
    'key32099': 'value2519',
},
    {
    'id': 17527482443264,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Robert Porter',
    'address': '718 Richardson Villages\nPort Jessica, AR 59818',
    'text': 'Large north hand affect. Yeah various people heart.\nWe as offer southern rise. Understand few necessary bill red rise.',
    'email': 'hufflaura@example.net',
    'phone_number': '360-260-9374',
    'json': {
    'name': 'Nicole Edwards',
    'address': '8207 Carroll Square\nJonesmouth, TN 52554',
},
    'key20792': 'value16504',
    'key96078': 'value83569',
    'key45842': 'value39606',
    'key226': 'value8250',
},
    {
    'id': 17527482443275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Christopher Welch',
    'address': '765 Kimberly Divide\nNew Susan, CT 14061',
    'text': 'People ground new west most population. Religious wife else senior with memory accept. Make exactly behind difficult evening.',
    'email': 'hzhang@example.com',
    'phone_number': '404-466-7596x82401',
    'json': {
    'name': 'Kimberly Jackson',
    'address': '318 Daniel Green\nSouth Victoriaside, WY 57746',
},
    'key31761': 'value57636',
},
    {
    'id': 17527482443285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Kerri Crawford',
    'address': '4527 Acosta Squares\nMichaelview, VA 86398',
    'text': 'Onto contain go we green list determine. Card lawyer land toward.\nGlass father education allow. Save deep wonder near. Crime race page course machine rich.',
    'email': 'carpentermichael@example.org',
    'phone_number': '771.606.6630',
    'json': {
    'name': 'Jesse Garcia',
    'address': 'Unit 9894 Box 8360\nDPO AA 18195',
},
    'key15645': 'value44946',
    'key38031': 'value65542',
    'key39839': 'value50630',
},
    {
    'id': 17527482443294,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Taylor Mays',
    'address': '7574 Henry Tunnel Suite 054\nWest Staceyside, MN 69609',
    'text': 'Water since different. Together improve realize worker million. Laugh adult during her because company. Write best carry alone no indeed.',
    'email': 'nathanburke@example.net',
    'phone_number': '808-222-2689x00550',
    'json': {
    'name': 'Courtney Farmer',
    'address': '750 Carlos Prairie\nEast Kimberly, CT 93334',
},
    'key1071': 'value87364',
    'key54112': 'value15803',
},
    {
    'id': 17527482443306,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Travis Washington',
    'address': '6164 Blackwell Fords\nPort Aliciaport, DE 35499',
    'text': 'So spend cup skin nice without. Second put him throughout almost. Already must every family return area speech.',
    'email': 'reedkaren@example.org',
    'phone_number': '(451)427-2541x324',
    'json': {
    'name': 'Arthur Mason',
    'address': '32492 Bryant Locks\nJustinchester, FL 58896',
},
    'key87417': 'value92755',
    'key65227': 'value98181',
    'key18107': 'value20951',
    'key83396': 'value18515',
    'key2120': 'value42727',
    'key79664': 'value38987',
},
    {
    'id': 17527482443317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Michael Ferguson',
    'address': '08457 Jack Parkway\nNathanielview, AZ 34417',
    'text': 'Physical particularly similar human there suddenly. Research resource throw eight.\nSure court listen rule. Writer measure will produce deep.\nFollow military cost trade apply.',
    'email': 'lynn82@example.net',
    'phone_number': '+1-787-576-1825x7574',
    'json': {
    'name': 'Michelle Ball',
    'address': '085 Richardson Ports\nSouth Cynthiabury, NC 08390',
},
    'key36639': 'value98845',
    'key87454': 'value58794',
},
    {
    'id': 17527482443327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Mary Haley',
    'address': '56404 Kevin Summit Suite 618\nEast Erica, MT 34585',
    'text': 'Require inside bit draw leg evidence across. Employee agent fall paper bag fund rest stand. Network leave bar act reveal country a simple.',
    'email': 'barbaramason@example.net',
    'phone_number': '4865213872',
    'json': {
    'name': 'Michelle Gonzalez',
    'address': '242 Michael Orchard Suite 664\nJeffland, TX 25486',
},
    'key29308': 'value94605',
    'key79270': 'value64172',
    'key96687': 'value60240',
    'key81417': 'value93411',
    'key89300': 'value35349',
    'key95416': 'value82199',
    'key27268': 'value94763',
    'key71748': 'value11671',
    'key1831': 'value55064',
    'key32079': 'value99137',
},
    {
    'id': 17527482443338,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Vickie Nelson',
    'address': '007 Tamara Isle Suite 911\nNew Coryfort, WV 08507',
    'text': 'Trip politics most member blood same most. Return simply environment theory threat serve have.',
    'email': 'justin29@example.com',
    'phone_number': '(969)398-6045',
    'json': {
    'name': 'Erika White',
    'address': '262 Brittany Vista Suite 055\nNew Stephaniechester, CT 17665',
},
    'key9573': 'value26578',
    'key85466': 'value84354',
    'key59075': 'value43540',
    'key51450': 'value68959',
},
    {
    'id': 17527482443348,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Andre Hernandez',
    'address': '44954 Kaitlyn Ranch Suite 594\nNorth Justinfurt, MH 23412',
    'text': 'There fight international seek foreign sing. Indeed film bed sit require try. Possible question fish against north another.\nStar either they turn check work green.',
    'email': 'smurphy@example.net',
    'phone_number': '646-648-2014x094',
    'json': {
    'name': 'Jose Sullivan',
    'address': '293 Rachel Course\nEast Jennifer, DE 59945',
},
    'key8169': 'value2861',
    'key59770': 'value3573',
    'key52951': 'value82310',
    'key8675': 'value49915',
},
    {
    'id': 17527482443358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'John Mata',
    'address': '03152 Betty Lodge\nNorth Patriciabury, IA 90675',
    'text': 'Doctor drive sure body set. Memory campaign cost.\nBeyond letter place road worry. Number little skill party try recently. Director pretty different detail doctor discover.',
    'email': 'gberry@example.com',
    'phone_number': '446-808-9786',
    'json': {
    'name': 'Alison Harper',
    'address': '85036 Willis Stravenue Apt. 651\nSouth Hollyview, AZ 41692',
},
    'key28394': 'value5227',
    'key32970': 'value77251',
    'key41064': 'value80580',
    'key62131': 'value46295',
    'key39793': 'value37006',
    'key14451': 'value93272',
    'key94504': 'value5899',
    'key34006': 'value21933',
    'key32537': 'value44333',
},
    {
    'id': 17527482443369,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Ashley Edwards',
    'address': '7151 Porter Tunnel\nDouglasside, WA 78920',
    'text': 'Health play test two decide.\nTell language occur see resource full nothing bring. List pay who environmental sure pressure.',
    'email': 'jennifer94@example.org',
    'phone_number': '735.869.9193x2883',
    'json': {
    'name': 'Jason Jackson',
    'address': '47477 Johnson Mills Suite 899\nChristopherview, LA 52877',
},
    'key43373': 'value39776',
    'key965': 'value76928',
    'key23868': 'value74538',
    'key23794': 'value6266',
    'key10153': 'value43575',
    'key3256': 'value87433',
    'key63399': 'value44604',
    'key92732': 'value81764',
    'key61425': 'value89974',
},
    {
    'id': 17527482443379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Dustin Gay',
    'address': '875 Scott Port\nNew Dawn, TX 93366',
    'text': 'Coach deep test their treatment tree surface. Poor find least fish expect ask simply. Allow product yes write game Congress leave certainly.',
    'email': 'woodsbrittany@example.org',
    'phone_number': '215.999.5352',
    'json': {
    'name': 'Rachel Thomas',
    'address': '53682 Dixon Lodge Suite 370\nAlanside, SD 80182',
},
    'key2790': 'value42204',
    'key33994': 'value45827',
    'key39778': 'value68601',
    'key43442': 'value70941',
    'key28115': 'value60899',
    'key72971': 'value92302',
    'key87842': 'value31832',
},
    {
    'id': 17527482443390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Sarah Diaz',
    'address': '7382 Sarah Meadows Apt. 649\nRichardchester, FM 01646',
    'text': 'Include police address yourself. Ok leave send medical wide morning place fear. Last growth PM he by.',
    'email': 'saundersrebecca@example.org',
    'phone_number': '+1-741-576-2881',
    'json': {
    'name': 'Jennifer Jacobson',
    'address': '91901 Hale Bypass Apt. 474\nWilliamsview, OR 44004',
},
    'key63802': 'value98707',
    'key92948': 'value61434',
    'key39293': 'value94683',
    'key97262': 'value93636',
    'key93195': 'value41301',
    'key10121': 'value26581',
    'key29893': 'value2047',
    'key93': 'value1566',
    'key12359': 'value6828',
    'key21944': 'value67680',
},
    {
    'id': 17527482443402,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Wanda Romero',
    'address': '9825 Chad Dale\nTheodoreside, AR 81650',
    'text': 'Each popular Mrs employee treatment. Technology together after suffer look.\nQuality collection compare popular shake staff green voice. Hotel care dog other bad player black. Idea garden something.',
    'email': 'stephanie01@example.com',
    'phone_number': '+1-883-741-4987x130',
    'json': {
    'name': 'Charles Obrien',
    'address': '713 Jason Locks\nSummershaven, WA 58890',
},
    'key11785': 'value14677',
    'key3791': 'value74048',
    'key24714': 'value72460',
    'key57552': 'value87328',
    'key85646': 'value51808',
    'key48220': 'value95839',
    'key24365': 'value93897',
    'key28900': 'value58849',
    'key85181': 'value36915',
},
    {
    'id': 17527482443412,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Jaime Sheppard',
    'address': 'USS Miller\nFPO AA 46556',
    'text': 'Provide animal matter condition data. Notice coach production sea.\nRule land available paper scene more probably. Color hold morning natural major.',
    'email': 'gregory99@example.org',
    'phone_number': '682-538-4274x4304',
    'json': {
    'name': 'Tyrone King',
    'address': '209 Evans Glens Suite 849\nNorth Matthewmouth, MS 41441',
},
    'key83604': 'value19552',
    'key59685': 'value62747',
    'key47752': 'value86624',
    'key42413': 'value88759',
    'key31061': 'value76367',
},
    {
    'id': 17527482443422,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Loretta Miller',
    'address': '7558 Benjamin Wells Suite 432\nLake Anne, FM 81114',
    'text': 'Boy eye modern beautiful activity there. Ok fall senior offer lose. Idea this pressure skill staff sound wrong.',
    'email': 'elane@example.org',
    'phone_number': '001-349-958-6927',
    'json': {
    'name': 'Andrew Day',
    'address': '663 Kimberly Viaduct Apt. 061\nPort Anne, AS 29210',
},
    'key40428': 'value7762',
    'key1325': 'value92106',
    'key15513': 'value649',
    'key14899': 'value97538',
    'key56336': 'value89708',
    'key78932': 'value43508',
    'key62301': 'value80863',
},
    {
    'id': 17527482443432,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Kevin Sanders',
    'address': '792 Laura River\nLake Alexis, OH 89960',
    'text': 'Face letter few director fear read. Loss property goal son win here.\nInside voice network perform add concern. Lawyer level quite the.',
    'email': 'amber29@example.com',
    'phone_number': '334.478.5990x05887',
    'json': {
    'name': 'Jeremy Harris',
    'address': '3535 Figueroa Cape Apt. 625\nKevintown, GA 21810',
},
    'key38998': 'value94623',
    'key44668': 'value18345',
    'key4326': 'value81428',
},
    {
    'id': 17527482443442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Michelle Nguyen',
    'address': '242 Natalie Ridges Apt. 337\nPort Colleenview, AS 33567',
    'text': 'Continue environmental firm national. Once family suddenly among another stock make action.',
    'email': 'chad53@example.com',
    'phone_number': '(584)220-7764x42258',
    'json': {
    'name': 'Roberta Kane',
    'address': '485 Peters Knolls\nSierraport, ND 68545',
},
    'key86004': 'value20453',
    'key7236': 'value80933',
    'key65594': 'value52739',
    'key92347': 'value39893',
    'key64437': 'value19979',
    'key53706': 'value51884',
},
    {
    'id': 17527482443452,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Brittany Cruz',
    'address': '7071 Amy Field\nMeghantown, RI 36359',
    'text': 'Win indeed small describe. Modern more camera reality.\nOut both tonight. School present paper. Study then onto economy.',
    'email': 'sberger@example.net',
    'phone_number': '001-220-228-3126x45828',
    'json': {
    'name': 'Matthew Snyder',
    'address': 'USNV Parsons\nFPO AP 08724',
},
    'key75023': 'value27276',
    'key39155': 'value92728',
    'key26379': 'value13442',
    'key89328': 'value40415',
    'key24748': 'value33794',
    'key647': 'value46008',
},
    {
    'id': 17527482443462,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Stephanie Johnson',
    'address': '32874 Olivia Squares Suite 561\nSouth Jill, GU 03802',
    'text': 'East boy north amount resource prevent. Back model record learn military keep room. Develop write participant arm walk travel vote special. Head occur up whom nature me serve.',
    'email': 'anthony17@example.net',
    'phone_number': '001-386-421-3285',
    'json': {
    'name': 'Christine Valenzuela',
    'address': 'PSC 6782, Box 4141\nAPO AP 27132',
},
    'key84587': 'value67257',
    'key79034': 'value70759',
    'key20581': 'value23613',
    'key68351': 'value90452',
    'key79137': 'value92543',
    'key32017': 'value61039',
    'key16189': 'value89930',
},
    {
    'id': 17527482443470,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Pamela Armstrong',
    'address': '73421 Alyssa Ville Suite 744\nLeonardstad, AS 08905',
    'text': 'Fine camera just prove by western capital. Affect night defense.\nImportant present recent soldier often. System truth school collection all bar resource.\nFive most city act some school.',
    'email': 'rodriguezsuzanne@example.com',
    'phone_number': '234-694-6167',
    'json': {
    'name': 'Ricardo Dunn',
    'address': '112 Knight Turnpike Suite 819\nNew Craig, WA 30699',
},
    'key27784': 'value9437',
    'key59062': 'value84678',
    'key87639': 'value56078',
    'key65949': 'value21426',
    'key6102': 'value53028',
    'key41577': 'value50859',
    'key43866': 'value55956',
    'key25200': 'value59042',
    'key97074': 'value15920',
},
    {
    'id': 17527482443482,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Mr. John White',
    'address': '2514 Michael Islands\nSouth Carrie, KY 94397',
    'text': 'Dog politics order recently. Trouble participant us. Thousand behind me.\nProtect try enter former medical note end. Attack what even hold. Common night station.',
    'email': 'melissa89@example.org',
    'phone_number': '001-733-544-0363x1336',
    'json': {
    'name': 'Terry Weber',
    'address': 'USS Rios\nFPO AE 13566',
},
    'key49733': 'value82710',
    'key42958': 'value14568',
    'key20500': 'value7793',
},
    {
    'id': 17527482443491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jason Wood',
    'address': '506 Baldwin Ways Suite 233\nHannahberg, IA 53769',
    'text': 'Instead eat draw record project.\nFact per go. Realize edge bed focus there assume radio model.',
    'email': 'charles16@example.net',
    'phone_number': '001-295-282-6556',
    'json': {
    'name': 'Tina Jones',
    'address': '7762 Johnson Landing\nPort Marymouth, OR 66318',
},
    'key54319': 'value95306',
    'key26191': 'value63753',
    'key7434': 'value24898',
    'key66972': 'value67963',
    'key16332': 'value64430',
    'key11851': 'value97260',
},
    {
    'id': 17527482443501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Kenneth Bowen',
    'address': '905 Mark Path\nLaurahaven, MP 08812',
    'text': 'Bar order leg probably. Design standard economic matter source stock fine.',
    'email': 'christophermayer@example.net',
    'phone_number': '+1-627-482-3151',
    'json': {
    'name': 'Diana Smith',
    'address': 'USCGC Bender\nFPO AP 22774',
},
    'key82398': 'value86947',
},
    {
    'id': 17527482443511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Erika Hoffman',
    'address': '81615 Harris Ports\nEast Elizabethmouth, GU 95491',
    'text': 'Group meet same civil. Stock third green.\nCampaign size chance order. Change yard food office. Traditional recently simple home minute. Hope item brother it it green.',
    'email': 'heather73@example.com',
    'phone_number': '673.211.8750x15846',
    'json': {
    'name': 'Mrs. Dawn Levine',
    'address': '2158 Sarah Brook\nCarsonstad, DC 55280',
},
    'key66359': 'value60253',
    'key54376': 'value68055',
    'key85085': 'value9079',
    'key6040': 'value21149',
    'key88156': 'value44681',
    'key59342': 'value91991',
    'key35918': 'value55081',
    'key5021': 'value8072',
},
    {
    'id': 17527482443521,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Larry Price',
    'address': '208 Arnold Summit\nEast Tamaraland, PR 38541',
    'text': 'Stand high require American manager perhaps treat. Pressure run street interview knowledge.\nMarriage prepare woman vote. Continue think always safe American program. Church mission try.',
    'email': 'cooperfranklin@example.com',
    'phone_number': '9203715075',
    'json': {
    'name': 'Richard Carr',
    'address': '2876 Wilson Creek Suite 213\nWest Sandra, FM 83108',
},
    'key28163': 'value9287',
    'key159': 'value36931',
},
    {
    'id': 17527482443533,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Jade Jones MD',
    'address': '6298 Raymond Park\nGibsonbury, MS 26069',
    'text': 'Must move law just energy yes. Piece support foreign. Meeting employee behind usually impact camera.\nLate success south his brother. Worker simple others.',
    'email': 'lucas44@example.com',
    'phone_number': '001-921-418-9419x492',
    'json': {
    'name': 'Cassandra Parsons',
    'address': '102 Amy Burgs\nStevenfort, LA 55877',
},
    'key50902': 'value24745',
    'key6357': 'value15439',
    'key43539': 'value12411',
    'key63909': 'value30105',
    'key71812': 'value55385',
    'key31873': 'value40907',
    'key77251': 'value41122',
    'key989': 'value8641',
},
    {
    'id': 17527482443543,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Michelle Williams',
    'address': '02339 Hale Ferry Suite 318\nSouth Courtneystad, ND 26079',
    'text': 'Join expert poor modern break mother. Involve enter himself.\nFear agree thought speak clearly positive chance. Guy bank artist increase opportunity. Material book policy stage him.',
    'email': 'andrew41@example.org',
    'phone_number': '001-980-310-2076x9732',
    'json': {
    'name': 'Angela Hodge',
    'address': '965 Valdez Spur Apt. 621\nRoberthaven, WA 01180',
},
    'key20726': 'value18922',
    'key98513': 'value59650',
    'key63222': 'value6708',
    'key34692': 'value91910',
    'key6229': 'value90744',
    'key53113': 'value36711',
    'key90804': 'value99461',
    'key81392': 'value60691',
    'key41021': 'value94326',
},
    {
    'id': 17527482443554,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Zachary Woods',
    'address': 'PSC 8924, Box 9152\nAPO AE 42369',
    'text': 'Camera owner growth contain quite. Employee let learn.\nFace simple serve manager million choose. Could though third increase certain.\nTotal writer visit. Reach support exist together film.',
    'email': 'jason91@example.org',
    'phone_number': '+1-636-933-4797',
    'json': {
    'name': 'Monica Perez',
    'address': '4683 Goodwin Fall Suite 733\nEast Drew, AL 85270',
},
    'key2239': 'value62965',
    'key77026': 'value83373',
    'key24011': 'value11011',
    'key85779': 'value6679',
    'key5809': 'value52722',
    'key69314': 'value69856',
    'key22045': 'value35444',
},
    {
    'id': 17527482443563,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Shawn Wolfe',
    'address': '141 Amber Mountains Apt. 384\nKennethchester, NC 84042',
    'text': 'Husband degree several war blue explain. State process claim goal budget soon.',
    'email': 'amywagner@example.com',
    'phone_number': '999.697.4465',
    'json': {
    'name': 'Brian Brown',
    'address': '5684 Donna Mill Apt. 466\nMarcusview, WI 59900',
},
    'key1431': 'value56260',
    'key60244': 'value83907',
    'key11485': 'value2881',
    'key39937': 'value7954',
},
    {
    'id': 17527482443574,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Ronald Watts',
    'address': '8804 Cathy Locks\nWest Jamesshire, AK 19333',
    'text': 'Set center forget executive. Size situation seven yes never prove name.\nThroughout at fish hope. Order on break PM. Doctor economy happy apply.',
    'email': 'fedwards@example.org',
    'phone_number': '218-604-0754x748',
    'json': {
    'name': 'Jessica Simpson',
    'address': '7962 Kelli Glen\nNorth Leahmouth, ID 98902',
},
    'key3992': 'value90883',
    'key63361': 'value33184',
    'key8535': 'value7747',
    'key47825': 'value90040',
    'key56400': 'value41739',
},
    {
    'id': 17527482443584,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Brittney Gibbs',
    'address': 'Unit 2697 Box 6138\nDPO AA 43911',
    'text': 'When worry environmental stay push. Leader mean teacher debate too lawyer amount.\nMiss structure occur PM food suffer once.',
    'email': 'scottgreene@example.com',
    'phone_number': '+1-723-266-9897',
    'json': {
    'name': 'Jimmy Martinez',
    'address': '30062 John Meadow\nStevensstad, WI 44159',
},
    'key59061': 'value92341',
    'key57414': 'value42781',
    'key80980': 'value61621',
},
    {
    'id': 17527482443594,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Christopher Kelley',
    'address': '30054 Williams Run\nEast Harry, IL 86317',
    'text': 'Peace eight no amount Congress watch. Issue cell cup popular keep lose cost. Fall continue toward west include wear.',
    'email': 'robert90@example.com',
    'phone_number': '(246)208-5926x560',
    'json': {
    'name': 'Christopher Allen',
    'address': '3742 Anne Light Suite 005\nEricberg, MA 14945',
},
    'key56098': 'value55069',
},
    {
    'id': 17527482443603,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Heather Kim',
    'address': '693 Eric Track\nLake Donnaborough, MS 30541',
    'text': 'But deal perform radio design maybe. Option others share station truth suddenly.\nGirl entire accept over. Operation unit option left above. Sport provide game true go specific.',
    'email': 'james71@example.org',
    'phone_number': '(458)856-7773x5289',
    'json': {
    'name': 'Jacob Case',
    'address': '75514 Timothy Camp Apt. 710\nRobertfort, NY 43261',
},
    'key86296': 'value92866',
    'key99301': 'value70752',
    'key11160': 'value23600',
    'key60937': 'value99161',
    'key58912': 'value35895',
},
    {
    'id': 17527482443614,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Kimberly Brown',
    'address': 'USNS Ward\nFPO AA 78519',
    'text': 'Card argue onto must win. American hundred maintain benefit.',
    'email': 'daniel87@example.org',
    'phone_number': '001-683-603-3468x613',
    'json': {
    'name': 'Katherine Hammond',
    'address': 'USNS Roberts\nFPO AP 64455',
},
    'key71167': 'value4278',
    'key82896': 'value31848',
    'key42196': 'value43753',
    'key40545': 'value97816',
    'key11787': 'value15119',
},
    {
    'id': 17527482443621,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Richard Brooks',
    'address': '89013 Myers Plains\nFoxmouth, MI 79033',
    'text': 'Everybody increase level economy. Civil early movie physical experience above down.',
    'email': 'morrisonchristine@example.com',
    'phone_number': '+1-473-709-3304x602',
    'json': {
    'name': 'Andrea Todd',
    'address': '05012 Huynh Trafficway Suite 094\nLake Dylan, MT 77742',
},
    'key59476': 'value29610',
    'key94175': 'value87633',
    'key73509': 'value86472',
    'key30809': 'value17241',
    'key12652': 'value74377',
    'key16563': 'value35718',
    'key33425': 'value40101',
    'key8059': 'value73869',
    'key20557': 'value61754',
    'key96676': 'value22252',
},
    {
    'id': 17527482443633,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Samantha Callahan',
    'address': '34621 Foster Cape Apt. 565\nPort Ryanbury, MH 51583',
    'text': 'Research bill action statement help. Make me nation throughout.\nIssue expert choose deal seven. Soldier blue he use head fact light. Skin best either majority low week.',
    'email': 'elizabethvasquez@example.net',
    'phone_number': '(545)915-9707x9248',
    'json': {
    'name': 'Denise Nicholson',
    'address': '971 Webb Mount Apt. 831\nAnthonyside, AZ 84459',
},
    'key88702': 'value58993',
    'key72476': 'value21441',
    'key66385': 'value24384',
    'key97360': 'value43579',
    'key80581': 'value23598',
    'key38583': 'value69311',
    'key50157': 'value92111',
    'key56562': 'value44764',
    'key87472': 'value50429',
},
    {
    'id': 17527482443645,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Jennifer Castillo',
    'address': '4331 Pugh Route Apt. 319\nBeckbury, MI 02223',
    'text': 'People season hair artist pressure create mean. So quite party wide field save number.',
    'email': 'katiesmith@example.net',
    'phone_number': '695-926-8709x8656',
    'json': {
    'name': 'Nicholas Callahan',
    'address': 'USS Clark\nFPO AA 42650',
},
    'key28113': 'value31732',
    'key71775': 'value17973',
    'key83916': 'value62262',
    'key3322': 'value77269',
    'key24947': 'value33372',
    'key93460': 'value34914',
    'key70790': 'value83426',
    'key45774': 'value86610',
    'key82776': 'value13117',
    'key42634': 'value25417',
},
    {
    'id': 17527482443656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Stephen Hoffman',
    'address': 'PSC 1993, Box 0121\nAPO AP 36735',
    'text': 'Within cost indicate back. Challenge truth never moment. Body mother game similar order business.',
    'email': 'wandagillespie@example.net',
    'phone_number': '(275)602-2342',
    'json': {
    'name': 'Samuel Adams',
    'address': '9561 Roberts Villages\nJerrymouth, WY 09506',
},
    'key82882': 'value28759',
    'key85045': 'value17276',
    'key90402': 'value84951',
},
    {
    'id': 17527482443665,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Rachel Pierce',
    'address': '02444 Peterson Extension\nEast Johnland, MP 31547',
    'text': 'Teach first bar. Executive stock nature everything room television.\nRecent avoid wind trade participant. Study reality amount race. Analysis reality group stay.',
    'email': 'karen52@example.com',
    'phone_number': '001-824-721-8447x068',
    'json': {
    'name': 'Bradley Richardson',
    'address': '4368 Allen Street\nPort Jennifer, PW 79477',
},
    'key27264': 'value37702',
    'key3158': 'value62025',
    'key75930': 'value70122',
    'key62289': 'value29836',
    'key61740': 'value78759',
    'key88953': 'value58500',
},
    {
    'id': 17527482443675,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Richard Baker',
    'address': '4684 Benjamin Stream Suite 349\nNew Danielview, MH 24310',
    'text': 'Whom floor run hour. Hotel let police this identify. Crime agreement chance resource.\nEducation citizen lay author million generation.',
    'email': 'dhickman@example.org',
    'phone_number': '418.924.2371x81050',
    'json': {
    'name': 'Amber Jimenez',
    'address': '5375 Acosta Gateway\nKathleentown, MS 74920',
},
    'key77852': 'value76283',
    'key76374': 'value13898',
    'key76317': 'value20598',
    'key54313': 'value52521',
},
    {
    'id': 17527482443686,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Megan Brooks',
    'address': '596 Jennifer Squares\nChristopherbury, AR 92680',
    'text': 'Amount difference watch similar build arrive again. Drive fact number war project evening.\nCause PM interest forward. Economy mother trade in. Common college watch hundred bit kid.',
    'email': 'mboyle@example.org',
    'phone_number': '819.512.1658x646',
    'json': {
    'name': 'Taylor Martinez',
    'address': '33143 Charles Cape\nSpencerchester, OH 34444',
},
    'key99230': 'value10559',
    'key58236': 'value4368',
    'key4848': 'value68256',
},
    {
    'id': 17527482443697,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Benjamin Jones',
    'address': '17585 Mark Orchard Apt. 577\nTapiafurt, TX 44200',
    'text': 'Point fill likely always watch. Drug else college quality short company. Base base author use field talk.',
    'email': 'michael45@example.com',
    'phone_number': '001-550-625-6760x8016',
    'json': {
    'name': 'Rebecca Lowe',
    'address': '93909 Davenport Islands\nSouth Megan, PA 28877',
},
    'key5400': 'value10836',
    'key20650': 'value54683',
    'key34228': 'value8683',
    'key28016': 'value64501',
    'key79044': 'value91982',
    'key52846': 'value29460',
    'key95150': 'value38568',
    'key69823': 'value19665',
    'key3324': 'value33331',
},
    {
    'id': 17527482443707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Shannon Flowers',
    'address': 'USNV Butler\nFPO AA 62356',
    'text': 'Nothing teacher light democratic. College street certainly contain top.\nLand cultural no forward single. Fact pay operation animal fear. Event prevent force.',
    'email': 'jholloway@example.com',
    'phone_number': '001-918-538-2238',
    'json': {
    'name': 'Michelle Morton',
    'address': '573 Garcia Summit\nNicholasfort, AK 85259',
},
    'key50955': 'value90299',
    'key4095': 'value89901',
    'key34622': 'value1760',
    'key8607': 'value88975',
    'key74174': 'value47438',
    'key13970': 'value9105',
},
    {
    'id': 17527482443717,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Laura Brown',
    'address': '810 Sonya Cape Apt. 283\nWest Emily, WA 59442',
    'text': 'Nor it day talk. May age behavior plant community. Star cause interesting law question thing.',
    'email': 'jill11@example.com',
    'phone_number': '(394)927-0527',
    'json': {
    'name': 'Stacey Olsen',
    'address': '97269 Sarah Station\nEast Williamville, MP 66026',
},
    'key97256': 'value90510',
},
    {
    'id': 17527482443727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Angela Ward',
    'address': 'Unit 9559 Box 0754\nDPO AP 88568',
    'text': 'Base operation crime ahead more prepare state choice. Material stage method way stock. Man how television until stop town. Establish thank generation report.',
    'email': 'thomasherrera@example.com',
    'phone_number': '394.771.5238',
    'json': {
    'name': 'Nathan Dominguez',
    'address': '78709 Jones Valley\nEast Edwardton, PR 35362',
},
    'key45052': 'value71040',
},
    {
    'id': 17527482443737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Debbie Ali',
    'address': '86813 Stephanie Highway Suite 892\nPort Tammiemouth, LA 58621',
    'text': 'Election affect mind agreement whole. Second likely among door under door.\nMarket happy house charge one. Career draw would impact country plant glass marriage. After authority suddenly.',
    'email': 'bnewman@example.net',
    'phone_number': '+1-600-336-5036x6219',
    'json': {
    'name': 'Christopher Keller',
    'address': '29805 Brooks Summit Suite 501\nNorth Beverlymouth, SD 39543',
},
    'key4908': 'value13351',
    'key94665': 'value97500',
    'key42053': 'value50187',
    'key50384': 'value76505',
    'key81996': 'value68875',
    'key51481': 'value90032',
    'key75924': 'value11500',
},
    {
    'id': 17527482443748,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Kari Robinson',
    'address': '059 Julie Radial Apt. 935\nLisaville, CT 82454',
    'text': 'Base must traditional ask save. Hour type and news three.',
    'email': 'edwardscaroline@example.net',
    'phone_number': '+1-980-875-8854x8166',
    'json': {
    'name': 'David Woods',
    'address': '635 Alyssa Forges Apt. 181\nThompsonland, PW 07479',
},
    'key35709': 'value51588',
    'key46678': 'value6993',
    'key20610': 'value71834',
    'key16518': 'value3941',
    'key23468': 'value96984',
    'key62027': 'value94312',
},
    {
    'id': 17527482443760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Richard Rosario',
    'address': '096 Travis Glens Apt. 895\nThomasbury, OR 33167',
    'text': 'Sure relate toward stage energy we mind. President land according civil nice total eat. Painting avoid me investment across.',
    'email': 'thomas38@example.net',
    'phone_number': '+1-692-991-9838x596',
    'json': {
    'name': 'Corey Taylor',
    'address': '607 Blanchard Viaduct Suite 514\nMarthaton, VT 79885',
},
    'key28718': 'value79898',
    'key63424': 'value79683',
    'key53638': 'value32122',
    'key63123': 'value20343',
},
    {
    'id': 17527482443771,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Jacob Taylor',
    'address': '77417 Bell Passage\nMichaelberg, UT 18959',
    'text': 'View radio project military study. Spring go case director very. Black best their hotel top radio.\nApply those cell indicate tend reach thank. Common back take modern.',
    'email': 'annajacobs@example.net',
    'phone_number': '(749)252-0585',
    'json': {
    'name': 'Timothy Thomas',
    'address': 'Unit 7786 Box 4497\nDPO AE 29490',
},
    'key96097': 'value69846',
},
    {
    'id': 17527482443781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Robin Paul',
    'address': '52040 Rivera Highway\nRobinsonstad, WI 08169',
    'text': 'Serious forget too couple city fish. Senior still relate so. Seven and light fight half buy industry.\nFamily policy arrive charge growth draw catch. Us tough bag focus perhaps.',
    'email': 'williamgates@example.com',
    'phone_number': '(400)295-8385x75931',
    'json': {
    'name': 'Tony Baird',
    'address': '161 Caitlin Meadow\nPort Carla, PR 33734',
},
    'key42428': 'value3411',
    'key54639': 'value35976',
    'key32056': 'value80398',
    'key59128': 'value15074',
    'key26521': 'value72268',
},
    {
    'id': 17527482443793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Gerald Pierce',
    'address': '310 Randy Cliffs Suite 326\nConradport, ME 71815',
    'text': 'Consider sort go. Blood military raise. Way old success address stock.\nManager raise blue along. Trouble alone describe air message bring.',
    'email': 'daniel62@example.net',
    'phone_number': '+1-894-440-5220x15215',
    'json': {
    'name': 'Jamie Carpenter',
    'address': '2199 Hernandez Corners\nLake Thomastown, FM 51548',
},
    'key24184': 'value78177',
    'key34583': 'value65816',
    'key28005': 'value40249',
    'key21198': 'value62670',
    'key37942': 'value53816',
    'key9299': 'value21951',
    'key25539': 'value75461',
    'key9750': 'value14886',
    'key5487': 'value73066',
},
    {
    'id': 17527482443804,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Karla Berry',
    'address': '556 Nicole Flat\nNorth Meghanburgh, OH 31602',
    'text': 'South effort per simply personal myself. Few news up road stuff what stop.\nChange discuss fish style dark exist security.',
    'email': 'stephanie47@example.org',
    'phone_number': '001-920-624-9152x69878',
    'json': {
    'name': 'William Lucas',
    'address': '4161 Smith Vista\nWest Michael, NC 56079',
},
    'key62951': 'value34351',
    'key25774': 'value53764',
    'key26993': 'value42634',
    'key83067': 'value38894',
    'key81220': 'value70572',
    'key11789': 'value50532',
    'key54507': 'value61518',
    'key10699': 'value14949',
},
    {
    'id': 17527482443814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Danielle Mejia',
    'address': '50393 Ronald Prairie Apt. 747\nMartinton, VI 59389',
    'text': 'Give ahead old success bed present Democrat. Discussion ok draw. Well last fund customer all man.\nWorker serve fire say. Never pay season lose.',
    'email': 'erin42@example.net',
    'phone_number': '675-502-1695x2226',
    'json': {
    'name': 'Michael Newton',
    'address': '075 Vincent Pine\nSouth Russellburgh, PW 97610',
},
    'key74075': 'value13269',
    'key38510': 'value4048',
    'key9489': 'value18146',
    'key69718': 'value4851',
    'key93163': 'value71767',
    'key7995': 'value89279',
    'key55688': 'value48956',
    'key9935': 'value96701',
    'key58905': 'value76335',
    'key72374': 'value4319',
},
    {
    'id': 17527482443825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Elizabeth Foley',
    'address': '78150 Mitchell Ways\nSouth Kimberly, AK 06472',
    'text': 'Enter most deal. North bring eye marriage heavy. Knowledge toward drive author stop east effort.\nUnit case series beyond age police. Less full still. Friend red this nation business.',
    'email': 'kevinlamb@example.net',
    'phone_number': '001-570-201-4011x2664',
    'json': {
    'name': 'Kristen Castro',
    'address': '640 Ann Flat Apt. 450\nEricfort, VI 05914',
},
    'key5534': 'value33829',
    'key53460': 'value97368',
},
    {
    'id': 17527482443836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Linda Gibbs',
    'address': '94324 Johnson Village Suite 788\nEast Michael, ME 55482',
    'text': 'Up until girl piece. Former agree serve charge open economy agency cost. Third increase Mrs center medical security represent.',
    'email': 'wagnermonique@example.com',
    'phone_number': '679.271.0750',
    'json': {
    'name': 'Patrick Brown',
    'address': '252 Jessica Villages Apt. 613\nMillerbury, NM 30044',
},
    'key98676': 'value13710',
    'key23722': 'value83754',
    'key80464': 'value76027',
    'key30512': 'value58537',
    'key98226': 'value54045',
},
    {
    'id': 17527482443848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Samantha Bell',
    'address': '444 Joseph Port Suite 648\nLake Jacob, KS 94129',
    'text': 'Create television parent Congress. Measure research theory space about.\nLook professor nice eight. Mention day you owner where PM decision.',
    'email': 'waltermay@example.net',
    'phone_number': '3924542158',
    'json': {
    'name': 'Kyle Wilkinson',
    'address': 'Unit 7702 Box 4905\nDPO AP 45804',
},
    'key54699': 'value62685',
    'key25415': 'value32195',
    'key3403': 'value36540',
    'key71081': 'value32624',
    'key7859': 'value28797',
},
    {
    'id': 17527482443857,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Michael May',
    'address': '00774 Christina Pike\nWest Bianca, WV 70730',
    'text': 'Upon already whole left TV sister again wear. Office consumer manage American.\nElection boy top. Company gun big month pressure source. Remember save wind assume news time energy.',
    'email': 'reedkathleen@example.org',
    'phone_number': '001-397-821-6011',
    'json': {
    'name': 'Joseph Nash',
    'address': '28303 Rios Spurs\nKaristad, FM 42145',
},
    'key406': 'value45010',
    'key48076': 'value56760',
    'key35317': 'value44417',
    'key18532': 'value12531',
    'key48501': 'value58595',
    'key27555': 'value7531',
    'key12195': 'value90916',
    'key28699': 'value20305',
    'key43266': 'value65164',
    'key36137': 'value81372',
},
    {
    'id': 17527482443868,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Stephanie Fields',
    'address': '2782 Guerra Center\nGregoryport, NV 59698',
    'text': 'Case fill wall health authority store turn. Bag grow indeed officer.\nPrepare west marriage page onto mind start. Require shoulder professor television challenge.',
    'email': 'pmckinney@example.org',
    'phone_number': '+1-452-237-7771x08770',
    'json': {
    'name': 'Cindy Robinson',
    'address': '349 Steven Plaza\nLake Amandaberg, MO 93920',
},
    'key95664': 'value24719',
    'key40540': 'value93701',
    'key7542': 'value12581',
    'key91303': 'value69281',
    'key43850': 'value95989',
    'key42260': 'value84468',
    'key47445': 'value50994',
    'key37571': 'value6251',
},
    {
    'id': 17527482443878,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Leonard Dickson',
    'address': '57661 Nathan Rapids Apt. 804\nLake Julie, MD 11860',
    'text': 'Able cover available cover condition. Important contain conference culture thing scene. Present business plant create stand.',
    'email': 'christopherbrown@example.org',
    'phone_number': '6025767400',
    'json': {
    'name': 'Jerry Collins',
    'address': '628 Karen Camp Apt. 869\nJonathonland, GU 61760',
},
    'key87326': 'value50217',
    'key3325': 'value83027',
    'key60599': 'value70565',
    'key78333': 'value61370',
},
    {
    'id': 17527482443889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Christopher Patrick',
    'address': '554 Richard Flats Apt. 746\nNorth Pamela, CT 88094',
    'text': 'Land TV less cup fast quickly. Stock by deep hold his.\nReceive offer their cause deal religious describe.',
    'email': 'timothy88@example.org',
    'phone_number': '822.699.6745',
    'json': {
    'name': 'Dawn Thomas',
    'address': '889 Jasmin Plaza Apt. 902\nEast Ashley, GA 13480',
},
    'key1044': 'value97853',
    'key41258': 'value84632',
    'key3364': 'value56773',
    'key38888': 'value21099',
    'key682': 'value94833',
    'key63735': 'value72093',
    'key77183': 'value38804',
    'key41573': 'value10282',
    'key44996': 'value77729',
},
    {
    'id': 17527482443899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Mary Garcia',
    'address': '39246 Courtney Spring Apt. 179\nLake Robert, WY 27560',
    'text': 'Alone that small cultural. Financial newspaper day wind management. Reflect successful collection safe.',
    'email': 'tjohnson@example.com',
    'phone_number': '522-773-5526x98465',
    'json': {
    'name': 'Lindsay Tucker',
    'address': '4542 Cline Island Apt. 034\nPort Andrea, ND 71078',
},
    'key43887': 'value1957',
    'key70693': 'value30571',
    'key92038': 'value70408',
    'key56789': 'value88373',
    'key73002': 'value40825',
    'key65330': 'value35865',
    'key9390': 'value70469',
    'key75957': 'value31903',
    'key23837': 'value84291',
},
    {
    'id': 17527482443910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Kelly Duncan',
    'address': '14305 Kevin Green Suite 804\nTinahaven, MN 27655',
    'text': 'Look itself must nature what move. Life thousand each focus how American consumer. West guess cultural perhaps.\nEntire reduce him thank industry stay. Different civil animal quickly.',
    'email': 'emily80@example.net',
    'phone_number': '(744)661-8914x038',
    'json': {
    'name': 'April Wright',
    'address': '2738 Schneider Forges Suite 640\nPort Randyview, KY 16956',
},
    'key9369': 'value17299',
    'key24893': 'value92352',
    'key44729': 'value38636',
    'key90875': 'value26959',
    'key70686': 'value823',
    'key24568': 'value27025',
    'key10055': 'value6893',
},
    {
    'id': 17527482443921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Anthony Coleman',
    'address': '362 Michelle Union Suite 889\nAllenstad, ID 79301',
    'text': 'Phone lead month machine measure. Present election recently hear let word. Continue science mind town.\nEdge investment across office commercial trade good.',
    'email': 'rlindsey@example.net',
    'phone_number': '001-238-606-1927',
    'json': {
    'name': 'Jason Thomas',
    'address': '6756 Vincent Rest\nElizabethborough, AZ 80480',
},
    'key89100': 'value52150',
    'key23468': 'value21603',
    'key14537': 'value5063',
    'key6978': 'value43728',
    'key71858': 'value24203',
    'key26544': 'value17526',
    'key75368': 'value49938',
    'key68958': 'value84188',
    'key68762': 'value87649',
},
    {
    'id': 17527482443932,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Kendra Barrera',
    'address': '166 Tara Pass\nAndersonborough, CA 02529',
    'text': 'Serious network argue less. Their study cause technology serve. Analysis character ball east short. Plan next wife voice lose.',
    'email': 'ohernandez@example.org',
    'phone_number': '+1-916-512-5976',
    'json': {
    'name': 'Pedro Lucas',
    'address': '868 Connie Villages Apt. 973\nLake Chelseafort, MI 95095',
},
    'key51406': 'value29931',
    'key93807': 'value39893',
    'key34075': 'value48978',
    'key37694': 'value99531',
    'key90945': 'value33341',
},
    {
    'id': 17527482443942,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Cristina Barker',
    'address': '391 Miller Mission Suite 860\nNorth Lisatown, CO 45920',
    'text': 'General ask east yourself particularly than. Stage various service strong interest. Cultural describe miss debate wife whether able.',
    'email': 'miguelmcdonald@example.net',
    'phone_number': '390.322.4594x554',
    'json': {
    'name': 'Jimmy Best',
    'address': '691 Clayton Burg\nGarciastad, DE 08436',
},
    'key64026': 'value16136',
    'key45456': 'value48082',
    'key58104': 'value66702',
    'key98177': 'value27367',
    'key99901': 'value52677',
    'key82938': 'value85594',
    'key27210': 'value43034',
    'key87884': 'value23026',
    'key68550': 'value31451',
},
    {
    'id': 17527482443954,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Shannon Braun',
    'address': '2584 Avila Turnpike Apt. 154\nWest Carla, NY 29300',
    'text': 'Experience take clearly shake determine top institution various. Lawyer drug business there. Shake yet late sense board operation.',
    'email': 'umoore@example.com',
    'phone_number': '4542144317',
    'json': {
    'name': 'Christopher Payne',
    'address': '765 Garcia Junction\nNew Jeffreyside, HI 05774',
},
    'key37015': 'value79324',
    'key20495': 'value25679',
    'key43010': 'value29692',
    'key78988': 'value83244',
    'key88740': 'value48283',
    'key52494': 'value23731',
    'key64996': 'value42896',
    'key22373': 'value45096',
},
    {
    'id': 17527482443965,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Nicholas Brewer',
    'address': '278 Howell Creek\nEast Alan, MT 00523',
    'text': 'Forget loss instead purpose. Professional response ground member student score camera.\nBill imagine happy whether. Music action board stay force.',
    'email': 'blakesarah@example.org',
    'phone_number': '(815)438-5148',
    'json': {
    'name': 'Aaron Jennings',
    'address': '61090 Hampton Locks\nJeremyville, LA 65842',
},
    'key56904': 'value91442',
    'key73404': 'value7738',
    'key74558': 'value94931',
    'key41810': 'value15612',
    'key92309': 'value65451',
},
    {
    'id': 17527482443976,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Shelley Tucker',
    'address': '1463 Joe Trafficway Apt. 773\nSouth James, AL 17329',
    'text': 'Give upon sell many some size big get. Outside stay member. Officer certain result state.\nStudy easy strong population commercial none town. Southern sell imagine rise.',
    'email': 'johnmorris@example.net',
    'phone_number': '686.479.2030x72290',
    'json': {
    'name': 'Christopher Ramos',
    'address': '104 Brandon Center\nLucasmouth, OR 40217',
},
    'key47139': 'value52947',
    'key80446': 'value10722',
},
    {
    'id': 17527482443989,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Emily Evans',
    'address': '874 Sullivan Crescent Apt. 333\nCynthiamouth, VT 78459',
    'text': 'Away nature media outside right challenge. Need any other similar.\nMove most sign clearly yes a international. Without all second possible dream employee.',
    'email': 'ulee@example.com',
    'phone_number': '(682)286-1642',
    'json': {
    'name': 'Matthew Blair',
    'address': '0584 Brandon Tunnel Apt. 593\nSouth Jasmine, MD 48845',
},
    'key84282': 'value10392',
},
    {
    'id': 17527482444001,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Timothy Wood',
    'address': 'USNV Patel\nFPO AA 99791',
    'text': 'Approach national bring send thought run throw. Challenge news grow eat trade film. System particularly eat side.',
    'email': 'austin65@example.net',
    'phone_number': '8028109814',
    'json': {
    'name': 'Brian Adams',
    'address': 'Unit 9254 Box 5079\nDPO AP 35249',
},
    'key38432': 'value62296',
    'key65565': 'value15020',
    'key51970': 'value56463',
    'key36740': 'value47096',
    'key63764': 'value58081',
},
    {
    'id': 17527482444009,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Lindsey Aguilar',
    'address': '6692 Rosario Camp\nLake Cole, WI 95868',
    'text': 'Front civil blood federal. Town beat just.\nPerform material result force course someone. Training what push try. Employee as what often scientist option.',
    'email': 'samuelbest@example.org',
    'phone_number': '878-736-4750',
    'json': {
    'name': 'Ronnie Mcclain',
    'address': '2499 Traci Isle\nSouth Erik, TX 70613',
},
    'key31954': 'value64881',
    'key9175': 'value82857',
    'key55885': 'value25792',
    'key41991': 'value34226',
    'key69286': 'value22263',
},
    {
    'id': 17527482444020,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'James Long DDS',
    'address': '436 Aguirre Rue Suite 879\nNorth Cindyview, OH 06848',
    'text': 'Hit certainly section else yes. Room build reach above beat. Fast loss so. Us dark member water pretty land local.',
    'email': 'christopher65@example.com',
    'phone_number': '896.867.8259',
    'json': {
    'name': 'David Benjamin',
    'address': '29488 Misty Avenue Suite 191\nEast Tara, FM 18939',
},
    'key85318': 'value27398',
    'key50850': 'value45509',
    'key54836': 'value82830',
    'key66174': 'value84067',
},
    {
    'id': 17527482444031,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Gina Vazquez',
    'address': '665 Robert Meadows\nKellyland, FL 80558',
    'text': 'Executive number meet enough. Everything article agree full on. Management then radio involve.\nHuge treatment so nearly. Check small myself whole describe available. Bed modern bill coach task.',
    'email': 'colleen20@example.org',
    'phone_number': '001-731-935-9361x8604',
    'json': {
    'name': 'Mckenzie Davis',
    'address': '15081 Elizabeth Walks Apt. 330\nBriannaside, NY 79473',
},
    'key3542': 'value71834',
    'key360': 'value74397',
    'key41886': 'value25081',
    'key70075': 'value3660',
    'key93497': 'value74293',
},
    {
    'id': 17527482444042,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Robert Williams',
    'address': '6200 Mary Bypass Apt. 337\nMahoneyberg, TX 11644',
    'text': 'Eight lead quickly painting another no pay five. Knowledge born buy rock system. Office hour police bit. Cup meeting have or.\nLoss option security read level. Summer the candidate may.',
    'email': 'lorihogan@example.com',
    'phone_number': '941-964-7973',
    'json': {
    'name': 'Gregory Chung',
    'address': '95259 Rush Heights\nBlankenshipmouth, PR 63791',
},
    'key67872': 'value11591',
    'key57766': 'value50592',
    'key95131': 'value58733',
},
    {
    'id': 17527482444055,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Wayne Carr',
    'address': '3873 Jason Meadow\nJustinfurt, TN 64518',
    'text': 'Store usually appear drop measure son up. Measure anything third treat. Likely when drug once.\nYourself process actually example teach else suddenly establish.',
    'email': 'samantha30@example.com',
    'phone_number': '928-493-6995x081',
    'json': {
    'name': 'Alyssa Jackson',
    'address': '44656 Christina Mall\nLake Brianaville, SC 18534',
},
    'key82680': 'value71094',
    'key99210': 'value15972',
    'key8454': 'value72878',
    'key28664': 'value9750',
    'key44948': 'value47486',
    'key4365': 'value95707',
},
    {
    'id': 17527482444066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Melissa Miller',
    'address': '75779 Young Mews\nNew Devin, UT 92159',
    'text': 'Early worker newspaper produce. Protect view history give less country. Right join same trial to hour town easy.\nEvery couple member house level continue always. Like out heart ever start.',
    'email': 'williamrodriguez@example.com',
    'phone_number': '+1-329-956-8845x33843',
    'json': {
    'name': 'Kelly Boyle',
    'address': '2941 William Square Suite 514\nStewartstad, VI 83627',
},
    'key98247': 'value15825',
    'key45603': 'value12106',
    'key83685': 'value89530',
},
    {
    'id': 17527482444079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Tara Chapman',
    'address': 'USS Watson\nFPO AP 66904',
    'text': 'Along moment color along. Blue voice through daughter they improve sense. Itself anyone day difference task.',
    'email': 'juanromero@example.net',
    'phone_number': '001-956-675-5626x453',
    'json': {
    'name': 'Jessica Shepherd',
    'address': '32311 Schneider Circle\nNew Stevenmouth, HI 29308',
},
    'key74030': 'value84513',
    'key97617': 'value43351',
    'key51003': 'value86614',
    'key9360': 'value77294',
    'key40474': 'value63489',
},
    {
    'id': 17527482444090,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Rebecca Miller',
    'address': '90663 Woods Prairie Apt. 503\nFishershire, HI 14733',
    'text': 'Television individual clearly model old body. Exactly difference reach size house.\nIdentify past positive employee push. Training picture drive or cold time beautiful.',
    'email': 'kristingray@example.com',
    'phone_number': '770-505-2331x092',
    'json': {
    'name': 'Monica Barnes',
    'address': '91337 Hill Gardens\nSouth Danielton, PR 83165',
},
    'key74547': 'value36559',
    'key25965': 'value58471',
    'key28844': 'value31587',
    'key5407': 'value74704',
    'key66554': 'value44001',
    'key33528': 'value22028',
    'key89230': 'value43346',
    'key39731': 'value66538',
    'key9873': 'value7172',
    'key23329': 'value59791',
},
    {
    'id': 17527482444102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Patrick Lee',
    'address': '959 Michael Hills\nNew Robert, NH 99013',
    'text': 'From take six only claim. Nature response develop behind sister window. Arrive increase we second garden west attack.',
    'email': 'david45@example.com',
    'phone_number': '+1-245-945-6119',
    'json': {
    'name': 'Laurie Davidson',
    'address': '992 Garrett Islands Apt. 079\nWest Davidland, UT 08449',
},
    'key58735': 'value20619',
    'key19101': 'value869',
    'key78693': 'value17592',
    'key32177': 'value95596',
    'key32620': 'value80587',
    'key67505': 'value32698',
},
    {
    'id': 17527482444112,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Margaret Rush',
    'address': '20857 Reyes Valley\nNew Ann, CO 28121',
    'text': 'Step would physical report exist eat major. Us along idea front option generation cost prevent.\nArticle adult note town ok. Once while court build collection. Game some among there mind measure much.',
    'email': 'danielreed@example.net',
    'phone_number': '469-398-9242x8825',
    'json': {
    'name': 'Randall Garcia',
    'address': '15368 Deanna Hills\nNew Larry, ID 14847',
},
    'key67315': 'value35357',
    'key95271': 'value53302',
    'key82756': 'value73325',
    'key88500': 'value11734',
    'key44230': 'value84599',
    'key74138': 'value21982',
    'key21502': 'value97720',
    'key51548': 'value28857',
},
    {
    'id': 17527482444124,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Aaron Rhodes',
    'address': '77936 Ronald Alley\nWest Dianaside, NC 18599',
    'text': 'Movement create onto son develop future key write. Notice agent leave almost. Development wonder reduce.',
    'email': 'gchoi@example.net',
    'phone_number': '001-367-841-9773x7704',
    'json': {
    'name': 'Debbie Hernandez',
    'address': '692 Moore Extensions\nJoshuaburgh, PA 67695',
},
    'key58212': 'value95334',
    'key33464': 'value13586',
    'key46396': 'value58243',
    'key32412': 'value64961',
    'key79344': 'value83605',
    'key89004': 'value28303',
},
    {
    'id': 17527482444135,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Steven Bauer',
    'address': '963 Mason Bridge Suite 478\nHernandezburgh, VI 64638',
    'text': 'Accept trial today board. Group step yeah.\nStyle daughter score Congress technology. Personal pick big for.',
    'email': 'bishopgerald@example.com',
    'phone_number': '001-323-233-3818x1954',
    'json': {
    'name': 'Joshua Ramos',
    'address': '3135 Hannah Station Apt. 239\nEast Jonathanmouth, UT 35721',
},
    'key34027': 'value13378',
    'key96369': 'value2604',
    'key78173': 'value37794',
    'key41882': 'value56278',
    'key32188': 'value54242',
},
    {
    'id': 17527482444147,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Richard Rowe',
    'address': '3513 Morales Spring Suite 486\nNew Tina, DC 63674',
    'text': 'Value important career avoid ready small bring. Full admit inside. Learn tax continue race thank result.\nAgree enter those quality sit mind force.',
    'email': 'washingtonangelica@example.net',
    'phone_number': '367.297.4630x675',
    'json': {
    'name': 'Adam Silva',
    'address': '68501 Santos Union\nAcostatown, HI 74611',
},
    'key74867': 'value57715',
    'key17534': 'value7330',
    'key89078': 'value11667',
    'key90355': 'value94863',
    'key75496': 'value61932',
    'key42860': 'value60159',
    'key64896': 'value32963',
},
    {
    'id': 17527482444159,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Mary Middleton',
    'address': 'PSC 3490, Box 3283\nAPO AA 55585',
    'text': 'Onto quite very interest. Cold develop spring talk these.\nRequire list themselves degree ten reality feeling. Wear language admit many pattern. Organization once know.',
    'email': 'millerkyle@example.com',
    'phone_number': '474.281.9262',
    'json': {
    'name': 'Dana Tucker',
    'address': '3810 Haley Junction Apt. 270\nCassidyfurt, SD 30972',
},
    'key48734': 'value12201',
    'key17400': 'value65298',
    'key71802': 'value69572',
    'key28118': 'value6997',
},
    {
    'id': 17527482444168,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Roy Nichols',
    'address': '437 Jamie Fork Suite 159\nDaniellemouth, TN 78330',
    'text': 'Use system affect finally. Good understand us order bit beyond.\nStructure point history notice. Doctor according than successful turn feel other.',
    'email': 'adkinsjessica@example.net',
    'phone_number': '886.332.1152x376',
    'json': {
    'name': 'Kristen Wilson',
    'address': '771 Anne Terrace\nEast Matthewton, WI 23283',
},
    'key50755': 'value75031',
    'key13212': 'value4814',
    'key47420': 'value23000',
    'key88703': 'value96047',
    'key8672': 'value91610',
    'key48433': 'value87368',
    'key61771': 'value17051',
    'key51490': 'value23115',
    'key97503': 'value17928',
    'key13087': 'value67713',
},
    {
    'id': 17527482444179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Heather Green',
    'address': '9223 Smith Groves Apt. 397\nMunozland, PR 68019',
    'text': 'Happy note leader fire about. Science present part reality. Deal sometimes race during prevent win Republican stage.',
    'email': 'svaughan@example.org',
    'phone_number': '+1-518-898-2957x62039',
    'json': {
    'name': 'Shannon Mendoza',
    'address': '8415 Daugherty Oval Apt. 536\nBrookeside, OR 95167',
},
    'key31020': 'value45282',
    'key95708': 'value67117',
    'key6131': 'value81397',
    'key93560': 'value97809',
    'key51146': 'value496',
    'key40897': 'value17071',
    'key30087': 'value14599',
    'key14269': 'value58408',
    'key86197': 'value15806',
    'key57254': 'value97231',
},
    {
    'id': 17527482444191,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Donald Brooks',
    'address': '0372 Oneill Plaza\nGregoryview, LA 27630',
    'text': 'Push eye account agency finish while accept. However mean theory method return whose involve everyone. Result quickly trip church whole finally station.',
    'email': 'lindsay30@example.net',
    'phone_number': '(231)701-3787x813',
    'json': {
    'name': 'Alexander Howell',
    'address': '22210 Robert Lock Apt. 046\nWest Melissaberg, NV 70959',
},
    'key48643': 'value10302',
},
    {
    'id': 17527482444203,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Laurie Robinson',
    'address': '35176 Robert Drive Apt. 304\nSouth Markport, DC 83636',
    'text': 'It better time whole I one dinner. Smile trade ground. Power such personal. Baby either use.',
    'email': 'holly70@example.org',
    'phone_number': '+1-760-353-5763x5702',
    'json': {
    'name': 'Paul Randall',
    'address': '2493 Rebecca Highway\nLake Justin, ME 35084',
},
    'key51413': 'value30345',
    'key68539': 'value32484',
    'key1825': 'value99731',
    'key64062': 'value48409',
    'key46460': 'value98780',
    'key85026': 'value68624',
    'key28912': 'value12362',
    'key57231': 'value72579',
    'key25244': 'value77358',
},
    {
    'id': 17527482444214,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Courtney Love',
    'address': '9756 Alyssa Via\nAnnahaven, MO 31296',
    'text': 'Leg east democratic brother away audience lot. Trial stock prove realize. Stay beyond anything ago opportunity.\nMan almost four.',
    'email': 'anthonydixon@example.org',
    'phone_number': '484.593.6075',
    'json': {
    'name': 'John Cantu',
    'address': '77159 Rebekah Squares Suite 821\nLucasview, DC 19358',
},
    'key46237': 'value58995',
    'key87909': 'value40379',
    'key80790': 'value69783',
    'key42417': 'value56670',
    'key84509': 'value89308',
    'key61225': 'value20360',
    'key63033': 'value72438',
    'key57299': 'value55127',
},
    {
    'id': 17527482444226,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Ryan Kim',
    'address': '6824 Erika Route Suite 208\nNicholasville, NJ 68550',
    'text': 'Believe arrive argue factor. Study fire test significant everything question.',
    'email': 'irwinariana@example.net',
    'phone_number': '(634)942-3247x07330',
    'json': {
    'name': 'Terry Lopez',
    'address': '0573 Andrew Greens\nEast Cherylberg, LA 16039',
},
    'key28527': 'value40923',
},
    {
    'id': 17527482444238,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Frederick Gomez',
    'address': '4871 Laura Grove Apt. 339\nEast Christian, MO 46485',
    'text': 'Read performance political among hospital box political. Side sister should give price box task. State star range try let specific.',
    'email': 'elizabeth91@example.com',
    'phone_number': '894-254-5652x00222',
    'json': {
    'name': 'Michelle Mcmahon',
    'address': 'USCGC Coleman\nFPO AE 68902',
},
    'key79715': 'value50954',
    'key57070': 'value95245',
    'key77657': 'value72028',
    'key32279': 'value69406',
    'key33817': 'value61027',
    'key15741': 'value56751',
    'key4728': 'value45919',
},
    {
    'id': 17527482444249,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Anthony Ward',
    'address': '275 Erik Coves\nLeahborough, VI 93867',
    'text': 'Power measure activity right record. As personal need expect expect TV raise. Stage work eight just current.\nWind in budget scene particularly we. Computer stuff these.',
    'email': 'bensonbryan@example.net',
    'phone_number': '912.368.1404x264',
    'json': {
    'name': 'Eric Navarro',
    'address': 'Unit 3571 Box 5738\nDPO AE 24780',
},
    'key16128': 'value79049',
    'key90159': 'value52951',
    'key96112': 'value27984',
},
    {
    'id': 17527482444259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Rebecca Ray',
    'address': '61126 Edward Fields\nNorth Jenniferville, VT 77559',
    'text': 'Meeting himself weight mean. Concern study quality quality traditional treatment.',
    'email': 'yuvirginia@example.net',
    'phone_number': '863-642-3788x05312',
    'json': {
    'name': 'Richard Vargas',
    'address': 'PSC 0739, Box 6702\nAPO AP 05449',
},
    'key4649': 'value52999',
    'key47140': 'value29762',
    'key18507': 'value57296',
    'key18766': 'value51099',
},
    {
    'id': 17527482444269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Sara Lawson',
    'address': '77555 Freeman Island Suite 171\nSouth Crystalside, ME 62073',
    'text': 'Leg understand them another bad gun. Commercial down issue probably list if big.\nSize ok spring analysis of. Address as sport staff.',
    'email': 'madams@example.org',
    'phone_number': '(868)802-2008x30072',
    'json': {
    'name': 'Robert Todd',
    'address': '624 Parsons Fall Apt. 421\nNorth Teresa, CO 06860',
},
    'key89638': 'value26311',
    'key89727': 'value56924',
    'key69594': 'value89849',
    'key51086': 'value71899',
    'key82937': 'value8699',
    'key19542': 'value14640',
    'key37846': 'value16753',
    'key83200': 'value33892',
    'key41799': 'value68669',
},
    {
    'id': 17527482444281,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Daniel Simmons',
    'address': '104 Stephanie Inlet\nPort Joanneview, HI 55444',
    'text': 'Few less above bag member shoulder. Prepare ten remember police do way at heart. Near art whatever culture have.\nInvestment pay sit should house.',
    'email': 'terry49@example.net',
    'phone_number': '(312)641-0919x8225',
    'json': {
    'name': 'Laura Moore',
    'address': '689 Osborn Parks Suite 279\nJohnmouth, ND 35023',
},
    'key82944': 'value25949',
    'key21325': 'value5967',
    'key12779': 'value50559',
    'key87053': 'value5488',
    'key73027': 'value66748',
},
    {
    'id': 17527482444292,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Antonio Hammond',
    'address': '7753 Moreno Rapids\nWoodfurt, NC 42720',
    'text': 'Could small necessary return seek. Near free eat avoid. Economic road those series several focus her.\nMoment about owner course role call. Matter reveal by book food environmental.',
    'email': 'marthanguyen@example.org',
    'phone_number': '(989)643-9488x348',
    'json': {
    'name': 'Samuel Beck',
    'address': '12793 Deborah Motorway\nErikaland, MO 71057',
},
    'key86204': 'value45304',
    'key23604': 'value57898',
    'key94888': 'value13512',
    'key94562': 'value85915',
    'key96612': 'value64627',
    'key79927': 'value1463',
    'key15788': 'value90223',
    'key69217': 'value52233',
    'key62667': 'value94749',
    'key71135': 'value83196',
},
    {
    'id': 17527482444305,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Dillon Drake',
    'address': '6897 Rebecca Court Apt. 539\nPort Jessicaport, NE 08949',
    'text': 'Whatever money party western. Democratic interesting stuff maybe occur director language.\nRequire sound real until. Quickly forward us.',
    'email': 'david10@example.net',
    'phone_number': '(578)639-7806x0428',
    'json': {
    'name': 'Amy King',
    'address': '927 Banks Crossroad\nNorth Lance, OH 39697',
},
    'key91976': 'value51385',
    'key50319': 'value41457',
    'key51691': 'value14390',
    'key92323': 'value63824',
    'key41780': 'value27557',
    'key97852': 'value39488',
    'key16785': 'value56657',
},
    {
    'id': 17527482444316,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Melissa Rogers',
    'address': '990 Kimberly Divide Apt. 790\nEast Audreyberg, OR 45741',
    'text': 'Mind understand green teacher officer. Life hit quality entire few computer reduce. Report doctor debate see.\nSociety point during hospital suggest spring. Wonder commercial she.',
    'email': 'jmckee@example.org',
    'phone_number': '(539)417-8626x360',
    'json': {
    'name': 'Deborah Holmes',
    'address': '2664 Russell Meadow\nNew Amber, VI 98432',
},
    'key61265': 'value41126',
},
    {
    'id': 17527482444328,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Anthony Murphy',
    'address': 'USS Bishop\nFPO AE 95882',
    'text': 'Bad bar light experience heart start American food. Western open view cut person. Issue away perhaps always long kid drop less.\nClear late indeed professional road tax.',
    'email': 'destinywatkins@example.org',
    'phone_number': '(483)868-6496x097',
    'json': {
    'name': 'Sheri Horne',
    'address': '7281 Cody Corner\nLaurenmouth, WI 75780',
},
    'key25622': 'value45724',
    'key72113': 'value49844',
    'key39760': 'value66985',
    'key35465': 'value48283',
},
    {
    'id': 17527482444340,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Kenneth Harrison',
    'address': '16495 Brown Lights\nLake Jessicafurt, SC 46701',
    'text': 'Response maybe guess appear list.\nBudget drop apply report bag writer this. Month practice those play resource leave loss. Speak onto difficult might treat.',
    'email': 'bwagner@example.com',
    'phone_number': '3474342888',
    'json': {
    'name': 'Spencer Mcmahon',
    'address': '79774 Campos Forest Apt. 986\nGlasshaven, AZ 59897',
},
    'key94229': 'value43912',
    'key84879': 'value5972',
    'key44554': 'value52737',
    'key13166': 'value8330',
    'key36855': 'value33768',
},
    {
    'id': 17527482444353,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Taylor Miller',
    'address': '494 Crystal Terrace\nWest William, MN 59464',
    'text': 'Service almost large company organization behind. Consider rock choose fact. Partner teach suddenly artist.',
    'email': 'esims@example.net',
    'phone_number': '+1-251-956-5292',
    'json': {
    'name': 'Travis Washington',
    'address': '72268 Smith Islands Apt. 530\nChaseburgh, AS 50619',
},
    'key38092': 'value38873',
    'key97880': 'value67030',
    'key95848': 'value47152',
    'key39498': 'value35912',
    'key42010': 'value65032',
    'key15550': 'value15975',
},
    {
    'id': 17527482444364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Rachel Owens',
    'address': '88714 Johnson Manor Suite 736\nEast Charlenefurt, MD 67341',
    'text': 'Mention stuff no figure consider. Foot bar return important information.\nTheory any industry environment old manage power late. Three as focus agreement. With customer sing society race travel fast.',
    'email': 'iwhite@example.com',
    'phone_number': '441.985.5335x786',
    'json': {
    'name': 'Elizabeth Bates',
    'address': '3137 Miller Route\nDouglasside, CA 24773',
},
    'key25217': 'value64224',
    'key64276': 'value7641',
    'key30412': 'value75060',
    'key46547': 'value8772',
    'key58702': 'value83066',
    'key34239': 'value50991',
    'key27141': 'value84833',
},
    {
    'id': 17527482444377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Charles Lopez',
    'address': '5215 Moore Ridges\nSouth Juliafurt, NM 33658',
    'text': 'Really tax yard lose feel. Because peace use.\nSound age early easy game others. Send magazine wide improve audience. Product human best best in.',
    'email': 'pwatts@example.net',
    'phone_number': '001-641-457-4792x141',
    'json': {
    'name': 'Gary Fowler',
    'address': '7653 Harmon Mission Apt. 903\nTaylorfort, SC 02738',
},
    'key40031': 'value35001',
    'key16523': 'value99811',
    'key42642': 'value68524',
    'key62242': 'value86202',
    'key9923': 'value56561',
    'key24680': 'value22245',
},
    {
    'id': 17527482444391,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Michael Palmer',
    'address': '224 Spencer Forest Suite 672\nSouth Gary, DE 50989',
    'text': 'Million yes family including. Beautiful choose seat.\nOperation arrive support yourself.\nSingle left trade support. Morning card task easy voice thus. Someone college career network human.',
    'email': 'briannacastro@example.com',
    'phone_number': '960.724.1264x63139',
    'json': {
    'name': 'Leslie Ford',
    'address': '063 Morgan Branch Apt. 766\nLake Amandaview, MS 30551',
},
    'key16112': 'value12241',
    'key96912': 'value54533',
    'key69181': 'value63999',
    'key19150': 'value42440',
},
    {
    'id': 17527482444405,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Amber Torres',
    'address': '1214 Deanna Burgs Suite 614\nEast Jillian, KS 23680',
    'text': 'Shake brother everything difficult fly. Society when rule industry nothing group such. Task about so lead sense.\nReality since available glass nearly if very.',
    'email': 'victoria52@example.org',
    'phone_number': '(499)525-2091x39287',
    'json': {
    'name': 'Anthony Francis',
    'address': '995 Joshua Overpass Apt. 182\nMitchellchester, OK 47222',
},
    'key74570': 'value1607',
    'key20917': 'value62248',
    'key47022': 'value61823',
    'key12730': 'value18294',
    'key7289': 'value25766',
    'key20715': 'value84446',
    'key8396': 'value53135',
    'key46682': 'value74777',
    'key67729': 'value82053',
    'key79925': 'value102',
},
    {
    'id': 17527482444416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Michael Roberts',
    'address': '48693 Pamela Rapid\nLindamouth, DC 54882',
    'text': 'Our another glass stuff party system. Address say win bad democratic dinner.\nIdea thus exactly any candidate. Effort stay safe guy song run. Boy trip fire argue design task.',
    'email': 'zjohnson@example.com',
    'phone_number': '496-696-1052x7517',
    'json': {
    'name': 'Logan Smith',
    'address': '499 Paul Brooks\nNew Petertown, PR 71284',
},
    'key29914': 'value70066',
    'key88293': 'value65475',
    'key58670': 'value43915',
    'key91669': 'value68963',
    'key84541': 'value94365',
    'key95851': 'value47624',
    'key25835': 'value64722',
    'key15823': 'value85819',
},
    {
    'id': 17527482444427,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Erin Holmes',
    'address': '60055 Anthony Path Suite 154\nMitchellport, GU 71607',
    'text': 'The natural have wonder teach. Also house experience better anything nature interesting.',
    'email': 'jessesmith@example.org',
    'phone_number': '573-291-8021x1238',
    'json': {
    'name': 'Jamie Brewer',
    'address': '39829 Alvarez Stravenue Apt. 900\nNicoleview, SC 36778',
},
    'key44906': 'value14991',
    'key84975': 'value75174',
    'key70864': 'value74010',
    'key85259': 'value79387',
    'key50500': 'value32543',
    'key40341': 'value29858',
    'key5798': 'value29227',
    'key55997': 'value2709',
    'key80497': 'value52946',
    'key62729': 'value98536',
},
    {
    'id': 17527482444440,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Emily Burnett',
    'address': '98711 Toni Cliffs\nSmithton, IL 83202',
    'text': 'Citizen throw special box. Rest pull bit may practice arm talk.\nDream test yet whom white.',
    'email': 'fcastro@example.org',
    'phone_number': '+1-209-353-4009',
    'json': {
    'name': 'Cynthia Stafford',
    'address': '62626 Aguirre Lights\nPort Michael, NV 21824',
},
    'key73360': 'value21187',
    'key4087': 'value93857',
},
    {
    'id': 17527482444451,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Barbara Foster',
    'address': '22471 Aguilar Spur Apt. 313\nSalasstad, NE 54202',
    'text': 'Draw effect visit collection plant once. Page store general read call red.\nBelieve window word moment. Business energy throw because station finish paper. Perhaps some section purpose set.',
    'email': 'uscott@example.com',
    'phone_number': '(402)416-1812x59580',
    'json': {
    'name': 'Joshua Nelson',
    'address': '8587 Grace Mall Suite 710\nNew Jacquelinemouth, MI 80157',
},
    'key40892': 'value68017',
    'key71963': 'value16160',
    'key50446': 'value71873',
    'key37101': 'value34220',
    'key81913': 'value2903',
},
    {
    'id': 17527482444463,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'James Johnson',
    'address': '9387 Morgan Brooks\nDorothyborough, PW 58721',
    'text': 'Girl nature hit recognize quality pull research rock. Tell peace growth wall worry institution. Deal democratic bit discuss house positive star.',
    'email': 'lisabennett@example.com',
    'phone_number': '583-472-0113x19118',
    'json': {
    'name': 'Thomas Smith',
    'address': '850 Paula Loaf\nHenrymouth, KS 40097',
},
    'key27340': 'value86573',
    'key80556': 'value19558',
    'key54493': 'value75909',
    'key28961': 'value38344',
    'key22642': 'value10996',
    'key4451': 'value13974',
    'key47740': 'value46200',
    'key49068': 'value17660',
    'key24244': 'value33992',
},
    {
    'id': 17527482444475,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Ronald Thompson',
    'address': '509 Tamara Trace Suite 351\nPort Briantown, NE 69581',
    'text': 'Every major admit continue truth.\nWithout about product interesting into college once. Suffer together carry society need. Not rather teacher feel month few.',
    'email': 'scurtis@example.org',
    'phone_number': '900-366-1216',
    'json': {
    'name': 'Michelle Fox',
    'address': '816 Bruce Curve Suite 418\nFreemanfort, OK 81715',
},
    'key38065': 'value57024',
    'key57018': 'value27771',
    'key41488': 'value20408',
    'key34123': 'value54921',
    'key8143': 'value9909',
    'key21976': 'value66996',
    'key86695': 'value40412',
    'key80153': 'value33655',
    'key9529': 'value24175',
    'key50643': 'value30721',
},
    {
    'id': 17527482444486,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Kristy Walker',
    'address': '07172 King Turnpike\nSouth Jennifer, VT 91282',
    'text': 'Scene fast compare against personal else. Talk avoid simple. Eye daughter yeah theory red realize.',
    'email': 'hschneider@example.com',
    'phone_number': '531.484.7028',
    'json': {
    'name': 'Samuel Lane',
    'address': '5187 Stewart Divide Apt. 927\nKingview, MH 05379',
},
    'key84139': 'value20191',
},
    {
    'id': 17527482444497,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Jeffrey Berg',
    'address': '2881 Pierce Alley Apt. 074\nBrianton, WI 65325',
    'text': 'Investment each step box. Response form Republican activity people arm.\nWhat hospital speak remain. Great it race will job. Soldier situation treatment property father wall.',
    'email': 'fbutler@example.com',
    'phone_number': '+1-597-364-4612x3282',
    'json': {
    'name': 'Michael Butler',
    'address': '75308 Neal Island Suite 206\nSpencerburgh, CO 89153',
},
    'key63096': 'value20240',
    'key65826': 'value47319',
    'key1773': 'value46939',
    'key25162': 'value61724',
},
    {
    'id': 17527482444509,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Kristen Rhodes',
    'address': '7717 Brown Track\nSummersside, AS 07699',
    'text': 'Serious site democratic long quality behind.\nEnergy response culture believe single from save. Child interview nation black owner meeting statement.',
    'email': 'dmann@example.net',
    'phone_number': '248-942-3913',
    'json': {
    'name': 'Paige Jennings',
    'address': '32952 Ayala Extension Suite 326\nMichaelview, MH 84819',
},
    'key66072': 'value71944',
    'key49224': 'value1081',
    'key78431': 'value7995',
    'key43140': 'value77066',
    'key26141': 'value70114',
    'key20965': 'value17102',
    'key36404': 'value78684',
    'key48983': 'value35030',
    'key68100': 'value31072',
    'key16935': 'value7120',
},
    {
    'id': 17527482444521,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Thomas Rice',
    'address': '39871 Evans Cliff\nWest Kathryn, MO 09401',
    'text': 'Heart bit local full never start try. Economic light will lot.\nPartner population finally it. World understand growth everyone.',
    'email': 'slyons@example.com',
    'phone_number': '373.973.7020',
    'json': {
    'name': 'Natalie Wilcox',
    'address': '047 Patricia Well Apt. 896\nWest John, MD 44842',
},
    'key55014': 'value95539',
    'key96590': 'value42913',
    'key67174': 'value34877',
    'key67898': 'value82913',
    'key78910': 'value97816',
    'key966': 'value32403',
    'key5911': 'value71742',
},
    {
    'id': 17527482444532,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Laura Robinson',
    'address': '534 Gary Harbor Suite 919\nLake Joshua, DE 60934',
    'text': 'Maybe already case ability yourself seek kitchen. Near institution political test during at.\nBefore dog education white although answer. Figure college government learn method why.',
    'email': 'gordonfrederick@example.com',
    'phone_number': '(853)630-3485x774',
    'json': {
    'name': 'Catherine Cunningham',
    'address': '1731 Abbott Way\nNorth Kristybury, GU 67022',
},
    'key11880': 'value41699',
    'key16466': 'value72209',
},
    {
    'id': 17527482444544,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Rachel Morrow',
    'address': '935 Sandra Pine Apt. 830\nMatthewchester, NH 60725',
    'text': 'Card front wait key environment. List choice American since since senior there smile. Among tree serious contain question term anything.\nPick guy where issue test growth suddenly.',
    'email': 'brandon00@example.org',
    'phone_number': '261-579-5584',
    'json': {
    'name': 'Laura Schmidt',
    'address': '32322 Evelyn Forges Suite 903\nSouth Gabrielhaven, UT 30091',
},
    'key97129': 'value48175',
},
    {
    'id': 17527482444555,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Katherine Estrada',
    'address': '137 Thomas Inlet\nHughesstad, VA 08387',
    'text': 'Clearly green start energy partner. Age friend fill. When manager good reason statement job lawyer.',
    'email': 'courtneylee@example.org',
    'phone_number': '731.443.8058x122',
    'json': {
    'name': 'Brandi Moore',
    'address': '864 James Row\nSouth Barbara, PA 33575',
},
    'key70859': 'value56896',
    'key32305': 'value43676',
    'key92635': 'value36620',
    'key87586': 'value35522',
    'key31852': 'value34795',
    'key92160': 'value81864',
    'key77563': 'value51184',
    'key73102': 'value82252',
    'key25113': 'value28080',
    'key88762': 'value76505',
},
    {
    'id': 17527482444568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Tammy Walker',
    'address': '1014 Michael Landing Suite 861\nLake Kevin, OK 45444',
    'text': 'Purpose far the bill research material. Pressure trade learn finally. Same statement sometimes local ok form face same.\nTime word car well. Common customer plant type voice expect.',
    'email': 'brenda92@example.org',
    'phone_number': '708-883-5821',
    'json': {
    'name': 'Jennifer Miller',
    'address': '32346 Nelson Wall Suite 504\nJonathanport, CT 24632',
},
    'key11026': 'value33086',
    'key46053': 'value53189',
    'key20504': 'value37313',
    'key87506': 'value16831',
},
    {
    'id': 17527482444579,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Amy Greene',
    'address': '697 Martin Lakes Suite 252\nNorth Melissa, NH 98519',
    'text': 'Apply last gas military country us home. Bank option in.',
    'email': 'fieldsholly@example.com',
    'phone_number': '001-673-687-7681x64039',
    'json': {
    'name': 'Victoria Smith',
    'address': '206 Erin Circles\nNorth Valerieview, MO 10542',
},
    'key86340': 'value28957',
    'key79945': 'value82926',
    'key36154': 'value11537',
    'key81960': 'value40293',
    'key23599': 'value21491',
    'key79326': 'value45499',
    'key7427': 'value75506',
    'key50336': 'value20014',
    'key45407': 'value8912',
    'key50579': 'value32676',
},
    {
    'id': 17527482444591,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Carrie Rios',
    'address': 'Unit 6446 Box 4969\nDPO AA 91288',
    'text': 'Increase his act teach president. Cause have doctor though list oil.\nHe think pick least green nor talk. Scene strategy sort exist along.\nPlayer company road music.',
    'email': 'murphyamanda@example.com',
    'phone_number': '(348)947-7757x7147',
    'json': {
    'name': 'Bryan Miller',
    'address': 'Unit 2112 Box 6305\nDPO AE 82316',
},
    'key19431': 'value89003',
    'key97590': 'value69715',
    'key64375': 'value33463',
    'key75697': 'value67891',
    'key67559': 'value9276',
    'key31477': 'value84366',
    'key54767': 'value43798',
    'key29952': 'value12459',
    'key76182': 'value66063',
},
    {
    'id': 17527482444600,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Monica Wilson',
    'address': '7327 Williams Shore Apt. 907\nWest Jasonborough, PA 34204',
    'text': 'Ball hour easy pattern economic. Drug senior machine employee police billion building. Party forget trial chair social.',
    'email': 'johnwalker@example.com',
    'phone_number': '(916)816-0596x0537',
    'json': {
    'name': 'Lindsey Newton',
    'address': '791 Hall Radial Apt. 422\nShaunfort, VI 67499',
},
    'key55568': 'value90693',
    'key86398': 'value69647',
    'key10318': 'value79',
    'key46848': 'value58159',
    'key45789': 'value90775',
    'key72099': 'value36466',
},
    {
    'id': 17527482444612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Sara Hurst',
    'address': '327 Gary Forest\nTimothyborough, KS 96237',
    'text': 'Project social goal your test he evidence. From hit money look easy feeling.\nWall southern member blue fight line. Clearly direction form deal charge middle. Issue door serve throw into how unit.',
    'email': 'suzanne24@example.com',
    'phone_number': '(501)814-3980',
    'json': {
    'name': 'Richard Clark',
    'address': 'USNV Johnson\nFPO AE 86618',
},
    'key64686': 'value41671',
    'key36456': 'value89734',
    'key33429': 'value64439',
    'key17149': 'value62358',
},
    {
    'id': 17527482444621,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Brian Gonzalez',
    'address': '45078 Brock Vista\nWest Margaret, MA 39533',
    'text': 'Machine parent yourself Democrat. Increase common shake at top approach.\nGoal behind national author these above. Exactly air ball difference control energy center. Whose join political charge style.',
    'email': 'marcosnyder@example.net',
    'phone_number': '915.889.2375x64846',
    'json': {
    'name': 'Michael Nelson',
    'address': '58246 Green Estates Apt. 300\nHannahburgh, DE 94008',
},
    'key24804': 'value61029',
    'key93449': 'value79599',
    'key4361': 'value63844',
    'key60163': 'value22223',
    'key62661': 'value29431',
    'key38624': 'value36182',
},
    {
    'id': 17527482444634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Jennifer Hart',
    'address': 'USNV Carroll\nFPO AP 99226',
    'text': 'Now card go. Contain significant article might laugh. Statement score consumer skill. Short act either election lay.',
    'email': 'traceydaniels@example.org',
    'phone_number': '+1-683-547-4722x290',
    'json': {
    'name': 'Richard Perry',
    'address': '28523 Cook Inlet Apt. 369\nNorth Daniel, WV 94781',
},
    'key51459': 'value11927',
    'key98440': 'value14710',
},
    {
    'id': 17527482444645,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Lawrence Elliott',
    'address': '5716 Bell Plain Apt. 419\nPort Chad, NM 13322',
    'text': 'Such oil so. Boy movie executive. One maintain her.\nRepresent wide stuff data.',
    'email': 'stacey04@example.org',
    'phone_number': '(902)584-9778x751',
    'json': {
    'name': 'Robert Davis',
    'address': '470 Estes Rapid\nSamanthashire, HI 67868',
},
    'key53736': 'value86816',
    'key74802': 'value90722',
},
    {
    'id': 17527482444657,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Victoria Bradford',
    'address': '67355 James Prairie Apt. 265\nSouth Timothy, AK 27271',
    'text': 'Man yes strategy team believe. Drug our idea fight where training. Floor behind daughter administration affect deep if discover.\nThen college voice minute manager discuss.',
    'email': 'barnesalexa@example.net',
    'phone_number': '+1-910-759-5515x0388',
    'json': {
    'name': 'Cristina Klein',
    'address': '41697 James Trail Suite 893\nSouth Colleen, NY 54412',
},
    'key57576': 'value8266',
    'key88533': 'value80440',
    'key61503': 'value65996',
    'key70817': 'value97421',
},
    {
    'id': 17527482444669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Robert Morgan',
    'address': '4990 Solomon Fords Apt. 128\nCollinschester, OK 19637',
    'text': 'Minute address job successful soon consumer his. Usually baby east herself. Effort national environmental election surface newspaper practice.',
    'email': 'mmorgan@example.org',
    'phone_number': '685.693.9475x9479',
    'json': {
    'name': 'Stephanie Richardson',
    'address': '34743 Sanders Knoll Apt. 455\nMaryfort, MS 11961',
},
    'key77563': 'value12177',
    'key66405': 'value55122',
    'key37095': 'value86637',
    'key61330': 'value72380',
    'key70504': 'value2485',
},
    {
    'id': 17527482444681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Daniel Hopkins',
    'address': '7594 Williams Loop\nMartinezville, VT 30072',
    'text': 'Mother only collection leg. Become although beat help which hit study as. Mother end else good.',
    'email': 'jacoblawson@example.net',
    'phone_number': '001-886-557-3560x80835',
    'json': {
    'name': 'Anthony Meyer',
    'address': '195 Michael Shoal Apt. 013\nBishopton, AS 00569',
},
    'key47090': 'value3695',
    'key95207': 'value46775',
    'key17243': 'value33630',
},
    {
    'id': 17527482444693,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Karen Church',
    'address': '9725 Michael Loop Suite 750\nBurnettmouth, MO 79799',
    'text': 'Doctor become knowledge executive. West either positive list majority beautiful talk western. Class machine effect here remain. Full quickly you.',
    'email': 'terrellamanda@example.com',
    'phone_number': '249.406.4584x91783',
    'json': {
    'name': 'James Owens',
    'address': '4161 Martin Ramp Suite 875\nMatthewsborough, LA 05540',
},
    'key15770': 'value71922',
    'key9653': 'value89021',
    'key52494': 'value18968',
    'key38358': 'value61388',
    'key38606': 'value2518',
    'key41926': 'value76945',
    'key76369': 'value61734',
    'key36819': 'value53708',
},
    {
    'id': 17527482444707,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Julie Alexander',
    'address': '3184 Mills Flat Apt. 295\nLongview, NM 22803',
    'text': 'Past side note sometimes board.\nStand school form. Speech land nature.\nArtist management family detail doctor edge employee. Reveal step actually build. Phone important single that.',
    'email': 'petersmichael@example.com',
    'phone_number': '001-632-792-5063x799',
    'json': {
    'name': 'Ryan Ford',
    'address': '58204 Susan Light Apt. 450\nOwenston, IL 85454',
},
    'key14362': 'value31566',
    'key80913': 'value10835',
    'key83801': 'value59965',
    'key73649': 'value88205',
    'key76485': 'value22479',
    'key748': 'value63960',
},
    {
    'id': 17527482444721,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Kenneth Shaw',
    'address': '962 Todd Circle\nDonaldtown, KS 60632',
    'text': 'Sign real look tend current during. Upon agency financial manage practice. Finally future record feel represent community.',
    'email': 'mitchellbrittany@example.com',
    'phone_number': '221-318-7346x931',
    'json': {
    'name': 'Sonya Duncan',
    'address': '1555 Jennifer Skyway\nSouth Amyview, VI 30725',
},
    'key20417': 'value72764',
    'key96964': 'value48710',
    'key366': 'value82637',
    'key93404': 'value28024',
    'key98830': 'value45391',
    'key50387': 'value32060',
    'key79505': 'value95451',
    'key62225': 'value26430',
    'key71718': 'value47101',
    'key2822': 'value50057',
},
    {
    'id': 17527482444733,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Carolyn Barton',
    'address': '06117 Christina Neck\nJessicashire, ND 22360',
    'text': 'Accept reveal find let turn. Data able degree fine amount beyond financial. One cultural about way many different house.',
    'email': 'kara55@example.net',
    'phone_number': '585-257-7810x027',
    'json': {
    'name': 'Whitney Collins',
    'address': '4623 Moore Viaduct Suite 391\nPort Timothyfort, MD 54082',
},
    'key32149': 'value616',
    'key50814': 'value14709',
    'key22932': 'value4024',
    'key41088': 'value26001',
    'key43446': 'value6152',
    'key92411': 'value79440',
    'key95214': 'value50321',
    'key84339': 'value50537',
    'key30756': 'value16123',
},
    {
    'id': 17527482444745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'William Todd',
    'address': '8124 Katherine Ports Apt. 739\nSouth Virginiaborough, MI 79602',
    'text': 'We she sometimes per kid side contain. Think star staff according number how.',
    'email': 'rachael21@example.com',
    'phone_number': '943-280-7168',
    'json': {
    'name': 'Jenna Griffith',
    'address': '215 Lisa Extension Apt. 056\nJacobsonport, GA 75079',
},
    'key21448': 'value79001',
    'key6085': 'value37871',
    'key27336': 'value95816',
    'key61900': 'value16142',
    'key90623': 'value56105',
    'key46528': 'value63723',
    'key9020': 'value69343',
    'key80948': 'value9578',
},
    {
    'id': 17527482444757,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Michael Coleman',
    'address': '8793 Jones Meadow Suite 497\nFelicialand, MH 72071',
    'text': 'Decade so center black shoulder. Could along avoid baby miss impact between court.\nMiss age remember. Baby represent specific she almost center military. Street federal teach range number look.',
    'email': 'oking@example.com',
    'phone_number': '714.341.9195',
    'json': {
    'name': 'Alan Kelley',
    'address': '40080 Kimberly Rest Suite 763\nHeatherton, KY 63460',
},
    'key27094': 'value77263',
    'key4091': 'value69385',
    'key4919': 'value49771',
    'key47867': 'value85590',
},
    {
    'id': 17527482444770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Denise Reyes',
    'address': '8881 Buchanan Orchard\nNorth Steven, IN 28600',
    'text': 'Alone whose cup gun girl soon. Right party financial write my.\nTo including true central light. Goal hotel try start by southern.',
    'email': 'nsimpson@example.org',
    'phone_number': '+1-662-599-3694x25213',
    'json': {
    'name': 'Laura Contreras',
    'address': '88783 Kevin Plains\nWest Scottmouth, DC 81250',
},
    'key39810': 'value68411',
    'key61344': 'value18956',
    'key92032': 'value3797',
    'key55905': 'value56172',
    'key35899': 'value11701',
    'key12996': 'value7660',
    'key26815': 'value96457',
    'key95032': 'value66569',
},
    {
    'id': 17527482444783,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Kari Henry',
    'address': '9922 Brian Circle\nSouth Mark, SD 65583',
    'text': 'Understand special until for. Possible all treatment.\nBag that support there. Provide weight you member.\nPrevent similar fall manage. Course with whole goal policy.',
    'email': 'meganspencer@example.net',
    'phone_number': '001-312-907-4024x5562',
    'json': {
    'name': 'Noah King',
    'address': '9881 Bennett Camp\nAmandachester, TX 15409',
},
    'key14822': 'value63519',
    'key99848': 'value44485',
    'key96541': 'value27285',
    'key49956': 'value80593',
    'key15255': 'value78936',
    'key3815': 'value89701',
    'key62126': 'value29528',
    'key12183': 'value70429',
},
    {
    'id': 17527482444796,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Brenda Simmons',
    'address': '91363 Waters Port\nBaileymouth, NH 43495',
    'text': 'Thought eat like instead. General hotel assume. Green fish read recent however television.\nResearch attention film audience bad million condition customer. Just Congress whether hundred into.',
    'email': 'bartlettjames@example.com',
    'phone_number': '+1-440-889-4405x19720',
    'json': {
    'name': 'Brian Heath',
    'address': '659 Daniel Points\nWest Ashley, AS 55408',
},
    'key75247': 'value99047',
    'key98830': 'value65302',
},
    {
    'id': 17527482444812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Scott White',
    'address': '90118 Lopez Mount\nEast Sandrahaven, AR 40182',
    'text': 'Wonder peace trade with everything strategy sport. Relate son focus.\nThus ago involve baby current. Help station those sure seek power.',
    'email': 'bradyluis@example.org',
    'phone_number': '(322)955-1313',
    'json': {
    'name': 'Rebecca Jackson',
    'address': '0370 Blackwell Freeway Apt. 259\nCurtisport, KY 11569',
},
    'key502': 'value51540',
    'key52027': 'value15592',
},
    {
    'id': 17527482444825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Joan Burton',
    'address': '016 Wise Vista\nNorth Zacharyport, WV 83187',
    'text': 'Attack hot increase main without painting. Knowledge action commercial work.\nView affect know probably system camera.',
    'email': 'jason18@example.com',
    'phone_number': '979-265-0256x630',
    'json': {
    'name': 'Mathew Anderson',
    'address': 'PSC 1134, Box 7267\nAPO AA 46025',
},
    'key1742': 'value78331',
    'key65810': 'value55485',
    'key10301': 'value5011',
    'key3797': 'value15058',
    'key25780': 'value97643',
    'key25117': 'value12488',
},
    {
    'id': 17527482444834,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Alexandra Collins',
    'address': '747 Laura Branch Suite 598\nSouth Taylorside, MS 21367',
    'text': 'Boy kitchen soon yourself world strategy use. Class TV former case research mouth. Civil month fear.\nOff material agency. Pm lot read. Traditional group bill sit.',
    'email': 'lewisadrian@example.net',
    'phone_number': '(306)798-2464x50566',
    'json': {
    'name': 'Jennifer Howard',
    'address': '9545 Jose Harbors Apt. 588\nPort Kenneth, ME 24676',
},
    'key62117': 'value20765',
    'key29139': 'value89736',
    'key91609': 'value29656',
    'key8356': 'value98500',
    'key55698': 'value47265',
},
    {
    'id': 17527482444846,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Danielle Dominguez',
    'address': '131 Douglas Forge\nSouth Colleenstad, RI 11447',
    'text': 'Democrat which water move yet information director. Blue by base society test share. Long smile performance fine into beautiful.\nChurch cost world wide fish million. One third whatever have arm.',
    'email': 'johnnywilcox@example.net',
    'phone_number': '524-307-5972x79112',
    'json': {
    'name': 'Juan Green',
    'address': 'USNS Evans\nFPO AP 02510',
},
    'key4824': 'value65754',
    'key73040': 'value16134',
    'key55147': 'value39389',
    'key48537': 'value62357',
    'key97599': 'value74544',
    'key15528': 'value64399',
    'key93559': 'value31519',
    'key93298': 'value46772',
    'key32262': 'value37656',
    'key71976': 'value6082',
},
    {
    'id': 17527482444858,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Kevin Roman',
    'address': '625 Kirby Parkways\nJamesberg, MN 84885',
    'text': 'Letter investment store budget together base. Civil trade edge about health image.',
    'email': 'fischerkenneth@example.net',
    'phone_number': '+1-729-913-0176x2324',
    'json': {
    'name': 'Stacy Barnes',
    'address': '765 Evan Flat\nRodriguezbury, NY 89347',
},
    'key9128': 'value38370',
    'key29908': 'value25344',
    'key16112': 'value36734',
    'key2132': 'value88419',
    'key70092': 'value97739',
    'key44867': 'value94477',
    'key31046': 'value67874',
    'key93504': 'value98696',
    'key95186': 'value16494',
},
    {
    'id': 17527482444870,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Travis Vasquez',
    'address': '58978 Todd Curve\nBateshaven, MS 63646',
    'text': 'Manager management enough wife responsibility. Partner size cultural foot type result member still. Responsibility think morning rate at. Environment financial name address size.',
    'email': 'mccannandrew@example.com',
    'phone_number': '2512992047',
    'json': {
    'name': 'Diana Henry',
    'address': '7496 Chase Crossroad Apt. 574\nLake Angela, MI 91888',
},
    'key33988': 'value15600',
    'key73290': 'value17902',
    'key85491': 'value72942',
    'key25339': 'value11271',
    'key36744': 'value86799',
    'key79359': 'value76124',
    'key7167': 'value99352',
},
    {
    'id': 17527482444883,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Warren Rogers',
    'address': '5917 Stone Flats Suite 780\nEast Kylieville, ME 24951',
    'text': 'Real view recently happen culture last serve. Suddenly cover success account. Step continue table citizen.\nSomebody design within sense second some. School father politics let image crime meeting.',
    'email': 'perry63@example.com',
    'phone_number': '823.375.6766',
    'json': {
    'name': 'Heather Butler',
    'address': '0838 Danielle Center\nWest Arthurburgh, MT 05340',
},
    'key58521': 'value360',
    'key18846': 'value11697',
},
    {
    'id': 17527482444894,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Ryan Johnson',
    'address': '060 Middleton View\nRiveraton, GU 68840',
    'text': 'Everyone contain lay this act exactly. Government end either she.\nResponse strong suddenly memory heavy where action. Various sing why account development culture. Happen type speak you next open on.',
    'email': 'astewart@example.com',
    'phone_number': '001-761-782-6988x336',
    'json': {
    'name': 'Lori Monroe',
    'address': '9333 Jessica Canyon\nReneeberg, IA 90355',
},
    'key81593': 'value44079',
    'key25948': 'value56669',
    'key86863': 'value28579',
    'key96031': 'value7885',
    'key62043': 'value76495',
    'key94674': 'value1425',
    'key40355': 'value77194',
    'key58612': 'value84950',
},
    {
    'id': 17527482444905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Meagan Watkins',
    'address': 'Unit 5954 Box 4587\nDPO AP 84508',
    'text': 'On lose over along put street of. Safe ten often sport loss the level. Despite management material no without.',
    'email': 'jennifer94@example.net',
    'phone_number': '776-366-5563',
    'json': {
    'name': 'Matthew Juarez',
    'address': '9019 Ian Mountain\nWest Stephanieside, AS 66244',
},
    'key59889': 'value90741',
    'key48485': 'value32829',
    'key2212': 'value12567',
    'key19203': 'value42271',
    'key28683': 'value33626',
    'key65660': 'value12522',
    'key36976': 'value49018',
    'key31101': 'value78678',
    'key53595': 'value45880',
},
    {
    'id': 17527482444914,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Alyssa Franklin',
    'address': '221 Gabriel Harbor Suite 026\nPort Kathryn, DC 76293',
    'text': 'Hit save case after. Sign cup party stop. Life owner beat behind situation sister book house.\nWait dream expert hand sea position teacher rich. Crime dream public out.',
    'email': 'jonesryan@example.net',
    'phone_number': '632.451.6301x00248',
    'json': {
    'name': 'Frederick Kramer',
    'address': '08953 Michael Keys\nKennethbury, AS 76579',
},
    'key49038': 'value45317',
    'key20400': 'value53260',
    'key2807': 'value18001',
},
    {
    'id': 17527482444925,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Mrs. Lisa Harris MD',
    'address': '61097 Davenport Parks\nLake Victorshire, MA 75118',
    'text': 'Sure east mean. Provide reality hot. Health number store treatment no it animal.\nState behind attention human author whom push. Civil region sport bill mouth east action everyone. Box claim because.',
    'email': 'hernandezgina@example.org',
    'phone_number': '001-609-832-3281x807',
    'json': {
    'name': 'Mr. Justin Cannon',
    'address': '497 Ruiz Flat Suite 135\nNorth Masonfort, TN 81431',
},
    'key61243': 'value64396',
},
    {
    'id': 17527482444937,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Sonya Hernandez',
    'address': '80033 Jose Summit\nNew Samanthaview, MS 77955',
    'text': 'Happy because development with job. Have choice nature within. Activity company drug compare matter learn onto.',
    'email': 'khopkins@example.org',
    'phone_number': '+1-471-623-7216x7966',
    'json': {
    'name': 'Jesse Mitchell',
    'address': '2673 Lopez Fort\nEast Jessicastad, WY 01796',
},
    'key15970': 'value16632',
    'key23445': 'value57056',
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_38_236022EgyVgppL',
    'data': self.mutator.generate_float_array(dimension=128, normalized=True),
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
    'json',
],
    'filter': 'name > \'Le\'',
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_38_236022EgyVgppL',
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_38_236022EgyVgppL',
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
    'RequestId': '14b59c64-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_30_38_236022EgyVgppL',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_varchar_filter[name > "placeholder"]_1752748247.json')
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
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithComplexVarcharFilterNamePlaceholder1752748247Json()
    test.run_tests()
