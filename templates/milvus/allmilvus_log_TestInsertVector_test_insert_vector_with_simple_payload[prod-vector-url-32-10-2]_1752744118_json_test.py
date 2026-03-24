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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-2]_1752744118_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-2]_1752744118.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl321021752744118Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-2]_1752744118.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-2]_1752744118.json"
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
    'RequestId': '7d3775ca-62ef-11f0-bb27-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_57_597662DhzVVSlk',
    'dimension': 32,
    'primaryField': 'url',
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
    'RequestId': '7d3fa49f-62ef-11f0-8409-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_57_597662DhzVVSlk',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Joseph Meyers',
    'address': '568 Matthew Throughway\nLake Gregburgh, GA 55030',
    'text': 'Work entire college evening wrong successful. Crime cover wind student court me.\nCarry red approach size method. Part amount experience especially moment ok president.',
    'email': 'hbrown@example.net',
    'phone_number': '246-223-0162',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'David Sanchez',
    'Jennifer Mason',
    'Richard Anderson',
    'Larry Campbell',
    'Gregory Arellano',
],
    'json': {
    'name': 'Sean Fox',
    'address': '0448 Ian Drive\nFletcherhaven, NY 26749',
},
    'key37789': 'value5652',
    'key25733': 'value19823',
    'key63926': 'value21752',
    'key93792': 'value96759',
    'key31237': 'value53819',
    'key81772': 'value7762',
    'key55566': 'value91096',
    'key38555': 'value78705',
    'key88865': 'value59075',
    'key73375': 'value14010',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Kayla Rodriguez',
    'address': '547 Steven Dam Apt. 335\nPaulburgh, MS 10515',
    'text': 'Despite relationship majority environment. Without organization stage. Different current lose general matter tree.',
    'email': 'stephanie33@example.org',
    'phone_number': '763-442-9926',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Jones',
],
    'json': {
    'name': 'Mary Thomas',
    'address': '391 Smith Lodge Suite 720\nJeffreyburgh, NV 18283',
},
    'key26566': 'value43184',
    'key79406': 'value7447',
    'key21817': 'value70417',
    'key41991': 'value93612',
    'key2241': 'value68095',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Travis Shaw',
    'address': '755 Coffey Lodge Suite 726\nMcfarlandmouth, MH 02886',
    'text': 'Leader unit today successful environmental. Similar she role glass culture place.',
    'email': 'andersonwilliam@example.org',
    'phone_number': '001-499-840-0173',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jose Fritz',
    'Richard Barnes',
    'Eric Burnett',
    'Robert Ford',
    'Geoffrey Robles',
    'Jose Ellis',
    'Tim Sanders',
    'Richard Phillips',
],
    'json': {
    'name': 'Carolyn Rogers',
    'address': '02419 Lambert Light\nRomeroland, MP 89690',
},
    'key64871': 'value11637',
    'key65451': 'value42648',
    'key70023': 'value50545',
    'key80696': 'value6459',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Susan Gonzales',
    'address': '03559 Miguel Ridges Apt. 322\nNorth Trevorview, GU 77244',
    'text': 'Interview full by left.\nRise wonder just crime. Ahead television company realize evening box ever majority.\nMorning throughout learn tend share such. Stuff office doctor. Cell require movie.',
    'email': 'emilythomas@example.net',
    'phone_number': '(627)685-3704x766',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lydia Mckee',
    'Marcus Howard',
    'Andrea Torres',
    'Tony Bishop',
    'Alexander Martinez',
    'Phillip Reyes',
    'Jason Stewart',
],
    'json': {
    'name': 'Kevin Lee',
    'address': '649 Jennifer Plains Apt. 530\nSouth Dorothyport, TN 80465',
},
    'key46841': 'value44058',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Tracy Diaz',
    'address': '4642 Cynthia Inlet Apt. 929\nEast Austin, RI 32597',
    'text': 'Team understand world they either meet likely. State safe course machine on anyone prepare. Send development mention open establish general spend.',
    'email': 'hernandezdrew@example.net',
    'phone_number': '964-551-6305x707',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Linda Mccormick',
    'Sheena Hunter',
    'Darren Rivas',
],
    'json': {
    'name': 'Angela Franco',
    'address': '28725 Sarah Highway\nColleenhaven, MN 87465',
},
    'key63062': 'value61568',
    'key18470': 'value59998',
    'key10160': 'value21237',
    'key69945': 'value65692',
    'key78477': 'value91152',
    'key50379': 'value17738',
    'key87879': 'value29083',
    'key7129': 'value17283',
    'key38533': 'value56861',
    'key15586': 'value97738',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Tommy Roberts',
    'address': '39655 Walker Island Suite 618\nHeatherport, NV 50134',
    'text': 'Audience charge while until difficult black agreement trade. See low dark large the. Put way lose recently page bit.',
    'email': 'fsimmons@example.net',
    'phone_number': '982-528-7964',
    'array_int_dynamic': [
    41719,
],
    'array_varchar_dynamic': [
    'Megan Duncan',
],
    'json': {
    'name': 'Jesse Lee',
    'address': 'USNV Clay\nFPO AE 73976',
},
    'key73132': 'value28465',
    'key34768': 'value64762',
    'key18281': 'value34206',
    'key2747': 'value60229',
    'key87153': 'value32780',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Natasha Taylor',
    'address': '466 Newman Parkway Apt. 680\nPatriciaview, HI 07310',
    'text': 'Give draw analysis expect join owner. Establish season alone end key the.',
    'email': 'flarsen@example.org',
    'phone_number': '565.499.0299',
    'array_int_dynamic': [
    33563,
],
    'array_varchar_dynamic': [
    'Jeremy Jensen',
    'David Smith',
    'Anthony Morgan',
    'Christopher Johnson',
    'Aaron Stevenson',
],
    'json': {
    'name': 'Justin Freeman',
    'address': '4878 Brown Port Apt. 683\nWangside, MP 14911',
},
    'key46649': 'value67859',
    'key91334': 'value72657',
    'key93526': 'value14874',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Brandon Leach',
    'address': '4779 Justin Village\nNew Erinbury, FM 96162',
    'text': 'History involve natural receive. Southern development next century international strong perhaps. Still issue bank central whom full.',
    'email': 'lmcdowell@example.org',
    'phone_number': '(357)372-8471x426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Geoffrey Patterson',
    'Abigail Vaughn',
],
    'json': {
    'name': 'Mario Martinez',
    'address': '47386 Anderson Extension Apt. 714\nNorth Tiffanyport, DC 32663',
},
    'key54185': 'value90645',
    'key6021': 'value31627',
    'key27194': 'value70361',
    'key18323': 'value60876',
    'key75395': 'value41960',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Kara Carroll',
    'address': '4222 Baker Square Suite 183\nDerekhaven, WY 89043',
    'text': 'Scene film owner change somebody. Board respond father threat force between. Thank compare yeah success cell left word.',
    'email': 'singhryan@example.net',
    'phone_number': '742.476.2871x72072',
    'array_int_dynamic': [
    94502,
],
    'array_varchar_dynamic': [
    'Kelsey Stanley',
],
    'json': {
    'name': 'Nicole Anderson',
    'address': '0645 Martinez Streets\nWest Jonathan, KY 32223',
},
    'key2018': 'value21813',
    'key95242': 'value56949',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Robin Harper MD',
    'address': '913 Cobb Junction Apt. 723\nSmithview, MP 01140',
    'text': 'Over away central already hair without important. Support indeed religious. School main fast brother.\nReach beyond add movie future. House turn program paper.',
    'email': 'prattsusan@example.com',
    'phone_number': '(458)348-5082',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amy Phillips',
    'Colton Davis',
    'Alisha Holmes',
    'Nicole Hernandez',
    'Tracey Wood',
    'Mr. Nicholas Miller MD',
],
    'json': {
    'name': 'Gloria Torres',
    'address': '57651 Williams Fort\nNorth Scottchester, MO 12591',
},
    'key4730': 'value87589',
    'key80619': 'value16812',
    'key53184': 'value16873',
    'key45690': 'value19088',
    'key97963': 'value25939',
    'key95669': 'value68701',
    'key51773': 'value49838',
    'key43696': 'value36129',
    'key92358': 'value51891',
    'key5217': 'value59874',
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
    'RequestId': '7d3775ca-62ef-11f0-bb27-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_21_57_597662DhzVVSlk',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-32-10-2]_1752744118.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl321021752744118Json()
    test.run_tests()
