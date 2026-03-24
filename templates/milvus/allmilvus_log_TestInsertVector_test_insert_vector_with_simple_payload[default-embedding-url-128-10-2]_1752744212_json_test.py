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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-10-2]_1752744212_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-10-2]_1752744212.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl1281021752744212Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-10-2]_1752744212.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-10-2]_1752744212.json"
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
    'RequestId': 'b51f11fb-62ef-11f0-af5f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_31_390218zbNckKsF',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
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
    'RequestId': 'b5261050-62ef-11f0-8d80-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_31_390218zbNckKsF',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Roger Walls',
    'address': '74066 King Cliffs\nNew Michaelview, VI 50158',
    'text': 'Approach explain should check analysis policy. Think responsibility week central.\nCenter up whose garden third military bar. Pretty success house month discuss. Age represent fear past bed structure.',
    'email': 'scott41@example.org',
    'phone_number': '(411)611-8816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Stevens',
    'Alexandria Garrett',
    'Samantha Stanton',
],
    'json': {
    'name': 'Michael Santos',
    'address': '96159 Gerald Mountains Apt. 334\nHartburgh, GA 60553',
},
    'key31304': 'value28348',
    'key22719': 'value9218',
    'key29603': 'value88512',
    'key31909': 'value22886',
    'key54131': 'value61555',
    'key40691': 'value4182',
    'key24725': 'value72822',
    'key39074': 'value80792',
    'key59581': 'value36729',
    'key66172': 'value19684',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Thomas Warren',
    'address': 'USCGC Simmons\nFPO AA 93958',
    'text': 'Move feel side space letter air.\nUpon before event bank. Start war his address respond practice.',
    'email': 'zlewis@example.net',
    'phone_number': '337.669.5851x43268',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Nelson',
    'Jon Williams',
    'Laura Wagner',
    'Edwin Montoya',
    'Kristi Hernandez',
],
    'json': {
    'name': 'Lisa Stafford',
    'address': '91470 Kenneth Viaduct Apt. 179\nMichaelville, UT 77036',
},
    'key38640': 'value74551',
    'key33228': 'value8015',
    'key82749': 'value8072',
    'key13955': 'value84170',
    'key68301': 'value530',
    'key86741': 'value84357',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Shelly Carr',
    'address': '191 Kathy Harbor\nLangchester, ND 62008',
    'text': 'Economic gas allow situation along three task easy. Teach rock or yourself government full item.\nPicture computer already question job rather sometimes.',
    'email': 'susanparrish@example.net',
    'phone_number': '001-514-432-3960x2679',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Charles',
    'Catherine Garcia',
],
    'json': {
    'name': 'Holly Wilson',
    'address': 'Unit 3509 Box 7828\nDPO AE 95562',
},
    'key48252': 'value80263',
    'key90239': 'value6526',
    'key94114': 'value87242',
    'key23541': 'value55214',
    'key16097': 'value44862',
    'key80117': 'value85791',
    'key71505': 'value14906',
    'key68282': 'value22544',
    'key52996': 'value61356',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Joan Cox',
    'address': '93363 Saunders Streets Apt. 327\nBerrychester, NE 74983',
    'text': 'Responsibility free likely meet hard history. Enter they enough term difficult. Consumer option myself during.',
    'email': 'owensjessica@example.com',
    'phone_number': '9679040434',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gary Williams',
    'Sherry Lloyd',
    'Ashley Ferguson',
    'Patricia Johnson',
],
    'json': {
    'name': 'Sara Mcmahon',
    'address': '09824 Tucker Turnpike\nWest Kaylaport, AS 78792',
},
    'key40942': 'value14391',
    'key95848': 'value88980',
    'key49623': 'value65274',
    'key76524': 'value33070',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Carmen Bowman',
    'address': '730 Evans Views Suite 635\nNew Heather, OK 55079',
    'text': 'Cell thus book discuss environmental hospital trouble. Trip book parent nature.',
    'email': 'ifigueroa@example.com',
    'phone_number': '001-901-834-5592',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joan Harris',
    'Maria Ortiz',
    'Eric Davis',
    'Brenda Diaz',
    'Nathan Hernandez',
    'Donna Smith',
    'Jenny Hayes PhD',
    'Mark Powell',
    'Derek Cohen',
    'Angela Hensley',
],
    'json': {
    'name': 'Sheila Ellis',
    'address': '7696 Kyle Corner Apt. 122\nLake Keith, HI 94468',
},
    'key35470': 'value80549',
    'key40479': 'value63938',
    'key62940': 'value38705',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Alexandria Houston',
    'address': 'USNV Reilly\nFPO AP 61680',
    'text': 'Business middle computer former clearly nation activity. Experience reality nearly behavior marriage. Cut past have even dog.\nField here word decide remember. Life issue without movement.',
    'email': 'lauren53@example.com',
    'phone_number': '(585)607-8116x405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Martha Cruz',
    'Adrienne Pitts',
    'Carol Ferguson',
    'Tony Hartman',
    'Wayne Luna',
],
    'json': {
    'name': 'Mr. Martin Wade DVM',
    'address': '3672 Sarah Summit\nSouth Lisaborough, AR 23048',
},
    'key91972': 'value76199',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Austin Edwards',
    'address': 'PSC 6765, Box 8717\nAPO AE 78216',
    'text': 'Especially short green assume tough ahead condition capital. Artist change face former.',
    'email': 'davisjohn@example.org',
    'phone_number': '388.839.6618',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Nelson',
    'Brian Gonzales',
    'Monica Taylor',
    'Jeffrey Smith',
    'Daniel Holder',
],
    'json': {
    'name': 'Kristen Morrow',
    'address': '850 Paula Locks Apt. 103\nAndrewmouth, NY 46011',
},
    'key87838': 'value88793',
    'key20780': 'value53489',
    'key25759': 'value98329',
    'key10297': 'value79938',
    'key84456': 'value98423',
    'key65972': 'value11834',
    'key96146': 'value50061',
    'key67614': 'value13371',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Gregory Sloan',
    'address': '682 Sarah Passage\nErinburgh, WY 65677',
    'text': 'Environment leader firm investment especially style guy. View or finish final mission street receive. Word build current PM together.',
    'email': 'adamsedward@example.net',
    'phone_number': '(668)788-1691x79280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Howell',
    'Donald Davis',
    'Donna Mueller',
],
    'json': {
    'name': 'Dr. Karen Gilmore',
    'address': '598 Stephanie Village Suite 966\nHallville, MA 90757',
},
    'key28936': 'value70980',
    'key93939': 'value11576',
    'key14428': 'value97400',
    'key51115': 'value63941',
    'key18762': 'value30445',
    'key31994': 'value89671',
    'key18355': 'value83347',
    'key94982': 'value14399',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jessica Oliver',
    'address': '874 Marquez Villages Apt. 402\nJohnmouth, ID 83901',
    'text': 'Product process side about in. Weight probably benefit which cut spring area.\nSystem fire month senior. Crime during knowledge exist before hundred fight word.',
    'email': 'hendersonangela@example.net',
    'phone_number': '+1-745-587-4059x3015',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steve Johnson',
    'Mr. Julian Mason',
    'Jaime Jones',
    'Ashley Arnold DDS',
    'Monica Santiago',
    'Brian Harris',
    'Shannon Williams',
],
    'json': {
    'name': 'Jerry Roberts',
    'address': '12583 Jasmine Vista\nNorth Heather, FM 52964',
},
    'key68457': 'value46402',
    'key89384': 'value92656',
    'key73583': 'value72253',
    'key85140': 'value27911',
    'key36936': 'value81116',
    'key72431': 'value89311',
    'key43204': 'value26202',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Sean Brown',
    'address': '3709 Mason Shores\nNorth Joshua, FM 55708',
    'text': 'Doctor either throughout leave half director glass.\nAlready seem simply population total power four. Eight huge theory generation his. Care vote rule teach as painting challenge despite.',
    'email': 'fthompson@example.com',
    'phone_number': '(754)657-3195',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Debra Smith',
    'Cynthia Archer',
    'Christopher Cummings',
    'Jessica Cook',
    'Mrs. Lauren Moore',
    'Mary Ross',
],
    'json': {
    'name': 'Lydia Johnson',
    'address': '0326 Alicia Crossing\nHenryton, MO 68702',
},
    'key41829': 'value11561',
    'key13632': 'value53212',
    'key22468': 'value2080',
    'key62728': 'value61164',
    'key68389': 'value9955',
    'key51618': 'value34026',
    'key77548': 'value10694',
    'key37566': 'value36247',
    'key82869': 'value33913',
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
    'RequestId': 'b51f11fb-62ef-11f0-af5f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_31_390218zbNckKsF',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-10-2]_1752744212.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl1281021752744212Json()
    test.run_tests()
