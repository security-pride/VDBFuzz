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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-1]_1752744148_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-1]_1752744148.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl321011752744148Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-1]_1752744148.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-1]_1752744148.json"
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
    'RequestId': '8f2107e3-62ef-11f0-9618-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_27_649665HEujjMut',
    'dimension': 32,
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
    'RequestId': '8f2d9cc3-62ef-11f0-81e5-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_27_649665HEujjMut',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Ashley West',
    'address': '50220 Sullivan Ford Suite 358\nKellyburgh, WV 12210',
    'text': 'Sit response play before. Help thought behind similar item. Join common our relate.\nDiscussion upon thing benefit court different. Simply government boy who. Pattern tell rule car.',
    'email': 'alexander31@example.com',
    'phone_number': '+1-268-250-5846x95727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christina Holland',
    'Joseph Nunez',
    'Kelsey Nguyen',
    'William Perez',
    'James Caldwell',
    'Michael Johnson',
    'Joanna Hansen',
    'David Bennett',
],
    'json': {
    'name': 'Brandon Bradshaw',
    'address': '3562 Nicole Prairie Apt. 912\nTerribury, VT 39097',
},
    'key12670': 'value22795',
    'key74756': 'value10636',
    'key58253': 'value2447',
    'key11878': 'value7028',
    'key1775': 'value32340',
    'key70954': 'value64766',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Gerald Weeks',
    'address': '79417 Perry Freeway\nDavidchester, WY 27736',
    'text': 'Democrat chair continue require may deal music. Improve deal final race. Yourself age Mr interest.',
    'email': 'howardjoan@example.org',
    'phone_number': '711-600-6757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Lee',
    'Stacey Lewis',
    'David Higgins',
    'Walter Walker',
    'Leonard Lyons',
    'Lauren Moore',
    'Laura Ochoa',
    'Joseph Willis',
    'Diane Warren',
    'Eric Fischer',
],
    'json': {
    'name': 'Patrick Phelps',
    'address': '14410 Kyle Lodge Apt. 871\nEast Katrina, OR 40401',
},
    'key23840': 'value68055',
    'key4785': 'value10574',
    'key80855': 'value24653',
    'key24359': 'value84358',
    'key89979': 'value39389',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Diane Harrington',
    'address': '9310 Sanchez Rest\nMichaelfort, IA 04493',
    'text': 'Collection song race whether. Another girl natural claim decide lead thought item.\nResponsibility nothing pick camera computer base none. Owner smile trial wide law front respond.',
    'email': 'yphillips@example.org',
    'phone_number': '(331)647-5599x090',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Swanson',
    'Harry Santos',
    'Patricia Smith',
    'Erica Erickson',
    'Laura Lambert',
    'Tracy Ellis',
],
    'json': {
    'name': 'Michael Franco',
    'address': '21550 Hill Junctions\nLake Shawn, MA 78487',
},
    'key54578': 'value58651',
    'key45982': 'value20155',
    'key92494': 'value76180',
    'key53324': 'value15797',
    'key99738': 'value7980',
    'key60120': 'value45977',
    'key39409': 'value98170',
    'key39306': 'value43426',
    'key42910': 'value33283',
    'key84749': 'value58131',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Joseph Perez',
    'address': '9463 Rasmussen Stravenue\nCarlmouth, MD 29086',
    'text': 'Part Republican successful western onto. Unit budget fall. Man moment environment age reflect nature course.',
    'email': 'cristinafriedman@example.net',
    'phone_number': '+1-856-776-9377x09636',
    'array_int_dynamic': [
    51346,
],
    'array_varchar_dynamic': [
    'Michael Turner',
    'Kristen Jarvis',
    'Sandra Anderson',
    'Lauren Walker',
    'Victoria Moreno MD',
    'Mary Frank',
    'Tammy Harding',
    'Clinton Smith',
    'Amber Brown',
],
    'json': {
    'name': 'George Armstrong',
    'address': '947 Kristin Knoll\nNorth Josephhaven, ID 01148',
},
    'key661': 'value49713',
    'key42112': 'value11195',
    'key58086': 'value28464',
    'key95598': 'value1477',
    'key69983': 'value33572',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Jessica Richardson',
    'address': '821 Erin Knoll\nGeorgemouth, ID 32860',
    'text': 'Do worry finally record none. Mind store station race deal natural. Light town bad daughter.\nMake police challenge. Necessary include little. Official work beat explain shoulder above.',
    'email': 'christophernolan@example.org',
    'phone_number': '842-864-8322x379',
    'array_int_dynamic': [
    52964,
],
    'array_varchar_dynamic': [
    'Jose Gilmore',
    'Leah Ramos',
    'Mark Fuentes',
],
    'json': {
    'name': 'Amanda White',
    'address': '19499 Travis Common Suite 919\nDestinytown, HI 46546',
},
    'key76851': 'value17419',
    'key71891': 'value42935',
    'key63057': 'value7833',
    'key76672': 'value52665',
    'key71449': 'value6457',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Ricky Duran',
    'address': '90456 Clark Views\nNorth Deniseton, CO 54782',
    'text': 'People offer hair. Light consumer force number budget. Only matter road purpose. Direction under happen international back charge.',
    'email': 'ashley25@example.net',
    'phone_number': '700.801.7323x350',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Cortez',
    'Crystal Kennedy',
    'Patrick Castro',
    'Natasha Medina',
    'Justin Mitchell',
    'Lance Bradford',
    'Courtney Diaz',
],
    'json': {
    'name': 'Jamie Fuller',
    'address': '906 Jessica Station Suite 012\nMichaelview, MA 78156',
},
    'key55248': 'value92998',
    'key67449': 'value8505',
    'key12755': 'value4886',
    'key33529': 'value9876',
    'key26811': 'value54335',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Jessica Wagner',
    'address': '634 Adams Landing Apt. 259\nEast Timothyfort, MD 70798',
    'text': 'Ok on change become character individual point seven. Memory home season environmental majority walk.\nPosition daughter staff hundred guess. Generation light process represent whose receive.',
    'email': 'natalie32@example.com',
    'phone_number': '683-694-0805',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Adam Walker',
    'Travis Wilson',
    'Robert Osborne',
    'Ashley Dawson',
    'Sabrina Jones',
],
    'json': {
    'name': 'Robin Bullock',
    'address': '7038 Harris Crossing Apt. 556\nHarriston, MN 15498',
},
    'key86221': 'value54592',
    'key20294': 'value11678',
    'key84408': 'value14659',
    'key36074': 'value56151',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Vanessa Chapman',
    'address': '21942 Pineda Hollow\nEast Jacqueline, IN 25745',
    'text': 'Heavy form dinner work your enjoy evening. Book fast cost every western about theory.\nBit attorney drug available leader mission expert. Mr reflect example business near future where.',
    'email': 'conwaywilliam@example.com',
    'phone_number': '(581)327-1326',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Green',
    'Christopher Todd',
    'Ann Murphy',
    'Anthony Bryant',
    'John Stone',
    'Loretta Evans',
    'Lisa Wilkinson',
    'Eric Owen',
    'Shaun Taylor',
],
    'json': {
    'name': 'Brian Lee',
    'address': 'USNS Foster\nFPO AP 50346',
},
    'key80415': 'value47211',
    'key85403': 'value18330',
    'key7575': 'value56830',
    'key25264': 'value91133',
    'key709': 'value84231',
    'key8761': 'value7419',
    'key52152': 'value94620',
    'key49500': 'value54226',
    'key59685': 'value34212',
    'key72338': 'value41087',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Ronald Ruiz',
    'address': 'Unit 5857 Box 1094\nDPO AE 71571',
    'text': 'Create information cost not short clear. Share whatever prepare wait environment. Stage sense get serious.\nSea have blood road whether price somebody. Size employee see wide director.',
    'email': 'gberry@example.net',
    'phone_number': '219.860.9434x3558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jack Miller',
    'Michelle Richardson',
    'Scott Haley',
],
    'json': {
    'name': 'Mrs. Toni Boyle MD',
    'address': '3860 Lisa Creek Suite 431\nOliverport, ND 80367',
},
    'key97158': 'value47110',
    'key30245': 'value59658',
    'key33984': 'value14852',
    'key54094': 'value63659',
    'key11144': 'value7095',
    'key506': 'value41666',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Tyrone Davis',
    'address': '49607 Sparks Groves Suite 165\nNorth Kevinmouth, IL 89178',
    'text': 'Road always worker arm. Black wrong medical provide situation.\nWriter word certain recently. Generation shoulder pull whole yard. Effect rock democratic reveal finish station station.',
    'email': 'sotomichael@example.net',
    'phone_number': '(903)405-2255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Adams',
    'Kevin Jackson',
    'Gregory Hamilton',
],
    'json': {
    'name': 'Robert Wilson',
    'address': '399 Susan Avenue Suite 595\nNorth Danielburgh, NV 15497',
},
    'key28848': 'value7574',
    'key96421': 'value28365',
    'key31187': 'value92998',
    'key8575': 'value2852',
    'key52874': 'value56555',
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
    'RequestId': '8f2107e3-62ef-11f0-9618-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_27_649665HEujjMut',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-1]_1752744148.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl321011752744148Json()
    test.run_tests()
