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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-2]_1752744137_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-2]_1752744137.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId12810021752744137Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-2]_1752744137.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-2]_1752744137.json"
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
    'RequestId': '884249ca-62ef-11f0-b302-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_16_123556NCkGXNvk',
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
    'RequestId': '88667b74-62ef-11f0-bbe7-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_16_123556NCkGXNvk',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Lisa Arias',
    'address': '83501 Robert Fields Suite 864\nHeatherfort, AS 06035',
    'text': 'Note garden issue. Newspaper loss room ever type feel.\nRate of also responsibility. Claim current word difference according season.',
    'email': 'angela63@example.org',
    'phone_number': '001-464-964-0430',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Lewis',
    'Wesley Young',
    'Monica Ortega',
    'Patrick Ray',
],
    'json': {
    'name': 'Kimberly Adams',
    'address': 'PSC 0011, Box 2802\nAPO AA 89587',
},
    'key42': 'value71033',
    'key81518': 'value93726',
    'key50333': 'value23177',
    'key67126': 'value56576',
    'key61846': 'value55031',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sharon Mcdonald',
    'address': '654 Thomas Groves\nCochranberg, CA 33865',
    'text': 'Themselves court structure. Manage west population build work behavior. Mean change medical agreement go land.\nStandard throughout the language. Door impact recent true marriage.',
    'email': 'christopher95@example.net',
    'phone_number': '001-845-805-6001x452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Johnson',
    'Derrick Price',
    'Sandra Brooks',
    'James Jenkins',
    'Elizabeth Rodriguez',
    'Jessica Shepherd',
    'Mark Hall',
    'Cole Barnett',
],
    'json': {
    'name': 'Michelle Collins',
    'address': '39512 Becky Harbor Apt. 484\nLake Matthewbury, SD 42421',
},
    'key36334': 'value60707',
    'key55373': 'value92426',
    'key66896': 'value84579',
    'key27629': 'value11093',
    'key65566': 'value70282',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Elizabeth Castillo',
    'address': '007 Mack Walks Suite 228\nPort Cynthia, TN 78960',
    'text': 'Election grow production and role upon. Current room short ability she toward into. Shake evidence cut inside author develop word. Police nation minute lose.',
    'email': 'joshuamcgrath@example.org',
    'phone_number': '(688)308-0087',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Mullins',
    'Brett Sanchez',
    'Miguel Smith',
    'Rita Benson',
    'Robert Blake',
    'Brittany Bryant',
    'Kim Shaw',
],
    'json': {
    'name': 'Elizabeth Evans',
    'address': 'PSC 5046, Box 7947\nAPO AE 34255',
},
    'key54422': 'value93656',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Teresa Taylor',
    'address': '3220 Kennedy Forges Suite 396\nSouth Corychester, MO 20721',
    'text': 'Different wrong soon be operation might least. White improve heart recently treat maybe.',
    'email': 'rodriguezolivia@example.com',
    'phone_number': '848.491.7339x6423',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Sweeney',
    'Tonya Parker',
    'Julie Clayton',
    'Ashley Murphy',
    'Samuel Moss',
    'Gina Robbins',
],
    'json': {
    'name': 'Anne Cooper',
    'address': '86418 Jocelyn Mills\nHebertview, HI 72227',
},
    'key48525': 'value45748',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Eric Johnson',
    'address': '7791 David Gateway Apt. 505\nNew Kim, ME 02173',
    'text': 'Enjoy field cold.\nWind agree seek idea parent couple threat. Action out debate director even. Point through mention understand.',
    'email': 'mariasexton@example.net',
    'phone_number': '+1-541-469-0230x6241',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Johnson',
    'Randall Duncan',
    'Wendy Waters',
    'Andrea Jenkins',
    'Sean Hall',
],
    'json': {
    'name': 'Devin Carpenter',
    'address': 'USCGC Lloyd\nFPO AP 48091',
},
    'key54654': 'value69962',
    'key88084': 'value91460',
    'key84563': 'value96996',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Sherry Obrien',
    'address': '0299 Evan Square\nColemanmouth, NY 23301',
    'text': 'Under night evening remember market. Paper exactly type figure analysis discuss artist. Prevent book play out five upon me life.\nRoad late hard action. Manager soldier American over wrong foot.',
    'email': 'michael44@example.org',
    'phone_number': '415.709.1129',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Palmer',
    'Briana Rice',
    'Joshua Green',
    'Eric Hubbard',
    'Mindy Wilson',
    'Melissa Conrad',
    'Andrew Fletcher',
    'Christine Vance',
],
    'json': {
    'name': 'Noah Barry',
    'address': '7185 Kimberly River Suite 217\nNorth Mistyborough, NJ 20153',
},
    'key75130': 'value55783',
    'key19824': 'value22585',
    'key24591': 'value22375',
    'key17396': 'value85252',
    'key16584': 'value33240',
    'key55834': 'value36563',
    'key52317': 'value80665',
    'key75394': 'value40614',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Sherry Booker',
    'address': '06808 Flores Mountains\nEast Christy, IA 33483',
    'text': 'Walk those popular century quality skill. There kitchen word last. Allow positive poor support former.',
    'email': 'teresa19@example.com',
    'phone_number': '001-259-401-8507x9896',
    'array_int_dynamic': [
    51897,
],
    'array_varchar_dynamic': [
    'Jennifer Shah',
    'Jesus Brock',
    'Aaron Moreno',
    'Danielle White',
    'Kendra Zamora',
    'Carol Hartman',
    'Jeremy Smith',
    'Jasmine Brown',
    'Peter Perez',
    'Laura Taylor',
],
    'json': {
    'name': 'Rose Terrell',
    'address': '432 Heather Hill\nBrownville, MH 78801',
},
    'key91675': 'value41756',
    'key17913': 'value15724',
    'key34831': 'value61955',
    'key5983': 'value88608',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Amber Taylor',
    'address': '37737 Ashley Rest\nJustinview, WI 96653',
    'text': 'Many each they human significant. South under eat food local. Similar everyone both material next so worker.\nTeacher late material partner close time. Table challenge follow inside kitchen million.',
    'email': 'stephaniegoodwin@example.net',
    'phone_number': '6428568349',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Monica Jordan',
    'Renee Andrews',
    'James Ibarra',
],
    'json': {
    'name': 'Leslie Johnson MD',
    'address': 'Unit 7024 Box 1127\nDPO AE 28750',
},
    'key36699': 'value57600',
    'key68887': 'value40040',
    'key54862': 'value18872',
    'key73082': 'value15326',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Casey Li',
    'address': '522 Bass Row\nWest Juliestad, VA 43793',
    'text': 'Bed score rate boy arm institution. Think successful often crime standard serious.\nSeason final education result. Attention citizen society as sell. Social three they off or pressure.',
    'email': 'zacharyevans@example.org',
    'phone_number': '001-527-454-3190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Nelson',
],
    'json': {
    'name': 'Benjamin Wilson',
    'address': '4896 Reynolds Cove Apt. 358\nStephaniebury, GA 72739',
},
    'key55807': 'value94531',
    'key6281': 'value7240',
    'key92224': 'value15816',
    'key88604': 'value71043',
    'key18880': 'value45600',
    'key8151': 'value72788',
    'key14892': 'value96476',
    'key13933': 'value87365',
    'key17069': 'value10914',
    'key85314': 'value98647',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Jessica Bowman',
    'address': '86646 Underwood Estates Apt. 753\nNicholsfort, DC 85296',
    'text': 'Car visit cut happen during sport either. Very and huge all. More car possible center hotel happy.\nFormer put clearly trade Mr follow which. Focus recent success film since center fear maybe.',
    'email': 'westangela@example.com',
    'phone_number': '001-760-721-3251x8102',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Allen',
    'Jaclyn Rogers',
    'Luis Whitaker',
    'Terry Carey',
    'Amanda Reed',
    'Makayla Davis',
],
    'json': {
    'name': 'John Ramos',
    'address': 'Unit 7681 Box 5366\nDPO AE 87306',
},
    'key70440': 'value50833',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Heather Reilly',
    'address': '65861 Cody Drives\nAbigailmouth, CO 64311',
    'text': 'Peace eat clearly also effect this. Still hour PM low girl.\nEye tax he pay in. Finish old see nothing add develop require common.',
    'email': 'raymondnelson@example.com',
    'phone_number': '001-767-413-7598x444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Castillo',
    'Christopher Jackson',
    'Crystal Acosta',
    'James Kim',
    'Sarah Wagner',
],
    'json': {
    'name': 'Joy Robinson',
    'address': '41441 Daniel Lodge\nKathrynstad, IL 53529',
},
    'key39058': 'value1264',
    'key74232': 'value70210',
    'key6288': 'value61898',
    'key33509': 'value19518',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Michael Miller',
    'address': '415 Thomas Way\nSouth David, WY 06628',
    'text': 'Notice exactly season quite before middle worker better. Significant political sure adult PM health.',
    'email': 'deborahlopez@example.org',
    'phone_number': '+1-913-211-3196x76888',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Heather Ramirez',
],
    'json': {
    'name': 'Phillip Mcfarland',
    'address': '2995 Robert Unions Suite 343\nLake Kristen, WV 17256',
},
    'key44806': 'value10864',
    'key62334': 'value90436',
    'key18191': 'value39879',
    'key48689': 'value45342',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Vanessa Yates',
    'address': '856 Scott Villages Apt. 013\nLake Andrew, PR 17232',
    'text': 'So employee scientist prepare various five. Along site form too. Thought summer evidence main pattern high front.',
    'email': 'charleslopez@example.org',
    'phone_number': '278.698.1707x95509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Harold Meadows',
    'Joan Stevens',
    'Erik Christian',
    'Diana Griffin',
    'Dana Watkins',
    'Kayla Baker',
    'Henry Morales',
],
    'json': {
    'name': 'Jennifer Morrow',
    'address': '13787 Lance Orchard\nLisaburgh, OH 19487',
},
    'key29312': 'value81615',
    'key49031': 'value30893',
    'key12915': 'value54388',
    'key47953': 'value88426',
    'key46507': 'value47230',
    'key12937': 'value20421',
    'key33392': 'value22288',
    'key68027': 'value60862',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Debbie Rowe',
    'address': '301 Mccullough Plains\nHopkinsmouth, TN 53628',
    'text': 'Idea another project itself politics suffer fast. Money American others ok. Mind suddenly play cost work itself central.',
    'email': 'obecker@example.org',
    'phone_number': '500.253.7014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Benson',
],
    'json': {
    'name': 'James Daniels',
    'address': 'PSC 4096, Box 0876\nAPO AP 27327',
},
    'key71493': 'value11169',
    'key4739': 'value45361',
    'key29922': 'value40804',
    'key63685': 'value51807',
    'key48233': 'value77807',
    'key42967': 'value43314',
    'key57592': 'value92504',
    'key72125': 'value82257',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Stuart Ayala',
    'address': '37774 Kurt Stream\nRebeccastad, MO 68539',
    'text': 'Final painting want center. Note either worry might black join. Peace ability administration fact section this.\nFor former theory record. Around pick future head take spring exactly.',
    'email': 'manndavid@example.net',
    'phone_number': '+1-763-371-2757x06229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Compton',
    'Ashley Thomas',
    'Joshua Mendoza',
    'Ricardo Lynch',
    'Stephen Edwards',
    'Tyler Patterson',
],
    'json': {
    'name': 'Richard Cunningham',
    'address': '7876 Edward Crescent\nNorth Danielland, UT 39702',
},
    'key35242': 'value88908',
    'key86901': 'value53543',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jonathan Mercado',
    'address': 'Unit 4023 Box 9134\nDPO AP 02208',
    'text': 'A tonight or wear. Hair look another local service word office throughout. Work sometimes in generation parent remember Mr.\nSort trade plant become. Above international by husband large Congress.',
    'email': 'anthony46@example.com',
    'phone_number': '9233301967',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Hood',
],
    'json': {
    'name': 'Jose Young',
    'address': '17459 Meredith Loop\nWebbmouth, CA 07217',
},
    'key61056': 'value12753',
    'key84482': 'value21012',
    'key57162': 'value79550',
    'key20596': 'value65172',
    'key30080': 'value51530',
    'key39038': 'value29886',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Joseph Flores',
    'address': '715 Melissa Street Suite 887\nLake Joseph, OH 73079',
    'text': 'Well something camera than big. Development evidence doctor remain.\nNor shake plant radio explain hope.\nSeat wait do general important. Power law standard worry responsibility.',
    'email': 'veronicarogers@example.net',
    'phone_number': '242.885.4810x09363',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Amber Morales',
    'Leonard Huff',
    'David Cordova',
    'Natalie Li',
    'Shelly Mills',
    'Amy Wagner',
],
    'json': {
    'name': 'Blake Maxwell',
    'address': '639 Adkins Trafficway\nJoshuaberg, RI 88537',
},
    'key59953': 'value46162',
    'key64551': 'value34122',
    'key91159': 'value42716',
    'key51012': 'value39194',
    'key66437': 'value60944',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Robin Thomas',
    'address': '448 Antonio Bypass Suite 091\nLewisbury, FM 05057',
    'text': 'Group forget someone reflect owner hit. Decide list rise education nation against around. Remember hour would.\nOnto available use role institution single base add. Modern go for pull land maintain.',
    'email': 'coreykennedy@example.org',
    'phone_number': '(587)222-3223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Butler',
    'Patricia Fisher',
    'Xavier Pennington',
    'Penny Johnson',
],
    'json': {
    'name': 'Steven Torres',
    'address': 'Unit 8424 Box 0643\nDPO AA 95745',
},
    'key71011': 'value44170',
    'key84933': 'value96405',
    'key7988': 'value70288',
    'key44732': 'value33694',
    'key42016': 'value38811',
    'key76211': 'value82358',
    'key15807': 'value6044',
    'key89536': 'value28416',
    'key84526': 'value71419',
    'key58148': 'value87510',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Terry Vasquez',
    'address': '47050 Kristen Brooks Apt. 863\nThompsonstad, OK 09543',
    'text': 'Plant technology change. Improve interest especially north. Particularly third follow employee.\nPolice which table policy everything understand life us. Team lay weight organization hundred.',
    'email': 'wesley70@example.net',
    'phone_number': '411-448-9356',
    'array_int_dynamic': [
    68800,
],
    'array_varchar_dynamic': [
    'Megan Romero',
    'Mark Best',
    'Melanie Meyer',
],
    'json': {
    'name': 'Joseph Newton',
    'address': '8477 Michael Forks\nMirandachester, DC 77603',
},
    'key2514': 'value85955',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Melissa Bennett',
    'address': '4540 Smith Ports\nEast Trevorland, IL 46131',
    'text': 'Nearly church writer reveal couple organization.\nInvolve some down mouth course debate return. Wrong ever into unit.',
    'email': 'evansmichael@example.com',
    'phone_number': '+1-244-938-8074x9409',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Wilson',
    'Leah Castro',
    'Shawn Benson MD',
    'Jordan Bass',
],
    'json': {
    'name': 'Philip Lutz',
    'address': 'PSC 1881, Box 2479\nAPO AE 63701',
},
    'key34367': 'value19040',
    'key25301': 'value94851',
    'key25450': 'value8151',
    'key94917': 'value39885',
    'key22063': 'value43868',
    'key82332': 'value18987',
    'key32563': 'value53170',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Joshua Higgins',
    'address': '2931 Smith Circle Apt. 194\nVasquezburgh, MA 23751',
    'text': 'Great company voice. Level star kitchen high base Congress. Bank every often school number lot she.',
    'email': 'mcphersontracy@example.org',
    'phone_number': '001-677-751-0286x93435',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tracey Anderson',
    'Michelle Davis',
    'Terri Dennis',
    'Matthew Jackson',
],
    'json': {
    'name': 'Patrick Rodriguez',
    'address': '80784 Cameron Lodge Apt. 909\nNew Rhondaside, KS 33601',
},
    'key63701': 'value56672',
    'key6731': 'value45556',
    'key53674': 'value46417',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jennifer Henry',
    'address': '746 Bradley Port\nNorth Jeanneport, AL 60730',
    'text': 'Court teacher treatment. Lose look treatment position nice sing. Stop on human sell yet war computer.',
    'email': 'breynolds@example.net',
    'phone_number': '(648)817-0956x49478',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Le',
    'Kevin Campbell',
    'Douglas Moore',
],
    'json': {
    'name': 'Cindy Rowe',
    'address': '5894 Tonya Ports Apt. 083\nNorth Melissastad, VA 45878',
},
    'key73810': 'value40088',
    'key55731': 'value25232',
    'key15569': 'value15216',
    'key24782': 'value68672',
    'key5130': 'value89614',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Timothy Neal',
    'address': '56104 Tyler Stream Suite 215\nNew Gina, NM 86988',
    'text': 'Up many sport contain field population visit. Bit set look house movie everyone threat.',
    'email': 'kimberly18@example.net',
    'phone_number': '4048031724',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jasmin Lowe',
],
    'json': {
    'name': 'Kristine Powers',
    'address': '280 Howard Shoal Apt. 374\nSandovalchester, FM 97858',
},
    'key128': 'value13289',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Donald Mosley',
    'address': '80103 Amber Burg Suite 851\nRaymondborough, MI 48173',
    'text': 'Perform study shoulder force admit. Something challenge listen young. Draw recent law participant become hope radio.',
    'email': 'kimberlyhaas@example.net',
    'phone_number': '461-626-8332x996',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Theodore Adams',
    'George Ross',
],
    'json': {
    'name': 'Susan Robinson',
    'address': '747 Wilson Hollow Suite 135\nWilliamstown, MP 99460',
},
    'key25367': 'value32353',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Craig Cantrell',
    'address': '942 Roy Fork\nPort Sarachester, MA 06020',
    'text': 'Raise sing skill believe worker everybody. President interesting skin not.\nFirm base current process my. Gun mean own. You amount expect.',
    'email': 'qallen@example.net',
    'phone_number': '(355)351-5638x950',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Regina Anderson DVM',
    'Karen George',
    'Tamara Mora',
    'James Perez',
    'Desiree Estrada',
],
    'json': {
    'name': 'Thomas Tanner',
    'address': '753 Seth Summit\nWest Thomas, AL 38460',
},
    'key81152': 'value13398',
    'key26040': 'value20793',
    'key52268': 'value40353',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Christina Young',
    'address': '828 Townsend Junction Apt. 272\nAndreaport, VA 47640',
    'text': 'Care life writer growth. Meet value successful paper performance.\nDinner house education do. Idea firm a.\nHeart trade will yeah none. Exist here off whether relate field. Water western foreign.',
    'email': 'jonathanhenderson@example.com',
    'phone_number': '+1-413-665-8882x733',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lawrence Jones',
],
    'json': {
    'name': 'William Martin',
    'address': '020 Richards Unions Suite 277\nMonicastad, MH 92268',
},
    'key15539': 'value81842',
    'key60496': 'value96206',
    'key50023': 'value41122',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Seth Mcconnell',
    'address': '4464 Hale Streets Suite 544\nMatthewshire, OH 03859',
    'text': 'Important business act partner. Maybe now current still interview way.\nProject tough war oil. Have young throughout difficult.\nLetter order mother across remain five. Today without right property.',
    'email': 'michaelcampos@example.com',
    'phone_number': '+1-556-227-8214x152',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Erik Jordan',
    'Jessica Lyons',
    'Jeffery Palmer',
    'Daniel Soto',
    'Sarah Davis',
    'Amanda Rose',
],
    'json': {
    'name': 'Katie Bates',
    'address': '7858 Mason Stream Suite 105\nAshleyburgh, HI 87234',
},
    'key21248': 'value90792',
    'key66762': 'value8878',
    'key6544': 'value99907',
    'key4764': 'value419',
    'key27219': 'value4553',
    'key85218': 'value67800',
    'key83564': 'value36362',
    'key19736': 'value34949',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jeffery Mccoy',
    'address': '877 Alexis Dale\nLake Dakota, AZ 66976',
    'text': 'Window south measure speech peace data. Fish land that focus. Happy understand way arm serious list region.\nStage pick well floor.',
    'email': 'karenallison@example.org',
    'phone_number': '453.660.7466x63549',
    'array_int_dynamic': [
    96329,
],
    'array_varchar_dynamic': [
    'Mitchell Byrd',
    'Susan Foster',
    'Deanna May',
    'Franklin Gutierrez',
    'Ana Escobar',
    'Rose Jones',
    'Michael Robertson',
],
    'json': {
    'name': 'Susan Alexander',
    'address': '89000 Rickey Valleys Apt. 377\nJohnsonborough, ID 98180',
},
    'key16093': 'value6646',
    'key57244': 'value19472',
    'key24319': 'value59509',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Joshua Lewis',
    'address': '510 Lester Highway Apt. 687\nNorth Adam, RI 45077',
    'text': 'Become difficult whatever security. Never my financial president hair despite civil.\nEnjoy hold player scene force own partner. Able build get money. Whose ability ready organization art.',
    'email': 'kevinhurley@example.org',
    'phone_number': '774-202-5404x3994',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christian Taylor',
    'Olivia Lane',
    'Mark Smith',
    'Joseph Smith',
    'Veronica Thompson',
    'James Rodriguez',
    'Lori Blair',
    'William Henson',
    'Jessica Rodriguez',
],
    'json': {
    'name': 'Russell Ryan',
    'address': '5994 Erik Forges\nEast Sarahfurt, MO 21294',
},
    'key44620': 'value53352',
    'key62915': 'value96346',
    'key28507': 'value26952',
    'key48878': 'value66154',
    'key16219': 'value92913',
    'key2995': 'value36591',
    'key89033': 'value98700',
    'key3162': 'value47769',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Brittany Singleton',
    'address': '622 Jackson Rest\nWest Monicaburgh, PA 61396',
    'text': 'Read meeting treatment follow maintain. Artist even focus education fill series share.',
    'email': 'vphelps@example.net',
    'phone_number': '001-646-357-8977x32738',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Keith Larson',
    'Peter Morales',
    'Paula Hubbard',
    'Amanda Edwards',
    'George Trujillo',
    'Mitchell Simmons',
],
    'json': {
    'name': 'Jodi Harris',
    'address': '37879 Hernandez Course Apt. 772\nCollinsburgh, KS 69134',
},
    'key78133': 'value81782',
    'key13838': 'value80922',
    'key70658': 'value54813',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Ashley Shaw',
    'address': 'Unit 5304 Box 7669\nDPO AP 62323',
    'text': 'Continue start well change later performance the.\nDark apply Mrs event nature.\nScore meeting six religious training main anything arrive.',
    'email': 'michaelburns@example.net',
    'phone_number': '001-308-965-2848',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'David Davis',
    'Pam Fleming',
    'Michelle Turner',
    'Stephanie Cervantes',
    'Jennifer Henry',
    'Peter Clark',
    'Kenneth Peters',
    'Richard Montoya',
],
    'json': {
    'name': 'Mary Warner',
    'address': 'PSC 6621, Box 8095\nAPO AP 54876',
},
    'key8049': 'value50111',
    'key34150': 'value25767',
    'key83103': 'value77662',
    'key88121': 'value18569',
    'key34493': 'value11798',
    'key7017': 'value55488',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Brian Schmidt',
    'address': '117 Joshua Rest\nNorth Diane, NJ 46832',
    'text': 'Wait see to manager. Item by program reflect professor time. Clearly compare second them charge five.',
    'email': 'yvetteandrews@example.org',
    'phone_number': '820-384-9260x38238',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Barrera',
    'John Lang',
    'John Smith',
    'Samuel Morgan',
    'Molly Sherman',
    'Nicholas Smith MD',
    'Brian Huff',
    'Jose Porter',
    'Mallory Sanchez',
],
    'json': {
    'name': 'Maria Davis',
    'address': '9793 Mueller Loaf\nMillshaven, PW 69912',
},
    'key33337': 'value37479',
    'key61455': 'value64502',
    'key77728': 'value85677',
    'key51970': 'value37459',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Steven Boyle',
    'address': '2743 Sarah Stream\nWest Josephport, SC 39272',
    'text': 'Early media onto miss try. Challenge next organization international. Smile national act training.\nMake never all southern newspaper study model. Stock room coach red either skill.',
    'email': 'jamesrhodes@example.com',
    'phone_number': '+1-555-442-7652x4386',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Rodriguez',
    'Thomas Reed',
    'Richard Jones III',
    'Amber Smith',
    'Matthew Cantrell',
],
    'json': {
    'name': 'Roy Collins',
    'address': '23574 Emily Fort Suite 926\nWest Elizabethmouth, AZ 60472',
},
    'key53877': 'value95421',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Elizabeth Hughes',
    'address': '052 Kerri Points Apt. 742\nElizabethview, VT 23984',
    'text': 'Method develop similar simply. Material sometimes usually until experience view happen. Author sing appear religious citizen.',
    'email': 'joseday@example.org',
    'phone_number': '750.625.4600',
    'array_int_dynamic': [
    2363,
],
    'array_varchar_dynamic': [
    'Erica Weber',
],
    'json': {
    'name': 'Pamela May',
    'address': '488 Hayes Haven\nWilliamsonfurt, MP 61267',
},
    'key7680': 'value82562',
    'key90715': 'value19965',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Billy Myers',
    'address': '423 Williams Forks Apt. 569\nYoungmouth, ID 54048',
    'text': 'National enough experience single many future change. Door gun person various. After federal take happy.',
    'email': 'brian44@example.com',
    'phone_number': '+1-561-348-0873x02916',
    'array_int_dynamic': [
    57142,
],
    'array_varchar_dynamic': [
    'Suzanne Johnson',
    'Kevin Ritter',
    'Jordan Haney',
    'Mr. John Powers',
    'Kelly Harrington',
    'John Roberts',
],
    'json': {
    'name': 'Luke Ball',
    'address': '7514 Johnson Tunnel Suite 501\nRushburgh, MA 37219',
},
    'key5795': 'value95884',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'James Robinson',
    'address': '749 Anderson Mountain\nJohnsonland, RI 32828',
    'text': 'One home resource lead. Turn together group us from by.\nStore allow official identify apply. Country off smile nothing gas clear.',
    'email': 'mary27@example.com',
    'phone_number': '382.214.2256x6296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Dillon Williams PhD',
    'Olivia Becker',
    'Julia Miles',
    'Melissa Ramos',
],
    'json': {
    'name': 'Tracy Scott',
    'address': '556 Daniel Cliffs Apt. 289\nNealbury, GU 47273',
},
    'key3693': 'value17785',
    'key70792': 'value40043',
    'key28828': 'value37215',
    'key59714': 'value59419',
    'key19988': 'value94670',
    'key92965': 'value74584',
    'key55558': 'value22482',
    'key52622': 'value15734',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Crystal Washington',
    'address': '80252 Maria Ports Apt. 294\nWillisside, IL 03097',
    'text': 'Yourself difficult success cultural most news note. Public example impact national series generation stop line.\nLine specific north there. Pm operation his.',
    'email': 'christopher46@example.com',
    'phone_number': '732-981-7451x19069',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dana Morales',
    'Chad Curtis',
    'Frank Durham',
    'Sherry Nelson',
    'Mary Ross',
    'Tara Glass',
    'Patricia Smith',
    'Kathleen Wallace',
    'Janet Griffin',
],
    'json': {
    'name': 'Shannon Jones',
    'address': '968 Summer Common\nSamanthabury, CO 98512',
},
    'key13611': 'value23461',
    'key37459': 'value58505',
    'key8776': 'value21433',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Charles Wall',
    'address': '89582 Laura Parkways Apt. 798\nNorth Kerry, NV 94968',
    'text': 'Safe matter should little expert. Movement box mission box position picture fall.\nChance majority range with father top test. Parent work make. Water fish others.',
    'email': 'peter23@example.net',
    'phone_number': '350.255.8988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Heather Sanders',
    'Lori Phelps',
    'Shannon Kline',
    'Robert Carter',
    'Madison Ortiz',
    'Amy Schaefer',
],
    'json': {
    'name': 'Brent Mueller',
    'address': '227 Alexa Rapid Suite 045\nJesseville, OH 24292',
},
    'key42027': 'value70496',
    'key68241': 'value94701',
    'key26407': 'value41266',
    'key75968': 'value4074',
    'key71045': 'value86138',
    'key62284': 'value15115',
    'key41199': 'value7765',
    'key44076': 'value65695',
    'key74521': 'value7039',
    'key916': 'value11249',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'James Rivas',
    'address': '81840 Thomas Road Apt. 957\nNicholasville, HI 50659',
    'text': 'Wide somebody town movie. Source free claim Democrat able.\nName recent sometimes him girl method. Tree coach hand that.\nMay experience health city main interview how. Those red black.',
    'email': 'xcoffey@example.org',
    'phone_number': '(263)873-0498',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jonathon Hernandez',
    'Todd Baxter',
    'Mr. Andrew Mcclain',
    'Shawn Davenport',
    'Lindsay Villanueva',
],
    'json': {
    'name': 'Rachel Baker',
    'address': '3873 Jessica Summit Apt. 516\nEast Robertside, NV 74865',
},
    'key41541': 'value60324',
    'key10046': 'value69558',
    'key94924': 'value95891',
    'key84954': 'value56244',
    'key62968': 'value36234',
    'key65255': 'value79003',
    'key64768': 'value15665',
    'key13590': 'value95965',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Stacy Hale',
    'address': '0172 Taylor Island Apt. 913\nPort Tarahaven, SC 88351',
    'text': 'Owner real star. Rest especially enter fly. Answer machine message science win control positive.',
    'email': 'lisalawson@example.com',
    'phone_number': '(657)378-4664x155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Hayes',
    'Melinda Jackson',
    'Mark Wood',
    'Cesar Holloway',
    'Matthew Collins',
    'Brian Kelly',
],
    'json': {
    'name': 'Gerald Glenn',
    'address': '8739 Gutierrez Heights Apt. 600\nSouth Amber, PW 30959',
},
    'key65018': 'value52980',
    'key31466': 'value60182',
    'key10945': 'value43855',
    'key96938': 'value54721',
    'key43240': 'value39851',
    'key23864': 'value86652',
    'key53001': 'value47872',
    'key15856': 'value74198',
    'key16316': 'value88066',
    'key15834': 'value72173',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Bailey Bridges',
    'address': '9609 Antonio Glen\nNew Christinatown, ID 46082',
    'text': 'Anything appear mention. Increase test store best list attorney. Democratic people religious board on.',
    'email': 'thomasmichelle@example.org',
    'phone_number': '8136132794',
    'array_int_dynamic': [
    40903,
],
    'array_varchar_dynamic': [
    'Evelyn Brady',
    'Alyssa Holmes',
],
    'json': {
    'name': 'Mark Hughes',
    'address': '31446 Sara Light\nRobertmouth, NJ 46426',
},
    'key57840': 'value24384',
    'key27622': 'value44150',
    'key96449': 'value80486',
    'key18874': 'value82141',
    'key44456': 'value68215',
    'key55406': 'value23206',
    'key71654': 'value26863',
    'key13946': 'value74916',
    'key92258': 'value98135',
    'key70922': 'value63038',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Richard Berg',
    'address': '779 Samantha Groves\nSmithhaven, PR 62424',
    'text': 'Health dark TV quality draw low.\nOnce growth dog with almost. Marriage pay like movie from. Data lay organization.',
    'email': 'sara58@example.com',
    'phone_number': '884.772.7293x78469',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Holly Taylor',
    'Laura Montgomery',
    'David Thomas',
    'Lisa Mccullough',
    'Alicia Foster',
    'Dennis Myers',
    'Michael Richardson',
    'Teresa Thompson',
    'Jennifer Austin',
    'Ryan Watson',
],
    'json': {
    'name': 'Joseph Dominguez',
    'address': '50766 Webb Wells\nBrownland, OK 26480',
},
    'key96332': 'value59167',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Kristin Ramirez',
    'address': '083 Kathy Manor Apt. 438\nAnnaport, GU 20810',
    'text': 'Rule bad school. Attack she career gas. Hand player into keep think sit hospital.\nRecent right have rest part. Left never require common up food. Arm under recent model choose sea.',
    'email': 'natalie02@example.org',
    'phone_number': '+1-595-951-9832x293',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kristy Graves',
    'Teresa Chase',
    'Lisa Mccormick',
    'Todd Morrison',
    'David Wilson',
    'Lisa Pitts',
],
    'json': {
    'name': 'Scott Hughes',
    'address': '34015 Hawkins Grove Apt. 012\nLake Nathanburgh, AL 35429',
},
    'key60198': 'value95658',
    'key81024': 'value54399',
    'key16493': 'value33838',
    'key86696': 'value39924',
    'key33343': 'value87123',
    'key32192': 'value40119',
    'key40741': 'value21045',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Patricia Lutz',
    'address': '769 Harris Mission Apt. 479\nPort Yolandaton, NC 93450',
    'text': 'Church community pretty positive beat describe thousand. Own director economic born number.\nManage arm fight past. Life win different really. Draw discuss including child its school very.',
    'email': 'christopherdavis@example.org',
    'phone_number': '870.356.2230',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Evans',
    'Jessica Bush',
    'Vincent Hudson',
],
    'json': {
    'name': 'Jeffrey Madden',
    'address': '96869 Saunders Prairie\nMooreside, MT 49893',
},
    'key65467': 'value20906',
    'key75827': 'value10942',
    'key86453': 'value93207',
    'key30918': 'value11979',
    'key30968': 'value3548',
    'key28223': 'value70521',
    'key46552': 'value57947',
    'key72660': 'value35272',
    'key21070': 'value8580',
    'key96975': 'value11204',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Amy Mayo',
    'address': '99762 Smith Fords\nColemanport, VA 57907',
    'text': 'Present apply cause opportunity. Listen week without hospital boy.\nIt loss seven audience. Turn early play gas else themselves. Writer among tax.',
    'email': 'connercolton@example.org',
    'phone_number': '840.365.6329',
    'array_int_dynamic': [
    35958,
],
    'array_varchar_dynamic': [
    'Ronald Kennedy',
    'Angel Flores',
    'Kenneth Simmons',
    'Jade Bright',
    'Amanda Barrett',
    'Jessica Gordon',
],
    'json': {
    'name': 'Richard Chapman',
    'address': '1705 Carla Branch Apt. 980\nPort Sophiabury, IN 48501',
},
    'key87106': 'value72615',
    'key36134': 'value7465',
    'key78050': 'value82773',
    'key59031': 'value90421',
    'key53938': 'value86368',
    'key71718': 'value41877',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Andrew Andersen',
    'address': '612 Robert Plaza\nRusselltown, DE 44145',
    'text': 'Authority raise despite from become understand view. Southern sound each themselves hair picture bit.\nHowever consider safe short behavior few. Professional whose require city however collection.',
    'email': 'jeremiahgomez@example.net',
    'phone_number': '(833)816-9816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Anderson',
    'Douglas Simon',
    'Michael Chapman',
    'Kristin Richardson',
    'Natalie Everett',
],
    'json': {
    'name': 'Deanna Townsend',
    'address': '742 Cheryl Trace\nWadeside, NH 97890',
},
    'key77742': 'value45738',
    'key44592': 'value32899',
    'key97310': 'value90107',
    'key47539': 'value63666',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Amy Hernandez',
    'address': '923 Kyle Inlet\nArthurland, OR 19134',
    'text': 'Animal bill cold nation. We same mention call. Little across must carry course.\nWhere play main pass century marriage. Team figure church.',
    'email': 'oford@example.net',
    'phone_number': '330.630.0048',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amber Johnson',
    'Vanessa Gutierrez',
],
    'json': {
    'name': 'Joseph Richards',
    'address': '51597 Dominguez Falls Apt. 914\nMikaylaville, AS 96781',
},
    'key79092': 'value9559',
    'key20799': 'value11717',
    'key99319': 'value50800',
    'key36400': 'value92521',
    'key89035': 'value52908',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Theresa Torres',
    'address': '4614 Brenda Light\nHarrismouth, SC 46892',
    'text': 'Doctor summer idea remain.\nPerson from each now early west.\nAffect listen point politics. Number difficult than while price statement. Author build begin structure.',
    'email': 'parksgary@example.net',
    'phone_number': '(333)965-7953x18308',
    'array_int_dynamic': [
    14656,
],
    'array_varchar_dynamic': [
    'Shawn Armstrong Jr.',
],
    'json': {
    'name': 'Jacob Ashley',
    'address': '6771 Boyle Shore\nTracyland, IA 10546',
},
    'key54476': 'value61699',
    'key37114': 'value97711',
    'key36631': 'value42921',
    'key16149': 'value227',
    'key6570': 'value46213',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'William Bradley',
    'address': '01683 Jeremy Trace\nGarrettberg, PW 02855',
    'text': 'Reduce wind music garden year. Break out something could cultural use course attorney. Realize bed task might late specific old.',
    'email': 'fmcdaniel@example.net',
    'phone_number': '5559586752',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Cook',
],
    'json': {
    'name': 'Steven Perez',
    'address': '2949 Caleb Springs\nLaneville, VT 82233',
},
    'key56879': 'value9873',
    'key19164': 'value95648',
    'key43218': 'value3810',
    'key7447': 'value95554',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Michael Williams',
    'address': '756 Melanie Falls Apt. 428\nColemanchester, UT 98830',
    'text': 'Social coach likely draw often. Nature change food morning.\nDevelopment summer to word reality head.\nSame issue inside idea rich city each. Despite air board story.',
    'email': 'griffinrobert@example.org',
    'phone_number': '880.553.5117x368',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Ferguson',
    'John Davis',
    'Karen Lewis',
    'Kristine Thompson',
    'Brooke Garcia',
    'Melissa Frederick',
    'Amber Carney',
    'William Owen',
    'Joseph Morgan',
    'Malik Mills',
],
    'json': {
    'name': 'Miguel Rivera',
    'address': '006 Mcintyre Mall Suite 615\nWest Stacey, LA 15959',
},
    'key51326': 'value3997',
    'key32401': 'value10614',
    'key76665': 'value1382',
    'key33274': 'value95442',
    'key69588': 'value81311',
    'key96881': 'value6922',
    'key56440': 'value51350',
    'key79830': 'value86887',
    'key67311': 'value33733',
    'key10638': 'value90416',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Catherine Butler',
    'address': '7131 Dixon Mountain Apt. 832\nHartmanmouth, LA 26412',
    'text': 'Everyone speech result out difficult enter story.\nDirector inside data top history these stay. Cold whether it consider let accept.',
    'email': 'bharper@example.org',
    'phone_number': '269.593.8090x075',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Garcia',
    'Martha Ochoa',
    'Matthew Sanchez',
    'Gary Schmidt',
],
    'json': {
    'name': 'Tyler Lee',
    'address': '1045 Albert Corners\nJeremiahberg, HI 49341',
},
    'key57036': 'value11475',
    'key63390': 'value59195',
    'key33205': 'value91588',
    'key2320': 'value22049',
    'key85455': 'value11323',
    'key28289': 'value8433',
    'key9147': 'value38113',
    'key72524': 'value751',
    'key38538': 'value27311',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Dr. Pamela Acevedo PhD',
    'address': '22916 Maynard Lights Apt. 029\nWilliamsfurt, VI 30221',
    'text': 'Sing television actually. Newspaper watch effort middle question.\nLeg none low professor detail bad.',
    'email': 'princejennifer@example.org',
    'phone_number': '(922)548-3319x03929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Myers',
    'Tina Erickson',
],
    'json': {
    'name': 'Toni Peters',
    'address': '66391 Timothy Crossroad\nWest Christopherbury, MA 87256',
},
    'key57835': 'value78842',
    'key58407': 'value28356',
    'key58764': 'value17511',
    'key64711': 'value61332',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Sherri Morales',
    'address': '742 Joseph Throughway\nRobertsonburgh, HI 96328',
    'text': 'Campaign side mouth whole floor stage me with. Trial care loss list full according.\nFirst member another hope drug white. Ten however argue great hard. Quite their involve cup land around help door.',
    'email': 'elizabethpatton@example.net',
    'phone_number': '784-717-0846x123',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Crawford',
],
    'json': {
    'name': 'Ashley Forbes',
    'address': '122 Allen Overpass Apt. 340\nLake Chadmouth, MP 62091',
},
    'key76673': 'value26327',
    'key90456': 'value80203',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Javier Jackson',
    'address': '161 Jonathan Islands Suite 429\nPort Suzanneborough, WI 26836',
    'text': 'Letter enjoy detail admit also clear. Save technology every particular must. Identify worry its conference cut politics example over.',
    'email': 'sfuller@example.org',
    'phone_number': '+1-619-217-2570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Robinson',
    'Lawrence Hayes',
    'April Reyes',
    'Kevin Baxter',
    'Charles Washington',
    'Gary Buchanan',
],
    'json': {
    'name': 'James Garcia',
    'address': '10659 Nash Creek Apt. 052\nLake Amandastad, IA 45115',
},
    'key25398': 'value17881',
    'key43558': 'value40084',
    'key18792': 'value27390',
    'key38487': 'value74429',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Walter Hobbs',
    'address': '645 Clarke Shores\nNew Patrickmouth, UT 94537',
    'text': 'Month difference garden fight hair including morning. Reduce realize generation part mission best.',
    'email': 'ashleyacosta@example.net',
    'phone_number': '001-552-457-2684x957',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Turner',
],
    'json': {
    'name': 'Joshua Greene',
    'address': 'PSC 0245, Box 8321\nAPO AP 33147',
},
    'key97267': 'value85758',
    'key7993': 'value82373',
    'key75922': 'value8804',
    'key31353': 'value46750',
    'key17702': 'value67360',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Amber Thomas',
    'address': '505 April Bypass\nJamesshire, KS 17567',
    'text': 'Make tend family think. Example treat not lawyer down. Audience senior financial throw baby simply.',
    'email': 'kelly38@example.org',
    'phone_number': '313-771-3598x213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tony Cruz',
    'Douglas Hughes',
    'Susan Miller',
    'Karen Brown',
    'Louis Wang',
    'Jennifer Myers',
],
    'json': {
    'name': 'Heather Scott',
    'address': '2898 Christopher Crossing Apt. 608\nPort Kimberly, VA 63984',
},
    'key79059': 'value90001',
    'key16695': 'value52812',
    'key32597': 'value83858',
    'key92474': 'value93762',
    'key46842': 'value59145',
    'key9114': 'value40591',
    'key84383': 'value55085',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Christopher Owens',
    'address': '6519 Michael Ramp Apt. 869\nHesterbury, MO 09989',
    'text': 'Contain beat executive. Art serious crime tonight he since dream approach. Surface only full page recognize college.',
    'email': 'jdavenport@example.com',
    'phone_number': '8013539462',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christine Hansen',
    'Amber Campbell',
    'Anita Ray',
    'Evan Jones',
],
    'json': {
    'name': 'Bobby Donovan',
    'address': '81626 Johnson Field\nWest Brandonburgh, AK 67998',
},
    'key39574': 'value70227',
    'key43754': 'value38522',
    'key4496': 'value79542',
    'key99462': 'value29746',
    'key12027': 'value63979',
    'key12545': 'value16437',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Monica Schmitt',
    'address': '4960 Eric Camp\nSouth Tylerfurt, PR 81017',
    'text': 'Budget life claim ball performance guy once. Art explain kitchen ago Democrat member thank. Health time stage appear information other.',
    'email': 'amy53@example.org',
    'phone_number': '589.438.8194x5965',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sergio Coleman',
    'Jennifer Young',
    'Michelle Flores',
    'John Brown',
    'Renee Archer',
    'Anthony Coffey',
    'Daniel Goodwin II',
    'Glenn Davis',
    'Margaret Valencia',
],
    'json': {
    'name': 'Katherine Aguilar',
    'address': '8843 Amber Harbors Suite 365\nJulieside, MT 21633',
},
    'key97417': 'value63932',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Joshua Johnson',
    'address': '6663 Green Prairie Suite 638\nGeoffreyland, VA 30856',
    'text': 'Probably option firm major.\nTeacher difficult heavy dinner term. May board herself difficult. Song attention institution pressure.',
    'email': 'loweryapril@example.org',
    'phone_number': '001-254-608-1676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Shelly Foster',
    'John Khan',
    'Taylor Gomez',
    'Samantha English',
    'Tina Soto',
    'Kelly Pugh',
    'Blake Le',
    'Lonnie Thompson',
],
    'json': {
    'name': 'Amber Juarez',
    'address': '911 Gregory Parks Apt. 109\nSouth Eric, MS 03407',
},
    'key59144': 'value26128',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Brittany Williamson',
    'address': 'Unit 7727 Box 0677\nDPO AA 60283',
    'text': 'Effect natural away sit address bit executive. Stay reduce worry should indeed. Heart wear of tough interesting.',
    'email': 'ydawson@example.com',
    'phone_number': '(682)204-3418',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tyler Carter',
    'Lisa Clark',
    'James Patel',
    'Tracy Taylor',
    'Stephanie Garcia',
    'Scott Melton',
    'Barry Caldwell',
],
    'json': {
    'name': 'Samantha King',
    'address': '797 Justin Light\nWest Kathrynburgh, NV 01749',
},
    'key99094': 'value36198',
    'key32098': 'value45686',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Troy Carlson',
    'address': '325 Thomas Orchard\nCarlatown, MD 60966',
    'text': 'Could down artist night region. Blue final training good me. Coach focus develop name machine box employee pass.\nBed agency write medical tonight leave girl guy. Chance shoulder well lay.',
    'email': 'tkrueger@example.com',
    'phone_number': '(826)351-6059x96089',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Adams',
    'Lisa Cox',
    'Eric Thomas',
    'Thomas Watts',
    'Michelle Sampson',
    'Paul Perez',
    'Chelsea Dixon',
    'Nancy Flores',
    'Brooke Morris',
    'Tammie Montes',
],
    'json': {
    'name': 'Elizabeth Harris',
    'address': '9910 Michael Land Suite 954\nTranside, FL 47641',
},
    'key44478': 'value98430',
    'key43016': 'value12004',
    'key67635': 'value46281',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Angela Ferrell',
    'address': 'Unit 0843 Box 8136\nDPO AP 06127',
    'text': 'Apply main senior start begin. Back couple try. Matter field fire player crime study commercial.',
    'email': 'tgutierrez@example.net',
    'phone_number': '(977)634-7388x372',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Laura Adams',
    'William Hawkins',
    'Jessica Roberts',
    'Carla Robinson',
    'Nicholas Gonzalez',
    'Warren Black',
    'Jeremy Holloway',
    'Kevin Cox',
],
    'json': {
    'name': 'Scott King',
    'address': '0596 Brenda Field\nAlexandershire, SC 82629',
},
    'key42018': 'value34891',
    'key80441': 'value42013',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'James Brown',
    'address': '277 Garza Grove Apt. 622\nMckinneyfort, UT 51944',
    'text': 'Thought coach Republican commercial just positive glass. Whatever imagine beyond never. Move from system lot air rest full. Item care much rate ability man.\nWrite instead many. Share concern Mr.',
    'email': 'matthewstheodore@example.org',
    'phone_number': '001-583-604-5973',
    'array_int_dynamic': [
    16185,
],
    'array_varchar_dynamic': [
    'Ray Joyce',
],
    'json': {
    'name': 'Kathleen Smith',
    'address': '293 Hooper Circle\nNew Wandaland, MI 93094',
},
    'key97843': 'value88782',
    'key64331': 'value58163',
    'key81794': 'value20662',
    'key93250': 'value16190',
    'key66482': 'value61865',
    'key90725': 'value71912',
    'key44470': 'value75470',
    'key35525': 'value26721',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Andrew Wilson',
    'address': '8447 Mccormick Court\nEast Kelsey, FM 74892',
    'text': 'Good woman know school worker detail east town. Enjoy institution side weight bank her along.\nSend final sign. Body foreign relationship have common.',
    'email': 'pfields@example.net',
    'phone_number': '001-393-445-7320',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Spencer Erickson',
    'Joseph Aguilar',
],
    'json': {
    'name': 'Jennifer Hudson',
    'address': '25865 Jeffery Inlet Apt. 366\nScotthaven, WV 48683',
},
    'key14813': 'value28545',
    'key34149': 'value20176',
    'key37596': 'value16216',
    'key75554': 'value67371',
    'key84780': 'value9295',
    'key65095': 'value47921',
    'key25350': 'value31462',
    'key94894': 'value20696',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Jennifer Tran',
    'address': '170 Clark Drive Suite 149\nMorganmouth, TN 70328',
    'text': 'Box structure idea avoid. Total quickly mind far finish today. His would player receive rich memory American.',
    'email': 'jhunt@example.org',
    'phone_number': '8886031729',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Adams',
    'Paul Barnett',
    'Laura Martin',
    'Heather Torres',
    'Christopher Gentry',
    'Melissa Chapman MD',
    'Jennifer Martinez',
],
    'json': {
    'name': 'Lisa Braun',
    'address': '70168 Juarez Way\nSouth Charlenemouth, VT 50924',
},
    'key51842': 'value4903',
    'key23879': 'value19414',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Brittany King',
    'address': '36808 Mitchell Park\nNorth Allison, NH 03566',
    'text': 'Performance though grow. Time sort red recent movie individual institution.\nReason key add. Sister two own.\nOwner arm sea try political. Fly century resource able up blood.',
    'email': 'monicabrooks@example.net',
    'phone_number': '+1-928-552-9076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Mahoney',
    'Kimberly Davis',
    'Patrick Hester',
],
    'json': {
    'name': 'Jocelyn King',
    'address': '49338 Sean Land Apt. 549\nSeanchester, VA 16236',
},
    'key82745': 'value3379',
    'key32438': 'value33140',
    'key67275': 'value56161',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Amy Proctor',
    'address': '385 Jason Roads Apt. 510\nWest Christopher, PW 98060',
    'text': 'Measure most group provide local could share want. Pull large fire cold network general arm.\nSell argue piece interest. Hope include now mind reason.',
    'email': 'munozrobin@example.com',
    'phone_number': '5975911483',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Rodney Glenn',
    'Brandon Garza',
    'Alejandra Thompson',
    'Lydia Gray',
],
    'json': {
    'name': 'Charles Lane',
    'address': '421 Rodriguez Lodge Apt. 852\nEast Sue, MS 56359',
},
    'key86401': 'value35856',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Debra Wilson',
    'address': '8897 Whitehead Lake\nPort Paulhaven, NC 40682',
    'text': 'Social play present magazine end stop TV care. Place wait ago.\nNever early else security past environment. Energy deal item attention all store her.',
    'email': 'michael02@example.com',
    'phone_number': '665-464-4740x794',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Julie Jackson',
    'Lisa Vega',
    'Scott Ross',
    'Brett Mcdaniel',
],
    'json': {
    'name': 'Amanda Richardson',
    'address': '964 Whitaker Drive\nWest Kimberly, MA 59231',
},
    'key91434': 'value29996',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Melissa Smith',
    'address': '7079 Andrea Island\nNorth Todd, WA 16532',
    'text': 'Glass fear without pattern.\nAnyone indicate peace market paper national. Scene lot sea. Business main manager conference.',
    'email': 'vaughnalvin@example.net',
    'phone_number': '(249)579-3646',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Ray',
    'Bryan Jenkins',
    'William Olson',
    'Joshua Carey',
    'Jennifer Griffin',
],
    'json': {
    'name': 'Mandy Harris',
    'address': '751 Michael Harbor\nRhondaberg, AS 18925',
},
    'key35504': 'value39930',
    'key44250': 'value43934',
    'key19420': 'value21940',
    'key83772': 'value88293',
    'key42610': 'value99002',
    'key71527': 'value37745',
    'key45633': 'value36508',
    'key28702': 'value44924',
    'key59630': 'value11739',
    'key2232': 'value62666',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Dorothy Ramirez',
    'address': '1999 Jacob Cliff Suite 158\nEast Charles, MD 47487',
    'text': 'Animal himself sea itself commercial leave.\nMeet nearly democratic ahead pretty. Really blue church many here.',
    'email': 'wmoore@example.com',
    'phone_number': '+1-570-887-1518x71339',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Lopez',
    'Tammy Esparza',
    'Kimberly Middleton DDS',
    'Michael Smith',
],
    'json': {
    'name': 'Denise Bradford',
    'address': '0600 Lisa Estate Suite 706\nMorrisonton, OK 92574',
},
    'key25038': 'value11944',
    'key4677': 'value23235',
    'key5162': 'value29432',
    'key31233': 'value24689',
    'key84357': 'value88871',
    'key55661': 'value97136',
    'key10318': 'value23056',
    'key4668': 'value76517',
    'key16466': 'value56971',
    'key87': 'value38467',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Rachel Hardy',
    'address': '84371 Rhonda Avenue\nMichelleton, OK 93471',
    'text': 'Do run simple report control be. Soon mind test down usually. Both like discuss lawyer likely win ahead.\nClearly huge view prepare. Plan magazine send responsibility recently total.',
    'email': 'anthony21@example.net',
    'phone_number': '001-397-512-0755x34124',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Emily Lin',
    'Erik Pugh',
    'Angela Dunlap',
    'Matthew Payne MD',
    'Thomas Jones',
    'Jessica Tran',
    'Frederick Lane',
    'Amber Bailey',
],
    'json': {
    'name': 'Nicholas Allen',
    'address': '972 Daniels Valley\nEast Rachel, AL 96568',
},
    'key41291': 'value81570',
    'key80680': 'value14424',
    'key2247': 'value92496',
    'key41795': 'value37870',
    'key86255': 'value71096',
    'key23515': 'value96587',
    'key81679': 'value8291',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Kristina Mayo',
    'address': '860 Cox Heights\nRonaldmouth, FM 40064',
    'text': 'Cup cold into matter. Long ask keep best eye focus PM. Could blue surface help even.\nColor maybe dark student clearly whether answer. My travel general wife.',
    'email': 'marc10@example.org',
    'phone_number': '(298)692-2800x48390',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Victor Baker',
    'Justin Garcia',
    'Reginald Vazquez',
    'Michelle Orr',
],
    'json': {
    'name': 'Tara Nguyen',
    'address': '04306 Martinez Roads Apt. 414\nGrantchester, FM 21814',
},
    'key10439': 'value31941',
    'key98379': 'value1629',
    'key40922': 'value82352',
    'key37472': 'value57589',
    'key79661': 'value43296',
    'key75715': 'value97736',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Robert Jones',
    'address': '276 Victoria Ports Suite 601\nJamesberg, NY 54066',
    'text': 'Apply finish very own bit quickly. Part education sea who cut anyone worker.\nPopular respond case factor. Should human space citizen choose item.',
    'email': 'todd28@example.com',
    'phone_number': '637-392-0666x2683',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ruben James',
    'Margaret Townsend',
    'Brenda Schultz',
    'Steve Thompson IV',
    'Katie Santiago',
    'Steven White',
    'Manuel Carlson MD',
],
    'json': {
    'name': 'Kenneth Kelly',
    'address': '5832 Garner Street Suite 793\nNew Lisaport, DC 73009',
},
    'key9324': 'value68019',
    'key45802': 'value23915',
    'key3620': 'value26938',
    'key33349': 'value77052',
    'key24597': 'value26572',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Christina Spears',
    'address': '38723 Christopher Lodge\nPort Jennifer, NC 51004',
    'text': 'School road use teach far stay pay. Choice thank them song itself pick opportunity. Air director magazine.\nProject choose finally range probably quickly. Break course me box financial.',
    'email': 'ijackson@example.net',
    'phone_number': '7132440039',
    'array_int_dynamic': [
    70380,
],
    'array_varchar_dynamic': [
    'Mrs. Amanda Watson DVM',
    'Laura Peterson',
    'Christina White',
    'Amanda Nelson',
    'Jesus Hernandez',
],
    'json': {
    'name': 'Frank Brooks',
    'address': '476 Garcia Unions\nMartinezside, VA 35841',
},
    'key27127': 'value30256',
    'key52721': 'value35656',
    'key23847': 'value11887',
    'key66143': 'value14135',
    'key26923': 'value45055',
    'key79827': 'value55218',
    'key5961': 'value50886',
    'key1339': 'value37955',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Mr. Blake Sanchez',
    'address': '7817 Angela Union\nEast Davidmouth, KS 68415',
    'text': 'Strategy record because wear very science discuss. Blood near throw. Study change experience entire.',
    'email': 'jadejohnson@example.com',
    'phone_number': '001-585-380-8394x6977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mindy Rodriguez',
    'Stephen Johnson',
    'Alejandro Murray',
    'Joel Hall Jr.',
],
    'json': {
    'name': 'Marcus West',
    'address': '5260 John Lights Apt. 522\nLake Brian, AK 54236',
},
    'key85164': 'value88004',
    'key40573': 'value58012',
    'key24269': 'value17865',
    'key23281': 'value37105',
    'key24377': 'value8033',
    'key85467': 'value36399',
    'key76235': 'value51213',
    'key43917': 'value28691',
    'key17609': 'value33965',
    'key91643': 'value25772',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Sandra Edwards',
    'address': '68776 Lisa Shore\nWest Kelly, NH 91278',
    'text': 'Their window option particular impact visit. Add these ago result respond painting. Would from never article his.\nMyself send particular officer anyone hit.',
    'email': 'johnwilson@example.net',
    'phone_number': '621-955-1225',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Connie Jackson',
    'Justin Morton',
],
    'json': {
    'name': 'Timothy Carpenter',
    'address': '2063 Powell Burgs\nDebraside, MN 50722',
},
    'key64667': 'value66425',
    'key26922': 'value5018',
    'key61434': 'value40093',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Michael Krueger',
    'address': '6902 Doyle Ramp Apt. 823\nCallahantown, WV 69314',
    'text': 'Wrong central herself appear then act. Everyone different create station reason Mrs.\nBetween door firm church yeah probably. Serious base film Republican case only.\nSimple get program.',
    'email': 'flogan@example.org',
    'phone_number': '(468)827-5279x80214',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Walton',
],
    'json': {
    'name': 'Amanda Simmons',
    'address': '2771 Lisa Lights\nEast Wendyhaven, UT 73343',
},
    'key62339': 'value78710',
    'key37716': 'value85491',
    'key49210': 'value97762',
    'key88301': 'value32692',
    'key16149': 'value50305',
    'key42906': 'value92174',
    'key76592': 'value72479',
    'key2465': 'value25532',
    'key54276': 'value95688',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Katrina Moore',
    'address': '187 Chad Extensions Apt. 810\nAdamside, OK 92763',
    'text': 'Which staff at official. Cause it help suggest human play produce. Rate after bring support great tonight want manager.\nProduce rule page. Live help including matter nothing official.',
    'email': 'williamsrodney@example.org',
    'phone_number': '526.579.9858',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Mclaughlin',
],
    'json': {
    'name': 'David White',
    'address': '72515 Debra Valley\nPort Daniel, WY 83435',
},
    'key69252': 'value74153',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Michelle Hanson',
    'address': '67347 Michelle Islands\nNorth Seanview, PR 71333',
    'text': 'Unit reduce then including yeah factor would. All probably account campaign.\nPersonal prevent story agree subject system. Ball get same head.\nTonight someone go.',
    'email': 'kingbrent@example.net',
    'phone_number': '(999)986-3002x6247',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Deborah Koch',
    'Charles Thompson',
    'Michael Adams',
    'Danielle Green',
    'Gilbert Hart',
    'Michael Manning',
],
    'json': {
    'name': 'Jeffrey Owens',
    'address': '330 Dylan Spring\nPort Kimberly, WA 70651',
},
    'key37981': 'value56870',
    'key17018': 'value88640',
    'key77820': 'value94192',
    'key76990': 'value89377',
    'key45901': 'value96851',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Jennifer Fox',
    'address': '2185 Bonnie Court\nJoanside, NC 39596',
    'text': 'Month hope appear common. Best make artist theory true analysis attack. Hotel feeling will concern other nothing.\nImpact data grow drug. Unit ahead notice expect reveal matter.',
    'email': 'jamie79@example.org',
    'phone_number': '298.314.4433x872',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Hernandez',
    'John Bernard',
    'Paula Ortiz',
    'Tracy Garcia',
    'Michael Ramirez',
    'Michelle Kelley',
    'John Edwards',
    'Miguel Hoffman',
    'Christopher Garcia',
],
    'json': {
    'name': 'Michael Armstrong',
    'address': 'PSC 3835, Box 3361\nAPO AE 33210',
},
    'key82721': 'value5540',
    'key79059': 'value64107',
    'key64683': 'value31199',
    'key57975': 'value76948',
    'key60453': 'value98931',
    'key36517': 'value1848',
    'key34557': 'value43459',
    'key45919': 'value21344',
    'key63219': 'value27797',
    'key15886': 'value8132',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Mrs. Debra Smith',
    'address': '57348 Mathis Extensions Apt. 775\nKevinmouth, ND 62464',
    'text': 'Wind wide popular focus. Cost amount space view head understand another.\nFree find six bad capital note. Nice action their chair. Sign at strong watch point debate eight.',
    'email': 'smithashley@example.net',
    'phone_number': '799.201.1229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dennis Young',
    'Natalie Williams',
    'Lance Powell',
],
    'json': {
    'name': 'Kevin Lewis',
    'address': '3162 Calderon Mountain Suite 064\nWrighthaven, ND 67083',
},
    'key37812': 'value42229',
    'key73665': 'value37046',
    'key44771': 'value48091',
    'key35990': 'value97767',
    'key67233': 'value42370',
    'key74285': 'value66386',
    'key41950': 'value61820',
    'key63841': 'value83478',
    'key19351': 'value85776',
    'key7002': 'value2402',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Kevin Barker',
    'address': '34002 Robert Meadows Apt. 817\nWilliamsmouth, MS 42055',
    'text': 'Kid TV worker minute Republican this agree.\nFew send executive else at anything. Section company Democrat PM benefit after.',
    'email': 'dprice@example.com',
    'phone_number': '344-892-0403',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Steven Odom',
    'Joseph Barker',
    'Lisa Palmer MD',
    'Bailey Warren',
    'Sue Horne',
    'Timothy Smith',
    'Marvin Larson',
],
    'json': {
    'name': 'Felicia Obrien',
    'address': '26292 Margaret Pine\nJonesborough, TX 57932',
},
    'key2910': 'value70954',
    'key25466': 'value33673',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Jamie Shaw',
    'address': '72780 Adams Shoal\nEast Ashley, PR 89554',
    'text': 'Soon later around religious. Military Democrat worry civil young.\nSit general church it business music theory. Cost section heavy my safe.',
    'email': 'urodriguez@example.org',
    'phone_number': '842-991-8603x3525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'William Reese',
    'Kurt Jones',
    'Holly Hill',
    'Linda Harding',
    'Tyler Reeves',
    'Luis Booth',
],
    'json': {
    'name': 'Lauren Villa',
    'address': '88849 Perez Mews Suite 699\nChelseaburgh, GU 24392',
},
    'key77624': 'value77374',
    'key24503': 'value61896',
    'key29413': 'value63364',
    'key90670': 'value89385',
    'key93938': 'value88702',
    'key62830': 'value87131',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Kimberly Morse',
    'address': '39270 Blevins Burg\nWest Elizabethtown, RI 05521',
    'text': 'Possible get foot father life evidence. Against country serve investment cause up. Production sing perhaps sea.',
    'email': 'charlesmason@example.org',
    'phone_number': '+1-998-752-8059x806',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Powell',
    'Amy Woods',
    'Daniel Velazquez',
    'Jon Scott',
    'Patrick Peterson',
],
    'json': {
    'name': 'Nicholas Ramirez',
    'address': '30929 Jaime Roads Apt. 196\nLake Joeltown, ND 40578',
},
    'key87086': 'value23342',
    'key13636': 'value1169',
    'key57289': 'value60472',
    'key76972': 'value83723',
    'key6825': 'value1590',
    'key18441': 'value83019',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Joshua Morrison',
    'address': 'PSC 4710, Box 7442\nAPO AA 78081',
    'text': 'Skill say professor interesting participant serve. Century hundred tax certain building bit whole.\nPicture more want kind style final. Sister your letter get out.',
    'email': 'michael01@example.org',
    'phone_number': '(994)724-1928x045',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gail Montgomery',
    'Carolyn Lam',
    'Kristina Murray',
    'Manuel Perez',
],
    'json': {
    'name': 'Mindy Finley',
    'address': '42004 Peters Lane\nLake Pamela, OH 96284',
},
    'key44458': 'value26834',
    'key41820': 'value42431',
    'key20823': 'value51822',
    'key2841': 'value99270',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Anthony Marquez',
    'address': '393 David Light\nRhondaville, WA 37961',
    'text': 'Daughter rule lose leave. Street available several degree food international.\nEffect health play six. Trial throughout play key break.\nAgreement marriage fly table break center seat position.',
    'email': 'josephpayne@example.com',
    'phone_number': '+1-709-296-9248x378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Hampton',
    'Roy Rogers',
    'Kayla Dominguez',
],
    'json': {
    'name': 'Kimberly Lane',
    'address': '822 Ernest Garden\nWest Tomview, RI 96276',
},
    'key27798': 'value72336',
    'key12021': 'value61171',
    'key51651': 'value87551',
    'key95301': 'value84104',
    'key82078': 'value52447',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Kenneth Byrd',
    'address': '22979 Peters Causeway Suite 759\nDrewmouth, MP 31317',
    'text': 'College state too talk anyone new choose. Stay sometimes first paper hard. Of several parent real world example property middle. Might side walk series.',
    'email': 'todd33@example.com',
    'phone_number': '931.867.4092x799',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lori Arnold',
    'Kim Alvarez',
    'Rachael Glover',
    'Susan Larsen',
    'Thomas Williams',
],
    'json': {
    'name': 'Christopher Thomas',
    'address': '008 Ann Shoal\nKarenshire, KY 97819',
},
    'key64979': 'value21753',
    'key23399': 'value9198',
    'key30220': 'value173',
    'key68713': 'value64792',
    'key76979': 'value51579',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Catherine Sandoval',
    'address': '19872 Tami Oval\nWest Scott, ND 04079',
    'text': 'Free safe whatever water. Region player let record task. Future model age assume world.\nThank then sometimes election. Whole which vote sea station employee.',
    'email': 'nramirez@example.org',
    'phone_number': '468-699-4180x8196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Eric Weaver',
    'Dawn Mayo',
    'Cheryl Fletcher',
    'Michael Conner',
    'Cory Logan',
    'Robert Bradford',
],
    'json': {
    'name': 'Marie Meyers',
    'address': '1077 Jose Mount\nWest Michaeltown, GU 43459',
},
    'key77830': 'value81678',
    'key23344': 'value76518',
    'key9048': 'value72646',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Erica Sanchez',
    'address': '4082 Edward Manors Suite 317\nWest Cynthia, SD 64323',
    'text': 'Should determine early how. Young official dream idea.\nIts either art miss church parent though water. All space consumer I still single. Play return even individual.',
    'email': 'elizabeth98@example.net',
    'phone_number': '(917)611-4930x766',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Campbell',
    'James Taylor',
    'Tanya Whitehead',
    'Karen Riggs',
],
    'json': {
    'name': 'Christopher Neal',
    'address': '5663 Craig Cliffs\nSouth Jamesfort, ID 50336',
},
    'key20545': 'value61406',
    'key16878': 'value85198',
    'key17970': 'value62525',
    'key52588': 'value99983',
    'key39139': 'value77339',
    'key3875': 'value94973',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Carolyn Heath',
    'address': '863 David Fort Suite 300\nVictormouth, IN 23794',
    'text': 'Responsibility already compare time camera. Mother wife product tree reduce.\nVoice on example during. The score nature experience. Set may group wrong.\nAbove mention wrong people trade right fish.',
    'email': 'mcneiljacqueline@example.org',
    'phone_number': '001-798-265-0078x965',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Brown',
    'Lori Walsh',
    'James Lucas',
],
    'json': {
    'name': 'Brandon Smith',
    'address': '010 Smith Green\nLake Daniel, OH 62454',
},
    'key74505': 'value13851',
    'key63381': 'value23962',
    'key30610': 'value28448',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Michael Riggs III',
    'address': 'PSC 1827, Box 1454\nAPO AE 82744',
    'text': 'Science night newspaper increase commercial good moment return. Without condition admit know discover top word.\nBut staff have quite now. Power phone instead able.',
    'email': 'villanuevadesiree@example.org',
    'phone_number': '683-280-3620',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Rogers',
    'Michelle Young',
    'Jenna Sparks',
    'Daniel Young',
],
    'json': {
    'name': 'Daniel Yu',
    'address': '168 David Dam Apt. 634\nSouth Suzanne, SD 63313',
},
    'key49203': 'value21591',
    'key30197': 'value23597',
    'key98370': 'value89449',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Erika Osborne',
    'address': '3713 Hill Landing Apt. 419\nNorth Christinaberg, FL 55664',
    'text': 'Recent decade long short. Bill mind wonder right answer simply expect deal.\nDescribe past chance reach. Include everybody through history.',
    'email': 'eric59@example.com',
    'phone_number': '258.376.7020',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Brooks',
    'Sylvia Williams',
    'Jessica Griffin',
    'Michael Moore',
    'Morgan Higgins',
    'Haley Walton',
    'David Simmons',
    'Joseph Torres',
    'Joseph Johnson',
    'Sarah Green',
],
    'json': {
    'name': 'James Chase',
    'address': '8640 John Plaza Apt. 834\nTaylorside, FL 66000',
},
    'key48486': 'value9436',
    'key20397': 'value69138',
    'key39098': 'value93513',
    'key62935': 'value7770',
    'key85941': 'value72879',
    'key29690': 'value1476',
    'key50016': 'value50620',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Connie Cox',
    'address': '98409 Small Center Suite 495\nKathleenbury, NM 64885',
    'text': 'However start control yes. Member while relationship nor suggest.\nBuilding deal war dinner. Agency shake young. Citizen Mrs officer skin myself throw.',
    'email': 'butleramber@example.net',
    'phone_number': '001-303-804-6224',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Joe Elliott',
    'Mr. Jason Knight',
    'Molly Mason',
    'William Kennedy',
    'James Miles',
    'Evelyn Pierce',
    'Daniel Garner',
    'Jeffrey Soto',
    'Kristin Berry',
],
    'json': {
    'name': 'Terri Reese',
    'address': '14651 Smith Highway\nRebeccahaven, WI 26886',
},
    'key9975': 'value44947',
    'key88126': 'value40445',
    'key32708': 'value25348',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Calvin Khan',
    'address': '87606 Mcdonald Key\nLake Shawn, PR 65248',
    'text': 'Budget concern enough find husband check brother. Interesting white head fly able grow personal.\nAcross wear almost character blue wall. Rule believe step letter firm.',
    'email': 'gbean@example.com',
    'phone_number': '(796)242-3846',
    'array_int_dynamic': [
    39663,
],
    'array_varchar_dynamic': [
    'Lori Long',
    'James Pena',
    'Allen Watson',
    'William Bell',
    'Michael Lowe',
    'Leah Hughes',
    'Timothy Ferguson',
    'Veronica Burch',
],
    'json': {
    'name': 'Matthew Holloway',
    'address': '299 Flowers Orchard Suite 531\nAmberborough, WA 58281',
},
    'key43598': 'value81992',
    'key62972': 'value54415',
    'key87961': 'value94929',
    'key12670': 'value14501',
    'key9744': 'value43737',
    'key72854': 'value4811',
    'key46156': 'value2271',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Morgan Miller',
    'address': '2547 Lisa Island\nEast James, CA 66504',
    'text': 'Hope clearly north find far support hand. Have happen walk south visit food sport very.\nPage responsibility agree consumer former shake. Blue discussion create friend early entire heart.',
    'email': 'garzalisa@example.org',
    'phone_number': '001-731-435-2162x7185',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sara Parker',
    'Caitlin Wilkins',
    'Sarah Pope',
    'Kimberly Roberts',
    'Logan Marquez',
    'Tricia Richards',
    'Eric Hernandez',
    'Jose Vazquez',
    'Kayla Norris',
],
    'json': {
    'name': 'Kelly Owens DDS',
    'address': '78133 Christine Lodge Suite 266\nPalmerchester, PW 20538',
},
    'key65389': 'value74642',
    'key30915': 'value59192',
    'key28776': 'value70850',
    'key38254': 'value28337',
    'key59423': 'value57657',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Garrett Dixon',
    'address': '934 Eric Road Apt. 177\nEast Amanda, ME 01910',
    'text': 'Experience play herself thus low someone business. Rule that here season always arm idea.\nSend camera able teach social. Bar standard own generation too forget Republican sing.',
    'email': 'zperry@example.com',
    'phone_number': '+1-482-994-7496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Darryl Bryant',
    'Debra Mathis',
    'William Ryan',
    'Kelly Ortiz',
    'Amanda Cox',
    'Jessica Santiago',
    'Lisa Mendoza',
    'Mary Carr',
    'Kelly Blair',
    'Mr. Brandon Robinson',
],
    'json': {
    'name': 'Maria French',
    'address': '21407 David Highway Apt. 420\nPort Markport, UT 65716',
},
    'key63631': 'value32055',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Joel Myers',
    'address': '6810 Christopher Shore Apt. 216\nEast James, AS 16370',
    'text': 'Son much learn partner but hair. Be fine evidence sit.\nDuring cover TV cost attack. Check store trade across. Quality wait company against speak.',
    'email': 'williamlevine@example.net',
    'phone_number': '845-291-8663x84281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Ruiz',
    'Kimberly Ruiz DDS',
    'Michael Richards',
    'April Lowe',
    'Stacy Sloan',
],
    'json': {
    'name': 'Melissa Stevens',
    'address': 'Unit 1197 Box 9548\nDPO AP 48798',
},
    'key55905': 'value2857',
    'key95811': 'value512',
    'key55676': 'value78016',
    'key91828': 'value99460',
    'key59790': 'value86536',
    'key12558': 'value36619',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Holly Fernandez',
    'address': '453 Calvin Trail\nJohnsonburgh, MS 06456',
    'text': 'Whole well future material mean cut. Direction task none agree bed kitchen.',
    'email': 'garciajoel@example.org',
    'phone_number': '(415)287-9190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Berger',
    'Cody Rosales',
],
    'json': {
    'name': 'Patrick Campbell',
    'address': 'PSC 3250, Box 5846\nAPO AP 32856',
},
    'key89709': 'value43105',
    'key3061': 'value84847',
    'key65265': 'value36550',
    'key36448': 'value25802',
    'key66895': 'value72887',
    'key55929': 'value85558',
    'key21112': 'value92924',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Jeff Johnson',
    'address': '1391 Anderson Dale Apt. 068\nWest Anthonyhaven, OH 72631',
    'text': 'Through use fly picture. Their member do carry method either. Son song leave him call.\nPeople reveal others quickly. Window sign alone raise operation picture civil side. Blood loss so rate.',
    'email': 'bobby25@example.org',
    'phone_number': '315-544-5928',
    'array_int_dynamic': [
    49727,
],
    'array_varchar_dynamic': [
    'Brendan Garrett',
    'Jill Smith',
    'John Berry',
    'Katherine Parker DDS',
    'Adam Hart',
    'Jeremy Cardenas',
    'Jim Hammond',
],
    'json': {
    'name': 'Crystal Davis',
    'address': '69535 Alexis Common Suite 832\nSaraland, WY 33509',
},
    'key44922': 'value33240',
    'key98574': 'value16152',
    'key54672': 'value18235',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Stephanie Miller',
    'address': '637 Angela Greens Apt. 359\nNew Matthew, NH 26968',
    'text': 'Still see education write feeling dream. Wrong garden available plant development.\nSpeech eat class put face it threat. Culture morning public man production. From one nature huge.',
    'email': 'webbamy@example.org',
    'phone_number': '(418)804-0598',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Brown',
    'Sabrina Johnson',
    'Catherine Obrien',
    'Christopher Lucas',
    'Jared Moyer',
    'Megan Parker',
],
    'json': {
    'name': 'Elizabeth Brewer',
    'address': '66917 Johnson Island\nChenton, ME 23060',
},
    'key65134': 'value52023',
    'key77782': 'value33581',
    'key54259': 'value65245',
    'key79312': 'value94233',
    'key14281': 'value61157',
    'key20329': 'value28976',
    'key26995': 'value75307',
    'key53418': 'value2302',
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
    'RequestId': '884249ca-62ef-11f0-b302-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_16_123556NCkGXNvk',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-id-128-100-2]_1752744137.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingId12810021752744137Json()
    test.run_tests()
