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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-2]_1752744183_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-2]_1752744183.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl1281021752744183Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-2]_1752744183.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-2]_1752744183.json"
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
    'RequestId': 'a4214113-62ef-11f0-ba46-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_02_883274nixaUvuF',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'vector',
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
    'RequestId': 'a428868b-62ef-11f0-a682-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_02_883274nixaUvuF',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Kevin Vasquez',
    'address': '247 Harris Meadow Suite 988\nOsbornhaven, FL 73575',
    'text': 'Century office herself quickly record event special. Of why avoid place. Feeling impact whole.\nManagement painting beyond choice. Tell tend really attack meeting bed.',
    'email': 'walljustin@example.com',
    'phone_number': '001-429-937-1679',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Chavez',
    'Kaitlyn Williams',
    'Matthew Alvarado DDS',
    'Megan Johnson MD',
    'Cynthia Perry',
],
    'json': {
    'name': 'Jason Jenkins',
    'address': '66991 Zachary Orchard\nAshleyburgh, PW 61603',
},
    'key93204': 'value5853',
    'key25868': 'value77631',
    'key78805': 'value20089',
    'key10359': 'value2772',
    'key64049': 'value51246',
    'key79936': 'value98183',
    'key1815': 'value12134',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Andrea Price',
    'address': '5640 Joe Divide Suite 343\nWest Holly, OH 79088',
    'text': 'Remember marriage family choose election research station process. Much eye own him reduce.\nParticularly behind everyone magazine. Open develop quickly. Some news yet entire.',
    'email': 'mariaeaton@example.org',
    'phone_number': '+1-634-707-4816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Susan Miller',
    'Tricia Anderson',
    'Brianna Merritt',
    'Janet Carter',
    'Julie Sullivan',
    'Ricardo Jones',
    'Debbie Hudson',
    'Donna Bass',
    'Craig Parker',
],
    'json': {
    'name': 'Frederick Berg',
    'address': '29240 Watson Street Suite 500\nJohnland, NE 20411',
},
    'key4202': 'value35999',
    'key97142': 'value5348',
    'key74341': 'value23137',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jessica Mills',
    'address': '5554 Justin Views\nSouth Jamie, CA 54469',
    'text': 'Similar but beat conference individual before. Best between say. Participant practice approach wide cause spend painting.',
    'email': 'mliu@example.net',
    'phone_number': '420-604-5409x84444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Davis',
    'Sarah Hall',
    'Samuel Rivera',
],
    'json': {
    'name': 'Robert Cooper',
    'address': '11233 Carla Harbor Apt. 350\nBrianchester, MP 19964',
},
    'key92762': 'value37077',
    'key64960': 'value97517',
    'key34891': 'value23050',
    'key86336': 'value97085',
    'key47632': 'value90255',
    'key53948': 'value90245',
    'key73144': 'value67051',
    'key60665': 'value67932',
    'key76399': 'value37636',
    'key96045': 'value16203',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Troy Bennett',
    'address': '4937 Janice Springs\nTravisland, UT 34673',
    'text': 'Term world research ball final. Control surface south tend one. Give ahead field baby sometimes.\nPerson board sea start response remain.\nBring author year sign nature young between.',
    'email': 'ronaldhanna@example.com',
    'phone_number': '4264327744',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Griffin',
    'Patrick Clay',
    'Oscar Martinez',
    'Olivia Bartlett',
    'Richard Mcneil',
],
    'json': {
    'name': 'Denise Cunningham',
    'address': '8403 Greene Fort Suite 408\nPort Shelleyport, TX 49414',
},
    'key34773': 'value23481',
    'key62650': 'value21768',
    'key88727': 'value67045',
    'key78923': 'value95684',
    'key10758': 'value29553',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Samantha Sanchez',
    'address': '239 Armstrong Trail Suite 839\nNew Markmouth, NM 90445',
    'text': 'Plant professor fast because. Catch decide should factor. Citizen above baby contain price deep high. Media too me lay meet through teacher politics.',
    'email': 'maynicholas@example.com',
    'phone_number': '259.740.0939x761',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Wood',
    'Sean Henderson',
],
    'json': {
    'name': 'Susan Mathis',
    'address': '472 Darlene Isle\nPort Jessicamouth, MD 97771',
},
    'key36350': 'value44416',
    'key58804': 'value72397',
    'key6816': 'value77101',
    'key31929': 'value61801',
    'key41455': 'value3608',
    'key7851': 'value30104',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Amy Shepherd',
    'address': '17782 Zachary Springs Apt. 741\nEast Jessica, MN 47303',
    'text': 'Several turn nor. Not manager director recently. Thought common great community pick. Building little foot letter admit create nothing officer.',
    'email': 'richard44@example.com',
    'phone_number': '724.318.4878',
    'array_int_dynamic': [
    38523,
],
    'array_varchar_dynamic': [
    'Gail Love',
    'Darren Anderson',
    'Robert Anderson',
],
    'json': {
    'name': 'Ronald Munoz',
    'address': '878 Marissa Glens Apt. 446\nNew Danielle, MD 69187',
},
    'key81274': 'value61072',
    'key6646': 'value14245',
    'key92936': 'value59112',
    'key53837': 'value31871',
    'key60253': 'value64009',
    'key1745': 'value71484',
    'key77121': 'value35418',
    'key78899': 'value81344',
    'key23211': 'value34767',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Sandra Thomas',
    'address': '9402 Gilbert Springs Suite 617\nAngelafort, AS 14866',
    'text': 'Not key give. Mission generation again instead discussion enough sing. Yourself man result bank agree thought.\nAnimal by prevent ability degree computer least. Serious product mind property tree she.',
    'email': 'ryan05@example.org',
    'phone_number': '823.979.7139x57312',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Robin Gonzalez',
    'Ariel Young',
    'Katherine Perez',
    'Holly Baird',
    'James Ward',
    'Kendra Thomas',
    'Christopher Klein',
    'Heather Mann',
],
    'json': {
    'name': 'Michael Long',
    'address': '100 Danielle Junctions\nWhitneytown, MI 45040',
},
    'key48336': 'value76726',
    'key34737': 'value73978',
    'key13345': 'value88301',
    'key28233': 'value63777',
    'key71429': 'value71084',
    'key52098': 'value82086',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Joshua Bryant',
    'address': '8969 Parker Crescent Apt. 914\nMorrowport, MS 05048',
    'text': 'Anyone almost his both local size. Throughout character type above weight develop. Hundred from hard trouble growth get of large. Size least street education close occur.',
    'email': 'caleb09@example.com',
    'phone_number': '862.689.5566',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brett Adams',
    'Jacob Johnston',
    'Sarah Jacobs DDS',
    'Kevin Johnson Jr.',
    'Terrence Rowe',
    'April Lopez',
    'Clarence Walker',
    'Taylor Lara',
],
    'json': {
    'name': 'Brittney Schroeder',
    'address': 'PSC 0485, Box 6577\nAPO AP 80485',
},
    'key51437': 'value84648',
    'key78290': 'value55938',
    'key88092': 'value49788',
    'key99066': 'value70564',
    'key14714': 'value2842',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Ronald Carter',
    'address': '1727 Amber Valleys\nEast Veronica, PR 79750',
    'text': 'Tough energy fund none voice. Positive plan space doctor trade billion create.',
    'email': 'mullenjuan@example.net',
    'phone_number': '001-305-997-7200x73443',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Janet Brock',
    'John Bolton',
    'Caitlin Smith',
    'Mark Campbell',
    'Scott Obrien',
    'Mike Clark',
    'Martin Knight',
    'Debra Soto',
],
    'json': {
    'name': 'Brenda Valenzuela',
    'address': '90872 Matthew Keys\nThomasstad, AS 02279',
},
    'key2950': 'value54117',
    'key86882': 'value57734',
    'key46749': 'value43751',
    'key93563': 'value74828',
    'key26247': 'value75792',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Jennifer Lin',
    'address': '75794 Weaver Union\nAlexhaven, VI 50260',
    'text': 'Onto though several goal administration. Continue often before employee task. Worry party bag group.\nCity economic several name cost shake growth thank. Site always into member.',
    'email': 'umurphy@example.net',
    'phone_number': '365.775.2031',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Rangel',
    'Abigail Lopez',
    'Evan White',
    'Juan Martinez',
],
    'json': {
    'name': 'Jessica Smith',
    'address': '216 Todd Spring Apt. 849\nWest Michael, MN 84236',
},
    'key20798': 'value76113',
    'key80276': 'value85412',
    'key52340': 'value31636',
    'key651': 'value76355',
    'key57633': 'value82064',
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
    'RequestId': 'a4214113-62ef-11f0-ba46-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_02_883274nixaUvuF',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-2]_1752744183.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl1281021752744183Json()
    test.run_tests()
