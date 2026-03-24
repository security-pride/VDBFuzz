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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestGetVector_test_get_vector_complex[True-True-list]_1752749086_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestGetVector_test_get_vector_complex[True-True-list]_1752749086.json"
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



class AllmilvusLogtestgetvectorTestGetVectorComplexTrueTrueList1752749086Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestGetVector_test_get_vector_complex[True-True-list]_1752749086.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestGetVector_test_get_vector_complex[True-True-list]_1752749086.json"
        self.test_count = 9  # 测试方法数量
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
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
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
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
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
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
    'data': [
    {
    'id': 17527490816027,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Daniel Carey',
    'address': '0196 Michael Key\nWarrenshire, CO 28453',
    'text': 'Still politics impact show whole moment. List easy always. Defense matter chance court general reflect.\nAccept behavior sense movie both after.',
    'email': 'reginald54@example.com',
    'phone_number': '001-373-671-3865x2446',
    'json': {
    'name': 'Joshua Weaver',
    'address': '959 Brown Views Apt. 072\nPhilipborough, AS 45563',
},
    'key87084': 'value80687',
    'key75187': 'value24708',
    'key69182': 'value51142',
},
    {
    'id': 17527490816042,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Jesus Clark',
    'address': '2780 Pugh Crossing Apt. 867\nEast Amber, VA 60727',
    'text': 'Key direction from. Suddenly green inside picture cold provide you. Little even already term difficult.\nHotel them draw lawyer worker maintain. Future herself quickly Congress main.',
    'email': 'brodriguez@example.org',
    'phone_number': '488-366-1412x6527',
    'json': {
    'name': 'Lisa Brown',
    'address': '03415 Thompson Row\nWoodland, TX 36769',
},
    'key85846': 'value83126',
    'key39068': 'value81551',
    'key35439': 'value17343',
    'key67496': 'value73215',
    'key35539': 'value30579',
    'key85114': 'value76707',
    'key66977': 'value28140',
    'key95844': 'value45570',
},
    {
    'id': 17527490816056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Cynthia Kirby',
    'address': 'PSC 1021, Box 2179\nAPO AA 41543',
    'text': 'Country agency rise fund radio child. Certainly know exist quickly expert.\nWhen over west threat information day ground. Poor already true practice different identify. Late article knowledge myself.',
    'email': 'jenkinsmichelle@example.org',
    'phone_number': '384.525.2416',
    'json': {
    'name': 'Jamie Mcdowell',
    'address': '689 Levine Station Suite 547\nWeaverfurt, CO 02519',
},
    'key11236': 'value22590',
    'key36390': 'value41026',
},
    {
    'id': 17527490816066,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Morgan Perez',
    'address': '5128 Patricia Mount\nLake Sabrinamouth, TX 73608',
    'text': 'Account decade cell drug. Project create catch Democrat food beat. Bar hard source husband something place.\nCongress firm wife bill left. Hundred identify fact front. Fine food their.',
    'email': 'wreeves@example.net',
    'phone_number': '727-404-5328x348',
    'json': {
    'name': 'Todd Miller',
    'address': '479 Hailey Drive Apt. 496\nGarciaburgh, CO 16266',
},
    'key1498': 'value23595',
    'key76634': 'value62521',
    'key79813': 'value50460',
    'key16269': 'value98275',
    'key63435': 'value78510',
    'key34605': 'value67563',
    'key46480': 'value41331',
    'key55254': 'value55170',
},
    {
    'id': 17527490816078,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Joshua Howell',
    'address': '2202 Fisher Square Apt. 591\nMichaelborough, MD 99397',
    'text': 'Fact whose more them. Near direction morning environmental over be address. Front race government production eight.',
    'email': 'regina68@example.com',
    'phone_number': '315-985-2744',
    'json': {
    'name': 'Jason Cohen',
    'address': '139 Acevedo Burg Suite 638\nPort Stevenmouth, MO 47803',
},
    'key10671': 'value5868',
    'key83151': 'value19756',
    'key57586': 'value67385',
},
    {
    'id': 17527490816089,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Tyler Zavala',
    'address': '7145 Underwood Islands\nLake Jasonport, MO 85367',
    'text': 'Rest when source magazine senior scientist. Group just wide production allow describe everything upon. Law voice miss rate within authority.',
    'email': 'mschmidt@example.com',
    'phone_number': '705-235-9198x6850',
    'json': {
    'name': 'Samuel Haley',
    'address': '4886 Russo Lakes Apt. 648\nTrujillochester, FM 13177',
},
    'key52259': 'value98642',
    'key63638': 'value84241',
    'key24442': 'value21261',
    'key40732': 'value28182',
    'key4629': 'value43046',
    'key67903': 'value21628',
    'key24590': 'value19128',
    'key22646': 'value51596',
},
    {
    'id': 17527490816101,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Tracy Stephens',
    'address': '614 Jamie Roads Suite 114\nEast Deborah, UT 26141',
    'text': 'Low available those so game dark reality. Another arm part food trade future protect.\nAgain anyone idea building guy. Daughter girl use pick today. Congress rather nation.',
    'email': 'dwhite@example.org',
    'phone_number': '592-736-4524',
    'json': {
    'name': 'Grant Hudson',
    'address': '7510 Jennifer Extensions\nVanessamouth, VA 81695',
},
    'key40566': 'value20631',
    'key40521': 'value46070',
},
    {
    'id': 17527490816111,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Samantha Green',
    'address': 'PSC 2767, Box 8841\nAPO AP 88683',
    'text': 'Agent boy local region political. Course fall manage member significant moment relationship. Trip them reality operation just focus within.',
    'email': 'henrycampbell@example.org',
    'phone_number': '515.337.4166x4924',
    'json': {
    'name': 'Corey Wilcox',
    'address': '408 Justin Curve\nAlexaland, SD 46160',
},
    'key16718': 'value49310',
    'key30125': 'value19552',
    'key93645': 'value76014',
    'key68161': 'value49041',
    'key8681': 'value95386',
    'key24952': 'value24230',
    'key31531': 'value6883',
},
    {
    'id': 17527490816120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Kimberly Reid',
    'address': '402 Chapman Shores\nSarahberg, NC 78548',
    'text': 'Shake produce teach face. Stand catch edge medical win last.\nYard here go crime just. Keep save seek main little Democrat animal. Character adult item certain picture side no.',
    'email': 'davidglover@example.com',
    'phone_number': '855-975-8846',
    'json': {
    'name': 'Sean Rivas',
    'address': '868 Chad Brooks Suite 427\nPort Waynehaven, WA 48376',
},
    'key21539': 'value54799',
    'key40747': 'value74485',
    'key11369': 'value30104',
    'key14462': 'value65312',
    'key88540': 'value24857',
},
    {
    'id': 17527490816131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Jean Rodriguez',
    'address': '7491 Alicia Walks Apt. 516\nWest Jeffreyland, NE 63383',
    'text': 'Trouble but stuff manager. Indicate nearly against morning. System culture pressure good.\nElection miss themselves billion show game. Trade power power reveal.',
    'email': 'tonisimmons@example.net',
    'phone_number': '001-956-811-0111x668',
    'json': {
    'name': 'Alejandra Lewis',
    'address': '026 Nicholas Harbors\nJenkinsport, MI 59687',
},
    'key53084': 'value92056',
    'key61109': 'value79316',
    'key27384': 'value83458',
    'key29915': 'value59014',
    'key74007': 'value95459',
    'key81493': 'value40148',
    'key93139': 'value71265',
},
    {
    'id': 17527490816143,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Ryan Thompson',
    'address': '064 Kathryn Falls\nShelbyside, VA 32998',
    'text': 'Central company plant well with respond. Employee type simple possible million. Pm minute federal participant.\nBlue lawyer speech defense others.',
    'email': 'uharris@example.org',
    'phone_number': '592-765-8257x3077',
    'json': {
    'name': 'Kristin Ramirez',
    'address': '410 Warner Spurs Suite 686\nWest Dawnmouth, OR 53886',
},
    'key5805': 'value91655',
    'key56358': 'value2433',
    'key94749': 'value55687',
    'key81910': 'value70790',
    'key2450': 'value83788',
    'key58715': 'value18153',
    'key54824': 'value53995',
},
    {
    'id': 17527490816154,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Sherri Green',
    'address': '686 Smith Row\nSouth April, KS 58523',
    'text': 'Movement inside this teacher structure fact safe. Follow then information number almost rule peace. Grow her dog civil improve example job carry.',
    'email': 'gporter@example.com',
    'phone_number': '231-262-9355',
    'json': {
    'name': 'Robert Welch',
    'address': '117 Lisa Lakes\nJenkinsmouth, MO 20346',
},
    'key96290': 'value2427',
    'key10020': 'value34163',
    'key2173': 'value12082',
    'key33833': 'value33755',
    'key28298': 'value67711',
    'key44895': 'value57221',
    'key20904': 'value89812',
    'key82911': 'value23509',
    'key49219': 'value55620',
},
    {
    'id': 17527490816165,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Ashley Allen',
    'address': 'Unit 9664 Box 9489\nDPO AP 70510',
    'text': 'Heavy dark bit. Send thing wall kid party. Where science loss probably each.\nMission first which five line close. Lot hour find citizen understand purpose. Development hit away many show food.',
    'email': 'debbie38@example.com',
    'phone_number': '577-327-4013',
    'json': {
    'name': 'Amanda Miller',
    'address': '8163 Russell Creek Suite 785\nNorth Kathyshire, ME 90788',
},
    'key64956': 'value75841',
    'key12988': 'value93333',
    'key42827': 'value59633',
    'key65869': 'value628',
    'key70203': 'value84764',
    'key30017': 'value47667',
    'key72508': 'value92130',
    'key37458': 'value59830',
},
    {
    'id': 17527490816174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Gregory Stout',
    'address': '2682 Robert Lane Apt. 709\nJonesshire, TN 36551',
    'text': 'Can like anything past thing lawyer phone rest. Than small agree. Majority green five population shoulder later.',
    'email': 'andrew24@example.com',
    'phone_number': '001-210-394-6841x682',
    'json': {
    'name': 'Robert Daniels',
    'address': '44018 Elizabeth Grove\nPort William, MT 23259',
},
    'key88899': 'value29102',
    'key51023': 'value31419',
    'key28494': 'value73943',
},
    {
    'id': 17527490816184,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Brittany Lee',
    'address': '533 Robert Forges Suite 623\nSloanview, ME 24027',
    'text': 'Order education citizen rise movie boy. Son stop realize kind treat our direction anyone.\nLearn land culture television. Traditional card rather. Let example information white.',
    'email': 'weberrebecca@example.net',
    'phone_number': '(917)995-9199x7736',
    'json': {
    'name': 'Catherine Kelley',
    'address': '822 Cruz Ridge Suite 366\nPort Rachelmouth, OK 76165',
},
    'key16328': 'value83116',
    'key31114': 'value1390',
    'key49050': 'value34858',
    'key55992': 'value20846',
    'key37474': 'value18060',
    'key55112': 'value61869',
    'key21629': 'value66713',
},
    {
    'id': 17527490816196,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'John Stephenson',
    'address': '2445 Moore Run\nNorth Reneemouth, MP 80723',
    'text': 'Provide now media nature scene. Lawyer beyond bag teach. Strong friend town. Media involve above stuff middle when much.\nSon carry trial himself soon. Air game become there pay view skin kitchen.',
    'email': 'coltonburch@example.net',
    'phone_number': '001-722-341-2460x89639',
    'json': {
    'name': 'David Richardson',
    'address': '6423 Wilson Track Suite 067\nKevinville, AL 31421',
},
    'key68220': 'value78181',
    'key92507': 'value43837',
    'key94767': 'value77703',
    'key22215': 'value84525',
    'key40584': 'value80446',
},
    {
    'id': 17527490816208,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Kyle Christensen',
    'address': '32383 Alan Turnpike\nPort Barbaraberg, NV 95205',
    'text': 'Important his that nothing economy true. Day boy tough figure day name apply. Response picture no against prove your indicate.',
    'email': 'davidsondouglas@example.net',
    'phone_number': '+1-398-787-6259x750',
    'json': {
    'name': 'Molly Palmer',
    'address': '276 Smith Lock\nNew Melissachester, CO 03485',
},
    'key27232': 'value41131',
    'key26697': 'value2781',
    'key76101': 'value80222',
    'key40665': 'value65089',
    'key34285': 'value16812',
    'key52027': 'value58090',
},
    {
    'id': 17527490816219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Vincent Avila',
    'address': 'USS Ramirez\nFPO AE 05100',
    'text': 'We why have necessary us free weight. Campaign as political together statement. Heart best successful many or leg exist.',
    'email': 'sandersthomas@example.net',
    'phone_number': '6232413461',
    'json': {
    'name': 'Melissa Blevins',
    'address': '84240 Hunter Run\nEdwardsberg, WI 39823',
},
    'key8848': 'value4634',
    'key11166': 'value78294',
    'key78374': 'value37499',
    'key56863': 'value1212',
    'key5502': 'value75154',
    'key5873': 'value23128',
    'key64385': 'value81691',
    'key32011': 'value10351',
},
    {
    'id': 17527490816230,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Rebecca Morales',
    'address': '60255 Howard Springs Suite 936\nTeresastad, VT 17618',
    'text': 'Type economy program natural ball wife business. Character detail himself claim any.\nCountry budget pay agent economy. Newspaper unit senior even daughter. Republican difficult vote him.',
    'email': 'jennifersmith@example.com',
    'phone_number': '7878731225',
    'json': {
    'name': 'Sarah Walker',
    'address': '7806 John Shoals Apt. 453\nMontgomeryside, TN 27092',
},
    'key24206': 'value78137',
},
    {
    'id': 17527490816241,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Dennis Tran',
    'address': '8618 Tyler Gardens Suite 703\nWest Stacyfurt, DE 48327',
    'text': 'Participant participant image what toward area Mr. Science agree choice Republican. Born professor fear medical simple energy.',
    'email': 'derrick81@example.com',
    'phone_number': '549-908-8367',
    'json': {
    'name': 'Rebecca Brown',
    'address': '10368 Shaw Row\nTimothystad, TN 68196',
},
    'key48833': 'value7734',
    'key38945': 'value78561',
    'key6930': 'value59405',
    'key57583': 'value47876',
    'key59709': 'value71748',
    'key79000': 'value17924',
    'key66099': 'value33697',
    'key74919': 'value27097',
},
    {
    'id': 17527490816252,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Betty Bailey',
    'address': '085 Debra Fork Suite 696\nSeanborough, AK 86062',
    'text': 'Still history few lose. Decade candidate relate us charge so without. Here station wind develop commercial large news.',
    'email': 'michelle37@example.org',
    'phone_number': '+1-370-427-8629',
    'json': {
    'name': 'Donald Matthews',
    'address': '8593 Fernando Run\nOlsenmouth, GU 01453',
},
    'key73449': 'value95807',
    'key69588': 'value95221',
    'key99055': 'value98363',
    'key18664': 'value94495',
    'key61296': 'value68640',
},
    {
    'id': 17527490816262,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Charles Reed',
    'address': '7525 James Park\nEatonville, AR 18217',
    'text': 'Listen far material world.\nRather beautiful reveal power fine spend.\nOur check level. Ten would different activity enough those management. Somebody last pressure else.',
    'email': 'ggoodman@example.net',
    'phone_number': '(986)641-7751x988',
    'json': {
    'name': 'Brandon Jackson',
    'address': '75406 Charles Springs Apt. 283\nNortonchester, WA 64100',
},
    'key29606': 'value93889',
    'key92079': 'value7190',
},
    {
    'id': 17527490816273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jenny Wallace DDS',
    'address': '8466 Laura Brook\nNorth Danielle, NY 96591',
    'text': 'Class kitchen the leave. Away wait read clearly agent improve image.\nAffect central floor number then guy.\nNot week get cold. Marriage huge star community recently.',
    'email': 'leetyrone@example.net',
    'phone_number': '(557)337-4534x3089',
    'json': {
    'name': 'Ricky Dickerson',
    'address': '072 Little Fields Apt. 459\nWrightchester, CT 65096',
},
    'key95251': 'value23089',
    'key84261': 'value12723',
    'key45092': 'value42456',
    'key14888': 'value87854',
    'key59813': 'value42953',
    'key80682': 'value68220',
    'key73103': 'value69142',
    'key42255': 'value99801',
    'key56089': 'value7753',
    'key65841': 'value66036',
},
    {
    'id': 17527490816286,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Timothy Stephenson',
    'address': '2637 Jason Cove Apt. 039\nRhondaport, FM 86256',
    'text': 'Crime actually he decade summer. Question commercial near among.\nWhen later most police. Industry operation whole treat follow. Something adult four market investment officer.',
    'email': 'woliver@example.com',
    'phone_number': '4394490892',
    'json': {
    'name': 'Tiffany Riley',
    'address': '02694 Adam Land\nNew Jeremy, FM 99124',
},
    'key40721': 'value34562',
},
    {
    'id': 17527490816298,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Gary Watts',
    'address': '789 Gabriel Forest\nNew Tracyshire, KS 69241',
    'text': 'Work program where old economic. Own after bank wish money.\nIndustry society never know a increase reality enter. Light central mission present. Body lay seat cultural policy exist try.',
    'email': 'lbennett@example.org',
    'phone_number': '001-491-299-5924x366',
    'json': {
    'name': 'Amy White',
    'address': '6786 Misty Coves\nPort Moniquetown, NY 85973',
},
    'key65020': 'value32296',
    'key18603': 'value63693',
    'key29087': 'value35763',
    'key74691': 'value48064',
    'key93535': 'value84223',
    'key98178': 'value46455',
    'key98614': 'value82749',
},
    {
    'id': 17527490816312,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Angela Johnson',
    'address': 'USNS Young\nFPO AP 89019',
    'text': 'Final dream about street analysis race establish. Player front from range girl later on.\nRecent establish week. As however military. Movement identify like size safe major rather.',
    'email': 'waynelewis@example.net',
    'phone_number': '378.825.2577x3380',
    'json': {
    'name': 'Shelly Cooper',
    'address': '5531 Bryant Crescent\nPort Angel, CO 08828',
},
    'key20057': 'value35920',
    'key43147': 'value88573',
    'key58269': 'value34725',
    'key81661': 'value79418',
    'key13936': 'value46302',
    'key30935': 'value70196',
    'key75798': 'value52498',
    'key89906': 'value48006',
    'key61815': 'value64409',
},
    {
    'id': 17527490816323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Michael Owens',
    'address': '14335 Carter Road Suite 867\nTiffanystad, SC 14440',
    'text': 'Certain computer science present certain. Heavy best town network president.',
    'email': 'hbaker@example.com',
    'phone_number': '928-621-6288x4119',
    'json': {
    'name': 'Robert Turner',
    'address': '662 Jared Villages Suite 074\nBauerton, TN 89407',
},
    'key27553': 'value20117',
    'key29820': 'value43679',
    'key20661': 'value18969',
},
    {
    'id': 17527490816334,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Dr. Anthony West',
    'address': '07946 Miller Roads\nFreemanland, SC 41247',
    'text': 'State father agent near job. Improve security oil security administration.\nMaybe by hard pass trial. Mean first walk surface. Yes drug relate court thank carry.',
    'email': 'cynthia80@example.net',
    'phone_number': '+1-560-396-3725x7487',
    'json': {
    'name': 'Melissa Burns',
    'address': '1133 Lawson Extension Apt. 506\nPort Kathy, PA 57199',
},
    'key51743': 'value93220',
    'key84303': 'value32860',
},
    {
    'id': 17527490816345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Ashley Ramos',
    'address': '90958 Benjamin Stream\nMichaelside, AS 63834',
    'text': 'Brother rate food soon debate may smile. Sport bad simple.\nFloor such night lawyer stock phone bed here. There sense brother lead admit fast.',
    'email': 'john19@example.net',
    'phone_number': '904.494.3259',
    'json': {
    'name': 'Donald Rivera',
    'address': '721 Janice Inlet\nNorth Timothyview, UT 16302',
},
    'key25030': 'value70016',
},
    {
    'id': 17527490816355,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Amanda Elliott',
    'address': 'PSC 1059, Box 0688\nAPO AA 65312',
    'text': 'Cause usually help couple under note here. Allow police light management skill describe. Type pick others officer.\nDay less perform away draw worker. Even raise audience like throughout else leave.',
    'email': 'jean32@example.com',
    'phone_number': '(933)586-5975x8912',
    'json': {
    'name': 'Gordon Shaw',
    'address': '39128 Jackson Shoals\nFreemanburgh, NJ 85323',
},
    'key68956': 'value83499',
    'key99808': 'value21368',
},
    {
    'id': 17527490816364,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Paul Price',
    'address': '681 Harmon Mount Apt. 482\nShellyhaven, KY 32751',
    'text': 'Box task ball concern thus pay time speak. But out threat with. Enough price laugh protect.',
    'email': 'dodsontammy@example.org',
    'phone_number': '453-816-8114x5909',
    'json': {
    'name': 'Ruben Williamson',
    'address': '607 Cody Union Apt. 423\nBoydbury, LA 67106',
},
    'key14016': 'value35809',
    'key23552': 'value55853',
    'key33491': 'value5447',
    'key98172': 'value10587',
    'key22743': 'value22261',
},
    {
    'id': 17527490816375,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Xavier Garcia',
    'address': '7700 Phillips Lane\nPort Ryan, WA 70780',
    'text': 'Particular traditional later soldier common. Month religious school fire community PM his. Industry capital instead forward who.',
    'email': 'zhicks@example.com',
    'phone_number': '+1-760-896-6034x90082',
    'json': {
    'name': 'Jennifer Chambers',
    'address': '420 Gomez Lodge\nLake Matthew, VI 79805',
},
    'key25666': 'value14071',
    'key18781': 'value57421',
    'key48211': 'value9684',
},
    {
    'id': 17527490816386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Steven Murphy',
    'address': '6173 Todd Knolls\nLarryport, OH 02586',
    'text': 'Support own religious what no field. Plan describe kind land back beyond plant over. Night easy become green he down knowledge.\nTrouble next life month amount. On push direction provide indicate.',
    'email': 'bakererin@example.org',
    'phone_number': '(625)745-6339x97332',
    'json': {
    'name': 'Aaron Webb',
    'address': '872 Steven Ramp\nLake Leslie, VA 26716',
},
    'key30786': 'value20029',
    'key26002': 'value931',
    'key39471': 'value381',
    'key17872': 'value77494',
    'key79746': 'value94853',
},
    {
    'id': 17527490816396,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Malik Bailey',
    'address': '7524 Cheryl Avenue\nLesliehaven, NV 77303',
    'text': 'Anything activity campaign of. Which property say run study.\nArrive make several toward use tell wonder expert. Loss responsibility agreement common. Wife quickly group method.',
    'email': 'meganmiranda@example.com',
    'phone_number': '925-694-6621x820',
    'json': {
    'name': 'Lauren Gonzalez',
    'address': 'Unit 1476 Box 1701\nDPO AA 53336',
},
    'key97849': 'value33093',
    'key77549': 'value20268',
    'key99581': 'value16708',
    'key81705': 'value34571',
    'key27268': 'value35660',
},
    {
    'id': 17527490816406,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Joshua Barton',
    'address': '59924 Jessica Shore Apt. 619\nJaystad, MI 03151',
    'text': 'Reveal shake service. Tough interest draw word sister. Follow successful well left type another however paper.\nTime note friend no. Commercial decade point kitchen machine card. Indeed true door.',
    'email': 'akennedy@example.com',
    'phone_number': '+1-283-916-0354',
    'json': {
    'name': 'Timothy Hood',
    'address': '8437 Brian Creek\nEast Kevin, MH 99717',
},
    'key12806': 'value73319',
    'key63065': 'value7191',
    'key78871': 'value47301',
    'key96756': 'value2510',
    'key27032': 'value51397',
},
    {
    'id': 17527490816416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Mrs. Heidi Murphy MD',
    'address': '03496 Reed Haven\nSmithhaven, AK 56038',
    'text': 'Push stay lawyer hot at positive anything. Majority get trip toward. Good case he.\nFinal appear project reflect word its. Almost expert edge provide more big region government.',
    'email': 'baileyjoseph@example.net',
    'phone_number': '398.599.9435',
    'json': {
    'name': 'Kyle Mckee',
    'address': '3219 George Roads\nBrownbury, AL 95123',
},
    'key12979': 'value51860',
    'key17589': 'value34413',
},
    {
    'id': 17527490816428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Tammy Hodges',
    'address': '061 Kenneth Run\nNew Davidport, AR 74262',
    'text': 'Teach job particularly also large quality spring. Another economic enter model.',
    'email': 'fwarren@example.com',
    'phone_number': '344.239.0572',
    'json': {
    'name': 'Penny Olsen',
    'address': '306 Jaime Skyway Suite 747\nSouth Clinton, DC 76291',
},
    'key48315': 'value32800',
    'key24407': 'value40987',
    'key88719': 'value57604',
    'key37654': 'value27953',
    'key29615': 'value57462',
    'key22042': 'value61147',
    'key87749': 'value91923',
    'key60119': 'value76490',
    'key5023': 'value35902',
    'key79734': 'value93698',
},
    {
    'id': 17527490816438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Leslie Zuniga',
    'address': '3282 Bill Mill Suite 602\nMatthewchester, HI 13751',
    'text': 'Least some this their picture. Do what husband college mention actually easy. Food economy participant experience than. Response do time over people history.',
    'email': 'cartersteven@example.net',
    'phone_number': '(797)676-1790x435',
    'json': {
    'name': 'John Jones',
    'address': '8383 Cline Knoll\nSouth Lisabury, MT 71277',
},
    'key98414': 'value75135',
    'key48184': 'value7431',
},
    {
    'id': 17527490816450,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Michael Thomas',
    'address': 'PSC 6580, Box 8506\nAPO AP 86412',
    'text': 'Contain project democratic check industry. Him no section certain against. Free six father central ahead floor protect. Explain agreement thousand threat.',
    'email': 'whitelauren@example.com',
    'phone_number': '+1-975-415-0142',
    'json': {
    'name': 'Steven Nash',
    'address': '8146 Ronald Locks\nWest Jennifer, HI 95726',
},
    'key34750': 'value90477',
    'key57940': 'value85887',
    'key13233': 'value80132',
    'key1353': 'value92775',
    'key17646': 'value42414',
    'key10287': 'value88816',
},
    {
    'id': 17527490816459,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jodi Sanders',
    'address': '755 Gray Rest\nPort Amy, OK 93425',
    'text': 'Save around just travel from here. Particularly degree teach whose trouble time forget. Travel garden evidence our class.',
    'email': 'wandaklein@example.com',
    'phone_number': '(684)834-0817x5424',
    'json': {
    'name': 'Tammy Daniel',
    'address': '9152 Harris Landing Suite 978\nMarthahaven, NY 95774',
},
    'key81252': 'value78019',
    'key38740': 'value35039',
    'key79185': 'value32804',
    'key98147': 'value58818',
    'key68893': 'value13084',
    'key74991': 'value10385',
    'key63508': 'value37930',
    'key37833': 'value1769',
    'key37765': 'value42621',
    'key72297': 'value97214',
},
    {
    'id': 17527490816470,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'William Richardson',
    'address': '68539 Joseph Estate Apt. 567\nSouth Colleen, OH 01368',
    'text': 'Economic institution little attention baby. Sit process old unit issue wish.\nDown recognize order practice send own your tough. With through foot fact.',
    'email': 'amurphy@example.org',
    'phone_number': '001-410-208-1353x074',
    'json': {
    'name': 'Jessica Barron',
    'address': '72110 Richard Ports\nNew Lisa, NC 09826',
},
    'key72150': 'value5687',
    'key25168': 'value94504',
    'key13058': 'value83742',
    'key36314': 'value54143',
    'key49442': 'value74404',
},
    {
    'id': 17527490816481,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Philip Rodriguez',
    'address': '787 Smith Ways\nPort William, CO 16788',
    'text': 'Economic success system part create. Purpose about add expect.',
    'email': 'jo03@example.com',
    'phone_number': '485-219-1759x98297',
    'json': {
    'name': 'Tanya Bell',
    'address': 'PSC 4990, Box 8530\nAPO AA 07122',
},
    'key54966': 'value89153',
    'key37058': 'value87597',
    'key85491': 'value73323',
    'key62753': 'value75016',
    'key65856': 'value14342',
    'key92114': 'value69807',
    'key42789': 'value81296',
    'key75721': 'value74891',
    'key79747': 'value20339',
},
    {
    'id': 17527490816489,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Chelsea Allen',
    'address': 'Unit 8073 Box 0870\nDPO AE 42564',
    'text': 'Take fill house team impact task various. Condition itself best make time site option.',
    'email': 'ygould@example.net',
    'phone_number': '+1-345-370-4102x25404',
    'json': {
    'name': 'Christina Velazquez',
    'address': '07572 Wilson Common\nNew Kaitlyn, MD 03165',
},
    'key32946': 'value8192',
    'key69063': 'value17777',
},
    {
    'id': 17527490816498,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Teresa Campbell',
    'address': '6461 Justin Manors Apt. 910\nNorth Christopherbury, MS 86228',
    'text': 'Happen task either pattern. Building prevent or three. Mission realize yes car.\nMinute current nation size peace heart other.',
    'email': 'stephanie35@example.org',
    'phone_number': '521-997-6649',
    'json': {
    'name': 'Kevin Anderson',
    'address': '438 Andres Harbor\nJuliafurt, FM 33512',
},
    'key87527': 'value36919',
    'key14502': 'value34038',
    'key71888': 'value32725',
    'key18187': 'value92712',
    'key76572': 'value90198',
    'key90317': 'value56108',
    'key54391': 'value41554',
    'key54868': 'value87315',
},
    {
    'id': 17527490816508,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Sara Anderson',
    'address': '610 Day Junction Suite 181\nGregoryland, MI 36473',
    'text': 'Apply family economy. Big happen western money. Cost often fill less although.\nFeeling show approach Mrs audience. Card process fast space age feeling. Within evidence live sing later energy.',
    'email': 'kimberlyrodriguez@example.org',
    'phone_number': '3655084770',
    'json': {
    'name': 'Janet Williams',
    'address': '5832 Butler Brooks Suite 754\nKimberlymouth, AZ 26842',
},
    'key9755': 'value7262',
},
    {
    'id': 17527490816520,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Mr. Jason Clark',
    'address': '8190 Patricia Route Suite 144\nMargaretbury, SC 67691',
    'text': 'Pattern level bit rich grow less everything. Painting not baby approach.\nNo modern environment fear military. Herself partner window history include mission yard.',
    'email': 'william33@example.org',
    'phone_number': '4153237953',
    'json': {
    'name': 'Sharon Pitts',
    'address': '37143 Gary Drives\nNew Brianburgh, VA 20352',
},
    'key56425': 'value87615',
    'key13753': 'value7435',
    'key42677': 'value6805',
    'key86816': 'value85084',
    'key78385': 'value85377',
},
    {
    'id': 17527490816530,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Ronnie Lucero',
    'address': '5624 Jeff Tunnel\nHarpermouth, OR 79597',
    'text': 'Management truth likely today should discussion rather. Plan standard my how fly day. Artist friend present once represent.',
    'email': 'brian97@example.net',
    'phone_number': '336.231.0540x501',
    'json': {
    'name': 'Dawn Campbell',
    'address': '889 William Turnpike Apt. 187\nMaryview, WV 46740',
},
    'key40949': 'value91734',
    'key50022': 'value32246',
},
    {
    'id': 17527490816540,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Michael Jenkins',
    'address': '82853 Richard Points Apt. 559\nSouth Jeanetteside, RI 01147',
    'text': 'Technology wait none. Really face some pick provide. Majority person clearly much.\nPoor she pick report. Maybe short station allow.',
    'email': 'barnesdennis@example.net',
    'phone_number': '+1-926-675-1443x0013',
    'json': {
    'name': 'Michelle Webb',
    'address': '7242 Walker Prairie Suite 517\nKatiestad, WI 63243',
},
    'key97078': 'value65726',
    'key56920': 'value95430',
    'key22740': 'value57550',
    'key88868': 'value12333',
    'key15913': 'value40855',
    'key15146': 'value80714',
    'key76184': 'value44917',
    'key29041': 'value36733',
    'key8207': 'value9072',
},
    {
    'id': 17527490816552,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Wendy Cunningham',
    'address': '5102 Tanner Fort Suite 533\nJenniferfort, SC 78846',
    'text': 'Military glass reduce should magazine. Share shake account water table.\nFinally job marriage. Mr minute month soon four decide more. Someone Democrat city free where remain check ball.',
    'email': 'delgadoroberto@example.net',
    'phone_number': '001-562-694-2863x3128',
    'json': {
    'name': 'James Bright',
    'address': '241 Jefferson Lock\nWalterfurt, GU 63899',
},
    'key18777': 'value89730',
    'key64532': 'value24865',
    'key49104': 'value92418',
},
    {
    'id': 17527490816564,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Mark Green',
    'address': '9148 Jason Estates\nTimothyport, CO 34377',
    'text': 'Admit save item open commercial. How administration season level scene trial under maybe. Family democratic baby question charge think theory remain.',
    'email': 'marclarson@example.net',
    'phone_number': '8282727223',
    'json': {
    'name': 'Victoria Benitez',
    'address': '940 Linda Forks\nJohnsonchester, HI 33932',
},
    'key62794': 'value19056',
    'key2711': 'value51940',
    'key53403': 'value94187',
    'key24207': 'value58139',
    'key53700': 'value12561',
    'key81643': 'value95952',
    'key61716': 'value13041',
    'key71394': 'value34002',
    'key36982': 'value3326',
    'key21804': 'value44949',
},
    {
    'id': 17527490816575,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Jeffrey Obrien',
    'address': '6278 Jennifer Manors Apt. 181\nPort Aaronside, UT 48351',
    'text': 'Radio manager save say nation last. Sign else author do list.\nHome stage everything risk agent.\nPay ten miss.',
    'email': 'thompsonlogan@example.org',
    'phone_number': '333-707-0068',
    'json': {
    'name': 'Kenneth King',
    'address': '54733 Porter Forges Suite 408\nChristianmouth, FL 53340',
},
    'key26446': 'value66148',
    'key2015': 'value49948',
    'key36220': 'value12554',
    'key25279': 'value2436',
    'key5309': 'value68004',
    'key72837': 'value68689',
    'key42107': 'value92192',
},
    {
    'id': 17527490816587,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Craig Cox',
    'address': '385 Ryan Islands Apt. 580\nLake Miranda, MP 32830',
    'text': 'Hot deal everything try room dark threat. Almost speech wonder movement clear suggest road include.\nDeal the require forward health provide. Trial much morning board political these really.',
    'email': 'david80@example.org',
    'phone_number': '562-789-2926',
    'json': {
    'name': 'Kimberly Stone',
    'address': '61537 Megan Valleys Apt. 997\nLewisport, GA 38449',
},
    'key60420': 'value18522',
    'key84336': 'value60802',
    'key755': 'value87908',
},
    {
    'id': 17527490816597,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'David Beck',
    'address': '751 Michael Ports Apt. 664\nNew Edwardview, CT 32904',
    'text': 'Weight push even. Than fill who room keep.\nTrade begin already site. Tree surface against. Wear teacher assume tonight. Skin woman give international.',
    'email': 'traviscooper@example.org',
    'phone_number': '001-246-296-8785',
    'json': {
    'name': 'Steven Smith',
    'address': '952 Barr Road\nWest Erin, TN 90615',
},
    'key53323': 'value73499',
    'key80775': 'value42891',
    'key52631': 'value83292',
    'key68157': 'value57938',
},
    {
    'id': 17527490816609,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Thomas Robinson',
    'address': '470 Adrienne Estates\nKathyfurt, VI 06213',
    'text': 'Fly side scientist finish. Relate base follow. Understand thus nice tend once.',
    'email': 'mchristian@example.org',
    'phone_number': '668.998.0562',
    'json': {
    'name': 'Ricky Keith',
    'address': '1124 Christine Gardens\nJustinfort, OK 20188',
},
    'key92699': 'value63227',
    'key47140': 'value3579',
    'key83125': 'value73647',
},
    {
    'id': 17527490816619,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Stacy Harris',
    'address': '855 Nicholas Place Apt. 384\nLauraville, MP 04011',
    'text': 'Front consider Congress accept from system north. Specific over who. Now agreement pull. Stand draw service put season career.',
    'email': 'sandraperez@example.com',
    'phone_number': '+1-865-411-9033x9429',
    'json': {
    'name': 'Anthony Powell',
    'address': '061 Cooper Via\nSeanstad, IN 39407',
},
    'key18843': 'value96073',
    'key1121': 'value96621',
    'key91183': 'value75463',
    'key52139': 'value13322',
},
    {
    'id': 17527490816629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'David Hayes',
    'address': '67812 Davis Roads Suite 859\nEast Sierraborough, IL 92443',
    'text': 'Necessary another grow any sea participant.\nBoy community theory third. Health offer debate feeling ability. Weight fill foot manage account claim attention.',
    'email': 'howardcharles@example.com',
    'phone_number': '417.526.1149x939',
    'json': {
    'name': 'Bethany Rodriguez',
    'address': 'Unit 2313 Box 3580\nDPO AA 45943',
},
    'key63855': 'value74188',
    'key46244': 'value55897',
    'key61208': 'value63171',
    'key37972': 'value21218',
},
    {
    'id': 17527490816639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Kristen Moore',
    'address': '6006 Alejandra Station Apt. 814\nWest Michelleport, RI 39243',
    'text': 'May try control art through. Tree south during sure. Public arrive product produce here.',
    'email': 'nicoledavis@example.com',
    'phone_number': '(477)425-5634x092',
    'json': {
    'name': 'Devin Morales',
    'address': '8512 Mcknight Lock Apt. 709\nMichaelmouth, KS 62123',
},
    'key4678': 'value23412',
    'key19677': 'value99781',
    'key81574': 'value92018',
    'key71615': 'value99379',
    'key14012': 'value11159',
    'key33871': 'value64348',
    'key61876': 'value23760',
    'key33450': 'value91737',
},
    {
    'id': 17527490816650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Brittany Schneider',
    'address': '943 Samantha Corner\nLake Jordanland, NV 12645',
    'text': 'Base strong mission more money task occur. Visit still my born enter crime town.\nHe rise every thus. Above list gun most budget poor president. Her parent particularly these.',
    'email': 'dmorgan@example.org',
    'phone_number': '977.591.9966x78310',
    'json': {
    'name': 'Jose Craig',
    'address': '5735 Castillo Glens Suite 774\nJessicaport, TN 14975',
},
    'key61612': 'value21449',
},
    {
    'id': 17527490816661,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Alicia Robertson',
    'address': '71786 Jennifer Mountain\nPort James, SD 73283',
    'text': 'Pressure billion protect report resource bit. Report public market discover political. Contain theory vote including end note change. Eat never speak left cultural boy music.',
    'email': 'qalvarez@example.org',
    'phone_number': '316-229-6028x48476',
    'json': {
    'name': 'Michael Peterson',
    'address': '81520 Clark Light\nMatthewsland, ND 33161',
},
    'key51030': 'value8321',
    'key46731': 'value6488',
    'key1293': 'value97046',
    'key29150': 'value5951',
    'key59781': 'value48172',
    'key82754': 'value18096',
    'key22514': 'value17476',
    'key52016': 'value42670',
    'key40596': 'value47100',
    'key14301': 'value5565',
},
    {
    'id': 17527490816671,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Ashley Barnes',
    'address': '66323 Jackson Mission Suite 753\nSouth Sara, AZ 14605',
    'text': 'Place game imagine fire town year walk. Full seek power while occur central. Young maybe just allow.',
    'email': 'amber00@example.net',
    'phone_number': '001-458-405-9505x80403',
    'json': {
    'name': 'Alexa Burgess',
    'address': '6914 Le Harbors Apt. 117\nWest Jamesbury, MT 01035',
},
    'key10470': 'value1866',
    'key89532': 'value79055',
    'key68499': 'value83293',
    'key80194': 'value97092',
    'key2366': 'value41911',
    'key83012': 'value53663',
    'key83665': 'value32765',
    'key19431': 'value78958',
    'key94127': 'value16091',
},
    {
    'id': 17527490816682,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jessica Wolfe',
    'address': '5268 Smith Gateway\nParkerstad, PA 29903',
    'text': 'None nearly song town learn information oil. Fact career important southern go.\nUp hotel above treatment. Discussion effort talk industry mother lawyer certainly address.',
    'email': 'john46@example.net',
    'phone_number': '579.368.7428x75342',
    'json': {
    'name': 'Nicholas Leach',
    'address': '12105 Casey Fork Apt. 874\nPort Jesseborough, PA 35991',
},
    'key93199': 'value7787',
},
    {
    'id': 17527490816693,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Tanya Hernandez',
    'address': '0417 Michelle Camp\nEast Traviston, IN 17878',
    'text': 'Agent stock decade pretty five prepare choose. Trip once remain real. Girl manage common according rise.\nAudience throughout score whatever east wear down. Hard boy table everyone continue suddenly.',
    'email': 'ariana95@example.com',
    'phone_number': '+1-210-344-7836x440',
    'json': {
    'name': 'Sarah Chaney',
    'address': '839 Alejandro Neck Suite 663\nMichaelside, MP 04874',
},
    'key2029': 'value53662',
    'key52434': 'value10397',
    'key18121': 'value42599',
    'key32600': 'value76991',
    'key84830': 'value98458',
    'key38952': 'value77820',
    'key18188': 'value97507',
},
    {
    'id': 17527490816704,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Mallory Stephens',
    'address': '159 Sarah Valleys\nNew Julie, AS 82467',
    'text': 'Exist newspaper appear painting American minute. Course present station wide wind discussion bad sell.',
    'email': 'sjames@example.net',
    'phone_number': '+1-871-944-8713',
    'json': {
    'name': 'Joy Snyder',
    'address': '72487 Jenna Garden Apt. 306\nPort Amberborough, KS 04630',
},
    'key64350': 'value50387',
},
    {
    'id': 17527490816715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Joseph Bailey',
    'address': 'PSC 2028, Box 0456\nAPO AP 70492',
    'text': 'Level until tax one. Entire inside sort garden huge billion child. Difficult budget energy.\nWhat administration what may help life soldier. Growth top policy position national light.',
    'email': 'yhudson@example.org',
    'phone_number': '743-743-0268',
    'json': {
    'name': 'Debbie Moody',
    'address': '8897 Davis Walk\nHarrisburgh, AR 82505',
},
    'key16109': 'value33613',
    'key25809': 'value19999',
    'key29253': 'value36157',
    'key27719': 'value91296',
    'key95871': 'value67740',
    'key54104': 'value82865',
    'key12768': 'value69497',
    'key56864': 'value34582',
    'key60334': 'value30074',
},
    {
    'id': 17527490816725,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'William Bush',
    'address': '586 Miller Ville Apt. 742\nEast Danielborough, MN 52751',
    'text': 'Real become about trial. Financial common early already ground catch front. Statement piece bed weight point key treat chance.\nWord down author take role give. Goal everyone challenge do.',
    'email': 'mdrake@example.com',
    'phone_number': '001-931-311-7038x6702',
    'json': {
    'name': 'John Richardson',
    'address': '519 Brock Rapid\nTateburgh, HI 81993',
},
    'key30953': 'value24106',
    'key79706': 'value57777',
    'key38646': 'value58074',
    'key56874': 'value53679',
    'key63402': 'value15578',
    'key72619': 'value98084',
},
    {
    'id': 17527490816737,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Emily Garcia',
    'address': '23946 Acevedo Corners\nPooleport, MS 30804',
    'text': 'They part Congress be ask measure.\nHour will at first people court voice. Toward do movement. Big large reveal crime also expert. Account hotel prove apply American successful.',
    'email': 'holtveronica@example.org',
    'phone_number': '+1-302-293-0729x111',
    'json': {
    'name': 'Peggy Miller',
    'address': '590 David Mountain\nLake Tiffanyport, WV 90274',
},
    'key60833': 'value58000',
    'key58510': 'value14366',
    'key41593': 'value60055',
    'key46721': 'value52834',
    'key30803': 'value71632',
    'key66064': 'value86035',
    'key79638': 'value56663',
    'key5602': 'value55683',
    'key11092': 'value35249',
    'key16435': 'value76257',
},
    {
    'id': 17527490816749,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Michael Medina',
    'address': '550 Joseph Ridge Apt. 097\nCaldwellhaven, FL 20266',
    'text': 'None management lay hope child course sound. President program fall station hard writer. Actually do everyone return keep fear crime reduce.',
    'email': 'yoderpaul@example.net',
    'phone_number': '242.944.1258x79577',
    'json': {
    'name': 'Francisco Smith',
    'address': '158 Ricky Mission\nSouth Albert, OH 49051',
},
    'key56153': 'value90413',
    'key33981': 'value43622',
    'key94056': 'value37850',
    'key68618': 'value59314',
    'key68306': 'value68810',
    'key83604': 'value16043',
    'key45524': 'value43706',
    'key90134': 'value36769',
    'key85290': 'value5314',
    'key95966': 'value38305',
},
    {
    'id': 17527490816761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Sean White',
    'address': 'Unit 4045 Box 8584\nDPO AE 30047',
    'text': 'Mean each help her still billion whose. Ok big easy serious save once. While teach tax note car wide.\nThey single land east player. Theory present TV media race could executive.',
    'email': 'joshua65@example.net',
    'phone_number': '001-778-237-6903x3687',
    'json': {
    'name': 'Crystal Lyons',
    'address': '601 Gregory Inlet\nPollardchester, CO 84276',
},
    'key44601': 'value19454',
    'key78476': 'value96020',
    'key69593': 'value3323',
},
    {
    'id': 17527490816770,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Kelly Clark',
    'address': '41274 Kelsey Unions\nNorth Jamesland, AZ 88134',
    'text': 'Baby situation key poor. Medical movement pull cold situation catch if. Home much its effect court.',
    'email': 'paulcarter@example.com',
    'phone_number': '697.992.4979x596',
    'json': {
    'name': 'Angel Murphy',
    'address': '8503 Smith Avenue\nLake Roybury, NM 47079',
},
    'key58755': 'value46863',
    'key40304': 'value57942',
    'key39123': 'value47290',
    'key60465': 'value49064',
    'key13333': 'value84364',
},
    {
    'id': 17527490816782,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jonathon Miller',
    'address': '0701 Wells Prairie\nLake Natasha, ND 20781',
    'text': 'Arrive everyone threat suggest watch why forget. Order oil ball student whole guy. Nation form visit break throughout as allow.',
    'email': 'qduncan@example.net',
    'phone_number': '607-731-0406',
    'json': {
    'name': 'George Williams',
    'address': '39673 Brian Turnpike Apt. 388\nLake Rebecca, MH 12111',
},
    'key11526': 'value48395',
    'key87747': 'value33006',
    'key2670': 'value89400',
    'key230': 'value83965',
},
    {
    'id': 17527490816793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Aaron Johnson',
    'address': '4437 Jason Squares\nNorth Roy, ME 68096',
    'text': 'Everybody carry doctor cover buy billion culture. Some next worry walk tax. Grow open good rest.\nHe serve majority exactly decision quality. Top wife company interview.',
    'email': 'rcraig@example.com',
    'phone_number': '599.892.4165',
    'json': {
    'name': 'Robert Case',
    'address': '68182 Stafford Land\nLake Tiffanymouth, TX 74545',
},
    'key58419': 'value53973',
    'key84572': 'value6655',
    'key2340': 'value46939',
    'key43181': 'value78911',
    'key73670': 'value5650',
    'key12820': 'value60105',
    'key3612': 'value33453',
    'key71967': 'value6941',
    'key36437': 'value31290',
    'key99270': 'value58254',
},
    {
    'id': 17527490816804,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Charles Woods',
    'address': '6822 Sarah Circles\nBurnsland, FL 98019',
    'text': 'Important property occur course open pretty might. Record bill article ability station cause.',
    'email': 'lharmon@example.org',
    'phone_number': '791-669-6386x96719',
    'json': {
    'name': 'Thomas Merritt',
    'address': 'PSC 6885, Box 1901\nAPO AE 95608',
},
    'key12949': 'value31112',
    'key77287': 'value94415',
    'key34596': 'value16988',
    'key53732': 'value46555',
    'key45449': 'value49067',
    'key54464': 'value60987',
    'key34046': 'value3772',
},
    {
    'id': 17527490816813,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Cindy Pruitt',
    'address': '039 Beth Lights Suite 434\nTaylorchester, ND 90429',
    'text': 'Computer program relate raise write. Car book easy here court. Voice most affect. Tv much care better art end.',
    'email': 'josephcole@example.org',
    'phone_number': '(509)518-9448',
    'json': {
    'name': 'Lisa Garrett',
    'address': '650 Gross Meadows\nRoberttown, MI 19828',
},
    'key65776': 'value11113',
    'key6905': 'value46876',
    'key89275': 'value45446',
},
    {
    'id': 17527490816825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'James Smith',
    'address': 'PSC 7843, Box 9898\nAPO AA 75564',
    'text': 'Policy performance computer indicate carry eye. Color large week figure central indeed join. Kind financial ahead least grow can offer. Explain book know economic organization hot unit always.',
    'email': 'stevebrown@example.net',
    'phone_number': '684-500-6522x03013',
    'json': {
    'name': 'Terry Mcneil',
    'address': '354 Albert Island\nTerriview, PW 41247',
},
    'key63593': 'value8080',
    'key78932': 'value5726',
    'key80555': 'value78084',
    'key14691': 'value11622',
    'key60117': 'value97485',
    'key49883': 'value62120',
    'key65023': 'value77581',
    'key31830': 'value82267',
},
    {
    'id': 17527490816835,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Bradley Booker',
    'address': '04338 Anderson Avenue Suite 886\nPort Matthew, WY 56043',
    'text': 'Who visit ready former six whether fill. Ask well available impact defense wear. Finally your tree total.\nMethod resource toward maintain smile. Share teacher difficult deal successful.',
    'email': 'jpalmer@example.org',
    'phone_number': '(241)212-5662',
    'json': {
    'name': 'Alexis Lynn',
    'address': '190 William Harbors\nJonesland, GU 02614',
},
    'key47358': 'value250',
    'key7663': 'value76615',
    'key89277': 'value57670',
},
    {
    'id': 17527490816847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Crystal Welch',
    'address': 'USNV Sherman\nFPO AA 91107',
    'text': 'Little easy travel lose friend out who very. Dog majority option whatever bill. These environment east.',
    'email': 'bishopdavid@example.org',
    'phone_number': '654.237.2453x41671',
    'json': {
    'name': 'Jessica Pena',
    'address': '598 Barnes Forges Suite 454\nJefferyhaven, VA 52756',
},
    'key9569': 'value32248',
    'key62505': 'value85772',
    'key10799': 'value66370',
    'key61565': 'value43494',
    'key26695': 'value71388',
    'key84191': 'value2582',
    'key61795': 'value33975',
    'key56988': 'value85502',
    'key79384': 'value65045',
    'key99863': 'value13900',
},
    {
    'id': 17527490816858,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Samantha Price',
    'address': '71066 Patrick Gardens Apt. 351\nWest Trevor, TN 69991',
    'text': 'Mission anyone town check serious recent ground. Discuss manager article environmental need.',
    'email': 'kevinmiller@example.org',
    'phone_number': '001-312-419-7684x95038',
    'json': {
    'name': 'Patty Rubio',
    'address': 'USS Wong\nFPO AP 30113',
},
    'key49357': 'value45303',
},
    {
    'id': 17527490816869,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Frank Wolfe',
    'address': '8823 Mark Crossroad Suite 666\nSmithport, FL 36210',
    'text': 'Enter executive support. Commercial until low. Think will senior explain.',
    'email': 'william79@example.net',
    'phone_number': '+1-955-418-6961',
    'json': {
    'name': 'Krista Thompson',
    'address': '78000 Walker Forks Apt. 424\nHudsonhaven, NM 30222',
},
    'key64131': 'value91773',
    'key16398': 'value27714',
    'key47231': 'value40312',
    'key75074': 'value51343',
    'key21751': 'value8312',
    'key87505': 'value39278',
},
    {
    'id': 17527490816881,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Madison Watson',
    'address': '8693 Dorsey Forge Suite 300\nWest Katelyn, CO 69289',
    'text': 'Suddenly section reason range deal around. Whether stop inside.\nDifference wide modern either right start. Process during those she. Against might candidate sound number skin be suddenly.',
    'email': 'tiffanypatterson@example.net',
    'phone_number': '+1-662-272-5492x9036',
    'json': {
    'name': 'Alexandria Tucker',
    'address': '9174 Andres Square\nPort Candace, VT 59296',
},
    'key50423': 'value54961',
    'key6926': 'value79498',
    'key77446': 'value4792',
    'key12528': 'value78537',
    'key71748': 'value1823',
    'key35008': 'value86159',
    'key39186': 'value82223',
    'key79185': 'value78539',
    'key98449': 'value68874',
},
    {
    'id': 17527490816893,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Jessica Bailey',
    'address': '6215 Kimberly Ranch\nSouth Nathan, IN 84770',
    'text': 'Entire door meeting miss result win. Give former tree box style campaign word.\nReady big trouble whatever billion economy loss. Picture sense suggest live difference use.',
    'email': 'melindaalexander@example.net',
    'phone_number': '549.648.1725',
    'json': {
    'name': 'Barbara Pace',
    'address': '08736 Elizabeth Greens Apt. 468\nEast Jamiemouth, RI 67212',
},
    'key40569': 'value80676',
    'key61994': 'value77363',
    'key91440': 'value80501',
},
    {
    'id': 17527490816905,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Tyler Leon',
    'address': 'PSC 5061, Box 2425\nAPO AA 85886',
    'text': 'Show writer how democratic pay plant hard former. Nearly best manager.\nGirl if three among personal. Man out such including.',
    'email': 'jonathan70@example.com',
    'phone_number': '(762)644-6126x825',
    'json': {
    'name': 'Leslie Durham',
    'address': '32175 Justin Forest Suite 821\nEast James, WA 04994',
},
    'key17057': 'value76474',
    'key83798': 'value86132',
    'key26657': 'value90945',
    'key93011': 'value80506',
    'key49622': 'value38224',
    'key49394': 'value90341',
    'key30644': 'value7986',
},
    {
    'id': 17527490816913,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Scott Lowe',
    'address': '509 Vance Mission\nSouth Christopher, LA 11912',
    'text': 'Power health everybody deal.\nCommon require to west account lay full good. Newspaper family stay speech eat on.',
    'email': 'jmckinney@example.com',
    'phone_number': '601.698.1043x38191',
    'json': {
    'name': 'Emily Wood',
    'address': '61596 Boyd Streets\nRodneyburgh, WI 16977',
},
    'key73786': 'value5082',
    'key17287': 'value76476',
    'key2950': 'value88126',
    'key42213': 'value11119',
    'key95505': 'value52545',
    'key35234': 'value17199',
    'key86172': 'value80098',
    'key92214': 'value49437',
    'key57581': 'value64963',
    'key10373': 'value51089',
},
    {
    'id': 17527490816924,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Amy Elliott',
    'address': '7761 Acosta Ridges Apt. 204\nEast Alexander, ND 55593',
    'text': 'Themselves final follow young order reality. School course that Mrs none.\nEither star all mean court claim. Drive specific style again every. Attention consider just billion.',
    'email': 'donna37@example.org',
    'phone_number': '001-508-586-9105x89820',
    'json': {
    'name': 'John Mann',
    'address': '1422 Little Extension\nWest Gabrielview, DC 08490',
},
    'key90505': 'value70345',
    'key64719': 'value63491',
    'key11365': 'value98681',
    'key875': 'value73721',
    'key66632': 'value89706',
    'key71305': 'value32236',
    'key68884': 'value74706',
},
    {
    'id': 17527490816935,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Shirley Phillips',
    'address': '8981 Mark Shores Suite 342\nBarbermouth, OK 86724',
    'text': 'Social hotel difficult of. About other suddenly street up thank. Need find few finally hour a option.\nHouse main fall often thank remember put there. Few factor game.',
    'email': 'andersongloria@example.org',
    'phone_number': '(429)989-9152x45326',
    'json': {
    'name': 'Kristi Greer',
    'address': '6009 Danielle Orchard Suite 739\nMartinmouth, OH 81746',
},
    'key66675': 'value26392',
    'key80409': 'value64779',
    'key35649': 'value92171',
    'key16335': 'value20619',
    'key77102': 'value53634',
    'key93958': 'value60064',
    'key25265': 'value76182',
    'key53280': 'value34095',
    'key58079': 'value27301',
},
    {
    'id': 17527490816948,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Richard Peterson',
    'address': '03345 Mejia Crossing Apt. 723\nPort Paulachester, OK 75351',
    'text': 'Wind window from. Part machine beautiful claim quality.\nProject vote finish turn.',
    'email': 'patricia72@example.org',
    'phone_number': '001-290-387-5912x05554',
    'json': {
    'name': 'William Cortez',
    'address': 'Unit 4572 Box 5158\nDPO AA 62296',
},
    'key67920': 'value66656',
    'key42380': 'value30405',
    'key36538': 'value36938',
    'key5895': 'value18061',
    'key30398': 'value84831',
    'key43623': 'value15263',
    'key31980': 'value31433',
},
    {
    'id': 17527490816957,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Bethany Wilkerson',
    'address': '0712 Montes Tunnel Suite 460\nPort Richardville, TN 20250',
    'text': 'Peace white clear authority certain customer party finally. Red return room.\nAlready happy success sort without similar. Doctor low picture.',
    'email': 'elizabethwashington@example.org',
    'phone_number': '808.361.8583x7814',
    'json': {
    'name': 'Jennifer Rodriguez',
    'address': '609 Edgar Glen Suite 194\nAnnside, NM 07505',
},
    'key96479': 'value9396',
    'key79164': 'value44213',
    'key69008': 'value15709',
    'key8336': 'value23019',
    'key63663': 'value79105',
},
    {
    'id': 17527490816969,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Ronnie Santana',
    'address': '1931 Timothy Plains Apt. 089\nLake Waynefurt, TX 67430',
    'text': 'Season result reason strategy it south. Doctor commercial pass hour travel agreement chair describe. Figure mean military sing growth speech body. Bill this half local market those mouth if.',
    'email': 'jeffrey90@example.net',
    'phone_number': '(762)699-0650',
    'json': {
    'name': 'Edward Fritz',
    'address': '31573 Edwards Cove\nJonathanstad, PW 70743',
},
    'key61122': 'value70134',
    'key21627': 'value65943',
    'key95178': 'value98560',
    'key37380': 'value53263',
    'key55594': 'value55105',
    'key25007': 'value63936',
    'key40993': 'value54690',
},
    {
    'id': 17527490816980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Robert Delacruz',
    'address': '79173 Samuel Forks Suite 819\nLake Ashleyland, RI 19748',
    'text': 'Term peace stage fine notice. Trip program nature parent add with world.\nThemselves none option move reason. Threat we necessary deal do.\nAnalysis who they. To order stop deal similar.',
    'email': 'jasminegarrett@example.net',
    'phone_number': '734-761-8846',
    'json': {
    'name': 'Stacy Davis',
    'address': '84472 Benton Walks\nNorth Charles, PR 02790',
},
    'key90303': 'value66736',
    'key27807': 'value47120',
    'key44796': 'value16154',
},
    {
    'id': 17527490816992,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Jacob Barry',
    'address': '8377 Peterson Village\nWest Heather, WA 94180',
    'text': 'Ask task bag. Claim wait loss hour. Spring wait front true suddenly information article.\nLoss since each size nearly player.\nSpring military consumer rich policy. Us keep by day.',
    'email': 'brooke53@example.net',
    'phone_number': '929-205-4310x951',
    'json': {
    'name': 'Mark Barker',
    'address': '62341 Nichols Glens\nAmandaview, CO 67243',
},
    'key72198': 'value12609',
    'key28428': 'value1546',
},
    {
    'id': 17527490817004,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Elizabeth Evans',
    'address': '444 Delacruz Mall Apt. 656\nMartinport, PW 84456',
    'text': 'Able space second suggest animal thousand often. List idea fund fly later writer.',
    'email': 'katherinebaldwin@example.net',
    'phone_number': '001-210-282-5413',
    'json': {
    'name': 'Regina Martin',
    'address': '20312 Rogers Islands\nStantonmouth, CT 03225',
},
    'key28256': 'value12833',
    'key99485': 'value87479',
    'key41204': 'value99123',
    'key40896': 'value88632',
    'key26988': 'value94623',
    'key79430': 'value97063',
},
    {
    'id': 17527490817016,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Daniel Fritz',
    'address': '0462 Thompson Course\nMitchellberg, DE 52876',
    'text': 'Manager operation study enter give together. Goal quality wrong ahead. Although produce war upon term lay available ahead. Girl key participant lot interesting herself bring.',
    'email': 'delgadosteven@example.net',
    'phone_number': '658-766-1387',
    'json': {
    'name': 'Tasha Holmes',
    'address': '3931 Jackson Key Apt. 663\nGonzalezbury, NH 00883',
},
    'key22216': 'value97970',
    'key24107': 'value53116',
    'key16049': 'value20893',
    'key1267': 'value63975',
    'key484': 'value49040',
    'key89295': 'value31644',
    'key16089': 'value33897',
},
    {
    'id': 17527490817029,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Brett Gutierrez',
    'address': '141 Kelley Village\nBethchester, SC 24609',
    'text': 'Until already could. Road close position million prepare people simply. Last wife someone foreign by.\nMain size serious western. Ball want still alone let by some lay.',
    'email': 'ehunt@example.com',
    'phone_number': '2465206916',
    'json': {
    'name': 'Thomas Atkins',
    'address': '990 Roy Shores\nLake Kirkland, MS 37380',
},
    'key40559': 'value24632',
    'key19868': 'value58126',
    'key77621': 'value19194',
    'key28628': 'value41085',
    'key49464': 'value40539',
    'key31711': 'value50660',
    'key5676': 'value2508',
    'key44517': 'value83893',
    'key81707': 'value64892',
},
    {
    'id': 17527490817039,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Tammy Goodwin DDS',
    'address': 'Unit 1324 Box 7874\nDPO AA 23008',
    'text': 'Establish do television institution kitchen PM former movement. Official own save whatever above clearly. Nature almost right institution available she.',
    'email': 'redwards@example.com',
    'phone_number': '001-780-243-8680x07782',
    'json': {
    'name': 'Joyce Howard',
    'address': '0317 Miller Trail\nLake Wendyton, PW 95489',
},
    'key99243': 'value18344',
    'key87198': 'value83780',
    'key6459': 'value90739',
    'key69119': 'value46806',
    'key49679': 'value72676',
    'key34639': 'value82986',
    'key45843': 'value66944',
},
    {
    'id': 17527490817048,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Bryan Barnes',
    'address': '75535 Brandon Spring\nJonathanberg, MP 69111',
    'text': 'Its coach difficult reach responsibility. Speak study physical participant instead somebody source. Business source serve be also number include.',
    'email': 'daniel89@example.net',
    'phone_number': '001-256-739-4201',
    'json': {
    'name': 'Courtney Russell',
    'address': '20685 Montoya Freeway Suite 802\nEast Hollyside, ID 95466',
},
    'key98501': 'value85807',
    'key22793': 'value87654',
    'key7659': 'value44371',
    'key90353': 'value1659',
},
    {
    'id': 17527490817058,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Stephanie Allen',
    'address': 'USNV Sanchez\nFPO AE 46275',
    'text': 'View type blood kitchen drop business middle. Baby relationship sit by. Sea treatment week.\nStation position customer. Seven three real main small just. Behavior something help among result pretty.',
    'email': 'raymond01@example.org',
    'phone_number': '(763)348-4214x82715',
    'json': {
    'name': 'Timothy Murphy',
    'address': '6078 James Plains\nRobinsonfurt, MI 16617',
},
    'key81982': 'value19814',
    'key87339': 'value59222',
    'key60258': 'value95054',
    'key70595': 'value44804',
    'key5266': 'value56446',
},
    {
    'id': 17527490817068,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Kevin Meyers',
    'address': '97905 Martin Light Suite 000\nSouth Daisystad, AK 65437',
    'text': 'Crime ok think lawyer. Writer second around authority tough.',
    'email': 'agutierrez@example.com',
    'phone_number': '522.296.4340',
    'json': {
    'name': 'Kathryn Lee',
    'address': 'USCGC Smith\nFPO AE 88018',
},
    'key25074': 'value51182',
    'key65785': 'value15616',
    'key5496': 'value21778',
},
    {
    'id': 17527490817077,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Robert Walker',
    'address': '383 Perry Views Apt. 491\nEast Angela, KY 59674',
    'text': 'Rate word necessary face garden heart no. Professional family example could girl value.\nGovernment institution past cold dog. Action factor recognize final few both find.',
    'email': 'matthew34@example.org',
    'phone_number': '692.447.2437x0329',
    'json': {
    'name': 'Molly Bird',
    'address': 'PSC 4299, Box 9440\nAPO AA 89610',
},
    'key34558': 'value82685',
},
    {
    'id': 17527490817086,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Paul Ramirez',
    'address': '1348 Holloway Drive Suite 398\nJennifertown, AL 02704',
    'text': 'Recently may figure low. Picture court major song former else project. Shake appear million movement position both first remember.',
    'email': 'aliciamendoza@example.com',
    'phone_number': '(934)240-3701',
    'json': {
    'name': 'Matthew Miller',
    'address': '5257 John Hollow\nRichardview, WY 60038',
},
    'key27413': 'value80648',
},
    {
    'id': 17527490817097,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Beverly Mcguire',
    'address': 'USS King\nFPO AA 30412',
    'text': 'Knowledge majority why their.\nHis hand executive center medical anything quite direction. Goal south commercial probably recent drug food.',
    'email': 'briannapatterson@example.org',
    'phone_number': '001-518-205-4146',
    'json': {
    'name': 'Jennifer Herrera',
    'address': 'PSC 5123, Box 9983\nAPO AP 79690',
},
    'key98821': 'value59779',
},
    {
    'id': 17527490817105,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jennifer Dixon',
    'address': '00758 Alexis Pass Apt. 845\nStephanieview, RI 23922',
    'text': 'Treat amount make. Scene my hear group better continue.\nFind describe nice. Bar hold weight site debate cost spring. Us even about land.',
    'email': 'wwilliamson@example.org',
    'phone_number': '(307)932-0516x1014',
    'json': {
    'name': 'Sandra Fletcher',
    'address': '01685 Mercado Shoal\nWalkerbury, IN 64379',
},
    'key77560': 'value28863',
    'key84046': 'value59147',
    'key92679': 'value41497',
    'key62691': 'value84523',
    'key30004': 'value16202',
    'key18588': 'value84843',
    'key18079': 'value41462',
    'key14585': 'value7626',
    'key14134': 'value27120',
    'key50763': 'value13229',
},
    {
    'id': 17527490817116,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Gloria West',
    'address': '9477 Robert Corner Apt. 064\nNorth Susan, NE 13436',
    'text': 'Staff nation mouth huge us draw general. Maybe both century thing peace act. Himself save make half small.\nDrug whose light first major. It decade order share commercial.',
    'email': 'katrina68@example.com',
    'phone_number': '269-581-0675x934',
    'json': {
    'name': 'Vanessa Shaffer',
    'address': '0455 Stephanie Harbors\nWoodsville, AL 07651',
},
    'key16308': 'value84227',
    'key58530': 'value5220',
},
    {
    'id': 17527490817126,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Heather Lee MD',
    'address': 'Unit 8917 Box 5087\nDPO AA 96390',
    'text': 'Former wish cup choose. Cause least dark outside community sure point. Network style painting data involve.',
    'email': 'smithemily@example.net',
    'phone_number': '(354)263-5375x3855',
    'json': {
    'name': 'Sylvia Rosales',
    'address': '20547 Nathaniel Roads\nPort Kathy, PW 50652',
},
    'key79166': 'value54690',
    'key98555': 'value62820',
    'key77261': 'value79201',
    'key78908': 'value91624',
    'key85520': 'value3115',
    'key44225': 'value44732',
    'key40287': 'value99829',
    'key15407': 'value83433',
},
    {
    'id': 17527490817136,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Melinda Holland',
    'address': '5850 Carpenter Dam\nAmyville, RI 93303',
    'text': 'Billion hair magazine well employee wear. The turn generation get.',
    'email': 'kalvarado@example.net',
    'phone_number': '001-472-423-0449x5217',
    'json': {
    'name': 'Jeremy Davis',
    'address': '697 Jordan Ports Apt. 875\nChristophermouth, TN 97562',
},
    'key22792': 'value19602',
    'key68548': 'value18442',
    'key63994': 'value89905',
    'key5065': 'value31316',
    'key81565': 'value62179',
    'key24332': 'value38242',
    'key60953': 'value57402',
    'key69206': 'value52513',
},
    {
    'id': 17527490817146,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Jordan Green',
    'address': '496 Brady Isle\nMichaelmouth, OK 25375',
    'text': 'My audience outside finally door. Quality letter employee perhaps. Everybody end federal environment.',
    'email': 'victoria22@example.net',
    'phone_number': '+1-697-773-8426x181',
    'json': {
    'name': 'Isaac Mclean',
    'address': '64268 Sarah Terrace\nNorth Patrickside, LA 62709',
},
    'key71391': 'value38124',
    'key12776': 'value16282',
    'key74584': 'value77163',
    'key57948': 'value85670',
    'key9801': 'value99072',
    'key23700': 'value70433',
},
    {
    'id': 17527490817157,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Ashley Smith',
    'address': '269 Joshua Key\nDavidtown, UT 07731',
    'text': 'Fight actually suddenly only. Experience participant boy lay not close brother Mr.\nBig tend seven support kid let stop. Fall school sound sound leave move state nearly.',
    'email': 'knappshannon@example.org',
    'phone_number': '226.802.2675',
    'json': {
    'name': 'Joseph Fletcher',
    'address': '15625 Daniel Garden\nRuizmouth, ND 68420',
},
    'key81676': 'value87476',
},
    {
    'id': 17527490817167,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Katherine Lee',
    'address': '47922 Angela Street Apt. 717\nBrowntown, ME 33732',
    'text': 'Few study man officer friend can issue. Upon growth represent effect marriage team assume. Candidate page forget force work.',
    'email': 'johnsonmark@example.com',
    'phone_number': '(700)432-6284x8102',
    'json': {
    'name': 'Tricia Ayers',
    'address': '0237 Barron Neck Suite 700\nNorth Susan, HI 59991',
},
    'key76355': 'value43211',
    'key43220': 'value23717',
    'key7224': 'value39052',
},
    {
    'id': 17527490817179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Christina Archer',
    'address': '334 Parrish Springs\nLake Sonyamouth, RI 83016',
    'text': 'Born western agency trip property. Sit while morning out. Yet writer choose lose hotel.\nKey pressure measure wear allow charge. Seek team light door.',
    'email': 'calderonthomas@example.com',
    'phone_number': '(688)947-1042',
    'json': {
    'name': 'Andrea Travis',
    'address': '93062 Castillo Corners\nNew Brendanside, SD 88825',
},
    'key93515': 'value4140',
    'key24628': 'value42520',
    'key8101': 'value98716',
    'key43674': 'value18048',
    'key19790': 'value27763',
    'key18223': 'value59182',
    'key85665': 'value84420',
},
    {
    'id': 17527490817191,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Rebecca Stone',
    'address': '635 Vance Road\nLake Williamport, KY 48679',
    'text': 'Across up four respond.\nFocus language defense continue eat. And student field crime sort feel guess.',
    'email': 'esheppard@example.net',
    'phone_number': '863.596.4142',
    'json': {
    'name': 'Heidi Hooper',
    'address': '100 Joshua Bridge Apt. 773\nAlvarezbury, PR 43515',
},
    'key45924': 'value32354',
    'key86339': 'value60449',
    'key42634': 'value8517',
    'key67769': 'value40355',
},
    {
    'id': 17527490817202,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Amber Vasquez',
    'address': '725 David Mission\nJonesmouth, MO 31567',
    'text': 'Federal especially space smile.\nRaise identify make every play late democratic. Song reduce sell name ahead. Need me everybody free move up sometimes.',
    'email': 'unichols@example.org',
    'phone_number': '674-269-7328',
    'json': {
    'name': 'Kelsey Fritz',
    'address': '667 Cassandra Prairie\nLake Matthew, PR 98045',
},
    'key57014': 'value45083',
    'key2042': 'value63737',
    'key87409': 'value27132',
    'key35862': 'value59669',
    'key77088': 'value17002',
    'key49265': 'value73179',
},
    {
    'id': 17527490817213,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Nicholas Kelly',
    'address': '68680 Crane Park\nSouth William, WA 06500',
    'text': 'In make page impact. Bank art throughout quite stop.\nPressure type reality condition. Throughout region week factor nothing happy coach. Democratic hand dark hard great sort true.',
    'email': 'brittany86@example.org',
    'phone_number': '276-468-1981',
    'json': {
    'name': 'Jonathan Baldwin',
    'address': 'PSC 5241, Box 9737\nAPO AP 77706',
},
    'key77005': 'value28973',
    'key53933': 'value99784',
    'key97314': 'value32284',
    'key16028': 'value58152',
},
    {
    'id': 17527490817221,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Mark Perry Jr.',
    'address': '76480 Juan Estate Apt. 863\nSmithview, CA 47079',
    'text': 'Race authority upon traditional spring effort. Base open cultural early. Husband better expert Congress.',
    'email': 'uerickson@example.net',
    'phone_number': '+1-728-901-3788x74924',
    'json': {
    'name': 'Evelyn Clark',
    'address': '22667 Figueroa Branch\nNew Amy, LA 88885',
},
    'key47544': 'value11885',
    'key71487': 'value1372',
    'key38928': 'value9783',
    'key96958': 'value8268',
},
    {
    'id': 17527490817232,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Eric Edwards',
    'address': '2690 Schneider Harbors Apt. 739\nMargaretville, AR 66028',
    'text': 'History draw kind five report blue join drive. Have speech parent would see sit event number.\nSerious issue type despite well include. Big organization before rather important mention.',
    'email': 'kevin98@example.org',
    'phone_number': '2042474544',
    'json': {
    'name': 'Lynn Matthews',
    'address': '0598 Rodriguez Tunnel\nEast Michelleview, AL 14486',
},
    'key94282': 'value31093',
    'key77992': 'value36685',
},
    {
    'id': 17527490817243,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Anthony Mccoy',
    'address': '0038 Gray Meadows\nLucasview, LA 45544',
    'text': 'Want physical writer few scientist that represent would. Expect kitchen rich include hold check must old. Some century away relate simple beyond rich. Board necessary maintain official oil.',
    'email': 'walkercharlene@example.com',
    'phone_number': '326.640.6453',
    'json': {
    'name': 'Yvonne Pratt',
    'address': '3600 Michelle Rue Suite 157\nWest Trevor, PR 25409',
},
    'key89211': 'value94698',
    'key72114': 'value25191',
    'key12865': 'value5036',
    'key86824': 'value22959',
},
    {
    'id': 17527490817255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Carla Hughes',
    'address': '9090 Wolf Row\nNorth Kristenbury, OR 29978',
    'text': 'Down budget wife degree build avoid. Man listen mention black child. Growth serve than use.\nPainting have range mother baby. Ok strategy short local new maybe pull.',
    'email': 'harrisfrank@example.org',
    'phone_number': '427.848.2023x751',
    'json': {
    'name': 'Megan Myers',
    'address': '169 Shannon Village\nEvanport, GU 84736',
},
    'key21156': 'value12584',
},
    {
    'id': 17527490817267,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Michael Elliott',
    'address': '37577 Kelly Road\nNew Patrick, NH 93574',
    'text': 'Reflect building control across message. Senior figure million man provide. Summer about nation.\nHistory left single nearly. Water research organization street. Goal organization pay face food.',
    'email': 'joshua92@example.org',
    'phone_number': '531-421-0001x1497',
    'json': {
    'name': 'Michelle Hernandez',
    'address': '3769 Dyer Key Apt. 907\nEast Lauren, TN 65757',
},
    'key39319': 'value86136',
    'key80295': 'value95412',
},
    {
    'id': 17527490817278,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Brian Velazquez',
    'address': '3841 Cheryl Causeway\nBateschester, IA 12393',
    'text': 'Toward food rise mention. Rock skin easy. Light drop lawyer message card almost.',
    'email': 'owest@example.com',
    'phone_number': '(256)913-6726',
    'json': {
    'name': 'Kevin Bowen',
    'address': '8853 Long Lodge\nSmithside, TX 55749',
},
    'key68651': 'value88257',
    'key154': 'value15424',
    'key62405': 'value31344',
    'key1164': 'value70862',
    'key31458': 'value515',
    'key46820': 'value97221',
    'key67296': 'value83699',
},
    {
    'id': 17527490817290,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Walter Morrison',
    'address': '5254 Patricia Loaf\nWaltersburgh, TX 89262',
    'text': 'Modern force pass cultural someone nature weight. Official economy a someone surface letter of. Rise page vote wife face daughter.',
    'email': 'danielle92@example.net',
    'phone_number': '805.522.6952',
    'json': {
    'name': 'Jacob Nixon',
    'address': '273 Samantha Meadows\nJimenezbury, SD 54791',
},
    'key16026': 'value82194',
    'key73069': 'value70908',
    'key60782': 'value42760',
    'key68627': 'value22588',
    'key47229': 'value87893',
    'key71195': 'value44358',
    'key25422': 'value17232',
    'key64591': 'value56497',
},
    {
    'id': 17527490817300,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Joshua Rodriguez',
    'address': 'USNV Alvarez\nFPO AA 38735',
    'text': 'With century eight lot almost share. Interesting water represent east life issue rate.\nRepresent week make quite majority strategy. Model second almost deal.',
    'email': 'fowlerkristin@example.org',
    'phone_number': '+1-364-993-3103x637',
    'json': {
    'name': 'James Wallace',
    'address': '615 Richard Motorway Apt. 291\nJohnsonland, AZ 21016',
},
    'key70788': 'value11665',
    'key97947': 'value80420',
},
    {
    'id': 17527490817311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Kimberly Morris',
    'address': '8138 Donna Street Suite 362\nGordonberg, TN 37413',
    'text': 'Tonight by question season. Letter explain certain standard trial me. Serious exist money personal itself suggest so factor. Performance these turn close here find Republican.',
    'email': 'allisonfisher@example.com',
    'phone_number': '(765)628-7912',
    'json': {
    'name': 'Matthew Vasquez',
    'address': '37088 Jeffery Lake\nAnthonychester, VI 72512',
},
    'key5375': 'value69512',
    'key54493': 'value29111',
    'key35865': 'value25504',
    'key2708': 'value68590',
},
    {
    'id': 17527490817322,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Scott Sandoval',
    'address': '72453 Elijah Lake\nWest Jesusside, GA 32598',
    'text': 'Bar style true interview guy role season TV. Include and instead sport.\nBudget environmental west near. Street beyond ago fight. Certain say sea.',
    'email': 'simpsonjason@example.com',
    'phone_number': '+1-381-672-4663x354',
    'json': {
    'name': 'Pamela Gonzalez',
    'address': '282 David Court Apt. 226\nNorth Joshuaborough, PA 48797',
},
    'key52312': 'value42544',
    'key25163': 'value20674',
},
    {
    'id': 17527490817333,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Susan Molina',
    'address': '92491 Tyler Junction Suite 659\nJaneberg, WY 18103',
    'text': 'Worry see treat. Direction actually note ready deal. Least staff close care with material fire.\nWish very night. Any five born population who kind.',
    'email': 'xmiller@example.net',
    'phone_number': '+1-996-295-7313x44463',
    'json': {
    'name': 'Mark Smith',
    'address': '615 Andrew Trail\nLittleland, AL 80966',
},
    'key91308': 'value13172',
    'key33148': 'value66466',
    'key89631': 'value20235',
    'key61189': 'value36737',
    'key78230': 'value55220',
    'key68698': 'value89703',
    'key16828': 'value47132',
    'key45961': 'value95849',
    'key21997': 'value83336',
    'key93594': 'value66350',
},
    {
    'id': 17527490817344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Katie Howell',
    'address': '3184 William Village Suite 227\nTimothyside, NV 16210',
    'text': 'Official born painting friend miss history here. After either western.',
    'email': 'odonnellrichard@example.com',
    'phone_number': '+1-625-879-3400x998',
    'json': {
    'name': 'Jeremy George',
    'address': '086 Austin View Suite 588\nEast Steven, GU 66561',
},
    'key6553': 'value22632',
    'key34684': 'value25399',
},
    {
    'id': 17527490817355,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Cynthia Wu',
    'address': '032 Moore Tunnel Suite 526\nEast Rachelside, ME 82902',
    'text': 'Treat chair occur subject life hand response. Week own woman.\nLanguage could create officer stay that. Point stage well brother ready.',
    'email': 'qstewart@example.com',
    'phone_number': '(242)734-5731',
    'json': {
    'name': 'Jesus Tyler',
    'address': '662 Kim Road Apt. 007\nJacksonview, GA 54441',
},
    'key59787': 'value34995',
    'key52747': 'value65202',
},
    {
    'id': 17527490817367,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Nicholas Cohen',
    'address': '00077 Sandra Roads\nSouth Andrewfort, SC 66394',
    'text': 'Like rich within down international set computer. Degree open since fast.',
    'email': 'rollinspaul@example.org',
    'phone_number': '387-611-2608',
    'json': {
    'name': 'Chad Kramer',
    'address': '006 Ann Prairie\nNew Gilbertmouth, NH 52050',
},
    'key72029': 'value55099',
    'key79905': 'value4391',
    'key40692': 'value87183',
},
    {
    'id': 17527490817377,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Ricky Garrison',
    'address': '07159 Tapia Street\nPort Nicole, NE 99449',
    'text': 'Suddenly life pattern. Describe necessary four different white city. Card stuff box painting yes act.\nResponse author culture unit bit area. Candidate dream anything major require.',
    'email': 'laurenthompson@example.com',
    'phone_number': '+1-527-619-3317',
    'json': {
    'name': 'Jonathan Diaz',
    'address': '390 Ross Squares Apt. 012\nSouth Randy, MD 42820',
},
    'key46862': 'value31790',
    'key59037': 'value16603',
    'key17182': 'value46026',
    'key15112': 'value50164',
    'key52973': 'value20619',
},
    {
    'id': 17527490817389,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Christine Nguyen',
    'address': '4953 Douglas Path\nWest William, GA 42175',
    'text': 'Large Mrs fall rather keep want. Cover later entire. History avoid environment clear technology behavior.\nStrong plan adult. While financial game third. Western eat poor nothing general produce art.',
    'email': 'victoria16@example.com',
    'phone_number': '600-255-0227',
    'json': {
    'name': 'Abigail Garza',
    'address': '39463 Bird Way Apt. 861\nWest Joel, MI 19898',
},
    'key57906': 'value89484',
    'key82850': 'value44954',
},
    {
    'id': 17527490817399,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Kristen Hamilton',
    'address': '48530 Matthew Spring\nNorth Jennifer, WI 57080',
    'text': 'Edge guy successful firm difference night month language. Nor artist tend water movement citizen. Since movement light three.\nHouse bag relationship rest about their upon. Between down feel mother.',
    'email': 'zmorris@example.com',
    'phone_number': '4794543373',
    'json': {
    'name': 'Margaret Anderson',
    'address': '74649 Margaret Bridge Suite 808\nWoodsborough, NM 42774',
},
    'key4730': 'value39808',
    'key69262': 'value28726',
    'key96526': 'value70049',
    'key92173': 'value93940',
    'key31313': 'value32921',
    'key73511': 'value19843',
    'key685': 'value24685',
    'key50518': 'value71578',
},
    {
    'id': 17527490817410,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Jamie Hamilton',
    'address': '597 Burgess Mountains\nAnthonystad, MI 77899',
    'text': 'Good task everything. Do kitchen low strategy heavy thing chair. Project center race information.',
    'email': 'bullockpatrick@example.org',
    'phone_number': '(606)414-2751x1068',
    'json': {
    'name': 'Kyle Barrera',
    'address': 'Unit 4917 Box 6076\nDPO AA 87893',
},
    'key16687': 'value65409',
    'key40605': 'value89040',
    'key56357': 'value71280',
    'key72812': 'value8622',
    'key81705': 'value78084',
    'key29751': 'value5014',
    'key84340': 'value11627',
    'key18484': 'value4589',
    'key74552': 'value65645',
},
    {
    'id': 17527490817419,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Jimmy Johnson',
    'address': '37398 Robert Lodge\nWest Marissashire, AL 50461',
    'text': 'Service clearly security unit like try on go. Near chair move concern.',
    'email': 'dwilkerson@example.org',
    'phone_number': '624.808.6255x2704',
    'json': {
    'name': 'Miranda Patterson',
    'address': 'Unit 8092 Box 5008\nDPO AP 90717',
},
    'key39828': 'value80964',
    'key21192': 'value36702',
    'key5372': 'value12986',
    'key65702': 'value20745',
},
    {
    'id': 17527490817428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Julia Henderson',
    'address': '87167 Kathryn Keys\nPort Gregoryfurt, NY 34860',
    'text': 'Method tell marriage meet loss explain. Outside this go owner part free enjoy. Everybody four current choice few wish such college.',
    'email': 'seanharper@example.com',
    'phone_number': '(484)549-6947',
    'json': {
    'name': 'Sydney Pham',
    'address': '72711 Beard Port Apt. 491\nHayleyfurt, MH 79898',
},
    'key43521': 'value39465',
    'key61152': 'value82369',
    'key77977': 'value94296',
    'key5142': 'value32729',
    'key53525': 'value98420',
    'key32517': 'value4715',
},
    {
    'id': 17527490817438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Derek Dawson',
    'address': 'USCGC Allen\nFPO AE 88747',
    'text': 'Purpose way charge both else nearly. Open guess police. End voice blood become agent. Drop foot mission trip none country.\nInstitution girl task morning save community. News computer quickly bad.',
    'email': 'charlesjackson@example.com',
    'phone_number': '773-425-9019x514',
    'json': {
    'name': 'Pamela Martinez',
    'address': '5577 Julie Drives\nPort Daniel, MH 35336',
},
    'key66997': 'value58050',
    'key22601': 'value26432',
    'key35595': 'value48012',
    'key452': 'value38473',
    'key49829': 'value12781',
    'key27179': 'value43113',
},
    {
    'id': 17527490817448,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Cynthia Bryant',
    'address': '45773 Johnson Stream Apt. 498\nLake Michael, NJ 36074',
    'text': 'Forget particularly model any language rest pay. White future television he.\nNearly know parent also.',
    'email': 'richardsdawn@example.com',
    'phone_number': '9082580120',
    'json': {
    'name': 'Barbara Smith',
    'address': '3142 Coleman Burg Apt. 099\nDesireemouth, NH 04269',
},
    'key17420': 'value76934',
    'key72266': 'value35874',
    'key68513': 'value66493',
    'key19308': 'value55721',
    'key96792': 'value20521',
    'key49451': 'value37640',
},
    {
    'id': 17527490817459,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Michael Montgomery',
    'address': '98203 Cindy Groves\nEast Richardmouth, WI 74053',
    'text': 'Project sea production election protect clearly know. Young necessary challenge mouth. Bring our politics among paper list.',
    'email': 'vreynolds@example.org',
    'phone_number': '+1-704-907-7138',
    'json': {
    'name': 'Chase Farley',
    'address': '564 Collins Stream\nJustinhaven, VA 37385',
},
    'key42319': 'value87445',
    'key58601': 'value4555',
    'key80660': 'value183',
},
    {
    'id': 17527490817469,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Janice Thomas',
    'address': '3728 Rogers Prairie\nNew Feliciachester, NV 74774',
    'text': 'Food right half. Say laugh process people expect various treat. Mention image agreement knowledge stay result determine.\nOwn result shoulder. Campaign a within quality red decision.',
    'email': 'gpatterson@example.org',
    'phone_number': '952.977.1377',
    'json': {
    'name': 'Jeremy Underwood',
    'address': '19640 Timothy Crescent Suite 594\nDeckerside, UT 02535',
},
    'key4757': 'value7110',
    'key81492': 'value8547',
},
    {
    'id': 17527490817480,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Dustin Ross',
    'address': '72796 Moran Run Apt. 330\nEast Veronica, NC 70942',
    'text': 'Share position resource book result while.\nDraw two even class probably single. Admit decade factor third order on interest professional.',
    'email': 'mferguson@example.com',
    'phone_number': '(686)280-6081',
    'json': {
    'name': 'Jeremy Scott',
    'address': '5224 Jamie Parks Apt. 460\nMejiaside, KS 60208',
},
    'key18447': 'value55727',
},
    {
    'id': 17527490817491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Brian Robertson',
    'address': '46554 Mckenzie Branch\nPort Marcusborough, OH 68979',
    'text': 'Front provide hot effect none return field. Design then area senior usually. Mrs I fact like agreement life system.',
    'email': 'swright@example.com',
    'phone_number': '001-959-348-4343x57110',
    'json': {
    'name': 'Brian Smith',
    'address': '2412 Crystal Cove\nBarbarastad, MS 01651',
},
    'key85017': 'value93907',
    'key16442': 'value72783',
    'key37285': 'value34618',
    'key82579': 'value40499',
    'key51488': 'value83677',
    'key56960': 'value90500',
    'key64671': 'value87492',
    'key83724': 'value55368',
},
    {
    'id': 17527490817501,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Stephanie Deleon',
    'address': '82512 Watson Springs Apt. 119\nNorth Raymondborough, NE 75469',
    'text': 'Popular serve century week form. Budget she radio audience reality until. Specific side development modern identify.\nTrue a citizen send which difficult. Light science data they.',
    'email': 'rosslindsay@example.com',
    'phone_number': '202.809.7994x6838',
    'json': {
    'name': 'Brian Owen',
    'address': '470 William Lakes Suite 697\nHarrismouth, AZ 13586',
},
    'key58295': 'value61413',
    'key29294': 'value49961',
    'key75797': 'value32222',
    'key38859': 'value99821',
    'key20824': 'value14869',
    'key75758': 'value89287',
    'key45410': 'value19788',
    'key34385': 'value62790',
    'key19559': 'value83078',
},
    {
    'id': 17527490817513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Lorraine Norman',
    'address': '593 Davis Station\nAntoniohaven, GA 18486',
    'text': 'International evidence eight subject may respond. Sit challenge raise many side writer.\nSister page necessary avoid much none. Really check yeah how chance.',
    'email': 'wkrause@example.com',
    'phone_number': '703.600.2221x0004',
    'json': {
    'name': 'Frank Smith',
    'address': '76113 Brian Park Suite 283\nLoriport, FM 61084',
},
    'key87981': 'value29287',
    'key68630': 'value97631',
},
    {
    'id': 17527490817524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Marisa Barnes',
    'address': 'Unit 5764 Box 3941\nDPO AP 37840',
    'text': 'Country effect keep born or unit. Beautiful set career result lot pressure. Particularly address language democratic population side score.',
    'email': 'breannayang@example.net',
    'phone_number': '544.807.6592',
    'json': {
    'name': 'James Reynolds',
    'address': 'USCGC Obrien\nFPO AA 30849',
},
    'key33492': 'value51578',
    'key86096': 'value45450',
    'key84780': 'value34173',
    'key12700': 'value36931',
    'key12670': 'value65800',
    'key55681': 'value95620',
    'key87136': 'value7463',
},
    {
    'id': 17527490817532,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Erica Richards',
    'address': '29799 Sophia Burgs\nEast Aliciachester, PA 95874',
    'text': 'Include general college become really. Behind medical general stage.\nFear scientist church interesting. Impact from us.\nEconomy major evidence argue. Truth western through stock concern next.',
    'email': 'nicole44@example.org',
    'phone_number': '937.939.1600x099',
    'json': {
    'name': 'Timothy Porter MD',
    'address': 'Unit 6497 Box 2621\nDPO AP 83100',
},
    'key67966': 'value2733',
},
    {
    'id': 17527490817541,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Thomas Vaughn',
    'address': '467 Grace Way\nSharonmouth, CT 74705',
    'text': 'Suddenly inside material debate. Race reality policy PM doctor degree use. Each be information responsibility animal woman west.',
    'email': 'francismoody@example.net',
    'phone_number': '+1-473-370-5123x43872',
    'json': {
    'name': 'Donna Walker',
    'address': 'USS Wilson\nFPO AE 54518',
},
    'key65858': 'value42172',
    'key29178': 'value63296',
    'key98614': 'value67743',
    'key28417': 'value90198',
    'key41163': 'value38028',
    'key19061': 'value55846',
    'key76656': 'value4064',
},
    {
    'id': 17527490817550,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Paul White',
    'address': 'Unit 5128 Box 7307\nDPO AP 10284',
    'text': 'Plant they participant wonder meet. Growth could analysis next. Believe good the model listen base anyone.\nStudent word between fine officer customer assume drop. Not series TV apply.',
    'email': 'taylormary@example.com',
    'phone_number': '+1-522-914-3366x1158',
    'json': {
    'name': 'Anna Diaz DVM',
    'address': '1032 Sharp Plains\nSanchezside, SD 46261',
},
    'key62746': 'value86104',
    'key98966': 'value23438',
    'key25491': 'value64905',
    'key97186': 'value84755',
    'key26516': 'value80231',
    'key52066': 'value73058',
},
    {
    'id': 17527490817560,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Peter Walters',
    'address': '80385 Victoria Stravenue Apt. 619\nEast Mary, NJ 05054',
    'text': 'Lawyer benefit force customer real sea since Mr.\nHear fall before four several this yeah. Article process citizen anything along.',
    'email': 'teresaburns@example.com',
    'phone_number': '(634)556-3252',
    'json': {
    'name': 'Luis Moore',
    'address': 'USCGC Lucas\nFPO AA 26489',
},
    'key15726': 'value49769',
    'key87794': 'value51255',
    'key63816': 'value60328',
    'key41856': 'value97983',
    'key33449': 'value58671',
    'key9173': 'value12033',
    'key73424': 'value81407',
    'key95396': 'value33713',
    'key89573': 'value19126',
    'key8168': 'value34932',
},
    {
    'id': 17527490817570,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Jessica George',
    'address': '6329 Pamela Union\nFrancisport, NE 73003',
    'text': 'Respond check stop southern. Economy would room record character blood follow school. Significant claim enjoy grow whom collection.',
    'email': 'ayalarodney@example.org',
    'phone_number': '(453)457-6228',
    'json': {
    'name': 'Cameron Lloyd',
    'address': '69866 Darren Port Suite 564\nRobertfurt, FL 85675',
},
    'key1012': 'value9538',
    'key80805': 'value51621',
    'key74936': 'value38132',
    'key39037': 'value24259',
    'key85379': 'value91871',
    'key87220': 'value95730',
    'key61283': 'value36394',
    'key41': 'value78947',
},
    {
    'id': 17527490817582,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Melissa Salinas',
    'address': 'USCGC Kirk\nFPO AA 32438',
    'text': 'Consider option scene than region whatever wish sure. Relate military catch class. Behind consider watch detail goal candidate character former.',
    'email': 'duane40@example.org',
    'phone_number': '837-276-5863',
    'json': {
    'name': 'Anthony Garcia',
    'address': '59677 Oneal Plains\nPort Philipberg, GU 83613',
},
    'key65695': 'value38029',
    'key74323': 'value4070',
},
    {
    'id': 17527490817591,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'Brian Charles',
    'address': '6626 Arnold Views Apt. 167\nLake David, MP 40612',
    'text': 'Toward follow girl operation somebody fish call.\nMission again night year enjoy theory. Civil someone shoulder responsibility ask military decide as.',
    'email': 'ifranklin@example.com',
    'phone_number': '001-591-868-2326x2779',
    'json': {
    'name': 'Michael Lawrence',
    'address': '42917 Smith Walk Suite 126\nKellyview, WV 64663',
},
    'key26907': 'value78844',
    'key46501': 'value62796',
    'key6866': 'value23270',
    'key20098': 'value59880',
    'key83793': 'value94439',
    'key84880': 'value66329',
    'key52351': 'value38287',
    'key96082': 'value28897',
    'key92117': 'value951',
    'key57759': 'value14254',
},
    {
    'id': 17527490817602,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Christina Quinn',
    'address': 'Unit 3622 Box 9740\nDPO AE 03283',
    'text': 'Office consumer few director light skin wait TV. Sign room want need.\nInstitution understand usually need six. Since wear run card. Probably only food.',
    'email': 'andrewsandoval@example.org',
    'phone_number': '446.547.2402x3383',
    'json': {
    'name': 'Lisa Russell',
    'address': '135 Sanders Glen\nHarrisview, NH 46909',
},
    'key98233': 'value77647',
    'key56941': 'value71012',
    'key52850': 'value48991',
    'key63894': 'value7022',
    'key45108': 'value91915',
    'key68703': 'value8777',
    'key72764': 'value20422',
    'key71490': 'value22562',
    'key21068': 'value13866',
    'key29814': 'value70995',
},
    {
    'id': 17527490817612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'Dr. Heather Wilson',
    'address': '383 Adam Forges Apt. 440\nHunterstad, NH 01680',
    'text': 'Despite behavior never truth century ten most. Small court history information education lose agency share. Me among building threat.',
    'email': 'hickstina@example.org',
    'phone_number': '+1-630-886-9659x60054',
    'json': {
    'name': 'Erica Williams',
    'address': '23169 Cooper Mall\nWest Tylerland, AK 59318',
},
    'key38867': 'value78541',
    'key4578': 'value83987',
    'key32368': 'value94498',
    'key46487': 'value95266',
    'key44810': 'value64409',
    'key93913': 'value80135',
},
    {
    'id': 17527490817624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Amy Perez',
    'address': '3128 Sparks Pine\nCamachochester, PA 19278',
    'text': 'Hour approach range again. Play will blood son understand. Article relate without consumer hold.\nResearch mind arm stay beautiful official. Goal here realize report.',
    'email': 'madisonjackson@example.net',
    'phone_number': '375-303-4215',
    'json': {
    'name': 'Vanessa Hawkins',
    'address': '604 Cunningham Forge\nPort Rebeccafort, IA 27817',
},
    'key77470': 'value34317',
    'key46627': 'value49368',
},
    {
    'id': 17527490817636,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'April Hansen',
    'address': '5503 Angelica Port\nLynnfurt, TX 54476',
    'text': 'Wish international together wide book data close. Majority whose plant do.\nManagement better or necessary nothing tonight such. However until west daughter whole which home.',
    'email': 'katherine20@example.com',
    'phone_number': '492.895.4160x538',
    'json': {
    'name': 'Kurt Powell',
    'address': '945 Garrett Loop Apt. 615\nNorth Danielle, MN 64032',
},
    'key48982': 'value1598',
    'key65252': 'value11475',
    'key81345': 'value61507',
    'key73704': 'value60118',
    'key18956': 'value29789',
    'key44042': 'value34073',
},
    {
    'id': 17527490817646,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Rachael Gomez',
    'address': 'USCGC Miller\nFPO AE 11979',
    'text': 'Indeed notice keep garden particular significant mother. Article away at former reduce option.',
    'email': 'rosselizabeth@example.net',
    'phone_number': '+1-735-267-6794x07415',
    'json': {
    'name': 'Justin Crawford',
    'address': '2947 Pamela Ports Apt. 105\nMcgeeside, SD 19966',
},
    'key37849': 'value42018',
    'key55015': 'value33932',
},
    {
    'id': 17527490817656,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Jennifer Davis',
    'address': '5920 Fields Underpass Apt. 935\nPort Summer, NM 96043',
    'text': 'Boy process reach. Food people information. Media money reality charge item imagine identify.',
    'email': 'jstrickland@example.net',
    'phone_number': '(860)229-5840x95128',
    'json': {
    'name': 'Brenda Whitaker',
    'address': '49971 Leon Springs Suite 962\nKellybury, OR 73679',
},
    'key4726': 'value77690',
    'key69249': 'value20945',
    'key27579': 'value72824',
    'key63149': 'value11680',
    'key65183': 'value57243',
},
    {
    'id': 17527490817667,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Erin Prince',
    'address': '03490 William Roads Apt. 786\nKimberlybury, MH 05373',
    'text': 'Factor suddenly serious prepare painting drop. Perform protect identify whole carry.',
    'email': 'amy29@example.org',
    'phone_number': '001-389-330-2204x2553',
    'json': {
    'name': 'Andrew Fisher',
    'address': '34343 Jim Junction Suite 562\nJonesside, ID 09521',
},
    'key65392': 'value72660',
    'key29778': 'value23796',
    'key21996': 'value70495',
    'key1757': 'value68588',
},
    {
    'id': 17527490817678,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Amy King',
    'address': '510 Tracy Loaf\nJuliashire, IN 18513',
    'text': 'Act inside several field oil cost operation professor. Story religious face seat mission opportunity able choice.',
    'email': 'justin85@example.net',
    'phone_number': '+1-542-402-5599x413',
    'json': {
    'name': 'Michelle Grant',
    'address': '2238 Avila Oval\nLeeborough, MD 72885',
},
    'key63124': 'value65145',
    'key68368': 'value83383',
    'key72657': 'value75278',
    'key15564': 'value85786',
},
    {
    'id': 17527490817688,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Veronica Wright',
    'address': '9596 Timothy Center Suite 549\nNew Ryan, IN 82290',
    'text': 'Operation young almost through writer pretty education.\nPer blood myself majority range whole always ground. Store seek western ten effect term.\nHusband form may staff since site. Source radio range.',
    'email': 'austinallen@example.net',
    'phone_number': '820.524.2524',
    'json': {
    'name': 'Joseph Gray',
    'address': '211 Christopher Land Suite 356\nEast Ronald, AS 12089',
},
    'key39213': 'value35764',
    'key62755': 'value62890',
    'key89777': 'value33028',
    'key42072': 'value98878',
    'key43484': 'value11087',
    'key75460': 'value1990',
    'key86490': 'value21790',
    'key85467': 'value6305',
    'key11871': 'value99707',
},
    {
    'id': 17527490817700,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Daniel Davies',
    'address': '29969 Brandy Estate\nNew Heather, ND 01644',
    'text': 'Often fill throughout food remember pressure may collection. At general test south TV plant response. Task source again seem large eye local.\nThan lot today young nor baby. Major author deep main.',
    'email': 'srichardson@example.com',
    'phone_number': '2246315352',
    'json': {
    'name': 'Julia Campbell',
    'address': '49460 Mitchell Wells\nJessicaton, AK 77998',
},
    'key79712': 'value26434',
    'key40394': 'value63350',
},
    {
    'id': 17527490817711,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Kevin Smith',
    'address': '7192 Ashley Junctions\nJesseton, OR 98619',
    'text': 'Loss whole foreign only. Push national system onto model how for.\nFar response task. Western game central affect.\nFocus expect important type call. East spend same party.',
    'email': 'michael07@example.net',
    'phone_number': '001-633-291-2199x617',
    'json': {
    'name': 'Dennis Flores',
    'address': '8001 Wolfe Springs Suite 751\nAmandahaven, MO 03656',
},
    'key53018': 'value56071',
    'key5218': 'value41670',
},
    {
    'id': 17527490817722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Daniel Robbins',
    'address': '6314 Shannon Mill Suite 201\nTamarahaven, TX 47861',
    'text': 'Child around through election instead coach. Edge maintain north can pull three. Show risk voice money term eight record.',
    'email': 'jamesgonzalez@example.com',
    'phone_number': '(764)366-4411x705',
    'json': {
    'name': 'Janet Mcdonald',
    'address': '082 Hartman Light\nWatsonhaven, AK 58239',
},
    'key24774': 'value96197',
    'key93398': 'value67583',
    'key27372': 'value51975',
},
    {
    'id': 17527490817734,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Stephen Johnson',
    'address': '3472 Joseph Row Suite 218\nPort Johnhaven, PW 62736',
    'text': 'Tax too poor wish quality speech. Husband central their line.\nMachine century system.\nAction building school enjoy this region guess.',
    'email': 'michaelhenry@example.com',
    'phone_number': '001-669-344-1361x23626',
    'json': {
    'name': 'Anne Weber',
    'address': '3092 Myers Fork Apt. 646\nNorth Rogerside, MS 37146',
},
    'key69948': 'value34640',
    'key72680': 'value70067',
},
    {
    'id': 17527490817747,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Katherine Mckenzie',
    'address': '789 Taylor River Apt. 153\nWest Joeville, NV 44582',
    'text': 'Television might lot through career consumer would. Through scene response middle.\nFly study herself personal scene. Leg decade explain green too. Suffer turn relate positive popular network.',
    'email': 'hannahsantiago@example.com',
    'phone_number': '+1-869-876-0915',
    'json': {
    'name': 'James Garza',
    'address': '8671 Colin Landing Apt. 154\nEast Kellyhaven, AK 18623',
},
    'key23807': 'value60378',
},
    {
    'id': 17527490817759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Sarah Franklin',
    'address': '46512 Lane Lodge\nMartinezfurt, GU 51783',
    'text': 'Security executive call chair. Success agency majority just long peace trip long.\nTen yeah participant end million practice natural. Artist every collection already.',
    'email': 'bpaul@example.org',
    'phone_number': '3033081737',
    'json': {
    'name': 'Caitlyn Hicks',
    'address': 'Unit 2546 Box 2178\nDPO AE 24931',
},
    'key87304': 'value97071',
    'key29508': 'value82790',
    'key11596': 'value41161',
},
    {
    'id': 17527490817768,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Marcus Marsh',
    'address': '8529 Lindsey Manors\nEast April, NH 32526',
    'text': 'Within pull claim sort since from. Help environmental employee process yard. Bank president radio government situation herself chance. Have respond experience pass popular.',
    'email': 'whitekelli@example.org',
    'phone_number': '636-614-2355x7072',
    'json': {
    'name': 'Patricia Scott',
    'address': '55495 Jacob Parkway Suite 589\nWest Virginiafurt, KY 12061',
},
    'key11377': 'value74006',
    'key34616': 'value63795',
    'key24727': 'value48927',
    'key76256': 'value67512',
    'key3688': 'value2557',
},
    {
    'id': 17527490817780,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Ashley Reed',
    'address': '81125 Brian Passage Apt. 335\nStanleyshire, SC 78601',
    'text': 'Challenge commercial standard ready. Us into exist something nearly dog indicate.\nSkill little save forward order everything. Win building market.',
    'email': 'seth96@example.net',
    'phone_number': '(662)566-9155x69818',
    'json': {
    'name': 'Christopher Hoffman',
    'address': '4188 Bailey Ports Apt. 877\nDavidport, NH 83703',
},
    'key8682': 'value35796',
    'key54131': 'value99179',
},
    {
    'id': 17527490817791,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Paul Wu',
    'address': '00796 Tommy Knoll Suite 363\nFischerton, MO 24948',
    'text': 'So charge change site both. Improve without exactly I drop then director.\nOutside all herself leader nor. Pretty item medical carry myself force. Several table enough event condition hand ready.',
    'email': 'campbellbrian@example.net',
    'phone_number': '513-753-8163x008',
    'json': {
    'name': 'Hailey Flynn',
    'address': '4342 Donna Isle\nWest Jameston, ID 73411',
},
    'key2120': 'value9428',
    'key30077': 'value26885',
    'key93552': 'value45844',
    'key48335': 'value38592',
    'key20076': 'value40917',
},
    {
    'id': 17527490817802,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Matthew Hale',
    'address': 'Unit 9796 Box 5704\nDPO AP 98689',
    'text': 'Thus leave left eat ball wide interest. Ok air notice else. Bring administration administration after.\nYear physical teacher police whom. Pay bag really here keep. Hour coach class debate American.',
    'email': 'robertsantos@example.com',
    'phone_number': '(382)320-7331x24858',
    'json': {
    'name': 'Veronica Pearson',
    'address': 'Unit 2610 Box 8425\nDPO AA 23259',
},
    'key51054': 'value71394',
},
    {
    'id': 17527490817810,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Anthony Meadows',
    'address': '56253 Joseph Creek\nLake Allison, KS 68810',
    'text': 'Condition simple whose. Short claim expect center.\nFormer south capital. Animal admit build human natural writer. Political movie event institution Mrs.',
    'email': 'elizabeth98@example.net',
    'phone_number': '001-934-893-9016x94035',
    'json': {
    'name': 'Tamara Carter',
    'address': '10478 Hill Manors\nWest Kathy, MS 54460',
},
    'key80719': 'value57419',
    'key15305': 'value42120',
},
    {
    'id': 17527490817820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Jennifer Miller',
    'address': '88724 Troy Turnpike Apt. 893\nSouth Karen, AR 83908',
    'text': 'Wonder wish road drug. Interview manager sometimes low meet in activity. Since offer involve agency popular.\nAbility here threat. Cost my create computer first up ago. Power prevent service fill.',
    'email': 'qdavis@example.net',
    'phone_number': '854.831.5457x42632',
    'json': {
    'name': 'Kelsey Crosby',
    'address': '7161 Nicholas Vista\nSouth Melissamouth, MT 81178',
},
    'key66799': 'value57929',
    'key47970': 'value40808',
    'key98136': 'value97143',
    'key58672': 'value1299',
    'key11343': 'value78972',
    'key13108': 'value96197',
    'key44555': 'value74031',
    'key82924': 'value88465',
    'key62502': 'value13351',
    'key3532': 'value55266',
},
    {
    'id': 17527490817831,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Elizabeth Cortez',
    'address': '04311 Matthew Parks\nWest Joannemouth, NM 38271',
    'text': 'Worker this sing once parent his white. Reduce huge television blue successful woman federal.\nOutside change meeting shake.\nLate as north. Matter effect fish father local throw behavior.',
    'email': 'armstrongwilliam@example.com',
    'phone_number': '711.703.1186x470',
    'json': {
    'name': 'John Lam',
    'address': '45368 Gary Port\nEast Marymouth, VT 70600',
},
    'key75005': 'value97357',
},
    {
    'id': 17527490817842,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'Thomas Khan',
    'address': '15700 Roberts Street\nPort Monica, WY 90505',
    'text': 'Magazine their run Mrs resource. Suggest film different.\nNatural who response year inside money. Talk medical compare general level opportunity area. Church budget just member spend.',
    'email': 'dhuffman@example.net',
    'phone_number': '522.831.8617x13083',
    'json': {
    'name': 'Greg Black',
    'address': 'Unit 3744 Box 3339\nDPO AA 54494',
},
    'key83013': 'value994',
    'key56307': 'value63428',
    'key96603': 'value47345',
    'key23442': 'value35665',
    'key94724': 'value65944',
},
    {
    'id': 17527490817851,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Jill Reed',
    'address': '59385 Miller Valleys Suite 059\nLake Ryan, CA 56776',
    'text': 'Security follow paper friend west. Individual possible role positive pretty.\nConference these age challenge current father school. North both others lay who available expect test.',
    'email': 'bauerjustin@example.com',
    'phone_number': '430-308-3225x31153',
    'json': {
    'name': 'Michael Cook',
    'address': '3904 Joseph Fields Apt. 200\nEast Markfurt, ND 36777',
},
    'key66075': 'value47797',
    'key62789': 'value72195',
    'key57132': 'value14878',
    'key38761': 'value29739',
    'key11427': 'value43202',
    'key63151': 'value58240',
    'key85171': 'value31978',
},
    {
    'id': 17527490817862,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Keith Smith',
    'address': '86866 Ward Haven Apt. 454\nLake Heidi, MO 41382',
    'text': 'Radio show reduce environment. Challenge gun believe technology their floor current rock.',
    'email': 'elizabeth21@example.com',
    'phone_number': '2022078237',
    'json': {
    'name': 'Jody Torres',
    'address': '037 Hickman Knolls Suite 987\nGuzmanmouth, VT 73775',
},
    'key59794': 'value5514',
    'key50879': 'value35954',
    'key24779': 'value16267',
    'key80396': 'value94434',
    'key91890': 'value35803',
    'key91831': 'value7242',
},
    {
    'id': 17527490817873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Alexandra Williamson',
    'address': '88383 Rodriguez Avenue Suite 849\nBrittanyfort, NM 36390',
    'text': 'Free certain too exist receive.\nSpeak as conference easy. Son impact board manage.\nCup responsibility these bed star fear. Democratic close sit own. Pick hold between common half hear bill.',
    'email': 'randy56@example.org',
    'phone_number': '500.880.6040',
    'json': {
    'name': 'Kimberly Trevino',
    'address': '2481 Allen Dam Suite 108\nEast Davidchester, MD 40442',
},
    'key30532': 'value42182',
    'key39720': 'value49146',
},
    {
    'id': 17527490817884,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Ashley Beasley',
    'address': '666 Wise Skyway Suite 703\nMaryborough, CO 35628',
    'text': 'Economic measure wind old choice. Media five tell since.\nPlant PM task research account your peace. Day operation interesting dinner lot instead.',
    'email': 'hamiltonjack@example.com',
    'phone_number': '001-440-499-1884x651',
    'json': {
    'name': 'Lucas Costa',
    'address': '43242 Jenkins Station\nSouth Andrew, MO 35064',
},
    'key44163': 'value35929',
    'key23709': 'value84111',
    'key97555': 'value52295',
    'key74526': 'value70333',
    'key11247': 'value54806',
    'key10046': 'value19776',
    'key31078': 'value60987',
    'key53313': 'value92082',
    'key69282': 'value60600',
    'key28637': 'value11088',
},
    {
    'id': 17527490817895,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Blake Holland',
    'address': '1630 Smith Village Suite 174\nLeeberg, IA 51456',
    'text': 'Responsibility staff thought player produce style idea industry. Arrive especially social effect friend standard. I team somebody leave set top.',
    'email': 'jlucas@example.net',
    'phone_number': '458-939-9206',
    'json': {
    'name': 'Samantha Young',
    'address': '4726 Jasmin Skyway Apt. 290\nKristinberg, MA 03373',
},
    'key89053': 'value75046',
    'key14185': 'value55795',
},
    {
    'id': 17527490817906,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Matthew Allen',
    'address': '4816 Martin Vista\nBethanyfurt, PW 46132',
    'text': 'Film smile rate different. Manager president project series world. Phone before administration open.',
    'email': 'wongrobert@example.org',
    'phone_number': '(317)581-1679',
    'json': {
    'name': 'Richard Rivera',
    'address': '95274 Allison Lights\nPort Shelly, DC 57803',
},
    'key33050': 'value27980',
    'key35818': 'value55841',
    'key90335': 'value62910',
    'key41445': 'value68745',
    'key57236': 'value74981',
    'key49793': 'value87209',
    'key30849': 'value25963',
},
    {
    'id': 17527490817917,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'Diana Butler',
    'address': '5273 Zachary Fork\nBrandonberg, UT 26234',
    'text': 'Myself sense improve executive. Middle use remain water.\nSeries boy pick training book fast employee. Sport large open perform successful meet.',
    'email': 'ffritz@example.org',
    'phone_number': '001-390-722-4211x07174',
    'json': {
    'name': 'Briana Miller',
    'address': '49242 Hale Throughway Suite 979\nNicoleland, CT 51346',
},
    'key8464': 'value74682',
    'key26796': 'value87932',
    'key23868': 'value91764',
    'key39335': 'value13267',
    'key25622': 'value38150',
    'key26862': 'value98799',
    'key76683': 'value66499',
    'key86757': 'value88550',
    'key28569': 'value38456',
},
    {
    'id': 17527490817928,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Angela Hernandez',
    'address': '082 Reid Rue Suite 234\nEast Edwardside, SD 30461',
    'text': 'Decide physical race place able. Fish house get popular.\nData city network hospital recently prepare end doctor. Cut rock light. Activity believe officer door must. Executive heart far career cell.',
    'email': 'younglisa@example.org',
    'phone_number': '301-434-2558',
    'json': {
    'name': 'David Johnson',
    'address': '83501 Rhonda Harbor Apt. 713\nJohnsonstad, VT 93533',
},
    'key33285': 'value95354',
    'key56601': 'value32774',
    'key30739': 'value99221',
    'key72586': 'value24866',
},
    {
    'id': 17527490817940,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Ricardo Campbell',
    'address': 'USNS Chandler\nFPO AE 04113',
    'text': 'Same seem southern affect natural candidate later among. Test trip down.\nCertain get likely situation although official decision. Skill character sort human officer.',
    'email': 'christopher97@example.net',
    'phone_number': '+1-316-928-5187x8670',
    'json': {
    'name': 'Amanda Harmon',
    'address': '47903 Moore Unions\nCabreramouth, ID 44952',
},
    'key51752': 'value92595',
    'key69616': 'value39168',
},
    {
    'id': 17527490817950,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Jennifer Delacruz',
    'address': '833 Alvarado Haven Suite 544\nSouth Cynthiaside, HI 56149',
    'text': 'Billion positive blue environment green explain. Though while challenge community sometimes.\nIndividual news me goal. Past alone own method idea.',
    'email': 'emma16@example.org',
    'phone_number': '(742)696-6214',
    'json': {
    'name': 'Jill Wise',
    'address': '0803 Gallegos Gateway Apt. 593\nLake Lauren, MI 22928',
},
    'key33451': 'value2823',
    'key57934': 'value67641',
    'key34053': 'value87597',
},
    {
    'id': 17527490817960,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Monica Holmes',
    'address': '0970 Jones Crescent\nMurrayfort, AS 93705',
    'text': 'Maintain fast region provide end however newspaper. Example far unit reach. Assume bag dream dog some manage ever.',
    'email': 'spencerjessica@example.org',
    'phone_number': '001-698-689-1572',
    'json': {
    'name': 'Mary Oconnor',
    'address': '23331 Taylor Corner\nEast Brett, ID 52717',
},
    'key46848': 'value20577',
    'key23946': 'value52316',
    'key48896': 'value99621',
    'key2066': 'value63828',
    'key65087': 'value55755',
    'key75815': 'value49343',
    'key66881': 'value2168',
    'key18001': 'value51261',
    'key11504': 'value13399',
},
    {
    'id': 17527490817972,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'Edward Hoffman',
    'address': '3082 Elizabeth Islands\nNew Cheyenneshire, FL 50253',
    'text': 'West practice former both. Word former make ask.\nHer majority fast. Mrs structure leg assume. Reason stop happen agree large improve.',
    'email': 'josephgamble@example.com',
    'phone_number': '(592)507-0002x40204',
    'json': {
    'name': 'Suzanne Wong',
    'address': '77811 Bowman Mountain Suite 510\nNorth Olivia, KY 65444',
},
    'key88456': 'value58454',
    'key96517': 'value68076',
},
    {
    'id': 17527490817983,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'William Graham',
    'address': '247 George Glen\nSouth Haleyside, UT 41239',
    'text': 'Prevent determine training help rule with life. Range market less participant work character.\nNot American friend long. Who individual gas newspaper read picture woman seem.',
    'email': 'orichardson@example.org',
    'phone_number': '001-537-319-8082x42385',
    'json': {
    'name': 'Craig Keller',
    'address': '37889 Daniel Pike Suite 769\nEast Debbieberg, MN 63456',
},
    'key62261': 'value39270',
    'key73104': 'value48859',
    'key49796': 'value10492',
    'key62256': 'value68851',
    'key54516': 'value75806',
    'key52851': 'value30567',
    'key845': 'value19699',
},
    {
    'id': 17527490817994,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'Paul Blake',
    'address': '965 Jonathan Hills Apt. 144\nLake Stephenland, NC 94155',
    'text': 'Course car free quickly evening. Down stop action quality. Other individual include list air.\nReveal air street describe human store. Moment ahead discussion because serve follow prepare.',
    'email': 'kgreen@example.net',
    'phone_number': '226-898-0557x9167',
    'json': {
    'name': 'Jeffrey Cunningham',
    'address': '58028 Townsend Square\nLucasmouth, PR 02861',
},
    'key61405': 'value69512',
    'key11197': 'value51760',
    'key52748': 'value49869',
    'key34244': 'value14386',
},
    {
    'id': 17527490818005,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Cynthia Cooper',
    'address': '159 Haley Way Suite 597\nPort Johnton, NV 92918',
    'text': 'Personal good place discover same. Imagine suffer itself there position according. Half also writer sort range quickly probably.\nRun interview citizen join military enjoy. Really special buy you.',
    'email': 'mary78@example.org',
    'phone_number': '001-519-512-1553x2936',
    'json': {
    'name': 'Sabrina Rodriguez',
    'address': '5087 David Club\nNew Rogerchester, CA 08820',
},
    'key56071': 'value79871',
    'key64301': 'value86454',
    'key84850': 'value6802',
    'key58002': 'value30934',
    'key11414': 'value38276',
    'key95448': 'value46678',
},
    {
    'id': 17527490818016,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Elizabeth Mejia',
    'address': '004 Meghan Spurs Apt. 745\nNew Julie, OK 28253',
    'text': 'Address allow store stop easy represent. Inside finally well ask accept story. Record join project check one.',
    'email': 'walkeramber@example.org',
    'phone_number': '001-533-594-0448x9850',
    'json': {
    'name': 'Frank Hoffman',
    'address': '927 Harris Alley\nShannonville, IN 37512',
},
    'key5684': 'value10484',
    'key38921': 'value58216',
    'key93365': 'value14776',
    'key19654': 'value42421',
    'key63183': 'value93177',
    'key23780': 'value92657',
    'key13174': 'value30726',
    'key65598': 'value58665',
    'key76371': 'value36955',
},
    {
    'id': 17527490818027,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Cheryl Brooks',
    'address': '5391 Amanda Pines Apt. 169\nMillermouth, MI 34680',
    'text': 'Wear take term data story medical. Without year surface him.\nBit population rule black. Easy task already participant.\nCurrent interesting either.',
    'email': 'rosecharles@example.org',
    'phone_number': '001-718-585-7406x649',
    'json': {
    'name': 'Brian Everett',
    'address': '034 Ortega Creek Suite 523\nNew Monica, CO 95963',
},
    'key71149': 'value29130',
    'key81975': 'value29680',
    'key13646': 'value28431',
    'key13068': 'value43014',
    'key77582': 'value52148',
    'key53708': 'value69251',
    'key44031': 'value18201',
    'key45108': 'value10647',
    'key18551': 'value20833',
    'key26514': 'value32201',
},
    {
    'id': 17527490818039,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Amy Hardy',
    'address': '429 Parker Parkway Suite 522\nSmithtown, SD 71823',
    'text': 'Relate seek small. Wish such support spring. Now land time clear.\nWhat model main town. Enough democratic tree despite player reduce identify. Some brother adult artist involve might.',
    'email': 'upatrick@example.net',
    'phone_number': '731-800-8656x7197',
    'json': {
    'name': 'Corey Garcia',
    'address': '828 Tricia Mill Suite 341\nWest Manuel, CO 03701',
},
    'key39761': 'value28113',
    'key46126': 'value94128',
    'key78733': 'value8846',
    'key14086': 'value73279',
    'key45549': 'value39729',
    'key12951': 'value58831',
    'key70025': 'value9159',
    'key59371': 'value10866',
    'key92053': 'value65981',
    'key50659': 'value48856',
},
    {
    'id': 17527490818051,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'Anna Luna',
    'address': '05315 April Inlet Apt. 979\nDamontown, KY 24859',
    'text': 'Mother return vote former career drop design hour. Against item her quite page low run.',
    'email': 'davidpowers@example.com',
    'phone_number': '001-986-695-0984x2642',
    'json': {
    'name': 'Jennifer Fleming',
    'address': '552 Thompson Fields Apt. 102\nWest Hector, WY 23037',
},
    'key28753': 'value98741',
},
    {
    'id': 17527490818062,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Austin Gonzalez',
    'address': '7182 Charles Estates Suite 458\nJosephfurt, VT 44177',
    'text': 'Customer part hundred pressure. Month happy heavy television until. Whose area easy.\nCell those four price idea positive choose. View time result.',
    'email': 'browndavid@example.net',
    'phone_number': '580-532-6171',
    'json': {
    'name': 'Alexandra Palmer',
    'address': '37387 Kimberly Loaf\nPort Gregoryberg, OR 03161',
},
    'key11174': 'value69398',
    'key90572': 'value73214',
    'key1773': 'value50704',
    'key62781': 'value47459',
    'key50457': 'value85021',
},
    {
    'id': 17527490818074,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Spencer Santiago',
    'address': 'Unit 4067 Box 8614\nDPO AA 61672',
    'text': 'Fear miss guy. Firm important doctor. Bag other administration strategy subject. Point American create artist.',
    'email': 'eallen@example.org',
    'phone_number': '563.506.4807x1537',
    'json': {
    'name': 'Cynthia Powell',
    'address': '076 Molly Plains Apt. 889\nYoungland, AS 17761',
},
    'key70227': 'value84205',
    'key5608': 'value927',
    'key34677': 'value6351',
    'key94817': 'value78884',
    'key62253': 'value77003',
    'key39371': 'value74294',
    'key46422': 'value69416',
},
    {
    'id': 17527490818083,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'Kelly Burns',
    'address': '0420 Melissa Extension\nBurtonshire, NV 33052',
    'text': 'Accept thus answer serious single down. Buy catch rest garden avoid amount piece.',
    'email': 'lauren69@example.org',
    'phone_number': '634-824-5163x28461',
    'json': {
    'name': 'Laura Williams',
    'address': '651 Tasha Inlet\nNew Matthew, MP 73453',
},
    'key92144': 'value16178',
    'key83262': 'value60745',
    'key66719': 'value8204',
    'key5351': 'value32779',
    'key27123': 'value5584',
    'key26436': 'value59879',
    'key74642': 'value32923',
    'key81226': 'value65265',
},
    {
    'id': 17527490818097,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Jose Baxter',
    'address': '4387 Moody Isle\nSouth Brandonbury, WV 63701',
    'text': 'Human forget entire billion win wonder box conference. Describe collection clearly best check rock.',
    'email': 'barnesjoseph@example.org',
    'phone_number': '+1-746-328-7884',
    'json': {
    'name': 'Melissa Holmes',
    'address': '714 Henry Spurs\nTurnerchester, OR 60944',
},
    'key93953': 'value9630',
    'key50400': 'value51971',
    'key70795': 'value27115',
    'key97859': 'value75064',
    'key20743': 'value82840',
    'key36661': 'value14835',
    'key65121': 'value91531',
    'key32763': 'value56041',
    'key54750': 'value81727',
    'key68698': 'value60746',
},
    {
    'id': 17527490818108,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Tiffany Mosley',
    'address': '7925 Lambert Mountains\nDarrellmouth, GA 69158',
    'text': 'Today affect interest describe yourself scientist. Degree near fear parent strong despite many. Attack seat good heavy challenge kitchen control go.',
    'email': 'tiffanyscott@example.com',
    'phone_number': '221.506.2302x11728',
    'json': {
    'name': 'Alex Arellano',
    'address': '0552 Collins Lodge\nSethside, DE 84265',
},
    'key20173': 'value65584',
    'key96493': 'value66088',
    'key46515': 'value35255',
    'key69072': 'value29559',
    'key526': 'value24985',
    'key53646': 'value84722',
    'key26860': 'value98815',
    'key79356': 'value29195',
    'key71991': 'value48111',
    'key46109': 'value3218',
},
    {
    'id': 17527490818120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Steven Matthews',
    'address': '4948 Reed Lodge Suite 789\nWest Michael, AR 86434',
    'text': 'Fact image peace really another dark. Magazine billion reality minute movement air include.\nMoment hard sister well to ever same.',
    'email': 'tonycarpenter@example.org',
    'phone_number': '(992)916-8859x9001',
    'json': {
    'name': 'Michael Hodges',
    'address': '082 Michelle Harbors Suite 465\nAprilmouth, VA 29668',
},
    'key71976': 'value80865',
    'key52207': 'value39734',
    'key39288': 'value61839',
    'key62641': 'value25924',
    'key46485': 'value33962',
    'key4175': 'value54358',
    'key61541': 'value36978',
    'key66592': 'value25880',
    'key41775': 'value6685',
    'key56368': 'value30092',
},
    {
    'id': 17527490818131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Patrick Woodard DVM',
    'address': '998 Amanda Stravenue\nBriannaview, WV 02618',
    'text': 'Size break else charge share small. Because decade community yet. Culture response establish rather huge book sound small.\nExist since physical amount form force. Head school couple memory believe.',
    'email': 'wrightchristopher@example.net',
    'phone_number': '(384)370-8741x568',
    'json': {
    'name': 'Sheri Smith',
    'address': '36589 Jesus Pass\nEast Christina, VI 03486',
},
    'key21061': 'value11287',
    'key73452': 'value62079',
    'key29308': 'value84598',
    'key94051': 'value45116',
    'key89633': 'value46427',
    'key14788': 'value70683',
    'key29402': 'value78183',
    'key96573': 'value30433',
    'key82493': 'value4715',
    'key62771': 'value1915',
},
    {
    'id': 17527490818143,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Caitlin Ochoa',
    'address': '485 Lindsey Stravenue Suite 575\nEast Michelle, VA 36941',
    'text': 'Pass movement he yourself central early. Life home that will.\nThat page enjoy boy me. Everybody point happen drop language. Stage vote can treat risk bank.',
    'email': 'juanjackson@example.org',
    'phone_number': '(628)205-3116x4387',
    'json': {
    'name': 'Samantha Pearson',
    'address': '956 Ward Rapid\nNorth Williamchester, AK 78639',
},
    'key23602': 'value72431',
    'key81478': 'value58216',
},
    {
    'id': 17527490818154,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Tammy Mccall',
    'address': '17659 Armstrong Tunnel\nLake Robinbury, ME 08651',
    'text': 'Where candidate daughter place happy move beautiful or. May letter high product conference.\nWill art draw. Writer cause senior report piece defense.',
    'email': 'jsimon@example.com',
    'phone_number': '7872014623',
    'json': {
    'name': 'Robin Dalton',
    'address': '61751 Christopher Mills\nLarsenberg, GU 01991',
},
    'key74831': 'value72711',
},
    {
    'id': 17527490818165,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Tina Roberts',
    'address': '508 Stephanie Street\nPort Cynthia, DC 29664',
    'text': 'Return everyone choose return source.\nMiss peace weight information detail top. Compare recent its agent price range personal.',
    'email': 'taylorralph@example.org',
    'phone_number': '001-676-835-6504x351',
    'json': {
    'name': 'Jared Carroll DDS',
    'address': '93210 Laura Island\nEmilyburgh, MN 23129',
},
    'key16489': 'value26653',
    'key66195': 'value86920',
    'key15272': 'value10948',
    'key10407': 'value54425',
},
    {
    'id': 17527490818176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Adriana Prince',
    'address': '34433 Cheyenne Street Suite 786\nDebbieside, WV 81751',
    'text': 'Discover work fight at hope. North you remain laugh.\nParticipant suffer move school. Model price organization decade know find experience behind. One discussion bag building.',
    'email': 'hjenkins@example.net',
    'phone_number': '936-830-6236',
    'json': {
    'name': 'Chad Ochoa',
    'address': '17163 Anna Manor Apt. 093\nNew Timothy, IA 02571',
},
    'key72302': 'value74867',
    'key6380': 'value71480',
    'key67250': 'value16819',
    'key88684': 'value93551',
},
    {
    'id': 17527490818186,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Bruce Larson',
    'address': '182 Nicholas Ferry\nMorsefort, VI 74921',
    'text': 'Black threat great.\nFinally someone environment issue ball. Attack establish white accept development early. Once those door structure ready.',
    'email': 'montoyalinda@example.net',
    'phone_number': '001-568-729-1890',
    'json': {
    'name': 'Barbara Henry',
    'address': '28828 Scott Valleys Apt. 510\nNorth Richardfort, GA 09679',
},
    'key23466': 'value98278',
    'key25964': 'value33377',
    'key55081': 'value20280',
    'key41371': 'value78928',
    'key25831': 'value39490',
    'key60383': 'value71742',
    'key94520': 'value15949',
    'key70535': 'value50719',
    'key52077': 'value65209',
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
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
    'vector',
    'json',
],
    'filter': 'uid in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199]',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/entities/get"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/get")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/get'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
    'vector',
    'json',
],
    'id': self.mutator.generate_float_array(dimension=100, normalized=True),
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
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
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



    def test_request_7(self):
        """测试请求 7 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
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



    def test_request_8(self):
        """测试请求 8 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '07cc8c22-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_44_35_568481PjVknrsO',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestGetVector_test_get_vector_complex[True-True-list]_1752749086.json')
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
    test = AllmilvusLogtestgetvectorTestGetVectorComplexTrueTrueList1752749086Json()
    test.run_tests()
