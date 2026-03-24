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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-2]_1752744155_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-2]_1752744155.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl1281021752744155Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-2]_1752744155.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-2]_1752744155.json"
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
    'RequestId': '9301a781-62ef-11f0-9ff3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_34_154908ibDyWgAU',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
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
    'RequestId': '9311d3f9-62ef-11f0-baa8-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_34_154908ibDyWgAU',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jeffrey Contreras',
    'address': '95034 Brittany Course Apt. 888\nMcclainfurt, VA 12450',
    'text': 'Defense effort list hope now. Knowledge land letter both memory method. Day beyond many choose there home. Add thing second money.',
    'email': 'nfarley@example.org',
    'phone_number': '001-350-226-4974x622',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Strong',
    'Michael Rodriguez',
    'Crystal Holmes',
    'Natasha Harris',
    'Amber Shaw',
    'Roger Waters',
    'Tammy Owens',
    'Sandra Russell',
    'Jodi Simmons',
],
    'json': {
    'name': 'James Mathews',
    'address': '74837 Lindsey Springs\nPetertown, FL 45558',
},
    'key81973': 'value84760',
    'key36100': 'value90922',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Denise Murphy',
    'address': '3912 Jason Meadow\nLake Danieltown, MS 61723',
    'text': 'As who box with pick piece. Trip specific artist across seat water. Again style site nice.',
    'email': 'hardingjoseph@example.org',
    'phone_number': '+1-742-385-1404x793',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Singh',
    'James Gould',
    'Reginald Prince',
    'Douglas Willis',
],
    'json': {
    'name': 'Scott Klein',
    'address': '0787 William Overpass\nPort Joeburgh, ME 83115',
},
    'key24879': 'value83399',
    'key217': 'value92245',
    'key15224': 'value11933',
    'key21430': 'value98679',
    'key59160': 'value41019',
    'key85400': 'value52648',
    'key12790': 'value24830',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Melissa Thomas',
    'address': '8919 Frank Expressway\nTurnerland, GA 05968',
    'text': 'Trial what pretty big may nearly. Last beautiful pull computer want health.\nOrganization will on what development protect.',
    'email': 'cynthiaparker@example.com',
    'phone_number': '244.842.0261',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Deleon',
    'Melissa Miller',
    'Roy Roman',
],
    'json': {
    'name': 'Carolyn Peterson',
    'address': '9009 Michelle Green\nSnyderfort, KY 23094',
},
    'key97264': 'value7312',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Luis Ward',
    'address': '38334 Paul Ridges Apt. 073\nJamesmouth, AS 11104',
    'text': 'Southern serious least large effect. Through successful deep former reality pay. Impact check role participant speak second several little.',
    'email': 'carlaalvarado@example.org',
    'phone_number': '848-829-8005x0639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Schmidt',
    'Daniel Lee',
    'Matthew Dougherty',
    'Jessica Miranda',
    'Leah Martinez',
    'Willie Stokes',
    'Mario Anderson',
    'Dawn Burke DDS',
    'Anthony Austin',
],
    'json': {
    'name': 'Jamie Brown',
    'address': '08820 Brenda Tunnel Apt. 770\nKarenfurt, TN 17025',
},
    'key31737': 'value37274',
    'key47903': 'value71027',
    'key29934': 'value27255',
    'key78962': 'value71201',
    'key2007': 'value89422',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Corey Rubio',
    'address': '934 Powell Grove Apt. 611\nClarkborough, LA 20521',
    'text': 'Describe fish eye property. Production your meet everyone.\nSea little evening discussion door prove. Summer black open source usually.\nFuture time article ok. During style serious.',
    'email': 'lanejoseph@example.org',
    'phone_number': '+1-866-694-5794x0686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sherri Fields',
    'Katrina Snyder',
    'Logan Hill',
    'Matthew Cook',
    'Andrew Wallace',
    'Charles Ewing',
],
    'json': {
    'name': 'Steven Jones',
    'address': '6146 Lauren Pine\nKarenfurt, WY 62734',
},
    'key35551': 'value65284',
    'key71945': 'value74813',
    'key72000': 'value53789',
    'key98507': 'value23616',
    'key91877': 'value2535',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Jessica Miller',
    'address': '1538 Moore Falls\nLake Susantown, FL 14111',
    'text': 'Remember remember describe rest ask. Side hand personal role involve someone.\nMajority tax many bad apply type. Tell particular ever along worry.',
    'email': 'sclark@example.com',
    'phone_number': '4158173141',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Wilson',
    'Donald Baker',
],
    'json': {
    'name': 'Douglas Sanders',
    'address': '8558 Alvarez Ports\nPort Lindsaymouth, AR 88117',
},
    'key31265': 'value57302',
    'key35260': 'value91626',
    'key19169': 'value97187',
    'key77369': 'value69360',
    'key56409': 'value49522',
    'key92084': 'value58491',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Matthew Reese',
    'address': 'Unit 3319 Box 4553\nDPO AA 18875',
    'text': 'Family event full affect. Know course everything next.\nFish father firm move use human. Style bring not future themselves. Traditional piece last computer.',
    'email': 'lisa80@example.net',
    'phone_number': '001-315-354-5905',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James Reilly',
    'Dennis Juarez',
    'David Nelson',
    'Kimberly Stokes',
    'Amanda Simpson',
],
    'json': {
    'name': 'Vincent Bailey',
    'address': '151 Timothy Plaza\nMerrittshire, VI 18971',
},
    'key70692': 'value60803',
    'key51361': 'value69658',
    'key46939': 'value34863',
    'key26036': 'value91533',
    'key48355': 'value29871',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Michael Murray',
    'address': '904 Jennings Expressway\nEast Ronaldport, OK 80832',
    'text': 'Skill perhaps for science future bank turn including. Theory although when chance respond inside. Lot able claim year.\nPerformance dinner seat race field its.',
    'email': 'carlsonjulia@example.com',
    'phone_number': '594-274-3256x56456',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Chen',
],
    'json': {
    'name': 'Todd Brown',
    'address': '482 James Garden\nSnydermouth, NE 07284',
},
    'key62537': 'value66297',
    'key95518': 'value95725',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Sandra Shelton',
    'address': 'PSC 9258, Box 6086\nAPO AA 27792',
    'text': 'Stay physical natural resource affect listen mind. Meet interview future sell several.\nStep traditional notice sit my within size.',
    'email': 'seth74@example.org',
    'phone_number': '(752)728-2737',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Heather Mcpherson',
    'Jeffrey Nelson',
],
    'json': {
    'name': 'Juan Matthews',
    'address': '38529 Perez Roads\nRichardsonland, AR 88519',
},
    'key78359': 'value14349',
    'key63120': 'value36466',
    'key30028': 'value58263',
    'key55469': 'value61935',
    'key80873': 'value93080',
    'key85479': 'value62326',
    'key32877': 'value31813',
    'key19419': 'value54778',
    'key37411': 'value37743',
    'key46570': 'value32622',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Amy Barnett',
    'address': '138 Jeffrey Route\nJonathanchester, DE 39387',
    'text': 'Truth tree class more writer. Project blood next modern find including. Ok audience push partner.\nImportant would nice spend. Way kid argue ahead put others still.',
    'email': 'jmcknight@example.com',
    'phone_number': '001-572-949-3843',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Campos',
    'Steven Duran',
    'Brandon Preston',
    'Elizabeth Brown',
],
    'json': {
    'name': 'Gregory George',
    'address': '9854 Adams Rapids\nRickyland, MN 70927',
},
    'key19751': 'value95589',
    'key67036': 'value92718',
    'key50122': 'value78952',
    'key39758': 'value58740',
},
],
    'dbName': 'prod',
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
    'RequestId': '9301a781-62ef-11f0-9ff3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_34_154908ibDyWgAU',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-2]_1752744155.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl1281021752744155Json()
    test.run_tests()
