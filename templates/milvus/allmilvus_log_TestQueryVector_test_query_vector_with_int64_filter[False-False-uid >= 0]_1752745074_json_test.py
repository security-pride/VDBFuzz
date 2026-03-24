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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752745074_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752745074.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid01752745074Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752745074.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752745074.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'afc2b408-62f1-11f0-9004-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_41_389724BhKjpica',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
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
    'RequestId': 'b2e3b5b9-62f1-11f0-b1be-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_41_389724BhKjpica',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Tonya Wright',
    'address': '934 Karen Vista Suite 560\nGarciashire, NE 29246',
    'text': 'College behind investment card become environmental.\nImportant peace then attack. Sound true decide blood range school.',
    'email': 'jbrown@example.com',
    'phone_number': '931.655.9306x6592',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robert Price',
],
    'json': {
    'name': 'Latoya Nguyen',
    'address': '440 Debra Keys\nSalazarfort, MI 75824',
},
    'key22101': 'value96935',
    'key65721': 'value84851',
    'key10747': 'value82858',
    'key14328': 'value90449',
    'key92557': 'value99335',
    'key46435': 'value50202',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Tammy Green',
    'address': '022 Zachary Junctions Suite 800\nWest Anthonyberg, NY 91992',
    'text': 'Wear company pretty whatever lead visit.\nTreatment what wife church. Firm daughter teach campaign guess order party dog. Seven three cup station go career.',
    'email': 'omclean@example.org',
    'phone_number': '001-521-709-4328',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Holmes',
    'Matthew Henderson',
    'Madison Lee',
    'Martin Fields',
    'Dominique Wade',
    'Leah Lambert',
    'James Cantu',
    'Miranda Hamilton',
    'Dustin Edwards',
],
    'json': {
    'name': 'James Smith',
    'address': '830 Patricia Meadow Apt. 050\nNew Samanthafort, AK 03532',
},
    'key68502': 'value79041',
    'key83384': 'value52045',
    'key75392': 'value68831',
    'key12210': 'value51110',
    'key17894': 'value7518',
    'key43354': 'value42698',
    'key83640': 'value21731',
    'key82304': 'value7291',
    'key73119': 'value60525',
    'key99488': 'value26267',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jeremy Vang',
    'address': '4543 Shirley Spurs Apt. 548\nOnealstad, LA 03874',
    'text': 'Others investment evening draw rest player. Woman put it coach available. Various peace various story arrive.\nPrepare film small turn image off billion.',
    'email': 'heather67@example.net',
    'phone_number': '001-548-871-3796x8935',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Charles Phillips',
],
    'json': {
    'name': 'Jodi Larsen',
    'address': '295 King Green Suite 452\nNorth Adam, PR 29399',
},
    'key20617': 'value51633',
    'key75492': 'value93480',
    'key73912': 'value95035',
    'key79168': 'value25365',
    'key97223': 'value2834',
    'key62413': 'value65330',
    'key11187': 'value99260',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Emma Schwartz',
    'address': '4154 Valerie Parks\nJohnsonfort, KS 71550',
    'text': 'Development agreement base treat simple treatment stock spend. Church easy throughout receive money college lawyer. Together than possible second analysis need.',
    'email': 'lameric@example.com',
    'phone_number': '(203)286-0038x17224',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Anderson',
    'Danielle Boone',
],
    'json': {
    'name': 'Aaron Barker',
    'address': 'PSC 7299, Box 5969\nAPO AA 41529',
},
    'key59594': 'value74897',
    'key50098': 'value18370',
    'key729': 'value81521',
    'key85816': 'value25996',
    'key2636': 'value31414',
    'key98280': 'value57063',
    'key43836': 'value75895',
    'key92836': 'value35203',
    'key75001': 'value43429',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Dustin Hernandez',
    'address': '4338 Murphy Well\nHodgesfort, OK 30842',
    'text': 'Can character current together leader. Style can support. Fire may just foreign resource down responsibility.\nBase pull drug foot billion candidate. Main about former beautiful everything should.',
    'email': 'patrickblackburn@example.com',
    'phone_number': '+1-472-889-9366x26338',
    'array_int_dynamic': [
    22107,
],
    'array_varchar_dynamic': [
    'Kimberly James',
    'Melissa Hart',
    'Mr. Louis Chavez DDS',
    'Dr. Paige Patrick',
    'Dwayne Kelley',
    'Aaron Lynn',
    'Teresa Evans',
    'Jennifer Clark',
    'Whitney Patterson',
    'Alexis Harrison',
],
    'json': {
    'name': 'Russell Boyle',
    'address': 'Unit 0666 Box 4885\nDPO AE 15231',
},
    'key23759': 'value12242',
    'key92197': 'value13066',
    'key23891': 'value70530',
    'key71501': 'value65761',
    'key69317': 'value46429',
    'key79714': 'value23116',
    'key45327': 'value87447',
    'key55453': 'value20914',
    'key49891': 'value18710',
    'key29822': 'value93431',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'George Bradley',
    'address': '80048 Gardner Forks\nNorth Jose, AR 98203',
    'text': 'Chance either rule central argue charge task. Democratic official father answer responsibility. Nice receive wall property star discuss.',
    'email': 'seanmccarthy@example.org',
    'phone_number': '+1-691-782-9914x3193',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Moore DVM',
    'Jared Harris',
    'Patricia Moore',
    'Robert Gonzalez',
    'Cameron Duran',
    'Frederick Thomas',
],
    'json': {
    'name': 'Frederick Mitchell',
    'address': '6903 Alexa Meadows Apt. 743\nWest Leonshire, MA 98124',
},
    'key26010': 'value65559',
    'key47636': 'value1601',
    'key51191': 'value95094',
    'key64813': 'value77550',
    'key41694': 'value80802',
    'key22818': 'value21371',
    'key40618': 'value61853',
    'key45865': 'value75601',
    'key73813': 'value81090',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Antonio Thomas',
    'address': '88480 Campbell Valleys\nNorth Phillip, LA 47701',
    'text': 'Not first quickly. Standard me none school send activity think.\nPossible score here without result between manager. Itself court situation politics inside.',
    'email': 'williamsmegan@example.net',
    'phone_number': '+1-962-972-9953x01477',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Johnny Rowe',
    'Sharon Dickerson',
    'Kyle Rios',
    'Steven Murphy',
],
    'json': {
    'name': 'Jennifer Campbell',
    'address': '3356 Joseph Summit\nAshleyview, MT 47081',
},
    'key7588': 'value39985',
    'key21768': 'value16212',
    'key9019': 'value12775',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Joseph Grimes',
    'address': '789 Adams Harbor\nNew Robert, MP 93981',
    'text': 'Together career response dark magazine card discussion. Response every yeah hospital test.\nPaper sure close they. Public mouth bank baby.',
    'email': 'robertsmall@example.com',
    'phone_number': '(985)226-3703',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Troy May',
    'Angel Daniel',
    'Kimberly Bray',
],
    'json': {
    'name': 'Kathy Cantu',
    'address': '37732 Reynolds Bridge\nEast Jacobberg, KY 95524',
},
    'key95505': 'value89762',
    'key47326': 'value46362',
    'key46044': 'value62633',
    'key19287': 'value25432',
    'key95365': 'value53190',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Robert Parker',
    'address': '8400 Carolyn Fords Suite 732\nNew Alexbury, MD 31038',
    'text': 'Heavy either ago whole. Life I program as nearly. Recent specific will.\nInformation discussion the nation. Box service so company.',
    'email': 'brittany02@example.com',
    'phone_number': '(636)738-7522x471',
    'array_int_dynamic': [
    20246,
],
    'array_varchar_dynamic': [
    'Robert Fowler',
    'Paul Thompson',
    'Lisa Fleming',
    'John Mitchell',
    'Dylan Owens',
    'Jill Hill',
    'Nathaniel Weaver',
    'Leslie Sullivan',
    'Terry Buchanan',
    'Jacob Fuentes',
],
    'json': {
    'name': 'Charles Mcbride',
    'address': '58501 Hunter Islands Apt. 081\nDavisville, MD 50916',
},
    'key20816': 'value38002',
    'key20610': 'value37964',
    'key14338': 'value81196',
    'key4554': 'value61529',
    'key28134': 'value23036',
    'key3518': 'value38773',
    'key55015': 'value4731',
    'key80799': 'value83317',
    'key64459': 'value31756',
    'key65574': 'value85951',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Richard Fleming',
    'address': '09585 Hogan Burgs Apt. 495\nEast Mark, WY 37249',
    'text': 'Thing second both probably different. He red education despite rock room. Class plan least professor though discover allow.',
    'email': 'megan45@example.com',
    'phone_number': '2697353601',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Laura Hernandez',
    'Brian Campbell',
    'Randy Burton',
],
    'json': {
    'name': 'Douglas Gallagher',
    'address': 'USCGC Shepherd\nFPO AP 48414',
},
    'key6422': 'value71159',
    'key96043': 'value32033',
    'key46444': 'value16682',
    'key10398': 'value91250',
    'key51281': 'value52966',
    'key13621': 'value26692',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Sandra Thompson',
    'address': '34654 Kimberly Glens\nPeggyberg, VI 65206',
    'text': 'Now figure others check gas identify design. Water total company campaign sit best image. Cup easy material whatever picture commercial.',
    'email': 'clifford09@example.net',
    'phone_number': '580-329-6188x0813',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Evan Odom',
    'Brian Murray',
    'Kathleen Wells',
    'Stephanie Morgan',
    'Micheal Hernandez',
    'Carrie Flores',
    'Dana Moore',
    'Kathleen Russell',
    'Jessica White',
    'Sandra Medina',
],
    'json': {
    'name': 'Taylor Collins',
    'address': '2533 Elizabeth Glen Apt. 461\nNew Sheliachester, WV 54397',
},
    'key4010': 'value26239',
    'key77571': 'value64126',
    'key5491': 'value18912',
    'key76568': 'value88828',
    'key7202': 'value41531',
    'key74492': 'value95674',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Manuel Nelson',
    'address': '60373 Maynard Station Apt. 074\nBrandontown, MH 18942',
    'text': 'Detail physical more foreign economic sport key mention. Well believe good message.\nMy item goal. Chance improve kind instead alone significant good. Tell enough social since.',
    'email': 'stanleymichelle@example.com',
    'phone_number': '001-536-897-7185x8715',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Austin Norris',
    'Matthew Baker',
    'Ryan Scott',
],
    'json': {
    'name': 'Elijah West',
    'address': '120 Wolfe Mews\nTammyberg, MP 26831',
},
    'key10850': 'value93176',
    'key2258': 'value61246',
    'key17070': 'value52967',
    'key5284': 'value94957',
    'key43125': 'value91883',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Mr. Daniel Jackson Jr.',
    'address': '68009 Brown Crossroad\nEast Jacobhaven, CT 75749',
    'text': 'Scene hand local.\nWorker party break when. Network voice dinner than. To vote by foot.\nStand building finish third discussion. Produce house add weight ask consider tough.',
    'email': 'rprice@example.org',
    'phone_number': '001-219-699-8318',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Colin Fletcher',
    'Brooke Parker',
    'Erik Rice',
    'Anita Armstrong',
    'Lawrence Burgess',
],
    'json': {
    'name': 'Jennifer Hernandez',
    'address': '259 Jason Stravenue Suite 429\nLake Mindyton, DE 36380',
},
    'key97616': 'value13370',
    'key55910': 'value54437',
    'key71001': 'value72902',
    'key68566': 'value63117',
    'key93234': 'value94560',
    'key38234': 'value79339',
    'key15171': 'value84263',
    'key7088': 'value30318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Janet Franklin',
    'address': '026 Thompson Divide\nSarachester, WV 49533',
    'text': 'Herself think check blue assume. Data open left throw her. Throw first mouth shake civil traditional office.\nExpect we send on stay later clear. Between claim laugh.',
    'email': 'yolandamartinez@example.org',
    'phone_number': '836.732.3388x08186',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Edwards MD',
    'Mary Pham',
    'David Brady',
    'Mrs. Pamela Werner MD',
],
    'json': {
    'name': 'Kimberly Davis',
    'address': '0130 David Common Suite 672\nSouth Brianna, NV 30539',
},
    'key32738': 'value59536',
    'key75416': 'value57971',
    'key19786': 'value66935',
    'key170': 'value18811',
    'key34607': 'value7039',
    'key63416': 'value71686',
    'key47910': 'value67155',
    'key6697': 'value68116',
    'key4728': 'value97583',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Brian Jackson',
    'address': '7469 Carrillo Spring\nMooreton, NM 11133',
    'text': 'Include green training bag thing happy we run. American how laugh grow seven woman. Arrive speech speak finish hour voice.\nWill white money. All tax perhaps. Future throw what whom pull.',
    'email': 'chad44@example.com',
    'phone_number': '514.342.3713',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Heather Richards',
    'Pamela Nguyen',
    'Donald Johnson',
    'Shawn Bradley',
    'Joan Hardy',
    'Scott Johnson',
    'Courtney Becker',
    'Gregory Castro',
    'Bonnie Rivera',
],
    'json': {
    'name': 'Thomas Perry',
    'address': '334 Brady Burg\nPort Ryanhaven, TX 25948',
},
    'key74357': 'value65057',
    'key43646': 'value10505',
    'key92991': 'value29356',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Lauren Palmer',
    'address': 'USCGC Chapman\nFPO AP 93014',
    'text': 'School peace where future anything color total. Ever toward between identify any fund a.\nAlready western carry institution. Eight Mr become business standard.',
    'email': 'nicole20@example.org',
    'phone_number': '(918)450-0729x81546',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Hartman',
],
    'json': {
    'name': 'Olivia Brown',
    'address': '8716 Robert Coves Apt. 007\nAlyssaside, OH 89874',
},
    'key69612': 'value1329',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Austin Jenkins',
    'address': 'PSC 2909, Box 0863\nAPO AE 49697',
    'text': 'Fish more get Democrat first somebody effort ready. Along player something energy.\nStill may trip blood yeah lead we. Entire seem time party.',
    'email': 'julia18@example.org',
    'phone_number': '(343)431-6832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alex Sanford',
    'Victoria Acosta',
    'Nicole Kim',
    'Megan Ochoa',
    'Elizabeth Mcknight',
    'Adrian Long',
    'Autumn Frazier',
    'Alexandra Wallace',
],
    'json': {
    'name': 'Juan Price',
    'address': '76160 Mary Crossing\nRochafort, TN 97019',
},
    'key38336': 'value23981',
    'key9588': 'value91689',
    'key92309': 'value83855',
    'key35033': 'value24810',
    'key94976': 'value88088',
    'key32384': 'value74148',
    'key72750': 'value50470',
    'key76245': 'value31371',
    'key76581': 'value27077',
    'key83531': 'value43737',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Phillip Wright',
    'address': '048 Mallory Wall Apt. 541\nEast Shane, PW 29244',
    'text': 'Light organization administration now especially away. Direction save speech per attorney collection. Popular various hold threat. Stay ago sense card popular hair morning.',
    'email': 'batestimothy@example.org',
    'phone_number': '2558313061',
    'array_int_dynamic': [
    15807,
],
    'array_varchar_dynamic': [
    'Heather Parker',
    'Patrick Wells',
    'Dana West',
    'Paul Harris',
    'Patricia Jenkins',
    'Krista Allison',
    'Mark Williams',
],
    'json': {
    'name': 'Richard Burch',
    'address': '2036 Hodge Shores Suite 470\nEast Danaport, AZ 78374',
},
    'key60392': 'value3161',
    'key85132': 'value24258',
    'key37340': 'value86015',
    'key8293': 'value20803',
    'key51623': 'value29976',
    'key27797': 'value59159',
    'key39880': 'value55793',
    'key83297': 'value28564',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'James Powers',
    'address': '68506 Mary Cliff Suite 695\nJacksonborough, DE 87402',
    'text': 'Strategy report upon several drop international choose. Bank business appear somebody wall recognize. Card player evidence. Beat discussion collection stand box cause.',
    'email': 'reynoldssteven@example.org',
    'phone_number': '001-241-334-2980x380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Lawrence',
],
    'json': {
    'name': 'Willie Duffy',
    'address': '132 Brittany Way\nToddside, PW 64078',
},
    'key52141': 'value23186',
    'key12911': 'value40285',
    'key87568': 'value88499',
    'key69983': 'value4396',
    'key81439': 'value80834',
    'key69620': 'value30540',
    'key29479': 'value55055',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'John Fisher',
    'address': '46717 Wendy Corners\nLake Carmen, TX 48855',
    'text': 'Despite expect stand one agree. Opportunity exactly allow ago green wear.\nBig mother sometimes yeah recent travel. Entire college hundred energy today today.',
    'email': 'schwartzjessica@example.com',
    'phone_number': '702-417-0781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Keith Martin',
    'Kristin Wheeler',
    'John Holland',
    'Randy Elliott',
    'Benjamin Benson',
    'Sharon Jones',
    'Jose Sanders',
],
    'json': {
    'name': 'Debra Kelley',
    'address': '252 Bean Extensions Suite 558\nParkershire, TN 92991',
},
    'key45790': 'value81822',
    'key4117': 'value55347',
    'key18251': 'value43979',
    'key7971': 'value12603',
    'key62500': 'value45164',
    'key55759': 'value31689',
    'key64056': 'value83596',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Adam Brown',
    'address': 'Unit 3947 Box 4651\nDPO AA 55886',
    'text': 'Bank miss western his general sure. Politics similar live give serve show bed.',
    'email': 'anthonyproctor@example.com',
    'phone_number': '001-260-568-0165',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Angela Martin',
    'Kristen Navarro',
    'Karen Bernard',
    'Charles Barber',
    'Brian Frey',
    'Laura Ramos',
    'Sarah Randall',
    'Walter Ruiz',
    'Jay Obrien',
    'Noah Vasquez',
],
    'json': {
    'name': 'Alexandria Walker',
    'address': 'PSC 3578, Box 8408\nAPO AP 82937',
},
    'key6946': 'value25140',
    'key97822': 'value95903',
    'key47641': 'value33836',
    'key13590': 'value96756',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Robin Clark',
    'address': '8325 Sandra Centers Suite 003\nNorth Stanley, KS 14319',
    'text': 'Draw any huge clear group sea. Marriage economy pick my. Decide space physical policy capital go dream.\nSix plant travel real. Team TV travel. Investment modern create population.',
    'email': 'longbrenda@example.org',
    'phone_number': '+1-789-621-1742',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Justin Mccoy',
    'Christopher Garza',
    'Joe Walter',
    'Tony Webster',
    'Stephanie Ford',
],
    'json': {
    'name': 'Zachary Robinson',
    'address': '25469 Cook Lights Suite 895\nSouth Christopherport, PW 90363',
},
    'key46848': 'value76905',
    'key99350': 'value26807',
    'key15198': 'value52994',
    'key73765': 'value5580',
    'key79220': 'value41544',
    'key15751': 'value81289',
    'key27828': 'value25740',
    'key39492': 'value7118',
    'key7305': 'value69371',
    'key32855': 'value18530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Dylan Chase',
    'address': '4220 Eddie Locks Apt. 727\nNorth Jessica, NY 42246',
    'text': 'President myself letter remain billion. Speech trial put let history traditional imagine. System animal from newspaper human oil trade.',
    'email': 'brooksheather@example.com',
    'phone_number': '896.407.3402',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Howard',
    'Albert Vasquez',
    'Thomas Burke',
    'Courtney Horton',
    'Donna Hill',
    'Sandra Allen',
    'Maurice Thomas',
],
    'json': {
    'name': 'Ray Lambert',
    'address': '05405 Sheppard Light\nCharlesfort, NE 78356',
},
    'key53753': 'value35301',
    'key24130': 'value46802',
    'key11077': 'value38312',
    'key29733': 'value67372',
    'key18117': 'value45512',
    'key61564': 'value93480',
    'key76691': 'value69687',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Kyle Wagner',
    'address': '96000 Foster Lake\nBryanmouth, KS 60805',
    'text': 'Public point memory say. As describe foot use really meeting down. Agency key because.',
    'email': 'kevin51@example.net',
    'phone_number': '+1-939-807-2831x46064',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Hector Wilcox',
    'Adrian Frank',
    'Hannah Mayer',
    'Christy Brown',
    'William Vazquez',
    'Randy Holder',
],
    'json': {
    'name': 'Maria Farrell',
    'address': '728 Gonzales Falls Apt. 330\nWest Lawrence, MS 93808',
},
    'key94112': 'value55087',
    'key27539': 'value53170',
    'key67420': 'value47232',
    'key82475': 'value63596',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Janet Dawson',
    'address': '284 Lane Landing\nWhiteborough, IL 47600',
    'text': 'Yourself describe ready win quickly write. Prevent ask sister.\nBody wish agree character provide project front big. Long mission avoid.',
    'email': 'cparks@example.net',
    'phone_number': '(669)328-5437x27454',
    'array_int_dynamic': [
    83089,
],
    'array_varchar_dynamic': [
    'Nancy Bowers',
    'Ashley Knight PhD',
    'Miguel Keller',
    'Cody Hull',
    'Heather Gibbs',
    'Charles Jimenez',
    'Robin Mcdaniel',
],
    'json': {
    'name': 'Mrs. Victoria Mullen DVM',
    'address': '915 Decker Knoll\nLaneberg, OH 05481',
},
    'key1856': 'value64931',
    'key38573': 'value88872',
    'key18728': 'value48430',
    'key60562': 'value67272',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Jennifer Gonzalez',
    'address': '10201 Chelsea Passage Suite 913\nEast Anthony, SC 49820',
    'text': 'Over address learn or. Agreement student huge. Skin now industry information notice month discuss.',
    'email': 'zwilliams@example.net',
    'phone_number': '(201)395-8629',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Emily Smith',
    'Patrick Crane',
    'Maria Chavez',
    'Jason Baker',
],
    'json': {
    'name': 'Summer Anderson',
    'address': 'USS Mercer\nFPO AP 44362',
},
    'key27939': 'value36498',
    'key18110': 'value48891',
    'key44835': 'value10577',
    'key78404': 'value52412',
    'key43852': 'value56250',
    'key92538': 'value54843',
    'key34452': 'value83405',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Wanda Daugherty',
    'address': '9241 Ortiz Mills\nJenniferbury, AL 28619',
    'text': 'Push difference pattern energy.\nHusband year mention past subject suffer sport. Approach final discussion reach land.',
    'email': 'brian92@example.org',
    'phone_number': '284.238.8407x57512',
    'array_int_dynamic': [
    10065,
],
    'array_varchar_dynamic': [
    'Bianca Moore',
    'Molly Johnson',
    'Sergio Yang',
    'Anthony Shepherd',
    'Terri Ferguson',
    'Sharon Stewart',
],
    'json': {
    'name': 'Lauren Griffin',
    'address': '81338 Hanson Place Apt. 530\nSouth Travisview, MA 68749',
},
    'key57450': 'value8602',
    'key39715': 'value3492',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jacob Taylor',
    'address': '34228 White Ways Suite 858\nNorth Grantstad, SC 33115',
    'text': 'Throughout interest start face me bed safe. Century skill teach total. Forward large add to response.',
    'email': 'emily34@example.com',
    'phone_number': '508.210.1657',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Bradley Johnson',
],
    'json': {
    'name': 'James Stein',
    'address': '95985 Rodriguez Cove\nTracyside, IL 27290',
},
    'key3289': 'value61176',
    'key97326': 'value7622',
    'key10968': 'value69806',
    'key67956': 'value71196',
    'key62501': 'value66857',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Walter Meyer',
    'address': '094 Jeremy Creek Apt. 702\nLarryfurt, GU 38602',
    'text': 'Ahead issue hope everything. Enjoy consumer stop teach. Former record threat sister but. Box main building receive hope.',
    'email': 'mwilliams@example.org',
    'phone_number': '420-440-9357',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jimmy Reid',
    'Kevin Castaneda',
    'Christina Poole',
    'Patrick Hayes',
],
    'json': {
    'name': 'Margaret Jackson',
    'address': '604 Delgado Mountains Suite 167\nNew Jacqueline, OK 89966',
},
    'key53407': 'value96315',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Samantha Harris',
    'address': '9806 Lauren Alley\nNew Patricia, GU 81591',
    'text': 'Speak suggest stand product soon. Kitchen too stop career establish somebody. Policy question movement number exactly society short.',
    'email': 'jason45@example.net',
    'phone_number': '+1-759-493-7774x453',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Woods',
],
    'json': {
    'name': 'Karen Miles',
    'address': 'PSC 0611, Box 8063\nAPO AP 67453',
},
    'key11748': 'value89722',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Linda Smith',
    'address': '0087 Jeanne Inlet Suite 216\nLake Kristenhaven, KS 22988',
    'text': 'Visit night most policy avoid relate language. Tree situation also art. Although after stand society especially keep west.',
    'email': 'pricecaleb@example.org',
    'phone_number': '+1-223-560-5998x1822',
    'array_int_dynamic': [
    78574,
],
    'array_varchar_dynamic': [
    'Justin Taylor',
    'Manuel Taylor',
    'David Boyd',
    'Victoria Wade',
    'Brent Newton',
    'Edwin Gomez',
],
    'json': {
    'name': 'Robin Green DVM',
    'address': '619 Jimmy Inlet\nPort Davidborough, FM 90082',
},
    'key8827': 'value32096',
    'key5412': 'value73765',
    'key32070': 'value74427',
    'key47541': 'value90741',
    'key71810': 'value27491',
    'key78023': 'value78964',
    'key8131': 'value18981',
    'key10606': 'value25458',
    'key15579': 'value76257',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Michael Anderson',
    'address': '538 David Mountain\nNew Rachel, NC 60604',
    'text': 'Cold effort need. Blue let throughout similar true likely. Staff behind PM many professor ago either.',
    'email': 'william60@example.org',
    'phone_number': '574-726-1728x965',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lawrence Wang',
    'Amber Morrow',
    'Shawn Phelps',
    'Brett Walton',
    'Edward Jordan',
    'Susan Williamson',
    'Mr. Richard Graham',
    'Deanna Aguilar',
    'Sierra Ferguson',
    'Samantha Stevens',
],
    'json': {
    'name': 'Kevin Reed',
    'address': '30685 Shannon Summit Suite 153\nAlexanderport, DE 57547',
},
    'key72883': 'value13903',
    'key852': 'value64874',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Alyssa Trevino',
    'address': '7016 Jeffrey Ford Apt. 215\nCatherinemouth, VT 23821',
    'text': 'Wrong smile heavy sit doctor. Build discuss recent big food. Energy always bad beat job notice piece.',
    'email': 'burnettbrenda@example.net',
    'phone_number': '+1-785-472-6145x844',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl Rojas',
    'Annette Smith',
],
    'json': {
    'name': 'Cassandra Young',
    'address': '41055 Smith Ranch\nSouth Franciscoville, DC 99739',
},
    'key99768': 'value24791',
    'key59063': 'value84159',
    'key48393': 'value30338',
    'key69184': 'value95905',
    'key81684': 'value62930',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Erica Lowery',
    'address': '87248 Lawrence Mews Suite 845\nNorth Shannonchester, MO 57872',
    'text': 'Sing though approach threat painting culture final. Herself test finish course man system impact.\nFire interview marriage adult approach score team. Man store nation picture artist cause.',
    'email': 'ashleymcconnell@example.com',
    'phone_number': '+1-903-942-9026',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Nguyen',
],
    'json': {
    'name': 'Adam Pham',
    'address': '5459 Amanda Centers\nNathanielside, PR 64950',
},
    'key23474': 'value85284',
    'key47499': 'value78240',
    'key46480': 'value1363',
    'key37042': 'value48870',
    'key68978': 'value88431',
    'key16833': 'value8385',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Brian Thomas',
    'address': '3738 Gardner Shores Suite 334\nJessicafort, DC 52623',
    'text': 'Above when effect your play physical. Week some something. Conference sometimes buy everyone sense night.\nBlood occur perform. Record we organization PM wrong gun or. Assume western store create.',
    'email': 'kevinanderson@example.org',
    'phone_number': '+1-825-514-6056x30082',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Rhodes',
    'Jacob Taylor',
    'Anna Rose',
],
    'json': {
    'name': 'Samantha Ochoa',
    'address': '93341 Kimberly Street\nLake Anafort, NE 35150',
},
    'key43145': 'value83897',
    'key84815': 'value33932',
    'key71014': 'value25596',
    'key44451': 'value12877',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Angela Clark',
    'address': 'PSC 1455, Box 8209\nAPO AA 49240',
    'text': 'Believe day room rule. Win expect turn. Task door like evening until wall.',
    'email': 'jennifer03@example.net',
    'phone_number': '804-768-6715x4159',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Prince',
    'Jay Washington',
    'Dawn Riddle',
    'Curtis Mullins',
    'Abigail Howell',
],
    'json': {
    'name': 'Daniel Howard',
    'address': '3159 Wolf Port\nThomasland, NC 08951',
},
    'key91720': 'value72981',
    'key2424': 'value4220',
    'key86348': 'value55569',
    'key98180': 'value72226',
    'key59514': 'value45435',
    'key89115': 'value51422',
    'key99431': 'value73807',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Jennifer Thompson',
    'address': '584 Jessica Path\nJenniferport, MT 78673',
    'text': 'Can soldier sit certainly. Seat fight finish top meet customer.\nGeneral outside generation man too cause send. Else yourself our over start knowledge.',
    'email': 'frazierkevin@example.org',
    'phone_number': '+1-642-698-9033x962',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Robin Christian',
    'Rachael Anderson',
    'Shelly Dickson',
    'Michelle Brown',
    'Angelica Davis',
    'Laura Wang',
    'Joe Cooper',
    'Hannah Warner',
    'Shelly Ellison',
],
    'json': {
    'name': 'Jill Hinton',
    'address': '24188 Richard Harbor\nJamesburgh, VI 86870',
},
    'key6693': 'value56786',
    'key37512': 'value46120',
    'key80375': 'value76450',
    'key79696': 'value31321',
    'key90805': 'value4625',
    'key58495': 'value15190',
    'key70199': 'value38136',
    'key16505': 'value29795',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Jennifer Torres',
    'address': '03951 Cheryl Wells Suite 447\nPort Susan, GU 99539',
    'text': 'Him sell way fly. Imagine voice couple.\nBecause trial prove child wall about drug. Money pull hour short.\nBest floor sport develop industry magazine. Although else environment attention.',
    'email': 'mary16@example.net',
    'phone_number': '001-459-905-1212x462',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Ortega',
    'Jill Lewis',
    'Daniel Shields',
    'Jeffery Coleman',
    'Michael Horton',
],
    'json': {
    'name': 'Megan Moreno',
    'address': '7350 Davies Underpass\nClaytontown, ME 57465',
},
    'key63764': 'value18512',
    'key71788': 'value65716',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Jennifer Tanner',
    'address': '702 Joshua Spurs\nKeyfort, OR 89047',
    'text': 'Boy position character degree plant door plan. Like whom necessary action assume than. Design dog provide where west toward good.\nCareer skill defense year over last. Smile where no toward available.',
    'email': 'chloe68@example.net',
    'phone_number': '001-503-991-8097x33531',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Garcia',
    'Grace Rivera',
    'Shelby Turner',
    'Samuel Howe',
    'Mr. Brian Martin',
    'Andrew Ramsey',
],
    'json': {
    'name': 'Daniel Gould',
    'address': '58093 Brady Glens Suite 998\nJulieview, PW 93108',
},
    'key48848': 'value60266',
    'key22221': 'value85779',
    'key37356': 'value98188',
    'key36831': 'value12995',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Blake Chambers',
    'address': '050 Newman Ferry Suite 999\nAtkinsonhaven, CO 01838',
    'text': 'Then consider issue at get discuss institution. Reality beautiful which growth. Decision allow sign economic camera. Age source network side series laugh something.',
    'email': 'esanchez@example.org',
    'phone_number': '(804)689-4455x3031',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Shane Noble',
    'Ethan Pacheco',
    'Andrew Moore',
    'Alexis Ferguson',
    'Eric Smith',
    'Victoria Huff',
    'Mr. Sean Roberson',
],
    'json': {
    'name': 'Bruce Mcclain',
    'address': '21187 Charles Rue\nLake Brooke, WY 08003',
},
    'key56955': 'value4844',
    'key4665': 'value46637',
    'key88646': 'value41123',
    'key57725': 'value54088',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Barry Wagner',
    'address': '859 Campbell Bypass Apt. 496\nNorth Huntertown, SD 57048',
    'text': 'Bring season third our face help. Issue return she official. Ball recognize allow music. Seek likely tend good shoulder particularly.',
    'email': 'dcombs@example.org',
    'phone_number': '574.576.6631x13444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kathy Holland',
    'James Chen',
    'James Harris',
],
    'json': {
    'name': 'Mitchell Santos',
    'address': '70846 Thompson Row Apt. 655\nPort Jessica, OH 48549',
},
    'key38353': 'value75882',
    'key3428': 'value57616',
    'key37698': 'value28572',
    'key42013': 'value85881',
    'key18945': 'value45625',
    'key18430': 'value33622',
    'key52788': 'value2993',
    'key93777': 'value40010',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Christina Cannon',
    'address': '583 Juan Junction\nNew Tammychester, ND 51608',
    'text': 'Could computer benefit financial brother degree. Will doctor plant similar international. Share old wait eye painting trip window.',
    'email': 'patriciasilva@example.com',
    'phone_number': '639.873.4413',
    'array_int_dynamic': [
    25401,
],
    'array_varchar_dynamic': [
    'John Estes',
    'Kara Thomas',
],
    'json': {
    'name': 'Tyler Cross',
    'address': '964 Karen Road Apt. 826\nEast Gabrielton, AR 23543',
},
    'key92658': 'value32384',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Katherine Williams',
    'address': '222 Roberto Inlet Suite 990\nStaceytown, MA 94569',
    'text': 'Poor himself price. Else week reveal generation level.\nFew PM reality lay various Congress. Ago support fear resource others new. Stop offer speak.',
    'email': 'chad57@example.net',
    'phone_number': '(380)414-1690x7323',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tim Woods',
    'Tina Garner',
    'Caleb Cooper',
    'Michael Cline',
    'Tanner Carney',
    'Sheila Key',
    'Patrick Simon',
    'Craig Johnson',
],
    'json': {
    'name': 'Alison Velasquez',
    'address': '224 William Plain Suite 804\nLuketon, CO 87521',
},
    'key89659': 'value16292',
    'key7700': 'value33647',
    'key86491': 'value99826',
    'key91057': 'value80190',
    'key83736': 'value50619',
    'key11755': 'value23887',
    'key23631': 'value46080',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Denise Jensen',
    'address': '7753 Weiss Street Apt. 673\nWest Samueltown, TN 71103',
    'text': 'Leader never day expect hit beautiful stay lot. Travel economy control teach try let.\nAlways should member hundred father prove. Ago effort form visit health hospital everybody.',
    'email': 'joshuaalvarez@example.com',
    'phone_number': '2899687048',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Scott Washington',
    'Karen Burns',
    'Douglas Williams',
    'Andrew Walker',
    'Leroy Moreno',
    'Bryan Boyd',
],
    'json': {
    'name': 'Renee Johnson',
    'address': '916 Hall Bridge\nLake Walter, NV 56846',
},
    'key37711': 'value61698',
    'key85561': 'value14898',
    'key27832': 'value25628',
    'key12476': 'value30962',
    'key1768': 'value56508',
    'key43818': 'value45059',
    'key85122': 'value72551',
    'key82426': 'value54044',
    'key61329': 'value65030',
    'key16483': 'value67246',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Mitchell Alexander',
    'address': '97011 Taylor Garden Suite 533\nEast Lindamouth, CO 98988',
    'text': 'Case bag include today. Way herself attorney beautiful language.\nBrother tax her professor very. Reduce Republican yard answer brother yeah door. Structure fact Mr gun difficult. Two budget Mr after.',
    'email': 'qtaylor@example.net',
    'phone_number': '413.502.9294x6357',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Richard Walsh',
    'Michelle Allen',
    'Lacey Matthews',
    'Katelyn Cox',
],
    'json': {
    'name': 'Lisa Simpson',
    'address': '62458 Mary Summit Apt. 453\nNew Vincentmouth, PW 04916',
},
    'key73913': 'value42661',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Kelly Rodriguez',
    'address': '3547 Robin Flat\nSouth Ryantown, PA 02266',
    'text': 'Performance tax fine hear employee allow physical so. Rich couple onto sing improve.',
    'email': 'davewells@example.net',
    'phone_number': '(960)407-2109',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Fuller Jr.',
    'Christopher Lopez',
    'Steven Marshall',
    'Keith Powell',
    'Tina Martinez',
    'Frederick Lloyd',
],
    'json': {
    'name': 'Anne Parsons',
    'address': '438 Black Plain Apt. 076\nJanetchester, GU 64299',
},
    'key99860': 'value66948',
    'key18639': 'value42711',
    'key67331': 'value38856',
    'key31483': 'value81509',
    'key31927': 'value68546',
    'key47999': 'value75236',
    'key26504': 'value282',
    'key783': 'value5801',
    'key80243': 'value48985',
    'key98189': 'value69351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Anthony Reynolds',
    'address': 'USCGC Young\nFPO AP 51159',
    'text': 'Cover middle short investment share. Rule billion people me senior car up. Per middle kitchen help work morning.',
    'email': 'patrick79@example.org',
    'phone_number': '8027892028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'John Palmer',
],
    'json': {
    'name': 'Megan Smith',
    'address': '88955 Allen Greens Apt. 137\nGonzalesside, PW 01982',
},
    'key93084': 'value96003',
    'key3092': 'value69779',
    'key87874': 'value89667',
    'key83284': 'value16463',
    'key88328': 'value70509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Kimberly Simmons',
    'address': '9317 Vaughn Isle\nRuizfurt, FL 77269',
    'text': 'Finally such court ago price. Walk action marriage. Big popular bring.\nIndicate pattern whatever economic physical medical order. Building condition top speak item.',
    'email': 'valerie61@example.com',
    'phone_number': '(553)951-5598x1825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Wendy White',
    'Mr. Jerry Brown',
    'Samantha Pearson',
    'Tami Pierce',
    'Amanda Bennett',
],
    'json': {
    'name': 'Andrea Ruiz',
    'address': '08325 Wall Meadows Apt. 599\nPort Christian, IA 67991',
},
    'key40022': 'value48946',
    'key1531': 'value70536',
    'key78140': 'value95756',
    'key41590': 'value30693',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Samuel Rodriguez',
    'address': '61148 Berry Hill Suite 881\nNew Seanside, NC 38403',
    'text': 'Account necessary interest herself wide beautiful this. Born clear alone and group through.',
    'email': 'frenchjennifer@example.net',
    'phone_number': '368-228-5155x14638',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Diaz',
    'Andre Thompson',
    'Tara Wright',
],
    'json': {
    'name': 'Brandon Morrison',
    'address': 'PSC 2262, Box 5977\nAPO AA 17852',
},
    'key57856': 'value17043',
    'key72539': 'value22753',
    'key26746': 'value28534',
    'key25339': 'value45974',
    'key43372': 'value45632',
    'key83301': 'value24929',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Theresa Taylor',
    'address': '96238 Warren Terrace\nCrosbychester, NM 97807',
    'text': 'Run large say coach on improve morning. Around send deep story else trade.\nOnly choose bag election local letter reflect.',
    'email': 'basschristine@example.org',
    'phone_number': '001-211-446-4757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Fuller',
    'Monica Cannon',
    'Heather Bryan DVM',
],
    'json': {
    'name': 'Jennifer Wilson',
    'address': '46528 Zuniga Brook Apt. 726\nVickiebury, CA 81283',
},
    'key65831': 'value8852',
    'key58898': 'value18455',
    'key17981': 'value81013',
    'key81435': 'value76746',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Sharon Jennings',
    'address': '7673 Bell Summit\nHeatherland, MH 60140',
    'text': 'Movement environment help interest as call note kind. Support structure cultural serious interesting peace. Traditional operation analysis world serve business. Finally high her.',
    'email': 'stokeselizabeth@example.com',
    'phone_number': '702.780.8123',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Seth Daniels',
    'Annette Flores',
    'Dr. Terri Price',
    'Zoe Smith',
    'Suzanne Drake',
],
    'json': {
    'name': 'Jasmin Bates',
    'address': '1061 Brittany Valleys\nLake Wendy, NH 11903',
},
    'key51517': 'value56398',
    'key14832': 'value98659',
    'key20293': 'value71057',
    'key17956': 'value54731',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Debbie Griffith',
    'address': '30381 Jensen Drive\nLake Charlesland, WY 34011',
    'text': 'Focus school your relate radio. Phone federal lead skin already. Baby single since four produce range. Card put thousand friend worry sign.',
    'email': 'fbrowning@example.net',
    'phone_number': '+1-881-714-9874x43527',
    'array_int_dynamic': [
    7867,
],
    'array_varchar_dynamic': [
    'Jeffrey Garcia',
    'Amy Davis',
    'Amy Costa',
    'Anthony Jones',
    'James Campos',
    'Juan Johnson',
    'Scott Gonzalez',
],
    'json': {
    'name': 'Holly Conley',
    'address': '960 Carroll Keys Apt. 938\nPeggyport, AL 32984',
},
    'key93708': 'value38961',
    'key54007': 'value61338',
    'key39827': 'value47282',
    'key40307': 'value67975',
    'key51475': 'value49173',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Daniel Cruz',
    'address': 'Unit 7839 Box 2927\nDPO AE 61199',
    'text': 'Fly a so direction feel. Child lose finally dog surface.\nImpact check base miss sea right expert treatment. Drop short scientist into leader forget large. Eight perform forward feel between.',
    'email': 'dsmith@example.org',
    'phone_number': '(993)233-2528',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brian Garcia',
    'Amy Lane',
    'Jeremy Duran',
    'Hannah Acevedo',
    'Austin English',
    'Denise Kelly',
],
    'json': {
    'name': 'Frank Hall',
    'address': '3428 Amy Squares\nPerryton, AZ 29814',
},
    'key98823': 'value13830',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Jennifer Anderson',
    'address': 'Unit 0199 Box 6509\nDPO AE 72870',
    'text': 'Article my heavy garden test charge no. Role former marriage building develop every.\nFocus sing anyone often throw. War own during magazine from last.',
    'email': 'hsullivan@example.com',
    'phone_number': '447.692.7700x6190',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Reyes',
],
    'json': {
    'name': 'Paul Walsh',
    'address': '03229 Christopher Street Apt. 418\nSouth Lindachester, MP 39611',
},
    'key7295': 'value95857',
    'key15699': 'value21206',
    'key78648': 'value21947',
    'key7974': 'value86711',
    'key64475': 'value73630',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Frank Mclean',
    'address': '8901 Stephanie Plains Apt. 855\nVictoriafurt, FL 41960',
    'text': 'Process process big war human rich live. Conference lead security Democrat. Company pattern generation.',
    'email': 'vincenthunter@example.net',
    'phone_number': '369-625-9807x703',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Regina Shelton',
],
    'json': {
    'name': 'Nathan Castro',
    'address': '2498 Morgan Field Apt. 931\nCraigburgh, TX 25619',
},
    'key61969': 'value73800',
    'key90551': 'value18879',
    'key82829': 'value66405',
    'key73675': 'value32913',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Alicia Hanna',
    'address': '7956 Chan Keys\nNew Terriborough, CA 55932',
    'text': 'Again send save animal news. Action value record energy.\nWear receive involve exactly child when. Congress tough whose focus general lawyer serious. Affect she small.',
    'email': 'devinhatfield@example.com',
    'phone_number': '+1-657-796-9888x879',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Allen',
    'Kathleen Gray',
    'Denise Brown',
    'Brittany Logan',
],
    'json': {
    'name': 'Heather Smith',
    'address': '1051 Kaufman Turnpike\nLake Kerriville, NY 60583',
},
    'key30563': 'value47833',
    'key7722': 'value11145',
    'key89748': 'value82196',
    'key84408': 'value75819',
    'key96533': 'value41447',
    'key75189': 'value60893',
    'key69022': 'value36174',
    'key83204': 'value9650',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Patricia Mueller',
    'address': '12841 Jimenez Fort\nSouth Gregory, GU 12232',
    'text': 'Base type gas hold woman scientist race example. Fact green forward for.',
    'email': 'ospencer@example.net',
    'phone_number': '370-767-6310x060',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Johnny Davila',
    'Rhonda Harris',
    'Michael Clark',
    'Mary Walker',
    'Brandon Allen',
    'Daniel Simmons',
    'Michelle Williams',
],
    'json': {
    'name': 'Mike Atkins',
    'address': '4053 Mclaughlin Estates\nSouth Thomas, UT 27817',
},
    'key55183': 'value54060',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Stephanie Bridges',
    'address': '61793 Cortez Pine Suite 727\nNorth Scott, CA 62082',
    'text': 'Traditional fear water various adult visit indicate. Recently including heart Mr relate simple grow.\nGun at market I certain quality. Its argue drop area. Kitchen alone when treat white sea.',
    'email': 'melissamiller@example.org',
    'phone_number': '510-332-3181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Fernando Jones',
    'Gregg Brown',
    'Courtney Mclean',
    'Heather Cameron',
    'Kevin Nixon MD',
    'Melissa Weeks',
    'Steven Lee',
    'Joseph Wong',
    'Andrea Mitchell',
    'Stephanie Scott',
],
    'json': {
    'name': 'Christopher Peterson',
    'address': '86342 Valerie Harbor Suite 791\nFranklinburgh, WI 46068',
},
    'key19032': 'value94089',
    'key59065': 'value8716',
    'key14696': 'value99334',
    'key99485': 'value93527',
    'key55284': 'value8568',
    'key79598': 'value7220',
    'key86687': 'value62938',
    'key65429': 'value89622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Timothy Morris',
    'address': '3071 Hayes Shore Apt. 579\nJacksonfurt, MS 57296',
    'text': 'Ground blood trial. Use fire make nearly. Couple yard medical quite spend.\nProduction manage agree center tonight. Truth space seem.',
    'email': 'burchbrian@example.org',
    'phone_number': '623.301.8804x1859',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Trevino',
    'Nicholas Morrison',
    'Casey Garcia',
    'Kimberly Singleton',
    'Chad Gonzalez',
],
    'json': {
    'name': 'Renee Hunter',
    'address': '712 Joseph Groves\nWest William, MD 29537',
},
    'key37075': 'value88811',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'John Taylor MD',
    'address': '4202 Michael Green Suite 306\nNorth Melanieshire, MA 88119',
    'text': 'Shake rule physical federal lawyer sea word since. Decade apply company plan. Available choose role be even back kid.',
    'email': 'nhart@example.com',
    'phone_number': '941.348.9711x07509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Cantu',
    'Sabrina Williams',
    'Megan Patterson',
    'Alicia Ward',
],
    'json': {
    'name': 'Cheryl Thomas',
    'address': '697 Austin Spur Suite 654\nMartinfurt, VA 17768',
},
    'key13641': 'value13809',
    'key28556': 'value12287',
    'key6496': 'value68784',
    'key18194': 'value97702',
    'key76643': 'value16172',
    'key7941': 'value87666',
    'key36844': 'value70416',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Joshua Nelson',
    'address': '4500 Cassandra Meadow\nHernandezmouth, VI 01317',
    'text': 'Seven enter it trip truth up peace someone.\nNews apply pay near. Animal subject method federal research notice color action. Lawyer traditional candidate sure against professor.',
    'email': 'lisanelson@example.net',
    'phone_number': '270.556.1371',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Spencer',
    'Steven Payne',
    'Charlene Howard',
    'Lindsay Hill',
    'Nichole Foster',
    'Heather Hill',
],
    'json': {
    'name': 'Mandy Gutierrez',
    'address': '0165 Laura Wells\nEast Jenniferton, CA 95319',
},
    'key26847': 'value57476',
    'key56913': 'value76146',
    'key18325': 'value60270',
    'key37834': 'value53590',
    'key29308': 'value99623',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Michael Hernandez DDS',
    'address': '8093 Savannah Pines\nNorth Frankmouth, VI 32956',
    'text': 'Particularly shoulder over. Ground list sometimes job so require. Least former will position arrive support.',
    'email': 'wcarter@example.com',
    'phone_number': '001-277-353-8234x58286',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Myers',
    'Christopher Alvarez',
    'Benjamin Garcia',
    'Melissa Tyler',
    'Suzanne Waller',
    'Brenda Palmer',
    'Desiree Berg',
    'Emily Lawson',
    'Jacqueline Davenport',
    'Jonathan Jones',
],
    'json': {
    'name': 'Jessica Chapman',
    'address': '2383 White Bridge Suite 451\nNew Brian, WA 49140',
},
    'key53127': 'value35018',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'April Maldonado',
    'address': '796 Sheryl Walks Apt. 705\nSouth Michellestad, DC 51606',
    'text': 'Baby true former outside his.\nSecond part bag head politics forget. On nor walk note support than evening. With seek church many send.',
    'email': 'russellli@example.net',
    'phone_number': '726-348-7489x447',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Perry',
    'Amber Anderson',
    'Corey Ruiz',
    'Lisa Nunez',
    'William Foster',
],
    'json': {
    'name': 'Darren Moss',
    'address': '57491 Connor Cliff Apt. 002\nSouth Cynthia, PW 20253',
},
    'key92878': 'value26077',
    'key79132': 'value24829',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Tyler Shepherd',
    'address': 'Unit 3599 Box 5701\nDPO AE 14058',
    'text': 'Full environment high few happen only people. Approach section economy apply quickly kind. Fight western plant fire himself party food.',
    'email': 'robert85@example.org',
    'phone_number': '7827593267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Scott Brown',
],
    'json': {
    'name': 'Richard Terry',
    'address': '2814 Clark Ford Suite 352\nCraigtown, CO 72287',
},
    'key88948': 'value8968',
    'key80556': 'value40515',
    'key95155': 'value31685',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Robert Strong',
    'address': 'USS Olson\nFPO AE 06819',
    'text': 'Close picture society issue though. Have lot information ten. Current side may deep everything force.\nTrue open everyone wind keep item. Soon paper agent smile change. Thing soon happy learn.',
    'email': 'petersonsharon@example.net',
    'phone_number': '001-405-600-0397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jason Vargas',
],
    'json': {
    'name': 'Nancy Hill',
    'address': '08568 Salinas Square Suite 066\nGreenland, WV 99171',
},
    'key64608': 'value92434',
    'key55812': 'value20568',
    'key71047': 'value57395',
    'key76668': 'value48468',
    'key1474': 'value47163',
    'key24513': 'value36394',
    'key23306': 'value86252',
    'key4815': 'value46853',
    'key35553': 'value34576',
    'key75891': 'value97742',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Regina Baldwin',
    'address': 'USNV White\nFPO AE 10318',
    'text': 'Significant rock phone. Up black another few character suggest similar.\nEverybody throw whose type. Space development down degree month make raise.',
    'email': 'jason61@example.com',
    'phone_number': '864-783-7821',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Morris DDS',
    'Lisa Blair',
    'Patricia Clark',
    'Alicia Pearson',
    'Jeffrey Bird',
],
    'json': {
    'name': 'Heidi Saunders',
    'address': 'PSC 3235, Box 1471\nAPO AA 39443',
},
    'key89100': 'value1817',
    'key10047': 'value22709',
    'key8678': 'value67340',
    'key68929': 'value91523',
    'key32185': 'value30635',
    'key14090': 'value17406',
    'key56396': 'value95149',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Mr. Nathaniel Williams DDS',
    'address': 'Unit 1640 Box 1336\nDPO AP 60272',
    'text': 'Since across election network never reveal sure art. Skin five support can method nation similar. Make stop per simple affect physical.',
    'email': 'josewarren@example.net',
    'phone_number': '750.415.9996x1564',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Joann Williams',
    'Sierra Nichols',
    'Stacey Norris',
],
    'json': {
    'name': 'Alan Gallagher',
    'address': '27786 Nathan Isle Apt. 925\nEast Sarahbury, NM 89442',
},
    'key40594': 'value86774',
    'key62040': 'value8762',
    'key3667': 'value34868',
    'key47566': 'value37370',
    'key75531': 'value94668',
    'key38798': 'value32054',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Zachary Bailey PhD',
    'address': '0265 Paula Pines Suite 541\nJosephburgh, DE 12991',
    'text': 'Tax risk western late off. Want majority month put. National school these seat work structure professor.\nWell still television involve. Simply fear hard provide life simply.',
    'email': 'juan52@example.com',
    'phone_number': '484.473.8030x646',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Wheeler',
    'Tammy Thornton',
],
    'json': {
    'name': 'Renee Ford',
    'address': '5407 Veronica Alley\nSouth Rebeccaville, GA 07384',
},
    'key82668': 'value74260',
    'key43579': 'value27052',
    'key23662': 'value9506',
    'key96448': 'value630',
    'key79764': 'value69210',
    'key96079': 'value84259',
    'key45744': 'value49004',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Jonathan Myers',
    'address': 'USS Collins\nFPO AE 38847',
    'text': 'One they ask attack class new garden.\nFocus majority single official for. Up although fall charge situation. Stock official respond him.',
    'email': 'schmidtjason@example.com',
    'phone_number': '652-623-1057x23424',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Daniels',
    'Michael Rivera',
    'Nathan Garcia',
    'Jennifer Smith',
    'Michael Avila',
    'Chad Frazier',
    'Tim Carter',
    'Mathew Murillo',
],
    'json': {
    'name': 'John Johnson',
    'address': '01223 Caldwell Extensions Suite 698\nLake William, ND 68387',
},
    'key42035': 'value27627',
    'key62314': 'value16361',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Daniel Stephens',
    'address': '614 Vega Mount Suite 014\nPort Brent, CO 62413',
    'text': 'Name defense college. Senior however end society tend. Detail I year fine realize law pull.\nProfessor my special performance show sea major military. Support take list although create city.',
    'email': 'angelahughes@example.org',
    'phone_number': '(587)331-8260x4691',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Eric Clay',
    'Carlos Gonzalez',
    'Tyler Wagner',
    'Mr. Nicholas Johnson DDS',
    'Victor Wallace',
    'Ashlee Callahan',
    'Patricia Norris',
    'Andrew Lawrence',
    'Lori Watson',
],
    'json': {
    'name': 'Luke Francis',
    'address': 'USNV Peck\nFPO AA 72160',
},
    'key60777': 'value35429',
    'key81278': 'value82859',
    'key51252': 'value7932',
    'key46783': 'value41194',
    'key76295': 'value83983',
    'key77408': 'value61511',
    'key70630': 'value75861',
    'key19322': 'value72402',
    'key41240': 'value89764',
    'key77760': 'value79155',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Amy Walter',
    'address': '63206 James River\nBenjaminport, KY 84406',
    'text': 'Majority add generation.\nWall improve leave well time yourself task.',
    'email': 'krystal35@example.org',
    'phone_number': '3339026078',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Paul Miller',
    'Jennifer Tucker',
    'Michele Campbell',
    'Kimberly Wilson',
    'Kaylee Williams',
    'Michael Mosley',
    'Sara Riley',
    'Amy Cobb',
    'Mark Lopez',
    'Brendan Dawson',
],
    'json': {
    'name': 'Kaylee Coleman',
    'address': '5958 Shannon Vista Suite 499\nScottberg, AS 53916',
},
    'key38632': 'value75689',
    'key982': 'value86167',
    'key65269': 'value44284',
    'key81930': 'value63041',
    'key46562': 'value12535',
    'key77609': 'value28810',
    'key21613': 'value92167',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Christopher Andersen',
    'address': '00179 Fox Mews Apt. 642\nGilesview, OH 51124',
    'text': 'Center bit result for. Across perform item across young ago. Notice ahead change window include item. Especially outside wide.',
    'email': 'pkelley@example.com',
    'phone_number': '(885)224-1347x5770',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brian Krause',
    'Frank Osborne',
    'Joseph Leach',
],
    'json': {
    'name': 'Alisha Schmidt',
    'address': '12924 Chan Manors Apt. 545\nEast David, PA 76772',
},
    'key5173': 'value76928',
    'key57118': 'value61998',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Michelle Campbell',
    'address': '3483 Julia Points\nAaronbury, NV 97418',
    'text': 'For decade nice degree late store fire. Reach think science alone. Will her can history southern believe.',
    'email': 'jessicahall@example.com',
    'phone_number': '439.953.1066x0932',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Alexandra Montgomery PhD',
    'Sharon Morales',
    'Rebecca Jennings',
    'Michelle Adams',
    'Timothy Willis',
],
    'json': {
    'name': 'Miguel Love',
    'address': '14809 Todd Streets\nRomanmouth, ND 69965',
},
    'key76161': 'value68272',
    'key49733': 'value27028',
    'key3472': 'value93074',
    'key5721': 'value28765',
    'key41882': 'value63697',
    'key83767': 'value61959',
    'key437': 'value51708',
    'key56900': 'value3426',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jennifer Cuevas',
    'address': '8059 Ryan Unions Suite 281\nWilliamsfurt, CT 27139',
    'text': 'Film staff conference us bit collection.\nService draw near toward fear rest. Age various culture play pay. Ability guess week economic.',
    'email': 'priceholly@example.com',
    'phone_number': '5947224841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Gabriella Davis',
    'Audrey Russo',
    'Christian Wright',
    'Emily Allen',
    'Daniel Barron',
    'Jonathan Howell',
    'Max Melendez MD',
    'Thomas Santiago',
    'John Harris',
],
    'json': {
    'name': 'Caroline Paul',
    'address': '180 Mason Ramp\nNorth Marialand, NH 94830',
},
    'key71645': 'value53756',
    'key40545': 'value803',
    'key71080': 'value99663',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Kristin Burgess',
    'address': '958 Dixon Key Apt. 332\nHeatherfurt, AK 83574',
    'text': 'Boy senior box short. Special truth week. Food personal wear.\nDefense run among. Summer majority account accept sit rich address. Condition out page speak move apply operation.',
    'email': 'thomassims@example.org',
    'phone_number': '(249)811-0195',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alison Drake',
    'Brianna White',
    'Mark Rogers',
    'Rachael Wilson',
],
    'json': {
    'name': 'Austin Ray',
    'address': 'PSC 3031, Box 4115\nAPO AP 78161',
},
    'key3398': 'value42980',
    'key75745': 'value36708',
    'key61101': 'value88624',
    'key92036': 'value37475',
    'key35134': 'value54069',
    'key70469': 'value20055',
    'key38046': 'value39235',
    'key34247': 'value64023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Vincent Johnson',
    'address': '28776 Norris Garden\nRyanton, DE 52563',
    'text': 'Sense every answer movie nice world. Nice edge level. Create figure reveal key.\nEvidence cost TV go notice produce. Long determine green room.',
    'email': 'denise94@example.net',
    'phone_number': '938-931-8497',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Angela Hernandez',
    'Cody Carter',
    'Antonio Martin',
    'Connie Ramirez',
    'Michael Banks',
    'Christian Ball PhD',
],
    'json': {
    'name': 'Steven Hogan',
    'address': '2346 Roberts Shoal Suite 212\nKimberlymouth, OR 03414',
},
    'key95530': 'value46146',
    'key11969': 'value94705',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Diana Robertson',
    'address': '010 Hannah Lane Apt. 139\nJonestown, MO 89613',
    'text': 'Training degree quickly out. Play president military read. Record sit success step field condition likely.\nInside culture vote program arrive billion family. Herself west light financial.',
    'email': 'shelley64@example.net',
    'phone_number': '704.462.0497x44785',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Evans',
    'Victor Sutton',
    'Robyn Dillon',
],
    'json': {
    'name': 'Devin Marks',
    'address': '68686 Mack Ramp\nEstradashire, UT 04525',
},
    'key8052': 'value77719',
    'key94790': 'value14855',
    'key48577': 'value32453',
    'key30437': 'value6388',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Wayne Smith',
    'address': '025 Thompson Gardens Suite 986\nDavistown, CT 67950',
    'text': 'Reflect treat return city skin authority particular. Hospital support interview development develop. Section best tough market. Race family above modern lead suggest effect.\nCase politics wait next.',
    'email': 'bsmith@example.com',
    'phone_number': '319.641.6481x19676',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sheri Meadows PhD',
    'Molly Wells',
    'John Zuniga',
],
    'json': {
    'name': 'Cynthia Pace',
    'address': 'USS Cox\nFPO AE 48095',
},
    'key63739': 'value63204',
    'key56468': 'value98421',
    'key78530': 'value54527',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'William Mclaughlin',
    'address': '2577 Figueroa Mall\nCynthiafurt, CA 91124',
    'text': 'Student by allow both region firm. Subject soldier whatever during himself. Matter paper example visit concern.\nWoman training within each within half. Get song large bag team.',
    'email': 'nicolecooke@example.net',
    'phone_number': '(347)917-8977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shelby Clark',
    'Robert Benson',
],
    'json': {
    'name': 'Sara Clark',
    'address': '4323 Ashley Valley Apt. 849\nWest Kimberly, AL 65795',
},
    'key68937': 'value84768',
    'key65379': 'value40638',
    'key32233': 'value71620',
    'key27425': 'value13364',
    'key68687': 'value93904',
    'key61650': 'value84167',
    'key50847': 'value1288',
    'key82917': 'value46785',
    'key52220': 'value36212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Richard Young',
    'address': '8407 Williams Falls Apt. 871\nLake Jasonfurt, GU 90105',
    'text': 'Myself expert officer store six. First dinner stay.\nKitchen avoid else maybe raise loss. National citizen clear crime special show wide. Trip dog little fear production culture ever.',
    'email': 'soliskatrina@example.org',
    'phone_number': '472-738-5262x7701',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Mann',
    'Paul Andrade',
    'Paul Haynes',
    'Bradley Mccall',
],
    'json': {
    'name': 'Chad Martin',
    'address': 'USNV Cameron\nFPO AE 85020',
},
    'key94098': 'value50081',
    'key37230': 'value57032',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Kelly Kim',
    'address': '8755 Donald Flat Apt. 179\nPort Eric, MI 53605',
    'text': 'Speak interesting song method bank car successful. Room another leg control worry. Though fine way security. Develop modern small concern.',
    'email': 'anthony52@example.net',
    'phone_number': '639.405.2655x37742',
    'array_int_dynamic': [
    15915,
],
    'array_varchar_dynamic': [
    'Luke Cunningham',
    'Jenny Booth',
],
    'json': {
    'name': 'Terri Mcknight',
    'address': '763 Green Points Suite 246\nNew Erinhaven, MN 23546',
},
    'key93253': 'value95405',
    'key40805': 'value80522',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Melinda Jones',
    'address': '929 Small Road Apt. 034\nNorth Davidtown, UT 33820',
    'text': 'Moment research military road force force its power. As shake magazine pull value. Support together star goal always.\nAudience popular else where tend campaign. Job design but increase between.',
    'email': 'jessica25@example.net',
    'phone_number': '(440)706-7980',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Laura Gardner',
    'Christopher Collins',
    'Desiree West',
    'Beth Simpson',
    'Juan White',
],
    'json': {
    'name': 'Rhonda Braun',
    'address': '452 Maria Tunnel Apt. 712\nNorth Jacobmouth, WI 48535',
},
    'key54861': 'value36021',
    'key45535': 'value49445',
    'key51031': 'value3642',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Nicholas Cook',
    'address': '03181 Hodge Squares Suite 161\nMendezfort, ND 58718',
    'text': 'Leg professor central wish nearly. Traditional pattern would reduce.\nAnimal avoid force through media usually. Family hair wish mind whole audience middle.',
    'email': 'boothwendy@example.com',
    'phone_number': '9605623255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Brown',
    'Juan Taylor',
    'Jill Steele',
    'Ashley Gregory',
],
    'json': {
    'name': 'Kelly Moore',
    'address': '18960 Frazier Junction Apt. 841\nRosariotown, AR 93220',
},
    'key7121': 'value48363',
    'key9055': 'value95062',
    'key71004': 'value35066',
    'key77970': 'value88822',
    'key72446': 'value30190',
    'key31188': 'value39029',
    'key44471': 'value79289',
    'key56281': 'value49113',
    'key64588': 'value96235',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Lori Rodriguez',
    'address': 'USCGC Campbell\nFPO AA 08356',
    'text': 'Owner cultural method mean people. Pm seven debate month prove ever material.',
    'email': 'ychristian@example.com',
    'phone_number': '386-213-4893x66656',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lindsey Hill',
    'Alexis Hughes',
],
    'json': {
    'name': 'Nancy Peterson',
    'address': '743 Laurie Prairie\nMillerchester, CO 46177',
},
    'key3614': 'value47086',
    'key44838': 'value23389',
    'key63206': 'value57693',
    'key686': 'value98545',
    'key74696': 'value15099',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'David Mcgrath',
    'address': '76626 Elizabeth Lane Apt. 548\nPort Coreyshire, CA 10183',
    'text': 'Item sign white return boy.\nGarden rock current foreign. Image Congress could when a nothing. Young with strategy treat season.\nDemocratic white billion nation. Beat operation per.',
    'email': 'scott29@example.org',
    'phone_number': '+1-699-816-9177x46286',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jocelyn Sanders',
    'Christy Armstrong',
],
    'json': {
    'name': 'Austin Peterson',
    'address': 'USS Reed\nFPO AA 05069',
},
    'key56282': 'value9244',
    'key58019': 'value45229',
    'key54655': 'value43886',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Jessica Hood',
    'address': 'Unit 4797 Box 9691\nDPO AP 92399',
    'text': 'Pay nothing century middle soon. Without audience would scientist about.\nSize age wish good. Mention both own feeling wait girl this.\nFund full executive mention recent nice opportunity.',
    'email': 'allisonscott@example.com',
    'phone_number': '715.567.5630',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Rita Powell',
    'Joseph Williams',
    'James Wilson',
    'Ronnie Aguilar',
    'Traci Johns',
    'Emma Kelly',
    'Belinda Salazar',
],
    'json': {
    'name': 'Michael Harper',
    'address': '5437 Arthur Trafficway\nBrandyburgh, VT 36477',
},
    'key87245': 'value39673',
    'key47297': 'value65222',
    'key66846': 'value69084',
    'key50815': 'value81194',
    'key59728': 'value11082',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Joshua Moore',
    'address': '370 Shannon Mountains Suite 481\nLake Wendyfort, RI 69488',
    'text': 'Sea cell fly card those professor million.\nPeace goal citizen. None audience day who. Give campaign second billion present beat any each. Western stock artist kitchen son decide alone.',
    'email': 'sweaver@example.com',
    'phone_number': '(370)730-8128x14582',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Lee',
    'Sarah Shelton',
    'Patricia Lambert',
    'Sheri Williamson',
    'Michael Rodriguez DDS',
],
    'json': {
    'name': 'Jay Yang',
    'address': '329 Adams Springs\nEast Sarah, MD 95304',
},
    'key21204': 'value68542',
    'key48395': 'value49616',
    'key58176': 'value8139',
    'key25660': 'value79653',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Victor Thompson',
    'address': 'USCGC Black\nFPO AA 93383',
    'text': 'Audience never moment apply already quality. Production let until worry. Age seem sure more site process.',
    'email': 'morganlinda@example.org',
    'phone_number': '+1-975-936-4407x597',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Morris',
    'David Manning',
    'Tammy Roberts',
    'Rebecca Wright',
    'Victoria Jimenez',
    'Sara Jones',
    'Sarah Mathews',
    'Kimberly Patel',
    'Amy Ware',
],
    'json': {
    'name': 'Curtis Jenkins',
    'address': '740 Corey Course Apt. 952\nEast Toddmouth, CA 77874',
},
    'key72121': 'value59475',
    'key28257': 'value88921',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Jamie Williams',
    'address': '742 Michael Park\nSouth Laura, TX 57306',
    'text': 'Management product American kitchen its gun size. During value teach artist true run.\nOff work surface they resource question. The truth scientist west guy coach stop.',
    'email': 'tiffany56@example.net',
    'phone_number': '001-261-622-8024x008',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ashley James',
    'David Brown',
    'Amanda Murray',
    'Paul Moore',
    'Joshua Hayes',
    'Joshua Krause',
],
    'json': {
    'name': 'Tyler Levy',
    'address': '740 Shepard Plains Apt. 246\nWest Elizabeth, PW 99525',
},
    'key16067': 'value9974',
    'key92676': 'value74680',
    'key37290': 'value57317',
    'key99129': 'value9788',
    'key30586': 'value63122',
    'key10937': 'value58594',
    'key64666': 'value17999',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Renee Garcia',
    'address': 'USS Gill\nFPO AE 06271',
    'text': 'Onto near save assume. Bit write say assume friend century.\nShoulder middle magazine none.\nStill floor former form stock agent recognize crime. Medical term fear floor country reason feel.',
    'email': 'gilbertdaniel@example.com',
    'phone_number': '001-621-631-1598x711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Anita Davis',
    'Kimberly Sullivan',
    'Margaret Alvarez',
    'Kathy Martin',
],
    'json': {
    'name': 'Stephanie Brown',
    'address': '48809 Lopez Skyway Apt. 558\nNew Douglasshire, CA 27903',
},
    'key36192': 'value80864',
    'key71110': 'value70092',
    'key87927': 'value27840',
    'key60529': 'value87801',
    'key59345': 'value97742',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Samantha Brown',
    'address': '80296 Laura Expressway Apt. 534\nEast Amyhaven, MH 60882',
    'text': 'Edge choice ok well leg. Medical draw off lawyer college. Evidence population federal amount rise machine. Generation defense hear throw.\nConference check itself much as.',
    'email': 'hreynolds@example.com',
    'phone_number': '248-585-3343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Corey Harper',
],
    'json': {
    'name': 'Pamela Vazquez',
    'address': '28558 Perry Ramp\nEast Kaitlin, AS 04946',
},
    'key55814': 'value65872',
    'key39649': 'value3930',
    'key47335': 'value82417',
    'key36611': 'value31598',
    'key79181': 'value83378',
    'key4425': 'value11853',
    'key81436': 'value69950',
    'key50379': 'value24751',
    'key74656': 'value68536',
    'key90117': 'value80531',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Jay Black',
    'address': '4827 Burns Glens\nNorth Hollymouth, WV 39894',
    'text': 'Management follow size summer participant people. Indicate land really off than or.',
    'email': 'uarellano@example.net',
    'phone_number': '207.378.9308x36804',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sylvia Harris',
    'Michelle Hughes',
    'Mr. Jerry Marshall MD',
    'Matthew Zimmerman',
    'Frederick Ramirez',
    'John Dunn',
    'Desiree Thomas',
    'Stacy Shelton',
    'Dylan Phillips',
    'Julian Calderon',
],
    'json': {
    'name': 'Christopher Mckinney',
    'address': 'PSC 8860, Box 6152\nAPO AA 18520',
},
    'key8316': 'value76480',
    'key85906': 'value7524',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Kelly Melton',
    'address': '7080 Gibbs Path\nSamanthachester, PR 10904',
    'text': 'Reach environment follow chair. Late chair continue watch star reflect. Site order always dark author force big music.',
    'email': 'jessica22@example.net',
    'phone_number': '+1-597-739-4082x1709',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Leah Allen',
    'Mark Holt',
    'Stephanie Evans',
],
    'json': {
    'name': 'Patrick Young',
    'address': 'Unit 7904 Box 7078\nDPO AP 42042',
},
    'key59863': 'value26090',
    'key44388': 'value36809',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Deborah Moore',
    'address': '466 Smith Radial\nWest Mark, IA 63572',
    'text': 'Still upon simple office or wish.\nSuccessful between image hear beyond painting other. Stay far finish whether technology capital defense major. Build can ten themselves.',
    'email': 'stacycoleman@example.net',
    'phone_number': '469-793-8970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'David Cook',
    'Holly Thompson',
    'Karen Arnold',
    'Justin Robinson',
    'Peggy Palmer',
    'Kimberly Perez',
    'Joseph Cruz',
    'Julie Espinoza',
    'Arthur Hudson',
],
    'json': {
    'name': 'Frank Baxter',
    'address': '2778 Brandon Rapid\nScottmouth, DE 23010',
},
    'key71571': 'value96055',
    'key88893': 'value69252',
    'key6662': 'value652',
    'key78236': 'value52872',
    'key17851': 'value70255',
    'key22676': 'value81116',
    'key42964': 'value45309',
    'key72320': 'value50981',
    'key77039': 'value71912',
    'key36647': 'value15267',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Donald Nunez',
    'address': '600 Emily Lock\nAlexville, IL 03367',
    'text': 'Phone range market push. Page bag blood know commercial store. As identify look trouble.\nDay difference minute lay. Simply than social news send movie service.',
    'email': 'hilltodd@example.net',
    'phone_number': '349.987.4378x60101',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amy Harris',
    'Keith Simpson',
],
    'json': {
    'name': 'Michael Snyder MD',
    'address': '51434 Meza Divide\nLake Julieville, CA 76262',
},
    'key16928': 'value83881',
    'key79696': 'value74035',
    'key14977': 'value75736',
    'key30630': 'value98535',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Kellie Rodriguez',
    'address': '42097 Pamela Drive\nLoribury, DE 85130',
    'text': 'Write leave I hit politics. Get space up benefit animal effect.\nEver if method like happy investment. Fight determine low worker daughter eat skill increase.',
    'email': 'brian16@example.com',
    'phone_number': '+1-905-359-5212x73621',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Patterson',
    'April Fischer',
],
    'json': {
    'name': 'Jason Johnson',
    'address': '27195 White Mills\nMurilloland, NE 00892',
},
    'key21251': 'value2862',
    'key34947': 'value42817',
    'key50553': 'value61805',
    'key20672': 'value37506',
    'key52350': 'value53880',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Heather Figueroa',
    'address': '8453 Sharon Bridge Apt. 085\nChelseaburgh, NM 18958',
    'text': 'Reason easy up drive. Hospital control particular management require head next. Space movement wall focus culture down.\nRealize she international statement trade summer give. Money less interest bit.',
    'email': 'adamwilliams@example.com',
    'phone_number': '822-855-3678x54382',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Charles Rosales',
    'Jordan Thomas',
    'Traci Murphy',
    'Manuel Summers',
    'Sheila Robertson',
    'Leslie Cross',
],
    'json': {
    'name': 'Samuel Perry',
    'address': '6545 Jermaine Loaf\nCraigtown, NJ 41309',
},
    'key50705': 'value94794',
    'key53672': 'value40460',
    'key2411': 'value32309',
    'key59170': 'value26386',
    'key7747': 'value53959',
    'key17753': 'value14080',
    'key99858': 'value40479',
    'key59467': 'value74393',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Christopher Green',
    'address': '5897 Scott Pass\nParkerburgh, SC 15730',
    'text': 'Both tax quality picture. With job only sport.\nWho herself media address thus. Where brother particular magazine.',
    'email': 'nmeyer@example.org',
    'phone_number': '7083549615',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Dougherty',
    'Heidi Williams',
    'Joshua Long',
    'Bill Hamilton',
    'Kayla Ward',
    'Ryan Singleton',
],
    'json': {
    'name': 'Amanda Washington',
    'address': '9373 Darrell Glens\nSouth Katelyn, WI 55709',
},
    'key42640': 'value64603',
    'key66461': 'value69320',
    'key69481': 'value48261',
    'key34700': 'value46511',
    'key53811': 'value11730',
    'key16774': 'value94972',
    'key93660': 'value79289',
    'key15871': 'value42799',
    'key26482': 'value84022',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Calvin Clayton',
    'address': '4985 Bryant Road Apt. 797\nWillieberg, CO 47052',
    'text': 'Start film long parent power despite should. Spend college close others.\nEverybody three wife media.',
    'email': 'alexismann@example.org',
    'phone_number': '001-296-325-5214x1069',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christina Wright',
    'Sean Martin',
    'Robert Jones',
    'Jennifer Brooks',
    'Christopher Guerrero',
],
    'json': {
    'name': 'Cynthia Cook',
    'address': '1945 Kelley Island\nSamanthaton, FM 97314',
},
    'key10990': 'value86770',
    'key4987': 'value65671',
    'key87654': 'value57699',
    'key66231': 'value1938',
    'key4846': 'value90639',
    'key62637': 'value84880',
    'key26647': 'value56124',
    'key94129': 'value12790',
    'key75992': 'value39727',
    'key17466': 'value96211',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Michael Campbell',
    'address': '679 Kimberly Wells\nNew Vincentton, PW 51777',
    'text': 'Hundred happen other see easy. Appear high account always alone full. Republican develop star whose.\nFirm moment process old.',
    'email': 'curtisjessica@example.net',
    'phone_number': '334.883.9708x87489',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Diane Poole',
    'Manuel Marsh',
    'Kayla Vega',
],
    'json': {
    'name': 'Patrick Bauer',
    'address': '1796 Carson Manors\nRussellport, CA 17321',
},
    'key31762': 'value85088',
    'key93723': 'value35409',
    'key75411': 'value29616',
    'key3461': 'value44050',
    'key14247': 'value87619',
    'key5811': 'value91180',
    'key7856': 'value85769',
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



    def test_request_2(self):
        """测试请求 2 - POST http://172.17.0.5:23210/v1/vector/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'b67d362f-62f1-11f0-ba1b-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_41_389724BhKjpica',
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



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v1/vector/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'b721246d-62f1-11f0-9a91-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_41_389724BhKjpica',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'afc2b408-62f1-11f0-9004-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_37_41_389724BhKjpica',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-False-uid >= 0]_1752745074.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseFalseUid01752745074Json()
    test.run_tests()
