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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-2]_1752744125_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-2]_1752744125.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl1281021752744125Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-2]_1752744125.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-2]_1752744125.json"
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
    'RequestId': '817bb3e6-62ef-11f0-936c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_04_755778eZCcRGch',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'vector',
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
    'RequestId': '8182997a-62ef-11f0-b225-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_04_755778eZCcRGch',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jennifer Suarez MD',
    'address': 'PSC 1845, Box 8042\nAPO AE 41640',
    'text': 'Play peace with begin. Pay like how collection yet according.\nLike any and pass. Try ground ball.\nGirl carry now project assume note. When cost together picture.',
    'email': 'ososa@example.net',
    'phone_number': '8289735660',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Ewing',
    'Daniel Kaufman',
    'Eric Hernandez',
    'Dustin Frederick',
    'Edward Valdez',
    'Bianca Brown',
    'Kimberly Brown',
    'Ricardo Gilbert',
],
    'json': {
    'name': 'Margaret Armstrong',
    'address': '527 Johnny Land\nLake David, AZ 28742',
},
    'key46841': 'value6703',
    'key72373': 'value42483',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Joshua Williams',
    'address': '5429 Michael Forge Apt. 838\nLake Richard, PA 44197',
    'text': 'Serve focus hard successful. Day into every record explain take avoid.\nUntil series evening now these line. Agreement Congress stand behind just price western.',
    'email': 'douglaswarren@example.com',
    'phone_number': '001-463-525-8663x581',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kara Lewis',
    'Diane Hamilton',
    'Kara Wagner',
],
    'json': {
    'name': 'Donald Byrd',
    'address': '86568 Chapman Center Suite 201\nNew Kevinfort, PA 28012',
},
    'key95707': 'value55771',
    'key79430': 'value59367',
    'key41920': 'value72597',
    'key45300': 'value83410',
    'key87356': 'value1722',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Mariah Thomas',
    'address': '56749 Bailey Mission\nTammyfort, NM 15765',
    'text': 'Any news then between subject. Card well scientist. Term stuff man responsibility cut dinner.\nNote much option man. Use it image matter.',
    'email': 'richard86@example.com',
    'phone_number': '646-662-3158',
    'array_int_dynamic': [
    43324,
],
    'array_varchar_dynamic': [
    'Jose Graham',
],
    'json': {
    'name': 'John Miller',
    'address': '349 Justin Mews\nWest Lisa, WI 91797',
},
    'key94283': 'value84991',
    'key90986': 'value43361',
    'key96813': 'value4009',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Wayne Hays',
    'address': '07053 Wright Spurs\nTammyland, NM 53404',
    'text': 'Wear throughout get woman behavior. Study huge TV after. Eye live threat she. Card fire room discover.\nOthers responsibility learn account staff. Black word federal history crime win.',
    'email': 'jon54@example.com',
    'phone_number': '881.673.9790x1976',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Rodriguez',
    'Michael Medina',
],
    'json': {
    'name': 'Kimberly Caldwell',
    'address': '02297 Isaac Gardens Apt. 951\nJerryview, CT 99531',
},
    'key75664': 'value63389',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'George Baldwin',
    'address': 'PSC 9605, Box 0703\nAPO AA 58396',
    'text': 'Investment education international head ask. Just government stage much describe cause study. Heavy everything break.',
    'email': 'tgardner@example.net',
    'phone_number': '558-451-1297x157',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Thompson',
    'Ana Jones',
    'Todd Rodriguez',
    'Sarah Martinez',
    'Anthony Olson',
],
    'json': {
    'name': 'Rodney Perez',
    'address': '49957 Jacobson Place Suite 007\nLake Leah, NV 68343',
},
    'key99038': 'value19997',
    'key67814': 'value76112',
    'key58701': 'value52801',
    'key98977': 'value87196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Sara Bryant',
    'address': '882 Roman Shoals Suite 726\nBarreraport, WY 14587',
    'text': 'Sort her resource program player do. Mouth expert great. All wide outside piece now whether test. Travel firm join few.',
    'email': 'kimberlybrown@example.net',
    'phone_number': '+1-286-447-7743x80772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Holly Rios',
    'Kristina Bradford',
    'Christine Garcia',
    'Tanner Li',
    'Troy Murphy',
    'John Aguilar',
    'Frank Johnson',
    'Jodi Williams',
    'Jessica Caldwell',
    'Tracy Roberts',
],
    'json': {
    'name': 'Alexandra Robinson',
    'address': '64492 Velasquez Tunnel Suite 574\nLake Madison, PA 49895',
},
    'key21906': 'value42037',
    'key15177': 'value42745',
    'key50604': 'value24207',
    'key99317': 'value83687',
    'key82113': 'value38113',
    'key11111': 'value27513',
    'key69104': 'value15927',
    'key69006': 'value35674',
    'key27569': 'value49355',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Benjamin Johnson',
    'address': 'PSC 6742, Box 9226\nAPO AE 59923',
    'text': 'Perform technology property include performance according. Wrong risk let.\nBar reality enough me evening yeah toward. Type plan upon stock recognize. And believe country so responsibility.',
    'email': 'sweeneyblake@example.net',
    'phone_number': '(719)743-6575',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Brooks',
    'Laura Jones',
    'Jody Anderson',
    'Gabrielle Everett',
],
    'json': {
    'name': 'Paul Williams',
    'address': '96547 Shaw Stream\nCarneyfort, WV 72794',
},
    'key42251': 'value7908',
    'key35954': 'value65025',
    'key67750': 'value13837',
    'key38138': 'value42200',
    'key33721': 'value52003',
    'key83190': 'value8526',
    'key37542': 'value79997',
    'key54351': 'value45052',
    'key88714': 'value64418',
    'key45619': 'value97330',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Megan Dillon',
    'address': '1291 Christopher Turnpike Apt. 915\nSouth Amber, TN 02455',
    'text': 'Send section glass add bank. True city church.\nMethod program fund rather learn receive traditional. American prevent north pull read off as key. Machine big question bring our.',
    'email': 'john62@example.com',
    'phone_number': '486.999.5873x934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Miranda',
    'Donna Ramirez',
    'Mr. Cody Best',
],
    'json': {
    'name': 'Cynthia Jones',
    'address': '60685 Rivera Junctions\nEast Peterchester, KS 21201',
},
    'key94059': 'value27266',
    'key38427': 'value3269',
    'key1139': 'value32671',
    'key79706': 'value90554',
    'key95803': 'value47407',
    'key95454': 'value82753',
    'key18560': 'value57709',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Lisa Ingram',
    'address': '798 Graham Spurs Apt. 708\nPetersonmouth, DE 18676',
    'text': 'Discover young rule those film sort popular. Example charge it compare learn method.',
    'email': 'virginiawhite@example.net',
    'phone_number': '(641)430-2757',
    'array_int_dynamic': [
    41019,
],
    'array_varchar_dynamic': [
    'Taylor Bass',
    'Marisa Perry',
    'David Nolan',
    'Luis Perry',
    'Stephanie Moore',
    'Karen Kline',
    'Lisa Mccarty',
],
    'json': {
    'name': 'Cassandra Price',
    'address': '81042 Cynthia Avenue Suite 963\nPort Robertside, NJ 28088',
},
    'key74930': 'value23961',
    'key51689': 'value3602',
    'key70992': 'value68230',
    'key31576': 'value71699',
    'key15868': 'value57708',
    'key13247': 'value4049',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Shawn Branch',
    'address': 'USCGC Gross\nFPO AP 73010',
    'text': 'Language guess trouble enjoy if policy good. Listen activity later operation somebody option young. Thousand pattern and director local feeling.\nNight who ground amount wear. Call write memory story.',
    'email': 'stephanie25@example.net',
    'phone_number': '+1-200-519-8031x36861',
    'array_int_dynamic': [
    56184,
],
    'array_varchar_dynamic': [
    'Eric Malone',
    'Darin Stout',
    'Aaron Lee',
],
    'json': {
    'name': 'Mario Burke',
    'address': 'USNS Cabrera\nFPO AA 06755',
},
    'key48519': 'value86111',
    'key26531': 'value8241',
    'key25933': 'value91464',
    'key65210': 'value78683',
    'key80562': 'value9587',
    'key7542': 'value45214',
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
    'RequestId': '817bb3e6-62ef-11f0-936c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_04_755778eZCcRGch',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-10-2]_1752744125.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl1281021752744125Json()
    test.run_tests()
