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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_complex_payload[IP-1-0-2]_1752744555_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[IP-1-0-2]_1752744555.json"
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithComplexPayloadIp1021752744555Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[IP-1-0-2]_1752744555.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[IP-1-0-2]_1752744555.json"
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
    'RequestId': '7d4ca87a-62f0-11f0-a446-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_29_07_233303yaeXcHvW',
    'dimension': 128,
    'metricType': 'IP',
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
    'RequestId': '807332a0-62f0-11f0-b44e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_29_07_233303yaeXcHvW',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Matthew Wilson',
    'address': '042 Victoria Burg\nRodriguezburgh, CO 77196',
    'text': 'Challenge third probably red free close should. However one glass eight attorney yet visit. Under me be.\nClaim true or from. Wide base ground plan reason line.',
    'email': 'bking@example.com',
    'phone_number': '566-303-6951',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Mcdonald',
    'Mary Long',
    'Jessica Anderson',
    'Arthur Miller',
    'Anna Berry',
    'Daniel Bowen',
    'Eric Garcia',
],
    'json': {
    'name': 'Andre Hayes',
    'address': '6341 Frazier Street Suite 245\nPort Angela, VI 16247',
},
    'key26470': 'value73261',
    'key99722': 'value1715',
    'key37020': 'value60957',
    'key25671': 'value57104',
    'key76879': 'value95610',
    'key63094': 'value26956',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Dylan Oneal',
    'address': 'PSC 0729, Box 5300\nAPO AP 06215',
    'text': 'Wonder institution million sort. Data mean glass group. Could job popular resource scene will.\nNever here exactly response attack green. Natural left party message.',
    'email': 'laura57@example.com',
    'phone_number': '(776)879-5166',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Erin Singh',
    'Christopher Trevino',
    'Benjamin Hill',
],
    'json': {
    'name': 'Michael Carlson',
    'address': 'USNS Meyer\nFPO AP 22991',
},
    'key72173': 'value98853',
    'key8257': 'value21148',
    'key1331': 'value76571',
    'key49545': 'value51122',
    'key407': 'value24373',
    'key5967': 'value4524',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Karen Tucker',
    'address': '79823 Jessica Lodge\nSmithbury, WV 95986',
    'text': 'Adult economic first general main outside. Record name wish eye fight movement. Democrat clear home although adult.',
    'email': 'phillipsbetty@example.com',
    'phone_number': '496.945.9863x25485',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Meghan Fox',
    'Melissa Walters',
    'Haley Moreno',
    'Justin Esparza',
],
    'json': {
    'name': 'Michelle Cruz',
    'address': 'USCGC Sampson\nFPO AE 28332',
},
    'key27017': 'value63080',
    'key33640': 'value95152',
    'key39288': 'value23382',
    'key14552': 'value50073',
    'key4853': 'value16307',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Samantha Gonzales',
    'address': '221 Susan Creek Apt. 738\nAndrewhaven, ID 57707',
    'text': 'Feel store various successful fight. Which democratic under business world image worry.',
    'email': 'taylor86@example.com',
    'phone_number': '001-728-274-5486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Julie Fischer',
    'Jessica Brewer',
    'Mark Bryant',
    'Gina Harrison',
    'Jeffrey Rogers',
    'Ashley Walker',
],
    'json': {
    'name': 'Dennis Dillon',
    'address': '9754 Steele Row Suite 829\nRiveraton, HI 42073',
},
    'key86824': 'value72931',
    'key69958': 'value80670',
    'key88912': 'value58626',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Matthew Vargas',
    'address': '043 Justin Road Apt. 920\nMartinezport, VA 64613',
    'text': 'Interview piece medical interesting room cut. Lay tell surface catch personal table become. Peace this successful participant.\nField affect Republican white way everything much.',
    'email': 'blakekelly@example.org',
    'phone_number': '001-600-428-4120x54809',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alan Mills',
    'Shawn Reynolds',
    'Jason Kline',
    'Aaron Molina',
    'Kerry Lee',
    'Robin Navarro',
    'Aaron Boyd',
    'Laurie Logan',
    'John Harris',
    'Patricia Price',
],
    'json': {
    'name': 'Aaron Moore',
    'address': '02043 Jennifer Underpass\nMartinezfort, OR 82713',
},
    'key79818': 'value70169',
    'key42150': 'value52220',
    'key57286': 'value80014',
    'key7553': 'value13651',
    'key45663': 'value9797',
    'key212': 'value27556',
    'key26476': 'value41635',
    'key64638': 'value35503',
    'key30022': 'value2757',
    'key29231': 'value26931',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Anthony Hart',
    'address': '5258 Myers Throughway\nNorth Colleenbury, IA 96555',
    'text': 'Drop alone around president scientist leg those. Several since out.\nFigure reflect alone follow.',
    'email': 'xnunez@example.com',
    'phone_number': '865.458.1990x136',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Powell',
    'Luis Bass',
    'Jeremy Reynolds',
    'Joseph Adams',
    'Michael Austin',
],
    'json': {
    'name': 'Amy Fox',
    'address': 'USS Reyes\nFPO AE 50406',
},
    'key22187': 'value64140',
    'key90079': 'value72361',
    'key67326': 'value1197',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Rita Thomas',
    'address': '46932 Dustin Mount\nMichaelmouth, WI 06542',
    'text': 'Method of address development eight. Each low discussion far again. Their rich heart writer bring relationship. Professor production anything hair.',
    'email': 'claytonrobert@example.org',
    'phone_number': '+1-584-988-0172x83918',
    'array_int_dynamic': [
    35338,
],
    'array_varchar_dynamic': [
    'Mrs. Stephanie Brown',
    'Angela Huber',
    'Jeffrey Leonard',
    'Lisa Wilson',
    'Tyler Johnson',
    'Amber Tyler',
    'Gina Klein',
],
    'json': {
    'name': 'Daniel Bowman',
    'address': '1586 Kennedy Pass\nChristopherport, TN 06333',
},
    'key7123': 'value45244',
    'key6649': 'value72633',
    'key79150': 'value50663',
    'key52472': 'value52609',
    'key10622': 'value88532',
    'key16890': 'value52505',
    'key98037': 'value15265',
    'key66995': 'value90384',
    'key78538': 'value93491',
    'key26736': 'value42711',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Scott Edwards',
    'address': '8331 James Branch\nNew Evan, AK 70519',
    'text': 'Family reality series general well floor likely. Total really road foot. Avoid war style collection.\nAny century thing tree individual my yeah.',
    'email': 'wrightlogan@example.org',
    'phone_number': '367-621-6798',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Gary Mcconnell',
    'Lorraine Preston MD',
    'Robin Simpson',
    'Harry Sanchez',
],
    'json': {
    'name': 'Alicia Brown',
    'address': '72682 Becker Cape\nOliverview, NM 61745',
},
    'key73869': 'value64064',
    'key14435': 'value23432',
    'key93278': 'value70444',
    'key59701': 'value74483',
    'key12764': 'value13707',
    'key10049': 'value52324',
    'key44911': 'value98707',
    'key385': 'value19964',
    'key8821': 'value1231',
    'key7666': 'value99459',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Devon Wise',
    'address': '43213 Nicole Trail\nNorth Brian, FL 62220',
    'text': 'Environment eat consumer. Draw others clear big together day. Notice throw citizen.',
    'email': 'shepardvincent@example.com',
    'phone_number': '001-740-228-6166',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Miranda',
    'Andrew Henry',
    'Andrea Ellis',
    'Jason Lopez',
    'Wesley King',
    'Charles Holland',
],
    'json': {
    'name': 'Nicole Turner',
    'address': '782 Williams Corners\nNew Charlesview, WI 76560',
},
    'key74802': 'value16229',
    'key15646': 'value23009',
    'key62014': 'value43271',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Abigail Anderson',
    'address': '408 Thomas Ranch\nWest Katie, NM 84258',
    'text': 'Actually language teach better fill. Ten threat team range unit voice activity.\nIndeed seven customer onto. Easy standard morning glass green. Less we professional imagine.',
    'email': 'hendersongary@example.com',
    'phone_number': '423.220.4750',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Wheeler',
    'Karen Smith',
    'Adam Jenkins',
    'Melissa Garcia',
    'Lynn Allen',
    'John Boyd',
],
    'json': {
    'name': 'William Bates',
    'address': '2894 Barbara Valleys\nNorth Tammymouth, CT 47818',
},
    'key98125': 'value11381',
    'key77967': 'value92334',
    'key678': 'value50136',
    'key57462': 'value54221',
    'key85050': 'value2556',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Melissa Davis',
    'address': '626 Yang Crossroad\nNew Ashleyside, WI 77112',
    'text': 'Since kitchen opportunity although close. Because policy detail high hot.\nCup third huge. Account movie region imagine example. Particularly physical bill national to magazine.',
    'email': 'gking@example.net',
    'phone_number': '(724)841-4943x2413',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Castro',
    'Eric Peterson',
    'Mrs. Dawn Burke',
    'Mr. Jared Montoya',
    'Linda Adams',
    'Barbara Kent',
    'Jenny Gonzalez',
    'Sandra Cruz',
],
    'json': {
    'name': 'James Vasquez',
    'address': '395 Gonzales Garden Apt. 688\nPhillipside, AZ 97069',
},
    'key28446': 'value70503',
    'key55465': 'value93474',
    'key18155': 'value47221',
    'key15071': 'value20693',
    'key85400': 'value95618',
    'key3504': 'value23881',
    'key57306': 'value25442',
    'key79832': 'value94783',
    'key65873': 'value14734',
    'key28950': 'value43010',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Dillon Petersen',
    'address': '02450 Hogan Ports\nNorth Jameshaven, MT 73492',
    'text': 'Put hit say present. Ground character budget.\nBook popular accept expert certainly. Trial create teacher current huge why suggest. Standard loss response member explain husband set.',
    'email': 'ymiller@example.net',
    'phone_number': '458-732-1918',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alicia Brown',
    'Patrick Moreno',
    'Lauren Soto',
    'Theodore Monroe',
    'Angela Blake',
    'Sarah Nelson',
    'Melissa Jimenez',
    'Michael Hancock',
],
    'json': {
    'name': 'Tina Lane',
    'address': 'Unit 0064 Box 1991\nDPO AE 40203',
},
    'key90412': 'value98859',
    'key94340': 'value56056',
    'key56080': 'value63275',
    'key40563': 'value60532',
    'key9841': 'value37586',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Michele Lee',
    'address': '9755 Steven Rapid Apt. 081\nPort Samanthaview, MO 17349',
    'text': 'Mention job their which. Example let beat marriage staff occur through single. Establish center act success would view. Explain present thought than hear gas.',
    'email': 'villarrealkenneth@example.com',
    'phone_number': '311-895-5241',
    'array_int_dynamic': [
    4197,
],
    'array_varchar_dynamic': [
    'Raymond Barnes',
    'Scott Dunlap',
    'Mrs. Monique Stephenson',
    'Pamela Williams',
    'Ryan Williams',
    'Lisa Richardson',
    'Taylor Owens',
    'Diane Valencia',
    'Andrea Guzman',
    'Holly Garcia',
],
    'json': {
    'name': 'Jennifer Archer',
    'address': '1339 Morrison Prairie\nBrittanyfort, MP 30524',
},
    'key96103': 'value59065',
    'key11020': 'value6780',
    'key52272': 'value71064',
    'key76160': 'value8603',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Charles Barnes',
    'address': '0023 Hannah Mountain Suite 064\nGriffinport, IL 08951',
    'text': 'Budget only development because ground others huge. Ten lawyer manager admit share.',
    'email': 'chaneylevi@example.com',
    'phone_number': '(668)970-9174',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Thompson',
    'Lee Miller',
    'Richard Jones',
    'Carl Young',
    'Amanda Gallagher',
    'Vanessa Buck',
    'Nicole Gibson',
    'Benjamin Mcintyre',
    'Jill Mack',
    'Courtney Brown',
],
    'json': {
    'name': 'Peter Snyder',
    'address': '15392 Boyle Hill Apt. 466\nDavisborough, CT 37799',
},
    'key71352': 'value39378',
    'key74357': 'value91215',
    'key41890': 'value68162',
    'key99661': 'value87266',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Mr. Stephen Smith',
    'address': '8708 James Passage\nNew Vanessaport, MP 31141',
    'text': 'Long name nation always group care far. Heavy night claim under. Because feeling early care class author.',
    'email': 'timothy49@example.org',
    'phone_number': '237.996.6857',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Erin Perez',
    'Sandra Sherman',
    'Joseph Riley',
    'Robin Potter',
    'Christopher West',
    'Richard Wu',
    'Kevin Rivera',
],
    'json': {
    'name': 'Jane Davila',
    'address': '576 Daniel Locks Suite 387\nNorth Austin, NM 87073',
},
    'key21386': 'value93206',
    'key22437': 'value12613',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Elizabeth Gray',
    'address': '119 Sanchez View\nRobinsontown, IA 88947',
    'text': 'Wear rock better drug none. Interesting there decade everybody Mr money treatment for. Whether yeah reason popular truth.\nOur realize large gas realize common. Writer agree where school gas.',
    'email': 'hwolfe@example.net',
    'phone_number': '406.884.5827',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Megan Nichols',
    'Ana Meyers',
    'Miguel Thompson',
    'Zachary Clark',
],
    'json': {
    'name': 'Michelle Webb',
    'address': '68599 Clark Lights Suite 508\nNew Johnmouth, CT 50959',
},
    'key90270': 'value24263',
    'key18535': 'value98356',
    'key79838': 'value53776',
    'key28877': 'value84265',
    'key37857': 'value81065',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Susan Benson',
    'address': '42128 Renee Mill Apt. 559\nPort Nicolechester, AK 07872',
    'text': 'Real painting hard require challenge live although task. Hand stand whose former.\nToward start determine culture class. Send whom standard appear.',
    'email': 'brian01@example.org',
    'phone_number': '272.962.0658x6685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Todd Warren',
    'Brittany Cole',
    'Jason Reed',
    'Christina Anderson',
    'Carlos Spencer',
    'Gregory Vaughn',
    'Peter Moon',
],
    'json': {
    'name': 'Stephen Henson',
    'address': '257 David Rapid\nSullivanberg, VI 97239',
},
    'key10629': 'value46690',
    'key30045': 'value42502',
    'key87080': 'value30748',
    'key61014': 'value81178',
    'key65991': 'value72567',
    'key88844': 'value13559',
    'key52268': 'value99818',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Dylan Weber',
    'address': 'PSC 0687, Box 3868\nAPO AA 56550',
    'text': 'Southern state if. Nation others factor either seat discussion. Able maintain listen everything under.\nLot stand easy wall almost visit fly some. Involve not friend approach gas on himself certain.',
    'email': 'iburns@example.com',
    'phone_number': '327-505-2025',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Burke',
    'Jacqueline Martinez',
],
    'json': {
    'name': 'Michael Scott',
    'address': 'PSC 7705, Box 4162\nAPO AP 72281',
},
    'key6047': 'value3204',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Beth Conway',
    'address': '57802 Howell Bypass\nNorth Monicachester, AK 28727',
    'text': 'Assume act international industry threat ok. Hope structure act data. Return your poor central real daughter choose.\nSecond voice fall. Measure subject help again.',
    'email': 'richardsonsteven@example.net',
    'phone_number': '6313320982',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Allen',
    'Anthony Owen',
    'Tyler Castillo',
    'Karl Flores',
],
    'json': {
    'name': 'Crystal Perez',
    'address': '456 Ortiz Street\nNew Michelle, AZ 09384',
},
    'key40154': 'value18346',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Chad Calderon',
    'address': '744 Odonnell Ridges Apt. 058\nBakerland, TN 46150',
    'text': 'Year begin piece always. Public specific son them. Song gun campaign ask before career develop.',
    'email': 'dkelly@example.com',
    'phone_number': '+1-958-271-7429x382',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Todd Fuller',
    'William Lopez',
    'Bryan Chapman',
    'Kevin Lawson',
    'Teresa Brown',
    'Lisa Clarke',
    'James Hoffman',
    'Daisy Anderson',
    'Jonathan Diaz',
    'Dennis Matthews',
],
    'json': {
    'name': 'Ms. Donna Nguyen',
    'address': '110 Bruce Brook Suite 297\nLake Tinaview, WY 45582',
},
    'key2886': 'value89902',
    'key62213': 'value75395',
    'key24540': 'value4161',
    'key65294': 'value29276',
    'key31583': 'value25709',
    'key74885': 'value51546',
    'key3840': 'value13271',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Tammy Lowe',
    'address': '615 Conner Shores Suite 054\nElizabethshire, PR 69850',
    'text': 'Per out future that evidence. Middle car recognize best lot scientist. Fact skin drive trade.\nDegree bag also article despite. Approach well edge and. Give office floor book choice film.',
    'email': 'traviscastillo@example.org',
    'phone_number': '001-759-620-8863',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Max Contreras',
    'Lance Schroeder DDS',
    'Richard Hansen',
    'Rebecca Smith',
    'Karen Cline',
    'Jeremy Contreras',
    'Matthew Reyes',
    'Christine Simmons',
],
    'json': {
    'name': 'Shannon Hurst',
    'address': '774 Webb Corners\nSandratown, NV 98351',
},
    'key73086': 'value92815',
    'key13610': 'value31323',
    'key67014': 'value95418',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Henry Bender',
    'address': '8777 Buckley Forks\nSouth Jennifer, RI 74837',
    'text': 'Analysis plant capital close production prevent draw show. Push nice five example life responsibility economy. Can real peace push ready.',
    'email': 'steinalexander@example.org',
    'phone_number': '+1-890-766-4568x203',
    'array_int_dynamic': [
    37318,
],
    'array_varchar_dynamic': [
    'Jessica Ross',
    'Derrick Stewart',
    'Abigail Long',
    'Donna Ramirez',
    'Jennifer Russell',
    'Jesse Garcia',
],
    'json': {
    'name': 'Donald Lawrence',
    'address': '794 Spencer Port\nDavisbury, NJ 47724',
},
    'key39426': 'value28179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Patrick Williams',
    'address': '66881 Karen Pike Suite 844\nHillview, DC 55573',
    'text': 'Where also sure all child into doctor. No across garden add up news.\nSeat happy rise community them memory between. Weight chair certainly ever citizen civil. Wait improve almost maintain yes.',
    'email': 'doylestephen@example.net',
    'phone_number': '(252)755-4210x570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Duarte',
    'Amanda Ritter',
    'Christopher Patel',
],
    'json': {
    'name': 'Albert Nichols',
    'address': '4511 Swanson Ramp Suite 788\nFishermouth, WA 30432',
},
    'key80092': 'value56173',
    'key1721': 'value51368',
    'key13443': 'value90940',
    'key60231': 'value60704',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jeffrey Young',
    'address': '832 Bell Centers Suite 400\nNew Tyler, TN 28811',
    'text': 'Capital so central board than still. Politics bank pattern check election.\nOpen determine forward fire social. Push it include vote.',
    'email': 'gonzaleskimberly@example.com',
    'phone_number': '(281)227-2879x6554',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christine Cantrell',
],
    'json': {
    'name': 'Dr. Curtis Price DDS',
    'address': '415 Zachary Via Apt. 790\nPort Kathleen, OR 69988',
},
    'key86251': 'value96312',
    'key53083': 'value65821',
    'key39156': 'value47665',
    'key79432': 'value1179',
    'key44412': 'value87321',
    'key76744': 'value32722',
    'key19823': 'value59196',
    'key16133': 'value4327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Mary Morton',
    'address': '97013 Walters Locks\nKimberlyview, WI 52237',
    'text': 'Buy around identify bit rock. Green wall certain up color.\nSource away turn. Thus much dream marriage agency recognize firm. Month vote possible computer direction kind hour seem.',
    'email': 'harrisamanda@example.org',
    'phone_number': '996-920-5166x9186',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Morrison',
],
    'json': {
    'name': 'Jeffrey Smith',
    'address': '982 Riley Plaza\nJessicafurt, MA 85844',
},
    'key46594': 'value21955',
    'key4683': 'value97349',
    'key67000': 'value83968',
    'key72173': 'value51333',
    'key67312': 'value75210',
    'key8767': 'value99299',
    'key78991': 'value60650',
    'key49875': 'value13172',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Heather Wood',
    'address': '03730 Jeremiah Wells Apt. 822\nWest Jacquelineborough, AS 14649',
    'text': 'Relate side painting for happy hour. Responsibility else same different past recent lawyer race. Sit health total establish decade white.',
    'email': 'garciamichael@example.org',
    'phone_number': '+1-563-457-5697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Gary Hull',
    'Cheryl Johnson',
    'Michael Williams',
    'David Fields',
    'Laura Montgomery',
    'Michael Rivas',
    'Gary Welch',
    'Michael Gonzalez',
],
    'json': {
    'name': 'Kyle George',
    'address': '3981 White Keys Apt. 957\nBarkerfort, MD 87443',
},
    'key28557': 'value75537',
    'key11592': 'value32785',
    'key25168': 'value94186',
    'key38049': 'value79038',
    'key53435': 'value50056',
    'key19870': 'value48973',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Kathleen Martin',
    'address': '316 Anthony Unions Apt. 926\nSouth Tammy, ND 71364',
    'text': 'Behavior help company lose. Loss government region night whether reason.\nFew leave base office. Window ever world. Third senior sort make price safe their decade. Somebody article health both others.',
    'email': 'marissa09@example.com',
    'phone_number': '(391)216-2426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jenna Jackson',
    'Felicia Decker',
    'Nicholas Brock',
],
    'json': {
    'name': 'Anthony Galloway',
    'address': '8122 Williams Cape\nHansenborough, MO 24337',
},
    'key41675': 'value41229',
    'key33670': 'value94090',
    'key86363': 'value56491',
    'key35675': 'value7538',
    'key68563': 'value36557',
    'key88838': 'value5422',
    'key83330': 'value13070',
    'key29911': 'value53295',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Thomas Reed',
    'address': '926 Jennings Fork Suite 357\nPort Nathan, NV 26018',
    'text': 'Increase serious board stock ok well them. Industry protect see value relate its fear. Center next life glass.',
    'email': 'davidcampbell@example.org',
    'phone_number': '4733471757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Garza',
    'Mr. Brian Malone MD',
    'Lorraine Marks',
    'Catherine Phillips',
],
    'json': {
    'name': 'Allison Chan',
    'address': '05080 Brian Street\nPort Julia, VA 30357',
},
    'key31875': 'value59990',
    'key13703': 'value83409',
    'key28987': 'value73753',
    'key64504': 'value41362',
    'key7939': 'value49650',
    'key61459': 'value9083',
    'key92594': 'value80445',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Patrick Harrington',
    'address': '695 Thomas Mill Apt. 311\nJessicatown, CT 74216',
    'text': 'Word building themselves scientist. Professional industry culture artist.\nLive movement herself. City meeting head light star baby box. All nothing be your time.',
    'email': 'alexander42@example.net',
    'phone_number': '882-665-7248x43971',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Erica Smith',
    'Ashley Mccoy',
    'Breanna Cherry',
],
    'json': {
    'name': 'Cody Barton',
    'address': '9148 Thornton Landing Apt. 239\nHeatherside, IA 86220',
},
    'key57379': 'value60400',
    'key96847': 'value5687',
    'key20895': 'value87365',
    'key94981': 'value97692',
    'key42636': 'value14586',
    'key20135': 'value1207',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Stacy Obrien',
    'address': 'USCGC Lee\nFPO AE 02130',
    'text': 'Senior also understand manager perhaps. Very modern behavior agency standard it use. Position participant draw fall compare purpose music now.\nLevel man significant. Able analysis meeting apply.',
    'email': 'michaelpaul@example.com',
    'phone_number': '(597)409-2245',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Tapia',
    'Justin Kennedy',
    'Danielle Gray',
    'Elizabeth Shields',
],
    'json': {
    'name': 'Christopher Prince',
    'address': '6181 Audrey Trace\nNorth Christina, PR 40587',
},
    'key41033': 'value14861',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Kimberly Miller',
    'address': '73902 Thomas Grove\nEast Peterhaven, MS 17659',
    'text': 'Task either so end best front every.\nToday away site most. Term down knowledge street difficult.',
    'email': 'amanda35@example.org',
    'phone_number': '(973)390-3053',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Felicia Wells',
    'Laura Roberts',
],
    'json': {
    'name': 'Cathy Morgan',
    'address': '41927 Lawrence Forks Apt. 146\nNew Justin, NV 87246',
},
    'key65780': 'value47053',
    'key93597': 'value60567',
    'key83935': 'value11652',
    'key25501': 'value10520',
    'key16621': 'value88065',
    'key45361': 'value59317',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'John Ware',
    'address': 'PSC 4915, Box 9855\nAPO AA 53114',
    'text': 'Race line upon month. Debate firm exist.\nOpen church activity. Law their hold exist rock. Carry represent individual focus low level no.',
    'email': 'brendaavila@example.com',
    'phone_number': '6503136170',
    'array_int_dynamic': [
    11795,
],
    'array_varchar_dynamic': [
    'Lisa Williams',
    'Valerie Gray',
    'George Bernard',
    'Matthew Murphy',
],
    'json': {
    'name': 'Michael Barton',
    'address': '1504 Jackson Junction Suite 252\nPowellhaven, AR 71116',
},
    'key4522': 'value78625',
    'key67843': 'value26063',
    'key45968': 'value27846',
    'key63499': 'value88635',
    'key49871': 'value77523',
    'key48666': 'value85935',
    'key55780': 'value91208',
    'key77971': 'value98652',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Martin Mcmahon',
    'address': '034 Christopher Plaza Suite 388\nChristinaside, KS 78559',
    'text': 'Window rule seven according compare.\nSense rather daughter indicate of per. Party foreign weight entire know.\nFact threat modern hair. Surface man pull.',
    'email': 'danny48@example.net',
    'phone_number': '(351)580-2309x49517',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'David Murray',
    'Bryan Davis',
],
    'json': {
    'name': 'Carla Jones',
    'address': '1889 Nathan Cliff Suite 270\nEast Jennifer, UT 71292',
},
    'key83567': 'value93691',
    'key42597': 'value19037',
    'key6506': 'value34631',
    'key75423': 'value19369',
    'key77786': 'value91925',
    'key36699': 'value50931',
    'key31309': 'value66348',
    'key5658': 'value66555',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Nancy Mclaughlin',
    'address': 'Unit 1823 Box 6355\nDPO AA 74915',
    'text': 'Behavior range many.\nCreate five above commercial. Different half probably how behind risk office. Create total factor say.\nQuestion different none. Carry region start course present group special.',
    'email': 'fhicks@example.com',
    'phone_number': '001-340-905-4914',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mark Joseph',
],
    'json': {
    'name': 'Robert Weaver',
    'address': 'Unit 7822 Box 0833\nDPO AA 49167',
},
    'key80893': 'value21821',
    'key66222': 'value17927',
    'key27896': 'value10327',
    'key18825': 'value43176',
    'key49045': 'value77653',
    'key97637': 'value3734',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Ashley Buchanan',
    'address': 'Unit 6839 Box 0432\nDPO AA 05818',
    'text': 'Blood course deep bed she.\nPlan small prove.\nCustomer rather possible require former beat. Girl discuss thus concern from everything. Method upon left policy method nothing them.',
    'email': 'cindycarlson@example.net',
    'phone_number': '+1-919-232-3685x450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Maria West',
    'Miss Marie Robinson DVM',
],
    'json': {
    'name': 'Andrew Morales',
    'address': '41030 Jones Common Suite 740\nKevinbury, MS 75827',
},
    'key5799': 'value62957',
    'key83620': 'value53930',
    'key89617': 'value30494',
    'key84323': 'value20128',
    'key79446': 'value45748',
    'key22759': 'value80085',
    'key75926': 'value38238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Douglas Fitzpatrick',
    'address': '675 King Garden\nMillerfurt, CO 69295',
    'text': 'Foot watch final agency current over stage. Peace war city this middle.\nBudget general put field color into. Campaign few fact. Just woman cultural reason.',
    'email': 'zcochran@example.com',
    'phone_number': '625.859.7578',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Cameron',
    'Travis Vincent',
    'Debra Walters',
],
    'json': {
    'name': 'Courtney Freeman',
    'address': '393 Gibbs Orchard Suite 955\nMartintown, AZ 05535',
},
    'key94044': 'value87627',
    'key39527': 'value4057',
    'key54201': 'value86582',
    'key56249': 'value47606',
    'key84913': 'value90056',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Andrea Wong',
    'address': 'PSC 6410, Box 7772\nAPO AA 22997',
    'text': 'Forget real war concern interest rule. Picture sister same least must hundred. Chair may theory.',
    'email': 'larry33@example.com',
    'phone_number': '887.930.5205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Gabrielle White',
    'Brittany Oconnell',
    'Renee Jackson',
    'Kim Cruz',
],
    'json': {
    'name': 'Bruce Cole',
    'address': '63941 Michelle Motorway Apt. 669\nBryantburgh, LA 32616',
},
    'key9264': 'value65730',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Sarah Brown',
    'address': '220 Faith Overpass\nEast Douglas, AL 23210',
    'text': 'Why after music beautiful walk debate charge. Chair why blue.\nCollection stand help sit give at short. Mouth skill yes my after others.\nRest class safe road. Song quite join.',
    'email': 'samantha76@example.com',
    'phone_number': '597-322-3262x6296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Donald Johnston',
    'Kendra Pham',
    'Chad Potts',
    'Matthew White',
    'Makayla Dixon',
    'Tamara Schwartz',
    'Jennifer Velazquez',
],
    'json': {
    'name': 'Tami Campbell',
    'address': '05556 Nguyen River\nNorth Eddie, OK 75094',
},
    'key27427': 'value67107',
    'key41647': 'value46099',
    'key96960': 'value34214',
    'key21782': 'value44841',
    'key69172': 'value92024',
    'key14314': 'value93487',
    'key11890': 'value91588',
    'key1325': 'value37034',
    'key71565': 'value5343',
    'key50925': 'value19299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Patricia Stephens',
    'address': '1614 Palmer Passage Apt. 123\nLake Rebecca, SC 53163',
    'text': 'Off debate happy house think risk. Enter item sea amount design scene Mrs decision. Support check near interest she.',
    'email': 'monicarosales@example.com',
    'phone_number': '(289)948-7231x85047',
    'array_int_dynamic': [
    47435,
],
    'array_varchar_dynamic': [
    'Heather Gonzalez',
    'Brandy Juarez MD',
    'Angela Scott',
    'Timothy Trujillo',
    'Regina Butler',
    'Andrew Rodriguez',
    'Scott Osborne',
    'Hannah Allison',
],
    'json': {
    'name': 'Peter Wade',
    'address': '6125 Robert Place\nEricmouth, OH 87257',
},
    'key46933': 'value78188',
    'key49995': 'value92728',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Robert Hernandez',
    'address': '8326 Nicholas Heights\nRubiostad, MN 01102',
    'text': 'Activity page decade baby science section so. Wrong boy operation interest last military. Perform major staff western guess deep.\nCause school phone spend cause if. Man on step agreement.',
    'email': 'qwilliams@example.net',
    'phone_number': '001-419-590-8083',
    'array_int_dynamic': [
    75791,
],
    'array_varchar_dynamic': [
    'Hannah Hoffman DVM',
    'Deborah Norman',
    'Willie Reynolds',
    'Chelsea Miller',
    'Shawn Nash',
],
    'json': {
    'name': 'Taylor Barton',
    'address': '795 Warren Forks Suite 440\nMccoyshire, VA 85031',
},
    'key59399': 'value25274',
    'key44162': 'value64625',
    'key83281': 'value45335',
    'key60086': 'value64074',
    'key75532': 'value90748',
    'key14526': 'value98951',
    'key12024': 'value49886',
    'key30520': 'value62703',
    'key63790': 'value11903',
    'key92726': 'value19312',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jennifer Stephenson',
    'address': '7196 Thomas Ford\nEast Kelly, VT 21041',
    'text': 'Mind husband child. Security account easy cup. Already become safe almost guess.\nGeneration message keep.',
    'email': 'david37@example.net',
    'phone_number': '7677809053',
    'array_int_dynamic': [
    3929,
],
    'array_varchar_dynamic': [
    'Dawn Spears DDS',
],
    'json': {
    'name': 'John Baker',
    'address': '81277 Jose Village\nNew Brian, CT 50509',
},
    'key73975': 'value45902',
    'key96088': 'value18830',
    'key59315': 'value62641',
    'key99924': 'value64403',
    'key95634': 'value95735',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Daniel Young',
    'address': '229 April Road Apt. 326\nEast Troyborough, NH 69341',
    'text': 'According believe stay perhaps majority teacher. Customer majority administration industry star later cost.',
    'email': 'michael93@example.com',
    'phone_number': '001-888-225-3518',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Connie Hansen',
    'Sandra Morales',
    'Vincent Patel',
    'Debbie Stewart',
    'Joseph Johnson',
    'Daniel Carter',
    'Elizabeth Wu',
],
    'json': {
    'name': 'William Cooper',
    'address': '6917 Christensen Key\nJamestown, CT 62008',
},
    'key42635': 'value95384',
    'key29302': 'value32804',
    'key68018': 'value79436',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Lucas Allen',
    'address': '3577 Rivera Light Apt. 567\nEast Martha, AZ 44886',
    'text': 'Bring decade professor.\nManager church one partner fight much. On four middle hour significant dream.',
    'email': 'vwilliams@example.org',
    'phone_number': '001-513-289-0034x544',
    'array_int_dynamic': [
    40883,
],
    'array_varchar_dynamic': [
    'Mary Buchanan',
    'Karen George',
    'Elizabeth Watts',
    'Erin Miles',
],
    'json': {
    'name': 'Marc Ali',
    'address': '87753 Preston Islands Apt. 912\nDebrashire, DC 46365',
},
    'key16730': 'value99231',
    'key90129': 'value84690',
    'key34527': 'value11687',
    'key32032': 'value71138',
    'key57612': 'value62711',
    'key71172': 'value2479',
    'key69322': 'value18756',
    'key61450': 'value49919',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Jason Ruiz',
    'address': '4261 Richards Gardens Suite 350\nBobbyborough, MS 01239',
    'text': 'Against form sure left possible over mother. City send thus peace ten.\nDebate field mention choose. Indeed range himself pay once either.',
    'email': 'newmangabriel@example.com',
    'phone_number': '+1-925-936-0105x6943',
    'array_int_dynamic': [
    55909,
],
    'array_varchar_dynamic': [
    'Toni Orr',
    'Kari Mathis',
    'Aaron Vargas',
    'Casey Benson',
    'Heather Wilson',
    'Gregory Fernandez',
    'Andrew Craig',
    'Kathleen Phillips',
    'Michael Banks',
],
    'json': {
    'name': 'Savannah King',
    'address': '523 Bray Stream Suite 810\nSouth Marvin, IL 24218',
},
    'key33171': 'value13773',
    'key12385': 'value99170',
    'key98423': 'value14291',
    'key89387': 'value29067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Peter Beck',
    'address': '211 Ingram Canyon Suite 109\nNorth Morgan, WV 30162',
    'text': 'Marriage affect play moment will. Sister operation build certainly what audience. Him PM cup idea heavy age case. Time attack day billion goal evening.',
    'email': 'poolepamela@example.org',
    'phone_number': '682.714.5808x39702',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Laura Galloway',
    'Shannon Williams',
],
    'json': {
    'name': 'Kylie Wilson',
    'address': '01559 Trevino Neck\nRichardview, FL 69292',
},
    'key45144': 'value19922',
    'key38799': 'value72188',
    'key60775': 'value54827',
    'key37776': 'value13778',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Gregory Cooper',
    'address': '812 Davis Haven Apt. 325\nFieldshaven, VT 76612',
    'text': 'Artist could woman walk either land.\nSeries understand just reveal drive money benefit. Letter phone way. Too girl throughout stop leg end. Ago rock film debate.',
    'email': 'hartkenneth@example.net',
    'phone_number': '365.428.4310x893',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Brewer',
    'Michael Taylor',
    'Kevin James',
    'Rebekah Orozco',
    'Courtney Decker',
],
    'json': {
    'name': 'Emily Hall',
    'address': '4369 Martinez Key\nWileybury, ND 77097',
},
    'key23810': 'value58026',
    'key88495': 'value78999',
    'key72405': 'value74655',
    'key54137': 'value49114',
    'key69740': 'value18340',
    'key88443': 'value85075',
    'key51416': 'value94311',
    'key65220': 'value96676',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Donald Thomas',
    'address': '47969 Leah Ports\nSmithview, WI 28179',
    'text': 'Ago soldier attorney. Less determine feel mean hospital.\nInternational hold father player be see. Compare south without letter the example.\nHow big pressure she network than. Worker stage view.',
    'email': 'john15@example.org',
    'phone_number': '001-765-672-9405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Charles Morris',
    'Shelly Smith',
    'Kathy Snyder',
],
    'json': {
    'name': 'Cynthia Haley',
    'address': '83515 Duke Village\nSouth Karenfurt, CO 54189',
},
    'key98973': 'value90415',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Alyssa Smith',
    'address': '126 Rose Pike Suite 161\nPort Mercedes, IN 02584',
    'text': 'Available season music certain because seem. Guy difficult way increase six. Spend officer so what worry son question short.\nWorker benefit whose vote operation.',
    'email': 'ajackson@example.com',
    'phone_number': '+1-828-894-2501x22083',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Suzanne Parker',
    'Kathryn Brown',
    'Bianca Ellison',
    'Alexandra Herman',
],
    'json': {
    'name': 'Courtney Chan',
    'address': '56320 Kevin Ports Apt. 355\nWest Billy, FM 92916',
},
    'key4403': 'value99704',
    'key92235': 'value44508',
    'key92602': 'value55058',
    'key7258': 'value54874',
    'key40123': 'value64324',
    'key3542': 'value85389',
    'key58109': 'value89782',
    'key29952': 'value44968',
    'key73288': 'value95099',
    'key14846': 'value76660',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Victoria Neal',
    'address': 'USS Roberts\nFPO AA 30992',
    'text': 'Per available according economy participant. American rate environment how understand produce peace worry.',
    'email': 'ktrujillo@example.com',
    'phone_number': '+1-280-677-1424x485',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Russell Duarte',
    'Jesse Soto',
    'Shelley Burton',
    'Steven Good',
    'Sarah Baker',
    'Jordan Cantu',
    'Katherine Davies',
    'Dustin Smith',
    'Angela Craig',
],
    'json': {
    'name': 'Sonya Peterson',
    'address': '903 Mcdowell Pass Apt. 390\nEast Emilyton, WI 47721',
},
    'key20422': 'value145',
    'key5245': 'value78802',
    'key30136': 'value20943',
    'key56966': 'value78307',
    'key47559': 'value52848',
    'key34299': 'value92637',
    'key606': 'value51251',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Daniel Riley',
    'address': '50028 Ramos Inlet\nHernandezmouth, WV 54857',
    'text': 'Major necessary or majority accept film ask reduce. Whole arm radio. Station film hand do serious alone culture. Memory media laugh receive rather issue.',
    'email': 'hholmes@example.org',
    'phone_number': '9455039891',
    'array_int_dynamic': [
    28599,
],
    'array_varchar_dynamic': [
    'Jonathan Brown',
    'Angela Yang',
    'Amy Evans',
],
    'json': {
    'name': 'Christine Hicks',
    'address': '77515 Leah Orchard\nWest Elizabethchester, FL 00599',
},
    'key10832': 'value99501',
    'key29742': 'value47733',
    'key39106': 'value62105',
    'key23165': 'value37043',
    'key37343': 'value14544',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Justin Mitchell',
    'address': '7282 Mccarty Fall\nWilsonmouth, NH 57292',
    'text': 'After everybody computer child.\nThose laugh agent from town prove good. Information leg speak consider. Small before most physical.',
    'email': 'qwhite@example.com',
    'phone_number': '919.790.6096',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Galvan',
    'Jennifer Pugh',
    'Mariah Hess',
    'Victoria Summers',
    'Anthony Bridges',
],
    'json': {
    'name': 'Paige Horn',
    'address': '1362 Reyes Inlet\nJaimechester, CO 60603',
},
    'key5448': 'value75703',
    'key71584': 'value73315',
    'key34971': 'value30873',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Jason Garcia',
    'address': '084 Kelsey Divide\nJavierton, DE 62746',
    'text': 'Share Mr hard cause. Politics involve financial husband training. Old debate development.\nDark let rise far option data relate very. Bad Mr available lose computer wind treatment.',
    'email': 'wolfeamanda@example.net',
    'phone_number': '001-234-366-0133x49368',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Wayne Perez',
    'Mike Perez',
],
    'json': {
    'name': 'Christine Barrera',
    'address': '0207 Joseph Rapid Suite 200\nWest George, OH 93534',
},
    'key34956': 'value14360',
    'key48641': 'value82370',
    'key17003': 'value62837',
    'key72556': 'value79467',
    'key49265': 'value48682',
    'key4371': 'value33680',
    'key86172': 'value51274',
    'key147': 'value72016',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Margaret Smith',
    'address': 'PSC 1961, Box 3802\nAPO AE 16120',
    'text': 'Modern brother ground central edge lay remember. New vote cost determine majority author.\nNever second usually floor. Fly energy tax.',
    'email': 'xsmith@example.net',
    'phone_number': '001-267-976-2781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Flores',
    'Dennis Jacobs',
    'Katherine Martin',
    'Taylor Kennedy',
    'Matthew Castro',
    'Danielle Baker',
    'Nicholas Ortiz',
    'Stacy Gardner',
    'Lacey Scott',
],
    'json': {
    'name': 'Robert Perez',
    'address': '89731 Jasmine Center\nJuliechester, AZ 20663',
},
    'key5755': 'value52260',
    'key90348': 'value25757',
    'key65895': 'value5294',
    'key90081': 'value65632',
    'key43803': 'value53077',
    'key44004': 'value49148',
    'key35115': 'value49091',
    'key37704': 'value32831',
    'key14431': 'value40874',
    'key39084': 'value7132',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'David Mosley',
    'address': '7530 Boyer Fields Suite 282\nGreggmouth, GU 09765',
    'text': 'North pressure garden impact.\nDebate record finally these worry common. Should scientist during certain investment store record. Relate mention him start improve change movie civil.',
    'email': 'pdavid@example.org',
    'phone_number': '001-753-941-4371x775',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ashlee Williams',
    'James Carlson',
    'Dustin Wood',
    'Donna Johnson',
    'Joshua Garcia',
    'Stephanie Sanders',
],
    'json': {
    'name': 'Daniel Jenkins Jr.',
    'address': '65455 Brown Fall Suite 403\nLarsonville, NE 69186',
},
    'key97892': 'value61528',
    'key19488': 'value62447',
    'key1637': 'value80786',
    'key3744': 'value4149',
    'key90894': 'value92872',
    'key63711': 'value34154',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jenna Allen',
    'address': '000 Jackson Square Apt. 177\nNorth Jaimeport, IL 70894',
    'text': 'Interview call find trial medical. Nature suffer too fly exist miss.\nStatement say administration pay table natural already able. Race describe student parent.',
    'email': 'mikayla55@example.org',
    'phone_number': '911-866-8842x4034',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Susan Kemp',
    'Joanna Nixon',
    'Joanna Martinez',
    'James Santos',
    'Lisa Murphy',
    'Maria Nichols',
    'Kristin Young',
    'Eric Carrillo',
    'Deborah Perez',
    'Dylan Juarez',
],
    'json': {
    'name': 'Russell Livingston',
    'address': '203 Janet Orchard\nJessicamouth, CA 78802',
},
    'key56622': 'value23714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Kristine Greene',
    'address': 'Unit 1281 Box 7886\nDPO AA 85619',
    'text': 'My weight project indeed raise commercial. Home need at grow.\nFive step consider ready onto. Price their provide although. Finish thousand office ability camera.',
    'email': 'meredithallen@example.org',
    'phone_number': '832.960.3049',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alvin Wilcox',
    'Robert Conley',
],
    'json': {
    'name': 'Jeff Wells',
    'address': '2293 Hill Unions\nVincentfort, WI 25141',
},
    'key1964': 'value47888',
    'key80547': 'value39777',
    'key18890': 'value40050',
    'key17427': 'value25955',
    'key24846': 'value59529',
    'key60997': 'value44718',
    'key69520': 'value98130',
    'key17142': 'value70142',
    'key48259': 'value81690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Courtney Campbell',
    'address': '674 Green Village Apt. 829\nEast Jeffreyberg, SD 40021',
    'text': 'Despite wall product bill situation would manager. Real fire future wide dinner.\nProduction full bag region always determine.',
    'email': 'lnoble@example.com',
    'phone_number': '+1-857-639-4248x29967',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jason King',
    'Ryan Hinton',
    'Mike Lozano',
    'Ryan Flynn',
    'Kristy Gaines',
    'Nicholas Carney',
    'Shelly Mcknight',
    'Monica Carter',
    'Mark Ward',
],
    'json': {
    'name': 'Lucas Soto',
    'address': '754 Martinez Vista Suite 833\nBrandyfort, WV 96749',
},
    'key84111': 'value34970',
    'key93659': 'value48615',
    'key82258': 'value92627',
    'key30972': 'value32687',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Lacey Swanson',
    'address': '62870 Fox Village\nNew Stephenfort, CT 41186',
    'text': 'Produce space history good author. Image difference finally girl event admit tough daughter. Discover day cold anyone final.',
    'email': 'dlarson@example.com',
    'phone_number': '001-398-895-7770x6623',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sheila Brown',
    'William Roth',
    'Mr. Alan Snow MD',
    'Michael Gray',
    'Karen Wu',
    'Patricia Vasquez',
    'Wayne Allen',
    'Ivan Hunt',
    'Bridget Roberts',
    'Renee Patton',
],
    'json': {
    'name': 'Dana Montgomery',
    'address': '30834 Gabrielle Garden Apt. 688\nEast Amandastad, WA 84388',
},
    'key22283': 'value75486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Sandy Heath',
    'address': '633 Anderson Passage\nLake Valerieside, TN 96223',
    'text': 'Hair late list suddenly. Beautiful quickly baby anything necessary west size interview.\nMission leg might others former. Those drop include already discuss. Both carry his others figure such.',
    'email': 'wilsonmatthew@example.com',
    'phone_number': '+1-615-711-4354x74474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Swanson',
    'Kelly Bean',
    'Michele Schultz',
    'Edwin Carlson',
    'Brian Hall',
],
    'json': {
    'name': 'Emily James',
    'address': '26815 Bryan Mission Apt. 266\nNew Davidville, AK 99656',
},
    'key72911': 'value91526',
    'key37760': 'value43302',
    'key21719': 'value40283',
    'key90667': 'value72305',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Shawn Valencia',
    'address': '511 West Cape Suite 807\nLawrenceville, KY 14568',
    'text': 'Remember light set. Two imagine city result. Election baby some teacher wish.\nSea others themselves ask ahead hot although. Natural statement general parent from. Ask south human.',
    'email': 'john61@example.net',
    'phone_number': '312.314.7778x3769',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Padilla',
    'Bobby Reed',
    'Jennifer Allen',
    'Robert Baker',
    'Jennifer Myers',
    'Dawn Watkins',
    'Bradley Vargas',
    'David Harris',
    'Mr. Steven Nunez Jr.',
],
    'json': {
    'name': 'Carol Mcintosh',
    'address': '068 Richard View\nScottshire, MT 04734',
},
    'key72088': 'value62307',
    'key32979': 'value94183',
    'key6525': 'value36503',
    'key44106': 'value82810',
    'key155': 'value75227',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Kathleen Lopez',
    'address': '001 Alexa Crest\nVeronicaberg, TX 28895',
    'text': 'Attention simple kid political meeting range. Industry red population century push piece number. Professor he official public American thus.',
    'email': 'mcneilangela@example.org',
    'phone_number': '001-863-487-9272x59393',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Susan Higgins',
    'Marie Gilbert',
    'Amy Khan',
    'Andrea Poole',
    'Julie Acosta',
    'Elizabeth Brown',
    'Craig Vargas',
    'Daniel Thomas',
],
    'json': {
    'name': 'Travis Orr',
    'address': '888 Angela Divide Apt. 293\nEast James, LA 67958',
},
    'key48138': 'value89871',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Nancy Rodriguez',
    'address': '9223 Wood Mews\nRobertmouth, WV 59777',
    'text': 'Current enough into inside case. Unit eight mother because many trade film.',
    'email': 'orobbins@example.com',
    'phone_number': '001-660-453-7668x396',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Martinez',
    'Charles Villegas',
    'Karen Martin',
],
    'json': {
    'name': 'Jasmine Davis',
    'address': '024 Crane Circles Apt. 104\nPowellhaven, VA 36278',
},
    'key17746': 'value74847',
    'key18784': 'value88701',
    'key98471': 'value40736',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Karen Carter',
    'address': 'USCGC Carter\nFPO AA 87021',
    'text': 'Sit expert cold door with. Modern structure bag full interesting late option. Action while develop clearly wrong each.\nVarious of ten. Almost above whether alone smile rock leave ten.',
    'email': 'william77@example.com',
    'phone_number': '233.975.8611',
    'array_int_dynamic': [
    38184,
],
    'array_varchar_dynamic': [
    'Rachel Hughes',
    'Shannon Harvey',
    'Mrs. Brooke Castillo',
],
    'json': {
    'name': 'Jennifer Chan',
    'address': '458 Hill Street\nPort Jeromeland, NJ 78542',
},
    'key49774': 'value19415',
    'key91630': 'value5996',
    'key29954': 'value35366',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Eric Torres DDS',
    'address': '9347 Franklin Loop\nRicemouth, FM 40496',
    'text': 'Arm which share. Direction cover activity own.\nSeason player order high leg both. By message something notice.',
    'email': 'norma44@example.org',
    'phone_number': '(298)285-7633x395',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Navarro',
],
    'json': {
    'name': 'Michael Taylor',
    'address': '1975 Jennifer Squares Suite 153\nWest Nicolestad, NY 74693',
},
    'key15055': 'value78793',
    'key66751': 'value26461',
    'key85565': 'value63799',
    'key53225': 'value53771',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Garrett King',
    'address': '4813 Kim Park Apt. 956\nPort Claytonfurt, FL 62520',
    'text': 'Spend job performance economy Mr likely. Sell she seat soon discuss understand fund exist.',
    'email': 'lopezanita@example.org',
    'phone_number': '+1-328-821-8634x93840',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Ferguson',
    'Dennis Sanchez',
    'Brian Espinoza',
    'Natalie Liu',
    'Brittney Peters',
    'Shane Fisher',
    'James Evans',
    'Deborah Coleman',
    'William Brown',
],
    'json': {
    'name': 'Travis Pena',
    'address': '5146 Lisa Mills\nEmilyville, FL 82689',
},
    'key15309': 'value95965',
    'key94037': 'value61042',
    'key47733': 'value1628',
    'key28066': 'value30895',
    'key21074': 'value34273',
    'key67722': 'value182',
    'key608': 'value4120',
    'key69606': 'value27936',
    'key50734': 'value69023',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Elizabeth Olson',
    'address': '612 Eileen Plain\nNew Jennifer, WY 98306',
    'text': 'Trial none letter writer. Paper month employee reveal movie. Authority country option stock central effect reason.\nLanguage small his. Industry top final garden project administration.',
    'email': 'rodriguezalexandra@example.com',
    'phone_number': '725-307-1594x81235',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard White',
    'Stephen Reed',
    'Olivia Smith',
    'Rebecca Barber',
    'Matthew Contreras',
    'Michael Fleming',
],
    'json': {
    'name': 'Morgan Lopez',
    'address': '840 Pittman Lake\nEast Mariamouth, GA 18181',
},
    'key66250': 'value18442',
    'key70451': 'value54120',
    'key56356': 'value84739',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Rachel Sloan',
    'address': '9308 Mark Corners Apt. 724\nSouth Jasonville, KS 31190',
    'text': 'Sell method number community. End military impact operation wonder city over. Thought rise religious side red figure.',
    'email': 'ologan@example.net',
    'phone_number': '+1-908-792-3656x752',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Jones',
    'Michael Joseph',
    'Tiffany Dixon',
    'Glenda Johnson',
    'David Berry',
    'Ricky Edwards',
    'Allison Jones',
    'Michele Lucero',
    'Victor Wilson',
],
    'json': {
    'name': 'Jesse Lee',
    'address': '614 Joseph Tunnel Apt. 599\nNew Sean, TN 62585',
},
    'key67632': 'value67481',
    'key41760': 'value46300',
    'key33172': 'value3517',
    'key53227': 'value73475',
    'key95605': 'value73387',
    'key7568': 'value42579',
    'key3762': 'value81781',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Tara Robinson',
    'address': '49055 Nicholas Plaza Apt. 629\nRyanhaven, OR 56890',
    'text': 'Child daughter edge inside movie account southern. Sister tonight president nothing. Financial writer fire strong part soon data.',
    'email': 'brightmichelle@example.net',
    'phone_number': '837-635-6093x380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Malik Davis',
    'Patricia Rich',
    'Amanda Rodriguez',
    'Alexander Atkins',
    'Debbie Leblanc',
    'Megan Sanford',
    'Calvin Sawyer',
    'Amy Adams',
    'Michael Johnson',
    'Sean Morris',
],
    'json': {
    'name': 'Taylor Francis',
    'address': '9954 Jennifer Stravenue Apt. 170\nPhillipberg, PR 21913',
},
    'key70427': 'value62583',
    'key75542': 'value58035',
    'key74022': 'value52009',
    'key44471': 'value18746',
    'key77802': 'value71372',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Kevin Hudson',
    'address': '63748 Valencia Pine Suite 326\nRussoton, VT 51044',
    'text': 'Both word total career trouble economic. Ok similar tax most. Summer then majority goal. Yes anyone sure mouth book especially.\nClear probably her positive product. Religious dream leader.',
    'email': 'tgill@example.net',
    'phone_number': '550-515-3859x97805',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michael Schwartz',
    'James Moore',
    'Mrs. Jennifer Chan',
    'Mr. Michael Watson',
],
    'json': {
    'name': 'John Stanley',
    'address': '77440 Carpenter Mount\nPaulfurt, NH 23203',
},
    'key50937': 'value65919',
    'key47717': 'value5533',
    'key26334': 'value1415',
    'key85836': 'value4046',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Brett Garner',
    'address': '235 Rodriguez Alley\nBobbyshire, LA 52266',
    'text': 'For bit put occur support animal against. Once gun another successful someone whatever.',
    'email': 'jensenzoe@example.org',
    'phone_number': '(938)938-2591',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tonya Davis',
    'Rebecca Garner',
    'Dr. Stephanie Cantu',
    'Deborah Koch',
    'Melinda Shaw',
    'Nicholas Banks',
    'Timothy Lowery',
    'Andrew Franklin',
    'Kimberly Hale',
    'Dylan Durham',
],
    'json': {
    'name': 'Zachary Martin',
    'address': '691 Lee Springs\nNorth Karenberg, PR 21199',
},
    'key69835': 'value4553',
    'key79302': 'value84414',
    'key481': 'value10403',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Stephanie Joyce',
    'address': '471 Kayla Loaf Suite 809\nEast Philipside, IL 59723',
    'text': 'Appear address ability. Avoid the kind clear few. Cup firm science enjoy.\nCapital subject dinner. Base firm husband simply fish. Organization ago until certain reduce.',
    'email': 'hessjulia@example.org',
    'phone_number': '(384)599-9672x2842',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Barker',
    'Thomas Yoder',
    'Cody Neal',
    'Harry Peters',
    'Angela Ford',
    'Christy Wilson',
    'Tammie Conrad',
    'Steven Shannon',
    'Antonio Rhodes',
    'Scott George',
],
    'json': {
    'name': 'Marvin White',
    'address': '5928 Bailey Trace\nBakerton, GU 97570',
},
    'key77630': 'value71624',
    'key91539': 'value95843',
    'key91685': 'value2359',
    'key54519': 'value6946',
    'key2021': 'value1871',
    'key96642': 'value67455',
    'key97697': 'value12121',
    'key86756': 'value63733',
    'key98931': 'value59671',
    'key11310': 'value39976',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Earl Hayes',
    'address': '9034 Cathy Junction\nMariaside, WV 21864',
    'text': 'Draw land end left key. Modern special task south. Bar assume painting production energy.',
    'email': 'gonzalezjoshua@example.net',
    'phone_number': '637-867-5106x5708',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'April Vazquez',
    'Robert Neal',
],
    'json': {
    'name': 'Jeffrey Allen',
    'address': '996 Bishop Cove\nBrittanyport, NE 17056',
},
    'key48775': 'value94705',
    'key27891': 'value99988',
    'key72596': 'value93261',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Lauren Rivera',
    'address': '1188 Lara Dale Apt. 014\nSalinasfurt, NJ 96151',
    'text': 'Move course pressure indicate. Alone somebody sometimes technology. Office senior condition sure fact side democratic. Sure safe activity sense collection.',
    'email': 'joseph62@example.com',
    'phone_number': '891-366-5095x60291',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Trevino',
    'Tom Boyd',
    'Stephen Hale',
    'Nicole Mcbride',
],
    'json': {
    'name': 'James Smith',
    'address': '33792 Veronica Green Suite 010\nNew William, NH 71859',
},
    'key15112': 'value43795',
    'key63460': 'value71551',
    'key79399': 'value86203',
    'key53440': 'value69849',
    'key83293': 'value7396',
    'key8811': 'value2134',
    'key91799': 'value50791',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Stacey Schmidt',
    'address': '5594 Salazar Isle Suite 224\nLake Williebury, TN 79654',
    'text': 'Item central green message join cover unit. Drop development drive it easy. Include player kind easy create quality marriage.',
    'email': 'burkekathy@example.org',
    'phone_number': '677.326.5542x260',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Richard Garcia',
    'Wendy Allen',
    'Jeff Collins',
    'Anthony Burnett',
],
    'json': {
    'name': 'Christine Harrell',
    'address': '360 Steven Place Suite 902\nCardenasmouth, MT 38819',
},
    'key64791': 'value30841',
    'key18013': 'value52971',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Brandi Foster',
    'address': '983 Hannah Glen Suite 249\nBrownton, NV 43110',
    'text': 'Message place son yard agreement throw. Democratic finish step middle around training pass wish. Throw truth she goal every believe.\nStep have cold green somebody none. Compare short another camera.',
    'email': 'cruzamanda@example.com',
    'phone_number': '996-463-0076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Lewis',
    'Larry Gonzales',
    'Brandon Bullock',
    'Chelsey Robles',
    'Lauren Castillo',
    'Bryan Byrd',
],
    'json': {
    'name': 'Ronald Fowler',
    'address': '8600 Clinton Forge Suite 372\nRosalesfort, VA 51613',
},
    'key3367': 'value86864',
    'key35110': 'value31045',
    'key242': 'value18951',
    'key74807': 'value78291',
    'key80483': 'value94409',
    'key51870': 'value87326',
    'key90604': 'value61705',
    'key73474': 'value40756',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Troy York',
    'address': '876 Williams Mountains Apt. 794\nEast Brookeland, WI 59731',
    'text': 'Life force major evidence. Behind when then middle door. Loss box produce product wish enter. Ready cover spring type west report fall should.',
    'email': 'tracierobles@example.com',
    'phone_number': '6762536397',
    'array_int_dynamic': [
    15212,
],
    'array_varchar_dynamic': [
    'Matthew Castro',
    'Deborah Thomas',
    'Jesus Green',
    'Phillip Cooper',
    'Mary Carter',
    'Julia Huerta',
    'Sharon Robles',
    'Ryan Fields',
    'Frank Ferguson',
],
    'json': {
    'name': 'Amanda Webster',
    'address': 'USCGC Davies\nFPO AP 60787',
},
    'key98339': 'value22340',
    'key88149': 'value55437',
    'key94779': 'value7514',
    'key91410': 'value19929',
    'key65653': 'value17894',
    'key40308': 'value27958',
    'key3886': 'value6419',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Pam Jenkins',
    'address': '711 Davis Pass\nSouth Darylfort, NE 67612',
    'text': 'Network continue to according land rise increase plant. Tree off also plant admit. Happy air decision rise hot phone theory.',
    'email': 'awalker@example.org',
    'phone_number': '377.822.7570',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Cory Williams',
    'Michael Flynn',
    'Charles Warren',
    'Matthew Jackson',
    'Felicia Galloway',
],
    'json': {
    'name': 'Travis Griffin',
    'address': '381 Charles Fords\nLake Valerieberg, MP 48148',
},
    'key98708': 'value57902',
    'key336': 'value48632',
    'key63039': 'value48744',
    'key21550': 'value72497',
    'key6201': 'value65807',
    'key6702': 'value15453',
    'key30448': 'value4442',
    'key24110': 'value23665',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Tanner Thompson',
    'address': '5993 Mitchell Falls Apt. 659\nNorth Tonymouth, CT 31594',
    'text': 'Bag pattern single position site. Indeed side tax size short ready production. Law fire especially month situation plan.\nFrom wish civil weight try.',
    'email': 'zflores@example.org',
    'phone_number': '(778)812-0678x024',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Charlene Weaver',
    'Tyler Wilson',
    'Andrea Castro',
    'Natalie Thompson',
],
    'json': {
    'name': 'Jennifer Taylor',
    'address': '07448 Burke Station\nNew Carl, GU 44210',
},
    'key76638': 'value61063',
    'key57006': 'value93947',
    'key88056': 'value24211',
    'key85755': 'value25945',
    'key89893': 'value31795',
    'key92139': 'value29017',
    'key32652': 'value80843',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Janet Flores',
    'address': '317 Alexander Isle Apt. 667\nWest Christopherstad, ME 84952',
    'text': 'Reach system her loss identify light. Season painting four theory our real.\nFill seek lay term increase different store. Show protect gun upon.',
    'email': 'haasdavid@example.net',
    'phone_number': '001-477-514-4602x370',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Thomas',
    'Matthew Henson',
],
    'json': {
    'name': 'Cory Lopez',
    'address': '7144 Chan Forge Suite 160\nNorth Danielleshire, IL 78751',
},
    'key70236': 'value11233',
    'key28661': 'value82270',
    'key89929': 'value65340',
    'key86134': 'value62522',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'James Cooper',
    'address': '482 Moore Village\nNew Kristopher, IN 62909',
    'text': 'How relate director could few.\nWant organization red. Thing tough organization perform.\nProduce man contain could physical. Figure upon structure cultural.',
    'email': 'ramosmike@example.org',
    'phone_number': '320-405-0776',
    'array_int_dynamic': [
    71122,
],
    'array_varchar_dynamic': [
    'Daniel Powell',
    'Patricia Rose',
    'Kevin Carter',
    'Matthew Webb',
    'James Young',
    'Marvin Mcmillan',
    'Kristy Lambert',
],
    'json': {
    'name': 'Jose Sanchez',
    'address': '55529 Wise Place Apt. 226\nCoryburgh, MP 52948',
},
    'key42867': 'value82625',
    'key92773': 'value20515',
    'key6050': 'value46754',
    'key4235': 'value78510',
    'key58620': 'value1157',
    'key67828': 'value92602',
    'key28389': 'value26025',
    'key20545': 'value33807',
    'key68334': 'value3640',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Sonya Kelley',
    'address': '732 Rebecca Locks\nMalonebury, IN 01136',
    'text': 'Go her professor process authority collection morning. Wall she impact development shoulder section whether. Approach but example toward choice.\nKid interesting fish would responsibility.',
    'email': 'jlawrence@example.net',
    'phone_number': '001-759-802-3973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'John Riley',
    'Kristen Holloway',
    'Brittany Guerrero',
    'Renee Townsend',
    'Audrey Hamilton',
    'Tamara Branch',
    'Alexandra Oconnor',
],
    'json': {
    'name': 'Jeffrey Lee',
    'address': '79773 Graham Corner Suite 165\nBenjaminburgh, ND 42437',
},
    'key69844': 'value17518',
    'key73189': 'value81201',
    'key48470': 'value34601',
    'key33433': 'value27530',
    'key34531': 'value93927',
    'key14592': 'value34410',
    'key43254': 'value60856',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Alicia Norton',
    'address': '39689 Dustin Ford Apt. 000\nPort Patrick, KS 55181',
    'text': 'Where the garden community economic. Movement air human kind can management religious.',
    'email': 'csmith@example.org',
    'phone_number': '(794)211-3565',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Hayley Cunningham',
    'Victoria Campbell',
    'Tiffany Berry',
    'Ryan Smith',
    'John Carpenter',
    'Samantha Love',
    'Monique Wright',
    'Cheryl Francis',
    'Christina Clark',
],
    'json': {
    'name': 'Thomas Thompson',
    'address': '518 David Streets\nSouth Joshua, KY 80852',
},
    'key32298': 'value16067',
    'key91570': 'value18693',
    'key33402': 'value61470',
    'key83857': 'value94770',
    'key224': 'value53173',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Isaiah Perry',
    'address': '47370 Wallace Canyon\nSouth Aaronside, HI 60422',
    'text': 'Important world student protect. Leader color join back magazine avoid official. Later young military list protect.',
    'email': 'nhaynes@example.org',
    'phone_number': '001-915-520-0853x75426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Anne Potter',
],
    'json': {
    'name': 'Glenn Taylor',
    'address': 'Unit 4677 Box 7497\nDPO AE 99681',
},
    'key58170': 'value33569',
    'key16611': 'value93580',
    'key71825': 'value51068',
    'key31232': 'value41182',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Justin Moore',
    'address': '61283 Marcus Unions\nNorth Amy, NH 32640',
    'text': 'Beat agency piece. Talk letter agency person us factor author either.\nSimply several stock. Letter perform back continue and imagine. Degree door realize should during.',
    'email': 'bmorgan@example.org',
    'phone_number': '822-438-8427',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Cantu',
    'David Holder',
    'Claudia Thomas',
    'Amber Williams',
    'Taylor Parrish',
    'Jessica Rowe',
    'Jessica Johnson',
    'Veronica Gibson',
    'Amanda Hayes',
    'Daniel Marks',
],
    'json': {
    'name': 'Christina Brown',
    'address': '2240 Collins Trace\nCastanedaton, IL 35398',
},
    'key92642': 'value23107',
    'key8888': 'value94485',
    'key7142': 'value33941',
    'key43422': 'value2836',
    'key49313': 'value61091',
    'key16329': 'value35044',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jamie Franco',
    'address': '886 Thompson Plaza Apt. 742\nNorth Rachel, VA 70651',
    'text': 'Buy wait fire modern population take. Decade approach huge place site.\nRelate field concern station bank defense officer. Story choose never anyone bill attorney enough. Pay answer artist western.',
    'email': 'fitzgeraldgilbert@example.com',
    'phone_number': '5584107900',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Leonard',
    'Nicole Hunt',
    'Jessica Moore',
    'Ethan Berry',
],
    'json': {
    'name': 'Andrew Graham',
    'address': 'USNV Davis\nFPO AP 19996',
},
    'key48329': 'value44308',
    'key47230': 'value52349',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Jonathan Thompson',
    'address': '0705 Hodge Parks\nEast Andrewborough, CA 43417',
    'text': 'Must media allow line usually. She order food debate serve.\nMeet campaign road pattern national. Treatment possible begin figure small. Return minute seek rise force forward how national.',
    'email': 'amy00@example.com',
    'phone_number': '001-208-740-1268',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Mora',
    'Sherry Mccullough',
    'Anthony Mccarthy',
    'Barbara Pitts',
],
    'json': {
    'name': 'Amy White DDS',
    'address': '061 Donna Mill\nWest Lawrence, TN 41037',
},
    'key34384': 'value18725',
    'key8140': 'value70601',
    'key17651': 'value1696',
    'key81657': 'value69679',
    'key76412': 'value89547',
    'key2473': 'value28802',
    'key9775': 'value92216',
    'key62462': 'value10288',
    'key26231': 'value47271',
    'key68622': 'value54927',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Stephen Kelly',
    'address': '089 Roberts Dam Apt. 947\nRonniehaven, GU 01067',
    'text': 'Laugh thing chair explain purpose former beautiful. Interview spend fine southern better as on.\nAir since design start whole where another. Ask still game. Fine do mention laugh.',
    'email': 'hancockmelissa@example.org',
    'phone_number': '(895)246-5749',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Laura Nixon',
    'Raymond Newman',
    'Stacey Hughes',
    'Joseph Frost',
    'Mark Jacobs',
    'Ronald Vasquez',
    'Hector Patterson',
    'Rachel Swanson MD',
    'Devon Lopez',
],
    'json': {
    'name': 'Madison Haley',
    'address': '39419 Smith Plains Apt. 995\nPort Justin, IL 81769',
},
    'key64817': 'value25261',
    'key16801': 'value69060',
    'key94594': 'value94943',
    'key34998': 'value5012',
    'key15158': 'value31629',
    'key30511': 'value2296',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Cynthia Castillo',
    'address': '6093 Martinez Throughway Apt. 523\nMelissaland, ID 73196',
    'text': 'Everybody send size stand.\nMovie send job. Moment always executive station. Race choose continue society oil gun significant.',
    'email': 'brandon74@example.org',
    'phone_number': '+1-504-373-1364x5350',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Orr',
    'George Mcclain',
    'Jennifer Francis',
    'Thomas Cole',
],
    'json': {
    'name': 'Vanessa Mitchell',
    'address': '68079 Becker Via Apt. 165\nWest Maryfurt, NV 26274',
},
    'key23599': 'value70952',
    'key22675': 'value51030',
    'key66095': 'value46350',
    'key46466': 'value36396',
    'key98634': 'value48055',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Linda Mckinney',
    'address': '0996 Moreno Inlet Suite 889\nBushside, FL 76527',
    'text': 'Science particular phone financial. Great every popular myself which. Move various understand blue chance particularly hear five.',
    'email': 'emily95@example.net',
    'phone_number': '(965)741-9445x90803',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Beard',
    'Jennifer Lopez',
    'Maria Pierce',
    'Nicole Harris',
    'Laura Murillo',
    'Jordan Sullivan',
    'Pamela Mcguire',
    'Rebecca Thomas',
    'Elizabeth Howard',
],
    'json': {
    'name': 'Brianna Oneal',
    'address': '96984 Jared Isle\nPort Loribury, RI 65760',
},
    'key1107': 'value82030',
    'key62256': 'value78603',
    'key36513': 'value18709',
    'key13728': 'value29714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Andrew Freeman',
    'address': 'PSC 9325, Box 2106\nAPO AP 39168',
    'text': 'Never realize single chair we various. Run including team major agent election world. View interest usually teach catch.\nParty have they front eight those.',
    'email': 'justin73@example.org',
    'phone_number': '+1-532-816-3130x0257',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Meza',
    'Elizabeth Jacobs',
    'Sandra Ramirez',
    'Angela Willis',
    'Sean Kline',
    'Vincent Gonzalez',
    'Brian Mitchell',
],
    'json': {
    'name': 'Ashley Taylor',
    'address': '7432 Wallace Oval\nSmithtown, VI 80191',
},
    'key72393': 'value29335',
    'key66312': 'value60382',
    'key85014': 'value33809',
    'key69214': 'value751',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Michael Townsend',
    'address': '733 Pierce Island Apt. 041\nNew Gregoryshire, DC 47606',
    'text': 'Human soldier discussion. Do relationship must instead rate program. Ground meeting address whole cover. Ability outside audience brother not wall include foreign.',
    'email': 'carrie89@example.org',
    'phone_number': '001-525-384-9138',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jackie Wells',
    'Amy Rodriguez',
    'Tony Rodriguez',
],
    'json': {
    'name': 'Patricia Butler',
    'address': 'USS Martin\nFPO AE 37906',
},
    'key3121': 'value46588',
    'key33233': 'value15590',
    'key82295': 'value340',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Eric Hill',
    'address': 'USS Anderson\nFPO AP 72140',
    'text': 'Score half successful. Ball positive visit the western party.\nCard move final husband fund throughout they wonder. Surface rock level seven color. Help head brother successful so name.',
    'email': 'mccoyjessica@example.org',
    'phone_number': '+1-329-249-0180',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amanda West',
    'Melissa Stone',
],
    'json': {
    'name': 'David Lopez',
    'address': '123 Joe Union\nWest Benjamin, WY 82550',
},
    'key45385': 'value88555',
    'key1945': 'value53625',
    'key15612': 'value644',
    'key80697': 'value53316',
    'key57016': 'value76306',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jennifer Dyer',
    'address': '158 Johnson Lights\nSouth Leahfurt, WA 76048',
    'text': 'Government product security fast less. Dark worry building fund produce parent goal. Room direction heavy might by north.',
    'email': 'mitchellbradley@example.org',
    'phone_number': '001-298-354-5729',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Smith',
    'Joseph Bradley',
    'Sharon Shaw',
    'Juan Odonnell',
    'Michelle Smith',
    'Monica Gilbert',
],
    'json': {
    'name': 'Brian Cherry',
    'address': '6574 Matthew Key Apt. 966\nPort Brooke, RI 28109',
},
    'key56521': 'value94855',
    'key16221': 'value26980',
    'key43680': 'value98763',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Danielle Morales',
    'address': '86104 Kathleen Fields\nBoltontown, RI 97097',
    'text': 'Full new key peace peace option member. Move view eye relationship concern. Senior organization for always next member understand yet.',
    'email': 'mercedesowens@example.org',
    'phone_number': '(236)620-3613',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Erica Manning',
    'Beverly Bailey',
    'Rebecca Walker',
    'Sherry Perry',
    'Alexandra Wright',
    'Renee Nicholson',
    'Richard Pierce',
    'Hunter Mcneil',
],
    'json': {
    'name': 'Jessica Payne',
    'address': '530 Barker Drive\nSmallbury, WI 46826',
},
    'key12329': 'value86428',
    'key42385': 'value60451',
    'key24431': 'value87877',
    'key46622': 'value38526',
    'key29578': 'value87327',
    'key3528': 'value42837',
    'key15968': 'value15533',
    'key17389': 'value15507',
    'key27184': 'value14726',
    'key14308': 'value6928',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Donald Thompson',
    'address': '1901 Vasquez Junctions\nClarkfort, OR 40586',
    'text': 'Risk dinner bit improve today respond. Real couple know head after significant. Single usually health bed green analysis.\nFood health trade song. Support check economy forget rule check.',
    'email': 'connermeredith@example.com',
    'phone_number': '+1-337-446-3829',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Cole',
    'Benjamin Harrington',
    'Beverly Olson',
],
    'json': {
    'name': 'Kelly May',
    'address': '5291 Burgess Rapids\nSouth James, GA 49374',
},
    'key92256': 'value46427',
    'key99807': 'value57835',
    'key85631': 'value98580',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Ashley Rivera',
    'address': '959 Lisa Field Apt. 850\nMileshaven, WA 44852',
    'text': 'What street lay of. Final role put interest article skill.\nUse film realize technology must. Prove kid area some bad than.\nExpert follow sing fine job hair trouble. Answer cold against morning far.',
    'email': 'simsjeremy@example.org',
    'phone_number': '001-656-507-7975x35855',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Dean Valdez',
    'Todd Harrington',
    'Jennifer Cortez',
    'Brandon Contreras',
],
    'json': {
    'name': 'Brittany Galloway',
    'address': '6472 Lucas Stravenue Apt. 615\nAlfredmouth, MH 66307',
},
    'key9415': 'value53315',
    'key20187': 'value24460',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Kevin Giles',
    'address': '3710 Matthew Track Apt. 467\nNorth Amy, SC 43464',
    'text': 'Should play practice manage off box nor. Place senior author training stock exist. Use any natural word short leg traditional.\nAdd meeting common specific. Choose fly nothing cold challenge southern.',
    'email': 'sherrimaxwell@example.org',
    'phone_number': '(321)619-5998',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Garcia',
    'Donald Chandler',
    'Tracy Rogers',
],
    'json': {
    'name': 'Paula George',
    'address': '16463 Stacy View\nPort David, MH 12935',
},
    'key43495': 'value85797',
    'key17581': 'value17641',
    'key70751': 'value50215',
    'key69065': 'value87054',
    'key12832': 'value32648',
    'key66724': 'value29614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Jennifer Horn',
    'address': '20659 Hansen Land\nPort Deborah, RI 44244',
    'text': 'Sound kitchen imagine if. Poor road policy since brother. Prevent shake man trouble join every.',
    'email': 'armstrongpaula@example.net',
    'phone_number': '001-978-951-3210x993',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Johnson',
    'Mr. James Stephens PhD',
    'Alisha Williams',
    'Sandra Pierce',
],
    'json': {
    'name': 'Danielle Martin',
    'address': '78379 Coffey Branch\nShafferfurt, FM 02052',
},
    'key10604': 'value87380',
    'key84846': 'value85346',
    'key39645': 'value44849',
    'key65404': 'value58987',
    'key75374': 'value28487',
    'key96391': 'value80840',
    'key65734': 'value63162',
    'key41516': 'value61980',
    'key58943': 'value8660',
    'key86661': 'value82687',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Gina Taylor',
    'address': '229 Jeffrey Centers Apt. 629\nGilberthaven, OR 39171',
    'text': 'Cold bit feeling either. Bad benefit hear through. Skin accept pressure race toward bill.\nSell manager adult break. Sense could guy.',
    'email': 'bmartinez@example.net',
    'phone_number': '001-710-576-4096',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Billy Ball',
    'Vanessa Martin',
    'Matthew Fletcher',
],
    'json': {
    'name': 'Daniel Gentry',
    'address': 'USNV Contreras\nFPO AP 69844',
},
    'key54697': 'value14972',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Amy Graham',
    'address': '25919 Cathy Mountains\nFrankbury, WY 04029',
    'text': 'Start manage factor necessary fact. Race outside describe site control picture scene here. Father behind my similar bank. Here ago do bag federal recent.',
    'email': 'hbaker@example.net',
    'phone_number': '253.213.5787',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jacqueline Good',
    'John Lane',
    'Kimberly Gardner',
    'Mark Zavala',
    'Nancy Walton',
    'Christina Jackson',
    'Rebecca Butler',
    'Jackson Wilson',
    'Jasmine Moore',
],
    'json': {
    'name': 'April Peterson',
    'address': '013 Ann Heights\nNew Crystal, MH 12791',
},
    'key8498': 'value18444',
    'key46753': 'value33063',
    'key29014': 'value32755',
    'key2368': 'value61221',
    'key9405': 'value77442',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Elizabeth Bradford',
    'address': '583 Walker Burg Apt. 636\nSmithmouth, AR 05127',
    'text': 'Record memory represent wind. Near born however. Leg time wait you him into.\nOutside eight purpose medical clear mind expect. Recently road home study financial black total. Interest late those.',
    'email': 'shafferwilliam@example.net',
    'phone_number': '801-209-8385x8329',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'William Reeves',
    'Abigail Leonard',
    'Gregory Knapp DDS',
],
    'json': {
    'name': 'Jacqueline Lane',
    'address': '52225 Patricia Pines\nAmyburgh, MO 36922',
},
    'key13481': 'value72476',
    'key95939': 'value68628',
    'key86825': 'value69755',
    'key60620': 'value13267',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v1/vector/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '811255f1-62f0-11f0-bdec-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_29_07_233303yaeXcHvW',
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'outputFields': [
    'phone_number',
    'name',
    'email',
    'json',
    'uid',
    'array_varchar_dynamic',
    'address',
    'text',
    'array_int_dynamic',
],
    'filter': 'uid >= 0',
    'limit': 1,
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
    'RequestId': '81b0e0b4-62f0-11f0-ba8e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_29_07_233303yaeXcHvW',
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
    'RequestId': '7d4ca87a-62f0-11f0-a446-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_29_07_233303yaeXcHvW',
    'dimension': 128,
    'metricType': 'IP',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_complex_payload[IP-1-0-2]_1752744555.json')
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
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithComplexPayloadIp1021752744555Json()
    test.run_tests()
