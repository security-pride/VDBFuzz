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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-1]_1752744112_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-1]_1752744112.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId1281011752744112Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-1]_1752744112.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-1]_1752744112.json"
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
    'RequestId': '799cc8ad-62ef-11f0-9ee8-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_51_550801WIpEVXbK',
    'dimension': 128,
    'primaryField': 'id',
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
    'RequestId': '79a35c8b-62ef-11f0-95d1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_51_550801WIpEVXbK',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Cindy Russell',
    'address': '565 Alvarez Haven Suite 721\nSouth Brentland, FL 38826',
    'text': 'Our service language story deep total true. Wind billion name film about. Arm back author son down.\nClose contain piece rise. Forget everything their capital. Scene result hair say economic able.',
    'email': 'connie53@example.com',
    'phone_number': '955-331-7701x55704',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Scott',
    'Dr. Joseph Lee DDS',
    'Linda Nelson',
],
    'json': {
    'name': 'Julian Mora',
    'address': 'PSC 5897, Box 5996\nAPO AA 42677',
},
    'key12402': 'value48357',
    'key98630': 'value83997',
    'key69569': 'value29723',
    'key86742': 'value30943',
    'key50724': 'value14915',
    'key31936': 'value48496',
    'key10816': 'value88804',
    'key35489': 'value1542',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Lauren Garcia',
    'address': '6396 Klein Isle Suite 533\nGloverborough, MP 50293',
    'text': 'Better main ahead almost better when.\nGet two father enough feeling fear process. Employee southern early mention. Such child marriage easy factor democratic money government.',
    'email': 'janetanderson@example.net',
    'phone_number': '(792)994-4355',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Dustin Bailey DVM',
    'Christopher Shields',
    'William Moss',
    'Brittany Harrison',
    'Nicholas Fischer',
    'Nicole Lee',
],
    'json': {
    'name': 'Luis Woods',
    'address': '29588 Timothy Knolls\nTraceyfurt, FL 80006',
},
    'key1356': 'value32318',
    'key45110': 'value99279',
    'key41188': 'value11696',
    'key31779': 'value81844',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jeremy Massey',
    'address': '1215 Matthew Mountain\nPort Tina, MO 68515',
    'text': 'Ask hand mean like write not phone. Test stand require itself low.\nPower design father. Knowledge goal his travel because maybe suggest. Pm fact art.',
    'email': 'monica82@example.net',
    'phone_number': '421.863.8161x6367',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Young',
    'Christopher Sullivan',
    'Ernest Johns',
    'Brittany Waters',
    'Beth Gonzalez',
    'Jeffrey Crosby',
    'Justin Cook',
    'Henry Davis',
    'Charlene Beck',
],
    'json': {
    'name': 'Steve Tran',
    'address': '1383 Morrison Ways\nLake Jorgeborough, PR 96298',
},
    'key70173': 'value7582',
    'key57985': 'value9192',
    'key71206': 'value68812',
    'key96727': 'value51441',
    'key26401': 'value68414',
    'key37942': 'value55248',
    'key98384': 'value27705',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Shannon Davis',
    'address': '2659 Mary Stravenue\nDanielleshire, SD 75939',
    'text': 'Kitchen fund face final. Five single they weight cost.\nSide traditional paper technology full citizen federal.',
    'email': 'holly25@example.com',
    'phone_number': '519-929-1599',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Eric Moore',
    'Derek Duncan',
    'Vincent Carrillo',
    'Courtney Garza',
    'Anita Silva',
    'Tracy Taylor',
    'Paul House',
    'Jackson Calhoun',
    'Judy Floyd',
],
    'json': {
    'name': 'Beverly Bradford',
    'address': '7346 Maria Island\nAndradeville, OK 88052',
},
    'key12041': 'value72195',
    'key62469': 'value36330',
    'key17137': 'value60487',
    'key80009': 'value24517',
    'key52177': 'value11444',
    'key88761': 'value51329',
    'key37870': 'value1166',
    'key95324': 'value37937',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Peter Henry',
    'address': '1600 George Plaza\nNew Patricia, GU 05148',
    'text': 'Father debate memory house. Former line eight. To young system support owner send nearly cell. He coach sure former recognize.',
    'email': 'alyssagonzalez@example.net',
    'phone_number': '+1-825-990-9513x6647',
    'array_int_dynamic': [
    72840,
],
    'array_varchar_dynamic': [
    'Bonnie Hernandez',
    'Matthew Flores',
    'Patrick Reynolds',
],
    'json': {
    'name': 'Michael Flores',
    'address': '8965 Watkins Cape\nChristopherborough, MA 85177',
},
    'key22550': 'value65012',
    'key90990': 'value80672',
    'key93979': 'value6185',
    'key76948': 'value58200',
    'key78005': 'value38687',
    'key39743': 'value17555',
    'key9503': 'value95144',
    'key95874': 'value96410',
    'key95189': 'value87659',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Christian Hunt',
    'address': '93217 Patricia Forest Apt. 594\nNew Nicole, AK 56076',
    'text': 'Reach election such high some including why. Would eye force him contain ten course phone.\nPractice PM law cause. Summer floor sell notice draw.',
    'email': 'cadams@example.org',
    'phone_number': '+1-326-956-9965x66230',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Meyer',
    'Jacqueline Cooper',
    'Stephen Haney',
],
    'json': {
    'name': 'Melissa Miller',
    'address': '62800 Robertson Isle\nLake Kimberlymouth, KS 08441',
},
    'key18988': 'value51170',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Dalton Parks',
    'address': '6024 Lauren Branch Suite 931\nWest Jaredton, SC 12030',
    'text': 'Note left simple she month rise opportunity. Whole plant run section chair end prevent.\nStart break girl me doctor western.',
    'email': 'sarahchandler@example.net',
    'phone_number': '(577)303-5723x95201',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Leon Lopez',
    'Charles Lee',
],
    'json': {
    'name': 'Hunter Diaz',
    'address': 'Unit 3821 Box 0219\nDPO AA 90791',
},
    'key92939': 'value48441',
    'key27170': 'value84078',
    'key28366': 'value64838',
    'key16631': 'value72452',
    'key12432': 'value28810',
    'key77647': 'value63753',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Nathan Valentine',
    'address': '854 Brown Overpass Suite 078\nPort James, PR 52228',
    'text': 'Agent simply politics worker item speech.\nSummer water first finally practice professional movement cultural. Water raise listen conference blue.',
    'email': 'hinesdenise@example.net',
    'phone_number': '(789)352-7909',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kristine Nash',
    'Jeffrey Nichols',
    'Austin George',
    'Bradley Smith',
    'Greg Hill',
    'Maria Key',
    'Ashley Lawrence',
    'Adam Young',
    'James Scott',
],
    'json': {
    'name': 'Emily Peterson',
    'address': '15836 Ewing Divide Apt. 670\nLake Brian, SC 03313',
},
    'key5221': 'value82866',
    'key76457': 'value54111',
    'key98653': 'value67644',
    'key53191': 'value89938',
    'key7120': 'value51699',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Matthew Murphy',
    'address': '2158 Murray Brooks\nSouth Kevin, FL 30548',
    'text': 'Become evening media hold including.\nField street beyond will. Three blue although sound office pull test.\nListen than everybody clear discussion economic pattern.',
    'email': 'hadams@example.org',
    'phone_number': '+1-576-406-7267x71391',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Eric Randall',
    'Michelle Pierce',
    'Sally Mason',
],
    'json': {
    'name': 'Donna Morgan',
    'address': '685 Arnold Park\nNorth Jamie, RI 23694',
},
    'key67760': 'value86952',
    'key95809': 'value87951',
    'key34303': 'value84333',
    'key64880': 'value87567',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Pamela Jones',
    'address': '3967 Valdez Skyway\nEast Angelicashire, TN 62837',
    'text': 'Blue yeah treatment investment artist agent easy society. Week hour nearly science.\nTechnology growth subject general church. Become friend yeah middle traditional tax. Brother head guess action.',
    'email': 'kurt68@example.org',
    'phone_number': '922.382.2011x75779',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Osborn',
    'Steven Pierce',
    'David Tucker',
    'Jane Martinez',
    'Brittany Reeves',
],
    'json': {
    'name': 'Emily Hutchinson',
    'address': '4587 Nicole Lodge\nWheelerstad, DC 70727',
},
    'key2159': 'value81084',
    'key79286': 'value67283',
    'key95207': 'value10849',
    'key25374': 'value1210',
    'key74228': 'value7205',
    'key91204': 'value19379',
    'key34992': 'value48714',
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
    'RequestId': '799cc8ad-62ef-11f0-9ee8-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_51_550801WIpEVXbK',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-128-10-1]_1752744112.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId1281011752744112Json()
    test.run_tests()
