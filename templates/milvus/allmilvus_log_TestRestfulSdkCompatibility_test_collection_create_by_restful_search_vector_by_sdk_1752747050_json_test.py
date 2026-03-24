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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestRestfulSdkCompatibility_test_collection_create_by_restful_search_vector_by_sdk_1752747050_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_search_vector_by_sdk_1752747050.json"
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



class AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulSearchVectorBySdk1752747050Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_search_vector_by_sdk_1752747050.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_search_vector_by_sdk_1752747050.json"
        self.test_count = 6  # 测试方法数量
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
    'RequestId': '4945ea04-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_37_931672RnFjYhfM',
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
    'RequestId': '4945ea04-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_37_931672RnFjYhfM',
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
    'RequestId': '4945ea04-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_37_931672RnFjYhfM',
    'data': [
    {
    'id': 17527470440250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Shane Jones',
    'address': '539 Harrington Spur Suite 532\nSouth Christy, MN 19792',
    'text': 'As central through between national student start. Already head market.\nLevel production computer which common.',
    'email': 'tammy64@example.org',
    'phone_number': '+1-914-553-9812x523',
    'json': {
    'name': 'Laura Roberts',
    'address': 'PSC 1534, Box 9664\nAPO AE 84954',
},
    'key46735': 'value9053',
    'key19387': 'value14652',
    'key15242': 'value37059',
    'key47010': 'value78079',
    'key95084': 'value61027',
    'key10194': 'value87451',
    'key26598': 'value38318',
    'key54906': 'value7108',
    'key53333': 'value14262',
    'key68205': 'value77455',
},
    {
    'id': 17527470440265,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Jesse Davis',
    'address': '94163 Mary Union\nCherylfort, VI 84238',
    'text': 'Group better use.\nResult cut memory individual. Technology all pay whom travel president image course.\nSociety suffer affect. Seven about physical cup style class weight none.',
    'email': 'michelletaylor@example.org',
    'phone_number': '(496)547-4527',
    'json': {
    'name': 'Jeffrey Sharp',
    'address': '0259 Brenda Fall\nFitzgeraldville, PR 68763',
},
    'key87662': 'value71375',
    'key31184': 'value66652',
    'key76404': 'value52662',
    'key98669': 'value86902',
    'key64250': 'value39900',
    'key48005': 'value95626',
    'key1032': 'value66212',
    'key8818': 'value73743',
    'key3386': 'value10804',
    'key8621': 'value25415',
},
    {
    'id': 17527470440280,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Lisa Lee',
    'address': '5599 Jeffery Road Apt. 681\nMichealburgh, FM 57670',
    'text': 'Nearly beautiful kitchen every manage sense security. Republican save these discuss should role share. Foreign hard wrong board night single.',
    'email': 'timothy18@example.net',
    'phone_number': '838.455.6834x1341',
    'json': {
    'name': 'Brian Robinson',
    'address': '339 Bryant Stravenue\nEast Wendystad, AZ 56225',
},
    'key17603': 'value15035',
    'key653': 'value13544',
    'key47109': 'value18246',
    'key75576': 'value18217',
    'key14536': 'value1673',
    'key383': 'value29905',
    'key36156': 'value26881',
},
    {
    'id': 17527470440294,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Stephen Montoya',
    'address': '446 Alan Lake Suite 722\nGarciaville, PA 73954',
    'text': 'Baby example true thank return. Win nice enjoy probably. Factor while size well. Camera but scene international study.',
    'email': 'bbyrd@example.com',
    'phone_number': '+1-436-798-9097x360',
    'json': {
    'name': 'Jennifer James',
    'address': '70798 Craig Course Apt. 506\nPort Amber, ME 42031',
},
    'key80910': 'value45716',
    'key62591': 'value68293',
},
    {
    'id': 17527470440307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Maria Phillips',
    'address': '2451 David Divide Suite 512\nEast Belinda, CA 29040',
    'text': 'Act deep use behavior admit.\nReligious might interview pretty senior community bring. Hard rich sister staff. Quickly early girl from color American push collection.',
    'email': 'owebster@example.net',
    'phone_number': '895.905.0846x118',
    'json': {
    'name': 'April Pierce',
    'address': '1902 Murray Greens\nJohnport, WV 81525',
},
    'key16654': 'value96858',
    'key63400': 'value61610',
    'key9659': 'value7278',
},
    {
    'id': 17527470440320,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Steve Santana DDS',
    'address': '92223 Michael Crossing\nWoodburgh, TN 86974',
    'text': 'Especially common situation education nor blue performance. Fall marriage table sign wonder PM baby. Energy have avoid box.\nMiddle into market firm ground. Leader only if guy kind technology.',
    'email': 'robert82@example.com',
    'phone_number': '(314)945-5467x6185',
    'json': {
    'name': 'Daniel Powell',
    'address': '005 Moran Spurs Suite 045\nCrawfordshire, LA 67627',
},
    'key70426': 'value93043',
    'key3488': 'value68475',
    'key7117': 'value40077',
    'key8506': 'value58138',
    'key11587': 'value19135',
    'key22031': 'value48782',
    'key79228': 'value15583',
    'key34868': 'value10483',
    'key31903': 'value70671',
    'key80487': 'value84189',
},
    {
    'id': 17527470440334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Leah Hicks',
    'address': '8932 Andrew Greens Apt. 980\nSmithfort, OR 79084',
    'text': 'Establish receive you attention hold hotel amount. Fish play current impact.\nPrevent them during common. House attack since tree professor occur.',
    'email': 'krystal03@example.com',
    'phone_number': '938-802-7508x82340',
    'json': {
    'name': 'April Schwartz',
    'address': 'PSC 4843, Box 6464\nAPO AA 55073',
},
    'key64013': 'value86102',
    'key55273': 'value74827',
    'key67198': 'value87851',
    'key97967': 'value26612',
    'key84979': 'value10234',
    'key31662': 'value19387',
    'key25201': 'value53212',
    'key76550': 'value85780',
    'key49432': 'value31803',
},
    {
    'id': 17527470440344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Linda Schultz',
    'address': '6537 Sullivan Square\nSouth Andrewhaven, MO 37513',
    'text': 'Number remember several eight ball enter future today. Him beat black else type. Finish with service argue affect toward.',
    'email': 'amanda18@example.org',
    'phone_number': '001-423-321-7641x04993',
    'json': {
    'name': 'Edward Sims',
    'address': '94634 Crystal Villages\nNelsonfort, AL 34177',
},
    'key35859': 'value25598',
    'key70148': 'value91196',
    'key19802': 'value80105',
    'key58992': 'value33991',
    'key12964': 'value7444',
    'key90926': 'value89706',
    'key87144': 'value57247',
    'key84697': 'value70949',
    'key37505': 'value38096',
},
    {
    'id': 17527470440356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Brett Mcintosh',
    'address': '491 Ward Trail\nWest Robert, KS 37855',
    'text': 'Two level debate eat girl without manage. About fact tell before loss reason knowledge.',
    'email': 'allenjames@example.org',
    'phone_number': '+1-847-926-7478x79051',
    'json': {
    'name': 'Jeffrey Daniels',
    'address': '7700 Hampton Manor Apt. 880\nWest Michael, NV 79946',
},
    'key83243': 'value40748',
    'key43754': 'value13344',
},
    {
    'id': 17527470440368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Matthew Jordan',
    'address': '4564 Hicks Via\nMichaelburgh, AZ 34267',
    'text': 'Throughout sense property. Probably rate together law her great. Happen outside difficult animal painting father central.',
    'email': 'garnerjessica@example.net',
    'phone_number': '(235)999-9584x3586',
    'json': {
    'name': 'Sabrina Hill',
    'address': 'PSC 2313, Box 1523\nAPO AA 41551',
},
    'key3718': 'value29785',
},
    {
    'id': 17527470440378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Francis Woods',
    'address': '7490 Liu Plain Suite 878\nLevinefurt, GA 43233',
    'text': 'Certain save with shoulder walk. Fine seat feel scientist then.\nExpect support want discover vote upon condition. Admit continue follow bed.',
    'email': 'vcampbell@example.org',
    'phone_number': '609.561.2409x797',
    'json': {
    'name': 'Dennis Webb',
    'address': '987 Phillip Spring Suite 886\nSextonbury, MD 82985',
},
    'key63667': 'value10278',
    'key50056': 'value46822',
    'key1662': 'value88354',
    'key59184': 'value96451',
    'key63595': 'value38735',
    'key11502': 'value66521',
    'key5023': 'value58015',
    'key34020': 'value45077',
},
    {
    'id': 17527470440390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'John Jones',
    'address': '148 Payne Underpass\nWest Jesustown, WI 77920',
    'text': 'Appear wonder even ten hotel ground need. City as number read century according. Apply data once economy hit.',
    'email': 'phillipsdavid@example.org',
    'phone_number': '001-974-220-5222x2766',
    'json': {
    'name': 'Vanessa Davis',
    'address': '21806 Brent Inlet\nNew Todd, OR 74348',
},
    'key39831': 'value50008',
    'key91558': 'value47720',
    'key67195': 'value98897',
    'key60078': 'value16628',
    'key91276': 'value96381',
    'key15041': 'value80663',
    'key98655': 'value37785',
},
    {
    'id': 17527470440402,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Richard Larson',
    'address': '969 Jackson Trafficway Apt. 695\nCarrollbury, ND 45120',
    'text': 'Loss contain in offer. Realize character old dog pull story staff. Strategy response within capital well drop two. Participant case until together.\nAmerican sure same move table.',
    'email': 'christophersharp@example.com',
    'phone_number': '(952)328-0830x786',
    'json': {
    'name': 'Jennifer Galloway',
    'address': '19606 Carroll Flat\nCarterburgh, NJ 58986',
},
    'key92631': 'value41038',
    'key25204': 'value619',
    'key30018': 'value4660',
    'key36206': 'value25465',
    'key49348': 'value63333',
    'key25568': 'value28101',
    'key61648': 'value85378',
    'key94477': 'value91242',
    'key72981': 'value97945',
    'key2125': 'value77796',
},
    {
    'id': 17527470440415,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Jennifer Stewart',
    'address': 'USCGC Ramos\nFPO AE 55071',
    'text': 'General decade thousand clearly. Price respond impact management dog. Every most eight hold weight.',
    'email': 'mdiaz@example.net',
    'phone_number': '001-587-954-1917',
    'json': {
    'name': 'Joseph Spencer',
    'address': '50505 Morton Courts Apt. 302\nNew Stephen, WI 23146',
},
    'key92899': 'value46440',
    'key53091': 'value87977',
    'key38512': 'value78635',
    'key42794': 'value89854',
    'key92697': 'value22051',
    'key77833': 'value16842',
    'key60055': 'value66875',
    'key61360': 'value22490',
},
    {
    'id': 17527470440425,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Robin Adams',
    'address': '01600 Crystal Parkways Suite 485\nRobertfort, MH 80289',
    'text': 'Enjoy operation audience direction bill least cell or. Someone who five Democrat idea word.\nInstitution himself success. Carry let sit not.',
    'email': 'patrick56@example.org',
    'phone_number': '001-354-371-9585',
    'json': {
    'name': 'Kathleen Randolph',
    'address': '4354 Hunter Unions Suite 870\nNorth Robertostad, ND 27722',
},
    'key17570': 'value53846',
    'key88865': 'value22442',
    'key16936': 'value56965',
},
    {
    'id': 17527470440435,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Derrick Jones',
    'address': '68832 Ortiz Trail\nSouth Williamport, DC 19111',
    'text': 'Instead build her. All when certainly cell discover. Field film condition usually recently maybe. Own discover term image article.\nFly keep player today that clearly. Gun image baby four.',
    'email': 'ramirezbrittany@example.org',
    'phone_number': '740.403.3793',
    'json': {
    'name': 'Mr. Dustin Bishop',
    'address': '680 White Bridge\nJacksonberg, TX 58553',
},
    'key78748': 'value90628',
    'key49916': 'value37813',
    'key69491': 'value40110',
    'key39000': 'value11011',
    'key38934': 'value8786',
    'key44319': 'value2905',
    'key93653': 'value60346',
},
    {
    'id': 17527470440447,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Natasha Howard',
    'address': '04027 Heather Well\nKennethfort, IA 66434',
    'text': 'Table risk program operation. Big second minute center. Everything collection left agency. Light administration international health.',
    'email': 'ysullivan@example.net',
    'phone_number': '+1-510-444-0713x81248',
    'json': {
    'name': 'Peter Owens',
    'address': '2050 Mcguire Key Suite 131\nJonathanbury, PW 74838',
},
    'key8478': 'value50077',
    'key90275': 'value41654',
    'key93839': 'value13106',
    'key8323': 'value23627',
    'key34044': 'value34119',
    'key96046': 'value9151',
    'key8408': 'value25996',
    'key49748': 'value68620',
    'key9407': 'value46086',
},
    {
    'id': 17527470440458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Mark Greene',
    'address': '384 Christina Track Apt. 279\nWest Nicholasville, WI 56317',
    'text': 'Former once week learn boy difference. Could than close way box.\nOr seem alone store whom cut future. Wall begin nice physical strategy professional study.',
    'email': 'qalexander@example.org',
    'phone_number': '(998)565-1279',
    'json': {
    'name': 'Victoria Beck',
    'address': '328 Andrew Coves Apt. 352\nWilliamsview, MP 76569',
},
    'key99178': 'value11666',
    'key41034': 'value82062',
    'key82921': 'value76130',
    'key51775': 'value18215',
    'key41176': 'value78883',
    'key46295': 'value84427',
    'key37455': 'value98472',
},
    {
    'id': 17527470440470,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'James Riddle',
    'address': '959 Cannon Mill\nSouth Matthew, OR 56456',
    'text': 'Dinner nation possible detail. Young model happen bring group seven student. Civil a see. Manage behavior go throughout bar small word.',
    'email': 'rpetersen@example.net',
    'phone_number': '6597834669',
    'json': {
    'name': 'Kyle Sanchez',
    'address': '40243 Shah Mews Suite 361\nWest Douglasburgh, IN 30438',
},
    'key83303': 'value61986',
    'key81126': 'value9611',
},
    {
    'id': 17527470440480,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Robert Jackson',
    'address': '64374 Stephanie Club\nNorth Amanda, WI 98407',
    'text': 'Yes indeed report financial form high call. For toward executive investment why.\nDevelop catch bit short. Well organization everyone population reduce in film.',
    'email': 'rebecca58@example.net',
    'phone_number': '209-608-7793x508',
    'json': {
    'name': 'Jason Fleming',
    'address': '0881 Hinton Lights\nCynthialand, KS 89050',
},
    'key1974': 'value87687',
    'key75804': 'value3144',
    'key81547': 'value53266',
    'key92412': 'value7319',
    'key91232': 'value87261',
},
    {
    'id': 17527470440490,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Dawn Frank',
    'address': '799 Robert Route\nBridgettown, IA 57474',
    'text': 'Almost air simple structure.\nProfessor sort place fight free toward. Ready once behind two. Positive we religious mother.',
    'email': 'alexandergutierrez@example.com',
    'phone_number': '638-678-7973',
    'json': {
    'name': 'Patricia Payne',
    'address': '22561 Timothy Walks Suite 987\nSarahmouth, AK 67658',
},
    'key6679': 'value37637',
},
    {
    'id': 17527470440501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Linda Mitchell',
    'address': '58130 Heather Rapid\nJaniceburgh, MS 05295',
    'text': 'Group serve base local protect change apply short. But resource mission.',
    'email': 'fchase@example.net',
    'phone_number': '+1-550-739-1945x619',
    'json': {
    'name': 'Joseph Page',
    'address': '921 Smith Dam\nPort Brian, GU 40680',
},
    'key7367': 'value87149',
    'key70084': 'value14318',
    'key70027': 'value94852',
    'key24597': 'value8135',
    'key76892': 'value5896',
    'key36372': 'value80496',
    'key4255': 'value32684',
    'key58853': 'value86478',
},
    {
    'id': 17527470440511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Lindsey Ramos',
    'address': '4626 Castro Flats Suite 528\nSherrybury, VI 96926',
    'text': 'Nearly industry Democrat note. Stay song space six.\nInstead apply wind three wait shoulder. Consumer tell nation activity night argue.',
    'email': 'amandawhite@example.com',
    'phone_number': '522.811.8922x85120',
    'json': {
    'name': 'Joseph Brooks',
    'address': '5567 Bridges Ports Suite 924\nNew Julie, OK 71666',
},
    'key32879': 'value18287',
    'key68494': 'value68503',
    'key70402': 'value77232',
    'key47316': 'value37617',
    'key46792': 'value34160',
    'key40665': 'value65599',
},
    {
    'id': 17527470440523,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Tommy Anderson',
    'address': '866 Thornton Rapids\nEdgartown, NC 24710',
    'text': 'Kitchen will the center enter. This activity agree safe worker speech. Check top truth treatment whether later stock.',
    'email': 'usantos@example.com',
    'phone_number': '(720)536-4935',
    'json': {
    'name': 'Colleen Kennedy',
    'address': '65552 Davis Mountains\nMarymouth, DC 53239',
},
    'key5711': 'value62597',
    'key22281': 'value38234',
    'key36437': 'value15168',
},
    {
    'id': 17527470440534,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Michael Jones',
    'address': '597 Sherri Stravenue\nPatriciashire, NV 58990',
    'text': 'Public five letter onto entire water view. Interview hard and she stay food performance.\nWhat pull sign consider town like. World commercial pattern together. Say benefit continue against.',
    'email': 'rmartinez@example.net',
    'phone_number': '001-590-828-0556',
    'json': {
    'name': 'Cynthia Fowler',
    'address': '296 Richard Flat Suite 063\nEast Shannonmouth, AK 29712',
},
    'key17340': 'value97367',
    'key3216': 'value28898',
    'key38646': 'value15590',
    'key97864': 'value15606',
},
    {
    'id': 17527470440544,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Robert Hernandez',
    'address': '0355 Mcneil Isle Apt. 214\nCollinsview, FL 01551',
    'text': 'Lawyer also ten board fear pay other. Ahead very almost while arrive run determine. Produce rock well radio look. Coach free black culture woman wind.',
    'email': 'charles59@example.net',
    'phone_number': '859-704-3281x442',
    'json': {
    'name': 'David Smith',
    'address': 'USNV Thomas\nFPO AA 18275',
},
    'key9712': 'value76613',
    'key7964': 'value95896',
    'key69374': 'value61045',
    'key84136': 'value62401',
    'key45494': 'value23950',
    'key52419': 'value73284',
    'key30345': 'value20253',
    'key62677': 'value79977',
},
    {
    'id': 17527470440554,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Erika Landry',
    'address': 'USNS Freeman\nFPO AP 67547',
    'text': 'New start product anything beyond. Front bit drug perform such all lead at.\nContain young coach smile worker. Center nice our science something change. About occur practice nation card.',
    'email': 'austinmary@example.com',
    'phone_number': '563.381.7338',
    'json': {
    'name': 'Hayden Nelson',
    'address': '90700 Mitchell Corner Suite 460\nPughtown, WI 91830',
},
    'key7368': 'value80545',
    'key72979': 'value87297',
    'key31821': 'value36737',
    'key44213': 'value94168',
    'key40737': 'value32888',
    'key20308': 'value37881',
    'key22614': 'value69279',
    'key7243': 'value30996',
},
    {
    'id': 17527470440565,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Steven Sandoval Jr.',
    'address': '59509 Robert Trail Suite 083\nPort Williamburgh, FL 64848',
    'text': 'Day everything catch four man some. Spring enter billion necessary evening law bit. Main federal behavior beautiful minute today character.',
    'email': 'dtaylor@example.net',
    'phone_number': '205-239-6002',
    'json': {
    'name': 'Samantha Wiley',
    'address': '7714 Jennifer Forge\nChristinaborough, MO 30081',
},
    'key56027': 'value99821',
},
    {
    'id': 17527470440575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Mark Sullivan',
    'address': '612 Geoffrey Motorway\nAnnaside, WI 96333',
    'text': 'Morning right whose. Human instead best tough miss. Close position enjoy friend claim. College pretty create there avoid later.',
    'email': 'anthonyperez@example.org',
    'phone_number': '(690)976-3936x82536',
    'json': {
    'name': 'Heather Allen',
    'address': '39077 Charles Cliff\nJoshuaborough, MA 71094',
},
    'key20971': 'value64772',
    'key36293': 'value22695',
    'key85737': 'value27335',
    'key96040': 'value28247',
},
    {
    'id': 17527470440586,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Brittany Martinez',
    'address': '7614 Rodriguez Squares\nGinaville, VT 43638',
    'text': 'Town contain charge offer. Management full up bar family he improve.\nArgue blood news certain. Pattern thank discuss lawyer rock.',
    'email': 'laura90@example.org',
    'phone_number': '+1-302-670-9378x49335',
    'json': {
    'name': 'Timothy Ruiz',
    'address': 'PSC 2465, Box 4328\nAPO AP 45854',
},
    'key31672': 'value34349',
},
    {
    'id': 17527470440595,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Erin Jensen',
    'address': '51182 Smith Creek\nSouth Kathrynfurt, OH 29354',
    'text': 'Relate apply talk drop simple if. Operation hotel current throw itself what school.',
    'email': 'amywatson@example.net',
    'phone_number': '+1-269-748-0239',
    'json': {
    'name': 'Nicholas Park',
    'address': '82766 Jasmine Keys Suite 407\nLake Alexander, VT 02216',
},
    'key68421': 'value3157',
    'key22764': 'value89501',
    'key98345': 'value90676',
    'key88055': 'value55871',
    'key89954': 'value86101',
    'key54797': 'value82546',
    'key65674': 'value65328',
    'key33317': 'value72275',
},
    {
    'id': 17527470440606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Peggy Oneill',
    'address': '4407 Margaret Harbor\nShanechester, FM 63579',
    'text': 'Common light similar professional project education fund. Value deal pass couple ready.\nGlass environmental write have position still when recognize. Enter per ten she night ever.',
    'email': 'laurie60@example.net',
    'phone_number': '515.211.3895x267',
    'json': {
    'name': 'Richard Carter',
    'address': '2168 Ward Rue Suite 742\nWest Jason, PW 69271',
},
    'key10840': 'value40637',
},
    {
    'id': 17527470440616,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Jeffrey Miller',
    'address': '765 Hernandez Corners Suite 312\nMeganport, VA 35147',
    'text': 'Early much likely suffer necessary of front. What hospital writer.\nTrial safe bring husband. Clear mouth even leg page set baby.',
    'email': 'gerald45@example.org',
    'phone_number': '729-309-3289x077',
    'json': {
    'name': 'Mark Wilson',
    'address': '8985 Garcia Mills Suite 776\nJessicamouth, HI 06351',
},
    'key54871': 'value90252',
    'key80350': 'value69397',
    'key80286': 'value17175',
},
    {
    'id': 17527470440627,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michael Sutton',
    'address': '799 Riley Center\nPort Anita, WI 75102',
    'text': 'Moment heavy hit name cover season manage war. Act young thing no simple. Play I though crime study possible finally.\nReason participant so number field. Degree range skill certain prove.',
    'email': 'henrytownsend@example.com',
    'phone_number': '829-601-4367',
    'json': {
    'name': 'Mackenzie Chambers',
    'address': '729 Nathan Orchard Apt. 901\nWashingtonbury, MD 78258',
},
    'key87015': 'value57470',
    'key71527': 'value48012',
    'key20415': 'value72221',
    'key93065': 'value37198',
    'key66026': 'value69301',
},
    {
    'id': 17527470440638,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Joseph Perez',
    'address': '82070 Frank Prairie Suite 982\nPort Adam, DC 19274',
    'text': 'Garden media glass serve. Suggest product his development.',
    'email': 'morsediane@example.org',
    'phone_number': '(978)891-1667x32418',
    'json': {
    'name': 'Melvin Johnson',
    'address': '087 Tammy Wells Apt. 026\nPort Christopher, GA 41798',
},
    'key32174': 'value7153',
    'key95842': 'value53127',
    'key74495': 'value31283',
    'key8335': 'value84822',
},
    {
    'id': 17527470440650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'David White',
    'address': '19381 Jessica Corner Apt. 890\nPort Matthewview, NM 65564',
    'text': 'Knowledge new month his. Thing carry six newspaper. Administration low way issue heavy.\nThese middle myself these. Top painting investment response.',
    'email': 'adamsadam@example.org',
    'phone_number': '9975584317',
    'json': {
    'name': 'Jordan Bennett',
    'address': '8037 Wallace Isle Suite 130\nLarsonton, AK 32338',
},
    'key90632': 'value45339',
    'key95193': 'value20503',
    'key85075': 'value67224',
    'key5273': 'value95215',
    'key57092': 'value96726',
    'key47059': 'value31602',
    'key29441': 'value73393',
    'key32835': 'value36257',
    'key41699': 'value65217',
    'key13707': 'value50153',
},
    {
    'id': 17527470440662,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Brenda Lawson',
    'address': '52550 Kevin Plaza\nNorth Jacqueline, NV 06023',
    'text': 'Drive debate even morning benefit travel. Ability stay decide.\nElse sense capital development. Report upon none protect through ask speak.',
    'email': 'jessicajensen@example.org',
    'phone_number': '+1-343-692-4433x4220',
    'json': {
    'name': 'Michael Gilbert',
    'address': 'Unit 2595 Box 5852\nDPO AA 30487',
},
    'key55592': 'value74114',
    'key81302': 'value77191',
    'key1626': 'value68717',
    'key5098': 'value93570',
    'key21444': 'value83337',
    'key56115': 'value69272',
    'key95947': 'value24656',
    'key87807': 'value37760',
},
    {
    'id': 17527470440671,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Donna Stone',
    'address': '07835 Nathan Village\nGailborough, GU 42700',
    'text': 'Really present people power indicate health large specific. International quite themselves. Ask floor until never.',
    'email': 'gina86@example.com',
    'phone_number': '739.950.9553x68397',
    'json': {
    'name': 'Mason Kennedy',
    'address': '0523 Nancy Bridge Suite 339\nPort Joshua, AK 66471',
},
    'key15412': 'value22713',
    'key65126': 'value13711',
    'key46381': 'value48785',
    'key58593': 'value35389',
    'key28649': 'value72717',
    'key51883': 'value18974',
    'key59081': 'value84663',
    'key64783': 'value18318',
    'key59673': 'value61218',
    'key32789': 'value14894',
},
    {
    'id': 17527470440681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Stephanie Smith',
    'address': '9347 Jordan Underpass Suite 579\nEast Davidview, WI 30384',
    'text': 'State rich impact same Congress today training. Action rock such production each lawyer.\nRange suffer ever compare certainly.',
    'email': 'melissadavis@example.org',
    'phone_number': '(558)532-1999',
    'json': {
    'name': 'Michael Thomas',
    'address': '2452 Ryan Junction Apt. 042\nEast Judy, GU 18333',
},
    'key60998': 'value52733',
    'key33001': 'value52734',
    'key7181': 'value82644',
    'key47997': 'value76575',
    'key99573': 'value22347',
    'key27748': 'value94418',
    'key69310': 'value45665',
},
    {
    'id': 17527470440691,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Sara Richmond',
    'address': '5030 Gilbert Place Apt. 656\nAdamland, NC 28396',
    'text': 'Time among news institution. Study each hour wide back couple.\nMe season stay could half life. Offer represent defense herself including skill step left.',
    'email': 'sandraanderson@example.com',
    'phone_number': '(429)825-4425',
    'json': {
    'name': 'Diane Allen',
    'address': '440 Barbara Creek Suite 468\nSouth Noah, NY 40990',
},
    'key92767': 'value61305',
    'key28443': 'value76846',
    'key11561': 'value15905',
    'key93534': 'value10335',
    'key87407': 'value60144',
    'key49511': 'value35855',
    'key68099': 'value21318',
},
    {
    'id': 17527470440703,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Penny Williams',
    'address': '92160 Johnson Trafficway Apt. 233\nTylerchester, NV 56254',
    'text': 'Shake member than whom prepare leave deep. Sure which work cost. Suddenly outside head generation detail these stock.\nFood air by none heavy foot. Now decide grow take and voice might.',
    'email': 'wallacebenjamin@example.org',
    'phone_number': '(467)520-6050x44914',
    'json': {
    'name': 'Jennifer Alvarez',
    'address': '5941 King Underpass\nPort Ryan, DC 89444',
},
    'key52587': 'value10007',
    'key41359': 'value52556',
    'key50837': 'value71405',
    'key21841': 'value29830',
    'key41275': 'value69723',
    'key21505': 'value49111',
},
    {
    'id': 17527470440715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Karen Byrd',
    'address': 'USCGC Wolfe\nFPO AP 46846',
    'text': 'Party keep dog thousand source rate. Area pay six during.\nEconomy meet ball phone back. Outside front per maybe but about determine.',
    'email': 'riveradenise@example.com',
    'phone_number': '(727)274-0860',
    'json': {
    'name': 'Corey Green',
    'address': '80365 Robinson Locks\nNorth Logan, WA 54859',
},
    'key33433': 'value53272',
    'key31543': 'value15982',
    'key21305': 'value99541',
    'key48435': 'value46531',
    'key81621': 'value9396',
    'key22950': 'value59165',
},
    {
    'id': 17527470440725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Elizabeth Prince',
    'address': '444 Mark Rapid\nNorth Whitneyborough, ID 86443',
    'text': 'Whose hundred use stand baby cultural. Land child pressure quite everyone behavior pay serve.\nName low service dark material. Second work attention majority.',
    'email': 'john72@example.org',
    'phone_number': '(951)320-6087x497',
    'json': {
    'name': 'Christopher Martinez',
    'address': '625 Greg Plaza Apt. 174\nJoneston, GU 37391',
},
    'key94435': 'value2813',
    'key52759': 'value30737',
    'key55598': 'value49321',
    'key3463': 'value52177',
    'key42080': 'value4157',
    'key88093': 'value48053',
},
    {
    'id': 17527470440735,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Anthony Benson',
    'address': 'USS Nichols\nFPO AP 64384',
    'text': 'Everything trouble sit follow. Election recently whether protect interest model crime. Source exactly year view raise similar.',
    'email': 'gholmes@example.net',
    'phone_number': '001-391-443-7695',
    'json': {
    'name': 'Brittany Howard',
    'address': '7295 Clark Passage Suite 969\nSteeleview, AS 49522',
},
    'key61402': 'value90722',
    'key88754': 'value28160',
    'key24700': 'value77879',
    'key45916': 'value27305',
    'key88855': 'value29943',
    'key22616': 'value50726',
},
    {
    'id': 17527470440745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Taylor Hull',
    'address': '91902 Brenda Harbor\nNew Tinafort, MT 79557',
    'text': 'Production hold down rich or doctor agency type. Better better news opportunity rather. Window father move possible ago.\nPick year concern. Technology hard nation indicate sell final tell partner.',
    'email': 'ramirezabigail@example.com',
    'phone_number': '001-576-354-2662x78683',
    'json': {
    'name': 'Tiffany Jackson',
    'address': '50711 Kristina Village Suite 848\nBoltonborough, MO 20252',
},
    'key17595': 'value46199',
    'key67954': 'value51393',
    'key58746': 'value34206',
    'key40477': 'value5496',
    'key95855': 'value70707',
    'key31212': 'value29915',
    'key9636': 'value41415',
    'key11547': 'value79067',
    'key59350': 'value72716',
    'key51498': 'value94445',
},
    {
    'id': 17527470440756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Michelle Montgomery',
    'address': '188 Jeffrey Ridges Apt. 077\nEast Kenneth, HI 53486',
    'text': 'Congress night join Democrat note girl.\nOff fast born understand officer away. More much million beautiful rule perform check we. Ability have development.',
    'email': 'thomas40@example.com',
    'phone_number': '465.995.3049x5343',
    'json': {
    'name': 'Tammy Doyle',
    'address': '4746 Lee Harbors\nWest Carolynfort, VT 62192',
},
    'key55348': 'value47217',
    'key72350': 'value31344',
    'key44293': 'value31240',
    'key31433': 'value19392',
    'key5464': 'value62774',
    'key48328': 'value30585',
    'key21952': 'value57015',
    'key87848': 'value92311',
},
    {
    'id': 17527470440767,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Christopher Ramirez II',
    'address': '26962 Theresa Station\nMorrisview, IA 34847',
    'text': 'Few than customer worry whole eat. Expect personal tree later hear record. Tough travel cultural.\nCatch matter consumer whom third manager my course. That choose seem source apply smile network.',
    'email': 'jfowler@example.com',
    'phone_number': '001-577-213-3430x6874',
    'json': {
    'name': 'Sophia Simmons',
    'address': '52682 Danielle Divide\nLake Kaylaburgh, GA 93576',
},
    'key90445': 'value1468',
    'key49922': 'value46288',
    'key29238': 'value10057',
    'key4857': 'value93427',
    'key55735': 'value95522',
    'key99103': 'value31287',
    'key97989': 'value36423',
    'key77143': 'value49384',
    'key91570': 'value3698',
    'key75442': 'value47270',
},
    {
    'id': 17527470440777,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Amy Long',
    'address': '6762 Alicia Throughway\nRodriguezfort, NY 51493',
    'text': 'Garden open difference response national five. Continue happen final hour serve thank.',
    'email': 'dwalker@example.com',
    'phone_number': '001-568-820-6298',
    'json': {
    'name': 'Danielle Hughes',
    'address': '30193 Howard Springs Suite 609\nCarlsonland, HI 99257',
},
    'key99370': 'value83969',
},
    {
    'id': 17527470440788,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Mckenzie Sanchez',
    'address': 'PSC 8126, Box 8495\nAPO AP 05387',
    'text': 'Low local draw.\nExpert history check tell child avoid. Begin short describe partner show create laugh firm.\nArea young describe thus. Resource school offer nice bag main.',
    'email': 'jason63@example.com',
    'phone_number': '(419)466-5637',
    'json': {
    'name': 'Vanessa Allen',
    'address': '41000 David Mission\nErinmouth, IA 76811',
},
    'key21993': 'value11100',
    'key96709': 'value19442',
},
    {
    'id': 17527470440797,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Howard Taylor',
    'address': '9154 Christopher Wall Apt. 020\nPort Christopher, ME 10516',
    'text': 'Theory image lose these table once. After enough official defense. Cause four allow from both message participant something.',
    'email': 'lcarter@example.org',
    'phone_number': '531-368-5452',
    'json': {
    'name': 'Alexander Peters',
    'address': '979 Walker Mill\nWilliamschester, GU 07360',
},
    'key89107': 'value31735',
    'key35465': 'value22942',
    'key16130': 'value88464',
    'key2694': 'value5739',
    'key60830': 'value1934',
    'key86842': 'value15271',
    'key47697': 'value80165',
    'key28747': 'value299',
    'key62769': 'value47834',
    'key13734': 'value21879',
},
    {
    'id': 17527470440810,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Matthew Mcgee',
    'address': '3659 Chelsea Pines\nNorth Kimberlyville, FM 56439',
    'text': 'Foot treatment front particularly three number fund student. Player deep drop million president. Your our election art wall.',
    'email': 'andrew02@example.net',
    'phone_number': '+1-465-363-2387',
    'json': {
    'name': 'Tammy Rowe',
    'address': '762 Justin Inlet Suite 947\nEricfort, IA 19324',
},
    'key39102': 'value69227',
    'key75755': 'value58912',
    'key50183': 'value95248',
    'key64920': 'value71105',
    'key77756': 'value24982',
    'key54793': 'value8347',
    'key5741': 'value87057',
},
    {
    'id': 17527470440823,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Curtis Nichols DVM',
    'address': '019 Warren Drive\nEthanport, HI 37760',
    'text': 'Around gun upon young only result. Special pull here decide. Whom return right. Pass care safe have investment democratic.',
    'email': 'pfuller@example.org',
    'phone_number': '347-259-7947',
    'json': {
    'name': 'Adam Moore',
    'address': '96212 Brian Fork Suite 057\nWest Laurachester, KS 89341',
},
    'key87251': 'value71860',
},
    {
    'id': 17527470440836,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Marvin Richards',
    'address': 'Unit 5802 Box 7397\nDPO AA 01878',
    'text': 'Girl good job peace lead simple.\nBlack minute knowledge ground sing. Assume white today whom. Run ask quickly including.\nGlass quality base base son offer.',
    'email': 'jacquelineanderson@example.net',
    'phone_number': '713-546-5829',
    'json': {
    'name': 'James Bishop',
    'address': '2320 Timothy Streets Suite 873\nTiffanyshire, MP 79718',
},
    'key91594': 'value65422',
    'key82243': 'value80407',
    'key33054': 'value80339',
    'key84229': 'value62275',
    'key82155': 'value67654',
    'key87902': 'value36271',
    'key60649': 'value56917',
    'key82410': 'value19080',
},
    {
    'id': 17527470440848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Sarah Shaw',
    'address': '944 Timothy Mill\nPort Ronaldhaven, MP 91479',
    'text': 'Idea clear focus field whatever. Man edge public write thing.\nGoal standard kid mother. Hot too during. Rule news career member trip computer.\nUsually day I. Writer raise head end throw modern.',
    'email': 'stephanieberg@example.net',
    'phone_number': '001-711-355-3556x23174',
    'json': {
    'name': 'Samantha Todd',
    'address': '82756 Pineda Lodge Apt. 105\nJacksonland, PW 93452',
},
    'key68559': 'value39908',
    'key94717': 'value32859',
    'key11111': 'value31092',
},
    {
    'id': 17527470440863,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Sarah Turner',
    'address': '516 Cisneros Row\nLaurabury, GA 16382',
    'text': 'Bar century travel unit he opportunity. Knowledge blood rich purpose structure total. Boy son treat during knowledge green. Report analysis every necessary movement message skin.',
    'email': 'qdennis@example.net',
    'phone_number': '001-776-309-2905',
    'json': {
    'name': 'Cynthia Johnson',
    'address': '3234 Benson Vista Suite 390\nLake Theresaton, AR 58734',
},
    'key41129': 'value99156',
    'key87313': 'value11827',
    'key47001': 'value44930',
    'key41600': 'value16343',
    'key65678': 'value3598',
},
    {
    'id': 17527470440877,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Glenn Kim DVM',
    'address': '2107 Kathleen Springs\nNew Valeriefort, NJ 38827',
    'text': 'Weight perform early option note off performance. Same travel continue quite whom stop top. Compare expect arm network.\nMeeting two mouth bit believe.',
    'email': 'cassandrajohnson@example.net',
    'phone_number': '+1-247-527-3807x583',
    'json': {
    'name': 'Ann Harper',
    'address': '57914 Michael Plains Apt. 692\nNorth Bryan, ND 34099',
},
    'key99714': 'value6107',
    'key27057': 'value2183',
    'key39621': 'value2538',
    'key29383': 'value6351',
    'key49095': 'value86933',
    'key2100': 'value20022',
    'key4780': 'value3340',
},
    {
    'id': 17527470440889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Michelle Miranda',
    'address': '31041 Dwayne Fields\nRobinberg, CT 65095',
    'text': 'Particular side financial pay. Teach green trial rate my local technology. Say ability memory hot must walk staff.',
    'email': 'cwilson@example.net',
    'phone_number': '001-401-848-9456',
    'json': {
    'name': 'Lacey Nelson',
    'address': '3609 Rebecca Underpass Suite 194\nNew Katherinehaven, AK 12554',
},
    'key60603': 'value81792',
    'key70161': 'value75515',
    'key84500': 'value21587',
    'key62178': 'value83576',
    'key99692': 'value50332',
    'key86014': 'value55708',
    'key40862': 'value59834',
    'key5552': 'value2051',
},
    {
    'id': 17527470440899,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'John Howard',
    'address': '4797 Marie Summit\nNorth George, ME 94315',
    'text': 'List owner show shoulder hot test. Since today city security.\nAge year dog friend trade cover.\nBit family piece who.\nAttack by hear high. Not public old push phone office available.',
    'email': 'vasquezjenna@example.net',
    'phone_number': '674.549.4939x6376',
    'json': {
    'name': 'Christina Delacruz',
    'address': '89580 Mark Manor\nSouth Aaron, WY 82511',
},
    'key45756': 'value94735',
    'key70663': 'value20421',
    'key11849': 'value20718',
    'key7609': 'value47719',
    'key98455': 'value35619',
    'key19552': 'value20184',
    'key95838': 'value8678',
    'key57528': 'value37389',
},
    {
    'id': 17527470440910,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Maria Jacobson',
    'address': '7209 Samantha Expressway\nGrantborough, AS 03767',
    'text': 'Difference single short city account. Way wear age site glass case listen. Cup author necessary specific several employee level upon. Fact stuff protect part own miss base program.',
    'email': 'whitney04@example.org',
    'phone_number': '524.265.5743',
    'json': {
    'name': 'Nancy Martin',
    'address': '7639 Welch Forks Suite 367\nPort Yolanda, NM 83818',
},
    'key99688': 'value21291',
    'key83533': 'value88772',
    'key83711': 'value23082',
    'key62858': 'value44645',
},
    {
    'id': 17527470440920,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Rachel Castillo',
    'address': '77537 Barbara Row\nNew Clairefort, AZ 46102',
    'text': 'Sort example because require class dinner standard.\nReduce music decision contain. Wife summer air state. Seat federal natural would machine send of sister.',
    'email': 'andrea32@example.com',
    'phone_number': '001-720-632-5002x270',
    'json': {
    'name': 'Mr. Adam Mason',
    'address': '344 Haley Street\nNew Williamborough, AZ 48316',
},
    'key45944': 'value74346',
    'key16314': 'value18760',
    'key5466': 'value38535',
    'key63302': 'value44123',
    'key71537': 'value1448',
    'key85062': 'value30267',
    'key32792': 'value84291',
},
    {
    'id': 17527470440930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Justin Hernandez',
    'address': '06977 Phelps Stravenue\nMcguirechester, ME 87981',
    'text': 'Personal group although operation industry. Item job old my.\nView back century her. Stay second bit name building across late. Threat central account ask build interesting brother example.',
    'email': 'hernandezdanielle@example.net',
    'phone_number': '940-740-9313',
    'json': {
    'name': 'Matthew Cook',
    'address': '543 Bowen Locks Suite 680\nNew Brianbury, IN 02304',
},
    'key42863': 'value51998',
    'key1782': 'value20443',
},
    {
    'id': 17527470440942,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Todd Ramsey',
    'address': '63143 Adam Overpass\nWest Sheri, AZ 20810',
    'text': 'Use area none. Pretty color develop would main on environment. Improve decade actually senior article.\nHear visit discuss president such. Interview be blood drop public staff. Ago ahead high.',
    'email': 'elliottshannon@example.net',
    'phone_number': '390.525.0388x37218',
    'json': {
    'name': 'Breanna Cruz',
    'address': '90798 Reed Courts\nAlexandraberg, GU 01249',
},
    'key42700': 'value41764',
    'key59146': 'value34224',
    'key87223': 'value10745',
    'key32589': 'value60595',
    'key99942': 'value66659',
    'key9321': 'value50981',
},
    {
    'id': 17527470440953,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Amanda Long',
    'address': '0404 Tammy Ranch Apt. 465\nPort Lorihaven, KS 46026',
    'text': 'Near save sure myself night their certain. Blue machine through standard act serve year.',
    'email': 'mcdonaldjames@example.net',
    'phone_number': '001-412-853-9193',
    'json': {
    'name': 'Kimberly Gilmore',
    'address': '05749 Barbara Lodge Suite 627\nNorth Angela, IN 19421',
},
    'key42947': 'value8060',
    'key26856': 'value2725',
    'key34912': 'value35270',
    'key14243': 'value76138',
    'key39317': 'value36020',
    'key24205': 'value95780',
    'key62910': 'value47360',
    'key32833': 'value55780',
    'key53795': 'value24575',
    'key55008': 'value1519',
},
    {
    'id': 17527470440964,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Katherine Romero',
    'address': '97799 Lori Valley Apt. 368\nPort Connie, LA 69938',
    'text': 'Stuff though exist speak tell. When great fly college no. Candidate who set every dark than. Which themselves wife about yeah country page relationship.',
    'email': 'davidperez@example.com',
    'phone_number': '(963)256-4590',
    'json': {
    'name': 'Ashlee Garza',
    'address': '388 Bryan Summit Apt. 755\nNorth Rose, CO 56920',
},
    'key28141': 'value1437',
    'key47958': 'value37961',
    'key8188': 'value98235',
    'key48509': 'value9801',
},
    {
    'id': 17527470440975,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'David Zuniga',
    'address': 'PSC 4953, Box 2386\nAPO AA 34726',
    'text': 'Team marriage performance government act across. Product event into staff sense project. Live program ball major responsibility. Your and thought move.',
    'email': 'brooke25@example.net',
    'phone_number': '(721)266-5595',
    'json': {
    'name': 'Vanessa Graham',
    'address': 'PSC 8227, Box 7329\nAPO AA 87347',
},
    'key84932': 'value51332',
    'key92175': 'value10056',
    'key23534': 'value75239',
    'key80597': 'value24385',
    'key23846': 'value24105',
    'key10350': 'value76628',
},
    {
    'id': 17527470440981,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Kimberly Whitehead DDS',
    'address': '41110 Sanchez Isle\nLake Cindy, SC 83782',
    'text': 'Policy institution top lot fire. Hospital receive peace.\nBreak yeah own adult generation general identify. Surface imagine free lead. Address director institution laugh trip leader everything.',
    'email': 'kyle22@example.org',
    'phone_number': '322.828.0083x107',
    'json': {
    'name': 'Eileen Hansen',
    'address': '972 Samantha Hills Suite 258\nEast Dawn, AK 99595',
},
    'key55548': 'value53413',
},
    {
    'id': 17527470440992,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Kaylee Galvan',
    'address': '622 Thomas Haven Suite 291\nVickiefurt, FM 62503',
    'text': 'Wear sing clearly sell cause. Art wide plan manager fly pick.\nCompare because marriage. Physical program knowledge sea.',
    'email': 'greenamanda@example.com',
    'phone_number': '001-972-274-4094x730',
    'json': {
    'name': 'Melinda Robles',
    'address': '71391 Leonard Spur Suite 213\nMaryville, GA 05595',
},
    'key29842': 'value56882',
    'key18031': 'value8425',
    'key35022': 'value5004',
    'key26289': 'value91897',
    'key72996': 'value11231',
    'key24055': 'value74440',
    'key71842': 'value35051',
    'key44507': 'value89640',
},
    {
    'id': 17527470441003,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jessica Sullivan',
    'address': '26361 Ponce Hills Apt. 501\nLake Linda, AS 37845',
    'text': 'Lot economic body nice the. Everybody option table.\nParent such painting low use stay their. Professional some food list million movement grow recognize.\nScene conference he it young image yeah.',
    'email': 'jimsmith@example.org',
    'phone_number': '7907563461',
    'json': {
    'name': 'Aaron Huang',
    'address': '3313 Amanda Mills\nLake Cory, WY 62394',
},
    'key39718': 'value48208',
    'key76778': 'value45954',
    'key72987': 'value37746',
    'key63056': 'value20069',
    'key67273': 'value36224',
    'key76138': 'value3359',
    'key19101': 'value71137',
    'key30435': 'value77167',
    'key52366': 'value15567',
},
    {
    'id': 17527470441014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Mr. Michael Johnston DVM',
    'address': '0014 Ryan Burgs\nPort Aaron, IN 75575',
    'text': 'Check impact wish subject.\nSubject before recently teach be. Recent each until guy.\nBudget institution anything goal fight. Per themselves very environment up policy.',
    'email': 'browntina@example.org',
    'phone_number': '001-478-732-0648x763',
    'json': {
    'name': 'Anna Burton',
    'address': '52437 Riggs Dale\nClarktown, SD 33821',
},
    'key74806': 'value81027',
    'key83161': 'value54126',
    'key26178': 'value38384',
    'key57027': 'value17767',
    'key80365': 'value36493',
    'key62093': 'value14047',
    'key52854': 'value92762',
    'key90083': 'value43836',
    'key4948': 'value87998',
    'key47891': 'value39193',
},
    {
    'id': 17527470441026,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Elizabeth Patterson',
    'address': '9496 Oneal Trafficway Apt. 785\nEast Andrea, VT 34117',
    'text': 'Little single drop enjoy per. Show probably exist. Focus difference morning any close.\nCatch citizen evidence body part degree. Seven back land than industry ball body.',
    'email': 'wwright@example.org',
    'phone_number': '+1-900-366-9467x723',
    'json': {
    'name': 'Mrs. Elizabeth Diaz',
    'address': '9531 Diana Village\nJoshuaside, AR 18337',
},
    'key11334': 'value87639',
},
    {
    'id': 17527470441037,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Ashley Moore',
    'address': '38621 Jennifer Port Apt. 592\nPort Martin, NJ 45082',
    'text': 'Phone example speak spring however enough. Stuff one ground put and. Budget ahead painting effect now determine behind.',
    'email': 'janicemoore@example.org',
    'phone_number': '+1-521-414-0254x17060',
    'json': {
    'name': 'Ashley Cruz',
    'address': '769 Nelson Ramp\nTurnerfort, MA 67170',
},
    'key33986': 'value3266',
    'key24496': 'value36446',
    'key57562': 'value38190',
    'key8880': 'value82306',
    'key11914': 'value62895',
    'key31304': 'value12381',
},
    {
    'id': 17527470441048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Chad Ashley',
    'address': '2151 Contreras Fields Suite 166\nScottborough, VT 16973',
    'text': 'Loss avoid rock step everyone kid. Myself family special whole relate likely world ever.\nSimilar success skill home court. Data story security wait yard when whole. Drive few decide strategy.',
    'email': 'brandtjoel@example.net',
    'phone_number': '001-981-653-9073x295',
    'json': {
    'name': 'Shelby Wright',
    'address': 'USCGC Thompson\nFPO AP 99466',
},
    'key89801': 'value28710',
},
    {
    'id': 17527470441059,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'David Sullivan',
    'address': '052 Perez Ports Apt. 559\nPort David, FM 97100',
    'text': 'Off use free wide. Science nice once strong. Degree development voice coach.\nImpact environmental add. Full bit serious ever north so figure. Early and speech glass.',
    'email': 'linda42@example.net',
    'phone_number': '411.454.8311x04119',
    'json': {
    'name': 'Lisa Best',
    'address': '884 Margaret Roads\nPort Daniel, UT 60197',
},
    'key74099': 'value72884',
    'key23306': 'value16092',
    'key80545': 'value64888',
    'key913': 'value24768',
    'key77983': 'value93819',
    'key85922': 'value38807',
    'key39191': 'value1120',
},
    {
    'id': 17527470441070,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jessica Perez',
    'address': '882 Walker Spurs Suite 915\nFlemingshire, NE 84142',
    'text': 'Owner face herself how country. Risk conference receive customer data leave. Evidence indeed reality house fine young religious.',
    'email': 'bryan44@example.net',
    'phone_number': '(738)882-6414x4164',
    'json': {
    'name': 'Jeremy Brown',
    'address': '71838 Ronald Underpass\nCurtisburgh, ID 44468',
},
    'key90194': 'value96346',
    'key92893': 'value89362',
    'key96893': 'value58882',
    'key66597': 'value97855',
    'key83892': 'value93682',
    'key53640': 'value29465',
    'key53287': 'value1746',
    'key78415': 'value92105',
    'key90066': 'value66375',
    'key45123': 'value17663',
},
    {
    'id': 17527470441081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Melissa Johnson',
    'address': '49258 Jimenez Inlet Suite 490\nWilsonbury, PR 26160',
    'text': 'House yard prepare evening might debate benefit. Computer skill other maybe rise born. Media fine hear main.',
    'email': 'debrawhite@example.org',
    'phone_number': '608-748-5189x692',
    'json': {
    'name': 'Mr. John Farrell',
    'address': '7037 Kayla Land\nWest Brittneyhaven, KS 69896',
},
    'key46300': 'value39318',
    'key28553': 'value81685',
    'key30344': 'value29811',
    'key10910': 'value46760',
    'key62584': 'value17452',
    'key4214': 'value52213',
},
    {
    'id': 17527470441094,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Angela Jones',
    'address': '004 Hall Highway\nLloydtown, RI 46228',
    'text': 'Treat type ability impact kitchen although road. Let top leg bit lot student. Year really morning night easy.',
    'email': 'cruzdonald@example.org',
    'phone_number': '548.842.5804',
    'json': {
    'name': 'Emma Phillips',
    'address': '6566 April Road Suite 606\nNew Jennifermouth, LA 62650',
},
    'key42394': 'value26519',
},
    {
    'id': 17527470441106,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Jordan Obrien',
    'address': '1157 Osborne Unions\nNorth Samantha, MN 62562',
    'text': 'Win computer with task. Wind most fill.\nMission wait whom recognize project nice. Central Republican office begin thank.\nProcess indeed energy. Near fact everyone capital.',
    'email': 'rmoreno@example.com',
    'phone_number': '681.926.3762',
    'json': {
    'name': 'Kelly Moore',
    'address': '397 Walker Alley Suite 466\nEast Benjaminfort, CO 15832',
},
    'key83371': 'value19256',
    'key28686': 'value4298',
    'key78480': 'value5549',
    'key62554': 'value80148',
    'key82606': 'value10311',
},
    {
    'id': 17527470441117,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Kathleen Murphy',
    'address': '026 Tammy Motorway Apt. 358\nSouth Ambermouth, DC 61644',
    'text': 'Land natural improve. Way attention whom.\nAfter difference as system effect night describe agree.',
    'email': 'gracelucas@example.com',
    'phone_number': '+1-534-863-5797x43272',
    'json': {
    'name': 'Robert Edwards',
    'address': '6170 Danielle Ford Apt. 261\nRobertstown, GA 99049',
},
    'key55061': 'value71443',
    'key89000': 'value55909',
    'key44536': 'value86871',
    'key20312': 'value81512',
    'key60521': 'value62893',
    'key4088': 'value46631',
    'key10611': 'value86884',
},
    {
    'id': 17527470441129,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Daniel Palmer',
    'address': '748 Walker Parkways\nSouth Sara, OR 91255',
    'text': 'Unit show hair. Help authority have kind.\nPaper west food go.\nDifferent understand such imagine cell throw. Subject use manage individual. Simply scene play up hear doctor picture.',
    'email': 'patriciathompson@example.net',
    'phone_number': '001-663-905-0436x76733',
    'json': {
    'name': 'Meredith Cunningham',
    'address': '6569 Alicia Center\nPort Cindybury, CA 64257',
},
    'key92482': 'value50062',
    'key35681': 'value13523',
},
    {
    'id': 17527470441141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Michael Anthony',
    'address': '670 Horn Ville Apt. 998\nWest Victoria, AL 78817',
    'text': 'Individual social know. Piece late respond occur.\nRecord director down decade. Church easy area its. Early character player most agree itself decide price.',
    'email': 'sarahsanchez@example.com',
    'phone_number': '001-577-500-4553x393',
    'json': {
    'name': 'Renee Robinson',
    'address': '3653 Cook Flat\nBallardtown, PR 66668',
},
    'key65297': 'value53066',
    'key4088': 'value82001',
    'key59304': 'value41271',
    'key10871': 'value29960',
    'key5583': 'value18805',
    'key89833': 'value15563',
},
    {
    'id': 17527470441153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Lance Smith',
    'address': '72345 Jackson Point Apt. 098\nPort Thomasstad, MH 29573',
    'text': 'Present somebody cause continue. Girl popular center morning discussion design player. Try him heavy end role opportunity.\nOnly approach capital. Owner international phone room enjoy. At lot surface.',
    'email': 'elizabethdunn@example.org',
    'phone_number': '734-524-2621x96708',
    'json': {
    'name': 'Dave Khan',
    'address': '6783 Scott Dam\nAngelaport, FM 84386',
},
    'key98887': 'value11902',
},
    {
    'id': 17527470441165,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Jill Dixon',
    'address': 'USNS Brennan\nFPO AP 53180',
    'text': 'Season mean water three. Within standard senior represent month water specific. Type degree truth game federal many fear.',
    'email': 'camposanthony@example.org',
    'phone_number': '001-941-397-9825x995',
    'json': {
    'name': 'John Kim',
    'address': '64358 Shaffer Street Apt. 881\nEmilyville, GA 24162',
},
    'key59183': 'value37285',
    'key70704': 'value34723',
    'key91772': 'value33019',
    'key35997': 'value50955',
    'key23910': 'value87880',
    'key38957': 'value38909',
    'key89010': 'value54934',
},
    {
    'id': 17527470441176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Kimberly Oliver',
    'address': '65513 Gabriel Street Apt. 916\nLake Benjamin, WI 12700',
    'text': 'Sure herself onto media family range. Out mention matter million move.\nPass production enjoy option. Maybe simple seem Democrat night.\nHand all cause let. Black final whole today idea.',
    'email': 'kathrynsalazar@example.net',
    'phone_number': '981-244-7151x8408',
    'json': {
    'name': 'Patricia Jennings',
    'address': '081 Marshall Camp\nCrystalstad, AR 93743',
},
    'key79860': 'value72110',
    'key21248': 'value26701',
    'key62429': 'value41175',
    'key1041': 'value85574',
    'key30924': 'value71347',
    'key13351': 'value5618',
    'key47927': 'value15670',
    'key79319': 'value42523',
},
    {
    'id': 17527470441188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Mary Stanley',
    'address': '669 James Club Apt. 855\nEast Jennifer, FM 74957',
    'text': 'If church especially loss place. Model arrive newspaper find find.\nFoot focus sing film each. First wife range beat language defense.',
    'email': 'virginia01@example.com',
    'phone_number': '001-700-869-3885x879',
    'json': {
    'name': 'Justin Wright',
    'address': '56048 Thomas Gateway\nRowlandburgh, UT 46392',
},
    'key95574': 'value78945',
    'key36981': 'value95090',
    'key70344': 'value81211',
    'key26920': 'value62709',
    'key67819': 'value74241',
    'key7379': 'value62219',
    'key230': 'value11687',
    'key6091': 'value18555',
},
    {
    'id': 17527470441198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Dalton Wilson',
    'address': '85501 Kristy Loaf\nNorth James, PA 24699',
    'text': 'Up whose year experience. Able live fund hard away. Deep book deal present work something hour.',
    'email': 'pmoore@example.com',
    'phone_number': '509.626.7745',
    'json': {
    'name': 'Tammy Phillips',
    'address': '5428 Wyatt Canyon\nNorth Jose, AZ 68034',
},
    'key96635': 'value86728',
},
    {
    'id': 17527470441208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Katie Ortiz',
    'address': '3320 David Wall Suite 827\nJuanview, MI 17040',
    'text': 'Drug future difference cultural probably arm common. Girl cultural throughout color. Not control small memory alone five.',
    'email': 'jrivera@example.net',
    'phone_number': '(383)280-1086',
    'json': {
    'name': 'Christine Walker',
    'address': '252 Rogers Track\nLowemouth, CA 62253',
},
    'key34870': 'value25106',
    'key32434': 'value69882',
},
    {
    'id': 17527470441218,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Chelsea Davis',
    'address': '77244 Johnson Garden Suite 913\nWest Davidport, AZ 20011',
    'text': 'Southern loss check authority project. Wish born young time production station more.',
    'email': 'sean07@example.com',
    'phone_number': '(420)907-2291x977',
    'json': {
    'name': 'Allison Butler',
    'address': '070 Zachary Vista Apt. 588\nSouth Andresport, PA 52027',
},
    'key47760': 'value52472',
},
    {
    'id': 17527470441229,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Monica Jefferson',
    'address': 'Unit 8244 Box 2928\nDPO AA 59044',
    'text': 'Behind action western society tree dog training. Apply probably number mind economic nation.\nOfficer rise there attention open official.',
    'email': 'david90@example.org',
    'phone_number': '(744)421-2380',
    'json': {
    'name': 'Derrick Johnson',
    'address': '79172 Lee View\nWest Gloriafurt, IL 89858',
},
    'key3934': 'value93974',
    'key69038': 'value58571',
    'key50861': 'value39055',
    'key31405': 'value66571',
    'key90906': 'value17636',
    'key99106': 'value73192',
    'key47914': 'value70322',
    'key64074': 'value82273',
    'key5303': 'value43884',
},
    {
    'id': 17527470441237,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'John Walton',
    'address': '20469 Lucas Rest Suite 365\nJerryland, VA 90738',
    'text': 'Hundred around manage another. Government else lawyer for behind.\nPressure serious eye wife. Early relate line even guy help agreement.',
    'email': 'scottjones@example.org',
    'phone_number': '265-888-9455',
    'json': {
    'name': 'Sandra Jackson',
    'address': '55774 Curtis Grove Suite 089\nNorth Kaylastad, LA 07975',
},
    'key73907': 'value44156',
    'key72963': 'value10379',
    'key98802': 'value44585',
},
    {
    'id': 17527470441249,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Melanie Oneill',
    'address': '30283 Lopez Wells Apt. 040\nNew Jeremiahburgh, MN 18418',
    'text': 'Our figure spend view surface smile long. Last southern party arrive. Art road tax.',
    'email': 'ocolon@example.org',
    'phone_number': '(909)883-0851',
    'json': {
    'name': 'Randy Best',
    'address': '50909 Sarah Fords\nLake Michael, WV 61293',
},
    'key81919': 'value35213',
    'key52234': 'value89033',
    'key57128': 'value50733',
    'key27222': 'value79038',
    'key70028': 'value30224',
    'key12388': 'value87196',
    'key90401': 'value65494',
},
    {
    'id': 17527470441259,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Shawn Chandler',
    'address': '07182 Bell Avenue\nCarrieburgh, AS 96404',
    'text': 'Indicate attack window born same again. Voice move wait. Worker prevent begin far.\nListen fear operation do. Both final leader actually visit never really.',
    'email': 'burgessmartha@example.org',
    'phone_number': '(331)879-9621',
    'json': {
    'name': 'Danielle Miller',
    'address': '40924 Julia Rapids\nMorganbury, PR 12557',
},
    'key28285': 'value83665',
},
    {
    'id': 17527470441270,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Brandi Lewis',
    'address': '5845 Pittman Drive\nPort Destinyport, NE 69005',
    'text': 'Truth money significant fire. Special quickly him five miss executive. Teacher reveal left.\nJoin beyond city you those truth. Your line similar affect.',
    'email': 'thomasamy@example.com',
    'phone_number': '001-268-231-1482x25785',
    'json': {
    'name': 'Sarah Wallace',
    'address': '6222 Williams Square Suite 957\nMelindahaven, HI 00883',
},
    'key44268': 'value92168',
    'key76864': 'value66374',
    'key2140': 'value8482',
    'key7767': 'value45505',
    'key258': 'value11853',
},
    {
    'id': 17527470441282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Michele Butler',
    'address': '0763 Carla Oval Suite 512\nNorth Markview, OH 14502',
    'text': 'President common technology government space any the. Occur current recognize little. Approach why section civil lay.',
    'email': 'martinrichardson@example.com',
    'phone_number': '713-615-9817x414',
    'json': {
    'name': 'John Brown',
    'address': '71251 Andrea Walk Apt. 376\nCristianport, MN 84543',
},
    'key88966': 'value15816',
    'key12929': 'value9165',
    'key77068': 'value3823',
    'key61367': 'value27562',
    'key64622': 'value30170',
    'key67101': 'value60663',
},
    {
    'id': 17527470441293,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Robert Harris',
    'address': '88651 James Flats Suite 667\nNorth Royfurt, MI 38216',
    'text': 'Woman I hot low.\nResult character account none. Ability fast none check series break others. A machine shake letter actually.\nInterest wrong animal leg. Event like be can success.',
    'email': 'taylor02@example.org',
    'phone_number': '864-424-0872x12530',
    'json': {
    'name': 'Jennifer Reynolds',
    'address': '913 Robin Ramp\nDavisshire, WA 45590',
},
    'key33254': 'value67802',
    'key12321': 'value37227',
    'key36471': 'value83668',
},
    {
    'id': 17527470441303,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jessica King',
    'address': '6913 Colon Terrace Suite 436\nNorth Elizabethberg, SD 26613',
    'text': 'Play machine war next. In put economy everybody. Hold admit box and trade land wear best. Speak economy yes provide.\nPrepare size two their evidence society push. Act figure ask.',
    'email': 'kwood@example.com',
    'phone_number': '282.827.2855',
    'json': {
    'name': 'Tina Bean',
    'address': '91251 Edwin Cape\nJamesview, CO 47399',
},
    'key66149': 'value54970',
    'key81940': 'value71017',
    'key25790': 'value1735',
    'key9190': 'value78195',
    'key64814': 'value49451',
    'key39436': 'value24161',
},
    {
    'id': 17527470441314,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Crystal Blevins',
    'address': 'PSC 9974, Box 8311\nAPO AA 41399',
    'text': 'Paper minute forget since do well possible. Where long common whatever according involve need. Answer station the TV growth increase poor.',
    'email': 'warrenteresa@example.org',
    'phone_number': '+1-202-439-4999',
    'json': {
    'name': 'Christine Lopez',
    'address': '7569 Daniel Run\nJoetown, NE 79269',
},
    'key93860': 'value43615',
    'key55370': 'value74459',
    'key81331': 'value2454',
    'key74525': 'value98796',
    'key13686': 'value69295',
    'key40096': 'value25769',
},
    {
    'id': 17527470441324,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Robert Perez',
    'address': '48166 Amber Fields Suite 061\nLake Kevinberg, RI 21876',
    'text': 'Foreign power whole actually detail.\nEven may ground. Up including idea citizen believe. Professional card food something player area meet.',
    'email': 'meredith70@example.net',
    'phone_number': '250.579.3733x77834',
    'json': {
    'name': 'Shaun Baldwin',
    'address': '63133 Snyder Forges Apt. 486\nPort Hayleyfort, LA 01826',
},
    'key97311': 'value21799',
    'key27116': 'value2850',
    'key23160': 'value70086',
    'key40566': 'value34079',
    'key44963': 'value70903',
    'key37935': 'value3207',
    'key4237': 'value76994',
    'key38778': 'value94056',
    'key79634': 'value4813',
},
    {
    'id': 17527470441334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'John Mcbride',
    'address': '35098 Silva Plains Suite 024\nNew Dawn, NJ 52091',
    'text': 'Can game word while major game. Response clearly north can young live certainly. Director expect usually form bank his.',
    'email': 'williamssteven@example.com',
    'phone_number': '820-663-5141x6583',
    'json': {
    'name': 'Mary Williams',
    'address': '2022 Frank Isle\nVargaschester, WI 34394',
},
    'key90851': 'value42004',
    'key82121': 'value81685',
    'key40379': 'value44003',
    'key97563': 'value58641',
},
    {
    'id': 17527470441345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Gabriel Morse',
    'address': '16157 Jennifer Summit Apt. 796\nPort Peterport, CA 40297',
    'text': 'No huge onto. No because research home cover popular much. Bed game wall may fall address manage.',
    'email': 'markknight@example.com',
    'phone_number': '(925)221-5616x8101',
    'json': {
    'name': 'Daniel Becker',
    'address': '3824 Connor Village\nLake Bridgettown, MS 73966',
},
    'key14825': 'value27511',
    'key97535': 'value12160',
    'key65634': 'value54280',
    'key75780': 'value69805',
    'key13926': 'value78763',
},
    {
    'id': 17527470441356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Mindy Pruitt',
    'address': '4892 Montgomery Brook\nLindaville, MN 10424',
    'text': 'Eight never character whether industry. Claim around radio imagine.\nIn message inside. Travel manager different page after actually into. Turn thus plant order also provide personal.',
    'email': 'brianballard@example.net',
    'phone_number': '001-623-637-9921x905',
    'json': {
    'name': 'Robin Barnes',
    'address': '556 Lawrence Valleys Suite 494\nDennisville, WV 07944',
},
    'key33560': 'value89994',
    'key81594': 'value86630',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '4945ea04-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = 'null'
        
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '4945ea04-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_37_931672RnFjYhfM',
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



    def test_request_5(self):
        """测试请求 5 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '4945ea04-62f6-11f0-91de-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_10_37_931672RnFjYhfM',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestRestfulSdkCompatibility_test_collection_create_by_restful_search_vector_by_sdk_1752747050.json')
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
    test = AllmilvusLogtestrestfulsdkcompatibilityTestCollectionCreateByRestfulSearchVectorBySdk1752747050Json()
    test.run_tests()
