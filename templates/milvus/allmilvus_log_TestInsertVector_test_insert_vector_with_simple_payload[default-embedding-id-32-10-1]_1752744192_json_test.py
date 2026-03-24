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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-1]_1752744192_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-1]_1752744192.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId321011752744192Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-1]_1752744192.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-1]_1752744192.json"
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
    'RequestId': 'a8fb00db-62ef-11f0-aab1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_11_021213aEZaKtIC',
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
    'RequestId': 'a901a6e4-62ef-11f0-bb25-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_11_021213aEZaKtIC',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Joshua Vang',
    'address': '189 Nunez Inlet\nDawsonstad, UT 67572',
    'text': 'Open talk table white event. Together wait how. College score partner part ready somebody.\nMe firm attorney possible hear receive. Suffer big education future.',
    'email': 'skinnerlisa@example.org',
    'phone_number': '874.249.8128x32966',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Burgess',
    'Veronica Kline',
    'Lori Mills',
    'Rachel Brown',
    'Matthew Parker',
    'Toni Rodriguez',
    'Michael Ward',
],
    'json': {
    'name': 'Brandi Crawford',
    'address': '67187 Eugene Keys Apt. 084\nCampbellfurt, OK 00871',
},
    'key9563': 'value68023',
    'key93813': 'value8604',
    'key89068': 'value73343',
    'key65641': 'value32948',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Justin Buck',
    'address': '91624 May Union Suite 515\nWest Jennifer, NY 69652',
    'text': 'Game box push purpose support probably your. Attention necessary send guess size. Poor begin just role chance machine.\nAllow resource tonight able. What commercial ever rest report.',
    'email': 'thomaslopez@example.com',
    'phone_number': '847.484.5652',
    'array_int_dynamic': [
    93048,
],
    'array_varchar_dynamic': [
    'Alisha Parker',
    'Heather Moore',
    'Frank Norris',
    'David Ware',
    'Michael Bowen',
    'Jennifer Irwin',
    'Michael Blake',
    'Denise Lee',
    'Matthew Campbell',
],
    'json': {
    'name': 'Brandon Arnold DDS',
    'address': '0902 Becker Prairie\nSouth Jacquelineshire, LA 38095',
},
    'key79173': 'value68253',
    'key23716': 'value45990',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Jose Dennis',
    'address': 'PSC 4401, Box 9778\nAPO AA 67618',
    'text': 'Knowledge it about ago. Only truth week town entire least. Make memory thing boy front.\nThroughout I each challenge scene determine. People arm statement move. Discover the generation reflect.',
    'email': 'fryconnor@example.net',
    'phone_number': '001-808-576-7517x99996',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ethan Williams',
    'Colleen James',
    'Susan Williams',
    'Crystal Moreno',
    'Daniel Walker',
    'Heidi Carter',
    'Jessica Juarez',
],
    'json': {
    'name': 'Chloe Jones',
    'address': 'PSC 9898, Box 8229\nAPO AP 34688',
},
    'key91754': 'value76198',
    'key40815': 'value36515',
    'key46288': 'value67493',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Danny King',
    'address': '302 Kiara Street Suite 284\nSouth Charles, CT 16850',
    'text': 'Could throw on see anyone religious business. Add knowledge southern particular prove north. Long standard require keep hold world.',
    'email': 'samanthaalvarez@example.net',
    'phone_number': '001-587-952-9764x9629',
    'array_int_dynamic': [
    38582,
],
    'array_varchar_dynamic': [
    'Leslie Thomas',
    'Kelly Burgess',
],
    'json': {
    'name': 'Aaron Jones',
    'address': 'Unit 8889 Box 0802\nDPO AA 36151',
},
    'key37673': 'value14180',
    'key79323': 'value20639',
    'key46543': 'value28912',
    'key8322': 'value96935',
    'key31823': 'value16109',
    'key99114': 'value66652',
    'key50800': 'value1755',
    'key26371': 'value24493',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Jessica Guerrero',
    'address': '303 Steven Field Suite 027\nScotttown, KS 77550',
    'text': 'Water movement environmental site spend. Source across mother big project. Site administration nation bar worker change.\nFocus reduce clear. Involve like be though doctor field.',
    'email': 'valerie07@example.com',
    'phone_number': '771-779-8881',
    'array_int_dynamic': [
    82713,
],
    'array_varchar_dynamic': [
    'Kaitlin Morgan',
    'Nicole Johnson',
    'Kyle Cohen',
    'Corey Boyd',
    'Henry Henry',
    'Desiree Morales',
    'Jennifer Baker',
    'Jordan Franklin',
],
    'json': {
    'name': 'Kenneth Barr',
    'address': '33867 Eric Expressway Apt. 437\nStacyville, PR 74440',
},
    'key46683': 'value53969',
    'key66437': 'value17520',
    'key87707': 'value16986',
    'key52352': 'value8436',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Hannah Wilson',
    'address': '4698 Kevin Ways Suite 150\nLaurieborough, PR 34260',
    'text': 'Quite trouble material choice season culture laugh. Science quite heart energy military.',
    'email': 'margaretellison@example.com',
    'phone_number': '001-596-253-0246x95162',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Alvarez',
    'Brian Melton',
    'Nathaniel King',
    'Brian Christian',
],
    'json': {
    'name': 'Patricia Wilson',
    'address': '6597 Melissa Ferry Suite 934\nSpenceborough, MI 18794',
},
    'key52278': 'value35700',
    'key75546': 'value93729',
    'key96959': 'value3531',
    'key37642': 'value33830',
    'key7344': 'value12128',
    'key97170': 'value56669',
    'key7270': 'value25265',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Angela Holland',
    'address': '44111 Ramos Fort\nPort Fernando, SC 62141',
    'text': 'Knowledge daughter measure. Their poor something happen scientist explain.\nRoad way cover thought inside. Entire serve relationship of. Note until general.',
    'email': 'victoriabriggs@example.net',
    'phone_number': '276-726-4921',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Charles Cruz',
],
    'json': {
    'name': 'Steven Armstrong',
    'address': '3436 Elizabeth Parks\nSouth Tylerland, MI 46046',
},
    'key63214': 'value23832',
    'key89529': 'value41928',
    'key19996': 'value96640',
    'key87390': 'value7976',
    'key20446': 'value90942',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Thomas Lawrence',
    'address': '98169 Mitchell Club Suite 781\nSmithfort, ID 68356',
    'text': 'Election plant health stop particularly. Actually cup too be member over.\nDay knowledge grow follow. Mouth this black notice.',
    'email': 'cochrancody@example.org',
    'phone_number': '9708123244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Terri Kennedy',
    'Katrina Oneal',
    'Kristie Wells',
    'Aaron Smith',
    'James Kelly',
],
    'json': {
    'name': 'Ashley Turner',
    'address': 'Unit 6430 Box 3074\nDPO AE 65162',
},
    'key4789': 'value10243',
    'key5937': 'value86460',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Cheryl Bruce',
    'address': '48763 Arias Branch\nLake Terrenceland, AR 80811',
    'text': 'Live page same write collection must become. Store no hit school.\nDeal campaign sea attention. Analysis authority three usually national.\nSoon hold term small. Fight common size city.',
    'email': 'nforbes@example.com',
    'phone_number': '001-856-349-5548x142',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Glenda Martin',
],
    'json': {
    'name': 'Richard Andrews',
    'address': '027 Catherine Terrace\nEast Paul, VI 60630',
},
    'key49550': 'value44914',
    'key34743': 'value93807',
    'key1144': 'value74533',
    'key22460': 'value21760',
    'key53834': 'value64905',
    'key43097': 'value37102',
    'key42710': 'value84356',
    'key37058': 'value83892',
    'key34974': 'value79098',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Elizabeth Walker',
    'address': '2944 Castro Shoals\nGibsonchester, MT 68565',
    'text': 'Require happen boy total explain. Article create expert remain difference improve. Story site plan.\nFish enjoy point service. Authority to cover field us. Week lay feeling family own.',
    'email': 'danielle87@example.net',
    'phone_number': '431.768.2569x6852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Davis',
    'Randy Barber',
    'Jason Roberts',
    'Carol Flores',
    'Pamela Cortez',
    'Jessica Schaefer',
],
    'json': {
    'name': 'Ryan Hill',
    'address': '0377 Robert Lane Suite 293\nChavezland, UT 23644',
},
    'key8456': 'value79766',
    'key41397': 'value80592',
    'key38766': 'value99817',
    'key77478': 'value90633',
    'key500': 'value85411',
    'key35725': 'value97851',
    'key27316': 'value17539',
    'key63974': 'value43119',
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
    'RequestId': 'a8fb00db-62ef-11f0-aab1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_11_021213aEZaKtIC',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-10-1]_1752744192.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId321011752744192Json()
    test.run_tests()
