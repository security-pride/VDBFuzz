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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752747061_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752747061.json"
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



class AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulQueryVectorBySdk1752747061Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752747061.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752747061.json"
        self.test_count = 4  # 测试方法数量
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
    'RequestId': '50c23c9c-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_50_491151yWWFeQhJ',
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
    'RequestId': '50c23c9c-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_50_491151yWWFeQhJ',
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
    'RequestId': '50c23c9c-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_50_491151yWWFeQhJ',
    'data': [
    {
    'id': 17527470565561,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'David Orozco',
    'address': '20189 Aaron Gateway\nRileyside, OR 41366',
    'text': 'Account industry Republican investment big note. Thousand reflect opportunity nation.\nPoint wonder skill pretty watch arm. College degree decade win section dream particularly.',
    'email': 'carloconnor@example.com',
    'phone_number': '868.522.3231x32268',
    'json': {
    'name': 'Juan Coleman',
    'address': '7195 Natasha Roads\nSouth Jon, CT 16888',
},
    'key91743': 'value74662',
    'key8699': 'value49839',
    'key34371': 'value79659',
},
    {
    'id': 17527470565578,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sharon Rodriguez',
    'address': '502 Julie Rue\nLake Alexis, VI 48629',
    'text': 'Bar speak role feel present. Difference movie room since.\nListen deal where room why become. Activity amount team section ten human ok. Law theory medical drug.',
    'email': 'joshuajones@example.net',
    'phone_number': '283.863.5107x748',
    'json': {
    'name': 'Shannon Morgan',
    'address': '505 Natasha Road\nNew Kara, PW 00572',
},
    'key39603': 'value20505',
    'key34150': 'value60338',
    'key54213': 'value3893',
    'key42990': 'value42495',
    'key58499': 'value12141',
    'key65762': 'value7041',
    'key62313': 'value83133',
    'key76930': 'value17293',
    'key94511': 'value32491',
    'key29986': 'value32630',
},
    {
    'id': 17527470565590,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Kelsey Ray',
    'address': '3912 Collins Turnpike\nFrankton, VT 01667',
    'text': 'Boy about value better chance admit believe. House trouble good theory on. Pm house oil young dream all.\nLeader pattern star end simply want new thousand.\nMean up identify natural ability.',
    'email': 'orogers@example.org',
    'phone_number': '(816)985-3770x263',
    'json': {
    'name': 'Joseph Lee',
    'address': '4519 Gomez Port Suite 456\nKevinton, UT 38472',
},
    'key83639': 'value15888',
    'key45233': 'value62421',
    'key37392': 'value84414',
    'key1377': 'value35632',
    'key54743': 'value40268',
    'key64071': 'value86673',
    'key69508': 'value14508',
    'key96078': 'value1570',
    'key743': 'value41817',
},
    {
    'id': 17527470565603,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'John Padilla',
    'address': '787 Christopher Key Suite 814\nChristopherview, NE 02161',
    'text': 'Modern state I back student miss. Senior treatment dog seven.\nSpecial force top if character agree.\nMagazine environmental share focus film. Around high field cultural manage glass society.',
    'email': 'davisdeborah@example.org',
    'phone_number': '+1-256-955-5432x6407',
    'json': {
    'name': 'Katie Allen',
    'address': '569 White Alley Suite 551\nNorth Melindafurt, SC 41077',
},
    'key81080': 'value72085',
    'key34782': 'value17697',
    'key69817': 'value85301',
    'key71114': 'value14091',
},
    {
    'id': 17527470565615,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Lee Gross',
    'address': 'Unit 0821 Box 5905\nDPO AA 85812',
    'text': 'Different positive economic station rock party. Matter speech them professional board system. Economic quality who what. Ground campaign voice buy way create sing.',
    'email': 'buckrachel@example.net',
    'phone_number': '(352)937-6231',
    'json': {
    'name': 'James Davenport',
    'address': '90139 Clark Ridges Apt. 962\nElizabethfurt, MN 59419',
},
    'key66376': 'value54964',
    'key78802': 'value32556',
    'key8824': 'value39232',
    'key39147': 'value95368',
    'key68153': 'value92994',
    'key25154': 'value98512',
},
    {
    'id': 17527470565626,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Scott Kelly',
    'address': '98490 Wesley Circle\nHollowayhaven, MD 53569',
    'text': 'Girl rise floor computer if ahead sit. Unit your think save end character especially. Near bad player control song prove drive.',
    'email': 'michaelwilson@example.com',
    'phone_number': '+1-382-923-1503x3286',
    'json': {
    'name': 'Jennifer Neal',
    'address': '4486 Proctor Ramp\nLorimouth, LA 36746',
},
    'key42739': 'value90363',
    'key62681': 'value87325',
    'key12563': 'value95800',
    'key53264': 'value63437',
},
    {
    'id': 17527470565638,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Angela Wallace',
    'address': '574 Antonio Green\nAmyside, GA 08682',
    'text': 'Dog physical range record involve trouble. Party other body usually contain student section social.\nMatter break through do yard beautiful hair. Class great along within.',
    'email': 'wrightkarla@example.com',
    'phone_number': '+1-550-454-2158x67089',
    'json': {
    'name': 'Erin Swanson',
    'address': '1006 Anthony Landing Suite 983\nAlexandratown, MA 91609',
},
    'key62575': 'value22718',
    'key70544': 'value52498',
    'key28412': 'value5782',
    'key4937': 'value18496',
},
    {
    'id': 17527470565650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jeffrey Martin',
    'address': '032 Castro Islands\nJonathanville, TX 46855',
    'text': 'Design kid season sure decision suddenly cold. Five attack population quite account indicate. Center large TV agree on tell.',
    'email': 'taylorferguson@example.net',
    'phone_number': '001-423-540-5529x82318',
    'json': {
    'name': 'Thomas Swanson',
    'address': '99946 Kurt Route Suite 565\nLake Susanfort, IA 37403',
},
    'key20895': 'value58434',
    'key72239': 'value36408',
    'key92266': 'value39476',
    'key5891': 'value2567',
},
    {
    'id': 17527470565662,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jeremy Khan',
    'address': '4610 Andrew Extensions\nNew Traceychester, CO 70676',
    'text': 'Interesting hotel soldier anyone become. Side skill step air. Move surface value film determine.\nBuild million recognize involve morning shake kitchen. Way stay picture shoulder.',
    'email': 'cherylsweeney@example.net',
    'phone_number': '(453)368-1583',
    'json': {
    'name': 'Austin Roberson',
    'address': '780 Brenda Vista\nNorth Reginaburgh, NJ 40149',
},
    'key74629': 'value92257',
    'key3854': 'value93096',
    'key2674': 'value62089',
    'key82351': 'value69283',
    'key29435': 'value5179',
    'key76393': 'value9950',
},
    {
    'id': 17527470565673,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Brittany Skinner',
    'address': 'PSC 8531, Box 3404\nAPO AP 47648',
    'text': 'Stay early small each debate sometimes them. Seek fill build tell war capital. Medical role art significant goal whatever over.',
    'email': 'shane71@example.com',
    'phone_number': '366-648-0830',
    'json': {
    'name': 'Tamara Ellison',
    'address': '6295 Judith Hollow Apt. 248\nNorth Alexander, FM 05093',
},
    'key87047': 'value2503',
},
    {
    'id': 17527470565682,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Matthew Gilbert',
    'address': '874 Jessica Causeway\nBrianfort, ND 53071',
    'text': 'Many possible have just word couple foot. Southern throw break everything year exist Republican likely. Possible win expect industry who team.',
    'email': 'coreycombs@example.net',
    'phone_number': '463-575-1586x48060',
    'json': {
    'name': 'Diane Greene',
    'address': '34904 Amanda Drive\nPetersonborough, CT 60871',
},
    'key43203': 'value21012',
    'key98792': 'value97685',
    'key23497': 'value29082',
    'key70930': 'value11555',
    'key61234': 'value40035',
},
    {
    'id': 17527470565692,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Steven Stewart',
    'address': '5143 Gaines Parks Apt. 902\nPort Brenda, MO 17575',
    'text': 'Far speech note crime. Couple politics at guy small. Door player modern and cost dinner. Democrat attack option must fire ago.',
    'email': 'pruittchristina@example.org',
    'phone_number': '001-825-402-8604x976',
    'json': {
    'name': 'Daniel Garcia',
    'address': '19050 Felicia Ranch Suite 699\nMckinneyborough, PW 47446',
},
    'key61525': 'value66615',
    'key79982': 'value23711',
    'key55939': 'value9118',
    'key52271': 'value89335',
    'key91232': 'value75472',
    'key97735': 'value44610',
},
    {
    'id': 17527470565704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'James Davis',
    'address': '533 Madden Keys\nHeatherborough, NY 61062',
    'text': 'Certainly show themselves once executive medical those. Various sport like both pay. Science floor ask successful should kind picture.\nDown sea it major. Structure who enter partner later.',
    'email': 'juan92@example.net',
    'phone_number': '5035759483',
    'json': {
    'name': 'Jonathan Cameron',
    'address': 'PSC 0143, Box 2403\nAPO AP 77847',
},
    'key82653': 'value23486',
},
    {
    'id': 17527470565713,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Krista Wilkins',
    'address': '8172 Smith Fall\nPort Natalie, MA 03977',
    'text': 'Hundred occur general into across action. Exist important range state several commercial. Time after rock job floor pay court yes.',
    'email': 'nealvanessa@example.org',
    'phone_number': '749.754.1777',
    'json': {
    'name': 'Brenda Melton',
    'address': '05150 Martinez Trail Apt. 260\nGregoryland, NY 63035',
},
    'key22015': 'value77083',
    'key82099': 'value97908',
    'key30129': 'value1895',
    'key23592': 'value83830',
    'key59922': 'value83672',
    'key76657': 'value99847',
},
    {
    'id': 17527470565725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Tracy Riley',
    'address': '74456 Jordan Estate Apt. 922\nAmandatown, SC 68567',
    'text': 'Simple side these tonight measure grow so. Us ready certainly occur student.\nAlthough debate between memory. Force partner character against drug ready.',
    'email': 'reidstanley@example.com',
    'phone_number': '778-840-2175x9456',
    'json': {
    'name': 'Patricia Ruiz',
    'address': '6389 Nguyen Fields Apt. 943\nNorth Katherine, MT 31963',
},
    'key6504': 'value47505',
    'key84572': 'value33679',
    'key34655': 'value77170',
    'key36748': 'value19350',
    'key64373': 'value18092',
    'key7817': 'value62201',
    'key70335': 'value76068',
    'key62007': 'value201',
    'key6034': 'value95328',
    'key51582': 'value25611',
},
    {
    'id': 17527470565737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Tammy Miller',
    'address': '74791 Angela Loaf\nSouth Patriciafurt, MD 83189',
    'text': 'Or affect up audience. Bed oil value mission financial small. Political around firm voice.\nReceive compare such sing out necessary market. Use know represent talk trouble somebody none example.',
    'email': 'elizabethday@example.net',
    'phone_number': '461.988.2785',
    'json': {
    'name': 'Jessica Sanders',
    'address': 'PSC 0639, Box 7175\nAPO AP 03559',
},
    'key99767': 'value65793',
    'key38572': 'value23355',
    'key29890': 'value50739',
    'key83723': 'value99217',
    'key38358': 'value27698',
    'key94667': 'value25346',
},
    {
    'id': 17527470565747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Joshua Ellis',
    'address': '03577 Matthew Summit\nEast Julie, AS 94908',
    'text': 'Executive eye research lot deal memory. Research trial film peace student. Different near service.\nHelp street Democrat drop listen none. Car article hard fight pretty.',
    'email': 'adamsmith@example.org',
    'phone_number': '426-295-9746x359',
    'json': {
    'name': 'Christopher Young',
    'address': '708 Laura Expressway Apt. 807\nErikborough, CT 64696',
},
    'key15667': 'value59109',
    'key98298': 'value59166',
},
    {
    'id': 17527470565759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Justin Santos',
    'address': 'Unit 8397 Box 9415\nDPO AA 77796',
    'text': 'Environmental head world woman fund keep. Offer man rest each develop sport foreign.\nPretty ever authority air finally. Require work firm seem.',
    'email': 'fishersusan@example.net',
    'phone_number': '6885993174',
    'json': {
    'name': 'Christopher Cunningham',
    'address': '4775 Jamie Prairie\nCassandraburgh, AR 92174',
},
    'key28713': 'value3267',
    'key6055': 'value98076',
    'key21078': 'value96575',
    'key41307': 'value68790',
    'key64719': 'value61371',
    'key30942': 'value19815',
    'key34312': 'value22256',
    'key38332': 'value77416',
},
    {
    'id': 17527470565769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Dale Lynch',
    'address': '8890 Holly Pike\nEast Jodiburgh, FM 78601',
    'text': 'Evidence prove him item leave. Join live government home section.\nSing mean table positive. Sport investment war experience ball see else. Miss agree rich stand economic.',
    'email': 'suzannerussell@example.org',
    'phone_number': '325-536-3587',
    'json': {
    'name': 'John Anderson',
    'address': '86330 Mcdonald Stream\nSouth Johnnymouth, FM 10224',
},
    'key53118': 'value90837',
    'key94155': 'value81970',
    'key67689': 'value96807',
    'key85258': 'value64592',
    'key49077': 'value87203',
    'key27977': 'value8280',
    'key96837': 'value44734',
},
    {
    'id': 17527470565780,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Brittany Sullivan',
    'address': '34267 Monica Highway\nThomastown, CO 11552',
    'text': 'Road claim paper future shoulder arrive. Enjoy sister medical scene.\nBeyond there see and behavior. Get end expect outside town.\nPrice position need money employee. Nor its woman majority care.',
    'email': 'peterrusso@example.org',
    'phone_number': '001-628-416-6707x77649',
    'json': {
    'name': 'John Higgins',
    'address': '6055 Jennifer Plain Apt. 745\nStarkchester, RI 81602',
},
    'key33129': 'value22579',
    'key83125': 'value24448',
    'key81024': 'value94595',
    'key54895': 'value95609',
    'key40260': 'value77412',
    'key40004': 'value67933',
},
    {
    'id': 17527470565794,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Danny Kaufman',
    'address': '83062 Brown Summit Suite 530\nDylanstad, HI 80430',
    'text': 'Adult hope government range street deal worry. Free price as unit despite.\nBelieve save cell main win.\nPrepare again process physical give take. Catch kid structure now may majority clearly.',
    'email': 'vazquezandrew@example.com',
    'phone_number': '(837)558-3835',
    'json': {
    'name': 'Elizabeth Hartman',
    'address': '64765 Richardson Lock Apt. 155\nCampbellbury, TN 12497',
},
    'key99759': 'value33686',
    'key19365': 'value67172',
    'key51175': 'value73059',
},
    {
    'id': 17527470565806,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Linda Johnson',
    'address': '44885 Amanda Camp Apt. 153\nEast Alexandertown, NY 66059',
    'text': 'Four matter should analysis start player customer. Account possible father into myself purpose particular decide. Keep hour network popular along two.',
    'email': 'bwalker@example.org',
    'phone_number': '+1-479-251-5666x3545',
    'json': {
    'name': 'Tracy Martinez',
    'address': '061 Mcdonald Brook Apt. 703\nMeganville, AK 19242',
},
    'key59596': 'value65896',
    'key95816': 'value63669',
    'key24961': 'value87448',
    'key42636': 'value46067',
    'key97479': 'value10341',
    'key80897': 'value12069',
    'key79651': 'value52610',
    'key61693': 'value29768',
},
    {
    'id': 17527470565817,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'David Williams',
    'address': 'USNV Sutton\nFPO AE 29261',
    'text': 'Chair party join week soon her. Visit director day move increase reason agent. Give half by generation loss huge leave.',
    'email': 'dcole@example.org',
    'phone_number': '391.613.0685x98173',
    'json': {
    'name': 'Heidi Collins',
    'address': '712 Hayes Ports Apt. 271\nEast Patricia, UT 82444',
},
    'key79166': 'value98852',
    'key59073': 'value68151',
},
    {
    'id': 17527470565827,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Bonnie Bird',
    'address': '9800 Gina Ranch\nPort Elizabeth, NM 12574',
    'text': 'Score however piece add program fall. Score white night edge tough crime billion.\nRadio if word hard part prevent add general. Often past beyond. Travel compare physical.',
    'email': 'emilymcmahon@example.com',
    'phone_number': '4126926310',
    'json': {
    'name': 'Matthew Barnes',
    'address': '4642 Adams Parks Apt. 665\nWest Andrew, NM 83773',
},
    'key55850': 'value27619',
    'key62794': 'value43665',
    'key60868': 'value72500',
    'key77268': 'value22350',
    'key23491': 'value40917',
    'key64200': 'value2510',
    'key7571': 'value44383',
    'key14276': 'value4449',
    'key69843': 'value53105',
},
    {
    'id': 17527470565838,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Miss Cynthia Davis DDS',
    'address': '10413 White Rapid Suite 298\nLake Ellenbury, WY 33220',
    'text': 'Candidate develop total well who run. Contain much Mr drive. Play tree impact economy campaign.\nVote identify executive western several light. Protect determine miss song.',
    'email': 'apriltownsend@example.com',
    'phone_number': '(644)382-6356',
    'json': {
    'name': 'Jordan Harrell',
    'address': '08690 Haley Crest Apt. 246\nRobertstown, DC 54500',
},
    'key9833': 'value97254',
    'key3693': 'value42600',
    'key34226': 'value88203',
    'key65056': 'value90184',
    'key48961': 'value60515',
    'key56659': 'value63607',
    'key16449': 'value90803',
},
    {
    'id': 17527470565850,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Eric Jones',
    'address': '3153 Laurie Avenue Apt. 903\nPort Jason, WY 73654',
    'text': 'Culture group entire. Else nation different the develop message along.\nAbility degree clearly security my. Military program respond catch theory tree. Once quite along.',
    'email': 'patrickbrian@example.org',
    'phone_number': '(234)483-1351',
    'json': {
    'name': 'John Baird',
    'address': '494 Jackson Station Apt. 279\nButlermouth, MN 09546',
},
    'key14424': 'value82165',
    'key28481': 'value61019',
    'key30785': 'value84893',
    'key92888': 'value23102',
    'key17430': 'value70243',
    'key37334': 'value84445',
    'key33166': 'value79746',
    'key19572': 'value62151',
    'key89297': 'value39225',
},
    {
    'id': 17527470565862,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Kimberly Morales',
    'address': '254 Parker Trafficway Apt. 966\nLake Katherineview, NM 69504',
    'text': 'Get know also.\nCommunity suggest court. Week my might describe expect total.\nJoin hot perform miss fall always. Tax she wrong less surface read. Life lose never.',
    'email': 'johnny17@example.com',
    'phone_number': '731-498-2388',
    'json': {
    'name': 'Leslie Alvarez',
    'address': '514 Duran Stream\nPort Daniellestad, MT 94851',
},
    'key67656': 'value83214',
},
    {
    'id': 17527470565873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jean Taylor',
    'address': '30824 Williams Oval Suite 789\nPhillipsstad, MP 22451',
    'text': 'End century move police their tax hard. Foot property task move.\nPlay everything event place. Hold spring citizen continue just. Act degree whose perform lead pay sort.',
    'email': 'delgadojuan@example.net',
    'phone_number': '459.650.6026',
    'json': {
    'name': 'Samuel Cox',
    'address': '411 Christopher Underpass Apt. 047\nPort Elizabethhaven, AS 53313',
},
    'key44756': 'value25980',
    'key15697': 'value2416',
    'key89699': 'value22120',
    'key81461': 'value37587',
    'key86857': 'value3728',
},
    {
    'id': 17527470565885,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Chad Oneill',
    'address': '8795 Michael Overpass\nNorth Stephanie, CA 30033',
    'text': 'Her price west everyone. Process performance heart foot. Forget take identify total.',
    'email': 'diazlisa@example.net',
    'phone_number': '001-546-233-1622x0956',
    'json': {
    'name': 'Jimmy Nelson',
    'address': '8057 Francis Island\nPort Alyssa, NM 23579',
},
    'key51799': 'value19988',
    'key40431': 'value5316',
    'key70538': 'value52560',
    'key90475': 'value36099',
    'key87923': 'value95071',
    'key71398': 'value61998',
    'key75771': 'value33707',
    'key6088': 'value7164',
},
    {
    'id': 17527470565896,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Troy Lewis',
    'address': '02886 Hughes Lakes\nEast Olivia, NM 91022',
    'text': 'Improve simple idea catch who let. Scene themselves method during fine choice suffer. Leg six statement.\nBad country draw summer marriage. Space may tax whose. Boy start soldier lead morning.',
    'email': 'pmendoza@example.net',
    'phone_number': '935-509-1485x61280',
    'json': {
    'name': 'Roger Sanchez',
    'address': '96194 Kathleen Green Suite 566\nRichardsonborough, PW 95468',
},
    'key33431': 'value39180',
    'key50938': 'value49955',
    'key48083': 'value11642',
},
    {
    'id': 17527470565907,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Deborah Stevens',
    'address': '14655 Wilson Cliffs Suite 831\nWest Anthonyton, IN 68410',
    'text': 'That quite business require. Bag beat share north various raise. Ok choose throw hard difficult.\nEight rise tonight yes speak admit indeed notice. Me worker box black. Time never special history.',
    'email': 'vturner@example.com',
    'phone_number': '+1-981-393-6538',
    'json': {
    'name': 'Jacob Black',
    'address': '140 Mcconnell Manor Suite 211\nRangelbury, OR 19020',
},
    'key8745': 'value82687',
    'key77207': 'value12559',
    'key32207': 'value15423',
    'key47454': 'value43834',
    'key75378': 'value20954',
},
    {
    'id': 17527470565919,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Victoria Murphy',
    'address': '0040 Franco Pass\nJacobland, OR 93352',
    'text': 'Create several around. Believe plant already person administration main rule. Who or management business dinner high business.',
    'email': 'krausecaleb@example.net',
    'phone_number': '(632)803-0114',
    'json': {
    'name': 'Cindy Adkins',
    'address': '902 King Village Apt. 753\nSouth Joelborough, VI 80322',
},
    'key48349': 'value85845',
},
    {
    'id': 17527470565930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Thomas Wilson',
    'address': '898 James Shoals\nNorth Geoffreymouth, HI 40262',
    'text': 'Technology wind again hit. Star step position teacher. Return build walk learn relate.',
    'email': 'josephroberts@example.com',
    'phone_number': '4717427935',
    'json': {
    'name': 'Madeline Goodwin',
    'address': 'USNV Nelson\nFPO AA 86916',
},
    'key7590': 'value30701',
    'key78794': 'value95892',
    'key87828': 'value9970',
},
    {
    'id': 17527470565940,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michael Washington',
    'address': '21249 Farley Heights Apt. 789\nNorth Mindyburgh, TX 86391',
    'text': 'Interesting indicate him give. Difficult wonder history drop condition.\nSeries woman news lawyer. Make head hope author participant he.',
    'email': 'doylejacob@example.com',
    'phone_number': '(734)354-0583x2276',
    'json': {
    'name': 'Taylor Gomez',
    'address': '43046 John Alley Apt. 037\nSouth Sherri, ME 36637',
},
    'key25173': 'value81642',
    'key63924': 'value80372',
    'key564': 'value60064',
    'key69268': 'value31619',
},
    {
    'id': 17527470565951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Teresa Roberts',
    'address': '8914 Murphy Forges Apt. 040\nWest Jimmy, VT 78310',
    'text': 'Letter early amount strategy. Reflect happy good effect church piece. Coach religious election American treatment recognize school. Back set political any heart.',
    'email': 'christopher48@example.net',
    'phone_number': '(253)413-9209',
    'json': {
    'name': 'Michael Cooper',
    'address': '600 Carrie Keys\nNew Jasonmouth, PW 57120',
},
    'key71393': 'value27196',
    'key28913': 'value292',
    'key78710': 'value43791',
    'key40411': 'value34450',
    'key16912': 'value70417',
    'key94151': 'value92298',
    'key77986': 'value243',
},
    {
    'id': 17527470565961,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Kristina Carroll',
    'address': '62679 William Springs\nNorth David, MA 33518',
    'text': 'Capital meet environment walk why camera board. Night law list sort.\nFilm lose society avoid. School kind chance still even list. Trip play whole. At race hospital group.',
    'email': 'johnsonchristopher@example.net',
    'phone_number': '3578670118',
    'json': {
    'name': 'Bernard Frazier',
    'address': '7075 Rodriguez Plains Suite 756\nPort Lisamouth, NH 53968',
},
    'key81675': 'value70319',
    'key17399': 'value28938',
    'key92885': 'value23831',
    'key48471': 'value98663',
    'key75030': 'value26542',
    'key56909': 'value8956',
},
    {
    'id': 17527470565973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Autumn Spears',
    'address': '20176 Sara Islands\nRyantown, HI 54729',
    'text': 'Every both history especially place number. Factor such suggest. Pay huge produce bar month we star.\nIn nice upon friend behavior professional. Inside thing media for particularly.',
    'email': 'jennifer46@example.org',
    'phone_number': '303-923-2200x902',
    'json': {
    'name': 'Kayla Shaffer',
    'address': '27193 Mary Fork\nPort Joel, RI 43865',
},
    'key11586': 'value26732',
    'key18267': 'value87427',
    'key12909': 'value98345',
    'key93788': 'value25027',
    'key25072': 'value45058',
    'key26381': 'value77238',
    'key66356': 'value75865',
    'key69268': 'value92103',
},
    {
    'id': 17527470565983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Steven Leonard',
    'address': '2282 Sandra Square Apt. 671\nWest Alicefort, IA 43897',
    'text': 'Man other instead indeed quickly. One list special quickly care mean always else. Work rest high training.',
    'email': 'renee05@example.com',
    'phone_number': '883-731-5992x05787',
    'json': {
    'name': 'Kenneth Murphy',
    'address': '5412 Calvin Bypass\nAnthonyfurt, MI 74643',
},
    'key27091': 'value20932',
    'key22598': 'value44615',
},
    {
    'id': 17527470565992,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Stephanie Ellison',
    'address': '429 Tina Alley Apt. 307\nSouth Malik, IL 02817',
    'text': 'Wind only add mouth author almost hit much. Strategy anything like tough them he worker.\nStaff guy tell left. Improve method carry debate special. Year push rise section cut whatever everybody.',
    'email': 'smithjoseph@example.org',
    'phone_number': '887-279-9472',
    'json': {
    'name': 'John Riddle',
    'address': '24291 Jordan Rapid\nNorth Norma, TX 66067',
},
    'key31146': 'value16855',
    'key59759': 'value40723',
    'key67217': 'value65047',
    'key75157': 'value20647',
    'key76557': 'value69656',
    'key71051': 'value48580',
    'key22198': 'value25159',
},
    {
    'id': 17527470566003,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'David Sweeney',
    'address': '3430 Caitlin Burg Suite 513\nNorth Michele, ND 48041',
    'text': 'Tough assume beyond someone today degree. Democrat position defense. Son camera factor see own.\nHope want natural loss option them.',
    'email': 'rlong@example.net',
    'phone_number': '741-265-0332',
    'json': {
    'name': 'Donna Williams',
    'address': '6313 Brad Junctions\nLake Michael, UT 14053',
},
    'key4485': 'value14262',
    'key38004': 'value37686',
    'key48933': 'value18015',
    'key96336': 'value26756',
    'key25970': 'value22031',
    'key46687': 'value3885',
    'key35591': 'value14308',
    'key60693': 'value24813',
    'key29593': 'value61407',
},
    {
    'id': 17527470566014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Shelley Davis',
    'address': '973 Wood Rapids\nNortonland, AK 22651',
    'text': 'Beautiful small author skin.\nSchool appear same best once hold camera role. Although beat response appear whether. Adult fund owner hundred goal have bring.',
    'email': 'xthompson@example.net',
    'phone_number': '(481)973-6553x692',
    'json': {
    'name': 'Diana Wolf',
    'address': '365 Ayers Groves Apt. 278\nSouth Tammyshire, NM 32642',
},
    'key36583': 'value11492',
    'key55264': 'value45742',
    'key53424': 'value39863',
    'key59410': 'value65296',
    'key64839': 'value82081',
    'key68504': 'value44010',
    'key46623': 'value21827',
    'key69508': 'value12111',
    'key31794': 'value52803',
},
    {
    'id': 17527470566025,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Barbara Hill',
    'address': '53658 Sandoval Walks Suite 175\nCameronborough, NV 69426',
    'text': 'Understand week specific artist left total. Interest environment explain wife hope choice air.\nMessage court computer company theory nation particular. Outside meeting under also.',
    'email': 'breynolds@example.com',
    'phone_number': '+1-594-992-1100x997',
    'json': {
    'name': 'Heather Brown',
    'address': '272 Hannah Garden\nRobertland, NH 78947',
},
    'key15995': 'value31384',
    'key1333': 'value82621',
},
    {
    'id': 17527470566037,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Jonathan Thompson',
    'address': '7498 Susan Road\nJonathanbury, SC 82414',
    'text': 'Party bed discuss modern guess magazine song. Deal sing rather doctor pressure even.\nCost look management civil plant population. Tonight local beautiful through against indeed baby send.',
    'email': 'hortonmargaret@example.org',
    'phone_number': '295.543.3597x9248',
    'json': {
    'name': 'Stephanie Lewis',
    'address': 'USS Dominguez\nFPO AP 96728',
},
    'key44207': 'value13127',
    'key5385': 'value7175',
    'key39693': 'value49705',
    'key48914': 'value52459',
    'key37889': 'value12769',
},
    {
    'id': 17527470566046,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Paula Jacobs',
    'address': '52748 John Square\nSchmidttown, KY 31771',
    'text': 'Set nice wide ever.\nDraw attention call star agency pattern. Hundred state wait be area pressure within. Lose adult lose woman toward her huge.',
    'email': 'wmyers@example.net',
    'phone_number': '+1-327-754-7706x6164',
    'json': {
    'name': 'Brandy Sanchez',
    'address': '020 Phillip Villages Apt. 172\nDaviesmouth, RI 63349',
},
    'key77710': 'value17719',
    'key32005': 'value50508',
    'key67715': 'value6998',
    'key52754': 'value26170',
    'key30047': 'value70524',
    'key52847': 'value64990',
},
    {
    'id': 17527470566057,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Kathleen Bates',
    'address': '0549 Franklin Hill\nWest Kristen, MN 00731',
    'text': 'Pass hit wrong probably scene million. Street forget front agency strong those whole.\nPerform policy letter view her. Include who above hot yourself. Send positive newspaper before here society.',
    'email': 'pattoncody@example.com',
    'phone_number': '601-558-2268',
    'json': {
    'name': 'Dawn Hart',
    'address': '7256 Jones Flats Suite 894\nSouth Steven, HI 75425',
},
    'key66125': 'value73243',
    'key70689': 'value36634',
    'key77301': 'value69313',
    'key96302': 'value92775',
    'key59963': 'value27891',
},
    {
    'id': 17527470566069,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Christopher Perez',
    'address': '423 Joy Viaduct\nBrittanyborough, TX 83938',
    'text': 'Reveal friend north night quickly sign. Crime return rate image history work same morning.\nLow reality standard major let mention. Worry cold leave mean.',
    'email': 'joshua74@example.org',
    'phone_number': '739-223-0724',
    'json': {
    'name': 'James Johnson',
    'address': '1310 Renee Union\nJesseland, AS 20851',
},
    'key55006': 'value8907',
    'key36418': 'value78143',
},
    {
    'id': 17527470566079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Andrew Snyder',
    'address': 'Unit 8573 Box 9686\nDPO AE 05411',
    'text': 'Four live star talk without deep. Son force fact see culture. Cold during subject thus represent usually few newspaper.',
    'email': 'sandersnicole@example.com',
    'phone_number': '425-354-9355',
    'json': {
    'name': 'Isaac Dunlap',
    'address': 'PSC 5875, Box 0429\nAPO AP 83758',
},
    'key18963': 'value18944',
    'key306': 'value7983',
},
    {
    'id': 17527470566086,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Nathan Chase',
    'address': '450 Johnson Isle\nKimfort, VA 95828',
    'text': 'Reflect daughter get listen staff hair cost figure. Service major what assume total popular. Pay property rate.\nSome ability force card interesting. Ready continue range. Local continue small stock.',
    'email': 'nancy38@example.org',
    'phone_number': '(841)360-9486x6047',
    'json': {
    'name': 'Marie Martin',
    'address': '05190 Maria Squares\nNorth Max, DE 76716',
},
    'key23830': 'value23151',
    'key89260': 'value32559',
    'key89517': 'value82441',
    'key38376': 'value99355',
    'key9671': 'value72579',
    'key22844': 'value5374',
    'key27': 'value65986',
    'key39870': 'value89238',
    'key97553': 'value47007',
    'key22268': 'value37984',
},
    {
    'id': 17527470566097,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Danny Long',
    'address': 'PSC 2595, Box 8365\nAPO AE 03633',
    'text': 'State true scientist draw key father. Oil general other six quality interesting.\nWatch participant those station. Cause specific special above here. Majority leg behind everyone manager.',
    'email': 'smithmonica@example.net',
    'phone_number': '(905)512-5136',
    'json': {
    'name': 'Melinda Mckinney',
    'address': '010 Benjamin Bridge Suite 272\nLimouth, MA 39530',
},
    'key57090': 'value43236',
    'key56550': 'value82710',
    'key44789': 'value84516',
    'key55187': 'value81332',
    'key98302': 'value2403',
    'key46924': 'value20711',
    'key6062': 'value19886',
    'key93293': 'value16466',
},
    {
    'id': 17527470566107,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Linda Chen',
    'address': '1918 Joyce Meadows Apt. 586\nJoditon, NH 80923',
    'text': 'Speech else blood result girl enjoy none. American number line theory figure least case environment.\nSuffer able tree see firm. Community what less lawyer.',
    'email': 'martinbernard@example.com',
    'phone_number': '273-694-3545',
    'json': {
    'name': 'Debra Schroeder',
    'address': '584 Stafford Estate\nKyliemouth, IN 44087',
},
    'key37302': 'value13485',
},
    {
    'id': 17527470566118,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Tony Henson',
    'address': '3867 Morgan Neck\nNorth Robertview, OK 20655',
    'text': 'Entire wish attack cell rock both car up. Leader other wait begin not new. Wait recognize but stand manager past.',
    'email': 'nsmith@example.net',
    'phone_number': '901.287.7209x44396',
    'json': {
    'name': 'Donna Chavez',
    'address': '643 Vincent Springs Apt. 801\nSouth Shawntown, MS 32634',
},
    'key16593': 'value42183',
},
    {
    'id': 17527470566128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Rhonda Robertson',
    'address': '035 Anna Coves\nSouth Ashley, LA 38517',
    'text': 'Thought final fact director. Firm college study smile citizen able.\nWhile news change interesting course. White very amount history allow million become bad.',
    'email': 'morgananderson@example.com',
    'phone_number': '802-494-5234',
    'json': {
    'name': 'Brian Jones',
    'address': '038 Hubbard Extension\nLake Cindy, WA 54568',
},
    'key29797': 'value83103',
    'key21482': 'value89107',
    'key76411': 'value87118',
    'key79409': 'value23141',
    'key63006': 'value71001',
    'key91980': 'value28971',
    'key26543': 'value72606',
    'key44508': 'value22179',
    'key63667': 'value38487',
},
    {
    'id': 17527470566140,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Daniel Mcgee',
    'address': '374 Sanchez Drive\nNew Shawnberg, CT 94034',
    'text': 'Mouth go couple. Guy evidence group toward research son fact. Leader read student special environment be team.',
    'email': 'braddyer@example.net',
    'phone_number': '001-723-709-7567x563',
    'json': {
    'name': 'Christopher Huber',
    'address': 'PSC 5532, Box 0899\nAPO AA 13790',
},
    'key66942': 'value2326',
    'key56903': 'value30839',
    'key42414': 'value46383',
    'key2405': 'value51557',
    'key18100': 'value24443',
    'key36403': 'value41117',
    'key32729': 'value93066',
    'key98404': 'value9067',
    'key9628': 'value84465',
},
    {
    'id': 17527470566149,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Joshua Velazquez',
    'address': 'Unit 7615 Box 7028\nDPO AE 35785',
    'text': 'Practice car follow final provide south change. Most skill rich home.\nListen image new out. Remain hold partner character keep. Kind attack soldier raise.',
    'email': 'jeffreysweeney@example.net',
    'phone_number': '945.820.3335x608',
    'json': {
    'name': 'Rachael Cobb',
    'address': '6877 John Courts\nEast Jennifer, ND 28984',
},
    'key77557': 'value41939',
    'key63002': 'value32877',
    'key76767': 'value63863',
    'key41141': 'value39768',
    'key4191': 'value87293',
    'key90516': 'value53763',
    'key18360': 'value34083',
    'key54000': 'value43728',
},
    {
    'id': 17527470566158,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Michael Chan',
    'address': '15491 Ashley Path\nSouth Justin, GU 39525',
    'text': 'Experience structure back like care. Daughter PM small expert month trial back. Growth create blue outside yeah director good.',
    'email': 'grosscolton@example.net',
    'phone_number': '001-640-334-8193x84151',
    'json': {
    'name': 'Kelly Glass',
    'address': '8474 Julie Pines Suite 266\nSouth Dorothyburgh, MA 96089',
},
    'key7293': 'value8520',
    'key69825': 'value58423',
    'key70415': 'value97127',
    'key26935': 'value82664',
    'key34535': 'value60632',
    'key98099': 'value94907',
    'key2745': 'value72102',
    'key13118': 'value18734',
    'key87233': 'value59784',
},
    {
    'id': 17527470566169,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Eric Horton',
    'address': '32643 Andrew Mountains\nAmandamouth, FM 78058',
    'text': 'Drug begin model account management though none. Same late entire nothing bit against hope.\nEvent concern cost open day peace state. Cultural bar before marriage red.',
    'email': 'perezvictoria@example.net',
    'phone_number': '001-729-398-7171x65384',
    'json': {
    'name': 'Philip Carter',
    'address': '065 Grant Forest Apt. 782\nMichaeltown, IN 61674',
},
    'key34536': 'value8713',
    'key58029': 'value22510',
    'key66079': 'value36324',
    'key49328': 'value12440',
},
    {
    'id': 17527470566180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Caleb Reed',
    'address': '50660 Matthew Shoal\nSarahfort, ID 53740',
    'text': 'Short happy high executive language only American. Fill adult agreement social necessary truth. Six eye vote amount.\nAvailable owner three general way. Thank firm value attack.',
    'email': 'david14@example.com',
    'phone_number': '+1-494-453-2059x4797',
    'json': {
    'name': 'Allison Phillips',
    'address': '20580 Williams Greens\nCampbellview, MD 34513',
},
    'key45557': 'value1265',
    'key62427': 'value12551',
    'key6739': 'value44864',
    'key78321': 'value19364',
    'key78095': 'value51419',
},
    {
    'id': 17527470566190,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Nicholas Vega',
    'address': '0691 Tony Mews Suite 941\nPort Rachelview, PA 91164',
    'text': 'Huge personal these end. Hour approach return beautiful how for.\nDoctor boy age world increase make myself. Do style recognize serious wait election movie.\nBag no Congress bring.',
    'email': 'alvaradojohn@example.com',
    'phone_number': '689.673.0134x6902',
    'json': {
    'name': 'Jill Peterson',
    'address': '55269 Macias Rest Apt. 575\nSouth Davidland, MT 31813',
},
    'key21855': 'value31600',
    'key85140': 'value55220',
    'key34008': 'value96427',
    'key28922': 'value18780',
    'key25975': 'value5901',
    'key12908': 'value62152',
    'key28871': 'value65850',
    'key61197': 'value45734',
    'key18801': 'value90827',
},
    {
    'id': 17527470566202,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Carol Hess',
    'address': '733 Jason Camp Suite 540\nNorth Nicoleland, VA 85473',
    'text': 'Across her hotel manage reality. Six head third suggest life admit. Move region book.\nWord wife will sell serve. Show have population kind local public wide without.',
    'email': 'albert41@example.net',
    'phone_number': '514.904.6873x5585',
    'json': {
    'name': 'Douglas Ingram',
    'address': '7250 Yates Street\nKimberlyborough, MI 76492',
},
    'key55000': 'value73123',
    'key57454': 'value32376',
},
    {
    'id': 17527470566212,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Glen Taylor',
    'address': '199 Sara Heights\nPort Ashleeside, WI 53873',
    'text': 'Carry program deal decide certain sister red decade. Perhaps clear training campaign effort loss avoid us.',
    'email': 'john92@example.com',
    'phone_number': '840.991.1396',
    'json': {
    'name': 'Angela Robles',
    'address': '23733 Valerie Forge Suite 536\nPort Samantha, MT 12784',
},
    'key47584': 'value29890',
    'key74452': 'value50003',
    'key73917': 'value14676',
    'key13156': 'value36736',
},
    {
    'id': 17527470566222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Gina Williams',
    'address': '2065 Lynn Overpass Suite 737\nNorth Jennifer, NH 96557',
    'text': 'Woman owner mean than speak pattern they cause.\nIt season consider her activity. Son toward suddenly move accept.',
    'email': 'james05@example.com',
    'phone_number': '001-377-754-4015',
    'json': {
    'name': 'Michelle Grimes',
    'address': '515 Burke Prairie Apt. 653\nEast Megan, DC 46209',
},
    'key40858': 'value26774',
    'key56319': 'value74541',
    'key82368': 'value62998',
},
    {
    'id': 17527470566232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Laura Mueller',
    'address': '5851 Betty Drive Apt. 327\nPort Anaton, IL 13432',
    'text': 'Stock approach few power writer five. Buy may spring body under cause account.',
    'email': 'morriskenneth@example.org',
    'phone_number': '+1-277-928-3459x68250',
    'json': {
    'name': 'Joe Chambers',
    'address': '932 Donald Expressway\nRodriguezstad, MS 79490',
},
    'key53185': 'value25274',
    'key43199': 'value89607',
    'key17391': 'value35501',
    'key45674': 'value83525',
},
    {
    'id': 17527470566243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Bryan Maxwell',
    'address': '96628 Edward Mount\nEast Timothy, GA 92527',
    'text': 'Future sea minute fine accept. Speech in cause when. Those own car anyone event staff today.',
    'email': 'amandaterry@example.com',
    'phone_number': '+1-683-861-2799x44957',
    'json': {
    'name': 'Cheryl Washington',
    'address': '7673 Snyder Creek Apt. 577\nSouth Nicholasborough, GA 40535',
},
    'key65087': 'value15423',
    'key49459': 'value78251',
    'key1778': 'value43174',
    'key34580': 'value96130',
    'key96996': 'value71916',
    'key40324': 'value59394',
    'key90916': 'value56225',
    'key62371': 'value35304',
    'key56909': 'value53405',
},
    {
    'id': 17527470566255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'James Gray',
    'address': '2607 Jacobs Creek Apt. 847\nJohnsonfurt, DC 09777',
    'text': 'Ready sometimes plan production various. Think what carry out do. Big response tough great.',
    'email': 'heather16@example.org',
    'phone_number': '7557468303',
    'json': {
    'name': 'Tina Robinson',
    'address': 'USNS Sawyer\nFPO AP 10133',
},
    'key65': 'value64384',
    'key29834': 'value77258',
    'key98807': 'value33187',
    'key954': 'value73351',
    'key24429': 'value35685',
    'key99688': 'value84447',
},
    {
    'id': 17527470566264,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Frederick Ramirez',
    'address': '3551 Jimmy Throughway Suite 106\nCoryland, OK 02720',
    'text': 'Spring television dark particular instead including. During own land agent despite people agent. Member simply option assume product campaign lose.',
    'email': 'johnanderson@example.com',
    'phone_number': '(883)414-2468',
    'json': {
    'name': 'Kyle Moore',
    'address': '863 Joseph Rest\nMaxwellfurt, HI 05079',
},
    'key66650': 'value88621',
    'key35317': 'value4722',
    'key24440': 'value73026',
    'key23051': 'value14815',
    'key71736': 'value68796',
    'key13720': 'value30543',
    'key16305': 'value15408',
    'key69518': 'value56581',
},
    {
    'id': 17527470566275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Heather Long',
    'address': '1910 Hughes Hollow\nNew Tiffanyburgh, WV 64165',
    'text': 'Stuff heavy that movement here scientist challenge. Director after billion.\nNone process charge whose score save quality. Ok require practice beat. Message red ago.',
    'email': 'ricky48@example.net',
    'phone_number': '(578)862-2739',
    'json': {
    'name': 'Heather Barnett',
    'address': '962 Calderon Streets\nWest Victoriaburgh, AS 63132',
},
    'key1664': 'value50710',
    'key59604': 'value22695',
    'key70785': 'value86410',
},
    {
    'id': 17527470566286,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Dennis Duran',
    'address': '682 Brandy Squares Suite 954\nNew Jacobville, ND 16161',
    'text': 'Low one history. Situation item task lot product authority.\nDegree go same red ahead.\nMoney behavior city hair. Week tend common message I front matter past. Small difficult all return each air.',
    'email': 'singhlinda@example.org',
    'phone_number': '(688)991-3712x167',
    'json': {
    'name': 'Heather Wong',
    'address': '5196 David Drives Suite 762\nNorth Lydiaview, SD 84432',
},
    'key789': 'value95862',
    'key46799': 'value12131',
    'key71227': 'value15135',
},
    {
    'id': 17527470566297,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Cheryl Morris',
    'address': 'USNS Newman\nFPO AE 47231',
    'text': 'Itself skin quite best yard. Bag system be top hotel public.\nAffect least minute responsibility yes wear statement. American last nation home work blood suddenly door.',
    'email': 'laguirre@example.org',
    'phone_number': '893.547.9029',
    'json': {
    'name': 'Mark Rivera',
    'address': '0107 Regina Gateway\nSouth Nicholas, MS 29236',
},
    'key16804': 'value76193',
    'key65037': 'value62498',
    'key69405': 'value65330',
    'key61236': 'value19000',
    'key36149': 'value72165',
},
    {
    'id': 17527470566307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Michael Nelson',
    'address': 'USS Todd\nFPO AP 57107',
    'text': 'Human practice near firm daughter. Understand prove make occur huge see.\nAgainst young member western moment yet. Thought long form pay by manage note. Science everybody card water at night.',
    'email': 'jesus10@example.net',
    'phone_number': '001-412-252-0562x04392',
    'json': {
    'name': 'Kristin Miller',
    'address': '0356 Monroe Groves\nSouth Maryton, VA 27276',
},
    'key17550': 'value91212',
},
    {
    'id': 17527470566316,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Levi Hill',
    'address': '668 Hill Ports Suite 149\nLake Claudiaside, MS 36559',
    'text': 'Political effect including raise treat note wonder source. Anything any dream either hour. First tell son drug evening life and claim.',
    'email': 'christophercooper@example.net',
    'phone_number': '+1-473-216-6855x44354',
    'json': {
    'name': 'Jason Parker',
    'address': '771 Steven Locks\nNew Danielhaven, OH 61293',
},
    'key53177': 'value38556',
    'key5164': 'value78271',
    'key92775': 'value67227',
    'key91332': 'value58439',
},
    {
    'id': 17527470566327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Michele Walker',
    'address': '258 Michael Fort Suite 036\nLake Tonyshire, RI 92877',
    'text': 'Investment true rich Congress. Team police question result.\nConcern difference without fall. Whose support five discuss police produce. Wide too enter fine a challenge.',
    'email': 'sandersbruce@example.com',
    'phone_number': '530.796.4594',
    'json': {
    'name': 'Laura Gallagher',
    'address': '41490 Bethany Circle\nWoodshire, CO 73349',
},
    'key61401': 'value9995',
    'key73225': 'value9222',
    'key25909': 'value76280',
    'key14195': 'value31333',
},
    {
    'id': 17527470566339,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Larry Meyer',
    'address': '384 Mcneil Via\nSouth Jamesville, LA 15925',
    'text': 'Would write happy month but range. Condition must research turn such everything.\nAlready center writer bed thought number. Summer her head common style view. Land type before last already no.',
    'email': 'amandaburns@example.net',
    'phone_number': '(391)361-6752x165',
    'json': {
    'name': 'Andrea Flores',
    'address': '780 Robert Ranch\nWest Courtney, VA 78261',
},
    'key83197': 'value96651',
    'key44920': 'value12408',
    'key25830': 'value54395',
    'key39524': 'value45041',
    'key57448': 'value37982',
    'key40743': 'value43675',
    'key6804': 'value11832',
    'key8999': 'value45972',
    'key30078': 'value71978',
},
    {
    'id': 17527470566350,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Troy Alvarez',
    'address': 'PSC 4781, Box 6578\nAPO AA 04041',
    'text': 'Million either process mention. On top role one government area. Window for all despite public them staff word. Budget really hand offer.',
    'email': 'usmith@example.net',
    'phone_number': '320-948-1142x7930',
    'json': {
    'name': 'John Gonzales',
    'address': '17722 Hill Glens Suite 674\nDeniseport, AS 21264',
},
    'key10038': 'value78780',
},
    {
    'id': 17527470566359,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Timothy Carroll',
    'address': '603 John Union\nEast Jeremy, PW 88631',
    'text': 'Determine character training trip. East only eye magazine summer.',
    'email': 'larrydavis@example.net',
    'phone_number': '+1-650-718-3499x7520',
    'json': {
    'name': 'Ellen Thompson',
    'address': '5392 Colleen Estates Apt. 787\nPort Sheilafort, TX 48431',
},
    'key66102': 'value25805',
    'key86207': 'value55487',
    'key92101': 'value25969',
},
    {
    'id': 17527470566369,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Michelle Melton',
    'address': '7784 Dylan Courts\nBrewertown, CO 65569',
    'text': 'Argue conference sort statement worker. News best what owner fund attack. Himself number determine current.',
    'email': 'johnsonnicholas@example.org',
    'phone_number': '(497)413-5276x7976',
    'json': {
    'name': 'Zachary Jackson DDS',
    'address': '98179 Jones Heights\nMullinsmouth, ND 48313',
},
    'key51093': 'value13034',
    'key74481': 'value52402',
},
    {
    'id': 17527470566381,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Traci Tran',
    'address': '46858 Herrera Camp Suite 019\nCraigfurt, KY 46422',
    'text': 'Scene shoulder special individual role ok. Plant lose health positive people national thought tough.',
    'email': 'tracigarcia@example.net',
    'phone_number': '(903)689-6750x442',
    'json': {
    'name': 'Bobby Jackson',
    'address': '15433 Cortez Curve Suite 409\nGordonview, AK 54186',
},
    'key68131': 'value10332',
    'key33333': 'value76174',
    'key58376': 'value41691',
    'key18970': 'value62009',
    'key6239': 'value46004',
    'key37095': 'value79365',
    'key17005': 'value13692',
    'key27476': 'value71694',
    'key35435': 'value53004',
},
    {
    'id': 17527470566393,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'David Shields',
    'address': '671 Ruth Village Suite 073\nMccormickville, IL 41965',
    'text': 'Certainly include wall media great course project. Operation floor kind gas likely as.\nEver choice value. None suggest sea base. Result father health including its.',
    'email': 'garciajacqueline@example.org',
    'phone_number': '+1-808-220-5151x1243',
    'json': {
    'name': 'Vincent Blevins',
    'address': '6368 Kristina Skyway Apt. 621\nNorth Pamelamouth, AL 71582',
},
    'key93766': 'value14471',
    'key38954': 'value10635',
    'key30790': 'value5170',
    'key13345': 'value88685',
    'key71592': 'value58899',
    'key27241': 'value82302',
    'key82616': 'value6682',
    'key54282': 'value12090',
},
    {
    'id': 17527470566405,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Jean Powell',
    'address': '168 Perry Locks\nDouglasburgh, ME 41129',
    'text': 'Thousand cup security professor. Reveal create act candidate will type.\nHis establish red fast. Affect always any buy. Budget machine impact book receive beat husband.',
    'email': 'rhernandez@example.org',
    'phone_number': '(594)702-2501',
    'json': {
    'name': 'Robert Richardson',
    'address': '24954 Jasmine Underpass\nNew Brandon, OK 45512',
},
    'key78228': 'value15560',
    'key80930': 'value30404',
    'key3024': 'value94223',
    'key69704': 'value18583',
    'key72103': 'value89385',
    'key26741': 'value66396',
    'key16479': 'value39024',
    'key92911': 'value30279',
},
    {
    'id': 17527470566415,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Elizabeth Horn',
    'address': '6429 Donna Mews Suite 514\nParkerton, ND 59500',
    'text': 'Then best chair put within minute baby. When push far never friend often.\nPolitical travel not same exist red office. Concern institution day race. Great trouble money well manager.',
    'email': 'richardestrada@example.org',
    'phone_number': '504-988-3619x30882',
    'json': {
    'name': 'Mary Martin',
    'address': '7029 Tom Ports Suite 582\nEast Tammy, DC 78988',
},
    'key18943': 'value36254',
    'key65887': 'value75374',
    'key58029': 'value24093',
    'key54719': 'value79541',
    'key59529': 'value95014',
    'key61873': 'value93806',
},
    {
    'id': 17527470566427,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Jennifer Mcgee',
    'address': '97757 Griffin Pike\nPort Sallyport, FL 97045',
    'text': 'Thousand stand no sound body school. At minute space produce ground.\nPick career discussion responsibility dinner think. Agency later girl say political. North anyone machine force discussion.',
    'email': 'angeljohnson@example.org',
    'phone_number': '(890)318-4266x33258',
    'json': {
    'name': 'Karen Petersen',
    'address': '0584 Hayes Unions\nSabrinaville, NH 13284',
},
    'key54850': 'value26128',
    'key18423': 'value19429',
    'key56590': 'value46624',
    'key91795': 'value65136',
},
    {
    'id': 17527470566438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Amanda Roach',
    'address': '863 Morrison Ranch\nMorganfurt, MA 59270',
    'text': 'Magazine often charge check positive. Key show mouth wind. Story audience space where human appear miss.',
    'email': 'ryanconrad@example.net',
    'phone_number': '001-715-305-8191x61854',
    'json': {
    'name': 'Mr. Larry Harris MD',
    'address': '8342 Bowman Trace\nBairdfurt, NV 44725',
},
    'key64455': 'value71101',
    'key16201': 'value74873',
    'key74801': 'value14930',
    'key72411': 'value11924',
    'key8874': 'value62101',
    'key35995': 'value52756',
    'key32185': 'value81163',
    'key6460': 'value30544',
    'key31968': 'value1766',
    'key60670': 'value23257',
},
    {
    'id': 17527470566450,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Amanda Smith',
    'address': '290 Conrad Brooks\nNew Evelynmouth, GU 53526',
    'text': 'War let night other. Mind truth realize lead reveal responsibility. Maintain specific should thing talk.',
    'email': 'christinahill@example.com',
    'phone_number': '861.820.9152',
    'json': {
    'name': 'Katie Lynch',
    'address': '1869 Krause Rue Apt. 090\nLake Richard, MN 84347',
},
    'key92133': 'value42842',
    'key31985': 'value6242',
    'key78900': 'value97732',
    'key72378': 'value49476',
    'key56800': 'value9181',
    'key69221': 'value92622',
    'key19844': 'value53073',
    'key76932': 'value35264',
},
    {
    'id': 17527470566462,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Amber Horton',
    'address': '0982 Sanchez Mountains\nWalkerland, WV 04293',
    'text': 'Training design suffer each. Different environmental risk fight movement lead.\nHusband common truth understand owner. Much culture fill southern so order we.',
    'email': 'jessicacrosby@example.org',
    'phone_number': '748.356.6908',
    'json': {
    'name': 'Thomas Walker',
    'address': '79621 Mercado Station Apt. 482\nRobinsonberg, WI 48305',
},
    'key50904': 'value60645',
    'key93023': 'value25509',
    'key46503': 'value60941',
    'key20886': 'value17570',
    'key73730': 'value84174',
    'key29920': 'value41761',
},
    {
    'id': 17527470566474,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Daniel Carter',
    'address': '930 Cooper Village\nLewishaven, CT 52551',
    'text': 'Make million follow.\nCondition eight training thought last someone. Paper imagine who know season.',
    'email': 'cantudavid@example.com',
    'phone_number': '001-603-398-8739x297',
    'json': {
    'name': 'Mr. Joe Williams',
    'address': '868 Thomas Green\nMatthewtown, ID 34495',
},
    'key2556': 'value72877',
    'key33669': 'value73666',
    'key8772': 'value71304',
    'key11808': 'value44646',
    'key45930': 'value27192',
    'key51271': 'value98983',
    'key44034': 'value42382',
    'key78381': 'value76274',
},
    {
    'id': 17527470566485,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Tiffany Best',
    'address': '117 Wendy Flats\nTammyfort, PW 72215',
    'text': 'Fine seem discuss her mission pick. Spring card member foreign door meeting road. Claim agreement help sit when office help.',
    'email': 'brownstephen@example.org',
    'phone_number': '(678)926-0908',
    'json': {
    'name': 'Crystal Wilkins',
    'address': '9229 Rodriguez Square\nPattersonland, AZ 84910',
},
    'key41389': 'value24146',
    'key37756': 'value85119',
    'key56756': 'value23634',
    'key93800': 'value31797',
    'key49653': 'value47632',
    'key35839': 'value30604',
    'key74561': 'value90146',
    'key72140': 'value37337',
    'key42861': 'value9077',
    'key76265': 'value56009',
},
    {
    'id': 17527470566496,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Amber Lucas',
    'address': '966 Smith Circle\nMorrisland, CO 58474',
    'text': 'Class three piece while travel moment.\nRaise government foot what. Brother ask night someone news list billion.\nCell paper anything head. Style walk sea hard. Talk economy risk far stand bag.',
    'email': 'jacquelinehernandez@example.net',
    'phone_number': '933.204.6050x319',
    'json': {
    'name': 'Brian Guzman',
    'address': 'PSC 7663, Box 6422\nAPO AA 76986',
},
    'key61093': 'value29652',
},
    {
    'id': 17527470566506,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Lisa Miller',
    'address': '91879 James Ford\nWalshfort, IA 83682',
    'text': 'Door establish benefit boy finally kid. Forward crime hear ten relationship pattern. History attorney evidence door.',
    'email': 'melissa36@example.org',
    'phone_number': '001-305-231-6603x5005',
    'json': {
    'name': 'Barry Ortiz',
    'address': '9677 Carey Ridges\nThompsonborough, MS 21769',
},
    'key48016': 'value49505',
    'key18106': 'value90215',
    'key17386': 'value68538',
},
    {
    'id': 17527470566516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Christopher Wong',
    'address': '20433 Andrew Ranch\nHuntville, TX 53031',
    'text': 'General certain pass people hit ok. Yet difference us join conference game.\nReturn material range near side.',
    'email': 'tjordan@example.com',
    'phone_number': '+1-223-209-3460x80775',
    'json': {
    'name': 'Deanna Macdonald',
    'address': '1192 Samantha Union\nCarlastad, AL 74095',
},
    'key48916': 'value98976',
    'key20364': 'value52672',
},
    {
    'id': 17527470566527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Michael Lewis',
    'address': '57013 Suarez Stravenue Suite 923\nPort Andrewborough, GU 94372',
    'text': 'Free involve speech him treatment into. Stuff political behavior science.\nFoot visit firm economy whole beautiful set.\nBig least worry woman wish. Yard list store management official radio pass.',
    'email': 'martinezfaith@example.com',
    'phone_number': '+1-252-364-7433x19352',
    'json': {
    'name': 'Haley Andersen',
    'address': '805 Kara Dale Apt. 504\nLake Joseph, VA 53611',
},
    'key73520': 'value38180',
    'key70596': 'value78555',
    'key55801': 'value5241',
    'key2039': 'value33857',
    'key40042': 'value49707',
    'key87525': 'value7299',
    'key18601': 'value99208',
    'key23819': 'value81336',
    'key87735': 'value88523',
    'key38647': 'value30588',
},
    {
    'id': 17527470566539,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Kevin Rojas',
    'address': '998 John Fork Suite 329\nCarlberg, RI 15574',
    'text': 'Whether culture strategy pressure artist stand east. Couple resource TV I month. Television peace site responsibility tree line back conference.',
    'email': 'burtonelijah@example.com',
    'phone_number': '515-586-8142x52513',
    'json': {
    'name': 'Joseph Montoya',
    'address': 'Unit 8520 Box 0992\nDPO AA 21656',
},
    'key5886': 'value18168',
    'key99999': 'value12360',
    'key38309': 'value98978',
    'key59368': 'value66337',
},
    {
    'id': 17527470566548,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Michael May',
    'address': '0117 Cindy Estate Apt. 430\nYesenialand, TN 95907',
    'text': 'Town crime position rise positive environment until west. Walk race no stop just. Mouth indeed hair step forget show nice.',
    'email': 'ztucker@example.com',
    'phone_number': '(842)760-1422',
    'json': {
    'name': 'Lynn Harris',
    'address': '4629 Anderson Land\nNew Robertmouth, MS 22628',
},
    'key14133': 'value74092',
},
    {
    'id': 17527470566558,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Jonathan Ortega',
    'address': 'Unit 8913 Box 9256\nDPO AE 64920',
    'text': 'Pattern memory change house accept. Increase receive long break. Seven street lose approach mind.\nBuy seek hand serve style. Eat wonder be worker.',
    'email': 'david57@example.net',
    'phone_number': '001-991-905-6566x57718',
    'json': {
    'name': 'Sarah Fisher',
    'address': '0310 Romero Lake Apt. 413\nHansenmouth, WA 09530',
},
    'key86199': 'value13545',
    'key82796': 'value86075',
    'key73399': 'value7752',
    'key11966': 'value59044',
    'key6537': 'value92948',
    'key69474': 'value13411',
    'key8453': 'value60839',
    'key64892': 'value73987',
    'key15304': 'value85189',
},
    {
    'id': 17527470566567,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Thomas King DVM',
    'address': '107 Tommy Squares\nWilsonshire, ME 40322',
    'text': 'Camera over evening century. I require tough goal event. Fast on must peace myself lay white.\nWhether large guess particular peace beautiful public. Whether manage old single.',
    'email': 'rebeccamorris@example.org',
    'phone_number': '662.594.8419x34920',
    'json': {
    'name': 'Richard Kramer',
    'address': '182 Kenneth Junctions\nCastroview, MT 25294',
},
    'key31334': 'value9050',
    'key48563': 'value7656',
    'key24303': 'value16918',
    'key37846': 'value28415',
    'key89650': 'value69075',
    'key6870': 'value55264',
    'key34151': 'value29077',
    'key29204': 'value28631',
    'key88911': 'value74540',
},
    {
    'id': 17527470566578,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Debra Paul',
    'address': 'Unit 5975 Box 6312\nDPO AE 86733',
    'text': 'These American attention the mother national table. Look actually seat mission.\nWhich partner develop himself there hit finally.\nTrade everyone full machine. Help focus we three on parent million.',
    'email': 'james49@example.net',
    'phone_number': '(754)945-5085',
    'json': {
    'name': 'Jermaine Rodriguez',
    'address': '466 Brittany Lakes Suite 621\nManningmouth, NY 13138',
},
    'key9285': 'value96651',
},
    {
    'id': 17527470566587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Kimberly Farley',
    'address': '685 Maxwell Row\nEast Don, NJ 00833',
    'text': 'Husband affect someone send view. Through past itself follow.\nOpen shake maintain live through. Finish attorney budget discuss bed right.',
    'email': 'tjacobson@example.net',
    'phone_number': '574.514.3944x869',
    'json': {
    'name': 'Sandra Gonzalez',
    'address': '643 Michelle Plains Apt. 490\nWilliammouth, MO 42696',
},
    'key47681': 'value14230',
    'key91206': 'value97114',
    'key13488': 'value39615',
    'key56029': 'value38736',
},
    {
    'id': 17527470566597,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Kyle York',
    'address': '4722 Raymond Drives Apt. 398\nNorth Bethland, MN 46711',
    'text': 'Citizen amount couple which choose lot. Popular ball imagine national. Must involve president campaign Mr listen remember situation.\nEvent very six determine same style. Stay once himself nature Mr.',
    'email': 'mmays@example.com',
    'phone_number': '+1-450-217-0906x167',
    'json': {
    'name': 'Peter Buck',
    'address': '374 Richard Plains Apt. 902\nSouth Jasonfort, MA 73281',
},
    'key37777': 'value23598',
    'key77666': 'value15200',
    'key20065': 'value48235',
    'key27644': 'value80994',
    'key46747': 'value67136',
    'key14363': 'value70847',
},
    {
    'id': 17527470566608,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Jennifer Barr',
    'address': 'PSC 7253, Box 8732\nAPO AA 24702',
    'text': 'Experience forward total risk piece. Reason away manager soldier hard attorney. Indeed present win professor raise.',
    'email': 'hharris@example.org',
    'phone_number': '001-466-283-2854',
    'json': {
    'name': 'Heather Garcia',
    'address': '2025 Brown Loop Suite 706\nStephaniefort, KS 79544',
},
    'key89798': 'value66723',
    'key13699': 'value39191',
    'key11462': 'value98068',
    'key91656': 'value25903',
    'key41333': 'value81677',
},
    {
    'id': 17527470566617,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Brian Ruiz',
    'address': '668 Johnson Road\nKatherinefort, MS 50170',
    'text': 'Degree interest person smile. Debate design method fund chance. Raise war decade check nation.',
    'email': 'carolyn75@example.org',
    'phone_number': '(252)332-4238x9111',
    'json': {
    'name': 'Joseph Perez',
    'address': '48159 Kemp Fall\nRoberthaven, OR 95530',
},
    'key30505': 'value17506',
    'key81467': 'value23155',
    'key13239': 'value51493',
    'key21981': 'value82186',
    'key49434': 'value24769',
    'key64771': 'value19760',
    'key74165': 'value35640',
    'key21689': 'value69962',
    'key40750': 'value49553',
    'key87927': 'value42273',
},
    {
    'id': 17527470566627,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Angela Holden',
    'address': '104 Martinez Cove\nPort Gary, GA 54106',
    'text': 'Person two early choice weight. Above save like bag different.\nAway travel reach free safe than lay even. Thought thought whatever few modern these. Scientist campaign early value.',
    'email': 'kgonzalez@example.com',
    'phone_number': '(360)480-5608x2514',
    'json': {
    'name': 'Jeffrey Brewer',
    'address': '3959 Montgomery Gateway\nSteinton, GU 64169',
},
    'key85315': 'value90306',
    'key82676': 'value27718',
    'key89303': 'value1934',
    'key98333': 'value47704',
    'key34584': 'value87283',
    'key27092': 'value97049',
    'key39045': 'value4157',
},
    {
    'id': 17527470566638,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Joe Anderson MD',
    'address': '492 Lisa Inlet Apt. 913\nLake Wandahaven, KY 54233',
    'text': 'Speech pay listen. Guy minute four million any. We matter bad their military under.\nNature father run TV memory sometimes recent share. Environmental yet time try huge close trouble.',
    'email': 'debraallison@example.org',
    'phone_number': '759-403-1932',
    'json': {
    'name': 'Rebecca Swanson',
    'address': '666 Kyle Bridge\nPort Adam, AR 59709',
},
    'key17430': 'value53344',
    'key73023': 'value76724',
    'key57941': 'value893',
    'key96354': 'value88246',
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
        """测试请求 3 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '50c23c9c-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_50_491151yWWFeQhJ',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_query_vector_by_sdk_1752747061.json')
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
    test = AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulQueryVectorBySdk1752747061Json()
    test.run_tests()
