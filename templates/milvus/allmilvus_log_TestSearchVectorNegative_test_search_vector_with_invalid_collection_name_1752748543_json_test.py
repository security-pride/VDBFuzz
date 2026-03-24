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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVectorNegative_test_search_vector_with_invalid_collection_name_1752748543_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_collection_name_1752748543.json"
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



class AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidCollectionName1752748543Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_collection_name_1752748543.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_collection_name_1752748543.json"
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
    'RequestId': 'c6317e0e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_36_003723oXyuhBsQ',
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
    'RequestId': 'c6317e0e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_36_003723oXyuhBsQ',
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
    'RequestId': 'c6317e0e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_36_003723oXyuhBsQ',
    'data': [
    {
    'id': 17527485420800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Kyle Glover',
    'address': '89907 Clark Corners Suite 906\nTimothyhaven, GA 04547',
    'text': 'Turn behavior relationship leg. Model anything leader radio.\nShe close current born one interest. Owner kid son simple sometimes affect account. Nothing benefit us best.',
    'email': 'carloscolon@example.org',
    'phone_number': '5746543387',
    'json': {
    'name': 'Nathan Cooper',
    'address': '479 Rangel Springs Suite 859\nEast James, WA 70193',
},
    'key25598': 'value23295',
    'key5661': 'value96432',
    'key63119': 'value7573',
    'key65024': 'value89896',
},
    {
    'id': 17527485420819,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Jennifer Diaz',
    'address': '81379 Davis Centers Suite 864\nNew Jason, CT 16262',
    'text': 'Which suffer mouth son forward phone age majority. Hard but less bed hot dog. Agree discuss nearly share all today easy.\nService none again story behind store. Any since tonight become born.',
    'email': 'sheppardzachary@example.org',
    'phone_number': '7465915437',
    'json': {
    'name': 'Cristian Pena',
    'address': 'Unit 9647 Box 0870\nDPO AP 08922',
},
    'key30887': 'value38632',
    'key57618': 'value39946',
    'key47360': 'value70089',
},
    {
    'id': 17527485420832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Sara Williams',
    'address': '130 Samantha Roads\nLake Shawn, WV 04208',
    'text': 'Site civil yet take toward. Drive picture picture site really summer. To yet owner instead police role. Billion speech suffer specific only institution.',
    'email': 'sarah18@example.net',
    'phone_number': '001-512-569-9811x857',
    'json': {
    'name': 'Jacob Nelson',
    'address': 'USNV Garrett\nFPO AA 81957',
},
    'key34033': 'value78492',
    'key73042': 'value43065',
    'key70692': 'value94193',
    'key87341': 'value20084',
    'key97807': 'value47004',
},
    {
    'id': 17527485420844,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jennifer Gamble',
    'address': '0332 Colleen Fort Suite 247\nOliverburgh, GU 91912',
    'text': 'Standard interest look. Appear city could state.\nSeem set pretty opportunity method across.\nMaybe your reveal left amount. Sense mind back skin reality.',
    'email': 'holly98@example.net',
    'phone_number': '(630)609-7083x165',
    'json': {
    'name': 'Judith Morgan',
    'address': '89796 Jonathan Points\nNew Davidmouth, AS 01095',
},
    'key59605': 'value97964',
    'key48160': 'value84746',
    'key51578': 'value75813',
    'key79733': 'value80034',
    'key99508': 'value24426',
    'key88237': 'value42540',
},
    {
    'id': 17527485420857,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Timothy Jimenez',
    'address': '3642 Robert Tunnel Suite 455\nEast Kenneth, IL 10448',
    'text': 'Describe dinner stage after local whom amount. Company most sport enjoy beautiful interest agreement. Along can our doctor possible get.',
    'email': 'lewisjonathan@example.org',
    'phone_number': '001-744-233-5175x23096',
    'json': {
    'name': 'James Mckenzie',
    'address': '722 Baker Ridges\nPort John, GU 39025',
},
    'key52669': 'value14255',
    'key3768': 'value73567',
    'key28567': 'value32060',
    'key55331': 'value20128',
},
    {
    'id': 17527485420871,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Maureen Cooper',
    'address': '8872 Welch Falls Suite 189\nWest Shannon, UT 81308',
    'text': 'Similar later majority born property direction him. So official indicate car use.',
    'email': 'donald31@example.org',
    'phone_number': '001-498-451-4872x24504',
    'json': {
    'name': 'Lisa Ewing',
    'address': 'USCGC Gray\nFPO AA 07460',
},
    'key33243': 'value91407',
},
    {
    'id': 17527485420883,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Shelby Clay',
    'address': '70215 Prince Path\nWest Rachel, WI 13350',
    'text': 'Home middle growth fight assume adult artist. Without college religious. White structure recently size art.\nBudget lose as traditional. Deep ok data lead city economy. Practice daughter though.',
    'email': 'kevin35@example.org',
    'phone_number': '7814434574',
    'json': {
    'name': 'Denise Ruiz',
    'address': '4692 Smith Flats\nKimberlymouth, HI 90429',
},
    'key22643': 'value17922',
    'key85548': 'value66648',
    'key36853': 'value12252',
    'key17563': 'value64360',
    'key71108': 'value66675',
},
    {
    'id': 17527485420896,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Eric Adams',
    'address': '4997 Christian Meadows\nKellymouth, TX 10869',
    'text': 'Nice management unit up former.\nLarge break conference evidence rock will. Detail become up employee modern safe college.',
    'email': 'kent12@example.org',
    'phone_number': '668-669-3236x0812',
    'json': {
    'name': 'Matthew Gonzalez',
    'address': 'Unit 0266 Box 9421\nDPO AA 89344',
},
    'key91724': 'value33316',
},
    {
    'id': 17527485420905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'James Guzman',
    'address': 'USCGC Bell\nFPO AA 95931',
    'text': 'Popular present quite police. Rule through reduce goal thought. Same bit home surface street almost.\nChoose itself building change.',
    'email': 'nicholasnguyen@example.net',
    'phone_number': '3169794063',
    'json': {
    'name': 'Christopher Clark',
    'address': '52621 Nancy Expressway\nNoahville, PW 02689',
},
    'key92920': 'value17132',
    'key56746': 'value29011',
    'key57798': 'value19578',
    'key91938': 'value70883',
    'key42683': 'value55651',
    'key23159': 'value21548',
    'key49470': 'value7813',
    'key35549': 'value61569',
    'key14862': 'value87867',
    'key82065': 'value74378',
},
    {
    'id': 17527485420915,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Heather Barrett',
    'address': '073 Barrera Shores Suite 949\nNew Mary, KS 50468',
    'text': 'Write good always wonder ready threat bank. Among law visit collection officer I culture.',
    'email': 'tylertaylor@example.org',
    'phone_number': '+1-924-956-1191',
    'json': {
    'name': 'Anthony Kim',
    'address': '78300 Dean Loop\nNew Paulmouth, DE 58891',
},
    'key60179': 'value71009',
    'key45737': 'value72176',
    'key23919': 'value82339',
    'key65032': 'value89601',
    'key77165': 'value80932',
    'key42463': 'value68324',
    'key82766': 'value49791',
},
    {
    'id': 17527485420928,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Rebecca Meyer',
    'address': '6291 Wang Pike Apt. 512\nRobertsview, LA 63858',
    'text': 'Theory different either general view recently. Avoid long analysis on.',
    'email': 'jbowers@example.com',
    'phone_number': '(417)756-8974',
    'json': {
    'name': 'Joshua Davis',
    'address': '81599 Weber Lock Apt. 000\nChristopherstad, KY 81152',
},
    'key21227': 'value21508',
},
    {
    'id': 17527485420939,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Gabriel Gray',
    'address': '44839 Christine Glens\nBrownchester, LA 61249',
    'text': 'Process good civil nation general rise tend leg.\nProvide how world there expert common. Happy along window identify design political.\nExpert sometimes like base. Name east final front.',
    'email': 'perkinscody@example.org',
    'phone_number': '+1-691-951-8433x609',
    'json': {
    'name': 'Barry Hernandez',
    'address': '0443 Teresa Trail Suite 267\nPort Davidland, CO 66970',
},
    'key31206': 'value27599',
    'key35899': 'value98344',
    'key46406': 'value84329',
    'key55804': 'value73099',
    'key70249': 'value84080',
    'key38920': 'value77266',
},
    {
    'id': 17527485420951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Joshua Jimenez',
    'address': '842 Cook Vista Suite 714\nJodiside, IL 55819',
    'text': 'Draw manager place. How pattern upon.\nGround evidence car day. Imagine particular do human study spring.',
    'email': 'wdavis@example.com',
    'phone_number': '001-851-918-2540x5932',
    'json': {
    'name': 'John Russell',
    'address': '8733 Parker Fords\nTheresashire, OH 22515',
},
    'key70741': 'value27698',
    'key81135': 'value1044',
    'key59614': 'value28553',
    'key62069': 'value61585',
    'key58660': 'value83149',
    'key84529': 'value68962',
    'key35997': 'value65427',
    'key66518': 'value4112',
    'key66755': 'value16182',
    'key5579': 'value57908',
},
    {
    'id': 17527485420963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Gabrielle Schneider',
    'address': 'Unit 0604 Box 8253\nDPO AA 73969',
    'text': 'Culture move soon. None get western research specific artist sure.\nBusiness drop apply form. Interview stock hotel party. Account quickly people he.',
    'email': 'craigshannon@example.com',
    'phone_number': '+1-204-834-0271',
    'json': {
    'name': 'Nathan Long',
    'address': '328 Morgan Union\nWest Jeff, NJ 08674',
},
    'key90259': 'value11229',
    'key63422': 'value66024',
    'key17967': 'value90830',
    'key89905': 'value56577',
    'key86585': 'value24237',
    'key78012': 'value87472',
    'key21892': 'value4314',
},
    {
    'id': 17527485420972,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Kimberly Maxwell',
    'address': 'USS Kelly\nFPO AE 42055',
    'text': 'Industry again brother marriage court main discuss next. My question court teacher. Offer their spring situation front appear.',
    'email': 'qrice@example.org',
    'phone_number': '(763)759-8636x166',
    'json': {
    'name': 'Noah Knight',
    'address': '51066 Chad Fields\nCynthiastad, CO 72271',
},
    'key88905': 'value43686',
    'key49656': 'value32169',
    'key14324': 'value40943',
    'key78791': 'value61730',
    'key38253': 'value67634',
    'key97234': 'value2584',
},
    {
    'id': 17527485420981,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Christopher Olson',
    'address': '661 Reynolds Tunnel\nHollandfort, IN 94956',
    'text': 'Doctor traditional again machine station wear. Resource from of evening offer computer. War every every better affect kind relationship.\nRest seem turn production skill. Fight ever kind share.',
    'email': 'gadams@example.com',
    'phone_number': '587-388-3841',
    'json': {
    'name': 'Megan Lopez',
    'address': '665 Mendoza Ferry Apt. 039\nMurphyfort, MS 53937',
},
    'key52009': 'value5446',
},
    {
    'id': 17527485420993,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Eric Lutz',
    'address': '7759 Villanueva Fork\nMitchellchester, CO 38521',
    'text': 'Write arm receive phone. Great glass relate environmental true high table force. Chance inside into particular into.',
    'email': 'cynthiavaughn@example.net',
    'phone_number': '801.217.3824x952',
    'json': {
    'name': 'John Diaz',
    'address': '29999 Foley Manors\nSouth Shaun, NV 69668',
},
    'key69697': 'value74941',
    'key13721': 'value32581',
    'key14100': 'value8800',
    'key64407': 'value52039',
    'key42645': 'value89530',
},
    {
    'id': 17527485421004,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Sherry Elliott',
    'address': '706 Smith Ridges\nSouth Tracy, SC 09358',
    'text': 'Leave two person. Enough until member power enough fight investment large. Likely environmental over tell of affect former real.\nCentral claim fast hour show.',
    'email': 'gabrielmason@example.net',
    'phone_number': '725.242.4529x406',
    'json': {
    'name': 'Angela Davis PhD',
    'address': '8545 Olivia Parks\nChavezmouth, MN 15172',
},
    'key52983': 'value47898',
    'key68714': 'value97936',
    'key77021': 'value29996',
    'key77516': 'value90105',
    'key28521': 'value91268',
    'key22872': 'value85054',
    'key67607': 'value76476',
    'key90545': 'value23449',
},
    {
    'id': 17527485421016,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Amanda Wilson',
    'address': '5886 Calvin Parkways\nTinaside, NY 18183',
    'text': 'Brother impact simple call stock important child. Reduce group their head attack do.\nRather particular team reach government. Word because simply message region professor.',
    'email': 'hebertamy@example.com',
    'phone_number': '924.409.0983x07886',
    'json': {
    'name': 'Dr. Eric Gutierrez PhD',
    'address': 'USS Gregory\nFPO AA 54747',
},
    'key42659': 'value74948',
    'key70385': 'value75884',
    'key62277': 'value92083',
    'key83195': 'value70406',
    'key55431': 'value93458',
    'key91388': 'value40314',
},
    {
    'id': 17527485421026,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Connie Crawford',
    'address': '606 Michael Point Apt. 413\nLake Jennifer, NY 54705',
    'text': 'Drop always staff late source discuss. Tough young style reduce. Position experience top figure officer lawyer.',
    'email': 'beardjean@example.com',
    'phone_number': '630.325.0966',
    'json': {
    'name': 'Jacob Stevens',
    'address': '3393 Garcia Junctions Apt. 180\nBrownbury, NE 01253',
},
    'key63649': 'value96683',
    'key41105': 'value92419',
    'key3645': 'value97489',
    'key40938': 'value76979',
    'key7845': 'value22686',
    'key29185': 'value4626',
},
    {
    'id': 17527485421038,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Daniel Madden',
    'address': '565 Garrett Grove Apt. 599\nJohnsonmouth, KS 23022',
    'text': 'Than foreign like economy wrong management miss. Maintain house good stock civil.\nRepresent apply leg everyone arrive investment. Minute hand economic rate leader. Opportunity police sign toward.',
    'email': 'sextontara@example.org',
    'phone_number': '001-217-652-2583x264',
    'json': {
    'name': 'Kathleen Livingston',
    'address': '687 Bradley Points\nKaitlynmouth, PW 25091',
},
    'key91521': 'value19528',
    'key43968': 'value64263',
    'key98557': 'value93794',
},
    {
    'id': 17527485421050,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Charles Whitney',
    'address': '7371 Sharon Port\nValenciaburgh, MA 57514',
    'text': 'Control human about only decade own. Eye soldier write radio. Song development the red surface town American.',
    'email': 'imccoy@example.org',
    'phone_number': '+1-919-389-4726',
    'json': {
    'name': 'Misty Perry',
    'address': '440 Powell Heights\nSouth David, FM 49923',
},
    'key46130': 'value38823',
    'key32336': 'value61764',
    'key23845': 'value38061',
    'key54961': 'value48126',
    'key47486': 'value5720',
    'key7110': 'value57734',
    'key50353': 'value3453',
    'key78274': 'value1833',
    'key48669': 'value74914',
},
    {
    'id': 17527485421060,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Curtis Mitchell',
    'address': '261 Brenda Rapid Apt. 418\nNorth Tara, RI 16623',
    'text': 'Cultural about officer feeling design spring. Institution despite remain society economic with. Father turn take behavior assume site recent.',
    'email': 'bryanbrown@example.com',
    'phone_number': '(766)701-9671x77241',
    'json': {
    'name': 'Jessica Stevenson',
    'address': '1986 Gregory Row\nLake Lynnshire, UT 75210',
},
    'key86650': 'value11719',
    'key35969': 'value66002',
    'key82116': 'value89846',
    'key25494': 'value86662',
    'key83841': 'value22220',
},
    {
    'id': 17527485421072,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Samantha Li',
    'address': '46584 Alexander Point\nMatthewview, NJ 66722',
    'text': 'Recently item meeting though.\nNature smile relationship south owner entire. If town person produce beautiful movement.',
    'email': 'nthomas@example.com',
    'phone_number': '(367)948-5064x75908',
    'json': {
    'name': 'Matthew Grant',
    'address': '48709 Brittany Ferry Suite 782\nPatelbury, MN 67631',
},
    'key2265': 'value70283',
},
    {
    'id': 17527485421082,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Adam White',
    'address': '1768 Monica Roads Apt. 341\nCoxland, VI 55841',
    'text': 'Approach seem box.\nHotel on cell include friend market travel. Fast either perhaps possible rather draw.',
    'email': 'williamsmichael@example.org',
    'phone_number': '(991)695-1989',
    'json': {
    'name': 'Michael Ward',
    'address': '54159 Sanchez Stream\nEast Davidfort, IL 67828',
},
    'key15995': 'value93047',
    'key61671': 'value46946',
    'key98839': 'value25612',
    'key28691': 'value75452',
    'key23237': 'value94819',
    'key96065': 'value96934',
    'key75449': 'value59996',
    'key91556': 'value32094',
    'key44668': 'value41045',
},
    {
    'id': 17527485421094,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Michael Stephens',
    'address': '031 Walter Stravenue Apt. 218\nNorth Lydia, OH 70970',
    'text': 'Serve manager will center value. Pm protect hold plan factor southern race. Course defense think sense Democrat mouth real. Husband front first second really really.',
    'email': 'jessica73@example.com',
    'phone_number': '213.573.4120',
    'json': {
    'name': 'Amber Mason',
    'address': '63588 Ian Brooks Apt. 399\nNelsonfort, WV 97844',
},
    'key69136': 'value48413',
    'key62235': 'value92272',
    'key46573': 'value48373',
    'key47178': 'value14410',
    'key81559': 'value99502',
},
    {
    'id': 17527485421104,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Sara Harmon',
    'address': '409 Gallegos Parkway\nParkton, OK 55487',
    'text': 'Bill face bad animal. Professor next catch artist.\nMake deal feel bed across lot. Forward quality eye foot.',
    'email': 'wrighttammy@example.net',
    'phone_number': '+1-451-638-3210x4518',
    'json': {
    'name': 'Lisa Dillon',
    'address': '934 Rogers Pass Apt. 015\nSarahaven, ME 15709',
},
    'key33196': 'value19092',
    'key62813': 'value58147',
    'key97405': 'value45529',
    'key8583': 'value74460',
    'key50629': 'value72019',
    'key99203': 'value97674',
},
    {
    'id': 17527485421116,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Robert Hobbs',
    'address': 'Unit 4898 Box 2521\nDPO AE 81161',
    'text': 'People design wife. Wind section treatment try inside end pressure. Drive spend around join group.\nPick summer no myself. Brother certainly happy. Minute record possible floor collection.',
    'email': 'oporter@example.net',
    'phone_number': '850-872-8251',
    'json': {
    'name': 'Terry Singh',
    'address': '60813 James Ports Suite 017\nJaredland, WY 87970',
},
    'key44929': 'value800',
    'key60582': 'value25010',
    'key34159': 'value60315',
    'key28030': 'value32547',
    'key76396': 'value17224',
    'key76235': 'value30049',
    'key34839': 'value63741',
    'key17843': 'value36170',
},
    {
    'id': 17527485421125,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Jonathan Poole',
    'address': '2715 Lopez Circle Apt. 496\nPort Carolmouth, MT 04758',
    'text': 'Bar capital seek threat executive weight car. How try in rule. Common fly question from speak technology stop.',
    'email': 'bridget31@example.com',
    'phone_number': '3912936100',
    'json': {
    'name': 'Eric Fowler',
    'address': '026 Richard Ports Apt. 055\nNew Stephaniehaven, IA 78534',
},
    'key18227': 'value80589',
    'key97358': 'value13520',
    'key84203': 'value8666',
    'key52592': 'value51017',
},
    {
    'id': 17527485421135,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Megan James',
    'address': '74840 James Ferry\nAshleyburgh, OR 87761',
    'text': 'Through water week seven low. Help food discuss foot citizen answer.\nAnalysis simply color music million decade up. Cost down boy indeed agreement. Night similar resource answer performance.',
    'email': 'daisy42@example.net',
    'phone_number': '(651)924-3821x3407',
    'json': {
    'name': 'Amy Hunt',
    'address': '906 Parks Corners\nTaylorport, WA 43357',
},
    'key28633': 'value13922',
    'key14773': 'value60234',
    'key92757': 'value70988',
    'key78399': 'value85616',
    'key33728': 'value75537',
    'key84055': 'value89964',
    'key92153': 'value41075',
    'key36749': 'value62552',
},
    {
    'id': 17527485421146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Victoria Miller',
    'address': '849 Ashley Mountain Suite 088\nMeghanberg, AL 41476',
    'text': 'Hotel television almost cover. News me case realize back happy play.\nProvide project human. She eye old get heavy feel particular bit.',
    'email': 'andersonwilliam@example.org',
    'phone_number': '819-833-7076',
    'json': {
    'name': 'Darius Wade',
    'address': 'Unit 5470 Box 8498\nDPO AE 42256',
},
    'key62649': 'value40484',
    'key24549': 'value91691',
    'key46421': 'value36868',
    'key82943': 'value2658',
    'key86859': 'value46991',
    'key41781': 'value5800',
    'key19385': 'value59162',
    'key41295': 'value73095',
},
    {
    'id': 17527485421155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Mandy Beltran',
    'address': '3075 Ford Club Apt. 509\nNorth Nicole, MS 23111',
    'text': 'Name ago continue contain. Product dinner art move.\nFine important base account enter this.\nMeeting film here rock chance expect west. Local respond glass tree though.',
    'email': 'blopez@example.org',
    'phone_number': '509.904.9828x9348',
    'json': {
    'name': 'Victoria Thomas',
    'address': '0161 Michael Plaza\nNew Chad, KS 65051',
},
    'key31525': 'value12184',
    'key63533': 'value67407',
    'key46608': 'value32119',
},
    {
    'id': 17527485421166,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Holly Santiago',
    'address': 'USCGC Snyder\nFPO AA 10667',
    'text': 'Only rule important group country. Pick plan conference force pattern audience ok. Between then deep put.\nMust national school itself. Measure contain economic wife.\nOk could reflect purpose college.',
    'email': 'nicolegreen@example.org',
    'phone_number': '832-434-8097',
    'json': {
    'name': 'Patricia Poole',
    'address': '18863 Ayala Highway Suite 899\nDarlenestad, FL 70761',
},
    'key61935': 'value63303',
    'key43003': 'value54888',
},
    {
    'id': 17527485421176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Rebecca Snyder',
    'address': '119 Michaela Mount Apt. 715\nNew Pamela, MT 76366',
    'text': 'Hair tax probably training religious sound various. Put turn course. Real bad foot PM.\nNote education guy church. Trade born sister. Later five either interesting weight.',
    'email': 'katievasquez@example.net',
    'phone_number': '821-612-8619',
    'json': {
    'name': 'Patrick Kim',
    'address': '68195 Martin Shoals Apt. 490\nEast Josephborough, DE 61459',
},
    'key24022': 'value19477',
    'key98678': 'value10542',
    'key89134': 'value63677',
    'key76945': 'value97322',
    'key90039': 'value25254',
    'key76501': 'value36351',
    'key55302': 'value77713',
    'key94015': 'value76221',
},
    {
    'id': 17527485421188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Jose Robinson',
    'address': '0423 Cody Rapid\nPort Dakota, CO 20083',
    'text': 'Spring too easy movie week Mr federal. Show ever store toward wear.\nQuickly study but green when. Room challenge range federal though movement who. Seat they establish effort.',
    'email': 'johnsonrobert@example.com',
    'phone_number': '001-303-273-8328',
    'json': {
    'name': 'Derrick Leon',
    'address': '5921 Samantha Ports Suite 607\nNorth Henry, NY 02408',
},
    'key18343': 'value12257',
    'key26394': 'value2958',
    'key58388': 'value64549',
    'key39944': 'value90760',
    'key86485': 'value46900',
    'key38962': 'value91740',
    'key67': 'value32356',
    'key20253': 'value78891',
    'key32314': 'value80497',
},
    {
    'id': 17527485421199,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Donald Rios',
    'address': '614 Jones Place\nLake Johnport, NJ 64618',
    'text': 'Among help result claim first. Approach prevent indicate.\nPresent all skin movement radio miss herself. Study where its soon service fact.',
    'email': 'elizabeth13@example.net',
    'phone_number': '320.815.5778',
    'json': {
    'name': 'Richard Mcdonald',
    'address': '0026 Moore Extensions Apt. 280\nLake Shaneport, MO 18879',
},
    'key28035': 'value84900',
    'key82650': 'value59457',
    'key95200': 'value59839',
},
    {
    'id': 17527485421210,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Chad Hicks',
    'address': '93016 Jennifer Estates Suite 076\nNorth Tiffanymouth, MD 53679',
    'text': 'Floor yes book two. Firm material better people nice. Political record above already.',
    'email': 'dicksondavid@example.com',
    'phone_number': '645-274-1510x8790',
    'json': {
    'name': 'Madison Chan',
    'address': '218 Shelby Curve\nCarterland, PW 23285',
},
    'key78268': 'value46931',
    'key63090': 'value89121',
    'key90207': 'value56917',
    'key11025': 'value42070',
    'key82105': 'value55139',
    'key2610': 'value88796',
    'key15660': 'value92332',
},
    {
    'id': 17527485421222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Robin Pineda',
    'address': '7691 Tyler Prairie\nNew Brandonview, PR 07971',
    'text': 'Fear once anyone produce. Traditional deal run car war.\nTrip certainly total guess talk analysis. Organization form certain third technology.',
    'email': 'deborah39@example.net',
    'phone_number': '2585170622',
    'json': {
    'name': 'Belinda Larson',
    'address': '63641 Timothy Island Suite 779\nLouisland, PW 21513',
},
    'key97063': 'value27974',
    'key48443': 'value13255',
    'key41575': 'value48456',
    'key37144': 'value41456',
    'key97358': 'value22978',
},
    {
    'id': 17527485421232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Megan White',
    'address': '9965 Peterson Park Suite 178\nDonnaland, TN 83681',
    'text': 'Big listen usually quickly. Later hospital mention conference speak her resource board.',
    'email': 'rosejames@example.org',
    'phone_number': '+1-991-679-8146',
    'json': {
    'name': 'David Sweeney',
    'address': '73689 Christopher Turnpike Suite 168\nPricemouth, ND 15334',
},
    'key2937': 'value72194',
    'key18250': 'value75242',
    'key46827': 'value37365',
},
    {
    'id': 17527485421244,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Kelly Gallagher',
    'address': '6647 Johnson Inlet Apt. 335\nMichaelfurt, HI 40434',
    'text': 'Wind painting rest authority effect seem PM. Space glass paper almost increase very east. Relate professor worry baby present.\nStory director second. Teacher team structure stand few.',
    'email': 'swashington@example.org',
    'phone_number': '285-967-8857x845',
    'json': {
    'name': 'Frank Harris',
    'address': '72172 Stevenson Crest\nNew Donaldmouth, AR 28116',
},
    'key4203': 'value51831',
    'key15284': 'value98027',
    'key84008': 'value50450',
    'key65084': 'value27567',
    'key96692': 'value31032',
    'key95855': 'value60441',
    'key85063': 'value62990',
},
    {
    'id': 17527485421255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Timothy Owens',
    'address': '9534 Elizabeth Trafficway Apt. 016\nPort Shelly, RI 29588',
    'text': 'Organization choice billion. Though discuss structure body. Defense increase general.\nAnother throw record bank food. Policy response star or. New method bring make now store church.',
    'email': 'jacksonmisty@example.org',
    'phone_number': '613-606-6042',
    'json': {
    'name': 'Tonya Baker',
    'address': '95351 Thompson Mews Suite 150\nAlexanderside, GA 99020',
},
    'key53867': 'value196',
    'key59587': 'value84736',
    'key10604': 'value88964',
    'key44884': 'value22976',
},
    {
    'id': 17527485421267,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Thomas Carter',
    'address': '8703 Joshua Green Suite 455\nLake Lisa, IN 04606',
    'text': 'Glass painting seem only support once world. Gas attorney structure money.',
    'email': 'michelle35@example.net',
    'phone_number': '001-917-705-8575',
    'json': {
    'name': 'Andrew Johnson',
    'address': '3552 Tim Ports Apt. 557\nNew Howard, TX 63933',
},
    'key25636': 'value52617',
    'key710': 'value18169',
    'key52215': 'value35989',
    'key49391': 'value69074',
    'key28787': 'value20655',
    'key62942': 'value31251',
    'key45657': 'value27351',
    'key78209': 'value29402',
    'key95414': 'value65526',
    'key38441': 'value69596',
},
    {
    'id': 17527485421288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Justin Rogers',
    'address': '596 Estes Cove\nSouth Terrence, DE 44279',
    'text': 'Dinner final put head black finish do. Prevent less together staff rather.',
    'email': 'breed@example.net',
    'phone_number': '+1-581-323-8186x506',
    'json': {
    'name': 'Natalie Walker',
    'address': '93641 Rachel Gardens Suite 022\nLake Amy, KS 39074',
},
    'key47144': 'value20999',
    'key1495': 'value7715',
    'key58312': 'value57980',
    'key11636': 'value42755',
    'key33370': 'value35484',
    'key62475': 'value65816',
    'key78400': 'value77664',
    'key72426': 'value41056',
    'key70377': 'value69187',
    'key77480': 'value90959',
},
    {
    'id': 17527485421299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kimberly Farrell',
    'address': '918 Ashlee Brooks\nEast Jacobview, DC 53159',
    'text': 'Follow thus growth race hard hard avoid career.\nLate entire ok window ball. Build situation only nothing cultural. Security data technology goal.',
    'email': 'simswesley@example.org',
    'phone_number': '+1-782-868-5972',
    'json': {
    'name': 'Lindsey Arias',
    'address': '376 Ellison Falls Apt. 391\nEast Danielmouth, GU 75304',
},
    'key71399': 'value91056',
    'key9795': 'value97251',
    'key57611': 'value84372',
    'key69764': 'value13369',
},
    {
    'id': 17527485421311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Clifford Harris',
    'address': '170 Kimberly Common\nLongshire, CT 11738',
    'text': 'Degree will kitchen line stuff allow food area. Baby growth year year. Half economy resource trouble once.\nBook consumer industry camera know.',
    'email': 'iangolden@example.net',
    'phone_number': '281.476.8653',
    'json': {
    'name': 'Heather Kim',
    'address': '824 Mata Forges Suite 502\nLake Chrisberg, VA 27026',
},
    'key93883': 'value3310',
    'key10868': 'value41279',
    'key8606': 'value56290',
    'key86559': 'value4998',
    'key6624': 'value52298',
    'key57283': 'value30230',
    'key39422': 'value9778',
},
    {
    'id': 17527485421323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Dana Hammond',
    'address': '870 Williams Flat\nLesliechester, VT 24802',
    'text': 'Color idea common clear know about leave song. Consumer live any energy.\nVoice response election imagine Mrs within. Treat bed until trade expert lead. Run win beat tree instead.',
    'email': 'nicolecraig@example.org',
    'phone_number': '+1-569-993-5551x59704',
    'json': {
    'name': 'Sara Copeland',
    'address': '53929 Jeffrey Bypass Apt. 843\nNew Pamela, UT 35163',
},
    'key80274': 'value33765',
    'key10063': 'value26191',
    'key28440': 'value81057',
    'key71425': 'value40579',
    'key64383': 'value6410',
},
    {
    'id': 17527485421335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Sandra Flores',
    'address': '4412 Wendy Canyon Apt. 684\nSouth Stevenview, TN 04653',
    'text': 'More unit raise law since or. News open occur discover.\nUntil necessary important standard no arrive. Decision include financial main.',
    'email': 'talvarez@example.org',
    'phone_number': '001-393-502-1183x93108',
    'json': {
    'name': 'Kristina Morgan',
    'address': '7284 Adams Valley\nNorth Trevor, IA 50219',
},
    'key61764': 'value65864',
    'key75597': 'value68776',
    'key43605': 'value57003',
    'key90188': 'value96337',
},
    {
    'id': 17527485421346,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'David Fisher',
    'address': '011 Gardner Gardens Suite 657\nConleyville, PA 94780',
    'text': 'Wonder from wind lay draw. Front fear care election blood that peace race.\nCold two in anyone see growth position. Material rest back land big. Herself book certain require live employee.',
    'email': 'holly07@example.net',
    'phone_number': '+1-634-263-9708x7496',
    'json': {
    'name': 'Kenneth Coleman',
    'address': '05337 Perez Trafficway\nErikborough, OH 69400',
},
    'key27735': 'value34589',
    'key94631': 'value79',
},
    {
    'id': 17527485421357,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'James Farrell',
    'address': '608 Jimmy Meadow Apt. 023\nPort Brittanybury, OR 50126',
    'text': 'Have call audience well themselves pretty. Check study speech both defense wind.',
    'email': 'gomezrobert@example.com',
    'phone_number': '001-488-853-0225x80465',
    'json': {
    'name': 'Tyler Reed',
    'address': '0345 Johnson Crossroad Apt. 552\nPort Kellyshire, MI 26522',
},
    'key64236': 'value81477',
    'key68858': 'value40387',
    'key20523': 'value214',
    'key29771': 'value38629',
    'key917': 'value75849',
    'key27857': 'value42394',
    'key51723': 'value85313',
    'key70408': 'value94822',
    'key74098': 'value43005',
    'key63798': 'value37582',
},
    {
    'id': 17527485421368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Brett Dawson',
    'address': '521 Wood Summit\nTimothyside, FM 40307',
    'text': 'Student main economy no site item.\nProduct seat add foreign writer everything. Write too raise concern quite. Group reflect serve expert suffer school.',
    'email': 'ellisanthony@example.org',
    'phone_number': '337.572.8725',
    'json': {
    'name': 'Amanda Johnson',
    'address': '14735 Maurice Groves Apt. 846\nBeckfurt, NM 35744',
},
    'key78243': 'value55667',
    'key59040': 'value70002',
    'key25599': 'value22918',
    'key20611': 'value74350',
    'key14053': 'value14834',
    'key67506': 'value39084',
    'key82758': 'value81379',
    'key1741': 'value76084',
    'key89505': 'value13124',
    'key55250': 'value30351',
},
    {
    'id': 17527485421381,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Kelly Moore',
    'address': '6116 Robin Expressway\nWest Wesleybury, MT 20107',
    'text': 'Run effort try choose join sometimes. Modern feeling box take day. Card use carry.\nCup simple dog protect management during. Learn education goal tell though later term. Whose usually foreign to.',
    'email': 'thomaslong@example.com',
    'phone_number': '001-845-854-1716x22561',
    'json': {
    'name': 'Joseph Diaz',
    'address': 'PSC 8167, Box 2998\nAPO AP 88231',
},
    'key59051': 'value20980',
},
    {
    'id': 17527485421390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Edward Vaughn',
    'address': '21184 Zuniga Trail\nJasonport, NY 85941',
    'text': 'Provide point say add. Necessary American want. Crime professional experience finally pressure central public.\nAnswer other television way. More style stuff law however.',
    'email': 'xcoleman@example.com',
    'phone_number': '750-967-0042',
    'json': {
    'name': 'Paul Munoz',
    'address': '02678 Heather Cape Suite 592\nNew Donald, AR 68664',
},
    'key88158': 'value16287',
    'key95061': 'value829',
    'key11820': 'value58935',
    'key10404': 'value5029',
    'key36068': 'value41140',
    'key25385': 'value93904',
    'key99160': 'value73157',
    'key73044': 'value11598',
    'key96919': 'value75855',
    'key74323': 'value73111',
},
    {
    'id': 17527485421401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Heather Harris',
    'address': 'PSC 6184, Box 0157\nAPO AA 07717',
    'text': 'Win no democratic to who the. When defense recognize.\nBig evidence hot toward. Yet everything perhaps present student.',
    'email': 'twilliamson@example.com',
    'phone_number': '001-517-687-2800x5117',
    'json': {
    'name': 'Christine Simmons',
    'address': '430 James Well\nNew Francisco, PR 88718',
},
    'key11612': 'value93585',
    'key49191': 'value96658',
},
    {
    'id': 17527485421409,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Kathy Mcmillan',
    'address': '9435 Madeline Camp Apt. 921\nSouth Brianport, MT 08091',
    'text': 'Example whole for plant decade color. Might raise since truth.',
    'email': 'martha79@example.org',
    'phone_number': '981-337-2333x624',
    'json': {
    'name': 'Manuel Perkins',
    'address': '9683 Jeffrey Mountain Apt. 010\nLake Nicole, OK 51784',
},
    'key51133': 'value94170',
    'key5090': 'value89396',
    'key18565': 'value19548',
    'key45343': 'value84008',
    'key16798': 'value77943',
    'key45586': 'value98432',
    'key35282': 'value48642',
},
    {
    'id': 17527485421420,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Sydney Johnson',
    'address': '03781 Christopher Islands Apt. 958\nDuranfort, HI 39776',
    'text': 'Popular exactly action participant enter. Adult us forget election source once. Agent reduce news one star without way.\nLate reach always before long. Party ask evening. Our hope hold meeting side.',
    'email': 'dixoncourtney@example.net',
    'phone_number': '737-573-6627x097',
    'json': {
    'name': 'John Anderson',
    'address': '3821 Willis Pass Suite 087\nPort Margaret, UT 01418',
},
    'key38441': 'value25368',
    'key34527': 'value21562',
    'key47364': 'value63883',
    'key75879': 'value63900',
    'key38398': 'value16895',
    'key75438': 'value7572',
},
    {
    'id': 17527485421432,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Bryan Beck',
    'address': '7433 Juan Roads Apt. 656\nPort Jacob, VT 78390',
    'text': 'Role language choice. Recently energy go strategy good become east.\nDecide water ready piece. Point recently image list. Require institution apply discussion hour big baby.',
    'email': 'vanessa00@example.com',
    'phone_number': '001-382-954-2598',
    'json': {
    'name': 'Anthony Underwood',
    'address': '698 Elaine Turnpike\nLake Jessicaland, RI 86728',
},
    'key15423': 'value84822',
    'key27412': 'value8678',
    'key97013': 'value78286',
    'key40839': 'value23217',
    'key92926': 'value30761',
},
    {
    'id': 17527485421442,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kristy Silva',
    'address': '9235 Martinez Trail\nPort Kathleentown, IA 30104',
    'text': 'Perform better degree begin age. Rate remain mind million financial. Our however pick with.',
    'email': 'smithjoe@example.org',
    'phone_number': '2369574911',
    'json': {
    'name': 'Michael Noble',
    'address': '1585 Jimenez Shore Suite 116\nSouth Marymouth, OH 52298',
},
    'key80801': 'value58819',
    'key96199': 'value47184',
    'key29975': 'value43634',
    'key37782': 'value83476',
},
    {
    'id': 17527485421454,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jessica Johnson',
    'address': '61519 Catherine Courts\nJacquelinechester, WY 49440',
    'text': 'Tree option religious end number. A quality above amount civil begin. Protect country strong policy employee exactly.',
    'email': 'warejesse@example.org',
    'phone_number': '+1-992-799-4510x6409',
    'json': {
    'name': 'Michelle Johnson',
    'address': '06734 Jennifer Mountains Suite 458\nPort Aarontown, TN 45499',
},
    'key46884': 'value95594',
    'key56765': 'value48269',
    'key77024': 'value91593',
    'key2600': 'value90089',
},
    {
    'id': 17527485421465,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Shannon Smith',
    'address': '2006 Brooks Mount Suite 837\nMatthewside, NJ 81931',
    'text': 'Do store son think reason.',
    'email': 'daltongabrielle@example.com',
    'phone_number': '419.855.1699x0320',
    'json': {
    'name': 'Troy Nelson',
    'address': '49607 Stone Street Apt. 300\nLevineborough, VI 05339',
},
    'key47057': 'value26331',
},
    {
    'id': 17527485421476,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Kelli Goodwin',
    'address': 'USNV Adkins\nFPO AA 68594',
    'text': 'Can Congress senior join rock local sport. One treat character mother court officer our.\nOnce reality field.\nDown former cut number might. Official term born radio knowledge decade.',
    'email': 'ronnienovak@example.net',
    'phone_number': '458-784-2562x490',
    'json': {
    'name': 'John Estrada',
    'address': '3397 Jared Pass Suite 556\nNorth Jamesfurt, MD 21955',
},
    'key89192': 'value36459',
    'key50731': 'value28741',
    'key26078': 'value11711',
    'key56441': 'value72914',
    'key25938': 'value81682',
    'key32569': 'value49475',
    'key15385': 'value57802',
},
    {
    'id': 17527485421487,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Vanessa Murphy',
    'address': '115 Julie Key Suite 597\nMoralesberg, LA 21180',
    'text': 'Follow successful collection arrive. Protect few only political short affect week. Voice official story street. Dinner street hear around carry left require.',
    'email': 'nball@example.com',
    'phone_number': '001-454-733-7815',
    'json': {
    'name': 'Misty Anderson MD',
    'address': '926 Robert Mountains Suite 690\nChasechester, NY 26866',
},
    'key40485': 'value69589',
    'key87005': 'value43122',
    'key12477': 'value3259',
    'key75883': 'value96560',
    'key55727': 'value33296',
    'key52996': 'value2069',
    'key40396': 'value27857',
    'key62668': 'value71187',
    'key63381': 'value22500',
},
    {
    'id': 17527485421498,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Tara Turner',
    'address': '78650 Janet Manors\nRobinsonborough, FM 86445',
    'text': 'Finally fill speak pattern part some never medical. Away our big.\nCity fight however especially finally later matter. Information capital rule perform. Read pressure movie ability us each beautiful.',
    'email': 'swilson@example.com',
    'phone_number': '+1-674-256-6336x4118',
    'json': {
    'name': 'Haley Duncan',
    'address': 'PSC 1325, Box 3446\nAPO AA 01200',
},
    'key30347': 'value81366',
},
    {
    'id': 17527485421507,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Courtney Johnson',
    'address': '305 Archer Green\nMooremouth, CO 47410',
    'text': 'Message perhaps pay much. Customer like positive girl sit base question.\nCoach bag pay defense name whether. Various single research later. Situation from hand color will gun local.',
    'email': 'jamie99@example.com',
    'phone_number': '337.310.3688x130',
    'json': {
    'name': 'Betty Goodwin',
    'address': 'PSC 4582, Box 8992\nAPO AP 68420',
},
    'key7586': 'value4285',
},
    {
    'id': 17527485421516,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Megan Brown',
    'address': '833 Paula Brook\nWhiteside, SD 65974',
    'text': 'Five direction deep less way. Which arm especially quality time eat.\nLeft determine while. Floor strong ago western add far cell. Large medical property discussion.',
    'email': 'brandon31@example.com',
    'phone_number': '(411)267-4073x8461',
    'json': {
    'name': 'Kurt Huerta',
    'address': '7374 Summer Divide Suite 251\nEmilytown, AL 53136',
},
    'key35825': 'value86895',
    'key47479': 'value13817',
    'key70070': 'value62798',
    'key20873': 'value77726',
},
    {
    'id': 17527485421527,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Leslie Dixon',
    'address': '7745 Morales Trail\nLake Bethanystad, GA 96605',
    'text': 'Mother something property head floor figure few hour.\nUntil money instead at. Record north couple interest west car.\nPopulation amount large past.',
    'email': 'nashstephanie@example.org',
    'phone_number': '5745237254',
    'json': {
    'name': 'Jenna Ray',
    'address': '126 Young Port\nWest Larrybury, WV 29133',
},
    'key72287': 'value19393',
    'key23666': 'value50157',
    'key89701': 'value32866',
    'key4005': 'value35376',
    'key23300': 'value12438',
    'key73314': 'value94840',
    'key33385': 'value16491',
},
    {
    'id': 17527485421538,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Nicholas Carroll',
    'address': '0721 Roman Groves\nLake Jamestown, MA 11882',
    'text': 'Little poor act. And evening item increase night lot huge ago. Window discussion girl Mr benefit five after.',
    'email': 'mrobertson@example.org',
    'phone_number': '(333)295-3760x838',
    'json': {
    'name': 'Scott Gordon',
    'address': '6320 Karen Squares\nWrightfort, AR 73415',
},
    'key54642': 'value76376',
    'key44765': 'value7515',
},
    {
    'id': 17527485421549,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Christopher Hall',
    'address': 'USNV Moody\nFPO AP 38820',
    'text': 'Avoid begin coach report least. Sell contain up make. Food religious close stage question east.\nOthers small agree discover ago term. Write make kind where success kitchen.',
    'email': 'kkidd@example.org',
    'phone_number': '001-283-479-4931',
    'json': {
    'name': 'Kenneth Nguyen',
    'address': 'Unit 5103 Box 2652\nDPO AE 75928',
},
    'key13631': 'value39056',
    'key12998': 'value15737',
    'key84230': 'value56607',
    'key93969': 'value43248',
},
    {
    'id': 17527485421557,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jesse Cook',
    'address': '954 Brooke Inlet\nRicestad, TN 34122',
    'text': 'Think for million hundred arrive. Arm student who western line hotel. Interview most keep would during spring.\nIncluding small film general number day. Whole positive last. Guess eat rest doctor.',
    'email': 'pchristian@example.com',
    'phone_number': '001-679-805-5058x6517',
    'json': {
    'name': 'Sherry Miller',
    'address': '502 Kayla Harbor\nRodriguezborough, HI 83907',
},
    'key61131': 'value41169',
    'key84907': 'value34647',
},
    {
    'id': 17527485421568,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Mary Hodge',
    'address': '1075 Daniel Turnpike\nEast Angela, PW 79666',
    'text': 'Serious tough machine its deep throughout office despite. Daughter customer body property.\nQuickly size pay. Better store effort parent throw. Drive hour possible travel worry.',
    'email': 'timothy53@example.org',
    'phone_number': '642.368.1135x265',
    'json': {
    'name': 'Brenda Vance',
    'address': '008 Stevens Light Apt. 372\nCastillohaven, KY 54657',
},
    'key5376': 'value31138',
    'key87820': 'value56402',
    'key57624': 'value66021',
    'key17732': 'value45971',
    'key19819': 'value3333',
    'key72871': 'value32930',
},
    {
    'id': 17527485421578,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Erin Dawson',
    'address': '27083 Matthew Estates\nJonesmouth, AR 20013',
    'text': 'Lawyer than painting because share old describe. Rather research both police. Senior rock call paper.\nExample imagine behavior never institution key morning church. Close amount west.',
    'email': 'bradleykevin@example.org',
    'phone_number': '6275076859',
    'json': {
    'name': 'Vincent Singleton',
    'address': '983 Brian Ramp Suite 770\nNorth Sara, TX 83657',
},
    'key38234': 'value14099',
    'key27372': 'value81041',
    'key52373': 'value65138',
    'key39026': 'value66896',
    'key80038': 'value3482',
    'key76665': 'value26945',
    'key40303': 'value46548',
    'key91095': 'value84943',
    'key76120': 'value84937',
},
    {
    'id': 17527485421590,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Alison Goodwin',
    'address': '0502 Colton Run Suite 809\nCaitlinmouth, AZ 33432',
    'text': 'Someone however inside situation blue a its. Difficult still window never employee similar assume. Police method fall market economy sometimes score.',
    'email': 'georgehenry@example.com',
    'phone_number': '918-896-4070x012',
    'json': {
    'name': 'Matthew Irwin',
    'address': '37362 Jessica Pass\nNorth Timothystad, SC 25030',
},
    'key80218': 'value79018',
    'key96506': 'value79925',
    'key36347': 'value20913',
},
    {
    'id': 17527485421601,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Lisa Miller',
    'address': '6042 Ortiz Parks\nEast Davidport, OR 55807',
    'text': 'Again quality factor could. Produce factor probably not factor.\nCertain decide idea page future together share training. Fill range yeah stand serve can. Cold act site physical.',
    'email': 'jacqueline85@example.net',
    'phone_number': '4076731962',
    'json': {
    'name': 'Justin Krueger',
    'address': '6370 Smith Junction Suite 648\nLake Brittany, VA 50059',
},
    'key48303': 'value65391',
    'key20421': 'value28245',
    'key12671': 'value99133',
},
    {
    'id': 17527485421612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'James Juarez',
    'address': '56182 Natasha Loop\nPort Anthonyfurt, MO 72088',
    'text': 'Coach fill street dark heart. Work authority entire quality beautiful important.\nSince include history identify. Final yourself movie task.\nMessage she mean field send.',
    'email': 'marcgreene@example.com',
    'phone_number': '(546)838-1650x5746',
    'json': {
    'name': 'Michael Kirk',
    'address': '899 Katherine Circle Suite 233\nAcostahaven, DE 75428',
},
    'key78945': 'value9849',
    'key3137': 'value6952',
},
    {
    'id': 17527485421623,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jennifer Gomez',
    'address': '58250 Kelly Ports\nNew Michaelfurt, CO 99213',
    'text': 'Meeting color discussion discuss. Hundred whose hear window. Center reduce player effort recently sister describe.',
    'email': 'stewartdana@example.com',
    'phone_number': '+1-787-473-5466x09430',
    'json': {
    'name': 'Richard Garcia',
    'address': '13001 Rice Mountains Apt. 130\nMichaelfort, AL 81794',
},
    'key8090': 'value35999',
    'key55857': 'value69979',
    'key26353': 'value8941',
    'key22866': 'value41499',
    'key77381': 'value96722',
    'key2669': 'value90882',
    'key74125': 'value82719',
},
    {
    'id': 17527485421634,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Timothy Reese',
    'address': '1344 Amber Roads Suite 134\nMelanieborough, AK 66508',
    'text': 'Writer color many every audience market. Ago leg run them once prove deep that.\nCup ball order security southern. See someone lawyer response.',
    'email': 'floydjustin@example.com',
    'phone_number': '(979)629-9270x563',
    'json': {
    'name': 'Kelsey Williamson',
    'address': 'Unit 3997 Box 5592\nDPO AA 84704',
},
    'key81407': 'value54229',
    'key2048': 'value72439',
    'key91789': 'value60748',
    'key12010': 'value54826',
},
    {
    'id': 17527485421644,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Amy Kirk',
    'address': '1143 David Pike\nHolmesview, PR 25417',
    'text': 'Fly us cover think success among. Ten wear rule parent arm near. Discuss one top guess back ball country.',
    'email': 'brandonrowe@example.org',
    'phone_number': '9528357386',
    'json': {
    'name': 'Christie Johnson',
    'address': '917 Amanda Shore Apt. 569\nNorth Masonchester, KS 14390',
},
    'key75844': 'value49299',
    'key57247': 'value4546',
    'key22612': 'value49662',
    'key21877': 'value51050',
    'key93648': 'value64255',
    'key31324': 'value14735',
    'key8226': 'value63122',
    'key5071': 'value2825',
    'key57736': 'value41030',
    'key8985': 'value97723',
},
    {
    'id': 17527485421654,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Janice Jones',
    'address': 'PSC 4524, Box 0633\nAPO AP 02305',
    'text': 'Number cause account than. Something religious audience argue page health. Economic measure clear organization most cut loss strategy.',
    'email': 'patrickspence@example.net',
    'phone_number': '833.958.0405x615',
    'json': {
    'name': 'Mary Duke',
    'address': '4681 Ashley Trail Suite 890\nSuttonhaven, HI 46150',
},
    'key60079': 'value79903',
    'key86493': 'value96211',
    'key31849': 'value92350',
    'key9584': 'value44576',
    'key61837': 'value96908',
    'key21974': 'value60907',
},
    {
    'id': 17527485421664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Lisa Buckley',
    'address': '0834 Lawrence Trail Suite 770\nAndersonland, MS 40089',
    'text': 'Condition chair product base yes family require. Government wrong reveal memory body leave. Model travel write analysis Congress.',
    'email': 'weberjill@example.net',
    'phone_number': '7203269986',
    'json': {
    'name': 'Rebecca Chan',
    'address': '00794 Brown Mall Apt. 974\nPort Melinda, TN 24595',
},
    'key76005': 'value62105',
    'key61824': 'value87327',
    'key12550': 'value94767',
},
    {
    'id': 17527485421676,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Corey Stevens',
    'address': '94158 Grant Unions\nThomasville, GU 84665',
    'text': 'Side source run magazine. Suffer west decide high produce quality likely.\nLot maybe use. Outside goal institution animal opportunity court happy.',
    'email': 'alexis16@example.org',
    'phone_number': '(939)972-1793x6116',
    'json': {
    'name': 'Jennifer Gonzalez',
    'address': '3272 Beth Orchard Suite 295\nSalazarchester, GA 98395',
},
    'key83648': 'value19050',
    'key63591': 'value15378',
    'key46468': 'value54073',
    'key70938': 'value99544',
    'key20546': 'value79184',
},
    {
    'id': 17527485421687,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Steven Williams',
    'address': '37976 Richard Rapids\nMcgeehaven, OH 10680',
    'text': 'Federal many night condition. Remain song own report call market. Source camera community difficult.\nDespite now son certainly return. Democratic practice weight open. Quite home after story.',
    'email': 'sarahlopez@example.org',
    'phone_number': '335-222-7195',
    'json': {
    'name': 'Jeremy Lowe',
    'address': '1233 Christina Fields\nMatthewton, RI 13566',
},
    'key45664': 'value95316',
    'key88367': 'value11957',
    'key73675': 'value63684',
    'key71636': 'value66117',
    'key97273': 'value43324',
    'key47025': 'value37633',
    'key92610': 'value24279',
},
    {
    'id': 17527485421698,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Nicole Montes',
    'address': '3354 Stewart Lodge Suite 897\nWest Dawnchester, LA 10055',
    'text': 'Task although huge red recently. Change movie foreign he card. Human save assume attack site relationship suffer keep. Out address heart eye.',
    'email': 'snowanne@example.com',
    'phone_number': '426-757-4163x9639',
    'json': {
    'name': 'Steven Bailey',
    'address': '43544 Townsend Bridge\nRandymouth, CA 69416',
},
    'key81701': 'value33261',
    'key98692': 'value97492',
    'key7127': 'value9362',
    'key42100': 'value19840',
    'key17847': 'value68409',
    'key89860': 'value68180',
    'key10152': 'value3647',
    'key34667': 'value99273',
},
    {
    'id': 17527485421710,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Scott Cunningham',
    'address': '65592 Carol Point\nEast Bruceville, NM 41334',
    'text': 'Staff blue entire thousand difference decide property spend. Else compare remember marriage personal. Fund gun exist sound.\nSouth continue perhaps right only.',
    'email': 'nhill@example.com',
    'phone_number': '524.699.9713',
    'json': {
    'name': 'Audrey Guerrero',
    'address': '91045 Gordon Orchard Suite 297\nCraigstad, AL 08612',
},
    'key2589': 'value12478',
    'key112': 'value258',
    'key95583': 'value21772',
    'key31712': 'value47490',
    'key58405': 'value14733',
    'key70013': 'value73388',
    'key33817': 'value5548',
    'key94885': 'value50774',
    'key98991': 'value39945',
},
    {
    'id': 17527485421721,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Evan Elliott',
    'address': '2860 Joshua Prairie Apt. 331\nWest Alexander, SC 82246',
    'text': 'Late ready military hospital assume. Price key good generation. Leave better brother important physical about task.',
    'email': 'oconley@example.net',
    'phone_number': '+1-407-774-4544x89948',
    'json': {
    'name': 'Mrs. Bethany West',
    'address': '89382 Walker Valley\nNorth Michael, VI 39505',
},
    'key51522': 'value84135',
    'key862': 'value18746',
    'key67011': 'value3389',
    'key4726': 'value63659',
    'key69236': 'value90560',
    'key78474': 'value50136',
    'key47090': 'value11366',
    'key54674': 'value71968',
    'key42002': 'value6416',
    'key47568': 'value81096',
},
    {
    'id': 17527485421732,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'John Ayala',
    'address': '3587 Steven Canyon\nSouth Debraport, ND 14229',
    'text': 'Describe walk offer pick.\nGarden glass for choose. Clear head he.\nWant anyone parent value next dinner. Before campaign from evening officer series.',
    'email': 'christopher67@example.com',
    'phone_number': '001-326-200-9757x09330',
    'json': {
    'name': 'Logan Shields',
    'address': '428 Heather Mountains\nPort Antonioview, ME 00702',
},
    'key22314': 'value14170',
    'key39344': 'value23448',
},
    {
    'id': 17527485421742,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jose Jordan',
    'address': '78613 Flores Course Apt. 407\nCarlsonport, PA 12108',
    'text': 'Treatment before know nearly professional bit have. Over trip huge interview difference.',
    'email': 'morganpeter@example.com',
    'phone_number': '(495)615-8694x0150',
    'json': {
    'name': 'Victor Sutton',
    'address': '27073 Davenport Lodge\nNorth Joshua, OK 83281',
},
    'key94102': 'value73288',
},
    {
    'id': 17527485421753,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Timothy Smith',
    'address': '821 Andre Loop\nNew Nathan, NC 90674',
    'text': 'Gun say trial couple throw question tell. Cover point line ability feel office. Drug future do white.\nOne significant put today million.',
    'email': 'finleyjerry@example.org',
    'phone_number': '816-936-2415x2381',
    'json': {
    'name': 'Shelly Herring',
    'address': 'Unit 3511 Box 1723\nDPO AA 75588',
},
    'key26968': 'value48012',
    'key94278': 'value99515',
    'key13324': 'value5320',
    'key65314': 'value68297',
    'key81230': 'value42895',
    'key886': 'value27485',
    'key55642': 'value1414',
},
    {
    'id': 17527485421762,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Jill Brown',
    'address': '9484 Carpenter Point\nPort Cheryltown, KY 56696',
    'text': 'Six world three short style offer. Some our nearly sell. Behavior rock degree whole buy now.\nWhom group join. Television performance marriage whether deep fund.',
    'email': 'jevans@example.org',
    'phone_number': '001-551-334-1019',
    'json': {
    'name': 'Paige Sharp',
    'address': '459 Melton Corner\nNorth Joseph, MT 81916',
},
    'key93522': 'value53762',
    'key37310': 'value47366',
    'key54987': 'value53563',
    'key3299': 'value16868',
    'key97628': 'value70901',
    'key93309': 'value90293',
    'key96371': 'value17750',
    'key86758': 'value26185',
    'key73819': 'value90767',
    'key54916': 'value3079',
},
    {
    'id': 17527485421773,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Jennifer Wallace',
    'address': '1301 May Common\nDavidhaven, IA 60896',
    'text': 'Gun point surface show woman. Actually accept affect. Bad result sure they radio new none.\nLater nor court address. Like loss spring wait stay per.',
    'email': 'palmerlisa@example.org',
    'phone_number': '(678)840-7879x586',
    'json': {
    'name': 'Carlos Cohen',
    'address': '3155 Adrian Ford Suite 050\nNorth Donnahaven, VI 81616',
},
    'key48650': 'value20938',
    'key58364': 'value71156',
},
    {
    'id': 17527485421784,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Kenneth Kerr',
    'address': 'PSC 4427, Box 9994\nAPO AA 54874',
    'text': 'Recent movie pull leader consider middle. Guess detail cover need ago run successful film.',
    'email': 'danielclay@example.com',
    'phone_number': '5529882892',
    'json': {
    'name': 'Larry Johnson',
    'address': '3610 Jose Pass Apt. 878\nMichaelland, CT 82309',
},
    'key90321': 'value66884',
    'key47200': 'value62253',
},
    {
    'id': 17527485421793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Ryan Wong',
    'address': '35014 Crane Terrace Suite 210\nNew Dylanhaven, NM 29728',
    'text': 'Discuss top get heart treatment commercial local at. Quickly per so affect. Color piece white forget west ten sort fight.',
    'email': 'staceyroach@example.net',
    'phone_number': '(441)425-2746x39056',
    'json': {
    'name': 'Colleen White',
    'address': '546 Smith Brooks Suite 942\nMasonstad, PW 93366',
},
    'key17998': 'value72712',
},
    {
    'id': 17527485421805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Michelle Phillips',
    'address': '38344 Esparza Place Suite 058\nRachelburgh, DC 36026',
    'text': 'Again him piece baby. Eat prove black day fine lot page military. Them popular time smile necessary dream scene action.\nStock view agree peace nothing surface. Remember grow my capital officer all.',
    'email': 'sean33@example.com',
    'phone_number': '+1-854-752-6702',
    'json': {
    'name': 'Emma Bradley',
    'address': '785 Thomas Square Suite 158\nRobertshire, IL 08431',
},
    'key13115': 'value55481',
},
    {
    'id': 17527485421815,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Janet Delgado',
    'address': '3276 Darren Drive\nLake Benjaminton, NM 42935',
    'text': 'Hour ten sing sign all give must.\nCar story kid. Do anyone eye nature moment any top. Whose less someone trade reflect reach.',
    'email': 'andrewgordon@example.com',
    'phone_number': '(703)640-3247x61210',
    'json': {
    'name': 'John Olson',
    'address': '127 Meghan Vista Apt. 832\nEast Nicole, ME 10564',
},
    'key44207': 'value77519',
    'key61252': 'value11070',
    'key73953': 'value47362',
},
    {
    'id': 17527485421827,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Sean Valdez',
    'address': '3766 Gonzalez Plaza\nJudithchester, OR 56969',
    'text': 'Various stuff rule by both walk. Remember executive white happy idea later next factor. Return management become financial be must peace hand.',
    'email': 'qtorres@example.net',
    'phone_number': '809.301.6292x2143',
    'json': {
    'name': 'Jose Woods',
    'address': '382 Mullins Fields Suite 477\nKellyside, TX 41567',
},
    'key57509': 'value29090',
    'key85379': 'value67096',
    'key93078': 'value59022',
    'key95557': 'value79539',
    'key83699': 'value375',
    'key76399': 'value51633',
    'key26333': 'value66279',
    'key15913': 'value57304',
    'key68716': 'value61556',
    'key1816': 'value91313',
},
    {
    'id': 17527485421838,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Chloe Figueroa',
    'address': '470 Erica Estate\nEast Barbara, PR 61081',
    'text': 'Indeed any manager skin much old image. And message major son couple none ahead. Born expect join himself clearly.',
    'email': 'kimberly66@example.org',
    'phone_number': '(922)293-8848x1944',
    'json': {
    'name': 'Donna Gonzales',
    'address': '878 Sweeney Port\nNeilland, GA 98461',
},
    'key22869': 'value93210',
    'key72338': 'value83211',
    'key78304': 'value66197',
    'key18648': 'value84308',
},
    {
    'id': 17527485421848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Jessica Key',
    'address': '77175 Young Mills\nSoniaside, NE 85964',
    'text': 'Build again rock eye.\nStrong modern system television difficult mother foot bed. Ask quite machine TV fight exactly.',
    'email': 'johnmartin@example.org',
    'phone_number': '001-740-345-1882x27503',
    'json': {
    'name': 'Shawn Smith',
    'address': '046 Barber Turnpike\nEast Erika, MH 48561',
},
    'key65979': 'value34397',
    'key889': 'value33029',
    'key99125': 'value52505',
    'key33038': 'value60572',
    'key32334': 'value76301',
    'key5061': 'value34896',
    'key94082': 'value99468',
},
    {
    'id': 17527485421859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Sonya Davis',
    'address': '62522 Cynthia Bridge Suite 457\nJoshuafort, CO 70142',
    'text': 'High six indicate buy mother.',
    'email': 'johnharrison@example.com',
    'phone_number': '001-687-497-4198x7143',
    'json': {
    'name': 'Michael Potts',
    'address': '541 Taylor Track\nWest Jamesmouth, MP 73186',
},
    'key7114': 'value49565',
    'key60950': 'value15792',
    'key18772': 'value89042',
    'key56017': 'value88365',
    'key89404': 'value66069',
},
    {
    'id': 17527485421870,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Ashlee Frazier',
    'address': '524 Sharon Lodge\nSouth Jonathonside, FM 59537',
    'text': 'Present everybody own will Mr since her. Century option sort door power star adult. Later message her friend interest scientist turn adult.',
    'email': 'tamara78@example.org',
    'phone_number': '001-737-947-4462x9560',
    'json': {
    'name': 'Deborah Douglas',
    'address': '9852 Shane Centers Apt. 905\nWilliamstad, KS 89425',
},
    'key49263': 'value7578',
    'key96653': 'value13564',
    'key68057': 'value8358',
    'key57739': 'value29809',
    'key20502': 'value43941',
    'key15856': 'value87844',
    'key7240': 'value5380',
    'key89969': 'value18016',
    'key34448': 'value36046',
    'key14243': 'value52767',
},
    {
    'id': 17527485421880,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Charles Savage',
    'address': '86605 Kathleen Spring\nPort Patrick, NH 32508',
    'text': 'During smile north big. Tv design inside how rather practice.\nConcern shoulder second for son. Under even here need bar us Mrs TV.',
    'email': 'stevenbrown@example.org',
    'phone_number': '248.416.6041',
    'json': {
    'name': 'Kyle James',
    'address': '69472 Lori Drive\nNorth Donald, KS 45356',
},
    'key27194': 'value48876',
    'key99309': 'value31893',
    'key47574': 'value8918',
    'key39628': 'value71348',
    'key17408': 'value48528',
    'key21136': 'value99607',
    'key16274': 'value22576',
},
    {
    'id': 17527485421892,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Frank Brown',
    'address': '04296 Huang Neck\nPort Robert, CT 14224',
    'text': 'Commercial father newspaper since follow. Early live pressure sing so wrong. Business forget someone they identify final quality.',
    'email': 'meghanmitchell@example.org',
    'phone_number': '(332)245-0473',
    'json': {
    'name': 'Jessica Howard',
    'address': '711 Scott Ways\nWest Jesse, OR 73057',
},
    'key36585': 'value6027',
    'key62080': 'value33731',
    'key90023': 'value78468',
    'key74003': 'value79624',
    'key79722': 'value82134',
    'key37568': 'value49908',
    'key98462': 'value76413',
    'key4767': 'value66800',
    'key23010': 'value36249',
    'key82626': 'value31078',
},
    {
    'id': 17527485421903,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Annette Lowery',
    'address': '5093 Hall Courts\nAmyshire, CO 49406',
    'text': 'Notice put send through. Consider address unit model. Factor plant course sort region occur end design.\nReality yeah agreement. Second raise decade end evening join physical.',
    'email': 'murphyshawna@example.com',
    'phone_number': '+1-954-956-7861x716',
    'json': {
    'name': 'Frances Morris',
    'address': '65552 Contreras Key Apt. 138\nWilkersonport, PW 79807',
},
    'key12597': 'value57583',
    'key2884': 'value81588',
    'key12586': 'value42974',
    'key77922': 'value27918',
    'key53493': 'value70225',
    'key81840': 'value82759',
    'key58623': 'value83506',
    'key40781': 'value55270',
    'key82865': 'value30297',
    'key79536': 'value91173',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': 'c6317e0e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'invalid_collection_name',
    'data': self.mutator.generate_float_array(dimension=128, normalized=True),
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'address',
    'uid',
    'email',
    'json',
],
    'filter': 'uid >= 0',
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
    'RequestId': 'c6317e0e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_35_36_003723oXyuhBsQ',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVectorNegative_test_search_vector_with_invalid_collection_name_1752748543.json')
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
    test = AllmilvusLogtestsearchvectornegativeTestSearchVectorWithInvalidCollectionName1752748543Json()
    test.run_tests()
