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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 00]_1752748893_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 00]_1752748893.json"
VDB_TYPE = "milvus"


def send_request(content, request_type="POST", url_path="http://172.17.0.5:23210/v2/vectordb/collections/create", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"POST"
        url_path: URL路径，默认为"http://172.17.0.5:23210/v2/vectordb/collections/create"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid001752748893Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 00]_1752748893.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 00]_1752748893.json"
        self.test_count = 5  # 测试方法数量
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
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '93964c30-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_20_597246VzGRsInE',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://172.17.0.5:23210/v2/vectordb/collections/describe"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/describe")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/describe'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '93964c30-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_20_597246VzGRsInE',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v2/vectordb/entities/insert"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/insert")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/insert'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '93964c30-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_20_597246VzGRsInE',
    'data': [
    {
    'id': 17527488866326,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Nathaniel Castillo',
    'address': '769 Brendan Junction\nDevinstad, NJ 45664',
    'text': 'Success than project light be push. Top western win instead thought keep current.',
    'email': 'matthewscorey@example.org',
    'phone_number': '725.236.4391x7841',
    'json': {
    'name': 'Jeffrey Peterson',
    'address': '3751 Ashley Drives Suite 230\nLake Mikaylastad, SD 28134',
},
    'key98182': 'value26293',
    'key72519': 'value7972',
    'key61662': 'value31382',
    'key52442': 'value10067',
    'key40369': 'value39491',
    'key88090': 'value16182',
    'key91651': 'value24584',
    'key83618': 'value22802',
},
    {
    'id': 17527488866346,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Leah Duncan',
    'address': '85661 Timothy Inlet\nRichport, NV 30064',
    'text': 'No someone hot. Region serve true any child care mean daughter. Wall father must lose anyone assume.',
    'email': 'lisa78@example.com',
    'phone_number': '790.260.7193',
    'json': {
    'name': 'Lori Stewart',
    'address': '57455 Ramirez Street Suite 245\nLake Eric, WY 35592',
},
    'key45245': 'value11813',
    'key89878': 'value54244',
    'key36914': 'value32830',
    'key5919': 'value91176',
    'key54862': 'value33749',
},
    {
    'id': 17527488866359,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Michael Cook',
    'address': '16405 Liu Heights\nCamposville, NM 31601',
    'text': 'After air far responsibility amount. Life especially player write task side per school. How professional start kind series.',
    'email': 'rhondarichards@example.com',
    'phone_number': '001-656-957-6076x9854',
    'json': {
    'name': 'Rebecca Castillo',
    'address': '5085 Perez Corners\nNorth Jamesshire, WA 47196',
},
    'key62686': 'value7488',
},
    {
    'id': 17527488866372,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Susan Rivers',
    'address': '6077 Jenna Loaf Apt. 021\nWuport, MS 90078',
    'text': 'Water do development. Room and television Mrs. Maybe story pass who imagine candidate. Gas reduce friend picture behavior.\nQuite Democrat kitchen Mr test. Young test toward occur list sort next.',
    'email': 'kevinpaul@example.com',
    'phone_number': '444-772-7960',
    'json': {
    'name': 'Mark Brown',
    'address': '6192 Justin Vista\nNew Krystalfort, MI 69172',
},
    'key48709': 'value63626',
    'key26225': 'value97099',
    'key53090': 'value9783',
},
    {
    'id': 17527488866385,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Tamara Williams',
    'address': '1503 Jessica Islands\nJohnsonchester, OK 57154',
    'text': 'Figure discover PM painting store like. Dog cold nor deal green. Instead recent doctor better use lose.',
    'email': 'johnhernandez@example.net',
    'phone_number': '(580)229-0923x475',
    'json': {
    'name': 'Juan Holt',
    'address': '6516 Andrew Crossroad\nMichaelside, PA 54154',
},
    'key53425': 'value77647',
    'key99654': 'value4453',
    'key48812': 'value720',
    'key9399': 'value30806',
    'key12411': 'value65544',
    'key83725': 'value16114',
    'key82647': 'value81586',
},
    {
    'id': 17527488866397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Calvin Walker',
    'address': '80940 Taylor Burg Suite 807\nKristenberg, WY 96142',
    'text': 'Tree organization husband black head capital interesting. Happen something right else chair fast. Cultural soon former sister though.',
    'email': 'patrick41@example.net',
    'phone_number': '(898)658-5142',
    'json': {
    'name': 'Reginald Bryan',
    'address': 'Unit 4663 Box 0034\nDPO AE 90859',
},
    'key39238': 'value97185',
    'key58354': 'value70127',
},
    {
    'id': 17527488866406,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Mrs. Heather Moore',
    'address': '371 Norton Prairie Apt. 945\nEast Antonioshire, AS 17506',
    'text': 'Enter responsibility president. Although why might leave class money security age.\nKnowledge memory degree someone everybody know list. Fine writer order per act maybe week move.',
    'email': 'qsnyder@example.org',
    'phone_number': '(238)527-5469x4975',
    'json': {
    'name': 'Melissa Rodriguez',
    'address': '15467 Robert Tunnel\nSouth Robertberg, MD 86441',
},
    'key52290': 'value55441',
    'key86172': 'value38531',
    'key53361': 'value460',
    'key44689': 'value22167',
    'key95974': 'value63546',
    'key5745': 'value8898',
},
    {
    'id': 17527488866417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jennifer Holmes',
    'address': '305 Durham Corners\nGilbertburgh, WV 47216',
    'text': 'Tell simple people. Relate safe oil crime information central. Whole other final fight.\nPopulation data field however avoid financial. Soldier they small professor yard.',
    'email': 'jennifer86@example.com',
    'phone_number': '001-695-761-4041x08422',
    'json': {
    'name': 'Elizabeth Fletcher',
    'address': '2885 Roy Pike Suite 258\nNelsonstad, AS 77685',
},
    'key5554': 'value91193',
    'key61313': 'value67427',
    'key85222': 'value35586',
    'key82241': 'value55693',
    'key80669': 'value37837',
    'key2467': 'value50657',
},
    {
    'id': 17527488866429,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Cory Thomas',
    'address': '9166 Allen Underpass\nDerekberg, VI 69161',
    'text': 'Play professional night cost action. With meeting your them chance home teacher.\nRange sound institution around success. Be opportunity finally more family I.',
    'email': 'jacksondonald@example.org',
    'phone_number': '378.308.7482x30352',
    'json': {
    'name': 'Andrew King',
    'address': '985 Berry Avenue Suite 610\nMelissaberg, AR 60693',
},
    'key94424': 'value54839',
    'key69573': 'value88215',
    'key75161': 'value5246',
    'key28821': 'value49280',
},
    {
    'id': 17527488866442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Angela Carter',
    'address': '5735 Albert Stravenue\nRichardtown, OR 47937',
    'text': 'Employee world light trouble wear miss. Article decision watch not. Avoid pressure think old available change step.',
    'email': 'rodriguezricardo@example.com',
    'phone_number': '947.276.8458',
    'json': {
    'name': 'Samuel Jones',
    'address': '07628 Miller Turnpike\nEricbury, CT 32247',
},
    'key58975': 'value7976',
    'key57574': 'value65209',
    'key10855': 'value56413',
    'key61087': 'value30205',
    'key90488': 'value99934',
    'key59241': 'value59581',
    'key83306': 'value21893',
    'key19772': 'value42175',
    'key45747': 'value36955',
    'key81140': 'value35099',
},
    {
    'id': 17527488866454,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'David Townsend',
    'address': '7764 Haynes Mission\nEast Douglas, WY 03756',
    'text': 'Federal read simple seem remain big mean. Accept reflect television know really.\nTogether because program north one people free.\nMovement PM realize. Act local owner once buy last present.',
    'email': 'beth49@example.com',
    'phone_number': '(458)913-6450',
    'json': {
    'name': 'Daniel Lane',
    'address': '61086 Johnson Road Suite 206\nPort Justin, PR 71971',
},
    'key83974': 'value4000',
},
    {
    'id': 17527488866466,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Renee Moore',
    'address': '12628 Jennifer Via\nStevensmouth, NJ 05427',
    'text': 'Image draw our indeed town toward decade four. Region exist positive out.\nOfficial year along leg provide.\nRemain for far movie able. Protect court movement rather nothing.',
    'email': 'ulee@example.net',
    'phone_number': '385.552.9024x2560',
    'json': {
    'name': 'Andre Patrick',
    'address': '29460 Nguyen Estate\nAndersonton, PR 79566',
},
    'key88571': 'value15086',
    'key1232': 'value83736',
    'key15714': 'value92159',
},
    {
    'id': 17527488866478,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Zachary Weeks',
    'address': '299 Smith Tunnel Suite 579\nJasonton, RI 25082',
    'text': 'Cause interesting president plan learn hair past. Bit stuff view challenge energy.',
    'email': 'robin64@example.net',
    'phone_number': '399-530-5078',
    'json': {
    'name': 'David Bradley',
    'address': '4661 Bradford Ville\nWest Travishaven, MH 76021',
},
    'key83914': 'value49759',
    'key51080': 'value58216',
    'key50192': 'value98071',
    'key6677': 'value83882',
    'key71242': 'value138',
    'key95973': 'value87622',
    'key97079': 'value60456',
    'key44323': 'value7210',
    'key14585': 'value5823',
},
    {
    'id': 17527488866490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Michael Scott',
    'address': '9060 William Coves\nRiosland, KY 61966',
    'text': 'Something as agreement mission better season herself material. Although how party prevent begin difficult age sure. City scene rock my during art.',
    'email': 'michelle10@example.net',
    'phone_number': '(787)575-9992x2735',
    'json': {
    'name': 'Heather Waller',
    'address': '366 Taylor Cove\nMargaretside, FL 88980',
},
    'key61315': 'value58588',
    'key8279': 'value259',
    'key87319': 'value7606',
},
    {
    'id': 17527488866502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Jordan Trujillo Jr.',
    'address': '0920 Morrison Court\nVargashaven, IN 63232',
    'text': 'Draw deal through hand her any. Us must moment set. Green become first out government.\nGeneration thank prepare learn election fly environment. Add question raise medical son training.',
    'email': 'robinsonpeggy@example.org',
    'phone_number': '+1-966-725-9796x6563',
    'json': {
    'name': 'Robert Ball',
    'address': '41978 Payne Bridge\nCopelandmouth, MS 82086',
},
    'key96334': 'value30101',
    'key90063': 'value87689',
    'key95921': 'value85000',
    'key33395': 'value55678',
    'key49811': 'value91366',
    'key62168': 'value38585',
    'key40858': 'value77939',
},
    {
    'id': 17527488866514,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jacqueline Trevino',
    'address': '7975 Hancock Well Apt. 450\nSouth Tiffanychester, CT 01815',
    'text': 'National because voice huge. Training significant physical culture former energy since. Whether boy pass ball himself close sense.',
    'email': 'george14@example.com',
    'phone_number': '001-218-620-3334',
    'json': {
    'name': 'Eric Hernandez',
    'address': '809 Wright Walk\nSouth Christopherfort, WA 85022',
},
    'key54832': 'value99930',
    'key47428': 'value91342',
    'key55111': 'value69990',
},
    {
    'id': 17527488866524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Shelley Crawford',
    'address': '1217 Nelson Mills Apt. 499\nLake Jennifer, IA 93810',
    'text': 'Some add wait stock support learn important rule. Life card three forget only seat.\nBetter win line owner through. Son loss join trouble.\nLaugh three feel real.',
    'email': 'george08@example.org',
    'phone_number': '+1-331-443-0280x112',
    'json': {
    'name': 'Nicholas Brown',
    'address': '149 York Village Suite 629\nEast Mckenziestad, CA 57162',
},
    'key86998': 'value33351',
    'key92953': 'value30749',
    'key65892': 'value58715',
    'key8184': 'value83843',
},
    {
    'id': 17527488866536,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Charles Cook',
    'address': 'Unit 7794 Box 2019\nDPO AA 94942',
    'text': 'About wish collection. Smile ready book maintain begin she hold.\nAll standard player at. General keep machine describe memory carry loss.',
    'email': 'wilsonshannon@example.net',
    'phone_number': '2674418171',
    'json': {
    'name': 'Kimberly Holloway',
    'address': '01286 Kimberly Mountain Apt. 560\nPort Russellville, RI 37086',
},
    'key75618': 'value21624',
    'key61057': 'value37287',
    'key21109': 'value23381',
    'key6857': 'value86509',
    'key36792': 'value11522',
    'key3078': 'value17777',
    'key54022': 'value61559',
    'key73117': 'value89184',
},
    {
    'id': 17527488866545,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Walter Stark',
    'address': '084 Garrett Forest Suite 715\nJessicashire, MT 07312',
    'text': 'A both specific two month soldier right. Stand walk six sort soldier. Least four fill management institution politics while.',
    'email': 'wguerrero@example.org',
    'phone_number': '624-965-5390x8038',
    'json': {
    'name': 'Diana Sanchez',
    'address': 'PSC 4864, Box 7850\nAPO AE 67820',
},
    'key42546': 'value80922',
    'key28418': 'value9642',
},
    {
    'id': 17527488866554,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Robert Hernandez',
    'address': '2631 Tyler Ridge Suite 211\nRoachside, MT 30966',
    'text': 'Late perform surface seem market beat seek improve. Provide kind affect able company book.\nPainting gun meeting also force itself. We hit situation. Any anything into prove production state.',
    'email': 'rileykelly@example.com',
    'phone_number': '5864005668',
    'json': {
    'name': 'Catherine Johnson',
    'address': 'Unit 1487 Box 8195\nDPO AA 79273',
},
    'key34565': 'value73105',
},
    {
    'id': 17527488866564,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Steven Reyes',
    'address': '118 Morgan Inlet\nPort Stacie, NV 87781',
    'text': 'Consumer stay artist carry job TV. Professor Republican part their. Door side energy fill beautiful.',
    'email': 'kathydelgado@example.org',
    'phone_number': '703.369.5687',
    'json': {
    'name': 'Adam Solis',
    'address': '26335 Mccarthy Light Apt. 337\nNorth Sharonhaven, MA 19139',
},
    'key60417': 'value14607',
    'key60086': 'value6103',
    'key60710': 'value74994',
    'key5358': 'value53132',
    'key14481': 'value21667',
    'key25161': 'value97715',
    'key45779': 'value11002',
    'key65015': 'value35061',
    'key56352': 'value81003',
},
    {
    'id': 17527488866574,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Justin Liu',
    'address': '6842 Smith Springs Suite 451\nHamptonberg, AS 47096',
    'text': 'Bit my create decide. Break machine together none money.\nThose tell style discover. Field already lose build. High management remember group green serve forward.',
    'email': 'snydertyler@example.org',
    'phone_number': '(616)862-3103x747',
    'json': {
    'name': 'Jennifer Gibbs',
    'address': '917 Stewart Rest\nTroystad, CA 62734',
},
    'key21942': 'value34226',
    'key76075': 'value88156',
    'key66912': 'value53698',
    'key51629': 'value90862',
    'key21429': 'value92925',
    'key37492': 'value12922',
    'key33150': 'value80281',
    'key72194': 'value47007',
    'key94590': 'value54787',
    'key12957': 'value44421',
},
    {
    'id': 17527488866586,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Robert Martinez',
    'address': '86450 Natalie Locks Apt. 523\nAshleyville, ID 21824',
    'text': 'Itself source your good. Ball seat call hear.\nArrive effect number take. Language week maintain technology theory event. Mention whose clear hotel job history strong particular.',
    'email': 'joelhill@example.net',
    'phone_number': '687.329.1976x060',
    'json': {
    'name': 'Molly Trujillo',
    'address': '31948 Lisa Walks Suite 190\nNorth Melissaville, WA 35451',
},
    'key45975': 'value31663',
    'key4075': 'value13772',
    'key31938': 'value3497',
    'key7774': 'value39517',
    'key57053': 'value66244',
    'key38594': 'value97086',
    'key90412': 'value23259',
    'key1605': 'value10833',
    'key12697': 'value91940',
    'key1544': 'value68614',
},
    {
    'id': 17527488866598,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jessica Williams',
    'address': '34427 Alvarado Camp Apt. 916\nLake Mary, NH 21512',
    'text': 'Democratic discuss beyond your season. Know statement with more various. Would none important big kind.\nFine upon base draw may. Ten national than very. Home fly large fast.',
    'email': 'jessica05@example.org',
    'phone_number': '955-653-4100x09305',
    'json': {
    'name': 'Christopher Watts',
    'address': 'PSC 2046, Box 8176\nAPO AA 09081',
},
    'key54546': 'value3783',
    'key77754': 'value32722',
},
    {
    'id': 17527488866607,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Misty Wells',
    'address': '18586 Richardson Ferry\nEast Heatherburgh, WI 22827',
    'text': 'Black order American suddenly maybe. Lay defense save answer style old. Fight back they rise impact.',
    'email': 'pateldaniel@example.net',
    'phone_number': '+1-834-706-7353x732',
    'json': {
    'name': 'Matthew Clark',
    'address': '2630 Crystal Valleys Apt. 343\nPort Veronicaburgh, DE 11227',
},
    'key21107': 'value18786',
    'key37947': 'value44089',
    'key22689': 'value37228',
    'key88595': 'value78970',
    'key37799': 'value67355',
    'key79824': 'value40626',
    'key76086': 'value30996',
},
    {
    'id': 17527488866618,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Daniel Anderson',
    'address': '481 Hull Orchard Apt. 048\nBrandonburgh, MD 82790',
    'text': 'Adult sound explain clear follow into level. Parent phone affect. Enough still success land but.\nDiscussion learn himself must card. Forward join issue dinner always.\nCare again film left.',
    'email': 'chandlerpatricia@example.org',
    'phone_number': '9614765200',
    'json': {
    'name': 'Ralph Mitchell',
    'address': '482 Gregory Views\nRodriguezborough, ID 35707',
},
    'key47884': 'value67309',
    'key73528': 'value58289',
    'key86015': 'value78599',
    'key43613': 'value3058',
    'key22056': 'value67995',
},
    {
    'id': 17527488866629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Mr. Patrick Stevens',
    'address': '995 Smith Loaf\nNorth Becky, NE 14131',
    'text': 'Point college measure quality what expect everybody. Including fact fear pretty. Wide green whom whether morning region.',
    'email': 'maria33@example.org',
    'phone_number': '742.744.8187',
    'json': {
    'name': 'Susan Simpson',
    'address': 'PSC 1060, Box 3373\nAPO AA 23857',
},
    'key18862': 'value99650',
    'key77756': 'value14685',
    'key94337': 'value59462',
    'key3925': 'value23392',
    'key14973': 'value79151',
    'key24874': 'value11135',
    'key57067': 'value42197',
    'key64006': 'value89177',
    'key73610': 'value33734',
},
    {
    'id': 17527488866647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Mariah Cabrera',
    'address': 'Unit 8766 Box 5437\nDPO AE 67087',
    'text': 'Movement seat produce. Hand budget herself conference themselves. Over similar available.\nDrug military heavy meet speech professional others. At artist even truth her. Lose attorney job gun total.',
    'email': 'jwells@example.net',
    'phone_number': '+1-470-420-9527x449',
    'json': {
    'name': 'Ann Griffith',
    'address': '551 Mata Forges\nAlexanderport, CT 31632',
},
    'key4856': 'value85514',
    'key36748': 'value10440',
    'key65087': 'value9646',
    'key28575': 'value34936',
    'key2432': 'value88948',
    'key47786': 'value46514',
    'key84425': 'value35076',
    'key85152': 'value15075',
},
    {
    'id': 17527488866658,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Kenneth Sanchez',
    'address': '0027 Roberto Gardens Suite 206\nLake Mary, SD 03895',
    'text': 'Play member serve author school low turn. Central claim her amount mean. Voice relationship probably citizen goal.\nChoice step together employee yes marriage not. Son meet Mr only big his poor.',
    'email': 'gibsonbrandon@example.net',
    'phone_number': '212-558-3319',
    'json': {
    'name': 'Dakota Mccoy',
    'address': '577 Davis Square\nMorganton, MT 19670',
},
    'key15861': 'value86418',
    'key80453': 'value40251',
    'key26301': 'value39027',
    'key6369': 'value62140',
    'key42329': 'value41642',
    'key47444': 'value27012',
    'key13975': 'value97986',
    'key77034': 'value57992',
    'key60355': 'value99778',
},
    {
    'id': 17527488866670,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Carol Hart',
    'address': '035 Harris Knoll Suite 640\nBishopshire, MO 30107',
    'text': 'Agent particularly tough president increase. Another subject result whom.',
    'email': 'richard28@example.net',
    'phone_number': '(645)908-2132',
    'json': {
    'name': 'Tammy Willis',
    'address': '50238 Smith Grove Suite 000\nRodneyfurt, ME 18841',
},
    'key20846': 'value58441',
    'key55523': 'value57132',
    'key45741': 'value12599',
    'key18961': 'value3686',
    'key49985': 'value87273',
    'key86528': 'value18100',
},
    {
    'id': 17527488866681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Janice Nguyen',
    'address': '710 Lisa Villages\nSouth Deannamouth, IA 99897',
    'text': 'Shoulder recent trial usually model. Site another director expect. Within defense wish.\nMaybe operation local available half today agency.\nHit ground very instead. Stage himself forward everyone.',
    'email': 'jfranklin@example.org',
    'phone_number': '873.984.5414x720',
    'json': {
    'name': 'Christopher Robinson',
    'address': '01217 Nancy Hills Suite 925\nMarkside, ME 47116',
},
    'key89686': 'value63828',
    'key91960': 'value18172',
    'key91389': 'value72707',
    'key21242': 'value69706',
    'key58673': 'value94907',
    'key77231': 'value39884',
    'key63154': 'value16553',
},
    {
    'id': 17527488866692,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Michelle Acevedo',
    'address': '61587 Ashley Ramp Suite 487\nMichaelfurt, FM 23477',
    'text': 'Avoid best growth short matter. Property make everything anything.\nNight southern size small front. Throughout Mr wall success.',
    'email': 'manningdeborah@example.com',
    'phone_number': '+1-923-748-9749x2869',
    'json': {
    'name': 'Margaret Ortega',
    'address': 'PSC 0058, Box 3039\nAPO AA 21662',
},
    'key37633': 'value61341',
},
    {
    'id': 17527488866702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Brett Ware',
    'address': '07429 Brown Vista\nKennethport, NE 17203',
    'text': 'Because under too hear. Billion city pattern goal ever put alone. At main provide. Above card law eat all quite business.\nCareer citizen each big common. Want hear office admit than.',
    'email': 'maryjackson@example.net',
    'phone_number': '+1-373-322-6932x792',
    'json': {
    'name': 'David Bowman',
    'address': '354 Blackwell Viaduct\nAndersontown, NC 05178',
},
    'key17918': 'value49041',
    'key78568': 'value83625',
},
    {
    'id': 17527488866713,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Sydney Johnson',
    'address': '9762 Jonathan Drive Suite 557\nPort Nicholas, PA 60066',
    'text': 'Everyone add put example less. Hundred military time character fight. Maintain right politics television car during.',
    'email': 'zboyer@example.net',
    'phone_number': '710.397.5962x489',
    'json': {
    'name': 'Tara Koch',
    'address': '2838 Hall Manors\nZacharyfurt, TX 82660',
},
    'key61926': 'value50269',
    'key98678': 'value11288',
    'key90509': 'value36578',
    'key48501': 'value86739',
},
    {
    'id': 17527488866724,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Julie Hughes',
    'address': '78313 Kyle Prairie Apt. 806\nJessechester, ME 26068',
    'text': 'Think south him fund. Adult year although spring. Provide only pay page foreign. Federal knowledge bar than develop goal.\nCandidate number federal where alone yes two. Rate benefit voice face.',
    'email': 'dawn55@example.com',
    'phone_number': '960.856.9360x37291',
    'json': {
    'name': 'Samantha Davis',
    'address': '740 Rowland Via Suite 943\nMichaelmouth, WV 09449',
},
    'key22452': 'value52865',
    'key34863': 'value59623',
    'key80813': 'value8321',
    'key69717': 'value68417',
    'key2076': 'value53598',
    'key95814': 'value43259',
    'key16919': 'value26146',
    'key65047': 'value42836',
    'key36966': 'value485',
},
    {
    'id': 17527488866735,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Andrew Perry',
    'address': '88967 Ellis Shoal\nJamesburgh, CA 53378',
    'text': 'Ever development quality never different blood country. Region culture night kid standard method. Hard able small all wind rich central cover.',
    'email': 'justintaylor@example.net',
    'phone_number': '845-933-1451x4031',
    'json': {
    'name': 'Aaron Bean',
    'address': '953 Jared Lights\nJeffreystad, LA 98419',
},
    'key81054': 'value72157',
    'key46453': 'value12276',
    'key63143': 'value18134',
    'key75943': 'value96096',
    'key9075': 'value37026',
    'key14318': 'value98907',
    'key58005': 'value91248',
    'key59381': 'value16177',
    'key90131': 'value24636',
    'key6336': 'value99501',
},
    {
    'id': 17527488866746,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Jamie Ferguson',
    'address': '2808 Meyer Isle Apt. 432\nPort George, ID 28720',
    'text': 'Top pull case. Near site general.\nFriend cut sea agent involve difference different cover. Stand speak somebody way we.',
    'email': 'susanpham@example.net',
    'phone_number': '(418)790-6903',
    'json': {
    'name': 'Richard Bell',
    'address': '53586 Carolyn Inlet\nEast Katherineside, IN 25090',
},
    'key95091': 'value84559',
    'key31895': 'value92126',
    'key96485': 'value95658',
    'key9995': 'value86250',
    'key34806': 'value77432',
},
    {
    'id': 17527488866758,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Karen Wilson',
    'address': 'USNV Burgess\nFPO AP 31642',
    'text': 'Game between plant always maintain out fear clearly. To effect have degree respond her. Require recently beautiful much speech commercial. Coach attention security senior long.',
    'email': 'zcarroll@example.org',
    'phone_number': '867-939-4411x0822',
    'json': {
    'name': 'Norma Thompson',
    'address': '450 Ronald Brook\nEast Ann, OH 78246',
},
    'key27404': 'value69724',
    'key38365': 'value34574',
    'key69110': 'value77287',
    'key31839': 'value28259',
    'key47282': 'value48466',
    'key81607': 'value67959',
    'key7761': 'value39441',
    'key41548': 'value907',
},
    {
    'id': 17527488866768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Tracy Hill',
    'address': '584 Moore Ramp\nWest Jermaineberg, DE 14500',
    'text': 'Phone like material enjoy. Most serve heart policy measure clearly. Everybody war morning anything analysis would.\nSouthern against community red. Growth tough bar range cup beautiful save stay.',
    'email': 'suzanne03@example.com',
    'phone_number': '730.976.5848',
    'json': {
    'name': 'Paige Morales',
    'address': '10757 Jackson Track\nNew John, AL 39439',
},
    'key59689': 'value41726',
},
    {
    'id': 17527488866778,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'John Brooks',
    'address': '56456 Ronald Mount\nDanielleport, RI 96243',
    'text': 'Career attack happy beautiful. Evening performance security our tonight detail health short.',
    'email': 'khamilton@example.org',
    'phone_number': '302.323.8042x3058',
    'json': {
    'name': 'Tyler Williams',
    'address': '8186 Moody Shores Apt. 190\nWest Amber, PA 04492',
},
    'key29398': 'value39037',
    'key45970': 'value39157',
    'key65470': 'value30520',
    'key65572': 'value69127',
    'key34332': 'value27596',
},
    {
    'id': 17527488866788,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Carolyn Adams',
    'address': '2756 Short Knolls Apt. 001\nNorth Lisaview, NM 30383',
    'text': 'West grow north buy truth. Analysis stand sense five create. Early with him party.\nSchool table several. Performance song too four cover language food. Table inside peace inside else.',
    'email': 'combsmark@example.com',
    'phone_number': '4146612482',
    'json': {
    'name': 'Joseph Johnson',
    'address': '68754 Heather Junctions Suite 375\nWest Kevinfurt, OK 90185',
},
    'key38970': 'value82299',
    'key32499': 'value81682',
},
    {
    'id': 17527488866800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Robert Charles',
    'address': '734 Patricia Brook Apt. 053\nNorth Theresa, CT 06566',
    'text': 'Man family top pass pick discussion. Keep deal election war throughout possible indicate still. Produce mission seat effect.',
    'email': 'hillcharles@example.org',
    'phone_number': '439.380.3437x8505',
    'json': {
    'name': 'Randy Miller MD',
    'address': '1403 Edward Squares Suite 408\nPort Stevenshire, RI 28847',
},
    'key7970': 'value64646',
    'key59975': 'value89554',
    'key29349': 'value7805',
    'key19337': 'value40418',
},
    {
    'id': 17527488866812,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Garrett Hopkins',
    'address': 'PSC 9652, Box 0073\nAPO AP 53873',
    'text': 'Sense store determine suggest public. Main third require thought.',
    'email': 'kparker@example.org',
    'phone_number': '568-271-6168x2673',
    'json': {
    'name': 'Ashley Logan',
    'address': '8014 Timothy Walks Suite 306\nBrittanyburgh, WY 59618',
},
    'key62305': 'value25982',
    'key36355': 'value23336',
    'key77152': 'value54163',
    'key72804': 'value33683',
    'key57976': 'value65379',
    'key88641': 'value98951',
    'key10065': 'value79692',
    'key38084': 'value53553',
    'key93447': 'value18792',
    'key47949': 'value88989',
},
    {
    'id': 17527488866821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Vincent Ferrell',
    'address': '39888 Levine Crest\nRobertland, ME 43383',
    'text': 'Among sing whom face own. Painting experience worker rather across question agreement.',
    'email': 'aaronhale@example.org',
    'phone_number': '940.340.8179x447',
    'json': {
    'name': 'Jennifer Moore',
    'address': '1103 Johnson Harbors\nHollyfort, GU 15854',
},
    'key87776': 'value16191',
    'key56503': 'value29483',
    'key21526': 'value13128',
},
    {
    'id': 17527488866832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Sheila Thomas',
    'address': '8527 Cesar Flat\nEast Lynnville, HI 87755',
    'text': 'Key deep entire discover at institution including. Thus remain sell bank. Easy own tend couple gun current no.',
    'email': 'hhoffman@example.com',
    'phone_number': '(512)803-8778x57564',
    'json': {
    'name': 'Bradley Harper',
    'address': '93769 Raymond Common\nNew Rodneytown, LA 50427',
},
    'key75897': 'value30796',
},
    {
    'id': 17527488866843,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Jonathan Gutierrez',
    'address': '48259 Collins Motorway\nValenciachester, FL 79763',
    'text': 'Threat bad fly country law fill weight. Month health word learn how myself. Firm democratic determine successful offer rest.\nAnswer allow large senior during same. Season green smile fund his less.',
    'email': 'willie10@example.org',
    'phone_number': '+1-867-550-7097x07223',
    'json': {
    'name': 'Haley Robinson',
    'address': '95516 Cooper Lane\nSmithport, MT 60178',
},
    'key65120': 'value54520',
    'key62104': 'value13249',
    'key29703': 'value42794',
    'key4777': 'value28989',
    'key98708': 'value98302',
    'key85951': 'value15107',
    'key62585': 'value55448',
},
    {
    'id': 17527488866856,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Jose Lee',
    'address': 'USNV Lowe\nFPO AE 68991',
    'text': 'Standard kitchen his his. Product provide life community group contain level him. Rate deal garden we should stage.\nThat recently we always hand.',
    'email': 'jacob09@example.org',
    'phone_number': '355-457-9753',
    'json': {
    'name': 'Scott Douglas',
    'address': 'Unit 6977 Box 6409\nDPO AE 79357',
},
    'key25349': 'value80032',
},
    {
    'id': 17527488866864,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Christian Black',
    'address': '970 Janet Center\nJohnsonchester, OK 16688',
    'text': 'Next require bed collection above. Law economic commercial create buy. Face authority animal former own.\nGlass evidence cut.\nGreat finish only school. Kid quite identify growth instead.',
    'email': 'sshort@example.org',
    'phone_number': '719-592-4231',
    'json': {
    'name': 'Eric Dyer',
    'address': '578 Angela Knoll\nWest Alexisburgh, NV 58366',
},
    'key88582': 'value92125',
},
    {
    'id': 17527488866874,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Russell Burke',
    'address': '53544 Arroyo Way Suite 846\nNorth Noah, AS 35709',
    'text': 'Movie several the voice. Material before friend mean factor better. Next half rate bring girl lose thousand.',
    'email': 'melissa24@example.org',
    'phone_number': '701-484-0462',
    'json': {
    'name': 'Charles Brady',
    'address': '42288 Johnson Club\nSouth Thomas, FL 53352',
},
    'key87044': 'value42527',
    'key80914': 'value24185',
    'key56467': 'value9577',
    'key61945': 'value24797',
    'key44113': 'value78865',
    'key15788': 'value93958',
    'key85826': 'value94813',
    'key54356': 'value34427',
    'key46308': 'value639',
    'key39684': 'value41116',
},
    {
    'id': 17527488866885,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Sharon Green',
    'address': '021 Galloway Radial\nSouth Michael, NY 88891',
    'text': 'Wall sort exist information national. Seat own thank level fire laugh back.',
    'email': 'morrisbruce@example.net',
    'phone_number': '(644)428-8877x90339',
    'json': {
    'name': 'Tracy Turner',
    'address': '18884 Andrew Shoal Apt. 602\nWhiteshire, DE 48368',
},
    'key4806': 'value39458',
    'key51505': 'value70914',
    'key17628': 'value42770',
    'key93429': 'value29493',
    'key33241': 'value33445',
},
    {
    'id': 17527488866897,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Christopher Shea',
    'address': 'PSC 9414, Box 8075\nAPO AA 61238',
    'text': 'Source staff expert must. Force run service face drug just top there. According easy worker stuff simple mother decade might.',
    'email': 'douglas74@example.org',
    'phone_number': '+1-971-541-1002x828',
    'json': {
    'name': 'Zachary Jackson',
    'address': 'PSC 0055, Box 6862\nAPO AA 99935',
},
    'key26036': 'value14992',
    'key40656': 'value3092',
    'key97247': 'value77671',
    'key51788': 'value49704',
    'key20936': 'value27126',
    'key35561': 'value49488',
    'key92786': 'value45724',
    'key57040': 'value24976',
},
    {
    'id': 17527488866903,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Alexandra Mitchell',
    'address': '060 Timothy Cliffs Apt. 934\nCarrside, AS 47520',
    'text': 'Go near budget out fear road. Hot notice wife.\nPicture who watch opportunity ten area help. Republican situation occur budget often tonight.',
    'email': 'patrick00@example.com',
    'phone_number': '365.529.0413x91258',
    'json': {
    'name': 'Peter Smith',
    'address': '45250 Zimmerman Summit\nNancyview, SC 71249',
},
    'key9442': 'value82794',
},
    {
    'id': 17527488866914,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Tiffany Medina',
    'address': '8817 Farmer Gardens\nJasonchester, IN 84685',
    'text': 'Myself draw affect area leader. Help ask believe general investment crime fight. Return too personal radio close decade.',
    'email': 'morsedonald@example.com',
    'phone_number': '+1-798-206-3560x4818',
    'json': {
    'name': 'James Carey',
    'address': '86420 Janice Isle Suite 946\nJimenezland, MI 63388',
},
    'key41160': 'value4731',
    'key75118': 'value34419',
    'key18966': 'value11668',
    'key38110': 'value99894',
    'key86017': 'value94810',
    'key71926': 'value14339',
    'key68085': 'value8856',
    'key43081': 'value14915',
    'key52699': 'value86565',
    'key67724': 'value44065',
},
    {
    'id': 17527488866926,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Kyle Becker',
    'address': '4342 Haas Roads Apt. 916\nRoachstad, VT 21804',
    'text': 'Article case last near agree unit challenge.\nGas cost white finish real. National town position. Total tend beautiful common but image.',
    'email': 'thomasjeffrey@example.org',
    'phone_number': '(897)845-4598x938',
    'json': {
    'name': 'Sarah Brown',
    'address': '694 Lee Coves Apt. 708\nBeckfort, KY 75324',
},
    'key12349': 'value47282',
    'key94702': 'value78050',
    'key64573': 'value1327',
    'key55319': 'value16701',
    'key80519': 'value55377',
},
    {
    'id': 17527488866938,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Erin Webb',
    'address': 'Unit 1047 Box 2674\nDPO AE 32887',
    'text': 'Agency dark research process pull describe. Certainly response head group almost skill and site.\nEnjoy poor gun. Structure different guess value measure. Property majority with upon movie place.',
    'email': 'mccarthyryan@example.com',
    'phone_number': '001-965-711-9763x51353',
    'json': {
    'name': 'Matthew Torres',
    'address': '67061 Walters Mission\nSouth Timothystad, AS 15964',
},
    'key6277': 'value89518',
    'key77674': 'value60249',
    'key63231': 'value70449',
},
    {
    'id': 17527488866948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Justin Meyers',
    'address': '743 Thomas Vista\nPort Jenniferhaven, PA 50151',
    'text': 'Adult read baby professional short life draw. Guy recognize bring hope include check someone. Enjoy like five answer consumer she. Everyone current all remain.',
    'email': 'victorharris@example.net',
    'phone_number': '(938)292-0764x346',
    'json': {
    'name': 'Jean Jenkins',
    'address': '3885 Stephanie Square Apt. 896\nSchmidtview, OR 60765',
},
    'key52570': 'value44549',
    'key20807': 'value56968',
    'key39502': 'value81992',
    'key19347': 'value54350',
    'key85216': 'value89065',
    'key98271': 'value55525',
},
    {
    'id': 17527488866959,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Patricia Bean',
    'address': '6330 Kayla Ranch\nAnnahaven, AK 78492',
    'text': 'Yeah many compare impact heavy watch. Relationship inside fly teacher.\nCar serious bill.\nFront personal player four else blood somebody.',
    'email': 'cynthia92@example.org',
    'phone_number': '001-600-541-7220',
    'json': {
    'name': 'Suzanne Williams DVM',
    'address': '0436 Pearson Lights Suite 670\nMeganstad, NY 30856',
},
    'key12228': 'value89019',
},
    {
    'id': 17527488866969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jason Ray',
    'address': '37031 Contreras Plain Suite 842\nWest Angelview, NV 91137',
    'text': 'All happen down strong. Make record team my.\nEnergy most million financial of. Without commercial week plan visit turn. Sign run idea land ready organization store.\nCare resource race into attention.',
    'email': 'vfowler@example.org',
    'phone_number': '(978)451-1790x75205',
    'json': {
    'name': 'Anthony Rodriguez',
    'address': '4093 Dennis Isle Suite 875\nWest Brian, VI 16975',
},
    'key59699': 'value64509',
    'key36379': 'value44618',
    'key78794': 'value95630',
    'key48900': 'value93276',
    'key27682': 'value97856',
},
    {
    'id': 17527488866980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Terri Hayes',
    'address': '891 Montes Islands Suite 604\nAarontown, AS 33047',
    'text': 'Compare Republican may property trip month method. Sea nothing American floor travel wind. Hand teach down heavy so response poor.',
    'email': 'crystalhernandez@example.net',
    'phone_number': '383-242-3304x428',
    'json': {
    'name': 'Shawn Melendez',
    'address': 'PSC 6650, Box 3557\nAPO AE 77254',
},
    'key49216': 'value28528',
    'key86437': 'value21533',
    'key2923': 'value20682',
    'key72405': 'value73133',
    'key94805': 'value65334',
    'key8759': 'value46374',
    'key47848': 'value15073',
    'key18021': 'value34863',
    'key74877': 'value54408',
    'key35593': 'value32975',
},
    {
    'id': 17527488866990,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Elizabeth Webb',
    'address': '712 Elizabeth Shoals Suite 746\nLake Collin, VI 39486',
    'text': 'Nor protect economy which interview. Moment important fire candidate. Apply none no four lead.\nExpect good again public sort. Pm option scientist economy course pay task.',
    'email': 'trevor86@example.org',
    'phone_number': '456-390-2044',
    'json': {
    'name': 'Melissa Rodriguez',
    'address': '1891 Jennifer Court Apt. 425\nRamoshaven, DE 29123',
},
    'key44388': 'value62514',
    'key54248': 'value80380',
    'key13140': 'value45600',
    'key96913': 'value1126',
    'key21209': 'value63019',
    'key31560': 'value6534',
    'key51386': 'value10124',
    'key7015': 'value33259',
    'key35272': 'value63958',
    'key79198': 'value73438',
},
    {
    'id': 17527488867001,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Kristin Rodriguez',
    'address': '559 Silva Highway\nWest Jennifer, VI 79697',
    'text': 'Level question else weight each hear. Music remember within music.\nCulture career skin month. Hot turn old than bill. Water hit memory price.',
    'email': 'davidshah@example.org',
    'phone_number': '824.446.5302',
    'json': {
    'name': 'Katherine Cantrell',
    'address': '49481 Fisher Tunnel\nSamanthatown, OH 07675',
},
    'key33791': 'value28607',
    'key52052': 'value52750',
    'key75901': 'value49665',
    'key26856': 'value50984',
    'key64792': 'value74476',
    'key81543': 'value59008',
    'key46246': 'value51340',
    'key24027': 'value43508',
},
    {
    'id': 17527488867012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Kevin Smith',
    'address': '598 Benson Hill Suite 160\nNorth Connieville, ND 71671',
    'text': 'Sort plan human management. That production by me do. Rule possible thought next everybody nothing direction.\nThus later song alone professional. Take rule last senior bar health. Keep from lay.',
    'email': 'sschwartz@example.org',
    'phone_number': '001-367-808-8588x6271',
    'json': {
    'name': 'David Wong',
    'address': '37860 Winters Flat\nSaundersberg, AS 82607',
},
    'key27662': 'value91383',
},
    {
    'id': 17527488867024,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Jerry Mitchell',
    'address': '131 Melissa Forest\nJasonmouth, ND 67736',
    'text': 'What speech card try move catch. Thing wall could song sit.\nAnother other conference however know into court. Detail party budget short.',
    'email': 'andersonkenneth@example.org',
    'phone_number': '+1-566-201-6781x2679',
    'json': {
    'name': 'William Walker',
    'address': '760 Darren Creek\nRoberthaven, CA 34760',
},
    'key38412': 'value54664',
    'key73421': 'value87840',
    'key64267': 'value25738',
},
    {
    'id': 17527488867035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Joshua Harmon',
    'address': '854 David Groves Apt. 271\nLopezport, AS 08075',
    'text': 'Arm practice as wonder great purpose late. Throw station call true.\nBeyond weight card. Because guess strong second stand play.\nOperation born or bag parent. Majority very series eight hope.',
    'email': 'mcollins@example.com',
    'phone_number': '+1-455-942-7418x421',
    'json': {
    'name': 'Christopher Gibson',
    'address': '7797 Gibson Centers\nChrisfort, FL 90202',
},
    'key86178': 'value72449',
    'key33546': 'value80471',
    'key31188': 'value17557',
},
    {
    'id': 17527488867047,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Scott Mcguire',
    'address': '033 Leonard Forest Apt. 870\nSouth Taylor, DC 10873',
    'text': 'Force next citizen performance individual happen their. Commercial bed just TV point describe me white. Wear and book one.\nCar serve article allow. Section significant TV strong coach now special.',
    'email': 'debraparker@example.com',
    'phone_number': '001-741-329-6731x979',
    'json': {
    'name': 'Michelle Wall',
    'address': '9718 Gray Circles Apt. 906\nKayleebury, MN 95237',
},
    'key32166': 'value33592',
    'key30269': 'value33121',
    'key78159': 'value18030',
    'key44047': 'value72000',
},
    {
    'id': 17527488867060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Evelyn Wilson',
    'address': '73076 Wyatt Junction\nNew Chelsealand, IN 00863',
    'text': 'Need west account building cover true challenge. West career conference turn paper.\nPass candidate place understand. Her wish sure involve of very administration. Lawyer use under far dream.',
    'email': 'adam58@example.org',
    'phone_number': '415-516-9761',
    'json': {
    'name': 'Todd Cunningham',
    'address': '73595 Holmes Highway Apt. 659\nAaronport, VA 55226',
},
    'key38422': 'value66975',
    'key4888': 'value4756',
    'key66237': 'value19507',
    'key19713': 'value96734',
    'key41155': 'value71565',
},
    {
    'id': 17527488867072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Sarah Wilkerson',
    'address': '5489 Christina Turnpike Suite 744\nPort Anthonymouth, DC 60772',
    'text': 'Federal though resource vote other fact. Common guess way son process unit.\nWhen bar tough share. Stuff charge something attack. Represent analysis student receive debate.',
    'email': 'richardsonjason@example.net',
    'phone_number': '969-388-7557x606',
    'json': {
    'name': 'Kevin Harris DDS',
    'address': 'PSC 8293, Box 1294\nAPO AE 06637',
},
    'key88775': 'value1835',
    'key34921': 'value6949',
    'key73941': 'value40602',
},
    {
    'id': 17527488867083,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Savannah Mcguire',
    'address': '3706 Grant Burg\nSouth Kevin, TN 23853',
    'text': 'Admit education hold candidate decide. Imagine base really beautiful free.\nCost treat prevent kitchen close. Lead court week recent class. It student trial drop.',
    'email': 'ianadkins@example.com',
    'phone_number': '(852)826-3765',
    'json': {
    'name': 'Todd Howard',
    'address': '26358 Gonzalez Canyon Apt. 557\nNew Andrechester, KY 07177',
},
    'key96412': 'value98042',
    'key76218': 'value27357',
    'key50391': 'value68954',
},
    {
    'id': 17527488867096,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Rita Sanchez',
    'address': '355 Dodson Corners Apt. 327\nDanielmouth, NE 63743',
    'text': 'Sister star write news recent their hit. Take mean whole heavy. Onto nor exist teach maybe attack movement with.',
    'email': 'udecker@example.net',
    'phone_number': '317.900.8768',
    'json': {
    'name': 'Jessica Callahan',
    'address': '07417 Evan Radial\nPort Jessica, ID 38137',
},
    'key39914': 'value90880',
    'key7456': 'value33035',
    'key74652': 'value18221',
    'key41307': 'value59651',
    'key73727': 'value66496',
    'key48053': 'value92274',
    'key82690': 'value1569',
},
    {
    'id': 17527488867108,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jessica Reyes',
    'address': '04335 Guerrero Corner\nGreenehaven, CA 49612',
    'text': 'Dark suffer art worker. Everyone professor two whose.\nYourself why face represent. Financial financial line treat hotel.\nScene just short state.',
    'email': 'jesse95@example.com',
    'phone_number': '951.242.9959x218',
    'json': {
    'name': 'Gary Mccullough',
    'address': '61009 Mary Trail\nWest Angelaburgh, KS 52289',
},
    'key27302': 'value24586',
    'key45140': 'value6930',
    'key23652': 'value922',
    'key80427': 'value73973',
    'key76538': 'value87791',
    'key64900': 'value25840',
    'key89998': 'value83234',
    'key11115': 'value81558',
    'key31353': 'value28627',
    'key61768': 'value83021',
},
    {
    'id': 17527488867121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jacob Burton',
    'address': 'Unit 0153 Box 4203\nDPO AE 64279',
    'text': 'Question far participant east. Language fast spend whatever for control pressure.\nAddress ready bag road mouth young. Call west center truth sell any thousand indicate.',
    'email': 'yward@example.net',
    'phone_number': '305.725.7452x292',
    'json': {
    'name': 'John Gutierrez',
    'address': '54200 Hawkins Lodge\nNew Stephanieborough, OH 91416',
},
    'key58963': 'value5661',
    'key26189': 'value54131',
    'key50986': 'value65998',
    'key48981': 'value90238',
    'key95359': 'value94973',
    'key46248': 'value86841',
    'key65215': 'value73727',
    'key35394': 'value4154',
},
    {
    'id': 17527488867131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jacob Thompson',
    'address': '3357 Jeffrey Highway\nBrownshire, AK 44645',
    'text': 'Join else air explain standard up. Statement contain mission artist choose.\nOrder price build put issue. Wrong down husband more upon author method husband.',
    'email': 'dianemendez@example.org',
    'phone_number': '(716)580-4967x520',
    'json': {
    'name': 'Robert Rivera',
    'address': '3294 Matthew Squares Suite 598\nEast Sydney, AZ 30984',
},
    'key28764': 'value4839',
    'key1281': 'value6642',
    'key68373': 'value2157',
    'key5694': 'value39255',
},
    {
    'id': 17527488867143,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Nichole Cabrera',
    'address': '400 Bauer Circles\nPort Brandy, KY 24058',
    'text': 'Anything analysis collection anyone hour. Office maintain employee.\nEvening a season even. Run condition share eye choose stay student. Term behavior deal wife. Market church able.',
    'email': 'melissamorris@example.org',
    'phone_number': '289.507.2046x673',
    'json': {
    'name': 'Andrew Holt',
    'address': '6286 Penny Rue\nWhiteheadfort, GA 10460',
},
    'key39531': 'value83695',
    'key36880': 'value14857',
    'key32976': 'value56875',
    'key39378': 'value48813',
    'key36330': 'value83299',
    'key21602': 'value38828',
},
    {
    'id': 17527488867155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Katherine Moore',
    'address': 'USCGC Gonzales\nFPO AA 23150',
    'text': 'Full often box.\nSea provide class never soon public require. Example vote surface.',
    'email': 'bsnyder@example.org',
    'phone_number': '668-759-4591',
    'json': {
    'name': 'Justin Thompson',
    'address': '73360 Miller Junctions\nCarterport, VA 45071',
},
    'key45900': 'value33569',
    'key21651': 'value347',
    'key9848': 'value88516',
    'key45444': 'value93900',
    'key60568': 'value27228',
    'key54822': 'value2673',
},
    {
    'id': 17527488867166,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Megan Welch',
    'address': '883 Shane Crest Apt. 657\nPowershaven, NE 70212',
    'text': 'Night artist as. Experience remain no life above analysis enough almost. American we although American.',
    'email': 'meyerrachel@example.org',
    'phone_number': '441-441-2296x456',
    'json': {
    'name': 'James Lopez',
    'address': 'PSC 4710, Box 9016\nAPO AA 54850',
},
    'key42284': 'value78495',
    'key53329': 'value78869',
    'key81183': 'value26137',
    'key37263': 'value64819',
    'key74085': 'value97629',
    'key10904': 'value54021',
    'key59498': 'value15190',
},
    {
    'id': 17527488867177,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'William Perez',
    'address': '2867 Russell Lane Apt. 107\nPort Katherineland, MI 89981',
    'text': 'Stay finally suggest movie catch cup water. Raise first follow cover bag. Exactly few left Mrs.',
    'email': 'christopher16@example.com',
    'phone_number': '+1-656-848-8020x4971',
    'json': {
    'name': 'Lauren Wilson',
    'address': '198 Vazquez Freeway\nHallmouth, OR 95600',
},
    'key40200': 'value48880',
    'key31918': 'value16074',
    'key16624': 'value16067',
    'key16332': 'value24453',
    'key44074': 'value10253',
    'key63528': 'value24756',
    'key62085': 'value2125',
    'key40571': 'value36318',
},
    {
    'id': 17527488867189,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Ms. Marie Moore',
    'address': '320 James Mount\nAlexandriaside, PA 66952',
    'text': 'Well hard stand population run past.\nRather school improve reason. Position impact detail be environmental owner item. Pattern sit front something. That none country.',
    'email': 'heathergarcia@example.org',
    'phone_number': '5336672587',
    'json': {
    'name': 'Harry Walters',
    'address': '44856 Miles Views\nNew Lisatown, AS 70081',
},
    'key99570': 'value44427',
    'key6172': 'value11028',
    'key41879': 'value39326',
    'key7698': 'value93085',
    'key7202': 'value49545',
},
    {
    'id': 17527488867201,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Ryan Bradford',
    'address': 'Unit 6544 Box 5750\nDPO AP 80514',
    'text': 'Mouth break box dream even. Who often approach it partner standard yeah new. Mother or magazine loss each. Character black since production certainly most.',
    'email': 'matthewpreston@example.com',
    'phone_number': '(246)892-6386',
    'json': {
    'name': 'Cheryl Shelton MD',
    'address': '82336 Wilson Summit\nEast Brenda, TN 93049',
},
    'key19204': 'value864',
    'key34249': 'value54230',
    'key34264': 'value24247',
    'key99887': 'value52983',
    'key24033': 'value23480',
    'key51676': 'value799',
    'key15724': 'value90181',
    'key31269': 'value63668',
    'key12467': 'value96644',
},
    {
    'id': 17527488867212,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Debbie Mccoy',
    'address': '89183 Charles Branch Suite 051\nLake Robinborough, CT 48892',
    'text': 'Production put alone recently financial draw. Election worker wind down. Friend daughter do every current act fly.',
    'email': 'samuel49@example.com',
    'phone_number': '(489)776-7991',
    'json': {
    'name': 'David Sanchez',
    'address': '369 Porter Ramp\nWest Kristychester, PW 11916',
},
    'key9952': 'value74346',
    'key53153': 'value74101',
    'key82603': 'value26791',
    'key76260': 'value68049',
    'key11928': 'value57853',
    'key44248': 'value19744',
    'key66290': 'value44315',
    'key39240': 'value27064',
    'key65021': 'value8157',
    'key36343': 'value25799',
},
    {
    'id': 17527488867224,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Taylor Stephens',
    'address': 'Unit 8029 Box 5705\nDPO AA 67503',
    'text': 'Miss fund two that moment thus. Hour toward then certain vote tax.\nOne environment impact environment almost rock. Film make space forward memory. Whole under subject soldier concern.',
    'email': 'sherry15@example.com',
    'phone_number': '(768)881-7166x8494',
    'json': {
    'name': 'Patrick Sanders',
    'address': '79399 Julie Ridges\nJohnview, UT 67300',
},
    'key93294': 'value41301',
    'key73958': 'value3552',
    'key26392': 'value23840',
    'key45110': 'value69328',
    'key67614': 'value18486',
    'key44935': 'value68801',
    'key64606': 'value72313',
},
    {
    'id': 17527488867234,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Mark Mcdonald',
    'address': '624 Melanie Manor Suite 598\nSouth Thomas, AZ 10297',
    'text': 'Your environment officer recently amount third true. May nature happen everything term nothing.\nWithin evening her. Financial similar southern fight mean green. Wall may current spring common wait.',
    'email': 'alangomez@example.org',
    'phone_number': '+1-506-225-3458x66664',
    'json': {
    'name': 'Joyce Lee',
    'address': '507 Sophia Stream\nJodimouth, ID 44153',
},
    'key62206': 'value97898',
    'key19764': 'value46651',
    'key22292': 'value74331',
    'key2088': 'value6277',
    'key85627': 'value71961',
},
    {
    'id': 17527488867246,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Matthew Gill',
    'address': '9141 Smith Haven\nFostershire, DC 71023',
    'text': 'House according whole everyone guy believe push. Condition by both wide. Around outside receive individual trade exist.\nPoor rather within law. Song option plant with never appear.',
    'email': 'douglaskyle@example.net',
    'phone_number': '461.244.8621x97423',
    'json': {
    'name': 'Aimee Parker',
    'address': 'Unit 9961 Box 9746\nDPO AA 03960',
},
    'key87103': 'value45437',
    'key42086': 'value92981',
    'key69476': 'value87372',
    'key21874': 'value64059',
    'key68600': 'value69920',
    'key48354': 'value11025',
    'key42591': 'value95675',
    'key14275': 'value67784',
},
    {
    'id': 17527488867257,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'James Nichols',
    'address': '5725 Gomez Junction\nNorth Jacob, VT 98479',
    'text': 'Offer special Republican increase against. Figure notice him investment series.',
    'email': 'brianna99@example.org',
    'phone_number': '797.617.3030x55497',
    'json': {
    'name': 'Thomas Griffin Jr.',
    'address': '9431 Maria Springs Suite 168\nSarahfort, CO 94536',
},
    'key62670': 'value59806',
    'key61742': 'value72234',
    'key39849': 'value18989',
    'key93863': 'value97177',
    'key1359': 'value41640',
    'key78043': 'value19632',
},
    {
    'id': 17527488867268,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Krystal Nelson',
    'address': 'Unit 9975 Box 5294\nDPO AP 76683',
    'text': 'Contain need significant away try. Base partner just yet agree.\nWin election cell throw test lay interest perhaps. Responsibility something free thousand floor. Everyone air decide baby full word.',
    'email': 'jayarroyo@example.org',
    'phone_number': '+1-388-231-0826',
    'json': {
    'name': 'Michael Smith',
    'address': '3902 Savannah Junction\nEast Tonyastad, NM 38913',
},
    'key17619': 'value58515',
    'key40944': 'value32422',
    'key60879': 'value35496',
    'key4351': 'value47260',
    'key43844': 'value15883',
    'key38573': 'value80353',
    'key11088': 'value96197',
    'key67349': 'value13321',
    'key73200': 'value56948',
    'key13430': 'value81851',
},
    {
    'id': 17527488867278,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Stephanie Ryan',
    'address': '943 Nichols Island\nAguilarside, UT 44768',
    'text': 'Because product short religious avoid. Administration officer hope. Head dark thank.\nPage score particularly machine style. Even despite technology stay yard.',
    'email': 'harrisadrian@example.com',
    'phone_number': '566-395-0505',
    'json': {
    'name': 'Nicholas Vargas',
    'address': '7941 Lisa Fork\nWest Sherryside, ID 98472',
},
    'key58755': 'value47011',
    'key61368': 'value19625',
},
    {
    'id': 17527488867290,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Corey Navarro',
    'address': '2420 Freeman Pines\nSouth Erin, WV 87627',
    'text': 'Reach again example heart wind. Most away mouth dog agent character majority. Data society challenge not four pay.',
    'email': 'nicole60@example.net',
    'phone_number': '473.693.1903',
    'json': {
    'name': 'Karen Waller',
    'address': '9249 Jackie Path\nEast Michael, KY 47907',
},
    'key4189': 'value70798',
    'key50927': 'value92117',
    'key43563': 'value64648',
    'key98749': 'value84221',
    'key81750': 'value73974',
    'key6422': 'value80237',
    'key14728': 'value99129',
},
    {
    'id': 17527488867301,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Brian Hall',
    'address': '5767 Gomez Inlet\nPort Andrew, ME 63703',
    'text': 'Popular high society product between player have. Size hotel enough yourself feel. Reveal happen both behavior until authority.\nMeet drive occur young social.',
    'email': 'robertmcdaniel@example.org',
    'phone_number': '228.931.9370',
    'json': {
    'name': 'Madison Fuentes',
    'address': '497 Harrison Summit\nEast Tamara, NH 70228',
},
    'key27901': 'value28024',
    'key82939': 'value78071',
    'key22272': 'value99142',
    'key56771': 'value86873',
    'key21523': 'value95863',
},
    {
    'id': 17527488867313,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Heather Hill',
    'address': '04506 Keith Keys Suite 246\nLake Juanmouth, DE 78275',
    'text': 'Sing focus foot rise in. Contain money on same network own peace ok.\nCare TV leave moment. Less thing course especially task road.',
    'email': 'nataliehamilton@example.com',
    'phone_number': '7628958924',
    'json': {
    'name': 'Robert Stark',
    'address': '711 Jeffrey View\nNorth Karenborough, NJ 96471',
},
    'key98043': 'value37700',
    'key85222': 'value31731',
},
    {
    'id': 17527488867324,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Daniel Garza',
    'address': '026 Michael Branch\nPatriciastad, LA 58668',
    'text': 'Worker much trip need trip scene even theory. Will say live role whose now. Technology believe task respond hard.\nNature until majority law. Back institution do.\nReady crime picture recently.',
    'email': 'michellebeck@example.org',
    'phone_number': '618.433.4924',
    'json': {
    'name': 'Karen Baker',
    'address': '12999 Payne Viaduct Apt. 113\nRosalesmouth, VI 19392',
},
    'key26281': 'value8116',
    'key91426': 'value80644',
    'key11751': 'value60428',
    'key15111': 'value74601',
    'key29087': 'value1535',
    'key20755': 'value10963',
    'key81255': 'value5639',
    'key76594': 'value26842',
    'key6156': 'value5221',
},
    {
    'id': 17527488867336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Alyssa Stewart',
    'address': '9700 Ruiz Spring Suite 654\nEast Laurenberg, FM 62565',
    'text': 'Recent church study crime. System appear small these together. Least defense country head other much.',
    'email': 'walterjulie@example.org',
    'phone_number': '805.486.4018x0816',
    'json': {
    'name': 'Dylan Scott',
    'address': '4794 Jarvis Road Apt. 451\nLake Jennifer, AR 90917',
},
    'key96961': 'value64826',
    'key71052': 'value44398',
    'key88562': 'value73978',
    'key7415': 'value97216',
    'key47180': 'value57747',
    'key9708': 'value60552',
    'key9374': 'value57358',
    'key41443': 'value73551',
},
    {
    'id': 17527488867348,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Andrea Mendez',
    'address': '520 Leslie Corner Suite 178\nNew Davidview, OR 56444',
    'text': 'Themselves middle for body effect general. Drug similar contain money people.',
    'email': 'davidharris@example.org',
    'phone_number': '+1-309-430-1037x938',
    'json': {
    'name': 'Bruce King',
    'address': 'Unit 9308 Box 4373\nDPO AE 80769',
},
    'key42669': 'value41168',
    'key83573': 'value55402',
    'key15033': 'value93984',
    'key44154': 'value63477',
    'key34974': 'value58557',
},
    {
    'id': 17527488867357,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'William Owens',
    'address': '19526 Irwin Passage\nShawntown, MD 19523',
    'text': 'Fine piece personal woman last consider. Strong audience boy shake movie ask.\nHave save throw spend police choice out. Fine forward television modern drug hot name.',
    'email': 'danielnewton@example.com',
    'phone_number': '698.427.5362',
    'json': {
    'name': 'Richard Johnson',
    'address': '1903 Danielle Inlet Apt. 725\nDickersonmouth, OH 01838',
},
    'key19026': 'value15513',
},
    {
    'id': 17527488867368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jennifer Marshall',
    'address': '093 Jones Station Apt. 485\nHarrisborough, MI 94410',
    'text': 'Create campaign she against feel hospital. Cut late loss Democrat.\nPart move pretty anything money over hear. Issue serve drop figure between. By response choose husband training.',
    'email': 'kayla12@example.com',
    'phone_number': '883.311.5621x94091',
    'json': {
    'name': 'Julia Green',
    'address': 'PSC 5317, Box 1657\nAPO AE 14132',
},
    'key84580': 'value49468',
},
    {
    'id': 17527488867377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Danny Chan',
    'address': '0705 Juan Highway\nEast Charlotte, ID 28809',
    'text': 'Speak toward wonder study. Show him despite interesting cell nothing good. Style term father both and pressure get reason. Seat along east try mouth.',
    'email': 'april56@example.net',
    'phone_number': '412.543.4891x4720',
    'json': {
    'name': 'Marie Perry',
    'address': '388 Ryan Expressway Suite 219\nSouth Michaelport, MS 59594',
},
    'key85568': 'value91119',
    'key4088': 'value22776',
    'key86196': 'value32048',
    'key20074': 'value62386',
},
    {
    'id': 17527488867387,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Kayla Turner MD',
    'address': '8921 Guzman Brooks\nGabrielletown, AS 68186',
    'text': 'Tell child as network public very. Firm series gun campaign.\nSpeech involve model activity each light. Field mouth arm. Option effect true share feeling personal.',
    'email': 'bryanmatthew@example.com',
    'phone_number': '762.512.3711x98081',
    'json': {
    'name': 'Melissa Ferguson',
    'address': '45942 Smith Cape Apt. 517\nPort Stephanie, MT 70429',
},
    'key91798': 'value50707',
    'key84046': 'value10583',
    'key32613': 'value49831',
    'key5791': 'value75376',
},
    {
    'id': 17527488867398,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Mark Taylor',
    'address': '6716 Robert Meadow\nWest Larryfurt, KY 98850',
    'text': 'Writer ball wind sound court son. New foreign fact big approach.',
    'email': 'tatedavid@example.net',
    'phone_number': '382-324-8512',
    'json': {
    'name': 'Adam Chase',
    'address': '691 Melissa Courts Suite 929\nBrownview, AS 37088',
},
    'key93716': 'value20672',
    'key82832': 'value21204',
    'key77475': 'value99808',
    'key17933': 'value91066',
    'key13785': 'value99443',
    'key33685': 'value34547',
},
    {
    'id': 17527488867410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Cindy Bond',
    'address': '2435 Phillips Dale Suite 368\nSouth Courtneybury, OH 23104',
    'text': 'Rule different offer network spend page player. Voice amount you program beat action understand land.\nCustomer character source success decade.\nFirst still it imagine. Color seem friend tonight.',
    'email': 'vincentpatterson@example.com',
    'phone_number': '821.408.4014x145',
    'json': {
    'name': 'Steven Robertson',
    'address': '2498 Stacy Orchard\nNorth Michaelburgh, LA 06349',
},
    'key56088': 'value48801',
    'key64890': 'value673',
    'key44071': 'value70144',
    'key41975': 'value88213',
    'key25477': 'value99465',
},
    {
    'id': 17527488867421,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Robert Bentley',
    'address': 'PSC 3037, Box 1814\nAPO AA 96554',
    'text': 'Trouble such boy challenge federal collection standard.\nResource program team authority. Various away try education.',
    'email': 'laurenharris@example.com',
    'phone_number': '+1-511-331-8187x341',
    'json': {
    'name': 'Greg Parrish',
    'address': '58012 Ward Cove Suite 714\nButlerbury, VA 27342',
},
    'key31091': 'value64441',
    'key32528': 'value60646',
    'key3547': 'value35018',
    'key99534': 'value69139',
    'key43642': 'value96038',
    'key30872': 'value50958',
    'key72510': 'value47387',
    'key50163': 'value34102',
    'key54998': 'value49492',
},
    {
    'id': 17527488867431,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Katelyn Compton',
    'address': '168 Wagner Lock Apt. 529\nLake Joshuashire, RI 64803',
    'text': 'Per democratic manage family. Necessary official available line. Him yeah even campaign economy ten. Media we authority my record can seem.',
    'email': 'nicholasblake@example.net',
    'phone_number': '992.900.9833x18375',
    'json': {
    'name': 'Patricia Pierce',
    'address': '2064 David Burgs\nAllenstad, RI 14372',
},
    'key74482': 'value73847',
    'key57972': 'value98943',
    'key72688': 'value40123',
    'key93485': 'value38824',
    'key66420': 'value14753',
    'key509': 'value91116',
},
    {
    'id': 17527488867443,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Bonnie Dennis',
    'address': '346 Garrett Square Apt. 296\nEast Thomas, NE 80407',
    'text': 'Any maybe yard dinner return per citizen. Recognize do seven budget mission land especially deep. Sea seat shoulder.',
    'email': 'brendadiaz@example.org',
    'phone_number': '(483)282-5575x35583',
    'json': {
    'name': 'Chelsey Mills',
    'address': '0498 Janet Avenue\nPort Marc, HI 78457',
},
    'key34601': 'value77128',
    'key1149': 'value61348',
    'key47812': 'value94109',
    'key97476': 'value97500',
    'key93179': 'value54165',
    'key56370': 'value33838',
    'key26645': 'value90432',
    'key71718': 'value95548',
    'key81058': 'value83340',
},
],
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



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '93964c30-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_20_597246VzGRsInE',
    'filter': 'uid > 0',
    'limit': 100,
    'offset': 0,
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



    def test_request_4(self):
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '93964c30-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_41_20_597246VzGRsInE',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid > 00]_1752748893.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid001752748893Json()
    test.run_tests()
