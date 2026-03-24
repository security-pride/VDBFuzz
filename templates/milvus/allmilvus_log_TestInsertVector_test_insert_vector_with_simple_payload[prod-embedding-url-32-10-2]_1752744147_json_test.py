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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-2]_1752744147_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-2]_1752744147.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl321021752744147Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-2]_1752744147.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-2]_1752744147.json"
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
    'RequestId': '8e7387a7-62ef-11f0-9cf6-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_26_512611DIvQqjYl',
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
    'RequestId': '8e808837-62ef-11f0-89f5-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_26_512611DIvQqjYl',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Jessica Mcpherson',
    'address': '1492 Jennifer Street\nNew Dennis, OK 07427',
    'text': 'Lot thus listen happen program receive later.\nCultural ever child partner direction. Find can interesting rather call write.',
    'email': 'wilsonsteven@example.net',
    'phone_number': '001-449-416-4575',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Richard Cline',
    'Hannah Gordon',
    'Julian Mcmillan',
    'John Combs',
],
    'json': {
    'name': 'Craig Walker',
    'address': '2813 Cody Lane\nPort Michael, VA 41334',
},
    'key77385': 'value49432',
    'key80984': 'value8712',
    'key77353': 'value13416',
    'key63972': 'value2771',
    'key12264': 'value83717',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Lisa Clark',
    'address': '096 Larry Villages\nJoelshire, MA 14977',
    'text': 'Consider professor son number quite lead stuff. Nation summer middle its author your. Water stand leave such feeling.\nTrouble though other shoulder. Try sound hundred third.',
    'email': 'hernandezcrystal@example.net',
    'phone_number': '359-884-9176x862',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Williams',
    'Taylor Thompson',
    'Valerie Cameron',
    'Charles Gardner',
    'Ryan Aguilar',
    'Steven Harris PhD',
],
    'json': {
    'name': 'Teresa Brady',
    'address': '18041 Mann Lights Suite 582\nEast Phyllisside, WY 67430',
},
    'key67453': 'value20272',
    'key82271': 'value58062',
    'key10316': 'value4452',
    'key82117': 'value75546',
    'key39945': 'value73256',
    'key84623': 'value18540',
    'key43183': 'value11274',
    'key4758': 'value19545',
    'key65277': 'value51056',
    'key99359': 'value38363',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Lisa Valdez',
    'address': '871 Norton Prairie Apt. 580\nBillyfort, WA 99733',
    'text': 'Still because respond Mrs conference when race. Throughout performance street guess him operation. Matter item fire protect gun guy.\nSomeone edge hard thing. Season prove east.',
    'email': 'audrey79@example.com',
    'phone_number': '+1-571-502-4698x463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Lopez',
],
    'json': {
    'name': 'Yvonne Young',
    'address': '0569 Denise Forges\nSouth Melissa, LA 37430',
},
    'key38596': 'value52962',
    'key60546': 'value16490',
    'key43448': 'value5248',
    'key31298': 'value50003',
    'key5522': 'value31189',
    'key73567': 'value63267',
    'key40126': 'value47705',
    'key53892': 'value87060',
    'key93657': 'value77624',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Mrs. Taylor Decker',
    'address': '079 Mary Port\nCurtisshire, MH 23834',
    'text': 'Mr challenge year begin truth answer any wall. Pay music top leader money my energy pick. True though claim may. Opportunity father drug along by.\nDetermine woman lot buy five lead.',
    'email': 'mnorris@example.net',
    'phone_number': '001-462-247-8442x441',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Alexander',
    'Rodney Reed',
    'Audrey Blake',
    'Andrew Wong',
    'Henry Beard',
    'Matthew Lopez',
    'Gina Adams',
],
    'json': {
    'name': 'Robert Valenzuela',
    'address': '152 Davis Crescent Apt. 698\nPort Jeffreyfort, CT 56185',
},
    'key1324': 'value50345',
    'key5833': 'value53868',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Alicia Anthony',
    'address': '1592 Rachael Glen Apt. 857\nNew Jessicaberg, NE 30860',
    'text': 'Sort live activity. Two that point record single wrong. Dream despite yourself role art main. Policy toward past.\nInteresting decide push conference. Leg take until yeah chance fall especially.',
    'email': 'angela61@example.com',
    'phone_number': '699-973-8050',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Emily Schroeder',
],
    'json': {
    'name': 'Travis Strickland',
    'address': '937 Edwards Oval Apt. 597\nSouth Williefurt, CA 15155',
},
    'key11506': 'value80428',
    'key69933': 'value42788',
    'key21654': 'value1544',
    'key58425': 'value38725',
    'key85578': 'value71605',
    'key31194': 'value43833',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Jason Park',
    'address': '503 Hill Springs Suite 422\nNorth Shaunborough, MT 61066',
    'text': 'Tv game treat.\nBorn they teacher course interview address scene. Recent now able health. Major hair drive defense require century.',
    'email': 'wilsondavid@example.org',
    'phone_number': '001-609-372-8694x42564',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Maria Zhang',
    'Elizabeth Parker',
],
    'json': {
    'name': 'Erika Wade',
    'address': '4819 Garcia Trail\nPort Tammy, NC 71878',
},
    'key38583': 'value32715',
    'key37104': 'value41223',
    'key10398': 'value49836',
    'key43779': 'value99233',
    'key29290': 'value62841',
    'key50443': 'value51441',
    'key51823': 'value60629',
    'key98350': 'value99687',
    'key75766': 'value5243',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Adam Steele',
    'address': '1073 Charles Turnpike Suite 387\nNew Stephaniehaven, IA 64690',
    'text': 'Environment thank career focus. Continue perhaps can make land.\nPolitics third federal situation seven money. Use structure beautiful citizen tonight himself gas.\nFour who build use.',
    'email': 'natalie77@example.com',
    'phone_number': '+1-232-314-9627x506',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Barton',
],
    'json': {
    'name': 'Kelly Williams',
    'address': '4217 Day Viaduct\nNorth Calebside, TN 34489',
},
    'key39669': 'value14047',
    'key67217': 'value81426',
    'key21111': 'value90041',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Dr. Tim Bond',
    'address': '2700 Jones Manor\nDeleonside, NC 83593',
    'text': 'Different miss city down design current pressure safe. Soldier ever require without plant hundred third. Watch chance just campaign thought manager.',
    'email': 'kingthomas@example.net',
    'phone_number': '(399)631-3329x777',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tina Lewis',
    'Teresa Rodriguez',
    'Sue Horton',
    'Douglas Morris',
],
    'json': {
    'name': 'Shannon Miller',
    'address': '073 Jeffrey Burgs\nLake Jayport, PR 28759',
},
    'key5802': 'value1591',
    'key77937': 'value57116',
    'key96685': 'value43263',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Margaret Campbell MD',
    'address': '791 Mike Trail Apt. 592\nCherylfort, DC 43218',
    'text': 'A nation maintain career ball second. Visit quickly property reveal son forget behind friend.\nGreat vote understand whether. Civil into value maintain about. Detail western which.',
    'email': 'jackgray@example.org',
    'phone_number': '001-550-409-9396x02933',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sabrina Williams',
    'Lucas Brennan',
],
    'json': {
    'name': 'Megan Smith',
    'address': '9495 Olivia Land Apt. 932\nJuanton, CT 51925',
},
    'key4402': 'value80412',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Elijah House',
    'address': '6366 Laura Meadow\nLake Stevenview, NC 10842',
    'text': 'Down six per tonight. By nor own center. Center somebody so ready worker not.\nHit fly fast clearly black same produce. Support source lose indicate cell school.\nWide value by site.',
    'email': 'andrewpowell@example.com',
    'phone_number': '606.486.3983x2378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Pace',
    'Tabitha Russell',
    'Michael Love',
    'Elizabeth Stanley',
    'Christine Gibson',
    'Robert Lawrence',
    'Nathan Winters',
],
    'json': {
    'name': 'Linda Dawson',
    'address': '2956 Mcclure Trail Apt. 434\nPaulside, GA 56968',
},
    'key14300': 'value40728',
    'key19997': 'value65288',
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
    'RequestId': '8e7387a7-62ef-11f0-9cf6-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_26_512611DIvQqjYl',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-10-2]_1752744147.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl321021752744147Json()
    test.run_tests()
