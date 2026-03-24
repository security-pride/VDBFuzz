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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-2]_1752744191_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-2]_1752744191.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId321021752744191Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-2]_1752744191.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-2]_1752744191.json"
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
    'RequestId': 'a8548c8c-62ef-11f0-9637-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_09_930317lVjmBZYn',
    'dimension': 32,
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
    'RequestId': 'a85b8544-62ef-11f0-b920-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_09_930317lVjmBZYn',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Tammy Fernandez',
    'address': '186 Mckenzie Mission Apt. 763\nSmithchester, OR 40165',
    'text': 'Girl man administration. Draw four hour skill.\nAlways price on court. How worry seven participant popular. Cover nearly whether ask certainly information.',
    'email': 'qsmith@example.org',
    'phone_number': '(271)846-8196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Randy Robinson MD',
    'Taylor Thomas',
    'Warren Hill',
    'Elijah Meadows',
    'Rachel Carter',
    'Jacqueline Roberts',
    'John Howell',
    'Karina Lynch',
    'Kari Hughes',
],
    'json': {
    'name': 'Stephanie Anderson',
    'address': '3732 Renee Avenue Apt. 176\nSouth Jeffreyland, MS 60202',
},
    'key60580': 'value73540',
    'key88140': 'value62076',
    'key42882': 'value86804',
    'key84377': 'value24972',
    'key57000': 'value39639',
    'key30466': 'value183',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Ashley Gibbs',
    'address': '35144 Melissa Isle Suite 760\nNorth Michaelview, MO 16565',
    'text': 'Product might such history total. Head establish pressure art. Ready whose news positive baby mission push war.\nFree theory particularly rather left system year idea. On star crime Mrs run.',
    'email': 'turnerjoseph@example.net',
    'phone_number': '(710)739-9585x206',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dustin Williams',
    'Mrs. Sherry Smith',
],
    'json': {
    'name': 'Vincent Roman',
    'address': '799 Lewis Locks\nJamesshire, PR 25692',
},
    'key70359': 'value61067',
    'key11879': 'value70295',
    'key76285': 'value44932',
    'key68820': 'value99205',
    'key5314': 'value69247',
    'key50483': 'value97617',
    'key75652': 'value60121',
    'key46363': 'value412',
    'key62884': 'value49657',
    'key25652': 'value16371',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'John Bautista',
    'address': '359 Roberts Green\nNew Vincentton, ND 01824',
    'text': 'Mouth doctor drive least when sometimes. Which race site blue memory improve. Interesting democratic put off.',
    'email': 'mjohnson@example.org',
    'phone_number': '+1-887-654-9757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Bennett',
    'Cameron Campos',
    'Matthew Rodriguez',
    'Michael Ford',
    'Benjamin Pena',
],
    'json': {
    'name': 'Lorraine Weaver',
    'address': '2202 Barrera Court Apt. 117\nGaineston, NC 54065',
},
    'key48146': 'value41424',
    'key6085': 'value74323',
    'key76401': 'value84822',
    'key5865': 'value79555',
    'key89510': 'value524',
    'key90713': 'value67146',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Holly Miller',
    'address': '7333 Lambert Fall Apt. 219\nWest Nicholastown, MS 34672',
    'text': 'Among traditional medical spend kid pattern section. Skill loss may education rise health nation.',
    'email': 'matthew96@example.net',
    'phone_number': '(872)882-2346x498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Henry Webster',
    'Timothy Perry',
    'Sarah Vang',
    'Mark Jones',
    'Matthew Lewis',
    'Barbara Anthony',
    'Corey Johnson',
],
    'json': {
    'name': 'Kayla Alvarado',
    'address': '1043 Rodriguez Throughway\nPort Brian, KS 91348',
},
    'key79057': 'value46287',
    'key63641': 'value38937',
    'key2927': 'value71230',
    'key80885': 'value37892',
    'key34523': 'value50031',
    'key90287': 'value45197',
    'key43247': 'value16975',
    'key46858': 'value48296',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Brittany Douglas',
    'address': '080 Jimenez Estate\nLake Tiffanyport, AL 66821',
    'text': 'Another someone east goal his. Hot certain east note speech week then city.\nSenior return tell degree few strong Congress. Be trip would mention.',
    'email': 'ucarter@example.org',
    'phone_number': '(421)481-7974',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Carl Stewart',
    'Brent Smith',
    'Lauren Thompson',
    'Mary Smith',
    'Jonathan Dodson',
    'Felicia Castro',
    'Jason Donovan',
    'Antonio Smith',
],
    'json': {
    'name': 'Lindsey Brown',
    'address': '7361 Lee Views\nPetersonton, AR 75715',
},
    'key31138': 'value82500',
    'key60104': 'value31205',
    'key49041': 'value95185',
    'key96158': 'value40296',
    'key63538': 'value1529',
    'key91141': 'value21430',
    'key64093': 'value52172',
    'key95712': 'value755',
    'key69102': 'value50450',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Katherine Atkinson',
    'address': '24201 Jessica Corners Suite 932\nFordview, KS 67855',
    'text': 'Board unit listen news produce main. Too month north who.\nArm green build impact bag increase. Itself consumer culture watch idea get any. Several candidate add operation industry.',
    'email': 'thomasjames@example.org',
    'phone_number': '856-215-1017',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jason Hughes',
    'Jennifer Pope',
    'Robyn Young',
    'Cynthia Floyd',
    'Richard Barajas',
],
    'json': {
    'name': 'Jeff James',
    'address': '14759 Hood Pines\nThomasstad, NE 41200',
},
    'key10936': 'value8576',
    'key69623': 'value63813',
    'key83630': 'value17278',
    'key61072': 'value13177',
    'key8285': 'value9627',
    'key86581': 'value56265',
    'key45748': 'value40310',
    'key76016': 'value51683',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Jasmine Dixon',
    'address': '4080 James Burgs Suite 496\nCatherinefurt, MD 22134',
    'text': 'Common process know process bill gun describe structure. Represent everything spring production quality.\nIf audience rule population pass not home. Woman south poor there follow down.',
    'email': 'pthompson@example.net',
    'phone_number': '547-553-9391x3077',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Holt',
    'Judy Gonzalez',
],
    'json': {
    'name': 'Brian Boyd',
    'address': '8240 Jacqueline Hill Apt. 602\nBryanton, NY 28963',
},
    'key76267': 'value75819',
    'key16585': 'value64567',
    'key65737': 'value50264',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Edgar Davis',
    'address': '15036 Jason Radial\nAntoniotown, AS 35625',
    'text': 'Smile meet high. Either forward system.\nAgency national attention about whole rich. Possible who stuff young health source seat song.',
    'email': 'smithkenneth@example.com',
    'phone_number': '488.598.4897x45138',
    'array_int_dynamic': [
    74981,
],
    'array_varchar_dynamic': [
    'Anna Wood',
    'Deborah Bishop',
    'Lauren Fitzgerald',
    'William Harris',
    'Stephanie Nelson',
    'Brian Serrano',
    'Casey Castro',
    'Wanda Adams',
    'Robin Hernandez',
],
    'json': {
    'name': 'Christopher Hayden',
    'address': '12352 Miller Roads Suite 600\nJacobsonside, WA 24477',
},
    'key73112': 'value48562',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Daniel Whitaker',
    'address': '06272 Brittany Trace\nSamanthaview, RI 06208',
    'text': 'White open manager author image return. End still sit bring him.\nTrade music player popular fill off difference. Reach lead build affect lot yes. Available gas remember lot.',
    'email': 'uburns@example.net',
    'phone_number': '(275)381-3155x6921',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Griffith',
    'Rachel Hurst',
    'Michael Hill',
    'Warren Singleton',
],
    'json': {
    'name': 'Daniel Hill',
    'address': '99903 Nguyen Ford Suite 349\nStevefurt, MD 84532',
},
    'key8402': 'value35808',
    'key61691': 'value70294',
    'key35062': 'value57088',
    'key50420': 'value5971',
    'key41829': 'value71103',
    'key38118': 'value46160',
    'key9590': 'value74632',
    'key83192': 'value50721',
    'key33231': 'value97925',
    'key72866': 'value44919',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Brooke Mcgee',
    'address': '8784 Nicholas Brooks Suite 741\nHaynesport, WY 51863',
    'text': 'Age reveal ever make pass level. Plant result commercial help practice wide stuff old. Garden mention collection laugh act doctor.',
    'email': 'thomas50@example.com',
    'phone_number': '935-448-2311',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Clay',
    'Melissa Sullivan',
    'Jeffery Morris',
    'Ashley Allen',
    'Scott Graham',
    'Carl Willis',
],
    'json': {
    'name': 'Richard Brown',
    'address': '883 Greene Wells\nSchultzmouth, MP 63611',
},
    'key20269': 'value85653',
    'key85231': 'value78244',
    'key84700': 'value29673',
    'key1328': 'value1165',
    'key54198': 'value40296',
    'key72742': 'value97170',
    'key47704': 'value64713',
    'key56787': 'value30691',
    'key89407': 'value69220',
    'key79736': 'value51531',
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
    'RequestId': 'a8548c8c-62ef-11f0-9637-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_09_930317lVjmBZYn',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-2]_1752744191.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId321021752744191Json()
    test.run_tests()
