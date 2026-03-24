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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-10-1]_1752744134_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-10-1]_1752744134.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId321011752744134Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-10-1]_1752744134.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-10-1]_1752744134.json"
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
    'RequestId': '86604785-62ef-11f0-abc3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_12_964682xUsVnnYA',
    'dimension': 32,
    'primaryField': 'id',
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
    'RequestId': '86672c8e-62ef-11f0-8113-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_12_964682xUsVnnYA',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Dr. Jennifer Robertson',
    'address': '6933 Angie Stream\nWest Tylerton, NC 73426',
    'text': 'Least traditional theory. Child but if seek drop community senior.\nCover us such. Guy close again scientist eight.',
    'email': 'monica89@example.org',
    'phone_number': '001-325-978-8204x7246',
    'array_int_dynamic': [
    25941,
],
    'array_varchar_dynamic': [
    'Keith Parker',
],
    'json': {
    'name': 'Tina Gibson',
    'address': '823 Gutierrez Plaza\nMillerfort, DE 28419',
},
    'key98592': 'value60861',
    'key89661': 'value51512',
    'key86463': 'value92656',
    'key76259': 'value13106',
    'key99612': 'value3564',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Andrew Bailey',
    'address': '05998 Ana Grove Apt. 369\nBowmantown, AZ 60293',
    'text': 'Table specific official strategy part condition. Approach because full various.',
    'email': 'daniel87@example.com',
    'phone_number': '654.366.5822x146',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Angela Hansen',
    'John Le',
    'Joshua Singh',
    'Amy Smith MD',
    'Amanda Craig',
    'Angela Wu',
],
    'json': {
    'name': 'Christina James',
    'address': '65685 Madison Road\nChoishire, RI 37423',
},
    'key70035': 'value9098',
    'key42786': 'value83449',
    'key94712': 'value6757',
    'key94682': 'value81915',
    'key45426': 'value20328',
    'key29722': 'value98284',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Matthew Bailey',
    'address': '840 Kimberly Pines Apt. 667\nColemanfort, MA 36940',
    'text': 'Focus end career guy center car.\nPlayer despite positive Republican both mention action. Subject success certainly. Morning over herself probably night.',
    'email': 'rachelrichards@example.org',
    'phone_number': '001-246-538-3685x29885',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Blackwell',
    'Michael Johns',
    'Billy Lewis',
    'Danielle Lucas',
    'Elizabeth Walker',
],
    'json': {
    'name': 'Patricia Reynolds',
    'address': 'USCGC Smith\nFPO AP 16602',
},
    'key41092': 'value73551',
    'key69948': 'value95407',
    'key92839': 'value61488',
    'key83716': 'value82626',
    'key89543': 'value46405',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Matthew Benjamin',
    'address': '6485 Kimberly Islands\nWest Thomas, FM 25332',
    'text': 'He record protect debate itself. Carry picture single about garden news. Heavy amount enter cup somebody.',
    'email': 'haleymartin@example.org',
    'phone_number': '(840)836-9697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Collins',
    'Cynthia Brown',
    'Jerry Jenkins',
    'Walter Russell',
    'Selena Caldwell',
],
    'json': {
    'name': 'Jerry Sullivan',
    'address': '200 Brown Harbors\nNathanton, DE 46625',
},
    'key10269': 'value69827',
    'key91110': 'value58547',
    'key99259': 'value8836',
    'key12165': 'value35268',
    'key37560': 'value98088',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Ryan Morales',
    'address': '482 Sarah Forge\nKennethview, CO 60491',
    'text': 'Middle prove treat cell election yourself particular. Bed director sister action behavior administration usually. Move executive everything debate story course.\nNote board majority your move weight.',
    'email': 'umoore@example.com',
    'phone_number': '758-413-4864x2509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Kim',
    'Ebony Carney',
    'Peter Donaldson',
    'Shawna Washington',
    'Randy Vega',
],
    'json': {
    'name': 'Robert Hunter',
    'address': '633 Paul Road\nMaxwellmouth, AL 35622',
},
    'key17019': 'value60424',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Andrew Gilmore',
    'address': '084 Raymond Roads Apt. 701\nNew Kimberly, ID 70461',
    'text': 'Article many nature. Because analysis management guess. Human shake really tough.\nMay conference issue suffer.',
    'email': 'isabel14@example.net',
    'phone_number': '639-413-9935x80800',
    'array_int_dynamic': [
    53863,
],
    'array_varchar_dynamic': [
    'Jonathon Schmidt',
    'Deborah Holt',
    'Janet Navarro',
    'Melissa Singleton',
    'Teresa Thomas',
],
    'json': {
    'name': 'Darius Martinez',
    'address': '68046 Kristin Fords\nJenniferburgh, ME 02535',
},
    'key55449': 'value34691',
    'key73504': 'value17141',
    'key52509': 'value17067',
    'key75548': 'value4873',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Rhonda Collins',
    'address': '3816 Courtney Skyway\nBellville, WA 50057',
    'text': 'Paper might adult shoulder. Dinner ability outside meeting someone on.\nQuickly answer really them audience state.',
    'email': 'prattmichael@example.com',
    'phone_number': '(519)226-6328x4365',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Julia Gomez',
    'Benjamin Meyer',
    'Lydia Mcneil',
    'Lisa Rowe',
    'Terry Chapman',
    'Ashlee Short',
    'Douglas Carlson',
    'Rebekah Vega',
],
    'json': {
    'name': 'James Williamson',
    'address': '265 Judy Ports\nSusanfort, AS 61095',
},
    'key86814': 'value70118',
    'key65302': 'value4175',
    'key94955': 'value21576',
    'key85636': 'value14749',
    'key33435': 'value94298',
    'key20300': 'value27',
    'key97898': 'value48325',
    'key84360': 'value32590',
    'key5246': 'value7122',
    'key30102': 'value24213',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Jesus Wilson',
    'address': '949 Bailey Common\nPagefurt, CO 90234',
    'text': 'Tree a method example because old. Many bit always air miss bag project.\nPut with place trip. Free few foreign book their catch explain. She fall have successful campaign modern.',
    'email': 'jfrazier@example.org',
    'phone_number': '+1-664-751-2119x276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Darren Roberts',
    'Richard Kim',
    'Diana Ayers',
    'Melissa Hart',
],
    'json': {
    'name': 'Thomas Butler',
    'address': 'Unit 4024 Box 0163\nDPO AE 75550',
},
    'key14346': 'value10031',
    'key48491': 'value20122',
    'key7706': 'value11253',
    'key35677': 'value8509',
    'key37971': 'value64747',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Denise Gray',
    'address': '2051 Ray Centers Suite 212\nKevinton, RI 64636',
    'text': 'Standard policy system real weight discussion institution serious. Base together it similar sell unit grow.',
    'email': 'shannonhernandez@example.org',
    'phone_number': '(805)643-9987',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alexandra Williams',
    'Justin Gonzalez',
    'John Kim',
    'John Espinoza',
    'Stephanie Stanley',
    'Dr. Joshua Snyder',
    'Michael Rhodes',
    'Michael Blake',
    'Nathan Ritter',
    'Joshua Fernandez',
],
    'json': {
    'name': 'James Nelson',
    'address': '2858 Javier Rapids\nHarrellfurt, CO 94413',
},
    'key62538': 'value57595',
    'key99012': 'value45794',
    'key58797': 'value17210',
    'key81733': 'value96739',
    'key84918': 'value77677',
    'key35813': 'value982',
    'key37837': 'value14669',
    'key75100': 'value78694',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Eric Marshall',
    'address': '139 Ryan Plains\nPort Catherine, NV 46093',
    'text': 'Market me discuss article. Ground raise quickly they stock likely ago. Recent mission present system six activity. Up help under four various however science.',
    'email': 'weaverphillip@example.com',
    'phone_number': '2804453387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Huang',
    'Cynthia Jones',
    'Jennifer Galvan',
    'Charlene Reeves',
    'Jennifer Robinson',
    'David Cox Jr.',
],
    'json': {
    'name': 'Steven Smith',
    'address': '54164 Hooper Extensions\nMeltonfort, CT 82340',
},
    'key75635': 'value72713',
    'key28875': 'value11763',
    'key1071': 'value80332',
    'key89793': 'value27638',
    'key39264': 'value75738',
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
    'RequestId': '86604785-62ef-11f0-abc3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_12_964682xUsVnnYA',
    'dimension': 32,
    'primaryField': 'id',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-32-10-1]_1752744134.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId321011752744134Json()
    test.run_tests()
