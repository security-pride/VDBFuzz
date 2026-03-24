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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_simple_payload[COSINE]_1752748015_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[COSINE]_1752748015.json"
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithSimplePayloadCosine1752748015Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[COSINE]_1752748015.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[COSINE]_1752748015.json"
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
    'RequestId': '8bb5d992-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_48_389446vLXzELEH',
    'dimension': 128,
    'metricType': 'COSINE',
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
    'RequestId': '8bb5d992-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_48_389446vLXzELEH',
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
    'RequestId': '8bb5d992-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_48_389446vLXzELEH',
    'data': [
    {
    'id': 17527480144272,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jessica Bradford',
    'address': '2316 Bobby Mills\nRiveraberg, DC 58484',
    'text': 'But keep street respond full send feel. Push hold someone you.\nThe world network tax. Mr however language although. Market if wish executive them economic us cause.',
    'email': 'newtoncarrie@example.org',
    'phone_number': '+1-214-964-9279x222',
    'json': {
    'name': 'Andrew Zamora',
    'address': '1346 Hill Haven\nNew Scott, AZ 33356',
},
    'key73864': 'value80550',
    'key55288': 'value81649',
    'key41633': 'value36110',
    'key25339': 'value29170',
    'key98874': 'value24875',
    'key82398': 'value85054',
},
    {
    'id': 17527480144291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Rebecca Robinson',
    'address': '7419 Michael Islands Apt. 214\nCorytown, WI 14598',
    'text': 'Hit through choice heavy vote old young.\nSimply never middle show brother ask stock western. Maintain can affect truth run statement. Majority consider throw hear deep.',
    'email': 'tylerhaynes@example.net',
    'phone_number': '001-804-766-5717x0394',
    'json': {
    'name': 'Cynthia Marshall',
    'address': '35726 Richard Brooks\nPort Gregoryshire, FM 79330',
},
    'key35460': 'value34966',
    'key30171': 'value91389',
},
    {
    'id': 17527480144306,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Tristan Mclaughlin',
    'address': '56010 Boone Shoals\nEast Patricia, IL 22496',
    'text': 'View middle knowledge house. Herself example claim.\nListen though north style. Stand debate be phone. Response soldier conference.',
    'email': 'jessicalawrence@example.net',
    'phone_number': '(371)343-7387',
    'json': {
    'name': 'Kirsten Bean',
    'address': '00344 Heather Flats Apt. 683\nRoachhaven, WI 22341',
},
    'key36839': 'value14151',
    'key76708': 'value98268',
    'key39489': 'value80532',
    'key6276': 'value21977',
    'key95204': 'value74621',
    'key52004': 'value67385',
    'key23654': 'value94245',
},
    {
    'id': 17527480144321,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Erika Dillon',
    'address': '953 Owens Point\nKingshire, SC 70816',
    'text': 'Blood watch task commercial tend pressure yeah student. Put while during natural.\nUs set skill phone exist after. Say evening gas meeting participant. Manage seek old.',
    'email': 'abutler@example.org',
    'phone_number': '(550)426-5908x9359',
    'json': {
    'name': 'Rita Gonzales',
    'address': '55043 Zimmerman Rapids\nNew Benjamin, IN 60278',
},
    'key84485': 'value31684',
    'key96586': 'value44355',
    'key43796': 'value6472',
    'key22202': 'value60002',
    'key34898': 'value64135',
    'key59659': 'value41261',
    'key61628': 'value72102',
    'key70397': 'value65885',
    'key49343': 'value1052',
},
    {
    'id': 17527480144335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Lisa Villarreal',
    'address': '9380 Nathaniel Roads Apt. 664\nBurnsfurt, SC 08809',
    'text': 'Half speech security treatment knowledge send. Painting deep election couple course your beyond.',
    'email': 'qpowell@example.com',
    'phone_number': '239-210-8904x410',
    'json': {
    'name': 'Pamela Moore',
    'address': '1048 Lopez Meadows Apt. 335\nWest Kayla, AL 24970',
},
    'key84155': 'value17413',
    'key70324': 'value97641',
    'key49071': 'value48553',
    'key66524': 'value14734',
    'key6667': 'value10721',
    'key51592': 'value71317',
},
    {
    'id': 17527480144348,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Joseph Lawrence',
    'address': '86677 Troy Shores Apt. 028\nEast Brendaburgh, DC 31672',
    'text': 'Hour color line. Main member include than.\nMight woman treat. Room generation article resource both. Section work make wonder. Do leg enter need little gun despite without.',
    'email': 'sarabrown@example.com',
    'phone_number': '(298)488-1895x54414',
    'json': {
    'name': 'Katie Cole',
    'address': '24738 Conrad Forest Suite 917\nSouth David, MH 30203',
},
    'key69970': 'value92575',
    'key58580': 'value60404',
    'key45162': 'value78302',
    'key72916': 'value95909',
    'key39830': 'value13567',
    'key91025': 'value72251',
    'key65444': 'value86293',
},
    {
    'id': 17527480144362,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'James Miller',
    'address': '42893 Sheila Hollow\nNew Emilyborough, WI 78413',
    'text': 'Move we yes action fly matter. Conference board bank pay technology prove.\nCare situation car account ever shoulder. A her until argue dark record.',
    'email': 'jamesdaugherty@example.net',
    'phone_number': '001-280-349-6120x374',
    'json': {
    'name': 'Robert White',
    'address': '745 Meyers Valley\nNew Taylor, GA 75173',
},
    'key77739': 'value69302',
    'key5683': 'value33757',
    'key35142': 'value46389',
    'key61560': 'value28050',
    'key73552': 'value89313',
},
    {
    'id': 17527480144374,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Samuel Anderson',
    'address': '211 Geoffrey Estates\nSouth Steven, ME 66135',
    'text': 'Most live type second travel difference. Film debate military no.\nThroughout activity catch against. Early Republican wall own. Character image possible institution stay.',
    'email': 'tanya27@example.net',
    'phone_number': '504.243.3488x7163',
    'json': {
    'name': 'Destiny Jefferson',
    'address': '9875 Carson Cliff\nMillerberg, WI 80996',
},
    'key33548': 'value83237',
    'key11355': 'value5183',
    'key33775': 'value50514',
    'key69681': 'value60235',
},
    {
    'id': 17527480144385,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Charles Smith',
    'address': '493 Andrew Rapids Suite 792\nNew Scotthaven, AZ 19652',
    'text': 'Only kid maybe record half. Rise because same sister fear your bill. Year move themselves top live edge food.\nSocial natural mean room. Fill go leg agreement.',
    'email': 'ashleyfrye@example.com',
    'phone_number': '001-996-406-5136x879',
    'json': {
    'name': 'Shannon Alvarez',
    'address': '298 Holder Hills Suite 780\nLopezburgh, VA 38955',
},
    'key89335': 'value89103',
    'key12525': 'value48786',
    'key62406': 'value12486',
    'key72007': 'value2608',
    'key64256': 'value73719',
    'key9457': 'value84169',
    'key55453': 'value663',
    'key52408': 'value7093',
    'key84373': 'value56020',
},
    {
    'id': 17527480144397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Amber Donovan',
    'address': '3053 Michelle Stream Apt. 420\nNew Michaeltown, OK 78578',
    'text': 'This job character standard situation land meet. Either agreement top. Visit program two media place agree police truth. Town perhaps weight able three those.',
    'email': 'zimmermanpaul@example.com',
    'phone_number': '+1-613-372-5606',
    'json': {
    'name': 'Seth Rodriguez',
    'address': '5440 David Field Suite 236\nSouth Lisaburgh, NM 91648',
},
    'key62203': 'value15172',
    'key26776': 'value67008',
    'key61171': 'value48434',
    'key69542': 'value21326',
    'key19706': 'value4872',
    'key18556': 'value57035',
    'key18218': 'value83209',
    'key89499': 'value61869',
    'key83209': 'value81769',
},
    {
    'id': 17527480144409,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Debbie Moore',
    'address': '956 Lauren Flats Apt. 975\nKatherineburgh, VT 15382',
    'text': 'Participant after itself less. House save after price relationship follow seem answer. Listen deal save gun six happy.',
    'email': 'fergusontina@example.org',
    'phone_number': '001-862-449-9628x337',
    'json': {
    'name': 'Angela King',
    'address': 'Unit 9140 Box 7417\nDPO AP 43156',
},
    'key74100': 'value40772',
    'key90013': 'value8199',
},
    {
    'id': 17527480144418,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Amy White',
    'address': '0102 David Gateway Apt. 464\nMooreport, WI 64210',
    'text': 'Letter their medical focus. Country new allow including charge. Successful whatever of early paper administration vote.',
    'email': 'laura27@example.net',
    'phone_number': '999.577.3641x3987',
    'json': {
    'name': 'Mindy Rodriguez',
    'address': '59820 Teresa Tunnel\nLake Xavier, MP 96338',
},
    'key57986': 'value99811',
    'key68302': 'value96919',
    'key11095': 'value86280',
    'key86646': 'value98182',
    'key91644': 'value79830',
    'key48816': 'value65122',
    'key70813': 'value55319',
    'key19282': 'value43493',
    'key62148': 'value11978',
    'key78116': 'value44766',
},
    {
    'id': 17527480144428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Jared Sweeney',
    'address': '49085 Paul Points\nRobertsberg, AK 68438',
    'text': 'Present spend adult range man firm environment. Those write seven from. Interest least color set other expect approach.',
    'email': 'ronald88@example.com',
    'phone_number': '(281)575-0567',
    'json': {
    'name': 'Norman Sellers',
    'address': '619 Alexander Track Apt. 684\nIanview, MD 52997',
},
    'key42439': 'value91342',
    'key49767': 'value49673',
    'key63824': 'value77329',
    'key57240': 'value8134',
    'key64848': 'value24090',
    'key3751': 'value80178',
    'key12579': 'value6020',
    'key23910': 'value9428',
    'key27826': 'value647',
    'key90128': 'value79189',
},
    {
    'id': 17527480144439,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Andrew Green',
    'address': '7055 Buckley Courts\nDebrabury, CT 44096',
    'text': 'Explain phone bring section.\nAway opportunity provide week ever tree instead. They design face our from simple.',
    'email': 'adrian79@example.com',
    'phone_number': '4242385150',
    'json': {
    'name': 'Timothy Ramirez',
    'address': '6461 Vargas Villages Apt. 546\nStevenstad, RI 15416',
},
    'key59220': 'value38994',
    'key98201': 'value67417',
    'key10290': 'value95501',
    'key46955': 'value89102',
    'key52159': 'value70018',
},
    {
    'id': 17527480144449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Troy Martinez',
    'address': '2417 Tyler Orchard Apt. 899\nBrandonshire, CA 70390',
    'text': 'Risk medical deep bring him. About run five cut performance power job. Rather action significant machine enter few. Where until finish beat ready speak author.',
    'email': 'oscarmartinez@example.net',
    'phone_number': '656-624-8737x1585',
    'json': {
    'name': 'Deanna Campbell',
    'address': '511 Patricia Trail\nMunozville, AZ 18147',
},
    'key87259': 'value2461',
},
    {
    'id': 17527480144460,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Nicholas Chandler',
    'address': '324 Cook Tunnel\nNew Danielside, OH 93631',
    'text': 'Budget piece kind message identify and. Top health tonight.\nSave player finish Republican upon herself although. Help somebody people crime at once feeling.',
    'email': 'toni70@example.org',
    'phone_number': '810.257.4662x824',
    'json': {
    'name': 'Laura Kennedy',
    'address': '27010 Brown View Apt. 141\nHamptonbury, OH 61155',
},
    'key72777': 'value34480',
    'key58508': 'value58449',
    'key93031': 'value53975',
    'key53509': 'value44381',
    'key30966': 'value55291',
    'key41945': 'value87652',
    'key66255': 'value81762',
    'key63472': 'value92180',
    'key35283': 'value51674',
    'key82590': 'value93077',
},
    {
    'id': 17527480144472,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Jennifer Werner',
    'address': '1471 Louis Turnpike\nNew Brooke, MN 57205',
    'text': 'After listen trial series agreement activity avoid. Catch certain fire reality. Quite subject capital evidence shake cup.',
    'email': 'crice@example.org',
    'phone_number': '(945)548-9850',
    'json': {
    'name': 'Kimberly Conway',
    'address': '959 Kenneth Way Suite 053\nNew Heather, IN 64748',
},
    'key3450': 'value53751',
    'key69721': 'value10721',
    'key45156': 'value74453',
    'key2816': 'value20983',
    'key2368': 'value20696',
    'key59051': 'value48108',
},
    {
    'id': 17527480144482,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Jamie Williams',
    'address': '28145 Fowler Key\nNorth Oliviafurt, ME 23213',
    'text': 'Difference adult arm day summer attention. Quickly how network occur system camera. Choice find month speech official.',
    'email': 'robert39@example.com',
    'phone_number': '537-410-4212',
    'json': {
    'name': 'Angela Jenkins',
    'address': '33536 Mendoza Fall\nJosebury, AR 21212',
},
    'key19432': 'value80890',
},
    {
    'id': 17527480144492,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Deborah Bradley',
    'address': 'Unit 1123 Box 0466\nDPO AP 52702',
    'text': 'Democrat south magazine who ground.\nCup data list beyond. Trade term degree two minute attack red. Rest offer same quickly away.',
    'email': 'mayarthur@example.org',
    'phone_number': '(209)466-8945',
    'json': {
    'name': 'David Fowler',
    'address': '151 Tracy Corner Suite 542\nJamesbury, DC 85093',
},
    'key86817': 'value47425',
    'key23794': 'value48563',
    'key53969': 'value96461',
    'key42105': 'value2025',
    'key5013': 'value80166',
    'key33018': 'value20430',
    'key15608': 'value792',
},
    {
    'id': 17527480144502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Rebecca Evans',
    'address': '694 Chambers View\nEvelynbury, OR 26523',
    'text': 'High provide left particularly western. Fish soldier loss time present she throw.\nPer design tough still here employee. Thing create age Mrs class pressure boy. Leg follow five increase relate.',
    'email': 'harperronald@example.com',
    'phone_number': '001-412-454-1842',
    'json': {
    'name': 'Shelby Schmitt',
    'address': '95762 Jonathan Ferry\nJessicabury, MH 35887',
},
    'key97942': 'value5679',
    'key62055': 'value73531',
    'key7367': 'value69786',
    'key69197': 'value15112',
    'key60018': 'value87256',
    'key81761': 'value4830',
    'key95256': 'value49289',
},
    {
    'id': 17527480144513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Andrew Williams',
    'address': '67283 Smith Bypass\nJohnsonstad, WI 62271',
    'text': 'Garden fear statement position each social.\nExecutive the technology drive charge you. Interview son establish bit add society.\nKeep gun none hair.',
    'email': 'lindamiles@example.net',
    'phone_number': '690-349-1655x6440',
    'json': {
    'name': 'Bruce Conner',
    'address': '4783 Patterson Landing Apt. 144\nJosephtown, MA 59508',
},
    'key86690': 'value50180',
    'key75304': 'value14463',
    'key3743': 'value45521',
    'key28458': 'value91886',
    'key3938': 'value66847',
    'key18331': 'value50361',
    'key76533': 'value26800',
},
    {
    'id': 17527480144525,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Mr. Daniel Cooper',
    'address': '771 Jennifer Plain Apt. 776\nNorth Elizabethside, MN 67987',
    'text': 'My it build feel score attorney how. Effort somebody report three produce away in yet. Read machine ever citizen. Responsibility section catch maybe any modern guy land.',
    'email': 'gregoryjohnson@example.net',
    'phone_number': '212-484-3975x7170',
    'json': {
    'name': 'Lisa Burke',
    'address': '047 Stephen Prairie\nPort Stephanieshire, MA 55467',
},
    'key65326': 'value24199',
    'key38853': 'value8565',
    'key51077': 'value82279',
},
    {
    'id': 17527480144535,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Megan Jackson',
    'address': '2742 Robinson Key Apt. 390\nSouth Jason, PR 94384',
    'text': 'Model listen civil record loss wonder. Walk trip light.\nBag about budget end from. Thing expect box child artist develop feeling network.',
    'email': 'barrerajohn@example.com',
    'phone_number': '249.285.7485x700',
    'json': {
    'name': 'Erica Miller',
    'address': 'PSC 3907, Box 2028\nAPO AA 90681',
},
    'key66343': 'value23906',
    'key83871': 'value35000',
    'key86014': 'value27973',
    'key56283': 'value8985',
},
    {
    'id': 17527480144545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Lauren Howard',
    'address': 'Unit 8126 Box 5073\nDPO AE 73056',
    'text': 'Run figure situation number. Indeed professional charge certain high physical poor. Agency until learn fine policy.',
    'email': 'fstewart@example.com',
    'phone_number': '886-978-5969x95304',
    'json': {
    'name': 'Ashley King',
    'address': '7067 Heather Islands\nMartineztown, LA 29407',
},
    'key70043': 'value94779',
    'key71449': 'value41450',
    'key12903': 'value82353',
    'key14066': 'value11529',
    'key71332': 'value57374',
    'key4042': 'value59597',
    'key286': 'value60729',
    'key76101': 'value38058',
    'key67266': 'value15205',
    'key16520': 'value55060',
},
    {
    'id': 17527480144554,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Steven Hale',
    'address': '2983 Jones Freeway Suite 774\nGarnerside, AZ 01658',
    'text': 'Space ground image edge. Offer once wear. Over receive near discuss pressure trip line cover.',
    'email': 'samantha97@example.net',
    'phone_number': '5805431305',
    'json': {
    'name': 'John Hart',
    'address': '4617 Michelle Way Suite 294\nEast Jessicahaven, UT 48523',
},
    'key59355': 'value60237',
},
    {
    'id': 17527480144565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Raymond Rivera',
    'address': '3214 Williams Knolls Suite 889\nEast Mary, VI 71646',
    'text': 'Happy reflect partner third.\nEnjoy country life detail adult list. Foreign present power according wonder finally care. Hard blue language same in.',
    'email': 'joshuaray@example.org',
    'phone_number': '001-899-697-9717',
    'json': {
    'name': 'Douglas Mitchell',
    'address': '3502 Pruitt Crossroad Suite 509\nEast Pamelastad, FL 83954',
},
    'key89754': 'value82699',
    'key64274': 'value45496',
    'key47130': 'value89937',
    'key8327': 'value48848',
},
    {
    'id': 17527480144577,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Brittany Scott',
    'address': '9867 Guzman Lodge\nSouth Danielport, MT 30123',
    'text': 'Stop wide first decision glass. Everyone character section but. Where keep girl defense.\nWill serious chance save. Oil picture including very. Past human nation business.',
    'email': 'pconner@example.com',
    'phone_number': '+1-414-938-1158x428',
    'json': {
    'name': 'Logan Martin',
    'address': '33783 Kristine Gateway Apt. 631\nSouth Christina, MS 40919',
},
    'key43057': 'value83922',
    'key92735': 'value57395',
},
    {
    'id': 17527480144587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Tammy White',
    'address': '9666 Lisa Trace Suite 261\nEast Deborah, UT 14713',
    'text': 'Concern sense some investment. Art as major various speak yourself.\nAuthor career make trade forward. Difficult take great establish grow simply.',
    'email': 'salinasrichard@example.com',
    'phone_number': '364.980.8657x01508',
    'json': {
    'name': 'Ashley Miller',
    'address': '05096 Krystal Ranch\nWest Charles, NV 78120',
},
    'key52697': 'value26720',
    'key34701': 'value9430',
    'key31298': 'value12441',
    'key95668': 'value12703',
    'key33303': 'value67388',
    'key21608': 'value81554',
    'key70212': 'value25272',
},
    {
    'id': 17527480144599,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Micheal Jennings',
    'address': '8281 Chavez Plains\nJonesview, FM 74195',
    'text': 'Three generation off line hundred.\nToo national generation plan large just. Population offer total.',
    'email': 'bonillatheresa@example.net',
    'phone_number': '595-871-3312x739',
    'json': {
    'name': 'Teresa Mullen',
    'address': '194 Phillips Rue\nPort Samuel, CO 14897',
},
    'key79225': 'value74938',
},
    {
    'id': 17527480144610,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Dylan Ford',
    'address': 'Unit 9734 Box 7416\nDPO AE 01771',
    'text': 'Gas miss low west off among human. Machine mouth with. Social sure white main.\nNor simply political front in. Price air friend pay religious natural us option.',
    'email': 'fswanson@example.org',
    'phone_number': '+1-237-313-2097x2795',
    'json': {
    'name': 'Rachel Meyers',
    'address': '5282 Lam Station\nNew Sandratown, LA 56542',
},
    'key85921': 'value64982',
    'key71295': 'value449',
    'key90503': 'value78079',
    'key70907': 'value1502',
},
    {
    'id': 17527480144619,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Tracy Hudson',
    'address': '274 Moses Lock Suite 944\nLake Micheleburgh, MH 21787',
    'text': 'Believe partner source together ever color. Especially condition almost letter behind season community.',
    'email': 'enichols@example.org',
    'phone_number': '(432)289-1697x52371',
    'json': {
    'name': 'Kathryn Cowan',
    'address': '518 Thomas Mountains\nBriantown, MA 05248',
},
    'key6705': 'value4956',
    'key93322': 'value62518',
    'key54427': 'value83979',
    'key76137': 'value90943',
    'key26337': 'value44383',
    'key12150': 'value26462',
    'key74325': 'value10374',
    'key25137': 'value15728',
    'key1388': 'value61173',
},
    {
    'id': 17527480144630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Janice Gonzalez',
    'address': '10710 Andrew Path\nAdamport, SC 46238',
    'text': 'Total poor agency public mind lawyer. Ability fire purpose now beyond degree.\nChallenge give middle hand even treatment sound. Become else mean. Time away agreement third old miss.',
    'email': 'chrishanson@example.org',
    'phone_number': '975.765.1403',
    'json': {
    'name': 'Catherine Sellers',
    'address': '807 Thomas Shores\nPort Joseph, ME 47466',
},
    'key29391': 'value2564',
    'key27678': 'value67149',
    'key34918': 'value41951',
    'key15367': 'value4677',
    'key74826': 'value24229',
    'key92253': 'value76697',
    'key5978': 'value83323',
},
    {
    'id': 17527480144641,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Matthew Mack',
    'address': '3578 Cole Mountain\nNorth Tammyhaven, GA 56925',
    'text': 'Training yard begin could. Control goal theory woman star about. But without our city worker.\nClass eat fight plant relate. Prepare than dinner quite money.',
    'email': 'zjennings@example.org',
    'phone_number': '001-814-719-1310x5767',
    'json': {
    'name': 'Isaac Brown',
    'address': '1377 William Gateway Suite 674\nNew Sonya, DC 15364',
},
    'key84871': 'value38025',
    'key51235': 'value59278',
    'key2011': 'value91068',
    'key81316': 'value11953',
    'key69078': 'value38639',
    'key28745': 'value72786',
    'key41012': 'value55258',
    'key77135': 'value54490',
},
    {
    'id': 17527480144652,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kristina Munoz',
    'address': '27532 Lori Village\nPort Tracietown, MD 90928',
    'text': 'Walk today himself will voice seem building. The show four nice gas teacher turn indeed.',
    'email': 'munozsusan@example.net',
    'phone_number': '001-716-735-4191x8749',
    'json': {
    'name': 'Michael Barron',
    'address': '38086 Brandon Rapids Apt. 589\nJenkinshaven, KY 71027',
},
    'key11304': 'value83265',
    'key56885': 'value66806',
    'key60806': 'value70131',
    'key17989': 'value31516',
    'key62922': 'value40294',
},
    {
    'id': 17527480144664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'James Blake',
    'address': '36948 Luis Radial Apt. 225\nRobinsonberg, NC 11566',
    'text': 'Most cut door under kind up. Run four unit no others short door.',
    'email': 'james88@example.net',
    'phone_number': '(596)949-8431x867',
    'json': {
    'name': 'James Jennings',
    'address': '6860 Schwartz Coves\nSouth Jessicatown, NE 74441',
},
    'key45364': 'value33769',
    'key63654': 'value51764',
    'key19122': 'value86433',
    'key88360': 'value31947',
    'key30780': 'value51957',
    'key85066': 'value63035',
    'key79618': 'value8963',
    'key47021': 'value45798',
},
    {
    'id': 17527480144675,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Laurie Barnett',
    'address': '66168 Joshua Ports\nWest Shawn, WI 26632',
    'text': 'Rate total scientist yet environmental.',
    'email': 'mscott@example.org',
    'phone_number': '+1-311-472-1357x6732',
    'json': {
    'name': 'Brandi Evans',
    'address': '79368 Cooley Parkways\nWest Tammy, MN 33240',
},
    'key48176': 'value91944',
    'key61710': 'value1197',
    'key32743': 'value27490',
    'key10024': 'value39791',
    'key68341': 'value79117',
    'key70837': 'value54930',
    'key90898': 'value56678',
},
    {
    'id': 17527480144685,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'John Bray',
    'address': '00824 Julie Flat\nPort Josemouth, HI 15312',
    'text': 'Strong receive middle few born bag painting. Fly shoulder admit where spend. Section across before program. Series subject gas ago write third few language.',
    'email': 'vparks@example.org',
    'phone_number': '(867)758-8211x62811',
    'json': {
    'name': 'Angela Travis',
    'address': '36444 Giles Rue\nCraigfurt, OR 50230',
},
    'key16179': 'value83437',
    'key23700': 'value47031',
},
    {
    'id': 17527480144695,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Joshua Herring',
    'address': '72262 Brian Harbor\nLake Katieland, ME 40871',
    'text': 'Decade everything suggest wind. Several use indeed hour ground author young old.\nExpert skin space very recognize. Yard may activity much his ever sometimes amount.',
    'email': 'avilarobin@example.com',
    'phone_number': '5167478875',
    'json': {
    'name': 'Mark Davis',
    'address': '384 Elaine Ranch\nNorth Robertborough, NM 74166',
},
    'key96718': 'value70312',
},
    {
    'id': 17527480144706,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Gina Austin',
    'address': '738 Amy Mission Suite 112\nNorth Christopher, IN 08333',
    'text': 'Truth oil station early leader. National history avoid. Truth speak ten save follow human.\nYet history nice money. Born modern Mrs try sell open. Director generation really deal full tonight.',
    'email': 'teresa57@example.net',
    'phone_number': '001-972-352-7660',
    'json': {
    'name': 'Benjamin Ortiz',
    'address': '226 Samuel Dale\nJessicaside, GA 75126',
},
    'key72337': 'value38796',
},
    {
    'id': 17527480144715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Meredith Jennings',
    'address': '07590 Gabrielle Shore Suite 250\nPort Hector, IA 51480',
    'text': 'Environmental carry buy onto. Among hospital high listen must stand race add.\nLet price clearly hand. Yard couple how speak dark ago.',
    'email': 'michellemorton@example.org',
    'phone_number': '811-743-6757x0152',
    'json': {
    'name': 'Patricia Fletcher',
    'address': '8279 Curtis Island Suite 362\nNew Scott, MA 52935',
},
    'key44410': 'value23088',
    'key94949': 'value32712',
    'key17354': 'value23674',
    'key40953': 'value78096',
    'key3469': 'value61252',
    'key54429': 'value76829',
    'key85795': 'value54800',
    'key42327': 'value38778',
    'key95660': 'value53635',
    'key76288': 'value51490',
},
    {
    'id': 17527480144726,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Maria Mercado',
    'address': 'USNS Gonzalez\nFPO AE 27551',
    'text': 'Light popular other season. Conference father form particular economic answer production.\nTeach blood mission rise. Simple next generation perhaps perhaps research.',
    'email': 'isaiahbennett@example.com',
    'phone_number': '(832)354-8417',
    'json': {
    'name': 'Glenn Carter',
    'address': '0583 Megan Tunnel Suite 224\nNew Johnhaven, CT 61206',
},
    'key72559': 'value959',
    'key89276': 'value34102',
    'key65002': 'value6538',
    'key61547': 'value6797',
    'key63401': 'value80181',
    'key24132': 'value63598',
},
    {
    'id': 17527480144736,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Sandra Ryan',
    'address': '398 Benson Row Apt. 671\nJeanneview, ND 99861',
    'text': 'Thing mission might lot expert. Across address age person.\nBe already citizen computer. Find something party management pick most.\nHimself yard scene. Hour article source than daughter these.',
    'email': 'amandariddle@example.com',
    'phone_number': '001-657-382-8664x29979',
    'json': {
    'name': 'Daniel Gibbs',
    'address': '4615 Wells Parkway Apt. 200\nNew Kenneth, MT 61872',
},
    'key97250': 'value73862',
    'key23801': 'value49911',
    'key61207': 'value98851',
    'key77850': 'value82555',
    'key16732': 'value35405',
    'key26144': 'value79936',
    'key29270': 'value77111',
},
    {
    'id': 17527480144752,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Timothy Saunders',
    'address': '6411 Aaron Ranch\nDonnahaven, GA 43064',
    'text': 'Worry recent heavy score military perform answer forget. Color know cultural its or drop.\nCar child none full start.\nVote pretty mouth ready. Near use six. Region nor work international city.',
    'email': 'glenn43@example.net',
    'phone_number': '5159104329',
    'json': {
    'name': 'Jennifer Garcia',
    'address': '911 Mcclain Plain Suite 280\nPerrytown, CO 74873',
},
    'key88945': 'value15384',
    'key70710': 'value50575',
    'key762': 'value82061',
    'key2316': 'value80649',
},
    {
    'id': 17527480144764,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Barbara Richardson',
    'address': '631 Carolyn Mountains\nEllenshire, MP 36391',
    'text': 'Song recently writer account. Inside poor during technology lot these.\nEvery try develop image toward follow. Probably career save together exist. Foot put stock wrong close.',
    'email': 'sadams@example.com',
    'phone_number': '(230)488-5946',
    'json': {
    'name': 'Terrance Williams',
    'address': '275 Charles Overpass\nRamosburgh, PR 41612',
},
    'key72344': 'value46912',
    'key60186': 'value9756',
    'key19389': 'value11615',
    'key37498': 'value26226',
    'key53944': 'value22884',
    'key41128': 'value70333',
},
    {
    'id': 17527480144775,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Sean Wright',
    'address': '4864 Cole Plaza Suite 137\nNorth Jean, SC 58749',
    'text': 'Enough establish word guess to challenge. Recently may actually western.\nLook notice test phone plan. Ground analysis hit force similar. Goal service before send too job.',
    'email': 'john50@example.com',
    'phone_number': '001-590-259-7749x4224',
    'json': {
    'name': 'Allison Lewis',
    'address': '17268 Reed Manors\nFloreshaven, IA 21258',
},
    'key92198': 'value42708',
    'key38152': 'value50715',
    'key16708': 'value38707',
    'key96217': 'value74641',
    'key63140': 'value23532',
    'key96947': 'value77623',
    'key86784': 'value45583',
    'key14691': 'value22460',
    'key38331': 'value1019',
},
    {
    'id': 17527480144786,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Nicole Brown',
    'address': '362 Hickman Mountains\nNew Danielleberg, ME 24356',
    'text': 'Main structure concern career green. Reflect record where participant purpose response.\nSociety fish born well forward choose road. Middle note foreign issue always heavy door.',
    'email': 'gregspears@example.net',
    'phone_number': '9568222969',
    'json': {
    'name': 'Alec Davidson',
    'address': '186 Richardson Circles Suite 065\nLake Linda, MO 07877',
},
    'key68664': 'value41124',
    'key96027': 'value36885',
    'key47562': 'value47649',
    'key41885': 'value84873',
    'key15926': 'value75977',
    'key99367': 'value7034',
    'key10047': 'value98265',
    'key61223': 'value15621',
    'key25700': 'value63210',
},
    {
    'id': 17527480144799,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Warren Reed',
    'address': '767 Regina Inlet\nNew Edwardshire, CA 27293',
    'text': 'In current region government total identify. Nature brother little amount. Character stage speech away.\nValue traditional energy suggest scientist. Ask east section soldier walk impact thing.',
    'email': 'aliciachase@example.org',
    'phone_number': '(309)456-7071',
    'json': {
    'name': 'Rachel Mccoy',
    'address': '06807 Cruz Divide Apt. 198\nMicheleview, WA 37693',
},
    'key50950': 'value34719',
    'key21835': 'value94314',
    'key13770': 'value59152',
    'key52241': 'value27801',
    'key5684': 'value25004',
    'key55930': 'value95372',
    'key37380': 'value76713',
    'key82772': 'value7194',
    'key31825': 'value34951',
},
    {
    'id': 17527480144813,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Cole Cain',
    'address': '30054 Kimberly Cliff Suite 514\nLake Austin, AR 35639',
    'text': 'Call see poor. Position until source. Own only almost money film risk. Democrat firm add week special.',
    'email': 'scott71@example.com',
    'phone_number': '558-255-9871x20444',
    'json': {
    'name': 'Carrie Wright',
    'address': '1202 Gregory Freeway\nLorifurt, ID 17337',
},
    'key88580': 'value25125',
    'key98834': 'value24049',
    'key69888': 'value58557',
    'key72845': 'value62437',
},
    {
    'id': 17527480144827,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Mrs. Krystal Schultz',
    'address': '3506 Lawson Inlet\nEast Michelle, IL 10710',
    'text': 'Black month husband minute matter. Once meet word production audience.\nFather us face around training. Capital what say fill measure skill economic detail.',
    'email': 'larrykaufman@example.net',
    'phone_number': '(490)448-6479',
    'json': {
    'name': 'Connie Jackson',
    'address': '8572 Neal Hollow\nWheelerside, NV 89417',
},
    'key83990': 'value27959',
    'key70040': 'value56284',
    'key29285': 'value10955',
    'key6543': 'value45872',
    'key55813': 'value54246',
},
    {
    'id': 17527480144841,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Jeffrey Rodriguez',
    'address': '390 Stanton Turnpike\nHudsonbury, IN 03014',
    'text': 'Yourself indicate school represent perform reason. Throw rather country put affect happy. Possible series history future.',
    'email': 'mary19@example.com',
    'phone_number': '826-594-7890',
    'json': {
    'name': 'Brandon Kim',
    'address': '56290 Daniels Stream\nMaryshire, GA 60092',
},
    'key7711': 'value11087',
},
    {
    'id': 17527480144854,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Christine King',
    'address': '1744 Rebecca Canyon Apt. 162\nNew John, PA 92974',
    'text': 'Responsibility state relate common find. Upon least thank people common. Body off grow wait cup author.\nGame here after front. Machine lead paper store. Such never method only.',
    'email': 'walkershari@example.com',
    'phone_number': '+1-876-820-8240x1101',
    'json': {
    'name': 'Tracy Schultz',
    'address': '329 Williams Stream Apt. 164\nStevenview, ME 19106',
},
    'key64733': 'value96747',
},
    {
    'id': 17527480144868,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Tiffany White',
    'address': '56953 Anthony Square\nNorth Kathy, MN 40633',
    'text': 'Industry appear beyond moment future bar. Assume herself personal several child. Particularly mission great.',
    'email': 'christinarodriguez@example.org',
    'phone_number': '681.760.0953',
    'json': {
    'name': 'Anthony Chandler',
    'address': '380 Baker Courts\nChristopherfurt, LA 44944',
},
    'key69704': 'value50245',
    'key41222': 'value81323',
    'key33305': 'value91989',
    'key94981': 'value74056',
    'key70299': 'value1817',
    'key69013': 'value4919',
},
    {
    'id': 17527480144882,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Stephanie Johnson',
    'address': '010 Price Causeway\nJohnsonfort, NV 71333',
    'text': 'Situation traditional believe matter design there.\nReal human like agree respond. Along goal condition whole.\nInteresting debate per nothing decade dinner. Bring bag foot event bad different memory.',
    'email': 'barbaragomez@example.com',
    'phone_number': '635-423-3665',
    'json': {
    'name': 'Mike Lee',
    'address': '26530 Humphrey Passage Suite 858\nLake Charles, PW 58949',
},
    'key49004': 'value4562',
    'key61425': 'value41768',
    'key53236': 'value44552',
    'key48389': 'value7167',
},
    {
    'id': 17527480144896,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Dr. Alan Roman',
    'address': '13865 Jackson Forges\nLake Patrick, ND 27504',
    'text': 'Single ability eye stop. Something despite letter subject smile.\nBehind laugh bit thank. After fact section enter state two structure. Bed machine still on relate question similar.',
    'email': 'gary48@example.org',
    'phone_number': '322-972-4255',
    'json': {
    'name': 'Holly Wood',
    'address': '61695 Diane Mission Suite 597\nIngramland, WA 29163',
},
    'key87960': 'value79358',
    'key25034': 'value86066',
    'key55489': 'value41941',
    'key46431': 'value15522',
    'key84102': 'value64714',
    'key62523': 'value74818',
    'key75465': 'value75141',
    'key94003': 'value69544',
    'key6844': 'value16004',
},
    {
    'id': 17527480144908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Suzanne Gallagher',
    'address': '4056 Nichole Estates\nSnyderberg, MO 39907',
    'text': 'Statement toward long adult join. Identify him woman memory. For kitchen husband people American.\nOut statement brother information why ability of. Result man its professor end store.',
    'email': 'talexander@example.org',
    'phone_number': '658.246.6242',
    'json': {
    'name': 'Joseph Anderson',
    'address': '28599 Jones Springs\nBenjaminview, MI 11603',
},
    'key15474': 'value74513',
    'key60212': 'value3135',
    'key61297': 'value69571',
    'key92134': 'value2490',
},
    {
    'id': 17527480144920,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Rhonda Moore',
    'address': 'PSC 5894, Box 5888\nAPO AE 24988',
    'text': 'Green look movie. Kitchen want art after wrong. Girl until factor small when work.\nAlthough option enter so push treatment take. Must human where environment miss son finish.',
    'email': 'danielslisa@example.net',
    'phone_number': '545-760-7163',
    'json': {
    'name': 'Dr. Kara Jones',
    'address': '7538 Taylor Underpass\nWillisside, VT 13197',
},
    'key59807': 'value34973',
    'key5248': 'value51581',
    'key16072': 'value63181',
    'key70059': 'value54916',
    'key23045': 'value50997',
    'key22765': 'value9705',
    'key92836': 'value93042',
    'key64972': 'value71071',
    'key19723': 'value20844',
    'key416': 'value24641',
},
    {
    'id': 17527480144931,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kenneth Brown',
    'address': 'Unit 4191 Box 5515\nDPO AA 64196',
    'text': 'Generation as free trip. World base make guy movement evidence.\nTrue wind station green drop cold Mrs certainly. Stay may sea road since. Them several great attorney wife get.',
    'email': 'davidmurphy@example.com',
    'phone_number': '+1-255-427-8049',
    'json': {
    'name': 'Misty Brewer',
    'address': '02356 Kelly Stream Apt. 483\nRuthland, AK 72278',
},
    'key80446': 'value56266',
    'key88193': 'value69506',
    'key76570': 'value55037',
    'key56445': 'value41889',
},
    {
    'id': 17527480144941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Joshua Marshall',
    'address': '654 Jessica Crossing\nNew Jessicastad, DE 39533',
    'text': 'Take write leg court political have. Compare military person tonight movement allow. Bad into level worker production.',
    'email': 'danielle11@example.net',
    'phone_number': '6168830333',
    'json': {
    'name': 'Justin Fitzgerald',
    'address': '23210 Woodard Extensions\nWilliestad, ME 03903',
},
    'key99577': 'value87343',
    'key3094': 'value99461',
    'key74620': 'value14906',
},
    {
    'id': 17527480144952,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Bradley Crawford',
    'address': '9403 Brown Spur Apt. 536\nLisaberg, SC 28522',
    'text': 'Decide others his kid seat south local president. Respond past wish staff me eye seek. Parent skin site play growth. Guy imagine every resource picture food.',
    'email': 'carol93@example.com',
    'phone_number': '640.371.6699x84453',
    'json': {
    'name': 'John Rivera',
    'address': '6929 Gay Gardens\nSusanfort, VA 77988',
},
    'key63268': 'value46402',
    'key83288': 'value56602',
    'key12879': 'value99391',
    'key34958': 'value95946',
    'key21091': 'value93825',
    'key10606': 'value76393',
    'key80185': 'value78151',
    'key65918': 'value71707',
    'key99665': 'value55541',
},
    {
    'id': 17527480144964,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Heidi Jackson',
    'address': '6511 Sawyer Mall\nNorth Donfort, NJ 15599',
    'text': 'Discover hold hard TV alone real suffer. Religious recently city.\nTrip data campaign measure road. Act small list rich identify. Employee level key reason you step.',
    'email': 'huffmanann@example.com',
    'phone_number': '(671)875-1502x573',
    'json': {
    'name': 'Melissa Torres',
    'address': '3092 Bianca Islands\nNorth Nicholas, OH 22259',
},
    'key21860': 'value24567',
    'key45238': 'value32812',
    'key18327': 'value27652',
    'key1775': 'value74201',
    'key77221': 'value57718',
    'key68232': 'value85953',
},
    {
    'id': 17527480144976,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Logan Oconnell',
    'address': '1084 Chris Station Suite 043\nSouth Reginafort, MS 31003',
    'text': 'Career hotel player worry. Administration force management long leader arm.\nYour blood some. Upon carry very sport day idea attention. Knowledge reveal sure star.',
    'email': 'leematthew@example.net',
    'phone_number': '(230)522-6672',
    'json': {
    'name': 'Brian Day',
    'address': '817 Harvey Glens Apt. 690\nHeatherchester, GA 07391',
},
    'key47062': 'value23994',
    'key70369': 'value44030',
},
    {
    'id': 17527480144988,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Brian Miller',
    'address': '35912 Erik Inlet\nPort Tracystad, IN 16562',
    'text': 'Write land once environmental source exist. Point finally conference soon thought party kid.\nGo similar indicate after could. Tough help military long.',
    'email': 'chelsea71@example.com',
    'phone_number': '492-286-3578x872',
    'json': {
    'name': 'Barbara Chang',
    'address': '219 Joan Roads\nSouth Soniaview, MH 89671',
},
    'key33138': 'value45071',
    'key8666': 'value79747',
    'key38222': 'value26391',
    'key55287': 'value30705',
    'key28938': 'value87198',
},
    {
    'id': 17527480145000,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'James Green',
    'address': '46535 Chaney Shore\nZacharychester, PW 06381',
    'text': 'Realize picture later example report economic.\nOld space determine be nearly. At beat through friend.\nArm there always. Majority report among anything. North enjoy police indicate her expect.',
    'email': 'denisecaldwell@example.org',
    'phone_number': '+1-625-941-8752x4501',
    'json': {
    'name': 'Kathleen Gonzalez',
    'address': '747 Meyer Land\nWilliamstown, VA 85759',
},
    'key25334': 'value85325',
    'key34571': 'value34014',
    'key54991': 'value66818',
    'key84758': 'value65137',
},
    {
    'id': 17527480145012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Robert Bishop',
    'address': '8590 Elizabeth Summit\nOrtizville, OH 41651',
    'text': 'Power experience couple hour away since. Admit hope require painting end. Me pay group issue program nice.\nRange fire any else big into oil. Provide up assume to. Second point wind test.',
    'email': 'davidlutz@example.org',
    'phone_number': '001-795-967-6158x550',
    'json': {
    'name': 'Jeffrey Hickman',
    'address': '579 Moon Court\nEast Allison, MS 14894',
},
    'key82930': 'value59516',
    'key56065': 'value98179',
},
    {
    'id': 17527480145024,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Richard Rosales',
    'address': '5545 Galloway Land\nHughesside, NC 06024',
    'text': 'Suffer generation property I drug. Subject north decade rise.\nReturn everything eight water relate easy one tell. Process minute memory soon.',
    'email': 'danielle64@example.com',
    'phone_number': '001-695-325-4903x6600',
    'json': {
    'name': 'Mark Andrews',
    'address': '613 Sanchez Fords\nTarafort, SC 34432',
},
    'key8206': 'value54204',
    'key33694': 'value76741',
    'key88260': 'value38566',
    'key17732': 'value74910',
    'key57482': 'value72850',
    'key29098': 'value98135',
},
    {
    'id': 17527480145035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Mckenzie Taylor',
    'address': '082 Gibson Neck\nSouth Pamelachester, AR 17396',
    'text': 'Decide wonder describe save may travel somebody. Into to prove set whose why. Central pressure employee paper fear. Office life notice data.',
    'email': 'kellywarner@example.org',
    'phone_number': '001-792-559-1680x9436',
    'json': {
    'name': 'Angela Banks',
    'address': '31393 Quinn Drive Suite 498\nNorth Mary, AR 01726',
},
    'key81249': 'value4663',
    'key16921': 'value44591',
},
    {
    'id': 17527480145047,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Jeremy Harris',
    'address': '42628 Barbara Station\nHeatherland, MI 29923',
    'text': 'Under result source home part happen thank. Piece a wife.\nOwn stand seek or good.\nAmong others key support. Talk behind per lawyer clear. Wait management picture begin lose.',
    'email': 'david67@example.net',
    'phone_number': '642.248.8090',
    'json': {
    'name': 'Julie Sims',
    'address': '788 Henderson Shoal Apt. 608\nNorth Michelle, MA 31770',
},
    'key55337': 'value92633',
    'key97524': 'value25636',
    'key61308': 'value76706',
    'key6005': 'value39772',
    'key22800': 'value71966',
},
    {
    'id': 17527480145057,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'David Shields',
    'address': '43505 Allen Mill Suite 572\nJoelborough, VT 53521',
    'text': 'Special worry point indicate rate travel. Late drop water.\nUpon reach writer treat reflect. Any another student cold number road.\nQuickly group store.',
    'email': 'bjenkins@example.com',
    'phone_number': '(796)260-9182',
    'json': {
    'name': 'Michael Chavez',
    'address': '47688 King Hollow\nNew Brandy, AS 94716',
},
    'key60364': 'value4931',
    'key52498': 'value52577',
},
    {
    'id': 17527480145068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Chad Williams',
    'address': 'USS Snyder\nFPO AP 17568',
    'text': 'Career force recent break yeah let. Effort help catch whether.\nOur history avoid direction protect within white. Hit general career. Face left history between figure sea.',
    'email': 'ywilliams@example.net',
    'phone_number': '(678)239-8385x217',
    'json': {
    'name': 'Sheri Wright',
    'address': '517 Ashley Ramp Apt. 485\nWest Michael, VT 16740',
},
    'key13689': 'value89497',
},
    {
    'id': 17527480145078,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Diana Joseph',
    'address': '784 Ray Courts\nWeissland, WA 09440',
    'text': 'Market myself city green recognize happy some. Various across herself stock reach responsibility former.\nBut song quality four very. Medical last traditional value letter fine give. Again type safe.',
    'email': 'gabrielle36@example.com',
    'phone_number': '001-857-554-1196',
    'json': {
    'name': 'Joy Dunn',
    'address': '21849 Fry Way\nLake Codyberg, WI 59260',
},
    'key41894': 'value43206',
    'key15257': 'value76754',
    'key49117': 'value12849',
    'key90142': 'value85397',
    'key9875': 'value9598',
    'key90600': 'value56979',
    'key35577': 'value58044',
    'key46514': 'value11754',
    'key35388': 'value57659',
},
    {
    'id': 17527480145089,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Michael Jacobson',
    'address': '94872 Palmer Rest Suite 877\nWest Aaronville, OR 49357',
    'text': 'Million kitchen action choose bar right left. Shoulder significant machine buy now.\nFour later growth together seek.',
    'email': 'jfields@example.com',
    'phone_number': '6538569386',
    'json': {
    'name': 'Sarah Singh',
    'address': '56065 Cheryl Alley Suite 527\nEast Larrychester, HI 50836',
},
    'key34550': 'value52991',
    'key26566': 'value10501',
    'key17099': 'value28561',
    'key86541': 'value95848',
    'key26211': 'value84735',
    'key52524': 'value53529',
},
    {
    'id': 17527480145099,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'William Duncan',
    'address': '977 James Branch\nWest Juan, IN 76182',
    'text': 'Inside reveal up much couple. Nearly environmental also still develop owner region.',
    'email': 'ehill@example.com',
    'phone_number': '001-425-202-7423x27209',
    'json': {
    'name': 'Travis Hall',
    'address': '5824 Bonnie Viaduct\nNorth Matthewfurt, PR 62597',
},
    'key57087': 'value93553',
    'key58199': 'value81398',
    'key3719': 'value31809',
},
    {
    'id': 17527480145110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Sharon Smith',
    'address': '654 Nancy Circles\nNorth Curtisbury, GA 38486',
    'text': 'Institution everything nor knowledge either game. Station behind father month. Provide individual after down.',
    'email': 'williamschristine@example.org',
    'phone_number': '(731)281-7284x1814',
    'json': {
    'name': 'Michael Jones',
    'address': '377 Price Lodge\nNicholasfort, WV 38822',
},
    'key78135': 'value53872',
    'key86736': 'value99163',
    'key27469': 'value71264',
    'key96005': 'value58377',
    'key30296': 'value14167',
    'key95874': 'value89132',
    'key12113': 'value14898',
    'key43401': 'value69117',
},
    {
    'id': 17527480145121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Kathryn Shah',
    'address': '1979 Martinez Ville Apt. 657\nJasonmouth, PA 33171',
    'text': 'Run form they happen toward. Remain hot important yeah.\nHuge teach hotel spring perhaps focus mention. Week level else us maintain argue response there. General thousand impact collection.',
    'email': 'ohuynh@example.org',
    'phone_number': '(213)388-2506x061',
    'json': {
    'name': 'Lisa Banks',
    'address': '60490 Diana Pass Suite 660\nWest Christopher, NC 33113',
},
    'key23824': 'value87683',
    'key37354': 'value75880',
    'key18768': 'value78781',
    'key62091': 'value56438',
    'key20881': 'value80603',
    'key42706': 'value2965',
},
    {
    'id': 17527480145132,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jessica Young',
    'address': '8134 Ray Fords Apt. 221\nWest Jim, TN 52621',
    'text': 'Ever weight if evidence certainly. Part single place piece person. How what sense possible.',
    'email': 'lauren40@example.net',
    'phone_number': '+1-770-883-0043x775',
    'json': {
    'name': 'Shannon Perez',
    'address': '550 Lewis Coves Suite 027\nEast Zacharyfurt, MT 11576',
},
    'key810': 'value79415',
    'key90292': 'value14672',
    'key24330': 'value27722',
    'key93159': 'value1436',
    'key5380': 'value6621',
    'key53304': 'value45252',
    'key41691': 'value90912',
    'key35583': 'value4641',
    'key71780': 'value92904',
},
    {
    'id': 17527480145144,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Charles Johnson',
    'address': '2523 Jeremy Meadow Suite 102\nEast Tracy, VA 99720',
    'text': 'Quickly dinner around sound.\nIncrease whose candidate house former. End and see interview example. Between those her skill group fill fire.',
    'email': 'gzimmerman@example.org',
    'phone_number': '+1-814-754-6901',
    'json': {
    'name': 'Debra Powell',
    'address': '03365 Karen Manors Apt. 397\nKlinetown, VA 56699',
},
    'key31933': 'value83849',
    'key83813': 'value92426',
},
    {
    'id': 17527480145154,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Emily Keller',
    'address': '38771 Matthew Grove\nMonicamouth, DE 67928',
    'text': 'Take again series industry. Between happy until. Body green rise campaign bank should half learn.\nTreat side debate fight behind sort remain.',
    'email': 'alexander74@example.com',
    'phone_number': '+1-978-716-7459',
    'json': {
    'name': 'Joseph Campbell',
    'address': '63150 Jason Trail\nReidmouth, MH 82203',
},
    'key97352': 'value51362',
},
    {
    'id': 17527480145164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Cristina Porter',
    'address': '9346 Charles Expressway\nSouth Jasonmouth, FL 72891',
    'text': 'Build modern under area subject. True measure detail no now.\nInternational large century rather lawyer expect however. Particularly sit stay two party Democrat. Imagine say any American.',
    'email': 'craigcarlos@example.com',
    'phone_number': '(802)778-6727',
    'json': {
    'name': 'Cynthia Fitzgerald',
    'address': '333 Howell Coves\nBarberfort, CA 64403',
},
    'key25762': 'value17338',
    'key50618': 'value77040',
    'key38851': 'value84510',
    'key71043': 'value80098',
    'key80032': 'value75555',
},
    {
    'id': 17527480145176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'John Hansen',
    'address': '12783 Derrick Street Suite 149\nAlicetown, CA 08385',
    'text': 'Authority maybe physical born. Decade hit former less education letter spring.\nAdministration call think guy. Hard task in now mouth. Attack place station theory summer less dark.',
    'email': 'courtney61@example.net',
    'phone_number': '660-916-4185x99005',
    'json': {
    'name': 'Sharon Stokes',
    'address': '39932 Vasquez Corners Apt. 692\nPort Scott, PW 62714',
},
    'key87526': 'value32215',
    'key20738': 'value38997',
    'key64652': 'value7685',
    'key7373': 'value98541',
    'key47326': 'value82668',
    'key51746': 'value48557',
    'key41714': 'value43893',
    'key11080': 'value50827',
    'key93713': 'value48208',
},
    {
    'id': 17527480145187,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Daniel Chambers',
    'address': '02249 Janice Village Suite 179\nEast Steven, NY 21397',
    'text': 'What once newspaper much guess. Almost few lawyer service phone.\nCapital prove design foreign whole. House value word town road.',
    'email': 'kathleendavis@example.org',
    'phone_number': '665-316-6005x528',
    'json': {
    'name': 'Juan Brown',
    'address': '74422 Green Village\nFowlerfort, OR 20297',
},
    'key65756': 'value67240',
    'key96042': 'value74852',
},
    {
    'id': 17527480145199,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Donald Steele',
    'address': '96721 Christina Isle\nEast Angela, MH 37675',
    'text': 'Everyone join sing value pretty class home. Style cold executive face really.',
    'email': 'brandonmills@example.org',
    'phone_number': '960-582-2244x410',
    'json': {
    'name': 'Anthony Johnson',
    'address': '0160 Heather Flat\nSouth Erin, OK 80121',
},
    'key62540': 'value36892',
},
    {
    'id': 17527480145209,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Joshua Daugherty',
    'address': 'USS Ford\nFPO AA 06071',
    'text': 'Court ago change minute subject. Growth quite matter black you film trip. Discuss down series.\nData hot lot kitchen deal. Debate late season back difficult add gas life. Alone front drop and data.',
    'email': 'kevinlarson@example.net',
    'phone_number': '462-589-8330',
    'json': {
    'name': 'Elizabeth Brown',
    'address': '9587 Alvarado Mills\nEricmouth, NJ 09315',
},
    'key20995': 'value58425',
    'key76116': 'value62648',
    'key97418': 'value72118',
    'key48565': 'value47274',
    'key71298': 'value9705',
    'key24622': 'value71808',
    'key45261': 'value84818',
    'key27956': 'value37035',
},
    {
    'id': 17527480145219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Kyle Powers',
    'address': 'Unit 7943 Box 1987\nDPO AA 63082',
    'text': 'Describe cultural seat data response security. Garden hour prepare cup memory item major.\nDemocrat writer person sister. Realize room yeah determine region.',
    'email': 'patricia33@example.com',
    'phone_number': '001-705-783-6704x60331',
    'json': {
    'name': 'Brenda Miller',
    'address': '202 Ricardo Flat Suite 431\nThomasville, MA 34745',
},
    'key59072': 'value57072',
    'key8502': 'value90221',
    'key45996': 'value71471',
    'key50529': 'value68457',
    'key60694': 'value69410',
    'key57874': 'value67801',
},
    {
    'id': 17527480145228,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'William Avila',
    'address': '21751 Shelly Knoll\nWigginstown, NV 16907',
    'text': 'Trial car price air.\nHuman lot student interesting down spring rule care. Though wait never nothing approach leave include. Management candidate often much range science reason.',
    'email': 'sara91@example.com',
    'phone_number': '+1-580-209-0819x42487',
    'json': {
    'name': 'Tina Perry',
    'address': '1836 Brian Oval Apt. 813\nNorth Kristin, WI 89004',
},
    'key70505': 'value97306',
    'key33873': 'value60325',
    'key65787': 'value42063',
    'key43790': 'value40803',
    'key88553': 'value86070',
    'key82126': 'value95104',
},
    {
    'id': 17527480145238,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Regina Barton',
    'address': '597 Stewart Spurs Suite 230\nAllenborough, SC 66090',
    'text': 'Billion recent minute teacher they company success. Green themselves western recently when else.\nTrue red note price try create.\nAvailable ground fine shoulder. Trouble rock son century remember.',
    'email': 'kristen39@example.com',
    'phone_number': '652.832.0336x0012',
    'json': {
    'name': 'Dr. Jason Richardson',
    'address': '072 Steven Path Suite 810\nEast Derekview, WV 48801',
},
    'key4008': 'value86509',
    'key43775': 'value972',
    'key65750': 'value70531',
    'key99818': 'value75495',
    'key15812': 'value50578',
    'key39512': 'value4476',
    'key69830': 'value83665',
    'key93949': 'value27814',
    'key78843': 'value18194',
    'key93875': 'value79120',
},
    {
    'id': 17527480145249,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Steven Wright',
    'address': '4591 Hall Knolls\nPort Jeffrey, CT 30663',
    'text': 'Answer really visit our. South available low but. Store service impact.\nMilitary set break necessary. Start leg guess fill peace wall hospital.',
    'email': 'allenbrenda@example.com',
    'phone_number': '783.507.1627',
    'json': {
    'name': 'Lisa Ali',
    'address': 'USS Hunt\nFPO AP 92992',
},
    'key36564': 'value40744',
    'key96939': 'value30857',
    'key16951': 'value85867',
    'key48902': 'value54572',
    'key13357': 'value76129',
    'key10642': 'value5456',
    'key68236': 'value84084',
    'key83188': 'value37084',
    'key59593': 'value78825',
},
    {
    'id': 17527480145259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Melissa Park',
    'address': '944 Drake Row Apt. 925\nJeffbury, GU 46110',
    'text': 'Fund Mrs four any nor say. Organization care issue know program.\nForward thought bad begin. Job picture those get ever live full industry.',
    'email': 'mccoyseth@example.com',
    'phone_number': '(907)316-9728',
    'json': {
    'name': 'Colleen Green',
    'address': 'USNS Stone\nFPO AA 44212',
},
    'key54498': 'value64309',
    'key27363': 'value78985',
    'key54998': 'value69263',
    'key19357': 'value4935',
    'key35609': 'value55895',
    'key31139': 'value14609',
    'key90479': 'value73996',
},
    {
    'id': 17527480145270,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Chelsey Harrison',
    'address': '05682 Bryan Valleys\nEast Natashaberg, MP 16633',
    'text': 'Reach soldier form follow father. Bit next campaign public show begin.\nMouth occur operation whom fine source season. But event suddenly. Line contain free administration must.',
    'email': 'bvargas@example.com',
    'phone_number': '2465760825',
    'json': {
    'name': 'Cynthia Sanchez',
    'address': '225 Williams Forest\nTammyberg, WI 96682',
},
    'key27896': 'value85345',
    'key61725': 'value53989',
    'key74188': 'value67357',
    'key62254': 'value77997',
    'key4542': 'value58354',
    'key11245': 'value60910',
},
    {
    'id': 17527480145280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Ryan Berry',
    'address': '50387 Parrish Gardens\nWest Johnathan, NM 78028',
    'text': 'Add herself water listen position. Source ground drive responsibility. Dog together now religious.',
    'email': 'josephmontes@example.net',
    'phone_number': '606-688-9431',
    'json': {
    'name': 'Jackson Shepherd',
    'address': 'USS Moore\nFPO AE 33314',
},
    'key20542': 'value58749',
    'key41700': 'value13386',
    'key94856': 'value85790',
    'key93645': 'value83712',
},
    {
    'id': 17527480145291,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Charles Buchanan',
    'address': '470 Victoria Hills\nStuartchester, IL 75254',
    'text': 'Mind moment simple receive whole fact. Nice north a dark. Section enough watch feel.\nTrip one best population many change clearly. Act wait large over. Party final you deep meet.',
    'email': 'ggriffin@example.org',
    'phone_number': '001-714-242-0950x3152',
    'json': {
    'name': 'Aaron Jones',
    'address': '7051 Kimberly Summit\nWest Stephanie, ID 52282',
},
    'key54117': 'value94613',
    'key96425': 'value42759',
    'key50525': 'value89121',
    'key18484': 'value86801',
    'key81889': 'value4580',
    'key45549': 'value55238',
    'key70619': 'value18334',
    'key26714': 'value38649',
    'key45629': 'value56018',
    'key85340': 'value28239',
},
    {
    'id': 17527480145301,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Jason Ortiz',
    'address': '0603 Andrew Pike\nNorth Craig, FL 32885',
    'text': 'Difficult see after send kitchen into hospital. Drive face large accept main.',
    'email': 'jonathangilbert@example.com',
    'phone_number': '(904)613-5091x795',
    'json': {
    'name': 'Bianca Guerrero',
    'address': '593 Barbara Crescent\nAlexanderport, WI 91970',
},
    'key78772': 'value1692',
    'key88381': 'value21948',
    'key81286': 'value79280',
    'key39364': 'value46062',
    'key66400': 'value75091',
    'key92104': 'value5585',
    'key90926': 'value81889',
},
    {
    'id': 17527480145312,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Tammy Schmidt',
    'address': '62942 Eugene Ridges Suite 805\nEast Brianhaven, AR 83668',
    'text': 'Improve medical while be form subject fine. Fear effort consider provide plan race president too.\nHere something Republican blue PM.',
    'email': 'jamesallen@example.org',
    'phone_number': '(243)240-3083',
    'json': {
    'name': 'Kimberly Bryant',
    'address': '58090 Ronnie Pike\nJonathantown, MD 72003',
},
    'key50366': 'value32131',
    'key22397': 'value42164',
    'key79853': 'value5269',
    'key14576': 'value44085',
    'key63364': 'value1780',
    'key28695': 'value47094',
    'key14169': 'value46305',
    'key9897': 'value48903',
    'key98270': 'value78070',
},
    {
    'id': 17527480145323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Ronald Wright Jr.',
    'address': '9076 Melinda Forges\nSamanthashire, PA 84666',
    'text': 'Glass simple trip but growth. Common value question owner some. Not on their receive force represent where pay. Miss quickly region challenge million new.',
    'email': 'jade09@example.com',
    'phone_number': '691-478-8018x0888',
    'json': {
    'name': 'Laurie Hansen',
    'address': '0510 Greer Mission Suite 114\nAllenland, FL 79192',
},
    'key42973': 'value83768',
    'key26747': 'value56535',
    'key26350': 'value68228',
    'key12901': 'value658',
    'key2674': 'value80470',
    'key13282': 'value23101',
    'key7019': 'value42632',
    'key70836': 'value96324',
    'key62486': 'value17411',
},
    {
    'id': 17527480145334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Mrs. Amanda Grant MD',
    'address': 'PSC 8390, Box 7643\nAPO AA 31402',
    'text': 'Themselves author produce west itself expect. As standard amount meet college back material. Week school result particular note pretty important.',
    'email': 'juareztimothy@example.net',
    'phone_number': '737.200.3803x803',
    'json': {
    'name': 'Jeffrey Rangel',
    'address': '361 Mcguire Isle Suite 008\nAutumnmouth, AS 47249',
},
    'key278': 'value31837',
    'key38750': 'value10881',
    'key90924': 'value30545',
    'key13270': 'value55440',
    'key15667': 'value89904',
    'key50798': 'value57904',
    'key11644': 'value44807',
    'key30599': 'value67287',
},
    {
    'id': 17527480145345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Angela Dixon',
    'address': '175 Becker Land\nSouth Johnburgh, RI 94317',
    'text': 'About second table professional me day list relate. Wind then media that. Common vote mission mouth expert necessary.',
    'email': 'heather32@example.org',
    'phone_number': '+1-868-366-6130x59916',
    'json': {
    'name': 'Philip Williams',
    'address': '435 Braun Plaza\nWest Lisaburgh, AK 93359',
},
    'key57850': 'value60645',
    'key2221': 'value28372',
    'key94249': 'value60390',
    'key18077': 'value177',
    'key30774': 'value88415',
    'key84603': 'value53021',
    'key38776': 'value5297',
    'key12412': 'value54799',
    'key36892': 'value63743',
    'key12821': 'value95584',
},
    {
    'id': 17527480145356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Amy Berg',
    'address': '354 Simon Ways\nPort Joy, OH 66364',
    'text': 'Though society nearly paper sister rock. Figure start during. They data business successful. Reduce value grow choose trip with.',
    'email': 'hhale@example.org',
    'phone_number': '5793596034',
    'json': {
    'name': 'Adam Mitchell',
    'address': '25136 Lopez Run Apt. 442\nPort Reneemouth, CT 63494',
},
    'key88952': 'value58359',
    'key87452': 'value88309',
    'key27947': 'value43683',
    'key66549': 'value37620',
    'key16637': 'value15471',
    'key38155': 'value98658',
    'key70873': 'value40991',
},
    {
    'id': 17527480145368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Alan Thompson',
    'address': '4656 Burnett Meadow\nLake Peterstad, IN 49667',
    'text': 'Develop attack pay feeling yourself.\nCall open raise ability watch. Another response figure start. Where cut difference.\nTogether young watch thank fly.',
    'email': 'othompson@example.com',
    'phone_number': '(667)418-5381x61741',
    'json': {
    'name': 'Stephanie Case',
    'address': '67399 Alvarez Glens\nPort Josephside, ID 65300',
},
    'key93600': 'value66552',
    'key52809': 'value21609',
    'key24374': 'value24830',
    'key45458': 'value90948',
    'key53507': 'value62174',
    'key47160': 'value88573',
    'key82036': 'value88675',
    'key63562': 'value85167',
    'key28237': 'value64902',
    'key86241': 'value39887',
},
    {
    'id': 17527480145380,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Robyn Parker',
    'address': '404 Brandi Circles\nMillerhaven, ND 33118',
    'text': 'Actually action far run national firm create control. Agreement then herself south entire future.',
    'email': 'andrew03@example.net',
    'phone_number': '557.863.9528x72524',
    'json': {
    'name': 'Michelle Bates',
    'address': '64356 Anderson Mall Apt. 253\nKhanberg, MN 73012',
},
    'key82093': 'value45213',
    'key89986': 'value72411',
    'key72867': 'value50122',
},
    {
    'id': 17527480145392,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Greg Watson',
    'address': '477 Michael Cape\nLake Francisco, ND 18561',
    'text': 'Us key teach. Just show result against. Radio about blood he.\nFrom Congress during ok plant parent do.',
    'email': 'sweeks@example.org',
    'phone_number': '574-950-2949',
    'json': {
    'name': 'Sandra Bennett',
    'address': '536 Lawrence Trafficway Apt. 911\nNew Kristenborough, KY 18694',
},
    'key44352': 'value69588',
    'key69381': 'value97535',
    'key56561': 'value95343',
    'key31916': 'value68170',
},
    {
    'id': 17527480145403,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Michael Caldwell',
    'address': '640 Martin Radial\nNew Lynnview, NV 24435',
    'text': 'Sport animal arm thousand. History assume road fast may across each. Fill since exist trade.\nWonder step loss. Course source total class may think operation along.',
    'email': 'icruz@example.net',
    'phone_number': '8423467334',
    'json': {
    'name': 'Andrew Meyers',
    'address': '4189 Shannon Turnpike\nMistyview, WI 82264',
},
    'key38631': 'value69325',
    'key38520': 'value52590',
    'key3808': 'value34742',
    'key87707': 'value75946',
    'key220': 'value48118',
    'key75211': 'value38004',
    'key55294': 'value17605',
    'key42802': 'value98513',
    'key14653': 'value93490',
    'key83491': 'value96476',
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
    'RequestId': '8bb5d992-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_48_389446vLXzELEH',
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
    'RequestId': '8bb5d992-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_26_48_389446vLXzELEH',
    'dimension': 128,
    'metricType': 'COSINE',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_simple_payload[COSINE]_1752748015.json')
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
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithSimplePayloadCosine1752748015Json()
    test.run_tests()
