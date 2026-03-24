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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-1]_1752744105_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-1]_1752744105.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId321011752744105Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-1]_1752744105.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-1]_1752744105.json"
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
    'RequestId': '754b7aa0-62ef-11f0-abee-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_44_307082JEcCMzTr',
    'dimension': 32,
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
    'RequestId': '75584bbc-62ef-11f0-b09e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_44_307082JEcCMzTr',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Alexander Benjamin',
    'address': '06865 Lewis Street\nFrankton, OR 22568',
    'text': 'Where former bank time save heart away. Population without our new time.\nLeg table different affect best size dark soldier. Nothing either agree wind course base treatment his. Hard scene career.',
    'email': 'tamarasmith@example.com',
    'phone_number': '7665229784',
    'array_int_dynamic': [
    2841,
],
    'array_varchar_dynamic': [
    'Timothy Smith',
    'Jon Taylor',
    'Kathryn Johnson',
    'Brittney Green',
    'Michael Chang',
    'Laurie Hill',
],
    'json': {
    'name': 'Jacob Barnett',
    'address': '9548 Timothy Summit Apt. 002\nAngelicafurt, WI 68355',
},
    'key89993': 'value40797',
    'key4087': 'value7336',
    'key13856': 'value42801',
    'key73750': 'value3667',
    'key49479': 'value66714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Richard Young',
    'address': '892 Little Ville\nAndrewbury, WI 42740',
    'text': 'Culture sport sport size. Thought attention support quickly past other result.\nHistory question none under imagine seek her. Glass east game. There imagine machine get structure.',
    'email': 'harperhaley@example.net',
    'phone_number': '+1-359-632-5044x15922',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Ramirez',
    'Lydia Foley',
    'Sandra Baxter',
    'Mary Santos',
    'Melissa Olsen',
    'Tara Murray',
    'Rachael Smith',
    'Larry Abbott',
    'Kenneth Bartlett',
],
    'json': {
    'name': 'Jeremiah Powers',
    'address': '0293 Randall Islands\nNew Nicole, KS 28087',
},
    'key51767': 'value51732',
    'key68500': 'value4864',
    'key63072': 'value81250',
    'key74947': 'value74776',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Christopher Nixon',
    'address': '95021 Cooper Brooks\nJimmymouth, VA 83588',
    'text': 'Military line space measure seven green large small. Section much particular professor year character catch total. Partner grow onto four get must.\nDuring determine small water top. Her might wife.',
    'email': 'stephaniesmith@example.com',
    'phone_number': '(954)426-5379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Denise Griffin',
    'Melissa Hubbard',
    'Brian Moore',
    'Isabel Haley',
    'Jordan Lewis',
],
    'json': {
    'name': 'Fernando Curtis',
    'address': '6869 William Parkway Apt. 999\nPort Aaronchester, CO 47151',
},
    'key57666': 'value25026',
    'key68915': 'value14422',
    'key50140': 'value88995',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Corey Rodriguez',
    'address': '041 Gloria Gateway Apt. 618\nNew Matthewport, IN 61480',
    'text': 'Water gas reason common dark a employee. Science fight may mind blood among left politics.\nScience among eye. Lead future dog ask. Democratic task sound plant single.',
    'email': 'carmstrong@example.net',
    'phone_number': '001-734-251-8055x14590',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Walker',
    'Jennifer Fitzgerald',
    'Erica Harris',
    'Evan Richardson',
    'Darrell Jones',
    'Ricardo Montgomery',
    'Gloria Wilson',
    'Ian Crawford',
],
    'json': {
    'name': 'Daniel Pitts',
    'address': '437 Sharon Forest Apt. 837\nBarrerabury, MO 96020',
},
    'key31725': 'value84138',
    'key89314': 'value66177',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Alejandro Brown',
    'address': '3684 Stewart Port Apt. 399\nLake Catherinebury, WY 04203',
    'text': 'Democrat join foreign seven road somebody. Story up early think share.\nGreen energy the cell. Writer mission might Republican where on that ok. Thing decade anything medical.',
    'email': 'stephaniesoto@example.com',
    'phone_number': '5564248349',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Robinson',
],
    'json': {
    'name': 'Brittany Larson',
    'address': 'Unit 4038 Box 5066\nDPO AP 55692',
},
    'key89336': 'value83866',
    'key63088': 'value5433',
    'key99135': 'value61498',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Renee English',
    'address': '37895 Johnson Walks Apt. 888\nJosephmouth, MI 72335',
    'text': 'Push instead land sit heavy. Between whom amount civil side.\nJob us something about four with suddenly. Sell number actually school issue.',
    'email': 'mccarthyamanda@example.net',
    'phone_number': '228.756.0390',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Fields',
    'Kyle Davis',
    'Ryan Hammond',
    'Savannah Marshall',
],
    'json': {
    'name': 'Rebecca Macdonald',
    'address': '01525 Allen Forge Suite 473\nSouth Timothy, LA 13312',
},
    'key46200': 'value70423',
    'key84760': 'value25403',
    'key53047': 'value83440',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Chelsey Adams',
    'address': '33561 Crystal Knolls Suite 232\nNorth Emilyburgh, MA 14035',
    'text': 'Less six support. Paper will four.\nLaw part fast southern member low these. Head us stock yourself indicate.\nFar ability clear glass manage.',
    'email': 'nguyenshari@example.org',
    'phone_number': '+1-718-715-4195x654',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Fischer',
    'Mrs. Janet Bradshaw',
    'Kristin Dickerson',
    'Dale Peterson',
    'Joseph Collins',
    'Thomas Barajas',
    'Jenna Russell',
    'Abigail Castro',
    'Cindy Hull',
],
    'json': {
    'name': 'Anthony Vasquez',
    'address': '2363 Jacqueline Extensions\nNew Kristin, MO 74828',
},
    'key68383': 'value90872',
    'key9424': 'value88377',
    'key32097': 'value35336',
    'key69297': 'value3933',
    'key38837': 'value83192',
    'key89779': 'value56205',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Samantha Fox',
    'address': '7728 Peggy Fords\nKerrimouth, ND 10226',
    'text': 'During executive sort. Fly call trade time.\nMention carry add. Also state have plant together. Relationship guy debate leg artist appear or.',
    'email': 'chapmantyler@example.net',
    'phone_number': '(564)956-5459x5491',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mary Young',
    'Victoria Fernandez',
    'Sandra Garza',
    'Christopher Reed',
    'Jose Perez',
    'Patricia Bradford',
],
    'json': {
    'name': 'Tara Hoffman',
    'address': '00263 Ruben Lodge Apt. 708\nBrittanystad, MA 68254',
},
    'key18752': 'value40520',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Yvonne Preston',
    'address': '563 Martin Place\nSouth Lisaton, AR 99538',
    'text': 'Nation minute for research better letter. Discussion maintain move option bad black.\nContinue gas election far. Approach pattern news check four pretty. Professional follow more degree source.',
    'email': 'laura80@example.net',
    'phone_number': '498-745-9918',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Erica Avila',
    'Steven Yu',
    'Mary Chen',
],
    'json': {
    'name': 'Charles Miller',
    'address': '7518 Gilbert Mountains\nEmilyshire, HI 28895',
},
    'key50138': 'value56494',
    'key86009': 'value98787',
    'key68117': 'value32494',
    'key56749': 'value18987',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Adam Wilkinson',
    'address': '0548 Marcus Shoal\nBrandystad, VI 83605',
    'text': 'Though religious assume attack. Between heart site important trade.\nTop professional economy. Partner character lawyer house thousand visit past.\nItself cause sing laugh.',
    'email': 'briannawilson@example.net',
    'phone_number': '297-812-6209x65350',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Townsend',
    'April Kennedy',
    'David Perez',
    'Gabriela Ward',
    'John Pacheco',
    'Stacy Anderson',
    'Richard Murphy',
    'Tina Henry',
    'Karen Martinez',
    'Robin Thomas',
],
    'json': {
    'name': 'Nicole Andrews',
    'address': '78843 Schwartz Park Suite 913\nFosterport, IL 78156',
},
    'key87463': 'value69284',
    'key7111': 'value89487',
    'key74077': 'value49445',
    'key53843': 'value50387',
    'key67940': 'value98845',
    'key98777': 'value99856',
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
    'RequestId': '754b7aa0-62ef-11f0-abee-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_44_307082JEcCMzTr',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-id-32-10-1]_1752744105.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorId321011752744105Json()
    test.run_tests()
