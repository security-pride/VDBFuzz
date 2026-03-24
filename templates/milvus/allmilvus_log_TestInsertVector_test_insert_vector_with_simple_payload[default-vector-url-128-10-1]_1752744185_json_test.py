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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-1]_1752744185_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-1]_1752744185.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl1281011752744185Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-1]_1752744185.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-1]_1752744185.json"
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
    'RequestId': 'a4ca3460-62ef-11f0-b5b3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_03_990501gQdzEqsC',
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
    'RequestId': 'a4d13072-62ef-11f0-960c-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_03_990501gQdzEqsC',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Michelle Smith',
    'address': '42491 Paul Trafficway Suite 538\nJoshuastad, MH 33935',
    'text': 'Accept sound worry now task art drive. Concern network own detail future.\nImprove door leg throughout. Other issue job.',
    'email': 'dkennedy@example.com',
    'phone_number': '629.919.1612x632',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Hernandez',
    'Jeffrey Lopez',
    'Michael Avila',
],
    'json': {
    'name': 'Ethan Wright',
    'address': '91479 Thomas Locks\nWest Connie, VA 97064',
},
    'key84618': 'value17017',
    'key67410': 'value49096',
    'key63881': 'value76277',
    'key92275': 'value83733',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Phillip Hall PhD',
    'address': '54415 Thompson Lights\nChavezmouth, WY 05177',
    'text': 'Understand wait attack again during. Exactly general meet then might. Walk will week marriage matter meet.\nAlthough girl standard ready actually reveal. Entire task keep teach himself.',
    'email': 'yatessara@example.org',
    'phone_number': '4258039386',
    'array_int_dynamic': [
    52875,
],
    'array_varchar_dynamic': [
    'Sarah Day',
    'Renee White',
    'Robert Greer',
    'Justin Koch',
    'James Collins',
    'Alexander Vasquez',
    'Scott Rasmussen',
    'Christopher Ball',
    'Nathan Martin',
    'Craig Khan',
],
    'json': {
    'name': 'Rebecca Fisher',
    'address': '7374 Rachel Fork Suite 460\nNew Thomas, KY 92577',
},
    'key94926': 'value4569',
    'key3517': 'value44374',
    'key5471': 'value23766',
    'key38357': 'value8622',
    'key39561': 'value70600',
    'key45532': 'value10615',
    'key32674': 'value18176',
    'key4934': 'value52945',
    'key71037': 'value69367',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Oscar White',
    'address': '3338 Adkins Port Apt. 618\nEast Matthewborough, AZ 91379',
    'text': 'Program audience half where dinner many certainly. Song scientist difference what. Night group wall hard similar heavy.',
    'email': 'velliott@example.org',
    'phone_number': '(285)759-6136',
    'array_int_dynamic': [
    4914,
],
    'array_varchar_dynamic': [
    'Donna House',
    'Carlos Malone',
    'Nicole Morgan',
    'Kyle George',
    'Joseph Porter',
    'Christopher Gentry',
    'Dr. Michael Lopez',
    'Taylor Lindsey',
    'Eric Dunn',
    'Lauren Gilmore',
],
    'json': {
    'name': 'Amanda Robertson',
    'address': '28276 Carter Knoll Suite 513\nPowersmouth, NJ 66580',
},
    'key17871': 'value10184',
    'key87317': 'value58914',
    'key46247': 'value62260',
    'key45679': 'value7262',
    'key5099': 'value33693',
    'key52167': 'value58243',
    'key9474': 'value61915',
    'key93925': 'value16888',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Annette Chen',
    'address': '648 Dominique Neck Suite 487\nTuckerberg, CA 85018',
    'text': 'Age hundred consumer. Question but walk everything.\nStandard music training. Special value store analysis try prevent through. Trouble east bed behavior seven.',
    'email': 'bernardstephanie@example.org',
    'phone_number': '317.770.1081x24220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Wall',
    'Shannon Hanson',
],
    'json': {
    'name': 'Timothy Wright',
    'address': '81476 Katrina Hill Suite 459\nLake Jerrytown, CO 30903',
},
    'key78977': 'value6499',
    'key3467': 'value48099',
    'key98225': 'value40891',
    'key21272': 'value90552',
    'key16485': 'value17579',
    'key3135': 'value87284',
    'key45506': 'value78603',
    'key70943': 'value42152',
    'key94830': 'value51533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Aaron Fisher',
    'address': '5995 Thomas Village Apt. 763\nEast Garrettland, OR 97392',
    'text': 'From edge party may. Everything spring degree leg home get. Option decade contain.',
    'email': 'cooperscott@example.net',
    'phone_number': '412-462-4787x134',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Bradley',
],
    'json': {
    'name': 'Christine Cruz',
    'address': '96953 Williams Walks Suite 365\nMaldonadomouth, VA 11419',
},
    'key92422': 'value70239',
    'key86035': 'value36577',
    'key18205': 'value78752',
    'key48649': 'value31920',
    'key3254': 'value14850',
    'key54747': 'value36601',
    'key48809': 'value197',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Kristen Key',
    'address': '7992 Boone Skyway Suite 191\nLake Scottview, AS 99201',
    'text': 'Where reduce upon. Trial fly company another environmental.\nSecond write design foreign organization enough town assume. Agreement build brother late address democratic now.',
    'email': 'christopherhoward@example.org',
    'phone_number': '(680)547-5224',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Angela Randall DDS',
    'Meredith Decker',
    'Michael Mcguire',
    'Robin Garrison',
    'Michael King',
    'Blake Duke',
    'Kenneth Cruz',
    'Tiffany Diaz',
    'Brandi Wang',
    'Stacy Burgess',
],
    'json': {
    'name': 'Adrienne Jones',
    'address': '219 Rodney Mount Suite 944\nNorth George, GU 41215',
},
    'key49021': 'value57244',
    'key473': 'value67231',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Thomas Hicks',
    'address': '233 Martin Flat Suite 920\nMorrowshire, UT 42682',
    'text': 'Speak task trip generation recognize. Health low whether take magazine yourself. Candidate reduce huge.\nNational between participant fine. Hundred office research.',
    'email': 'josephwu@example.net',
    'phone_number': '616.631.6538x334',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Moore',
    'Kristin Gallegos',
    'Kathy Schmidt',
    'Carlos Davis',
],
    'json': {
    'name': 'Ronnie Wilson',
    'address': '61265 Huynh Rest\nEast Michael, FL 39664',
},
    'key62835': 'value9624',
    'key37286': 'value67674',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Cynthia Garcia',
    'address': '152 Michael Rest\nWest David, TX 88265',
    'text': 'Choose debate production subject government. Consider start fund change yeah me view feel. Rich cell again quality already.',
    'email': 'marissaturner@example.org',
    'phone_number': '733-532-2713x301',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Neal',
    'Kenneth Johnson',
    'Patrick Rodriguez',
    'Jessica Keller',
    'Mark Gomez',
    'Kevin Wilson',
    'Nicole Brooks',
    'Katie Herrera',
    'Helen Martinez',
    'Jasmine Lopez',
],
    'json': {
    'name': 'Nicole Price',
    'address': '76907 Tiffany Unions\nEast Meaganbury, KS 99182',
},
    'key78200': 'value21683',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Sara Garner',
    'address': '5679 Vance Freeway Apt. 695\nJenniferport, OR 19162',
    'text': 'Personal to store manage capital himself. Itself ago important debate home control. Administration seem society common generation before.',
    'email': 'emily32@example.com',
    'phone_number': '748-230-8105x540',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Lewis',
    'April Wood',
],
    'json': {
    'name': 'Paula Reynolds',
    'address': '98870 Jackson Run\nMccannborough, HI 45332',
},
    'key47546': 'value42724',
    'key26167': 'value70253',
    'key98505': 'value28040',
    'key92727': 'value65050',
    'key53926': 'value50628',
    'key76528': 'value95737',
    'key27099': 'value40917',
    'key94651': 'value8191',
    'key27543': 'value95403',
    'key13362': 'value53529',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Brittany Davis',
    'address': '6456 Brianna Shore Apt. 121\nNew Kayla, CA 86810',
    'text': 'Too away course us scene.\nYoung language change happen speech for apply. Fight can add student eat plan everything. Defense civil explain voice.',
    'email': 'erica36@example.net',
    'phone_number': '953.340.8139',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Adrian Smith',
    'James Chandler',
    'Timothy Williams',
    'Brian Burke',
    'Mason Perez',
],
    'json': {
    'name': 'David Perkins',
    'address': '087 Gibson Pike\nSmithmouth, IL 78479',
},
    'key25461': 'value21605',
    'key74066': 'value12582',
    'key4853': 'value98733',
    'key13417': 'value35616',
    'key58058': 'value61109',
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
    'RequestId': 'a4ca3460-62ef-11f0-b5b3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_03_990501gQdzEqsC',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-10-1]_1752744185.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl1281011752744185Json()
    test.run_tests()
