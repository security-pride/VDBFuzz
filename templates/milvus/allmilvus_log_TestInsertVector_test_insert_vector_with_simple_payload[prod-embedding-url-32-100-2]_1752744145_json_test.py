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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-2]_1752744145_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-2]_1752744145.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl3210021752744145Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-2]_1752744145.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-2]_1752744145.json"
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
    'RequestId': '8cbac079-62ef-11f0-9a2a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_23_623916aTqOyFCI',
    'dimension': 32,
    'primaryField': 'url',
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
    'RequestId': '8ce0e4a6-62ef-11f0-8f21-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_23_623916aTqOyFCI',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Michelle Santiago',
    'address': '8284 Wendy Corner Suite 429\nMontgomeryhaven, OR 25428',
    'text': 'Thing experience study agency goal discussion.\nAlmost nation else network them. Admit enter man green that accept close.',
    'email': 'shawgregory@example.com',
    'phone_number': '(230)877-8094x3518',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Douglas Estes',
    'Angela Vaughn',
    'Stephanie Mccarthy',
    'Teresa Krause',
    'Zachary Tucker',
    'Lisa Jackson',
    'Tiffany Vasquez',
],
    'json': {
    'name': 'Kelly Castillo',
    'address': '524 Thompson Springs\nCatherineburgh, WA 06944',
},
    'key73564': 'value41305',
    'key24040': 'value60881',
    'key9299': 'value6843',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Terrence Moran',
    'address': '5127 Pena Oval\nPort Linda, NE 18097',
    'text': 'She well song party lose city.\nProject live outside also such. Dream political city interest.\nSense probably hospital sea. Thing watch government top material if.',
    'email': 'angelalewis@example.org',
    'phone_number': '+1-993-784-6199x48056',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Monroe',
    'Gina Haynes',
    'Nancy Kline',
    'Nina May',
],
    'json': {
    'name': 'Kenneth Williams Jr.',
    'address': '431 Michele Ford\nWest Jennifer, NY 92743',
},
    'key43990': 'value98087',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Adam Parks',
    'address': '07856 Edward Brook Apt. 306\nMichaelland, OK 80355',
    'text': 'Her left box. Impact see finally sign quite just. Figure second middle exist theory interview.\nLoss toward week kind agree very. Deep employee after again peace area.',
    'email': 'rrobinson@example.org',
    'phone_number': '611.298.7778',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Turner',
    'Jeffrey Velazquez',
],
    'json': {
    'name': 'Marcus Grant',
    'address': '50711 Wilson Parkways Apt. 566\nWilsonberg, NE 33118',
},
    'key35469': 'value1372',
    'key92728': 'value1637',
    'key51150': 'value7721',
    'key79118': 'value99049',
    'key98107': 'value94314',
    'key77426': 'value60559',
    'key8833': 'value95418',
    'key83533': 'value72938',
    'key92469': 'value53788',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Barbara Moses DDS',
    'address': '114 Gomez Cape Apt. 641\nPort Krista, FL 81477',
    'text': 'Plant century role place article. While watch politics write heart.\nTree expert election turn case customer. Soldier onto rich third which. Book management commercial same structure fight.',
    'email': 'jennifer38@example.com',
    'phone_number': '2509044996',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Gonzales',
    'Jonathan Miller',
    'Ashley Boyer',
    'Lisa Vaughn',
    'Jennifer Colon',
],
    'json': {
    'name': 'Kristi Barnes',
    'address': 'Unit 7595 Box 7080\nDPO AE 41045',
},
    'key94883': 'value30895',
    'key28273': 'value54564',
    'key93314': 'value33783',
    'key39918': 'value62074',
    'key82042': 'value13294',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'William Smith',
    'address': '257 Cameron Well\nLake Kaylashire, DE 66269',
    'text': 'Himself make pull light. Reveal concern hot vote raise mother.\nManage of vote. Worker yard major should power. Bring under character recognize research have.',
    'email': 'danielcastillo@example.net',
    'phone_number': '579-744-0750x863',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Keith Le',
],
    'json': {
    'name': 'Cynthia Lewis',
    'address': '33640 Burgess Walk Suite 730\nJamesfort, KS 21869',
},
    'key22868': 'value70829',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Jennifer Harrison',
    'address': '8649 Smith Row\nWest Kylemouth, SD 17325',
    'text': 'Peace offer interview skill necessary than reflect. Break city above one. Hot national senior defense prepare foreign.',
    'email': 'cynthiabrown@example.org',
    'phone_number': '634.988.8144x68662',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Duncan',
    'Monica Garcia',
    'John White',
    'Jaclyn Atkins',
    'Christine Robinson',
    'David Carrillo',
    'Joanna Hall',
    'Rodney Lopez',
],
    'json': {
    'name': 'Christy Martinez',
    'address': '659 Wells Wells Apt. 341\nPerezfurt, LA 25928',
},
    'key38065': 'value41666',
    'key85139': 'value90327',
    'key39724': 'value84973',
    'key37294': 'value9782',
    'key87584': 'value43946',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Brian Zuniga',
    'address': '791 Kimberly Square\nNew Christine, NV 20678',
    'text': 'Cut decade perform international front detail loss. Particular brother alone executive whole sometimes. Again see good agent develop he use.',
    'email': 'rebeccahughes@example.net',
    'phone_number': '469.832.9483x90768',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Richardson',
    'Crystal Garcia',
    'Christopher Becker',
    'Jason Lee',
    'Karen Brown',
    'Diana Johnson',
    'David Leon',
    'Barbara Macdonald',
],
    'json': {
    'name': 'Chad Odonnell',
    'address': '745 Peterson Roads Apt. 843\nAdamside, NE 69943',
},
    'key75041': 'value10423',
    'key36485': 'value50267',
    'key54640': 'value32920',
    'key71201': 'value77096',
    'key49057': 'value55306',
    'key62633': 'value67455',
    'key84938': 'value72528',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Ryan Romero',
    'address': '17219 Garner Tunnel Apt. 074\nWest Micheletown, MD 65718',
    'text': 'Deal economic job. Civil cost paper find push of investment. Dog entire once upon citizen against.\nLand deep throw challenge future. Yet production moment. Fall action meet see defense since.',
    'email': 'egallegos@example.org',
    'phone_number': '(438)380-1263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amy Rios',
    'Frank Price',
    'Hunter Leonard',
    'Todd Merritt',
    'Kristen Miller',
    'Kari Thompson',
    'Elizabeth Jackson',
    'Susan Ewing',
    'Daniel Charles',
],
    'json': {
    'name': 'Carrie Garcia',
    'address': '1734 Smith Ford\nKarenhaven, AZ 67700',
},
    'key30848': 'value79883',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Christian Green',
    'address': '0188 Russell Parks\nLake Tyler, DC 40613',
    'text': 'Rock leave detail one assume. Candidate full everyone know worry red true language. She wife reveal fight.\nOccur necessary yeah likely put different. Above cut standard citizen end amount bed dog.',
    'email': 'kristinmcdonald@example.org',
    'phone_number': '336-614-1038x034',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brett Mcknight',
    'Joshua Wong',
    'Mia Aguilar',
    'Amanda Jackson',
    'Willie Schmidt',
    'Austin Singh',
    'Nathan Turner',
],
    'json': {
    'name': 'Toni Keller',
    'address': '43871 Garcia Wells\nWest Andrea, HI 41217',
},
    'key19911': 'value82317',
    'key29624': 'value81593',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Christopher Greer',
    'address': '902 Roberts Harbor\nYoungview, GU 81503',
    'text': 'Ability technology she relationship art great. Choose prevent baby reflect work stand west watch.\nMemory require month do. Research rather simple question pretty heart time. Bar explain together to.',
    'email': 'gail88@example.org',
    'phone_number': '756.483.0541',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Casey Ford',
    'Julie Davila',
    'Brian Davis',
    'Jo Hill',
],
    'json': {
    'name': 'Mr. Dennis Berg Jr.',
    'address': '556 Smith Lights Apt. 491\nPort Judith, ND 63007',
},
    'key26173': 'value94561',
    'key39920': 'value82911',
    'key35320': 'value2222',
    'key24888': 'value25748',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Margaret Hill',
    'address': 'Unit 8853 Box 6424\nDPO AE 76175',
    'text': 'Whole discussion huge war among. Occur citizen first guy check.\nRespond contain two spend although mother technology prevent. Owner game continue force. Focus marriage imagine vote.',
    'email': 'thomasmartinez@example.net',
    'phone_number': '449-642-9118x555',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Jordan',
    'Audrey Schroeder',
    'Tracy Nunez',
    'Bobby King',
    'Kevin Reid',
    'Kenneth Brown',
],
    'json': {
    'name': 'Alexis Macdonald',
    'address': '421 Lee Freeway\nElizabethshire, AK 30250',
},
    'key37942': 'value56192',
    'key72169': 'value62130',
    'key25509': 'value87298',
    'key79632': 'value23324',
    'key22913': 'value42050',
    'key41515': 'value21058',
    'key49265': 'value66740',
    'key22383': 'value5365',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Sarah Morris',
    'address': '53396 Moore Throughway\nPort Chelseabury, PR 05085',
    'text': 'Quality defense here land himself popular. Song election water. Service back operation me blood. Pass everyone manage size within former door.',
    'email': 'richardsjames@example.com',
    'phone_number': '+1-906-468-5774x126',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ethan Davis',
    'Abigail Silva',
    'Melissa Ingram PhD',
    'Erica Jackson',
    'Nichole Brown',
],
    'json': {
    'name': 'Dominic Flores',
    'address': 'PSC 7290, Box 4658\nAPO AE 50885',
},
    'key34397': 'value54255',
    'key5056': 'value9207',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Lori Velasquez',
    'address': '79563 Sullivan Pine Suite 602\nJoelchester, MT 26685',
    'text': 'Almost about especially smile while cold wish. Chair figure cut bank.\nAnalysis close now. Easy save just.',
    'email': 'lbarajas@example.org',
    'phone_number': '507.926.8815x12290',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jim Burton',
    'Casey Dodson',
    'Brandon Molina',
    'Melissa Palmer',
],
    'json': {
    'name': 'Lori Beck',
    'address': '61807 Kathryn Mountains Apt. 879\nNorth Dennis, OH 99134',
},
    'key91354': 'value74661',
    'key58983': 'value4611',
    'key65347': 'value53098',
    'key7558': 'value73115',
    'key2798': 'value54809',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'John Blackwell',
    'address': '8714 Erin Crest\nMatthewview, WV 91562',
    'text': 'Mention administration such brother. Security else young professor take adult figure produce. Wait maybe interview tax entire entire TV.',
    'email': 'mariapowell@example.com',
    'phone_number': '802.999.9419',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Cheryl House',
    'Sandra Perry',
    'Scott Blanchard',
    'Andrew Jones',
    'Melissa Lawson',
],
    'json': {
    'name': 'Megan Le',
    'address': 'PSC 8979, Box 4478\nAPO AE 69849',
},
    'key93453': 'value83812',
    'key50062': 'value9838',
    'key12751': 'value87505',
    'key72928': 'value11802',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Theodore Price',
    'address': 'PSC 3785, Box 4179\nAPO AA 62664',
    'text': 'Light court movement weight. Natural view interesting summer voice edge still. Arrive order relate available. Five quality Republican environment hear.',
    'email': 'randallsandra@example.org',
    'phone_number': '001-597-826-7348',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Allison Orozco',
    'Charles Brown',
    'Kevin Parker',
    'Susan Morton',
    'David Gonzalez',
],
    'json': {
    'name': 'Kristi Hernandez',
    'address': '292 Long Springs\nJamesville, KS 84071',
},
    'key78058': 'value77467',
    'key1799': 'value10174',
    'key78529': 'value99125',
    'key40664': 'value29577',
    'key64009': 'value82953',
    'key81836': 'value94547',
    'key14844': 'value31618',
    'key33244': 'value27819',
    'key49343': 'value98590',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Cynthia Phillips',
    'address': '74781 Anthony Shoal\nWest Stephen, UT 90412',
    'text': 'Oil price present training. Story scientist professional ball yourself. While even home. Rise add quickly answer better themselves girl.',
    'email': 'kaguilar@example.net',
    'phone_number': '755.435.8410',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Patterson',
    'Samuel Simpson',
    'David Anderson',
    'Diana Johnson',
    'Ashley Hodges',
    'Rick Adams',
    'Beth Thomas',
    'Philip Welch',
    'Lauren Mcbride',
],
    'json': {
    'name': 'Jessica West',
    'address': '26601 Aaron Forges\nNew Alejandrotown, MS 58191',
},
    'key21999': 'value94804',
    'key39766': 'value81480',
    'key74880': 'value42231',
    'key52297': 'value54483',
    'key3541': 'value36721',
    'key89401': 'value34617',
    'key33348': 'value67093',
    'key87123': 'value11189',
    'key95423': 'value81526',
    'key42482': 'value78109',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'David Wright',
    'address': '8226 Joshua Club Apt. 754\nVictormouth, TX 59632',
    'text': 'Base group cup. Grow support side nature.\nShe when firm capital cell or. Behind especially just new food. Together loss ten officer care.',
    'email': 'michelle34@example.com',
    'phone_number': '351-690-2938x9811',
    'array_int_dynamic': [
    8561,
],
    'array_varchar_dynamic': [
    'Brittany Gardner',
    'Michelle Clark',
    'Tony Barker',
    'Nathan Sims',
    'Curtis Ross',
    'Tyrone Clark',
    'Leah Lowery',
    'Cheryl Stanton',
],
    'json': {
    'name': 'Chris Aguilar',
    'address': 'PSC 6711, Box 5214\nAPO AE 08889',
},
    'key58386': 'value39638',
    'key29787': 'value98986',
    'key92064': 'value33073',
    'key68118': 'value98099',
    'key59531': 'value17795',
    'key2713': 'value73126',
    'key82347': 'value90781',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Carol Salazar',
    'address': '35856 Lisa Hill\nNew Allen, VA 37883',
    'text': 'Point president middle each. Later bad prove. Similar body threat quite hour international government cut.',
    'email': 'nmorrison@example.net',
    'phone_number': '+1-868-342-4613x37867',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sydney Collins',
    'Dustin Ramsey',
    'Christopher Smith',
    'Karen Vasquez',
    'Cynthia Craig',
    'Timothy Wilson',
    'Gerald Smith',
],
    'json': {
    'name': 'Heidi Griffin',
    'address': '551 Barron Manors Apt. 235\nTranhaven, MN 48509',
},
    'key79692': 'value86224',
    'key73074': 'value58406',
    'key7534': 'value90389',
    'key37512': 'value10567',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Robert Daniel',
    'address': '809 Perez Center\nJeffreyland, ID 64507',
    'text': 'Decade true half majority. Share computer very seem.\nCost benefit benefit father fly realize. Member point study surface other couple.',
    'email': 'richarddunn@example.org',
    'phone_number': '(425)848-4032',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kristopher Walker',
    'Sarah Ramirez',
    'Autumn Burke',
    'Peter Ingram',
    'Anna Murray DVM',
    'Lisa Smith',
    'Jaime Scott',
    'Brandon Kelly',
],
    'json': {
    'name': 'Jeremy Palmer',
    'address': '29120 Wise Street\nWilkinstown, DC 14290',
},
    'key49873': 'value34479',
    'key47555': 'value96819',
    'key23791': 'value75307',
    'key14175': 'value95720',
    'key80517': 'value15410',
    'key74052': 'value34531',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Michael Sanchez',
    'address': '2918 Seth Junctions\nLake Joshuafurt, ND 01626',
    'text': 'Agree condition which look star investment article.\nWhat start trouble kid source. Today eat clear myself west animal among. Ball respond number guy tell nothing north.',
    'email': 'nicholsalexander@example.net',
    'phone_number': '001-284-261-2664x70508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Eugene Porter',
    'Anthony Gordon',
    'Cheryl Davis',
],
    'json': {
    'name': 'Anna Smith',
    'address': '59899 Roth Heights\nKatieshire, IN 33969',
},
    'key41662': 'value74029',
    'key87268': 'value80892',
    'key18241': 'value22578',
    'key85152': 'value66590',
    'key74085': 'value5804',
    'key8564': 'value17810',
    'key92460': 'value5656',
    'key32801': 'value98792',
    'key8941': 'value17504',
    'key7040': 'value70048',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Mary Harris',
    'address': '3014 Graham Crossroad Suite 984\nWest Christineberg, PA 29972',
    'text': 'Season any down attack agency table interview weight. Must support check item consider then.',
    'email': 'amanda42@example.net',
    'phone_number': '(221)252-8584',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Snyder MD',
    'Jennifer Mathis',
    'Jeffrey Mosley',
    'Evelyn Sherman',
    'Carrie Morgan',
],
    'json': {
    'name': 'Emily Patton',
    'address': '0198 Michael Underpass\nMcdowellton, OH 39514',
},
    'key46313': 'value36522',
    'key80169': 'value81013',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'David Peterson',
    'address': '8234 Miranda Harbors\nJohnsonchester, CA 75357',
    'text': 'Air network computer the for media. Tonight Republican politics service. Heavy build lead technology.\nHot enough marriage night. Big technology operation somebody.',
    'email': 'bellgabrielle@example.org',
    'phone_number': '001-893-470-3338',
    'array_int_dynamic': [
    22459,
],
    'array_varchar_dynamic': [
    'Tristan Sandoval',
    'Christy Douglas',
],
    'json': {
    'name': 'Allen Ward',
    'address': '565 Diaz Knolls Suite 388\nBranditown, AL 60050',
},
    'key18410': 'value89570',
    'key97149': 'value42852',
    'key52175': 'value74714',
    'key85874': 'value17336',
    'key21508': 'value40774',
    'key85477': 'value98363',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Travis Willis',
    'address': '778 Kelly Gardens\nPort Anthony, FM 48536',
    'text': 'Behind sit increase guess who. Against guess chair itself gun night thank. Which protect like investment player.',
    'email': 'crawfordpatricia@example.org',
    'phone_number': '+1-677-618-0023x635',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Vazquez',
    'Danny Gonzales',
    'Shannon Jones',
    'Cathy Riddle',
    'Lori Bradley',
    'Kimberly Washington',
    'Sheryl Maddox',
    'Zachary Burns',
],
    'json': {
    'name': 'Jason Kaufman',
    'address': 'Unit 7326 Box 3188\nDPO AE 73077',
},
    'key69312': 'value91837',
    'key7680': 'value96299',
    'key25218': 'value20357',
    'key27920': 'value4505',
    'key4529': 'value9989',
    'key49908': 'value91183',
    'key38546': 'value6503',
    'key7086': 'value8127',
    'key1866': 'value78681',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Valerie Wilson',
    'address': '2758 Hanson Estate\nStevenchester, TN 16044',
    'text': 'Wide issue action entire. Computer professional citizen large material heart.\nFace service end performance. Film conference position allow. Finish conference medical capital.',
    'email': 'harriskatherine@example.net',
    'phone_number': '979.326.4586x981',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Martinez',
    'Sean Conway',
    'Laura Liu',
    'Megan Martinez',
    'Angela Wyatt',
],
    'json': {
    'name': 'Tracey Jones',
    'address': '22279 Elizabeth Shores Suite 740\nStevensshire, MS 72812',
},
    'key17734': 'value22673',
    'key67560': 'value71566',
    'key51926': 'value14322',
    'key22347': 'value32692',
    'key1158': 'value38174',
    'key41776': 'value78414',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Kaitlyn Rios',
    'address': '10068 Henry Parkway Apt. 613\nNorth Colton, MD 03497',
    'text': 'Leader allow yeah very evidence into too. Democratic bed quality interest. Charge later pretty information indeed.\nSea baby skill. View leave wait response.',
    'email': 'oponce@example.net',
    'phone_number': '001-826-531-2917',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kari Norton',
    'Robin Miller',
],
    'json': {
    'name': 'Michael Torres',
    'address': '97849 Thomas Forges Suite 495\nWest Brian, WI 17445',
},
    'key30223': 'value98830',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Randall Martin',
    'address': '50070 Matthew Locks\nRiveraton, WI 91168',
    'text': 'Move responsibility red ball writer nature current. Physical people never street fall control bed.',
    'email': 'maloneamanda@example.com',
    'phone_number': '+1-457-920-9857x1122',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brandy Lucero',
    'Michelle Davis',
    'Matthew Porter',
],
    'json': {
    'name': 'Maria Jones',
    'address': '618 Henry Corner\nEast Andrewmouth, MD 15153',
},
    'key75550': 'value24506',
    'key35156': 'value55754',
    'key40265': 'value96867',
    'key81102': 'value61376',
    'key69775': 'value60688',
    'key13905': 'value49930',
    'key36945': 'value79885',
    'key11651': 'value94402',
    'key54755': 'value36361',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Cheryl Smith',
    'address': '2909 Weaver Greens Apt. 435\nKristenborough, MT 21930',
    'text': 'State course million require. Story remember responsibility church.\nArt term prove car little hit tonight. During after wide red theory value per.',
    'email': 'michaelmiller@example.org',
    'phone_number': '292-584-1460x40304',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Heather Hunt',
    'Megan Stewart',
],
    'json': {
    'name': 'Jennifer Luna',
    'address': '6987 Duncan Road Suite 479\nGarrettport, AK 00864',
},
    'key98250': 'value24015',
    'key33411': 'value8205',
    'key6943': 'value20045',
    'key12803': 'value66035',
    'key93675': 'value25823',
    'key65799': 'value75389',
    'key3666': 'value42378',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Jennifer Andrews',
    'address': '555 Kim Stream\nPort Karen, KY 29268',
    'text': 'Artist air style bill music source card. Dog prevent under as just station. Mean set politics general.\nRelationship property tax before bar quickly. For pass rate entire base no condition.',
    'email': 'gallegosscott@example.org',
    'phone_number': '359.240.3742x87711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Isaac Long',
    'Christina Todd',
    'Steven Reyes',
    'Jonathan Turner',
],
    'json': {
    'name': 'Kirk Medina',
    'address': 'USNS White\nFPO AA 79507',
},
    'key81712': 'value18259',
    'key407': 'value16863',
    'key85398': 'value51548',
    'key71660': 'value46007',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Kim Williams',
    'address': '478 Dylan Fort Suite 368\nAshleyfort, DE 60370',
    'text': 'Professional gas focus man issue actually. Blood cut use per thing in yes high.\nFocus girl purpose hundred. Deal couple structure and where church per pass.',
    'email': 'mckenzienathaniel@example.com',
    'phone_number': '001-464-301-1743',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christine Friedman',
    'Sarah Berry',
    'Stacey Miles',
    'Sara Esparza',
    'Melvin White',
    'Ryan Thompson',
    'Terri Wade',
    'Carla Jennings',
    'Christina Nelson',
    'Ashley Smith',
],
    'json': {
    'name': 'Mariah Wilson',
    'address': '6039 Mcgrath Point Apt. 464\nDaniellebury, RI 56411',
},
    'key51830': 'value34181',
    'key22909': 'value51536',
    'key76623': 'value33127',
    'key45527': 'value17572',
    'key14274': 'value57955',
    'key97178': 'value73786',
    'key43335': 'value57998',
    'key84705': 'value70928',
    'key38411': 'value24980',
    'key17672': 'value2371',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Raymond Walker',
    'address': '80410 Todd Views\nSouth Samanthaview, SC 01463',
    'text': 'Age offer dinner available threat line occur bit. Suddenly technology special wind professional together. Brother among political.',
    'email': 'john37@example.net',
    'phone_number': '(561)534-8508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tina Wright',
    'Lauren Brady',
    'Kelly Lamb',
    'John Taylor',
    'Dominic King',
    'Heather Jones PhD',
    'Zachary Carpenter',
    'Ashley Bernard',
],
    'json': {
    'name': 'Deborah Massey',
    'address': '976 John Rapids Apt. 995\nLake Sylvia, FL 85312',
},
    'key80955': 'value82740',
    'key53464': 'value20341',
    'key33830': 'value40130',
    'key29129': 'value74060',
    'key74750': 'value54564',
    'key64093': 'value13033',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Tammie Smith',
    'address': '50475 Shannon Centers Apt. 789\nNew Jason, NJ 51357',
    'text': 'Box get concern would. Watch stay character.\nParty in nice collection painting space tough. Prepare air build many require administration. Reason race around young you art would that.',
    'email': 'ytorres@example.com',
    'phone_number': '903-654-1504',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Clarke',
    'Jay Benson',
    'Mr. Taylor Morris III',
    'Laura Werner',
    'Jennifer Marshall',
    'Amy Collins',
],
    'json': {
    'name': 'Devin Murphy',
    'address': '730 Thompson Grove Apt. 090\nNorth Brandon, MO 91205',
},
    'key75911': 'value84976',
    'key73207': 'value81083',
    'key96206': 'value56583',
    'key30937': 'value62324',
    'key99306': 'value48265',
    'key32400': 'value11163',
    'key47210': 'value96122',
    'key22034': 'value28978',
    'key90674': 'value92224',
    'key85205': 'value82498',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Andre Franklin',
    'address': '402 Thomas Turnpike\nFosterchester, MH 81899',
    'text': 'Amount event commercial system.\nEnvironment reveal interest claim also nature. Something action court debate marriage green study full.',
    'email': 'patrickshannon@example.com',
    'phone_number': '(275)556-2296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Elliott',
    'David Barrera',
],
    'json': {
    'name': 'Alyssa Johnson',
    'address': 'PSC 9246, Box 8081\nAPO AP 34948',
},
    'key90001': 'value65813',
    'key64933': 'value9051',
    'key17328': 'value46705',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Joel Carter',
    'address': '724 David Isle Apt. 317\nNorth Robertberg, VT 99007',
    'text': 'Industry add culture. Through serve sing try.\nClose ready including success hard off. Beyond set baby election fund star. Rest result plan of someone full. Which smile world push market.',
    'email': 'leephilip@example.net',
    'phone_number': '+1-690-952-0048',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Marshall',
    'April Pham',
],
    'json': {
    'name': 'Kyle Rivera',
    'address': 'USS Mckinney\nFPO AA 67674',
},
    'key17068': 'value89984',
    'key19075': 'value95459',
    'key17533': 'value67514',
    'key9168': 'value59697',
    'key77135': 'value61668',
    'key84261': 'value16015',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Jessica Ramirez',
    'address': '1191 Lloyd Tunnel Apt. 825\nWest Michael, OH 77734',
    'text': 'Difficult identify both. In blood mother gas gun middle how wish.\nRepublican idea of determine able federal as. By star manage parent.',
    'email': 'hscott@example.com',
    'phone_number': '579.800.7542x880',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Coleman',
    'Donald Cummings',
    'Paul Richardson',
    'Yvonne Terrell',
    'Katherine Mullins',
],
    'json': {
    'name': 'Wendy Barrera',
    'address': 'Unit 6308 Box 1261\nDPO AP 90962',
},
    'key833': 'value77587',
    'key83642': 'value7652',
    'key57746': 'value50207',
    'key92464': 'value98229',
    'key81686': 'value85239',
    'key52725': 'value33496',
    'key33225': 'value41324',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Allen Peters',
    'address': '63555 Wilson Summit Apt. 290\nLuisbury, CO 68376',
    'text': 'Just brother tree market above per above. Dinner include indicate good far market gas.\nBudget trial claim item less along laugh. Must international cup fund history network thank. Trade line I.',
    'email': 'charlesevans@example.org',
    'phone_number': '(422)939-0136',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Moore',
    'Sabrina Taylor',
    'Jane Davis',
    'Jose Stout',
    'Melanie Baker',
],
    'json': {
    'name': 'Daniel Alvarez',
    'address': '017 Haney Extension\nAnthonyview, NE 24739',
},
    'key7194': 'value21288',
    'key64018': 'value75355',
    'key15986': 'value88953',
    'key81437': 'value11497',
    'key79539': 'value70606',
    'key53121': 'value38684',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Norman Dawson',
    'address': 'Unit 8545 Box 0404\nDPO AA 73898',
    'text': 'Half old teach question black brother yes mission. Approach couple operation film.',
    'email': 'erica89@example.com',
    'phone_number': '254.456.1852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Martinez',
    'Lisa Wilkins',
    'Victor Jones',
],
    'json': {
    'name': 'Allison Smith',
    'address': 'PSC 3394, Box 3126\nAPO AE 35843',
},
    'key48415': 'value12821',
    'key32703': 'value29583',
    'key85180': 'value18590',
    'key2735': 'value95913',
    'key33896': 'value6301',
    'key41641': 'value41037',
    'key82388': 'value88565',
    'key28119': 'value74360',
    'key32579': 'value84052',
    'key20408': 'value291',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Emily Price',
    'address': '41302 Ashley Tunnel Apt. 287\nSouth Andreaville, ID 19306',
    'text': 'Heart land require two. Herself first company region four. Suddenly Mrs interesting say enough mother official.',
    'email': 'jenniferrobertson@example.com',
    'phone_number': '001-928-963-2868',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Roy',
    'Dr. Steven Simpson PhD',
    'Andrew Henderson',
    'Vanessa Jones',
],
    'json': {
    'name': 'Ashley Rhodes',
    'address': '99527 Joseph Road Suite 451\nCurtisland, MP 03446',
},
    'key68141': 'value74817',
    'key67404': 'value66695',
    'key87994': 'value57023',
    'key91783': 'value39554',
    'key3914': 'value8658',
    'key26914': 'value20212',
    'key80716': 'value1345',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Dean Rivera',
    'address': 'PSC 1903, Box 1114\nAPO AE 25076',
    'text': 'Real top character but. Local light wind left amount. Weight tax tree use.\nFriend big blood seek major prevent among. Thousand drug price government.\nRoad financial call activity one.',
    'email': 'tyler63@example.org',
    'phone_number': '(666)473-3985x449',
    'array_int_dynamic': [
    40806,
],
    'array_varchar_dynamic': [
    'Belinda Small',
    'Thomas Powell',
    'Dennis Mcdonald',
    'Brian Escobar',
],
    'json': {
    'name': 'Dominique Smith',
    'address': '5914 Robert Wall\nNew Julie, MP 77805',
},
    'key26068': 'value38461',
    'key39407': 'value60990',
    'key54882': 'value42481',
    'key15601': 'value47264',
    'key33498': 'value88614',
    'key89095': 'value77348',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'James Mora',
    'address': '5501 Brown Orchard\nLake Tracyland, RI 90386',
    'text': 'It southern toward book company top style. Financial I time. As respond street factor bad. Book where walk be.',
    'email': 'wstevens@example.net',
    'phone_number': '711.647.0478',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Monique Krueger',
    'Ronald Miller',
    'Cheryl Smith',
    'Yvonne Gallagher',
],
    'json': {
    'name': 'John Woodard',
    'address': '799 Cherry Path\nStacystad, WI 17569',
},
    'key21671': 'value20036',
    'key12754': 'value43261',
    'key94369': 'value42649',
    'key70253': 'value65863',
    'key62532': 'value2495',
    'key97148': 'value23096',
    'key37364': 'value82800',
    'key2698': 'value14910',
    'key45259': 'value64086',
    'key33878': 'value48619',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Bryan Gonzalez',
    'address': '37662 Montgomery Turnpike Suite 637\nSouth Christian, MI 91402',
    'text': 'Side door go deal how rule. Beyond movement image interview.\nHow really make important. Huge far player window finally body bring.\nMaybe arm rather direction general this risk.',
    'email': 'michaelleonard@example.com',
    'phone_number': '(510)257-1185',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Roger Hendricks',
    'Jacqueline Kemp',
],
    'json': {
    'name': 'Kelly Cardenas',
    'address': 'Unit 2285 Box 7523\nDPO AE 98917',
},
    'key71829': 'value30677',
    'key59016': 'value45416',
    'key75637': 'value66163',
    'key25034': 'value30793',
    'key48521': 'value58721',
    'key37631': 'value86494',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Christopher Stark',
    'address': '54718 Olivia Curve\nWest Michael, OK 52980',
    'text': 'Decision large fact no his. Add between choice level organization. Different every activity born president.\nEvidence card number hospital major sure music or. Star machine state.',
    'email': 'jared58@example.com',
    'phone_number': '741.560.6988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Marshall',
    'Brandon Cruz',
    'David Conner',
    'Gary Clark',
    'Tamara English',
    'Trevor Mckinney',
    'Hannah Herring',
    'Timothy Sandoval',
    'Joel Rojas',
    'Tara Glover',
],
    'json': {
    'name': 'Christopher Pugh',
    'address': '65939 Laura Track\nNew Crystalbury, MI 09399',
},
    'key45196': 'value43980',
    'key83178': 'value10795',
    'key2317': 'value21873',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Michelle Harris',
    'address': '8344 Haas Alley Suite 903\nEast Jenniferfurt, SC 05713',
    'text': 'Interview say mean look. Question indeed almost threat hundred prepare court. Pm more various within at page. Throughout voice operation own.',
    'email': 'craigregina@example.com',
    'phone_number': '258.669.3498x5204',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Vicki Collins',
    'Holly Mcdaniel',
    'Carla Gonzalez',
    'Dean Long',
    'Theresa Ford',
],
    'json': {
    'name': 'Evelyn Thornton',
    'address': '5650 White Field\nSouth Mirandahaven, RI 97006',
},
    'key38849': 'value79071',
    'key25448': 'value22362',
    'key35706': 'value88729',
    'key23495': 'value85534',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Lisa Ford',
    'address': '05265 Cooper Inlet Apt. 893\nSouth Deborahport, GU 26574',
    'text': 'Improve century direction pick television. His including public nearly its development teach through. Pressure happy sister such.',
    'email': 'simschristine@example.com',
    'phone_number': '2047209551',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Whitney Chambers',
    'Emily Nelson',
    'Kimberly Mitchell',
    'David Kramer',
    'Christopher Ellis',
    'James Richards',
    'Kathryn Wiley',
    'Teresa Serrano',
    'Jennifer Mejia',
],
    'json': {
    'name': 'Ryan Harris',
    'address': '4111 Laura Rest Suite 303\nNew Jacobhaven, KS 54969',
},
    'key52401': 'value12297',
    'key40069': 'value66934',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Jorge Lopez',
    'address': '6461 Crystal Land Apt. 164\nWest Jonathantown, AZ 66869',
    'text': 'Professional until to follow ability nation truth. This drop act address both buy.\nTest southern why senior half. War far PM knowledge second beyond.',
    'email': 'tferguson@example.net',
    'phone_number': '666.789.1401x203',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Julie Wilson',
    'Kathleen Bridges',
    'Melissa Riley',
],
    'json': {
    'name': 'Stephen Mcdonald',
    'address': 'USNV Rivas\nFPO AP 30386',
},
    'key81729': 'value85122',
    'key37184': 'value57338',
    'key49951': 'value75402',
    'key72348': 'value53141',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Jamie Cole',
    'address': 'Unit 2163 Box 7734\nDPO AP 88174',
    'text': 'Figure film about security traditional nearly. Begin something agree pass which item easy.\nThis decide sometimes paper. Beyond appear into unit degree. Law better tax.',
    'email': 'yball@example.net',
    'phone_number': '+1-323-266-2080x693',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Harrington',
    'Nathan Anderson',
    'Tiffany Williams PhD',
    'Ruth Freeman',
    'Lori Wilson',
    'Jessica Gonzalez',
    'Matthew Medina',
    'Eric Barrett',
    'Leroy Brewer',
    'Kathleen Warren',
],
    'json': {
    'name': 'Dr. Dominique Thomas',
    'address': '29860 Sherri Well\nKyleland, CT 39012',
},
    'key99597': 'value18067',
    'key76233': 'value31233',
    'key49104': 'value77770',
    'key46111': 'value96555',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Robin Wiggins',
    'address': '7836 Krista Radial Suite 933\nNorth Richard, IN 81420',
    'text': 'Information simply war professional task base worker any. Seem somebody know seek. Reveal special American teach.\nTechnology your notice price set.',
    'email': 'marissamiller@example.org',
    'phone_number': '(990)208-2221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Ayala',
    'Matthew Moore',
    'Donna Henderson',
    'Carl Banks',
    'Frank Robertson',
    'David Montoya',
],
    'json': {
    'name': 'Adam Barrera',
    'address': '103 Bruce Walk Apt. 874\nNew Scott, NJ 54190',
},
    'key60896': 'value51765',
    'key66024': 'value80538',
    'key86960': 'value61537',
    'key97046': 'value91',
    'key31345': 'value80600',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Stephanie Cooper',
    'address': 'USNV Hebert\nFPO AP 64896',
    'text': 'Special likely girl then. Accept ready pull vote industry best. Teach on decide tend brother book.\nSeveral job be risk away arrive. Create wait international else.',
    'email': 'erodgers@example.org',
    'phone_number': '589-795-4014x1083',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Peters',
    'Andrew Harper',
    'Rebecca Harris',
    'Andre Thomas',
    'Leslie Holloway',
    'Michael Lucas',
    'Angela Lewis',
    'Austin Hobbs',
    'Melissa Ford',
    'Justin Jackson',
],
    'json': {
    'name': 'Gabrielle Moss',
    'address': '4019 Jones Plains Apt. 513\nKristinafurt, PR 73276',
},
    'key50287': 'value15142',
    'key10165': 'value62224',
    'key28997': 'value54159',
    'key66251': 'value10085',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Krystal Morgan',
    'address': '7022 Michael Groves\nGarciaburgh, VT 52007',
    'text': 'Task international herself media sing eight. Couple nearly service ok move method safe.\nWhite than decision simple more real. Race century must face yourself study. Cost himself raise kind.',
    'email': 'moniquemiller@example.org',
    'phone_number': '001-471-406-7636x439',
    'array_int_dynamic': [
    6320,
],
    'array_varchar_dynamic': [
    'Renee Schultz',
    'Cody Rogers',
    'Rebecca Campbell',
],
    'json': {
    'name': 'Glenda Pacheco',
    'address': '96662 Hess Ways\nWest Jessicatown, AL 17643',
},
    'key42984': 'value74829',
    'key65720': 'value84150',
    'key71021': 'value82405',
    'key19239': 'value52646',
    'key71343': 'value96363',
    'key35079': 'value50763',
    'key87496': 'value52095',
    'key17606': 'value50270',
    'key88483': 'value31044',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Justin Todd',
    'address': '4306 Perez Dale\nSouth Michellefort, FM 62892',
    'text': 'For themselves wall nation serve participant. Teach that relate trouble partner court international. Sign fund million happen ago individual.',
    'email': 'ramosjessica@example.org',
    'phone_number': '331.227.9842x940',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Edwards DDS',
    'Amy Gross',
    'Joseph Jones',
    'Amanda Palmer',
    'Brian Gonzalez',
    'Mary Chavez',
    'Alexander Young',
    'Daniel Allison',
    'Brandy Baker',
],
    'json': {
    'name': 'Patricia Mueller',
    'address': '6595 Denise Stravenue Apt. 817\nJacquelinefurt, WY 16058',
},
    'key39341': 'value53438',
    'key8027': 'value7628',
    'key92128': 'value12734',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Cheryl Petersen',
    'address': '469 Stephanie Oval Suite 624\nNorth Jamesburgh, IN 19623',
    'text': 'Too public more. Fine amount keep before quite along general. Million indicate into meeting interest mind entire.\nArrive moment more anyone pretty matter account. Child though there else method.',
    'email': 'holly32@example.com',
    'phone_number': '544.412.8279x5841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Giles',
    'Stacey Strickland',
    'Kevin Bowers',
    'Susan Sullivan',
    'Heather Parks',
    'Jimmy King',
],
    'json': {
    'name': 'Angela Barrett',
    'address': '59722 Harrison Circle\nHammondchester, IN 01752',
},
    'key49858': 'value49788',
    'key8924': 'value57828',
    'key6621': 'value17272',
    'key36336': 'value82898',
    'key84796': 'value81754',
    'key21907': 'value27801',
    'key93734': 'value40110',
    'key93423': 'value18202',
    'key79657': 'value37541',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Kirk Dillon',
    'address': '36770 Arroyo Shores Apt. 042\nJoshuamouth, CT 57725',
    'text': 'Wrong provide century figure coach stand occur back.\nIf run particular plant add. Live late student. Hit use building success write.',
    'email': 'robinmacdonald@example.net',
    'phone_number': '+1-824-815-3752x014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michael Smith',
    'Laura Fischer',
    'Kirk Hill',
    'Rachel Leblanc',
    'David Cole',
],
    'json': {
    'name': 'Ryan Aguilar',
    'address': '90212 Williams Island Suite 338\nSouth Alyssaberg, NH 01367',
},
    'key63825': 'value56206',
    'key64150': 'value1885',
    'key59170': 'value74591',
    'key48047': 'value85783',
    'key13403': 'value3166',
    'key93060': 'value80780',
    'key90069': 'value26763',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Justin Kelley',
    'address': '5783 Karen Trace\nWilliamsstad, KS 12964',
    'text': 'Tonight once drop where store. Some beyond beautiful nor allow wait development.',
    'email': 'christypitts@example.net',
    'phone_number': '(787)338-3268x54472',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jesus May MD',
    'Terry Stone',
],
    'json': {
    'name': 'Joel Hubbard',
    'address': '2526 Derek Court\nPort Zacharymouth, AR 42050',
},
    'key3592': 'value82999',
    'key36763': 'value30977',
    'key76197': 'value3116',
    'key6532': 'value86347',
    'key29048': 'value8601',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Mr. Mark Cole MD',
    'address': '1689 Christine Burg Apt. 485\nSouth Jacqueline, WY 16651',
    'text': 'Pm outside easy human. Respond four couple produce standard all song upon.',
    'email': 'pyang@example.net',
    'phone_number': '271.433.9284x9497',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Harold Elliott',
    'Veronica Johnson',
    'Kelly Bailey',
],
    'json': {
    'name': 'Jennifer Martinez',
    'address': '02751 Sharon Lodge Suite 226\nNorth Donaldstad, MH 03917',
},
    'key22169': 'value63198',
    'key53312': 'value29977',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Aaron Wolfe',
    'address': 'Unit 1535 Box 4249\nDPO AE 27104',
    'text': 'On local watch avoid sell friend north.\nPersonal must business key too. Size more how though.',
    'email': 'marcuscosta@example.org',
    'phone_number': '592.217.2550',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Nicholas Wright Jr.',
    'Kimberly Castillo',
    'Sherry Johnson',
],
    'json': {
    'name': 'Stephanie Olson',
    'address': 'Unit 7287 Box 9839\nDPO AE 80791',
},
    'key6296': 'value69183',
    'key23828': 'value44955',
    'key33335': 'value77322',
    'key40623': 'value55636',
    'key8952': 'value97746',
    'key3393': 'value38134',
    'key14820': 'value52284',
    'key69140': 'value79195',
    'key20241': 'value65691',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Benjamin Juarez',
    'address': '247 Annette Forges\nPort Cassandratown, SD 99143',
    'text': 'Heavy receive approach number entire Mr. Thought international recognize country.',
    'email': 'colleen39@example.net',
    'phone_number': '(948)492-1762x103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Gary Smith',
    'Kathy Chen',
    'Karla Brown',
    'Elizabeth Anderson',
    'Tracy Johnson',
    'Joseph Flores',
    'Nicholas Powers',
    'Donald Lang',
    'Ashley Singh',
],
    'json': {
    'name': 'Lauren Watkins',
    'address': '04908 Jeffery Brook Suite 391\nSouth Leslieland, NC 81839',
},
    'key32662': 'value46351',
    'key41570': 'value49394',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Jesse Roberts',
    'address': '6326 Baker Corners\nWest Mark, RI 02103',
    'text': 'Meet break what last blue. Nothing rate question investment agreement. Weight forget senior like.\nHuman few meet or gun financial pattern far. Record out strategy who.',
    'email': 'alyssabarnett@example.com',
    'phone_number': '+1-221-430-7276x17051',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Miss Sandra Hernandez',
    'Mary Flynn',
    'Michele Griffin',
    'Alex Green',
],
    'json': {
    'name': 'Samantha Moore',
    'address': '16943 Emily Neck\nSouth Justinbury, PW 40312',
},
    'key41398': 'value39505',
    'key97504': 'value13694',
    'key39410': 'value36945',
    'key70832': 'value88334',
    'key81191': 'value98813',
    'key6465': 'value8660',
    'key4864': 'value35455',
    'key71112': 'value11003',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Louis Roberts',
    'address': '395 Harris Viaduct Apt. 422\nNew Heidi, MN 40427',
    'text': 'Himself these really design thousand. Enough Democrat institution capital. Realize true nation time his investment fact.\nGood wife whatever performance money project. World song TV thing issue.',
    'email': 'lisaray@example.net',
    'phone_number': '2153547986',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Randall Nash',
    'Teresa Patrick',
    'Kathleen Peters',
    'Amanda Gordon',
    'Linda Davis',
    'Daniel Jones',
    'Dustin Zavala',
    'Christine Hunter',
    'Stacey Mcgee',
],
    'json': {
    'name': 'April Howard',
    'address': '37504 Thomas Club Apt. 953\nPort James, CT 76989',
},
    'key44249': 'value78408',
    'key80865': 'value46273',
    'key83133': 'value16421',
    'key11424': 'value29997',
    'key81050': 'value97697',
    'key84039': 'value1418',
    'key40283': 'value7334',
    'key7140': 'value48359',
    'key15910': 'value762',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Katherine Stevens',
    'address': '746 Ryan Pass Suite 064\nRyanfurt, VT 83504',
    'text': 'Community happen fly something without success different. Require ability visit. Strong to myself note first nearly us deal.',
    'email': 'harrislisa@example.net',
    'phone_number': '001-890-305-2163x66781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Taylor',
    'Catherine Camacho',
    'Chad Lee',
    'Robert Young',
    'Kimberly Mitchell',
    'Tyler Brown',
    'Jane Brown',
    'Kenneth Wagner',
],
    'json': {
    'name': 'Jose Dunlap',
    'address': '624 Brittney Dam\nSouth Robertatown, VT 69890',
},
    'key13246': 'value18539',
    'key56636': 'value74908',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Gina Cortez',
    'address': '358 Danielle Shores Apt. 253\nNorth George, PW 19725',
    'text': 'Plan off stop some and business. Doctor paper camera grow movie call feeling thank.\nScience board situation spend behavior worry. Table nice concern herself save speak. Have they oil fine four.',
    'email': 'pamelareid@example.org',
    'phone_number': '6317945908',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Ray',
    'Thomas Henderson',
    'Sandra Arnold',
    'Jason Wells',
    'Amanda Barrera',
    'Dean Bender',
    'Natalie Young',
    'Sarah Ramirez',
    'Katherine Larsen',
    'Mark Johnson',
],
    'json': {
    'name': 'Allen Rodriguez',
    'address': '6083 Heather Station\nGarciaburgh, RI 92854',
},
    'key48832': 'value94380',
    'key59520': 'value56391',
    'key47777': 'value44100',
    'key9652': 'value90187',
    'key56674': 'value67076',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Michael Ponce',
    'address': '105 Lucas Skyway Suite 437\nPort Jeremyville, OH 03535',
    'text': 'Understand whom body money her.\nMedical seat might. Citizen mother arm important network whom account.\nTend least second for computer race. Quickly manage fine suffer.',
    'email': 'reedcathy@example.net',
    'phone_number': '961.534.5036x2125',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Katelyn Johnson',
    'Victor Lawson',
    'Barbara Johnson',
    'Lori Wang',
    'Jessica Johnson',
    'Robert Turner',
    'Vincent Potter',
    'Christy Chen',
    'Miss Vicki Wilson DDS',
    'John Lucero',
],
    'json': {
    'name': 'Garrett Collins',
    'address': '233 Watson Ports Apt. 866\nCarrilloborough, NV 20070',
},
    'key74663': 'value22672',
    'key47371': 'value46655',
    'key38372': 'value96348',
    'key63915': 'value14841',
    'key63054': 'value61719',
    'key64628': 'value43965',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Adrian Gross',
    'address': '3772 Maxwell Crest\nPort Maria, AZ 58281',
    'text': 'Talk strong father human.\nNo treat whom growth western walk. Radio past detail green expert seek. Structure bar morning beautiful. Mind rate away under behind leader join.',
    'email': 'anthonywoods@example.com',
    'phone_number': '001-628-869-8331x4348',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Walker',
    'Tina Garcia',
    'Robert Boyd',
],
    'json': {
    'name': 'Jason Williams',
    'address': 'PSC 3846, Box 4497\nAPO AP 55510',
},
    'key75959': 'value1801',
    'key89362': 'value5240',
    'key61449': 'value27513',
    'key51630': 'value13345',
    'key33598': 'value84369',
    'key20867': 'value92490',
    'key31530': 'value54969',
    'key15070': 'value78788',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'John Walton',
    'address': '10288 Romero Highway Suite 304\nNorth Kristy, NY 15898',
    'text': 'Agency political need.\nStop over cost last happen. Huge treatment institution explain speak thing.',
    'email': 'hunter29@example.org',
    'phone_number': '+1-420-795-6697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Dennis',
    'Anna Shepherd',
    'Nicholas King',
    'Joseph Monroe',
    'Amber Hoffman',
    'Melinda Wheeler',
],
    'json': {
    'name': 'Kathy Copeland',
    'address': '46526 Hart Cape Suite 182\nGrahamchester, IA 48432',
},
    'key31737': 'value43021',
    'key32024': 'value96406',
    'key50288': 'value70767',
    'key99900': 'value13456',
    'key63974': 'value64305',
    'key30214': 'value51493',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Jermaine Martinez',
    'address': '39654 James Walk\nLake Yvonne, VT 31349',
    'text': 'Very area soon happen. Type resource represent. He white own compare option.\nClass score social morning what. Girl level close reality be administration war. Character outside quality family stay.',
    'email': 'mariareyes@example.net',
    'phone_number': '+1-712-735-9873x005',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brian Meyers',
    'Chelsea Johnson',
],
    'json': {
    'name': 'Sharon Wang',
    'address': '144 Noble Spring\nFreemanbury, NM 65659',
},
    'key2611': 'value87974',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Joseph Brown',
    'address': 'PSC 7555, Box 5665\nAPO AA 92407',
    'text': 'Case purpose style rest during instead list. Treat kid prevent open base bag analysis recently. Adult sit PM.',
    'email': 'theresa35@example.org',
    'phone_number': '259-786-5476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Leonard',
    'Nancy Caldwell',
    'Michael Watson',
    'Mrs. Erin Alvarado',
    'Jared Gutierrez',
    'Matthew Pierce',
],
    'json': {
    'name': 'Pamela Grimes',
    'address': '889 Heather Dale Apt. 418\nChristopherport, NH 83560',
},
    'key71719': 'value49865',
    'key26264': 'value38974',
    'key32403': 'value76461',
    'key76379': 'value5526',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Andrea Gill',
    'address': '7473 Kathleen Isle\nBowersside, TX 75434',
    'text': 'Have view authority reality decision see then. Same toward bill technology set.',
    'email': 'blackdaniel@example.net',
    'phone_number': '001-241-623-1068x3370',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kathy Scott',
    'Stephanie Monroe',
    'Cheryl Oconnell',
    'Darius Jimenez',
    'Christopher Bradley',
    'Kevin Combs',
    'Diana Phillips',
],
    'json': {
    'name': 'Brian Bailey',
    'address': '7168 Powers Field Suite 104\nShannonville, FL 19787',
},
    'key11483': 'value28451',
    'key77363': 'value36498',
    'key30039': 'value633',
    'key12967': 'value84969',
    'key30293': 'value50249',
    'key16283': 'value24292',
    'key28942': 'value87080',
    'key59810': 'value36837',
    'key70556': 'value3713',
    'key93994': 'value57189',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Michelle Burton',
    'address': 'USNS Mueller\nFPO AA 60826',
    'text': 'Practice probably how himself spring business recent call. Far energy law. Water each his language chair able reveal.',
    'email': 'nathanbowers@example.com',
    'phone_number': '+1-536-999-8110x34012',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Glen Powell',
    'Kayla Golden',
    'David Rodriguez',
    'Charles Peterson',
],
    'json': {
    'name': 'John Tran',
    'address': '793 Maureen Street Suite 288\nOrozcostad, PW 39626',
},
    'key19170': 'value72767',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Jason Huffman',
    'address': '82404 Alexis Manors Apt. 984\nWest Scottside, NM 51239',
    'text': 'Focus consider hit drive whole reality soldier design. Rather carry lot school. Civil change beat star value glass season role.\nAuthor huge sometimes prevent. Have between stop growth read offer cup.',
    'email': 'abrown@example.net',
    'phone_number': '(663)225-2523',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Darius Hernandez',
    'Samuel Barker',
    'Austin Colon',
    'Paul Henderson',
    'Micheal Taylor',
    'Michael Larsen',
    'Sandra Hancock',
    'Jasmin Spence',
    'Andrew Haynes',
    'Victoria Odonnell',
],
    'json': {
    'name': 'Andrew Walker',
    'address': '4602 Caitlin Cape Suite 907\nScotthaven, SD 60465',
},
    'key12100': 'value29928',
    'key89463': 'value61853',
    'key27961': 'value68830',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Bruce Thomas',
    'address': '76343 Hansen Squares Suite 541\nWest Michelle, FM 51013',
    'text': 'Per public else. Government head player own among. Trip wife general century year I reach.',
    'email': 'alyssa06@example.com',
    'phone_number': '(216)563-3199x530',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dustin Jones',
    'Adrian Lutz',
    'Brittany Golden',
    'Gerald Faulkner',
    'Xavier Barnes',
    'Shari Powell',
    'Regina Mitchell',
    'Carolyn Roberts',
],
    'json': {
    'name': 'Amy Sanders',
    'address': '03256 Mckinney Shoal Apt. 212\nNorth Jenniferbury, AZ 90289',
},
    'key51377': 'value32038',
    'key56224': 'value81381',
    'key72469': 'value11235',
    'key53192': 'value68022',
    'key74219': 'value35351',
    'key66581': 'value83220',
    'key10243': 'value67917',
    'key9957': 'value9284',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Jennifer Wilkins',
    'address': '66136 Butler Junctions Apt. 682\nLake Angelburgh, MP 40842',
    'text': 'Media official wear. Might watch experience less order mention skill.',
    'email': 'pcohen@example.com',
    'phone_number': '289-926-2516x28410',
    'array_int_dynamic': [
    22805,
],
    'array_varchar_dynamic': [
    'Ray Armstrong',
    'Laura Weber',
    'Shannon Moore',
    'Martin Hall',
    'Lisa Golden',
    'Michael Saunders',
    'Lauren Downs',
    'Melanie Brown',
    'Michael Jackson',
    'Melissa Thomas',
],
    'json': {
    'name': 'Megan Rodriguez',
    'address': '90454 Peters Flat Suite 684\nHollandville, MO 43366',
},
    'key11710': 'value27123',
    'key55136': 'value61533',
    'key39343': 'value73353',
    'key4492': 'value20442',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Charles Cabrera',
    'address': '9910 Williams Loaf Apt. 307\nChristopherborough, PW 71108',
    'text': 'Break technology produce senior. Senior consider back human throughout.\nArgue view provide trip join party health. Break meet out media price size watch.',
    'email': 'beltranmary@example.com',
    'phone_number': '001-705-313-1201',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Johnathan Rivas',
    'Lisa Robertson',
    'Autumn Nichols',
    'David Pham',
    'Robert Walters',
    'Anita Robinson',
    'Darren Hart',
    'Jo Benson',
    'Miss Jessica Carpenter MD',
    'Mitchell Suarez',
],
    'json': {
    'name': 'Jonathan Adams',
    'address': '05283 White Well Apt. 099\nKennedymouth, AS 01653',
},
    'key29590': 'value99634',
    'key61676': 'value81364',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Christina Crawford',
    'address': '6180 Carter Harbor\nLake Kelly, DC 00683',
    'text': 'Yet hear early thus provide dog situation. Conference per smile base eye exactly that. Place both analysis this better him human.',
    'email': 'christine21@example.com',
    'phone_number': '+1-992-857-0491x5172',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'George Andrews',
],
    'json': {
    'name': 'James Palmer',
    'address': 'PSC 2612, Box 1620\nAPO AA 38968',
},
    'key68829': 'value22913',
    'key20698': 'value99207',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'James Hernandez',
    'address': '3509 Wagner Key Apt. 477\nPort Crystal, CT 52413',
    'text': 'Control drive southern if nation my capital. Traditional test rule ground fund. All adult present sound into or special.\nDifferent foreign pull camera. Box control those lay election know.',
    'email': 'atkinsondavid@example.com',
    'phone_number': '5423710520',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Howell',
    'Whitney Smith',
],
    'json': {
    'name': 'Andrea Wagner',
    'address': '894 Barajas Ranch\nEast Alejandro, ND 47553',
},
    'key99509': 'value98186',
    'key47008': 'value1359',
    'key91608': 'value74421',
    'key26460': 'value69683',
    'key21723': 'value4856',
    'key3165': 'value40756',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Jose White',
    'address': '4764 Beck Summit Apt. 842\nSouth Lisa, MI 57740',
    'text': 'Wrong few suffer law occur base walk.\nCheck century time religious him assume your. Consider bar agree appear effect mother sense draw.',
    'email': 'marcus67@example.org',
    'phone_number': '247.229.8528x6930',
    'array_int_dynamic': [
    57433,
],
    'array_varchar_dynamic': [
    'Michael Anderson',
    'Katherine Weaver',
],
    'json': {
    'name': 'Dawn Wilkins',
    'address': '9759 Chad Neck Apt. 928\nChristinaland, KS 42455',
},
    'key95657': 'value47120',
    'key93558': 'value24019',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Matthew Gutierrez',
    'address': '1813 Johnson Crossing\nLake Emilyland, LA 18798',
    'text': 'Personal country commercial child might stock. High we control site newspaper since hour.',
    'email': 'roberta17@example.net',
    'phone_number': '280.233.5252x33694',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Wolf',
    'Michael Morris',
    'Justin Huber',
    'Wendy Moore',
    'Melissa Boone',
    'Marcus Sanchez',
    'Janet Lozano',
    'Erik Gibbs',
],
    'json': {
    'name': 'Grant Dyer',
    'address': '843 Michael Village\nBrandibury, WI 15150',
},
    'key92261': 'value1809',
    'key27779': 'value60031',
    'key23564': 'value66042',
    'key96646': 'value44397',
    'key90317': 'value65071',
    'key35073': 'value43898',
    'key14132': 'value55207',
    'key4553': 'value8143',
    'key58573': 'value90651',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Adam Allen',
    'address': '12702 John Lodge Apt. 140\nNew Rhondachester, SC 18531',
    'text': 'War simply take style. Ten seat experience.\nShare call court surface draw often wait. Involve task whatever experience. Commercial plan computer usually artist less bill.',
    'email': 'laurasmith@example.com',
    'phone_number': '(329)935-1426x9884',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tracey Garcia',
],
    'json': {
    'name': 'Sara Gates',
    'address': '107 White Passage\nElizabethfurt, WV 11027',
},
    'key80366': 'value25479',
    'key7555': 'value88512',
    'key19015': 'value64651',
    'key80671': 'value48811',
    'key28680': 'value73598',
    'key86132': 'value92939',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Christine Smith',
    'address': '10994 Sweeney Unions\nNew Jonathanside, AL 29658',
    'text': 'Various economy figure own them drug between. Put bit mother letter. Work reality soon project recently avoid size.\nCivil into your however foot conference recognize. Reach material oil economy.',
    'email': 'mfoley@example.org',
    'phone_number': '+1-317-960-7723x7386',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Fields',
    'Rhonda Thompson DDS',
    'Ruben Johnson',
    'Dominic Nielsen',
    'Matthew Eaton',
    'Shari Larsen',
    'Anthony Wheeler',
    'Nicholas Foster',
    'Heather Lewis',
    'Melissa Stewart',
],
    'json': {
    'name': 'Brandon Smith',
    'address': '98215 Mccarthy Roads\nNew Robert, ID 00766',
},
    'key86003': 'value31912',
    'key58212': 'value9960',
    'key30564': 'value23967',
    'key91265': 'value85253',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Joseph Keith',
    'address': '38320 Coffey Course\nNew Jesse, CT 07250',
    'text': 'Bank worry four strong share than step. Service physical indeed play. Crime item tough tell.\nUnder address hundred care agency hot Congress. Simply but present seat.',
    'email': 'candrews@example.org',
    'phone_number': '(810)994-7909x9064',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Katie Watkins',
    'Emma Gomez',
    'Jacqueline James',
    'Kimberly Bennett',
    'Kathy Schmidt',
    'Dustin Hernandez',
    'Mr. Michael Johnson',
    'Mrs. Julie Roy',
    'David Villarreal',
],
    'json': {
    'name': 'Samuel Hall',
    'address': '022 Heather Plains\nMariochester, PA 46727',
},
    'key35364': 'value54073',
    'key40099': 'value32072',
    'key43867': 'value25332',
    'key6387': 'value73592',
    'key2866': 'value25931',
    'key99251': 'value92538',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Donald Medina',
    'address': '31963 Patricia Fords\nMurphyfurt, IA 72182',
    'text': 'Player move next low a Democrat. Share price happen customer while.\nNotice nature executive never. Discover feeling population hit.',
    'email': 'leecrystal@example.net',
    'phone_number': '872-493-1272',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Monique Lowe',
    'Tony Owens',
    'Christopher Haas',
    'James Maynard',
    'Courtney Smith',
    'Janice Ingram',
],
    'json': {
    'name': 'Michele Young',
    'address': 'USNS Ortega\nFPO AA 80150',
},
    'key50787': 'value46561',
    'key67372': 'value17833',
    'key91608': 'value67262',
    'key56376': 'value82766',
    'key47319': 'value25175',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'James Russell',
    'address': '71350 Thomas Trail Apt. 745\nEast Cherylmouth, TN 25116',
    'text': 'Physical house in value. Organization blue blood something detail draw. Who forward heart meet others shoulder history.',
    'email': 'bsmith@example.org',
    'phone_number': '810-249-3434x27254',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Wilson',
    'Jonathan Davenport',
    'Heather Frye',
    'Kevin Munoz',
    'Frank Barnes',
    'John Sheppard',
    'Ashley Simpson',
    'Jonathon Mullen',
    'Terry Dickerson',
],
    'json': {
    'name': 'Johnathan Lewis',
    'address': '98200 Steve Wall Apt. 938\nAmberport, NM 22342',
},
    'key55415': 'value69515',
    'key45435': 'value19878',
    'key57740': 'value89373',
    'key11855': 'value49541',
    'key47003': 'value22407',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Patricia Alvarez',
    'address': '43134 Blake Vista Apt. 041\nBrittneyport, FL 77300',
    'text': 'Fall her others seem. Generation against economy north lay page. Method its product agency board.\nLast concern southern mouth cost director perhaps. Music leave list man whom just.',
    'email': 'lijohnny@example.net',
    'phone_number': '368.749.4579',
    'array_int_dynamic': [
    88698,
],
    'array_varchar_dynamic': [
    'Russell Silva',
    'Mike Brown',
    'Ricardo Gilbert',
    'Kevin Moreno',
],
    'json': {
    'name': 'Mrs. Sarah Hubbard',
    'address': '935 White Stream Suite 317\nDebbieborough, TX 44736',
},
    'key66869': 'value83886',
    'key495': 'value70834',
    'key87683': 'value33247',
    'key78429': 'value91431',
    'key24448': 'value84650',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Allison Charles',
    'address': '88759 Noah Stravenue Suite 653\nLake Christine, ME 74781',
    'text': 'Something down prove determine painting.\nDetail number support painting. Someone tend anything hand region too.',
    'email': 'shawjose@example.net',
    'phone_number': '638-841-2002x076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'John Jones',
],
    'json': {
    'name': 'Debra Gonzalez',
    'address': '362 Perkins Wall\nSouth Shannontown, MT 97754',
},
    'key53080': 'value69556',
    'key15672': 'value96895',
    'key3336': 'value58811',
    'key43109': 'value94847',
    'key78812': 'value74189',
    'key17150': 'value94317',
    'key93891': 'value14208',
    'key57652': 'value1863',
    'key72665': 'value53045',
    'key20850': 'value37210',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Eileen Richmond',
    'address': 'PSC 7875, Box 8343\nAPO AP 34906',
    'text': 'Fill hand middle finish shoulder behind. Soldier deep election friend.\nBed lay hotel argue night site rather. Factor author loss. View understand once.',
    'email': 'joshuakim@example.net',
    'phone_number': '001-866-433-2538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'James Porter',
    'Bianca Brown',
],
    'json': {
    'name': 'Mia Dawson',
    'address': '438 Smith Harbors\nJameshaven, NH 03810',
},
    'key3947': 'value88660',
    'key76261': 'value33488',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Matthew Neal',
    'address': '99361 Moran Union Suite 953\nKellyfurt, CA 65730',
    'text': 'Parent agency piece southern. Surface stuff teacher four every wait despite. Card cover call order require.',
    'email': 'holmesdonna@example.net',
    'phone_number': '+1-909-762-3124x456',
    'array_int_dynamic': [
    92775,
],
    'array_varchar_dynamic': [
    'Rachel Jordan',
    'Daniel Harris',
    'Leslie Newman',
    'Rhonda Cantrell',
    'Stephanie Rivera',
    'Nathan Smith',
    'Michael Allen',
],
    'json': {
    'name': 'Karen Johnson',
    'address': '2410 Barnes Hill Apt. 711\nHarryton, SC 94786',
},
    'key84701': 'value28131',
    'key66698': 'value58226',
    'key87832': 'value57867',
    'key85409': 'value18929',
    'key608': 'value12874',
    'key64314': 'value64605',
    'key74844': 'value87019',
    'key14526': 'value16249',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Amanda Stevens',
    'address': '37824 Michelle Via Suite 907\nSophiafurt, DC 95410',
    'text': 'Time window lose writer. Region when space participant always benefit his.\nFly either court. Bit eight great care performance oil. Thing local wrong.',
    'email': 'kwashington@example.org',
    'phone_number': '+1-850-831-4570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Schultz',
],
    'json': {
    'name': 'Jason Richardson',
    'address': '420 Wagner Radial\nEllischester, CA 34554',
},
    'key44745': 'value80231',
    'key89261': 'value56064',
    'key5276': 'value79099',
    'key27919': 'value61972',
    'key51214': 'value43085',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Ebony Schmidt',
    'address': '004 Matthews Shoal Suite 817\nLake Patrickberg, KS 04150',
    'text': 'Public sometimes strategy order everything trouble reflect look. Leave ever time open detail produce accept bill. Modern land room read.',
    'email': 'melissaanderson@example.org',
    'phone_number': '(632)840-0545x4496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Morris',
    'Christopher Hill PhD',
    'Alicia Chung',
    'Amanda King',
    'Darlene Edwards',
    'Elizabeth Green',
    'Dr. Mary Rodriguez',
    'Bryan Owens',
],
    'json': {
    'name': 'Joshua Garcia',
    'address': '1252 Jimenez Forge\nSinghville, CA 62623',
},
    'key5245': 'value21655',
    'key3258': 'value42201',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Todd Collier',
    'address': '0500 Angela Drive\nJamesstad, NV 74430',
    'text': 'Rich ready against home event industry without message. Learn participant be factor. Music north ask end decade. Mr little black.',
    'email': 'teresachan@example.org',
    'phone_number': '4275385921',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Barbara White',
    'Danielle Fuentes',
    'Tanya Baker',
],
    'json': {
    'name': 'Mr. Michael Gibson',
    'address': '27812 Diana Falls Suite 397\nWest Aaronville, MA 41202',
},
    'key90410': 'value34331',
    'key1508': 'value99287',
    'key51537': 'value22173',
    'key3262': 'value44764',
    'key37314': 'value39947',
    'key36361': 'value38864',
    'key61808': 'value16997',
    'key52694': 'value8154',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Jose Austin',
    'address': '01775 Alicia Skyway Apt. 118\nJonathanport, HI 83064',
    'text': 'Issue our theory under kid trial. Fear policy example you. Range above ten central.',
    'email': 'nathanielmckinney@example.org',
    'phone_number': '(653)547-8981x0113',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Darrell Ray',
    'Bruce Hodges',
    'Jennifer Montgomery',
    'Robin Hernandez',
],
    'json': {
    'name': 'Kimberly Robinson',
    'address': '734 Christy Lake\nCantuberg, ND 01838',
},
    'key67803': 'value9365',
    'key79825': 'value55',
    'key23581': 'value45671',
    'key77583': 'value27410',
    'key38761': 'value19854',
    'key22813': 'value73719',
    'key94789': 'value66236',
    'key92437': 'value96553',
    'key72271': 'value80225',
    'key70615': 'value2021',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Ashley Cortez',
    'address': '59443 Trujillo Spurs\nConradville, OK 12607',
    'text': 'Many evening much building their season. Early rise employee suggest suffer.\nMan foot upon matter hope cell blood person. Sea oil herself. Rule dog both program.',
    'email': 'hunterkaitlyn@example.com',
    'phone_number': '+1-983-501-4882',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Richard Espinoza',
    'Laura Morgan',
    'Cassie Hudson MD',
    'Denise Mann',
    'Mackenzie Gibson',
    'Crystal Wiggins',
    'Jennifer Marshall',
    'Gerald Long',
    'Sheila Green',
],
    'json': {
    'name': 'Joyce Jennings',
    'address': '187 Diana Way\nPort Jasonchester, WY 14000',
},
    'key24026': 'value81730',
    'key88811': 'value24319',
    'key40930': 'value29300',
    'key76733': 'value4317',
    'key18381': 'value90889',
    'key25029': 'value16490',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Derek Johnson',
    'address': '42065 Montes Mountains Suite 483\nNorth Scottshire, LA 86250',
    'text': 'Purpose senior will style most contain. Sell certain idea actually friend. Night receive street dream three day.',
    'email': 'williambranch@example.net',
    'phone_number': '249.414.5212x65761',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jason Turner',
    'Erin King',
],
    'json': {
    'name': 'Patricia Buchanan',
    'address': '10831 Claudia Turnpike Suite 466\nLake Anthony, IN 57493',
},
    'key54418': 'value41183',
    'key18146': 'value21542',
    'key75829': 'value11639',
    'key84076': 'value72656',
    'key65351': 'value80464',
    'key95763': 'value14339',
    'key81623': 'value97408',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Michael Richardson',
    'address': '2255 Lindsey Key Suite 609\nTheresaside, NY 00913',
    'text': 'Oil front include dream official. Good training than it they change church. A than opportunity wife call sound vote.',
    'email': 'elizabeth16@example.net',
    'phone_number': '902-552-9348x7923',
    'array_int_dynamic': [
    77016,
],
    'array_varchar_dynamic': [
    'Michael Howard',
    'John Banks',
    'James Jackson',
    'John Scott',
    'Peter Franco',
],
    'json': {
    'name': 'Jamie Hansen',
    'address': '1831 Tiffany Forge Suite 965\nPort Matthew, PA 81720',
},
    'key86110': 'value16990',
    'key56835': 'value75560',
    'key6264': 'value98693',
    'key76396': 'value6973',
    'key56366': 'value42804',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Dr. Catherine Graham MD',
    'address': '83615 Regina Vista Suite 351\nEast Karen, MH 19730',
    'text': 'Hour commercial perhaps. Federal win by. Else control write chair.\nWorry shoulder country shoulder. Thing good happen cell. Experience special rise movement exactly dark movement.',
    'email': 'joshuagarcia@example.net',
    'phone_number': '+1-819-614-9998x275',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Davidson',
    'Megan Rivera',
    'Michelle Black',
    'Jessica Booth',
    'Stephen Fuller',
    'Cody Lee',
    'Brian Oliver',
    'Jonathan Hill',
    'Maxwell Thomas',
    'Christina Stewart',
],
    'json': {
    'name': 'Daniel Burnett',
    'address': '832 Ferguson Lakes\nSouth Scottland, OK 11934',
},
    'key1988': 'value14124',
    'key34368': 'value57001',
    'key25135': 'value88174',
    'key90571': 'value58712',
    'key83662': 'value69150',
    'key80404': 'value7381',
    'key65493': 'value79538',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Joseph White',
    'address': '9403 Sarah Extensions\nWest Shannonview, TX 51955',
    'text': 'Only until away serious thing think manager. Energy subject six product who citizen.\nContinue everything resource reflect. Out read bed benefit professional.\nThat front floor base event forward.',
    'email': 'villegaschristina@example.com',
    'phone_number': '6276372698',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Simon',
    'Alicia Campbell',
    'Kenneth Rice',
    'Nicholas Becker',
    'Tina Harrison',
],
    'json': {
    'name': 'Melissa Wall',
    'address': '756 Baldwin Glens\nRandyshire, FL 38208',
},
    'key73217': 'value78188',
    'key94213': 'value59536',
    'key88476': 'value41994',
    'key19762': 'value79452',
    'key17824': 'value55345',
    'key31334': 'value35465',
    'key64025': 'value35120',
    'key76148': 'value60687',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Susan Baker',
    'address': '20850 Wilson Knolls\nWest Deanton, CT 58676',
    'text': 'Allow stop without surface. Four pattern situation character. Citizen interesting protect defense.\nIncluding state have maintain former. Will rather structure media price.',
    'email': 'awaters@example.net',
    'phone_number': '(249)692-1346x7020',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Jackson',
    'Bryan Hensley',
    'Joel Johnston',
    'Matthew Lopez',
    'Jeffrey Howell',
    'Jason Kerr',
    'John Moore',
    'Beth Brown',
],
    'json': {
    'name': 'Timothy Roberts',
    'address': 'PSC 6622, Box 1975\nAPO AE 66967',
},
    'key47929': 'value40064',
    'key22365': 'value4282',
    'key51668': 'value22259',
    'key53576': 'value14495',
    'key68877': 'value64038',
    'key61415': 'value95908',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Sandra Estrada',
    'address': '5990 Bradley Mall Apt. 954\nCampbellport, GA 36495',
    'text': 'Such amount themselves space. Campaign indicate small place.\nIf politics respond method hotel real campaign believe. More someone life less. Learn group something think debate answer.',
    'email': 'xavier72@example.com',
    'phone_number': '001-789-508-3071',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Carter',
    'Emily Carroll',
    'Christine Lara',
    'Christine Bridges',
    'Walter Ortiz',
    'Daniel Smith',
],
    'json': {
    'name': 'Steven Moody',
    'address': '608 Williams Green Suite 659\nNorth Megan, NJ 70347',
},
    'key49937': 'value19762',
    'key96049': 'value93585',
    'key13130': 'value17711',
    'key62271': 'value38406',
    'key20625': 'value4541',
    'key91092': 'value58801',
    'key79390': 'value69083',
    'key66877': 'value71702',
    'key11957': 'value15857',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Amy Burns',
    'address': '5427 Barr Wells Suite 862\nSouth Michelle, AS 51223',
    'text': 'Particularly boy level risk maybe. Computer it fire.\nNumber probably son ability radio bit. Could environmental participant senior above.\nLearn place voice. Book something offer statement allow.',
    'email': 'davidfaulkner@example.net',
    'phone_number': '983.926.8725x3629',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Hicks',
    'Michael Brown',
    'Stephen Clark',
    'Andrew Kelly',
    'Laura Gamble',
    'Joseph Marsh',
    'William Erickson',
],
    'json': {
    'name': 'Lisa Pearson',
    'address': '578 Miller Valley\nPort Wesleyhaven, AK 59077',
},
    'key84687': 'value18397',
    'key43903': 'value6958',
    'key12045': 'value94308',
    'key72978': 'value45512',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Erik Phillips',
    'address': 'Unit 6176 Box 3833\nDPO AE 35961',
    'text': 'Believe policy concern practice since. Mouth interest answer hospital significant since third. Discussion present position keep performance wish as.',
    'email': 'medinathomas@example.com',
    'phone_number': '208-858-5405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mark Blair',
    'Kathryn Reyes',
],
    'json': {
    'name': 'Yolanda Cook',
    'address': '76725 John Drive Apt. 138\nKendraton, WI 50864',
},
    'key51650': 'value11438',
    'key20962': 'value3440',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Isaac Ward',
    'address': '8858 Lopez Crescent\nEast Jenniferbury, MA 50721',
    'text': 'Behind west event tax hard money. Expert under cover cut magazine reason assume born.\nChange boy from. Follow toward occur consider likely media.',
    'email': 'johnjuarez@example.org',
    'phone_number': '+1-681-405-4495x9378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Webster',
    'Roger Merritt',
    'Zoe Gonzalez',
    'Paige Howard',
    'Javier King',
    'Karina Matthews',
    'Julie Bell',
    'Dr. Dylan Ramirez DVM',
],
    'json': {
    'name': 'Laura Jackson',
    'address': '122 Heather Oval Suite 881\nLake Savannah, NM 83439',
},
    'key8136': 'value70835',
    'key14343': 'value57571',
    'key37394': 'value32974',
    'key31677': 'value72141',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Mark Henry',
    'address': '741 Brown Terrace\nNorth Codyland, NV 24279',
    'text': 'According should seven onto.\nSeason task building room arm. Pressure increase age discover outside land.',
    'email': 'jacqueline48@example.com',
    'phone_number': '(253)843-3023x14450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Rodriguez',
    'Javier Jones',
    'Lisa Young',
    'Anthony Garcia',
    'Dennis Bradford',
    'Dr. Alexandra Davis DVM',
    'Tara Powell',
    'Brian Garza',
    'Leonard Herrera',
],
    'json': {
    'name': 'Gregory Rodriguez',
    'address': 'Unit 3132 Box 3424\nDPO AA 62443',
},
    'key80047': 'value40695',
    'key17175': 'value55700',
    'key12867': 'value51945',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Crystal Young',
    'address': '0220 David Ferry\nFosterchester, OK 66765',
    'text': 'Affect cause begin wish however song research. Bit similar scene.\nSee actually be during. Newspaper find whose home structure fine charge. Worry together try sometimes trip learn.',
    'email': 'kingjared@example.net',
    'phone_number': '879-571-4807',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Justin Mccarthy',
    'Benjamin Brewer',
    'Christina Yates',
    'Nicole Caldwell',
    'Laurie Simmons',
    'Chad Cox',
    'Joseph Wilson',
    'Joshua Rivas',
    'Anthony Pearson',
],
    'json': {
    'name': 'Dawn Trevino',
    'address': '2655 David Ferry Suite 621\nNorth Alanbury, MA 39155',
},
    'key31846': 'value87162',
    'key16275': 'value70054',
    'key77808': 'value72056',
    'key25067': 'value11652',
    'key43737': 'value29331',
    'key46000': 'value62690',
    'key20446': 'value93485',
    'key69555': 'value32536',
    'key29283': 'value18171',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Miguel Diaz',
    'address': 'PSC 9125, Box 9345\nAPO AP 32117',
    'text': 'Hope step significant worker more catch near whom. At his over whatever.\nDetail doctor blue could including most decision. Point to argue language ball individual central effort.',
    'email': 'chadbrock@example.com',
    'phone_number': '723-492-4777',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Scott',
    'Nicole Wilson',
    'Jessica Guzman',
],
    'json': {
    'name': 'Jessica Mills',
    'address': 'Unit 6464 Box 8366\nDPO AP 77447',
},
    'key1721': 'value62899',
    'key23633': 'value31637',
    'key43179': 'value72772',
    'key34308': 'value57086',
    'key1903': 'value51705',
    'key2766': 'value8385',
    'key56949': 'value82807',
    'key99799': 'value62247',
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
    'RequestId': '8cbac079-62ef-11f0-9a2a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_23_623916aTqOyFCI',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-embedding-url-32-100-2]_1752744145.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdEmbeddingUrl3210021752744145Json()
    test.run_tests()
