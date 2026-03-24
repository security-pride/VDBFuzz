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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-1]_1752744141_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-1]_1752744141.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId1281011752744141Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-1]_1752744141.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-1]_1752744141.json"
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
    'RequestId': '8ac42a52-62ef-11f0-a642-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_20_330168LFEWPNuj',
    'dimension': 128,
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
    'RequestId': '8acb29b3-62ef-11f0-ab96-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_20_330168LFEWPNuj',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Alan Jones',
    'address': '4796 Bryant Crest\nSamueltown, RI 67440',
    'text': 'Such theory lot forward defense. Along deal all teacher.\nAdd produce write run affect. Interesting during leader think certain difference.',
    'email': 'laura86@example.net',
    'phone_number': '676.728.8858x2758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Reed',
    'Michael Cruz',
    'Olivia Mitchell',
],
    'json': {
    'name': 'Robert Hicks',
    'address': '092 Woodward Springs\nJohnnystad, AR 31651',
},
    'key72787': 'value35367',
    'key68788': 'value29844',
    'key18841': 'value20467',
    'key35684': 'value81592',
    'key95702': 'value68621',
    'key20344': 'value49775',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Mary Holloway',
    'address': 'USS Thompson\nFPO AP 24419',
    'text': 'Employee practice stuff should decision. Finally production mission century clear sea gun. Final affect mention keep wall behind recent.',
    'email': 'jenkinsnicole@example.net',
    'phone_number': '242.462.6287x14190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Heather Roberts',
    'Alejandra Riggs',
    'Ashley Lowe',
    'Linda Esparza',
    'Joshua Alvarez',
    'Kimberly Le',
    'Crystal Obrien',
    'Ryan Vaughn',
],
    'json': {
    'name': 'Danielle Gonzalez',
    'address': '92706 Henry Port\nEast Heather, PR 98799',
},
    'key49673': 'value65968',
    'key50269': 'value9121',
    'key27676': 'value66283',
    'key11637': 'value972',
    'key61974': 'value93066',
    'key88233': 'value44936',
    'key40822': 'value80460',
    'key82717': 'value77775',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Michele Wood',
    'address': '4900 Manuel Throughway\nBerryberg, LA 31673',
    'text': 'Service statement score size. Foreign remember activity themselves commercial through position.\nWrong by the others general source ground. Step third professor entire better wrong east.',
    'email': 'jessicahood@example.net',
    'phone_number': '(428)421-3715',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Luna',
    'Ryan Cooper',
    'James Logan',
    'Michael Lawrence',
    'Ross Bennett',
    'Ryan Lawrence',
    'Chad Arnold',
    'Michael Stephens',
    'Tiffany Farrell',
],
    'json': {
    'name': 'Katherine Allen',
    'address': '64827 Allen Ports Apt. 120\nSouth Teresaland, MS 62269',
},
    'key11753': 'value50841',
    'key13295': 'value76376',
    'key76680': 'value66226',
    'key98725': 'value62143',
    'key37289': 'value20989',
    'key13700': 'value46',
    'key1557': 'value56919',
    'key35781': 'value56418',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Angela Larson',
    'address': '480 Brian Streets Suite 490\nGomezbury, RI 81563',
    'text': 'Deal argue market. Fund senior appear school value deal.\nSimple allow him arm red. Between herself energy surface wonder truth.\nNice want sell it. Move door set sure.',
    'email': 'whitechristopher@example.net',
    'phone_number': '+1-984-447-8129x450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Adam Summers',
    'Robert Hays',
],
    'json': {
    'name': 'Andrea Pope',
    'address': '16416 Watts Ridges Suite 151\nChavezburgh, LA 86612',
},
    'key85863': 'value82120',
    'key46849': 'value38381',
    'key3502': 'value6980',
    'key39963': 'value12372',
    'key62008': 'value60676',
    'key46838': 'value61472',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Amber Wilson',
    'address': 'PSC 3555, Box 7130\nAPO AP 68801',
    'text': 'Reality where serious fear. Old start develop my.',
    'email': 'pamela02@example.org',
    'phone_number': '793-480-7119',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Charles Gordon',
    'Kristine Martin',
    'Jackie Oliver',
    'Sarah Davies',
    'Joseph Meza',
    'Jason Velasquez',
    'Amanda Washington',
],
    'json': {
    'name': 'Mary Thomas',
    'address': '0136 Hanson Forges Apt. 863\nBasschester, ME 14443',
},
    'key9380': 'value7385',
    'key57586': 'value11564',
    'key35196': 'value93092',
    'key62250': 'value21073',
    'key42134': 'value62332',
    'key50232': 'value64097',
    'key43882': 'value88899',
    'key2205': 'value77248',
    'key26650': 'value49494',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Todd Koch',
    'address': 'USNV Hudson\nFPO AA 90889',
    'text': 'Factor into reveal relationship film. It administration last hand. Their official food go see.\nCollection relate himself data hit. Class buy himself candidate part.',
    'email': 'benjaminsmith@example.net',
    'phone_number': '390.495.2332x22559',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Joseph',
    'Casey Harris',
    'Matthew Levine',
    'Ariana Harris',
    'Andrea Jensen',
],
    'json': {
    'name': 'Yvonne Sanchez',
    'address': '41204 Fuller Forest Apt. 688\nMarybury, PA 15044',
},
    'key55481': 'value36666',
    'key59388': 'value587',
    'key26419': 'value14241',
    'key30801': 'value98552',
    'key31358': 'value32111',
    'key40532': 'value28146',
    'key49783': 'value14257',
    'key39856': 'value30756',
    'key55962': 'value22156',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kelly Lopez',
    'address': '3847 Cox Mall\nRobertsstad, GU 05934',
    'text': 'Success local word seat. Remain range but matter. Wide claim son majority reduce lay deep.\nOn process say machine claim politics season.',
    'email': 'imitchell@example.org',
    'phone_number': '+1-947-430-2032',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Angela Guerrero',
    'Susan Thompson',
    'Amber Smith',
],
    'json': {
    'name': 'Bailey Black',
    'address': '666 Hannah Hills\nNew Melissamouth, CA 57562',
},
    'key87624': 'value96985',
    'key34287': 'value38996',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'David Shepherd',
    'address': '6255 Paul Station Apt. 167\nArmstrongstad, OK 24611',
    'text': 'Price require cover me option race today. Lead state carry its do avoid.\nHigh reduce nation high somebody. Unit they pay cell great. Use wish south room new blue wind.',
    'email': 'amy40@example.org',
    'phone_number': '001-934-826-2100x3115',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica French',
    'Kim Vazquez',
    'Edward Howell',
],
    'json': {
    'name': 'Tiffany Macias',
    'address': '693 Christopher Crest\nBrownfurt, UT 31037',
},
    'key96623': 'value6945',
    'key47283': 'value71368',
    'key5630': 'value4189',
    'key83144': 'value90188',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Russell King MD',
    'address': '7501 Joseph Spur\nSouth Martin, WV 04302',
    'text': 'Leg low compare upon. Set talk general professional bill crime nature food. Work buy trip behind.\nBreak during bag she talk condition. Summer too culture name likely learn impact.',
    'email': 'janderson@example.net',
    'phone_number': '700.237.5755x026',
    'array_int_dynamic': [
    87052,
],
    'array_varchar_dynamic': [
    'Jeffrey Murillo',
    'Scott Miller',
    'Samantha Moran',
    'Clifford Henderson',
    'Jason Valenzuela',
    'Melinda Mcdonald',
],
    'json': {
    'name': 'Kimberly Maxwell',
    'address': 'USNV Rivers\nFPO AA 04085',
},
    'key36620': 'value64876',
    'key54843': 'value18520',
    'key12559': 'value27689',
    'key20676': 'value80771',
    'key47644': 'value35306',
    'key42926': 'value38093',
    'key10389': 'value88332',
    'key66183': 'value81836',
    'key8068': 'value12865',
    'key29719': 'value98764',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Mrs. Natasha Jensen',
    'address': 'Unit 5614 Box 3133\nDPO AE 67082',
    'text': 'Environmental those the modern majority call tend interview. All treat short really bar thank. Cause bag since treat subject voice.\nHospital thing owner yet. Keep must college never you real.',
    'email': 'brocksteven@example.com',
    'phone_number': '(344)826-3755x0854',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Scott',
    'David Crane',
    'Nathaniel Rosales',
    'James Taylor MD',
    'William Martinez',
    'Michelle Brown',
    'Richard Martinez',
],
    'json': {
    'name': 'Anna Hernandez',
    'address': '387 Anthony Cliffs\nNew Bridgetport, AZ 11927',
},
    'key42622': 'value90627',
    'key54905': 'value91456',
    'key64468': 'value92181',
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
    'RequestId': '8ac42a52-62ef-11f0-a642-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_20_330168LFEWPNuj',
    'dimension': 128,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-10-1]_1752744141.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId1281011752744141Json()
    test.run_tests()
