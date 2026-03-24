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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-1]_1752744199_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-1]_1752744199.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId1281011752744199Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-1]_1752744199.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-1]_1752744199.json"
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
    'RequestId': 'ad476909-62ef-11f0-a87f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_18_232822zbXHsxNb',
    'dimension': 128,
    'primaryField': 'id',
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
    'RequestId': 'ad4ea12a-62ef-11f0-8e19-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_18_232822zbXHsxNb',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Catherine Austin',
    'address': 'Unit 1357 Box 2800\nDPO AA 42340',
    'text': 'Deep best use instead. Away since too election. Remember find measure fall.\nGlass rise record no drug state to.',
    'email': 'bruce12@example.net',
    'phone_number': '(459)381-0231',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mark Lopez',
    'Abigail Figueroa',
    'Daniel Harrison',
    'Stacy Vargas',
    'Matthew Brown',
    'Dana Chambers',
    'Jesse Little',
    'Bradley Salazar',
    'Ian Lara',
],
    'json': {
    'name': 'Elizabeth Ross',
    'address': '49091 Jacob Forks Apt. 531\nSmithburgh, UT 11141',
},
    'key39183': 'value19749',
    'key90898': 'value31350',
    'key83318': 'value86572',
    'key12953': 'value65248',
    'key38022': 'value84627',
    'key79826': 'value80441',
    'key79902': 'value59125',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Ashley Ferguson',
    'address': '04789 Aaron Rapid Apt. 134\nEast Barbaraton, AZ 50171',
    'text': 'Decade shake indeed majority prevent record. Against government mother us. Edge window activity cost cup shoulder but.',
    'email': 'austinflores@example.net',
    'phone_number': '930-484-3935',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Juan Green',
    'Erica Hamilton',
    'Susan Ford',
    'Brent Rollins',
    'Melissa Knight',
    'Brett Clark',
    'Andrea Perez',
    'Anthony Chavez',
],
    'json': {
    'name': 'Virginia Weber',
    'address': '88407 Carter Gardens\nGrayton, AZ 98281',
},
    'key50415': 'value38184',
    'key79625': 'value41976',
    'key59483': 'value93498',
    'key82901': 'value23058',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Deborah Bradley',
    'address': '7506 Lee Curve\nPattersonmouth, IA 39929',
    'text': 'We after age hard. Risk evidence need center instead artist.\nRest although organization successful town spend join push. Even watch that serious modern entire.',
    'email': 'davisjohnny@example.net',
    'phone_number': '(516)944-9258',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Eric Walton',
],
    'json': {
    'name': 'Suzanne Singh',
    'address': '57513 Neal Plaza\nLake Jenniferborough, IL 55107',
},
    'key60780': 'value69523',
    'key98671': 'value69862',
    'key82329': 'value85914',
    'key92895': 'value51360',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Dustin Horne',
    'address': '8582 Gardner Ports\nLake Julianstad, AS 29735',
    'text': 'Letter oil among make yes relate. Executive Republican card doctor never include he.\nHear country its center least shake.\nRealize easy stop. Story shoulder anything moment learn here.',
    'email': 'aaguilar@example.net',
    'phone_number': '+1-457-795-0490x344',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christine Stone',
    'Dawn Ramirez',
    'Mary Nielsen',
    'Danielle Kennedy',
],
    'json': {
    'name': 'Michael Roach',
    'address': '8702 Jeffrey Brook\nRodriguezfort, PR 65130',
},
    'key26164': 'value45247',
    'key47689': 'value6326',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Darlene Salazar',
    'address': '54267 Caldwell Road\nCrystaltown, UT 82740',
    'text': 'Deal bill best enter paper create his. Explain identify that case opportunity consider. Week sea ask miss.\nBaby effect environmental figure put result. Wife not nice subject standard.',
    'email': 'alice81@example.net',
    'phone_number': '768-519-8136x82156',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tony Craig DDS',
    'Danielle Vega',
    'Gerald Jimenez',
],
    'json': {
    'name': 'Matthew Ortiz',
    'address': '682 Amanda Highway\nWangshire, MP 95195',
},
    'key36153': 'value82657',
    'key2705': 'value5012',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Mary Walker',
    'address': '60681 Melissa Glens Suite 775\nPort Jonathan, TN 83964',
    'text': 'Dog Mr western reveal particularly. Thus play since personal movement environment necessary.',
    'email': 'skane@example.org',
    'phone_number': '001-926-299-3714',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Lin',
    'Cameron Pierce',
    'Samantha Liu',
    'Richard Moore',
    'Amber Lewis',
    'Joseph Patton',
],
    'json': {
    'name': 'Ronald Evans',
    'address': 'Unit 5493 Box 3354\nDPO AA 93526',
},
    'key19480': 'value98875',
    'key73921': 'value1255',
    'key38259': 'value70323',
    'key87677': 'value93240',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Destiny Miller DDS',
    'address': '2258 Williams Wells\nPort Madison, PW 93628',
    'text': 'Situation evidence believe side a few as. Myself education nothing son so.\nDrive could decade occur everybody cup. Rather bed card myself.',
    'email': 'josephmcdonald@example.com',
    'phone_number': '+1-587-943-4675x8412',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Kennedy',
    'Dr. Jennifer Gill',
    'Cynthia Glover',
    'Mary Collins',
    'Ashley Byrd',
    'Leah Romero',
],
    'json': {
    'name': 'Jason Harris',
    'address': '47279 Brown Ridges Apt. 091\nWest Kevinstad, MI 86871',
},
    'key90683': 'value19143',
    'key19551': 'value51128',
    'key40194': 'value10311',
    'key82959': 'value82575',
    'key55003': 'value77779',
    'key96837': 'value88635',
    'key60534': 'value94556',
    'key96216': 'value96738',
    'key41771': 'value16704',
    'key71060': 'value37464',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Scott Ramos',
    'address': '7780 Mary Point\nErinstad, WV 94144',
    'text': 'Structure room recent chance. White however student.\nDescribe certainly discover act form capital. Serve writer other table cell. Table commercial through task west inside.',
    'email': 'natalie85@example.net',
    'phone_number': '818.478.4284',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Hernandez',
    'Cathy Gomez',
    'Lisa Reid',
    'Cassandra Casey',
],
    'json': {
    'name': 'Adam Lindsey',
    'address': '788 Bill Falls\nSandrafurt, ID 22670',
},
    'key6943': 'value82541',
    'key50113': 'value64217',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Dillon Shepard',
    'address': '96267 Carroll Isle Apt. 796\nBrowningstad, ME 36952',
    'text': 'His choose work section find.\nState down since. Down receive consumer civil stock member.\nSon world visit. Range recognize eye five might. Audience enter nice group describe never name.',
    'email': 'ginastevens@example.com',
    'phone_number': '001-782-845-5309x253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Avila',
    'Andrew Jacobs',
    'Dr. Monica George',
    'Jennifer Coleman',
    'Kristi Ruiz',
    'Renee Hudson',
],
    'json': {
    'name': 'Tiffany Sanchez',
    'address': 'Unit 3569 Box 5103\nDPO AA 77092',
},
    'key26543': 'value51586',
    'key69856': 'value13292',
    'key37685': 'value40488',
    'key15717': 'value53206',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Joe Mejia',
    'address': '8804 Ronnie Cliffs\nWest Jonathanburgh, GA 38101',
    'text': 'By reduce agree. Nice player stock exist yard. Source operation market difficult natural future.',
    'email': 'jon41@example.net',
    'phone_number': '469.993.1169x5841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joe Powell',
    'Diane Griffin',
],
    'json': {
    'name': 'Maria Carey',
    'address': '054 King Flats Suite 029\nPort Laura, AK 59546',
},
    'key50655': 'value742',
    'key25506': 'value51434',
    'key2148': 'value76631',
    'key78291': 'value37410',
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
    'RequestId': 'ad476909-62ef-11f0-a87f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_18_232822zbXHsxNb',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-10-1]_1752744199.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId1281011752744199Json()
    test.run_tests()
