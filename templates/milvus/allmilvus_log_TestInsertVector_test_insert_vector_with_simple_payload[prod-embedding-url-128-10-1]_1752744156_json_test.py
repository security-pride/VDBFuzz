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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-1]_1752744156_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-1]_1752744156.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl1281011752744156Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-1]_1752744156.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-1]_1752744156.json"
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
    'RequestId': '93b2d875-62ef-11f0-96c1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_35_316156HWcbZrRO',
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
    'RequestId': '93ba8f04-62ef-11f0-876e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_35_316156HWcbZrRO',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'William Ramos',
    'address': 'Unit 8676 Box 3913\nDPO AP 46865',
    'text': 'Campaign issue drug majority her. Direction everybody training computer late catch. Policy lay collection voice turn image.\nDemocratic case ok report over guy. Million soldier suggest.',
    'email': 'ssimmons@example.com',
    'phone_number': '516.403.6219x14832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Samantha Johnson MD',
    'Kristina Allen',
    'Shannon Martinez',
    'Travis Sellers',
    'Larry Smith',
    'Sarah Riley',
    'Tyler James',
    'Gilbert Greer',
    'Vincent Coleman',
],
    'json': {
    'name': 'Leah Stewart',
    'address': 'PSC 2480, Box 0337\nAPO AP 79058',
},
    'key16852': 'value59915',
    'key99038': 'value8952',
    'key10616': 'value16707',
    'key6063': 'value58877',
    'key55676': 'value19760',
    'key56665': 'value82034',
    'key20272': 'value93333',
    'key15930': 'value33869',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Christina Henderson',
    'address': '86556 Larry Mountains\nSouth Gregshire, VI 74374',
    'text': 'Practice like cost notice. Science such run easy young expect. Quickly shake case early pattern fish. Also church difference next subject through.',
    'email': 'dunnarthur@example.net',
    'phone_number': '688-727-7628x148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Gray',
    'Billy Ford',
    'Christopher Johnson',
    'Bryan Mitchell',
    'William Smith',
    'Robert Werner',
    'Patrick Andrade',
    'Sarah Green',
    'John Palmer',
],
    'json': {
    'name': 'Sean Dunn DDS',
    'address': '6072 Mary Point Apt. 180\nSharontown, MH 72401',
},
    'key23586': 'value29114',
    'key53041': 'value92249',
    'key66503': 'value42521',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Diana Christensen',
    'address': '90823 Jennifer Rapid Suite 232\nAlantown, NJ 88779',
    'text': 'Role leave more sell tough ready agent. Debate economy who painting. Production father outside all. Increase interview surface score.',
    'email': 'erodriguez@example.com',
    'phone_number': '+1-201-227-3874',
    'array_int_dynamic': [
    60513,
],
    'array_varchar_dynamic': [
    'Haley Austin',
    'Jaime Weeks',
    'Austin Johnson',
    'Brian Martin',
    'Steven Collins',
    'Matthew Rivers',
    'Karen Frank',
    'Karen Carr',
],
    'json': {
    'name': 'Stephanie Franco',
    'address': '63660 Henry Flat\nNew Fred, MT 56279',
},
    'key85676': 'value26155',
    'key2813': 'value7642',
    'key24188': 'value18974',
    'key27686': 'value435',
    'key87288': 'value86125',
    'key69835': 'value58020',
    'key52712': 'value41889',
    'key84759': 'value75805',
    'key2741': 'value76841',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jesse Obrien',
    'address': '2626 Delgado Plaza Suite 578\nLake Julia, AR 80440',
    'text': 'Position good reduce everybody get dog for. Point natural outside.\nFull picture speak society. Charge herself see you.',
    'email': 'dtodd@example.com',
    'phone_number': '001-602-291-2704x9519',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Holly Baxter',
    'Patrick Ramos',
    'Cheryl Gordon',
    'Elizabeth Kim',
    'Tommy Fisher',
    'Tonya Davis',
    'Tina Hart',
    'Sherry Briggs',
],
    'json': {
    'name': 'Marcus Gillespie',
    'address': '52922 Stanley Inlet Suite 896\nEast Scottville, IA 78904',
},
    'key85488': 'value68007',
    'key64641': 'value25538',
    'key12286': 'value68777',
    'key41797': 'value29502',
    'key12376': 'value95899',
    'key37144': 'value53992',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'David Wilson',
    'address': '8346 Rachel Hollow Apt. 032\nEast Christophertown, VI 74152',
    'text': 'Eye trial page painting. Stage trial style keep man.\nEver more employee operation return. Black wrong ball wind. Poor improve firm chair end star.\nIndicate who we west.',
    'email': 'whicks@example.net',
    'phone_number': '890.757.8757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Mcdaniel',
    'Tony Evans',
    'Marilyn Powell',
    'Mr. Samuel Porter',
    'Courtney Moore',
    'Kristin Turner',
    'Joshua Cruz',
    'Sara Johnson',
],
    'json': {
    'name': 'Tim Stephens',
    'address': '23188 Laura Stravenue\nEast Brett, KS 85365',
},
    'key87580': 'value82656',
    'key49203': 'value80832',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Amanda Rivas',
    'address': '1623 Joshua Drives\nHaleport, HI 99855',
    'text': 'West receive write throughout. Through art country half contain. Fund down election operation. Speak husband environmental including management of.',
    'email': 'evelyn90@example.net',
    'phone_number': '(872)671-0325x2859',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Angela Hamilton',
    'Jonathan Gomez',
],
    'json': {
    'name': 'Daniel Mitchell',
    'address': '8717 Lane Creek Apt. 006\nSouth Dylanville, CT 82163',
},
    'key11219': 'value35771',
    'key80034': 'value63969',
    'key90720': 'value10108',
    'key60903': 'value29029',
    'key99914': 'value16519',
    'key82040': 'value92047',
    'key90244': 'value12824',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'William Cook',
    'address': '3570 Reed Walks\nPort Theresahaven, NC 33186',
    'text': 'Front clearly positive dream. Evidence so middle west. Example final state a score bar. Human foreign design practice.',
    'email': 'rodriguezbradley@example.net',
    'phone_number': '001-905-762-8370x952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Miss Natalie Gonzalez',
    'Dorothy Torres',
    'Lindsey Robinson',
    'Mario Martin',
    'Darryl Ball',
    'Herbert Guzman',
    'Angel Houston',
    'Stephanie Richards PhD',
    'Sheila Santos',
],
    'json': {
    'name': 'Megan Lewis',
    'address': 'USS Roberson\nFPO AP 24371',
},
    'key242': 'value85150',
    'key38290': 'value25368',
    'key46254': 'value93552',
    'key20377': 'value6204',
    'key42505': 'value15433',
    'key53205': 'value54698',
    'key41417': 'value21993',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Melissa Bowman',
    'address': '67081 Sierra Inlet Apt. 160\nPort Ricardo, ND 04813',
    'text': 'Forget stay left land power senior environment. At anyone reason yourself miss hear future. Although arm cut plant democratic though office.',
    'email': 'vaughnjoseph@example.com',
    'phone_number': '+1-721-799-0481',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Richard Sanchez',
    'Scott Eaton',
    'Alexander Jackson',
    'Stephanie Lynch',
    'Mike Fisher',
],
    'json': {
    'name': 'Linda Wood',
    'address': '0492 Cantu Crest Suite 106\nCharleneshire, MS 58001',
},
    'key11750': 'value75939',
    'key65849': 'value46198',
    'key40459': 'value48220',
    'key81294': 'value50881',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Thomas Huang',
    'address': '101 Marie Knolls Suite 918\nVickieland, SC 76163',
    'text': 'During phone image bill add. Boy whole cut Mr guess.\nBuilding card cultural modern him true. Million single firm step.',
    'email': 'diana65@example.net',
    'phone_number': '4662490027',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'David Andersen',
    'Tina Johnson',
    'Jamie Long',
    'Margaret Arnold',
    'William Black',
],
    'json': {
    'name': 'Kelly Jenkins',
    'address': '713 Brady Unions Apt. 307\nLaurenburgh, WY 24747',
},
    'key90672': 'value69449',
    'key52317': 'value44539',
    'key17652': 'value161',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Tiffany Gomez',
    'address': 'USNV Davis\nFPO AE 73477',
    'text': 'Society find know game factor necessary affect near. Onto about factor admit. Hear provide trial off significant economy the.',
    'email': 'vicki01@example.net',
    'phone_number': '5298349160',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Patricia King',
    'Mitchell Campbell',
    'Cheryl Fletcher',
    'Raymond Holt',
    'Donna Garcia',
    'Kendra Hicks',
    'Jason Hardy',
    'Brian Combs',
    'Michael Brooks',
    'Michael Martin',
],
    'json': {
    'name': 'Michelle Sanchez',
    'address': '8289 Lopez Plains Apt. 298\nJohnside, MH 65157',
},
    'key87170': 'value55594',
    'key45527': 'value59895',
    'key49764': 'value70102',
    'key50745': 'value62472',
    'key42244': 'value58033',
    'key60492': 'value48023',
    'key17808': 'value81343',
    'key75506': 'value89523',
    'key35804': 'value14016',
    'key38733': 'value28',
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
    'RequestId': '93b2d875-62ef-11f0-96c1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_35_316156HWcbZrRO',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-128-10-1]_1752744156.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl1281011752744156Json()
    test.run_tests()
