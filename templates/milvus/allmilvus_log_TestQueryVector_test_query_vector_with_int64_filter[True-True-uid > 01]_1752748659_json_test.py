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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 01]_1752748659_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 01]_1752748659.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid011752748659Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 01]_1752748659.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 01]_1752748659.json"
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
    'RequestId': '083743ce-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_26_889953JOjSAqRc',
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
    'RequestId': '083743ce-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_26_889953JOjSAqRc',
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
    'RequestId': '083743ce-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_26_889953JOjSAqRc',
    'data': [
    {
    'id': 17527486529254,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Robert Ruiz',
    'address': '265 Jill Port\nJosephfort, NY 76367',
    'text': 'Challenge prove paper require. Despite choose consumer final method.\nHot whether where fly price. Hit those piece ahead challenge walk color.\nMaintain child fear produce address. First lay cause.',
    'email': 'youngjoseph@example.com',
    'phone_number': '(475)913-0090x28798',
    'json': {
    'name': 'Mark Wilson',
    'address': '9174 Lindsey Stream\nBrentton, ME 11574',
},
    'key36951': 'value12410',
    'key63457': 'value78498',
    'key36390': 'value33645',
},
    {
    'id': 17527486529269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Jamie Gonzalez',
    'address': '680 Erika Underpass\nPort Thomas, WI 72056',
    'text': 'Hundred only also either responsibility travel hour. Big identify there organization land attorney. Can create receive business.',
    'email': 'vhicks@example.net',
    'phone_number': '851-233-7424',
    'json': {
    'name': 'Elizabeth Gonzales',
    'address': '6133 Steven Village Suite 262\nPort Nicholasmouth, AR 82309',
},
    'key375': 'value46447',
},
    {
    'id': 17527486529280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Nicholas Blair',
    'address': '92403 Amanda Knoll\nHaroldchester, MD 92725',
    'text': 'Available support pressure.\nMrs firm close democratic piece unit long. Entire western floor idea.\nWant through assume soon stage environmental physical leader. Several their forget use.',
    'email': 'sean92@example.org',
    'phone_number': '952-755-6307x603',
    'json': {
    'name': 'Alexis Swanson',
    'address': '47871 Rivera Landing Apt. 985\nCarlsonmouth, MN 85901',
},
    'key5228': 'value44698',
    'key78746': 'value84235',
    'key72696': 'value1315',
    'key6139': 'value64007',
    'key8018': 'value52391',
    'key57142': 'value80752',
    'key82467': 'value42986',
    'key74328': 'value85926',
    'key58708': 'value56581',
    'key4876': 'value96406',
},
    {
    'id': 17527486529292,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Holly Smith',
    'address': '602 Parker Valley Apt. 728\nBurtonburgh, IA 56144',
    'text': 'Probably rate table air around race. Candidate finally difference meeting wait fear water material. Threat rise avoid allow husband more treatment sister.',
    'email': 'heatherali@example.net',
    'phone_number': '+1-313-413-2254',
    'json': {
    'name': 'Natasha Richardson',
    'address': '402 Young Green\nNew Amanda, SC 86200',
},
    'key92886': 'value30564',
    'key92695': 'value27254',
},
    {
    'id': 17527486529304,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Ana Stafford',
    'address': '8762 Stephens Plaza Apt. 407\nNew Julia, PA 43703',
    'text': 'Senior thus table full. American and either note little along. Deal form think me act like special road.',
    'email': 'brianna25@example.com',
    'phone_number': '(262)533-5253',
    'json': {
    'name': 'Lindsey Howell',
    'address': '228 Brooke Trafficway Apt. 893\nSouth Toddville, PA 14346',
},
    'key96644': 'value18311',
    'key28762': 'value51132',
    'key5083': 'value25095',
    'key86611': 'value32771',
    'key66804': 'value45403',
    'key96435': 'value44648',
    'key91153': 'value97769',
},
    {
    'id': 17527486529315,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Sandra Patel',
    'address': 'PSC 5092, Box 2998\nAPO AE 28044',
    'text': 'Important while service wife deep third. Born like cell share.\nEnjoy wall another structure green material class. House western window west career receive. Wish whose evening forget memory.',
    'email': 'johnallen@example.com',
    'phone_number': '001-439-487-8796x0983',
    'json': {
    'name': 'Molly Griffith',
    'address': '088 Kim Shoal Suite 469\nNorth Carlahaven, VA 36388',
},
    'key86423': 'value26774',
    'key30736': 'value35249',
    'key16842': 'value59905',
    'key36966': 'value49352',
    'key13666': 'value29829',
    'key50421': 'value48990',
},
    {
    'id': 17527486529325,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Danielle Lewis',
    'address': 'PSC 1337, Box 6026\nAPO AA 72087',
    'text': 'Baby push form situation walk. Process form tell without wear. Specific executive size discussion poor. See every size fight indeed coach.',
    'email': 'ethan42@example.org',
    'phone_number': '+1-770-923-5710',
    'json': {
    'name': 'Donna Cardenas',
    'address': '08151 Susan Run Suite 564\nWest Karenview, PR 02563',
},
    'key11359': 'value58805',
    'key83846': 'value30731',
    'key9506': 'value76036',
    'key8492': 'value60443',
},
    {
    'id': 17527486529333,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Wendy Johnson',
    'address': '27429 Jenkins Turnpike Apt. 370\nMartinside, MA 81287',
    'text': 'Heart stay see turn Mr name. Ahead vote apply college picture else nothing. Option official condition home place city term. Trouble past weight wait practice audience drive.',
    'email': 'gthompson@example.net',
    'phone_number': '(737)657-2561',
    'json': {
    'name': 'Jessica Wallace',
    'address': '39086 Hernandez Circle\nPort Melissa, MD 07594',
},
    'key88224': 'value67400',
    'key34681': 'value40639',
    'key58653': 'value49894',
    'key17923': 'value5084',
},
    {
    'id': 17527486529344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Natalie Murray',
    'address': 'PSC 0606, Box 7134\nAPO AA 54792',
    'text': 'Decide rise general design. By over pay relationship style never. Management task figure reach.\nEducation it until pay point low. Design perform new defense despite process.\nFactor theory concern.',
    'email': 'erik36@example.com',
    'phone_number': '(839)613-2360x2883',
    'json': {
    'name': 'Erik Knight',
    'address': '732 Martin Mills Suite 364\nRasmussenfort, RI 02386',
},
    'key20903': 'value22811',
    'key50867': 'value34904',
    'key92217': 'value59012',
    'key60282': 'value62001',
},
    {
    'id': 17527486529354,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Benjamin Johnson',
    'address': '6045 White Harbor Apt. 161\nSouth Joseph, MS 82663',
    'text': 'Camera hit someone bill indeed. There national space space. Contain those never blue bit far reality off.\nBook study whole garden finally development. Short move likely allow.',
    'email': 'shannonortiz@example.net',
    'phone_number': '274.945.3194x053',
    'json': {
    'name': 'Jennifer Drake',
    'address': '52865 Wells Mall\nNew Rhondaburgh, FL 19002',
},
    'key52489': 'value12089',
},
    {
    'id': 17527486529365,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Scott Sosa',
    'address': '941 Christopher Wall Apt. 338\nLake Colleen, IA 12290',
    'text': 'Plan personal push. Where player entire. Whole help event standard trouble choice finish.',
    'email': 'luis31@example.net',
    'phone_number': '+1-281-279-8752x5284',
    'json': {
    'name': 'Mark Carlson',
    'address': '36928 Morris Route Apt. 054\nBrianaborough, TN 22286',
},
    'key8843': 'value33431',
    'key36735': 'value43565',
    'key34242': 'value19172',
    'key99518': 'value17707',
    'key74810': 'value53804',
    'key83783': 'value46250',
    'key93998': 'value18226',
    'key35256': 'value56391',
    'key1461': 'value82512',
},
    {
    'id': 17527486529375,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Brittney Nguyen',
    'address': 'PSC 0950, Box 9028\nAPO AE 36788',
    'text': 'Miss he head door drug set listen own. Method act interest professional day.',
    'email': 'kevin63@example.org',
    'phone_number': '297.683.1110x8338',
    'json': {
    'name': 'Kelly Martinez',
    'address': '2954 Haynes Mission\nKyleburgh, CO 96369',
},
    'key9408': 'value9419',
    'key35886': 'value19794',
    'key47310': 'value68570',
},
    {
    'id': 17527486529384,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'William Rogers',
    'address': '0131 Williams Crescent Apt. 584\nNew Heatherville, TN 11809',
    'text': 'No that sister break them Republican nearly. Senior white account artist family. First investment stage recently see field hair.\nSave pass worker wind difficult detail. Owner score admit.',
    'email': 'qolson@example.net',
    'phone_number': '+1-783-651-6404x165',
    'json': {
    'name': 'Kimberly Wright',
    'address': '924 Bush Inlet Apt. 517\nClarkview, NE 64130',
},
    'key11105': 'value2449',
    'key61604': 'value56514',
    'key24629': 'value45058',
    'key58534': 'value28867',
    'key14338': 'value29172',
    'key41739': 'value18573',
    'key53461': 'value94154',
    'key91980': 'value58354',
    'key97581': 'value93188',
    'key11387': 'value66083',
},
    {
    'id': 17527486529395,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Mark Whitney',
    'address': '387 Oneill Islands\nPooleside, AR 62675',
    'text': 'At seven economy TV same until. Training south thus certain include.\nSkill sea six discussion.',
    'email': 'cookdonald@example.net',
    'phone_number': '001-931-349-5999x33419',
    'json': {
    'name': 'Tamara Johnson DDS',
    'address': '48498 Elliott Rest Suite 291\nKylieport, MD 31733',
},
    'key45014': 'value66842',
    'key11286': 'value7028',
},
    {
    'id': 17527486529407,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Alejandro Bradley',
    'address': '3540 David Walk\nConnieborough, NE 89781',
    'text': 'Through agency party century pull certain. Stuff way that single beyond old.',
    'email': 'theodore80@example.com',
    'phone_number': '(293)564-2379x3167',
    'json': {
    'name': 'Sarah Prince',
    'address': '89323 Mitchell Cliff\nNorth Tracey, FM 75513',
},
    'key37375': 'value72795',
    'key81238': 'value39126',
    'key33530': 'value60165',
    'key65127': 'value50340',
    'key22936': 'value33536',
    'key9417': 'value34918',
    'key69426': 'value9880',
    'key27495': 'value69005',
    'key53758': 'value56056',
    'key86782': 'value38423',
},
    {
    'id': 17527486529417,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Douglas Pierce',
    'address': '311 Brenda Summit\nEast Thomasfurt, MN 19180',
    'text': 'Environment anyone western newspaper conference hundred. Industry sport teach join really. Any look fire will.\nAttack measure nor true who color. Near some game rule every always.',
    'email': 'ncortez@example.com',
    'phone_number': '3887487850',
    'json': {
    'name': 'Jesse Horn',
    'address': '8046 Mosley Mountain Apt. 300\nWest Jamesmouth, FM 87572',
},
    'key51720': 'value77940',
    'key70706': 'value77540',
},
    {
    'id': 17527486529427,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Susan Lamb',
    'address': '4546 Keller Keys\nNorth Michaelland, VI 88331',
    'text': 'Ahead author art here story. Really star address cup. Party item almost degree firm.\nSit red toward animal yeah could now. Husband close get commercial point detail thousand.',
    'email': 'heidi72@example.com',
    'phone_number': '217-613-0162',
    'json': {
    'name': 'Steven Benson',
    'address': '38969 Singh Knolls Apt. 356\nFosterton, IL 78854',
},
    'key2982': 'value48956',
},
    {
    'id': 17527486529439,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Christine Cooper',
    'address': '92808 Obrien Isle\nChavezview, AR 28610',
    'text': 'Whose stop understand source. Benefit study base explain we under. Ago turn decision great. Kitchen prevent politics something toward whatever maybe.',
    'email': 'schmidtthomas@example.org',
    'phone_number': '544.447.4080',
    'json': {
    'name': 'Travis Cooper',
    'address': 'PSC 8271, Box 0328\nAPO AP 30243',
},
    'key28730': 'value23182',
    'key37065': 'value34464',
    'key59207': 'value907',
    'key78242': 'value30748',
    'key69347': 'value93967',
    'key67239': 'value95956',
    'key5614': 'value55013',
},
    {
    'id': 17527486529449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Renee Ramos',
    'address': '23642 Sheila Pine\nSouth Kimberly, IL 16770',
    'text': 'Close enough throw student pattern. Phone difficult move everyone take rise.\nTable on send himself specific since. Positive send around produce.',
    'email': 'blairjohn@example.com',
    'phone_number': '598-582-6536x8418',
    'json': {
    'name': 'Jason Adkins',
    'address': '846 Nancy Loop\nNew Jeffborough, OK 38676',
},
    'key96745': 'value68119',
    'key53010': 'value88861',
    'key55278': 'value73931',
    'key35678': 'value32830',
    'key96023': 'value85008',
},
    {
    'id': 17527486529460,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jared Norton',
    'address': '104 Lynch Forge Suite 296\nNorth Jeffrey, NV 59274',
    'text': 'To decide wife the message. Treat senior blue significant pass.\nThrow church team power partner also own. What six hair carry upon analysis middle staff.\nPainting car series. Have far image.',
    'email': 'jesse86@example.com',
    'phone_number': '711-925-0313',
    'json': {
    'name': 'Melissa Hill',
    'address': '43039 Jones Club Apt. 694\nWest Williamfort, CO 71644',
},
    'key79183': 'value43329',
    'key74719': 'value59913',
    'key73313': 'value71171',
    'key3155': 'value78843',
    'key12178': 'value32851',
    'key66290': 'value32855',
},
    {
    'id': 17527486529471,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Michelle Luna',
    'address': '0095 Brown Oval\nNorth Michael, CA 43230',
    'text': 'Himself see effect dark environmental wish act. Case each church garden.\nBe agree could game. Until number certain assume sort contain customer.',
    'email': 'martinmichele@example.net',
    'phone_number': '571-300-4463x771',
    'json': {
    'name': 'Kelly Dixon',
    'address': '0363 Ortiz Extensions Suite 228\nSouth Erinfurt, MO 61399',
},
    'key95467': 'value98071',
    'key46115': 'value24874',
    'key41666': 'value94175',
    'key69356': 'value51704',
    'key52868': 'value77226',
    'key71868': 'value27425',
    'key97827': 'value6435',
},
    {
    'id': 17527486529483,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Alicia Hill',
    'address': '0211 Preston Garden Apt. 460\nKevinport, IL 03403',
    'text': 'High buy who main tonight nor. War huge while teach. Quickly focus part hour card require drug open. Mission start office blood age.',
    'email': 'riggspaul@example.com',
    'phone_number': '839-351-5037',
    'json': {
    'name': 'Maria Adams',
    'address': '60293 Smith Gateway Apt. 378\nNorth Jamesburgh, AK 82954',
},
    'key96411': 'value83750',
    'key9566': 'value22626',
},
    {
    'id': 17527486529495,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Luis Nguyen',
    'address': '5114 Deanna Walks Suite 596\nLake Anitatown, CA 62387',
    'text': 'Mention affect nor western term. Word every million though participant.\nHit success thus suggest although. Prove their heart them raise camera with.\nReflect paper stock then. Foreign sign answer.',
    'email': 'bbrown@example.org',
    'phone_number': '+1-998-223-4426x455',
    'json': {
    'name': 'David Potter MD',
    'address': '6642 Tristan Throughway\nJessemouth, ID 64663',
},
    'key36875': 'value48500',
    'key85809': 'value45890',
    'key95512': 'value85959',
    'key70966': 'value30841',
    'key65621': 'value98138',
    'key78963': 'value85780',
    'key32349': 'value2966',
},
    {
    'id': 17527486529506,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Tracey Diaz DVM',
    'address': '517 Ralph Orchard Suite 073\nNew Nicolemouth, MI 46323',
    'text': 'Partner area else message. Organization nice partner space.\nAffect raise dark personal interview. Maybe citizen these professional reach stage safe. Practice company defense there.',
    'email': 'michellekelly@example.com',
    'phone_number': '868-414-7503',
    'json': {
    'name': 'Alyssa Garcia',
    'address': '25743 Bailey Ports Suite 177\nLake Janice, GA 98882',
},
    'key42923': 'value652',
    'key53227': 'value75243',
    'key71231': 'value2383',
    'key85291': 'value36680',
    'key66641': 'value12099',
},
    {
    'id': 17527486529518,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Crystal Jackson',
    'address': 'PSC 9614, Box 7128\nAPO AA 57417',
    'text': 'Speech instead specific return including. Rise morning expect war watch. Try base too billion next break must.',
    'email': 'mary41@example.com',
    'phone_number': '350-637-1132',
    'json': {
    'name': 'Jenna Cruz',
    'address': '363 Smith Ridge Apt. 962\nKevinside, KY 34729',
},
    'key79330': 'value97237',
    'key42950': 'value98168',
    'key83856': 'value54823',
    'key51447': 'value60098',
    'key91105': 'value42611',
    'key84038': 'value11197',
    'key87850': 'value21048',
    'key34778': 'value12936',
},
    {
    'id': 17527486529526,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Michael Garcia',
    'address': '3429 Odonnell Crescent Apt. 979\nSouth Keith, DC 32546',
    'text': 'Fish speech knowledge against TV cover knowledge. Floor entire audience seek. North material institution bit teach scene best.\nSmile let goal. Forward result Mrs health.',
    'email': 'smendez@example.org',
    'phone_number': '922.498.3079',
    'json': {
    'name': 'Dawn Berger',
    'address': 'USNV Hughes\nFPO AE 32640',
},
    'key41758': 'value50521',
    'key99771': 'value36752',
    'key57629': 'value81127',
},
    {
    'id': 17527486529536,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Thomas Clark',
    'address': '62722 Novak Alley Suite 212\nPort Bailey, AS 29524',
    'text': 'Million surface huge natural I will stay change. Tell vote save me special recent tax. Per century world often may establish.\nStyle ready yeah.\nParticularly miss eat must compare western land play.',
    'email': 'colton71@example.com',
    'phone_number': '+1-676-284-2213x61549',
    'json': {
    'name': 'Taylor Edwards',
    'address': '24993 Reed Trafficway\nAmandaburgh, AZ 30501',
},
    'key69164': 'value38018',
    'key65943': 'value38883',
    'key25559': 'value16828',
    'key99609': 'value54732',
    'key57617': 'value40659',
    'key13635': 'value95422',
    'key70359': 'value38503',
    'key82595': 'value55671',
},
    {
    'id': 17527486529547,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Robin Jones',
    'address': '744 Davis Row\nNew Alexander, MH 58257',
    'text': 'Nearly family guy language bad. Son miss really do lot inside. Commercial challenge director continue today agency information.',
    'email': 'angelachang@example.com',
    'phone_number': '+1-409-357-3879',
    'json': {
    'name': 'Veronica Curry',
    'address': '95753 Smith Shore\nEast Amanda, VI 87488',
},
    'key24806': 'value78245',
},
    {
    'id': 17527486529559,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jeffrey Reid',
    'address': '42174 Elizabeth Pine\nWest Paulland, IN 27820',
    'text': 'Same employee everyone medical. Know stuff agreement run ball make address.\nIssue education even. Author cause performance government record within example. Gun soldier song performance.',
    'email': 'caitlin69@example.org',
    'phone_number': '+1-978-397-6345',
    'json': {
    'name': 'Joyce Morris',
    'address': '77988 Chelsey Spring\nReyesburgh, VA 71925',
},
    'key2466': 'value12668',
    'key55520': 'value35952',
    'key46204': 'value47996',
    'key58932': 'value52781',
    'key58930': 'value24542',
    'key53427': 'value8453',
    'key59030': 'value51499',
    'key96123': 'value95853',
    'key26278': 'value72011',
    'key49790': 'value61665',
},
    {
    'id': 17527486529570,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Joseph Young',
    'address': '64452 Randy Points\nSouth Jillchester, VT 17448',
    'text': 'Find maintain trade her yeah actually. Region goal mission quality account hair serious subject. Surface prevent brother task.\nTeacher teacher give picture. Kind activity value area short.',
    'email': 'wgamble@example.com',
    'phone_number': '+1-206-983-3867x08993',
    'json': {
    'name': 'Brandi English',
    'address': '93557 Eaton Trafficway\nHendersonberg, NE 23538',
},
    'key72450': 'value99593',
    'key13765': 'value26252',
    'key9751': 'value93917',
    'key43371': 'value38075',
    'key36532': 'value33477',
    'key67722': 'value62655',
    'key54137': 'value15003',
    'key23952': 'value28073',
    'key90002': 'value38907',
    'key65919': 'value3929',
},
    {
    'id': 17527486529581,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Amanda Riley',
    'address': '4940 Jessica Row\nFlowershaven, MH 10201',
    'text': 'Rule work drive once. Small window give indicate health cold three. Hospital figure catch make official next able.\nPm anything road carry. Account anything full message actually prevent night child.',
    'email': 'gregory35@example.net',
    'phone_number': '734-644-6800',
    'json': {
    'name': 'Melinda Miller',
    'address': '4955 Perez Key\nJillborough, NJ 31489',
},
    'key28772': 'value94048',
    'key11779': 'value72438',
    'key30772': 'value67612',
    'key88105': 'value15692',
    'key80946': 'value47539',
    'key15422': 'value10681',
    'key71890': 'value53743',
    'key81185': 'value76327',
},
    {
    'id': 17527486529592,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Daniel Wallace',
    'address': '263 Angela Glen\nSouth Robertville, MS 52443',
    'text': 'Put south sort security security should. Body money issue member knowledge enjoy statement world. Able ahead later prevent.',
    'email': 'hthomas@example.com',
    'phone_number': '+1-215-651-8260x73651',
    'json': {
    'name': 'Andrew Davila',
    'address': '654 Wilson Springs Suite 290\nEast Eric, CO 95634',
},
    'key30679': 'value40461',
    'key45026': 'value38042',
    'key76270': 'value17943',
    'key21799': 'value23977',
    'key49203': 'value89075',
    'key72344': 'value81058',
    'key30970': 'value15359',
    'key37093': 'value31137',
},
    {
    'id': 17527486529603,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Daniel Ellis',
    'address': '1978 Ryan Extension Apt. 423\nStephaniemouth, TN 98524',
    'text': 'Officer focus product herself difference. Lawyer believe hair cup fear.\nDown animal front window answer outside.',
    'email': 'jon88@example.com',
    'phone_number': '+1-747-709-5173',
    'json': {
    'name': 'Phillip Melton',
    'address': '9686 Angela Canyon\nSouth Jessica, DC 90964',
},
    'key98391': 'value36622',
    'key29557': 'value11005',
    'key89252': 'value18393',
    'key7381': 'value63976',
    'key40936': 'value27763',
    'key76628': 'value10759',
    'key23613': 'value93243',
    'key69614': 'value24012',
},
    {
    'id': 17527486529612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Angela Williams',
    'address': 'PSC 4886, Box 3521\nAPO AE 33073',
    'text': 'Environmental security consumer yet into read room. Dream beautiful network everyone born approach what. Front bank charge why. Single act civil always report.',
    'email': 'xmayer@example.com',
    'phone_number': '363-594-8189',
    'json': {
    'name': 'Amy King',
    'address': 'PSC 4435, Box 9882\nAPO AA 24272',
},
    'key165': 'value74855',
    'key65464': 'value83255',
    'key76959': 'value25918',
    'key18232': 'value73972',
    'key38736': 'value66291',
},
    {
    'id': 17527486529619,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Melissa Garcia',
    'address': '232 Justin Street Suite 492\nNorth Tyler, MO 42705',
    'text': 'End once production test say contain so. Bed Mrs reality carry response here. Turn pull store will.\nThemselves career every prevent. Outside task over program take road buy.',
    'email': 'wendy70@example.net',
    'phone_number': '(869)414-5114x25864',
    'json': {
    'name': 'Sarah Anderson',
    'address': '3816 Scott Ford\nGillespietown, ID 05036',
},
    'key77356': 'value67832',
    'key44108': 'value56984',
},
    {
    'id': 17527486529630,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Kyle Villarreal',
    'address': '0970 Lisa Causeway\nPort Martinfurt, NJ 38374',
    'text': 'In interview appear process brother knowledge. Operation if discuss leader southern enough once truth.',
    'email': 'douglas61@example.com',
    'phone_number': '5398660556',
    'json': {
    'name': 'Jennifer Mccormick',
    'address': '04919 Ortiz Cape Suite 156\nElizabethhaven, PW 86910',
},
    'key7623': 'value65184',
},
    {
    'id': 17527486529641,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'James Jones',
    'address': '340 Robinson Pine\nAndrewshire, DE 24899',
    'text': 'Show task PM prepare nature.\nInterest amount way. Despite oil may help accept late keep.\nSuccess special compare role. Determine world here chance conference stuff really.',
    'email': 'melaniepatel@example.net',
    'phone_number': '515.526.2443x613',
    'json': {
    'name': 'Jeffrey Weaver',
    'address': '901 Phillips Radial Suite 563\nNorth Michaelton, NJ 69253',
},
    'key94087': 'value92986',
},
    {
    'id': 17527486529653,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Michelle Castaneda',
    'address': '5401 George Spur\nPort Miguelburgh, WA 11379',
    'text': 'Laugh success right difficult. Evidence visit image entire article exist indeed. Man state set rich TV something national.\nExist set forward dinner rise notice brother second.',
    'email': 'matthewramirez@example.net',
    'phone_number': '(225)232-2949',
    'json': {
    'name': 'Dr. Jerry Jones DVM',
    'address': '30534 Nicholas Drive Apt. 707\nJamesshire, NH 45130',
},
    'key38052': 'value29936',
    'key48202': 'value57410',
},
    {
    'id': 17527486529664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Anthony Ballard',
    'address': '640 Haynes Shoal\nLisaview, WI 61538',
    'text': 'Court piece though first easy. Notice expect financial money feeling into charge.\nMovement change top itself exist old left any. Important more student show base woman image. One explain late.',
    'email': 'lebrittany@example.net',
    'phone_number': '(482)584-6801x07226',
    'json': {
    'name': 'Daniel Malone',
    'address': '85386 Elizabeth Cape Suite 996\nMurphyshire, DC 76479',
},
    'key53421': 'value36247',
},
    {
    'id': 17527486529676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jose Franklin',
    'address': '79977 Michael Ferry Apt. 679\nWest Kyletown, CA 26566',
    'text': 'Article scientist themselves near this. Peace rise audience financial. Television art describe street long worker.\nMatter debate campaign call. Walk important pass section consumer.',
    'email': 'yburke@example.net',
    'phone_number': '001-688-726-2569x11874',
    'json': {
    'name': 'Leslie Sanders',
    'address': '017 Reed Rue Apt. 046\nNew Brendamouth, MI 06596',
},
    'key79896': 'value80222',
    'key24097': 'value84123',
    'key72278': 'value85572',
    'key81663': 'value42936',
    'key33324': 'value8016',
    'key74972': 'value16329',
    'key70142': 'value82580',
    'key10362': 'value14737',
    'key33348': 'value75064',
    'key75108': 'value91305',
},
    {
    'id': 17527486529687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Christina Rosario',
    'address': '1224 Mcintyre Field Apt. 120\nStephanieton, LA 90941',
    'text': 'Effect grow and college personal sound. Ever ready information cover.\nKnowledge war actually role example truth help while. Kitchen live unit information us total. News scene green future.',
    'email': 'xsteele@example.org',
    'phone_number': '995.821.5250',
    'json': {
    'name': 'Catherine Duncan',
    'address': '39478 Davis Estate Suite 239\nSouth Kennethburgh, NM 27496',
},
    'key65072': 'value99486',
    'key68518': 'value83635',
    'key68260': 'value86510',
    'key97366': 'value24512',
    'key95995': 'value11520',
    'key91641': 'value77066',
    'key73737': 'value10212',
},
    {
    'id': 17527486529698,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Megan Jackson',
    'address': '59096 Erica Cliff\nNew Francisco, WI 75796',
    'text': 'Many myself shake ask animal. Forget rich no.\nThen writer form safe including leg scientist. Artist win guess. Threat there system.',
    'email': 'ecastaneda@example.org',
    'phone_number': '+1-368-372-6269',
    'json': {
    'name': 'Megan Davis',
    'address': '0478 Jeffrey Gateway\nNorth Josephland, PW 35617',
},
    'key44747': 'value87406',
    'key8353': 'value44215',
    'key68520': 'value85901',
    'key27206': 'value66621',
    'key21746': 'value39069',
    'key60645': 'value72356',
    'key44113': 'value42645',
    'key94761': 'value71815',
    'key34712': 'value29016',
},
    {
    'id': 17527486529708,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Jeremy Crawford MD',
    'address': '4089 Sanchez Rapids Suite 828\nWilsonport, NE 79665',
    'text': 'Fast computer drug the health. Coach draw big.\nMouth build half its son ok. Onto onto guess factor.',
    'email': 'valentinetanya@example.org',
    'phone_number': '(477)523-7428x0573',
    'json': {
    'name': 'Robin Byrd',
    'address': '2890 Teresa Mall\nChristopherfurt, NV 72490',
},
    'key27869': 'value93625',
    'key26854': 'value90743',
    'key20975': 'value92930',
},
    {
    'id': 17527486529720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Heather Huffman',
    'address': '99556 Michael Isle Apt. 353\nRogersmouth, UT 17889',
    'text': 'Available president Mr environmental. Line hear particularly thought industry quality.\nProgram far story. Evidence account trade music. Down citizen just brother rate.',
    'email': 'paulahull@example.com',
    'phone_number': '(523)757-1412x129',
    'json': {
    'name': 'Tiffany Horton DVM',
    'address': '161 Johnson Shoals Apt. 504\nWest James, AS 52520',
},
    'key2198': 'value78298',
    'key49869': 'value25021',
    'key95793': 'value88903',
},
    {
    'id': 17527486529732,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Michael Nielsen',
    'address': '658 Leslie Island\nCasestad, SC 78603',
    'text': 'Should certainly mention a economy pass music so. Talk marriage church per. Ability finish name PM necessary find center. Language fly baby resource.',
    'email': 'mariamorrow@example.net',
    'phone_number': '001-416-419-7246x9091',
    'json': {
    'name': 'Kenneth Ruiz',
    'address': '770 Andrews Turnpike\nEast Michael, ID 07497',
},
    'key91577': 'value67869',
    'key49051': 'value93341',
    'key62060': 'value86465',
    'key52451': 'value88132',
    'key33345': 'value99689',
    'key26389': 'value63725',
    'key82050': 'value85153',
},
    {
    'id': 17527486529743,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Ashley Farrell',
    'address': '40904 Carolyn Common Apt. 565\nJohnberg, LA 36367',
    'text': 'Mean great explain three manage. Go performance example before mind deep director.\nLive include statement executive north agree.',
    'email': 'tara03@example.com',
    'phone_number': '001-560-275-4326x10108',
    'json': {
    'name': 'Frank Ray',
    'address': '217 Roberts Mountains Apt. 165\nRichardsonborough, PA 35384',
},
    'key64423': 'value46314',
    'key67479': 'value59986',
    'key48839': 'value62338',
    'key20235': 'value62738',
    'key64146': 'value73218',
    'key31210': 'value39200',
    'key15538': 'value29384',
    'key11222': 'value97960',
    'key30753': 'value39096',
    'key82031': 'value97605',
},
    {
    'id': 17527486529754,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Michele Holmes',
    'address': '9275 Stephanie Plaza\nMosleystad, WV 64839',
    'text': 'Three want same. Leave billion nature price over.\nMaterial establish soon certainly effect tree. Figure dark become interview wind. Yard old individual large quickly reflect effect.',
    'email': 'justinhicks@example.net',
    'phone_number': '+1-903-689-1415x9072',
    'json': {
    'name': 'Belinda Jackson',
    'address': '3477 Meyer Lakes\nNorth Mary, LA 92909',
},
    'key15923': 'value8789',
    'key46163': 'value84620',
    'key56997': 'value24371',
    'key14078': 'value91728',
    'key15970': 'value52319',
    'key23121': 'value49750',
    'key25210': 'value10052',
    'key54266': 'value32836',
    'key68784': 'value24607',
    'key44460': 'value31289',
},
    {
    'id': 17527486529766,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Danny Gomez',
    'address': '04390 Kim Lane Apt. 345\nPort Joseville, NV 59735',
    'text': 'Receive those debate ten teacher. Almost western author task wrong art wide. Throughout example could skin exist short.',
    'email': 'hilldestiny@example.com',
    'phone_number': '+1-528-463-9290x0242',
    'json': {
    'name': 'Wendy Savage',
    'address': '5980 Michael Forest Suite 591\nEmilyville, IN 30619',
},
    'key57196': 'value72481',
    'key55272': 'value23842',
    'key77572': 'value74872',
    'key6750': 'value60790',
    'key72254': 'value21215',
    'key84186': 'value55404',
    'key84412': 'value72648',
    'key99929': 'value84299',
},
    {
    'id': 17527486529777,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Paul Torres',
    'address': '10850 Deleon Heights\nJenniferburgh, VA 02582',
    'text': 'In final staff fine human think. Network inside more unit. Animal where art myself single college. Result few red suffer indicate reach west.',
    'email': 'wardsarah@example.net',
    'phone_number': '855.908.6258x646',
    'json': {
    'name': 'Sydney Harris',
    'address': '8683 Thompson Crossroad\nReyesbury, MT 68729',
},
    'key33983': 'value60257',
    'key25052': 'value90480',
    'key42589': 'value92081',
    'key15336': 'value9299',
    'key15341': 'value78237',
    'key89922': 'value14121',
},
    {
    'id': 17527486529789,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Kathleen Davis',
    'address': '696 Hernandez Lake\nTorresfurt, MO 07676',
    'text': 'Focus better red team site sure customer son. Local audience personal challenge election then green. Scientist report rate report build.',
    'email': 'allenmichael@example.com',
    'phone_number': '354-334-1187x6285',
    'json': {
    'name': 'Jacob Figueroa',
    'address': '74156 John Mountain\nChenfort, PR 37565',
},
    'key68254': 'value57620',
    'key46599': 'value14612',
    'key57733': 'value50191',
    'key71276': 'value78996',
    'key8783': 'value33887',
    'key48271': 'value97581',
    'key54720': 'value40707',
},
    {
    'id': 17527486529801,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Michael Houston',
    'address': '74903 Hamilton Terrace\nTiffanytown, CA 75879',
    'text': 'Ok piece security. Ball simple must exist everybody plant.\nWithout collection until with marriage.\nFood cause sell make born left leg. Fly push return decade us.',
    'email': 'kylehuber@example.com',
    'phone_number': '(419)789-5370x2413',
    'json': {
    'name': 'Robert Brock',
    'address': '014 Erica Mission\nSweeneychester, GU 44817',
},
    'key34352': 'value42426',
    'key58478': 'value42484',
    'key1897': 'value64740',
    'key85913': 'value10989',
    'key2632': 'value834',
    'key31959': 'value74065',
    'key75771': 'value99634',
    'key63105': 'value68683',
    'key32557': 'value38749',
    'key96609': 'value50225',
},
    {
    'id': 17527486529813,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Eric Wilkins',
    'address': '4752 Miller Point Suite 838\nEast Dennis, KY 93393',
    'text': 'Time guy receive five activity hundred.\nTrial that here class. Page reveal which table sign since would administration.',
    'email': 'jack21@example.net',
    'phone_number': '(749)659-5124x71909',
    'json': {
    'name': 'Natalie Hamilton',
    'address': '18684 Jennifer Burgs Suite 305\nGriffinfurt, FL 58896',
},
    'key86729': 'value54568',
    'key82307': 'value23009',
    'key50474': 'value82459',
    'key82764': 'value82496',
    'key33492': 'value36014',
    'key98818': 'value17660',
    'key52114': 'value53557',
    'key95357': 'value23987',
    'key14966': 'value22379',
    'key96829': 'value95268',
},
    {
    'id': 17527486529824,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Derek Robbins',
    'address': '8937 Kristen Garden Apt. 539\nTimothybury, MP 90314',
    'text': 'Series almost church stage force range determine. Task third walk good create.\nIncrease drive on throw speech. Own study city total into mother long.',
    'email': 'johnsonclaire@example.net',
    'phone_number': '610.900.8156x129',
    'json': {
    'name': 'Nancy Jones',
    'address': '1743 Young Locks Apt. 389\nPort Daniel, MT 85574',
},
    'key24796': 'value4263',
},
    {
    'id': 17527486529835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Cody Walker',
    'address': '074 Oconnell Curve Apt. 529\nWest Coreyfort, PR 33228',
    'text': 'Middle drive American dinner cut imagine customer. Fight it none treatment offer great.\nDog game clear view. Level for real nation.',
    'email': 'dmartin@example.net',
    'phone_number': '+1-556-310-6544x81116',
    'json': {
    'name': 'Kayla Grimes',
    'address': '7570 Kimberly Rest Suite 702\nLake Brandon, MS 64333',
},
    'key99181': 'value81439',
    'key59604': 'value49334',
    'key71203': 'value91715',
    'key44135': 'value18709',
    'key7243': 'value51667',
    'key30343': 'value61480',
},
    {
    'id': 17527486529846,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Russell Stone',
    'address': '0279 Reynolds Plaza\nLake Allisonmouth, VA 78998',
    'text': 'Left citizen PM mind care use. Red guess begin. Over fund behavior thus pay. Particular herself customer break join reach.\nMessage join financial number avoid which with. Factor total onto become.',
    'email': 'kingtracy@example.org',
    'phone_number': '+1-665-437-1005',
    'json': {
    'name': 'Austin Hicks',
    'address': '822 Christina Drive\nSandovalland, IN 37726',
},
    'key21562': 'value66200',
    'key19583': 'value99596',
    'key96512': 'value57082',
    'key19188': 'value49409',
    'key82335': 'value7359',
    'key60597': 'value21305',
},
    {
    'id': 17527486529858,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Shane Escobar',
    'address': '06430 Kimberly Radial\nKanehaven, IN 83783',
    'text': 'Get up film with. Deal husband understand who girl. Fish order behavior usually.\nSituation floor peace just reach explain. Happy matter thus movie large energy laugh.',
    'email': 'johnsonmatthew@example.org',
    'phone_number': '001-571-721-5179',
    'json': {
    'name': 'Mark Johnson',
    'address': '8603 Briana Greens\nEast Anthony, WA 18749',
},
    'key1002': 'value72947',
    'key84812': 'value63598',
    'key47517': 'value76493',
    'key3917': 'value13582',
    'key76505': 'value81275',
    'key75632': 'value38047',
    'key92134': 'value73437',
    'key24491': 'value50911',
    'key47742': 'value64810',
},
    {
    'id': 17527486529869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Sarah Conrad',
    'address': '800 Alyssa Parkway Apt. 448\nWendychester, MO 68017',
    'text': 'Strong behavior police level that stage. Baby with source entire adult long free.\nWhole sell behavior if see conference. Set law want.',
    'email': 'hwood@example.com',
    'phone_number': '001-694-708-8934',
    'json': {
    'name': 'John Benson',
    'address': '436 Perkins Village\nWest Deborahview, WV 70566',
},
    'key12416': 'value4429',
    'key12747': 'value27079',
    'key78871': 'value16913',
    'key67210': 'value16254',
},
    {
    'id': 17527486529880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Emily Johnson',
    'address': '8918 Scott Station\nElizabethbury, MP 76031',
    'text': 'Eight really task whole whatever reveal measure. Her small describe. Crime scene help others west listen. Model organization cultural.\nDown professor entire of against high sea.',
    'email': 'edwardsbryan@example.org',
    'phone_number': '5009193365',
    'json': {
    'name': 'Holly Harmon',
    'address': '72665 Jennifer Unions\nJenniferborough, WI 29354',
},
    'key59592': 'value21105',
    'key24682': 'value69107',
    'key30736': 'value3145',
    'key8569': 'value76377',
},
    {
    'id': 17527486529891,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Katrina Christian',
    'address': 'Unit 0947 Box 9751\nDPO AP 71659',
    'text': 'Join without win ago. Great church practice report industry.\nBenefit hope wrong people thousand. Know course enough quite wish give number. Thought a yard. Water quickly say.',
    'email': 'dunnrobert@example.com',
    'phone_number': '2628813699',
    'json': {
    'name': 'Marie Palmer DVM',
    'address': '34022 Michael Circles Suite 505\nLake Paulashire, MT 61603',
},
    'key54680': 'value93598',
    'key66498': 'value31203',
    'key76830': 'value25330',
    'key71139': 'value68108',
    'key7622': 'value89443',
    'key19418': 'value1006',
    'key31108': 'value23027',
},
    {
    'id': 17527486529901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Jonathan Johnson',
    'address': '886 April Corner Apt. 200\nPattersonhaven, PR 81521',
    'text': 'Attack act necessary reveal.\nOpen war similar myself. Great challenge successful suddenly early wife. Carry probably top term.',
    'email': 'fisherjennifer@example.net',
    'phone_number': '925.404.9804',
    'json': {
    'name': 'Wanda Church',
    'address': '0872 Danielle Loaf\nLambertview, VT 51212',
},
    'key60302': 'value70589',
    'key35423': 'value40315',
    'key87061': 'value26410',
    'key9885': 'value26017',
    'key98732': 'value95660',
    'key18754': 'value88291',
    'key7228': 'value23921',
    'key76819': 'value80683',
    'key13815': 'value31174',
},
    {
    'id': 17527486529912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Anthony Wilson',
    'address': '19793 Benjamin Hills Suite 083\nMurphyberg, CT 63721',
    'text': 'Above wrong nature outside themselves. Serious draw want church question technology. Per from case nice chair. Doctor form management sport see piece.\nVisit plan fall. Us result building write.',
    'email': 'pmarsh@example.net',
    'phone_number': '6939691305',
    'json': {
    'name': 'Daniel Foley',
    'address': 'Unit 3962 Box 5213\nDPO AP 07794',
},
    'key43008': 'value52724',
    'key76762': 'value78975',
    'key42261': 'value71331',
    'key90651': 'value21096',
},
    {
    'id': 17527486529921,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Dylan Montgomery',
    'address': '918 Carter Lodge\nNew Pamela, WV 65637',
    'text': 'Role respond focus want allow world place. Boy return pass center street leave.\nAlone sell within item woman number. Physical fund what design.\nHis information economy growth.',
    'email': 'ashley23@example.com',
    'phone_number': '754.936.1095x667',
    'json': {
    'name': 'Terry George',
    'address': '7294 Donna Key Suite 790\nSouth Charles, WA 87526',
},
    'key40104': 'value35327',
    'key44856': 'value3629',
    'key11712': 'value7966',
    'key60013': 'value79303',
    'key8596': 'value85608',
    'key30169': 'value29914',
},
    {
    'id': 17527486529931,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Troy David',
    'address': 'Unit 0091 Box 2124\nDPO AA 98413',
    'text': 'Food culture spend prove back. Leave reduce successful pattern.\nAnyone art conference hundred leave why. Few feeling will training team.',
    'email': 'bpetty@example.net',
    'phone_number': '933.445.8087x142',
    'json': {
    'name': 'Robert Thomas',
    'address': '091 Miller Road Apt. 572\nSavagechester, CT 85417',
},
    'key65549': 'value38687',
    'key19193': 'value88725',
    'key9367': 'value8277',
    'key39222': 'value52705',
    'key29254': 'value3790',
    'key48473': 'value85564',
    'key92053': 'value42120',
    'key70386': 'value45317',
    'key92054': 'value96506',
},
    {
    'id': 17527486529941,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Travis Santiago',
    'address': '783 Lopez Viaduct Suite 712\nReginaside, IA 64115',
    'text': 'Someone through dark politics analysis case model real. Industry bring build each process hospital compare.',
    'email': 'tbridges@example.org',
    'phone_number': '+1-671-560-1761x4007',
    'json': {
    'name': 'Mr. Justin Olson',
    'address': '8852 Megan Parks Suite 681\nLake Nicole, KS 35220',
},
    'key27278': 'value99040',
    'key48215': 'value35534',
},
    {
    'id': 17527486529951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Christopher Brown',
    'address': '770 Brittany Burg\nLisaburgh, IL 69438',
    'text': 'Right goal this culture practice. Now represent board customer author PM present.\nEasy international majority program condition TV. Join realize partner if half Congress this.',
    'email': 'nancybrady@example.net',
    'phone_number': '831.298.0913x1434',
    'json': {
    'name': 'Traci Harris',
    'address': '71901 Derrick Walks Suite 300\nPatrickland, TN 04995',
},
    'key79979': 'value62177',
    'key54020': 'value49323',
    'key8458': 'value41104',
    'key61902': 'value4386',
    'key39088': 'value28143',
    'key34166': 'value80042',
    'key67140': 'value42749',
    'key60649': 'value12302',
},
    {
    'id': 17527486529962,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Lisa Leonard',
    'address': '5364 Amy Port\nAmandashire, OH 72150',
    'text': 'Memory daughter these. Think resource growth real. Test heavy name southern age.\nPossible both school mean. Something describe pretty player nor catch. Out affect write modern work week.',
    'email': 'laura03@example.net',
    'phone_number': '777-556-2523x3818',
    'json': {
    'name': 'Alexander Pham',
    'address': '75679 Gill Center\nSolisville, LA 20794',
},
    'key32505': 'value86584',
    'key82623': 'value95098',
    'key48566': 'value86865',
    'key70575': 'value73675',
    'key68543': 'value14273',
},
    {
    'id': 17527486529973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Mindy Hoover',
    'address': '5456 Oscar Land\nWest Anthony, AS 77497',
    'text': 'Deal rather people lead set save. Character run speech lose consumer break. Send choice garden agent movie matter eat doctor.',
    'email': 'lesliefreeman@example.org',
    'phone_number': '(562)938-0060',
    'json': {
    'name': 'Allison Decker',
    'address': '383 Christopher Trafficway Apt. 270\nGrahammouth, WA 55530',
},
    'key4615': 'value22204',
    'key95489': 'value87009',
    'key14244': 'value15212',
    'key26138': 'value39137',
},
    {
    'id': 17527486529983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Joanna Franklin',
    'address': '10576 Perez Knoll\nRichborough, VA 16555',
    'text': 'Election computer relationship social. Become owner whose beautiful modern prepare. From nature art already soldier girl hotel ball.',
    'email': 'andrewburns@example.net',
    'phone_number': '+1-709-296-8705x12300',
    'json': {
    'name': 'Gabriela Nash',
    'address': '264 Daniel Shoals\nHowardmouth, AZ 45908',
},
    'key15636': 'value57919',
    'key29552': 'value20473',
    'key43641': 'value21491',
    'key20195': 'value54498',
    'key10259': 'value43610',
    'key84733': 'value98639',
    'key98871': 'value3695',
    'key25815': 'value63373',
    'key64265': 'value57489',
    'key176': 'value34270',
},
    {
    'id': 17527486529995,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Cathy Glenn',
    'address': '92375 Dawn Row Apt. 877\nSavannahfurt, CA 80145',
    'text': 'Your between theory list rate someone. Far arm use history.\nDinner adult camera magazine. Owner ground well himself black story.',
    'email': 'jacksonroberto@example.com',
    'phone_number': '470-248-8516x11932',
    'json': {
    'name': 'Amy Mccann',
    'address': '761 Gonzalez Court\nNew Kimberlymouth, GU 76653',
},
    'key69508': 'value31465',
    'key800': 'value30123',
    'key87695': 'value28618',
    'key80939': 'value3884',
    'key14383': 'value95500',
},
    {
    'id': 17527486530007,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jacob Rose',
    'address': 'PSC 9190, Box 5268\nAPO AP 24906',
    'text': 'Respond adult strategy Republican small nor. Hospital remember most Republican. Chance base item north system political seem.\nWind building daughter. Create moment kitchen upon than financial.',
    'email': 'wandablanchard@example.org',
    'phone_number': '271-460-5514',
    'json': {
    'name': 'Brian Kane',
    'address': '1609 Watts Circle\nMillerton, ND 78331',
},
    'key8076': 'value53955',
},
    {
    'id': 17527486530017,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Kelly Salazar',
    'address': '29634 Davenport Courts\nSouth Allison, NM 69494',
    'text': 'Down among student. Entire stock decade lot. Pattern certainly least ask identify sit trouble. Bring test military however best develop office.',
    'email': 'rmartin@example.org',
    'phone_number': '6185780469',
    'json': {
    'name': 'Paula Parker',
    'address': '124 Ford Rest\nTracimouth, MD 29848',
},
    'key74377': 'value36244',
    'key54821': 'value97538',
    'key19174': 'value45151',
    'key30675': 'value67000',
    'key90807': 'value68801',
    'key38500': 'value46210',
},
    {
    'id': 17527486530027,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'James Vazquez',
    'address': 'PSC 0550, Box 4600\nAPO AP 19397',
    'text': 'Consumer culture sit policy. Nation between run camera site long be. Dog check report course toward explain star.',
    'email': 'nguyendiane@example.org',
    'phone_number': '(981)556-7314x0815',
    'json': {
    'name': 'Mark Hopkins',
    'address': 'Unit 7521 Box 1816\nDPO AA 90748',
},
    'key65680': 'value51328',
    'key92384': 'value24652',
    'key7399': 'value30006',
    'key51945': 'value40465',
    'key44734': 'value46410',
    'key1612': 'value62026',
},
    {
    'id': 17527486530035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Nicole Mason',
    'address': '541 Alyssa Course\nNorth Christopher, NM 02548',
    'text': 'Well save federal according challenge. Note color second civil view treatment exactly. Many education level later.',
    'email': 'paul30@example.net',
    'phone_number': '(857)497-8725x3817',
    'json': {
    'name': 'Alexis Hill',
    'address': '1613 Mary Stream\nNathanton, NE 38555',
},
    'key70829': 'value60048',
    'key52358': 'value69930',
    'key27343': 'value36684',
    'key50825': 'value99599',
    'key81090': 'value73399',
    'key53887': 'value90217',
    'key22257': 'value9615',
    'key51139': 'value69084',
    'key14163': 'value72779',
},
    {
    'id': 17527486530045,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Catherine Wheeler',
    'address': '228 Aguilar Green Suite 574\nEast Brianna, FL 87239',
    'text': 'Accept race summer above field five customer. Gun nice play because. Leader amount reflect.',
    'email': 'jessica98@example.org',
    'phone_number': '+1-897-958-9177x00817',
    'json': {
    'name': 'Mr. Adam Ryan Jr.',
    'address': '695 Malone Island Suite 176\nWest Barbaraton, GU 96649',
},
    'key25714': 'value48949',
    'key66314': 'value65801',
    'key56120': 'value32618',
    'key3874': 'value85102',
},
    {
    'id': 17527486530056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Benjamin Garza',
    'address': '41018 Gregory View Suite 832\nSouth Carolyn, PA 43070',
    'text': 'Mouth hold senior degree bank raise. Stand onto lawyer sense in run tough. Add more room.\nElse picture expect. Strategy focus yes thank stage pull.',
    'email': 'andrew88@example.com',
    'phone_number': '5034273885',
    'json': {
    'name': 'Kelly Park',
    'address': '26368 Chapman Mountains\nWallacestad, NV 98459',
},
    'key51771': 'value33773',
    'key38153': 'value19228',
    'key23509': 'value30521',
    'key95641': 'value70642',
    'key44157': 'value66807',
},
    {
    'id': 17527486530067,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Dawn Aguilar',
    'address': '034 Conway Trail Suite 684\nLake Nancy, WI 26135',
    'text': 'Write start for include energy. Enough must employee become minute still. Again what fall color note production need everything.',
    'email': 'vaughananne@example.org',
    'phone_number': '3959599646',
    'json': {
    'name': 'Jason Parker',
    'address': 'Unit 6527 Box 7169\nDPO AE 21283',
},
    'key40527': 'value50886',
    'key73514': 'value56762',
    'key96794': 'value77702',
    'key69067': 'value55634',
},
    {
    'id': 17527486530076,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Pamela Stevens',
    'address': '860 Johnny Loop Apt. 328\nNguyenview, LA 25041',
    'text': 'Buy tree pay new near. When either Mr figure address continue box. Kid about writer skin current.\nPurpose use college day drug wind no. Nor writer goal compare.',
    'email': 'johnmcclain@example.org',
    'phone_number': '707-451-2604x0888',
    'json': {
    'name': 'Robert Smith',
    'address': '17018 Erica Coves\nLake Melissachester, WY 39524',
},
    'key90025': 'value25989',
    'key32105': 'value82470',
    'key65592': 'value196',
    'key19691': 'value79544',
},
    {
    'id': 17527486530087,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Ryan Lambert',
    'address': '358 Jessica Passage Suite 256\nDavidport, HI 78625',
    'text': 'Important real quality. Example read environment mention return. Law will nice. Present strong knowledge support ago anything.\nAgency hear whether bad the. Many fall student can local.',
    'email': 'williamgonzales@example.org',
    'phone_number': '904.973.9799',
    'json': {
    'name': 'David Williams',
    'address': '555 Christensen Pine Apt. 690\nBethfort, DE 62352',
},
    'key88178': 'value53781',
    'key83547': 'value80950',
    'key29591': 'value82802',
    'key25799': 'value81115',
    'key8403': 'value19390',
    'key5196': 'value21194',
    'key41923': 'value24427',
},
    {
    'id': 17527486530099,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Joseph Alexander',
    'address': '882 Cassandra Club Apt. 964\nPort Brianna, KY 84954',
    'text': 'Themselves pass check discussion amount another physical.\nDesign put some perhaps. Go term meeting. Air century effect marriage fast.\nFormer site whether.',
    'email': 'nicolesutton@example.org',
    'phone_number': '311.835.5184',
    'json': {
    'name': 'Carrie Jacobs',
    'address': '989 Charles Terrace Suite 249\nNew Michelle, MS 80254',
},
    'key12150': 'value35725',
},
    {
    'id': 17527486530110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Timothy Ponce',
    'address': '756 Graham Mews Apt. 451\nBruceland, MO 40770',
    'text': 'Her item none go where discover prepare. Task green building always clear evening century course. Stage share late where financial director say.\nIdentify present sense account general.',
    'email': 'oruiz@example.net',
    'phone_number': '923-495-2552x1793',
    'json': {
    'name': 'Kimberly Sparks',
    'address': '5713 Lang Mission Apt. 990\nColtonton, OH 86069',
},
    'key34749': 'value96352',
},
    {
    'id': 17527486530121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Amanda Nunez',
    'address': '733 Castillo Meadow Suite 740\nNew Eric, ND 20527',
    'text': 'Operation local small public look reflect organization. Since home heavy hold word speech carry none.',
    'email': 'martinezjade@example.com',
    'phone_number': '291.865.4961',
    'json': {
    'name': 'Tammy Hodge',
    'address': 'PSC 4714, Box 2219\nAPO AA 15924',
},
    'key39605': 'value31867',
    'key26990': 'value89452',
    'key1511': 'value76899',
    'key34683': 'value10703',
    'key10397': 'value27158',
    'key2111': 'value45981',
    'key37262': 'value55641',
    'key87782': 'value94797',
    'key37227': 'value90322',
    'key22506': 'value22907',
},
    {
    'id': 17527486530131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Kelly Strickland',
    'address': 'USS Velasquez\nFPO AE 56065',
    'text': 'Successful visit indicate professor detail new just. Today one performance whole example else meeting suggest.\nCompare teach thousand strategy red rise no down. Professor open feel crime business.',
    'email': 'qmcdowell@example.org',
    'phone_number': '483-811-2327x6048',
    'json': {
    'name': 'Christopher Morales',
    'address': '23904 Savannah Pike Apt. 903\nNorth David, NY 38784',
},
    'key72930': 'value50051',
    'key15464': 'value31385',
    'key85661': 'value35714',
    'key30678': 'value2328',
    'key85072': 'value70985',
    'key95654': 'value4924',
    'key73368': 'value79857',
    'key35300': 'value1410',
    'key29461': 'value63257',
},
    {
    'id': 17527486530140,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Nicole Clark',
    'address': '6803 Shelley Tunnel\nThompsonberg, MS 85630',
    'text': 'Determine evidence usually full protect with finish ground. War prevent social room war. International law our bill health these. Leave attack for defense.',
    'email': 'katrina84@example.net',
    'phone_number': '+1-259-309-3873x70218',
    'json': {
    'name': 'Bailey Hernandez',
    'address': '120 Laura Pines\nStephenfort, TX 03795',
},
    'key44233': 'value72715',
    'key19541': 'value82635',
    'key31924': 'value68516',
    'key75519': 'value12176',
},
    {
    'id': 17527486530151,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'John Johnson',
    'address': '839 Jennifer Ramp Apt. 304\nBobbyville, NJ 91880',
    'text': 'Accept attack identify believe professional color would. Experience pick road majority second term.\nPull important old live. Former air wall.',
    'email': 'brendanwilson@example.org',
    'phone_number': '+1-329-538-8711',
    'json': {
    'name': 'Robert Mercado Jr.',
    'address': '68308 Boyle Prairie Suite 350\nLake Jesse, NH 94377',
},
    'key47451': 'value62665',
    'key20552': 'value99782',
    'key47871': 'value95589',
    'key42615': 'value58029',
    'key20606': 'value17857',
    'key40091': 'value87142',
    'key23630': 'value76901',
    'key91085': 'value789',
    'key44614': 'value55169',
},
    {
    'id': 17527486530164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Linda Thomas',
    'address': 'Unit 9407 Box 0198\nDPO AE 00630',
    'text': 'With senior score wife.\nAlready individual sister product hear exactly shoulder. Make however those significant management meet arrive. Nation company become heavy put beat.',
    'email': 'stephaniesanchez@example.org',
    'phone_number': '001-897-732-5503x87578',
    'json': {
    'name': 'Gwendolyn Wilkins',
    'address': '83120 Michael Squares\nLewismouth, VT 53977',
},
    'key31103': 'value94243',
    'key77305': 'value36947',
},
    {
    'id': 17527486530174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Brenda Hartman',
    'address': '2775 Sarah Estate\nSophiaton, MH 91270',
    'text': 'Food her important edge bag strategy. Fund write treat friend. Seem might west collection technology medical Mr.',
    'email': 'travissmith@example.net',
    'phone_number': '660.852.6419x20942',
    'json': {
    'name': 'Cheryl Herrera',
    'address': '759 Deanna Light Apt. 903\nMichaelfort, AL 79893',
},
    'key43307': 'value2498',
    'key3837': 'value9984',
    'key99732': 'value21851',
    'key58208': 'value62947',
    'key51817': 'value59353',
    'key55755': 'value31606',
    'key87809': 'value19206',
},
    {
    'id': 17527486530184,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Peter Vasquez',
    'address': '633 Nicole Mill\nPacehaven, WA 38703',
    'text': 'Blood lose break view hundred world floor his. No machine statement again. Always benefit scene citizen change.\nContinue there step movie else mission send. Impact reflect never half song.',
    'email': 'lori89@example.net',
    'phone_number': '758-705-4602x6423',
    'json': {
    'name': 'Richard Fisher',
    'address': '5040 White Lock Apt. 986\nLisaland, KS 70218',
},
    'key97802': 'value73013',
    'key67946': 'value18160',
    'key17204': 'value71341',
    'key75853': 'value45872',
    'key76318': 'value11818',
    'key99808': 'value63255',
    'key95843': 'value64409',
},
    {
    'id': 17527486530195,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Rodney Holmes',
    'address': '8037 Vincent Park Apt. 048\nEast Brianna, WI 73817',
    'text': 'Performance surface economy technology federal.\nAnything look certainly inside ago program type job. Until southern major art. Attention race seek bad free wonder.',
    'email': 'jasonbarnett@example.net',
    'phone_number': '254.598.3871x005',
    'json': {
    'name': 'Luke Cobb DVM',
    'address': '04688 Burton Knolls\nLake Tinafort, GA 51993',
},
    'key23192': 'value31427',
},
    {
    'id': 17527486530207,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Rebecca Gibbs',
    'address': '084 Mills Canyon\nMichelestad, FL 99104',
    'text': 'Half near home candidate country popular recently. Responsibility about child pull Republican.',
    'email': 'wrightchelsea@example.com',
    'phone_number': '253.417.8653',
    'json': {
    'name': 'Amy Morales',
    'address': '8188 Smith Cliffs\nNorth Shariberg, WI 27167',
},
    'key14900': 'value61974',
    'key38586': 'value66924',
    'key90516': 'value40500',
    'key50232': 'value67468',
    'key81636': 'value97564',
    'key853': 'value37858',
},
    {
    'id': 17527486530218,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Amanda Rivera',
    'address': '5337 Nicholas Fall\nOmarfurt, VI 76520',
    'text': 'In spend kitchen seem system off. Science require letter recently can list low. Economic other drive civil form next piece.',
    'email': 'mitchell90@example.com',
    'phone_number': '+1-224-531-9718x6524',
    'json': {
    'name': 'Brendan Mcguire',
    'address': '57304 Gary Glens\nLake Vanessashire, KY 63883',
},
    'key73476': 'value86489',
    'key80344': 'value71169',
    'key33524': 'value1742',
},
    {
    'id': 17527486530228,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Erica Barnes',
    'address': '860 Jordan Run Apt. 283\nKaylaberg, NH 18749',
    'text': 'Instead talk on. Wide note receive receive.\nWin pressure response compare too. Feeling head nation this property somebody interesting through.',
    'email': 'petersontheresa@example.com',
    'phone_number': '278.735.8728',
    'json': {
    'name': 'Karen Gutierrez',
    'address': '32034 Toni Fork\nFuentesbury, IA 74473',
},
    'key68284': 'value74936',
    'key76155': 'value82369',
    'key33517': 'value68024',
},
    {
    'id': 17527486530240,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Cynthia Williamson',
    'address': '25906 Fox Station\nNorth Brianmouth, MS 79627',
    'text': 'Amount if at security. Involve direction while line individual you majority. Let character speak soldier. Town finish without contain truth its soon begin.',
    'email': 'spencerlaura@example.net',
    'phone_number': '911-384-1906',
    'json': {
    'name': 'Sharon Williams',
    'address': '402 Sanchez Row\nLeachland, MD 23214',
},
    'key76800': 'value5484',
    'key82532': 'value97899',
    'key18013': 'value21437',
    'key26101': 'value33373',
    'key9066': 'value38865',
    'key97937': 'value45618',
    'key58639': 'value78336',
},
    {
    'id': 17527486530252,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Miguel Tyler',
    'address': '867 Mcdonald Motorway\nEast Andrew, AZ 74633',
    'text': 'Effort north performance.\nGround state certain authority this history. Population book stage production. Phone government field against husband through allow your.',
    'email': 'showard@example.org',
    'phone_number': '7685725972',
    'json': {
    'name': 'Holly Green',
    'address': '8997 Garza Junctions Apt. 573\nPort Dawnburgh, MD 23551',
},
    'key49431': 'value55117',
    'key55021': 'value68249',
    'key75574': 'value65811',
    'key36072': 'value1728',
    'key21234': 'value60135',
    'key20452': 'value93752',
    'key74612': 'value62689',
    'key75148': 'value68391',
    'key83816': 'value47283',
    'key92705': 'value57429',
},
    {
    'id': 17527486530263,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kevin Montoya',
    'address': '389 Proctor Dam\nNew Veronicastad, SC 99090',
    'text': 'Hundred grow wish gas. Individual environmental responsibility base believe interview local.',
    'email': 'ortizbarbara@example.com',
    'phone_number': '(289)694-6601',
    'json': {
    'name': 'Veronica Schmidt',
    'address': 'USS Murphy\nFPO AA 18458',
},
    'key50372': 'value58429',
},
    {
    'id': 17527486530273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jennifer Reid',
    'address': '76001 Heidi Island\nWest Alanfurt, CA 38465',
    'text': 'Marriage have simple energy painting head. Vote task his group field now knowledge.\nSince ask have teacher. Everybody catch could. With particular ability fight total player them with.',
    'email': 'hdawson@example.net',
    'phone_number': '877.511.6317',
    'json': {
    'name': 'Joseph Hughes',
    'address': '789 Young Springs Suite 799\nYanghaven, MD 57651',
},
    'key72185': 'value58275',
    'key8990': 'value11970',
},
    {
    'id': 17527486530284,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'James Chandler',
    'address': '906 Christopher Isle Apt. 493\nMaryside, WA 21482',
    'text': 'However team away necessary laugh side which available.\nStay around finish. Investment certain question.\nOperation executive six phone. Commercial court end beautiful.',
    'email': 'elizabethhenry@example.com',
    'phone_number': '4888238640',
    'json': {
    'name': 'Rhonda Yang',
    'address': '35137 Christina Extensions Suite 913\nMichaelview, NY 76497',
},
    'key88775': 'value92340',
    'key37357': 'value56609',
    'key97083': 'value77750',
    'key3897': 'value30266',
    'key81749': 'value55624',
    'key96980': 'value32189',
    'key76445': 'value66876',
    'key35729': 'value15048',
    'key92053': 'value61063',
    'key63271': 'value82482',
},
    {
    'id': 17527486530296,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Kevin Harvey',
    'address': '69251 Donna Expressway\nNew Kimberlymouth, PR 00881',
    'text': 'Who air mind reality education these news vote. Policy side social with before. Floor message add floor dream.',
    'email': 'thomasgregory@example.net',
    'phone_number': '001-685-767-0502x81881',
    'json': {
    'name': 'Joshua Deleon',
    'address': '547 Tyler Villages\nLake Kimberlyberg, TN 23749',
},
    'key14961': 'value24957',
    'key57901': 'value48109',
    'key88406': 'value97994',
    'key54786': 'value21982',
    'key67033': 'value49983',
    'key35822': 'value14909',
    'key50808': 'value38405',
    'key21257': 'value72396',
    'key96823': 'value96914',
    'key66405': 'value71029',
},
    {
    'id': 17527486530307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Jennifer Blankenship',
    'address': '172 Robinson Parkways\nHarrisside, HI 58043',
    'text': 'Cell hold throughout soon treat change. Leader even tree wrong live.\nThis such to participant factor. Food western practice this go. Some sometimes dog number point.',
    'email': 'alexandria51@example.net',
    'phone_number': '481-228-9773',
    'json': {
    'name': 'Brandon Huff',
    'address': '15495 Herrera Port Apt. 389\nNew Kristen, HI 76167',
},
    'key5280': 'value92178',
    'key98459': 'value65583',
    'key68017': 'value59480',
    'key55992': 'value20759',
    'key34125': 'value28955',
    'key98139': 'value43288',
    'key33274': 'value40681',
    'key84160': 'value35032',
    'key91530': 'value88960',
    'key38231': 'value68145',
},
    {
    'id': 17527486530318,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Sharon Gonzalez',
    'address': '4068 Jeremy Loop Suite 362\nBishopberg, SC 81050',
    'text': 'Officer fill voice accept. Young well early quickly mother science start. Might teacher yes city month.',
    'email': 'heather83@example.com',
    'phone_number': '2565250545',
    'json': {
    'name': 'Lauren Taylor',
    'address': '9063 John Lock Apt. 394\nNew Michael, SC 11908',
},
    'key27859': 'value79059',
    'key56363': 'value29300',
    'key23579': 'value46605',
    'key47025': 'value36858',
    'key17181': 'value78755',
    'key83699': 'value93546',
},
    {
    'id': 17527486530329,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Susan Harrington',
    'address': '58486 Carlson Lock\nTammyland, ND 09353',
    'text': 'Law charge role area industry. Size population travel federal method. Smile marriage radio international most.',
    'email': 'david99@example.org',
    'phone_number': '764.352.2594x165',
    'json': {
    'name': 'Mr. Steven Morales MD',
    'address': '65121 Dustin Common Suite 343\nLake Patricia, VA 91955',
},
    'key68836': 'value43466',
    'key7678': 'value30046',
    'key14308': 'value82766',
    'key24052': 'value3685',
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
    'RequestId': '083743ce-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_26_889953JOjSAqRc',
    'filter': 'uid > 0',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'uid',
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



    def test_request_4(self):
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '083743ce-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_37_26_889953JOjSAqRc',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 01]_1752748659.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid011752748659Json()
    test.run_tests()
