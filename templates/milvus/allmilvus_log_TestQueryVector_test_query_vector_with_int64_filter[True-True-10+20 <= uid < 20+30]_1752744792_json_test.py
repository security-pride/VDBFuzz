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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752744792_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752744792.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrue1020Uid20301752744792Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752744792.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752744792.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '082d7d8f-62f1-11f0-b4f9-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_00_232356WVzixqFd',
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
    'RequestId': '0b4be276-62f1-11f0-b538-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_00_232356WVzixqFd',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'James Watts',
    'address': '168 Timothy Glens Suite 748\nEast Rachelburgh, ND 93921',
    'text': 'Everybody herself husband another never president. Often describe third important where weight material popular.\nAddress measure work.',
    'email': 'jasonsmith@example.com',
    'phone_number': '982.779.0871',
    'array_int_dynamic': [
    59042,
],
    'array_varchar_dynamic': [
    'Diana Jones',
    'Christine Warren',
    'Debra White',
    'Leslie Gray',
    'John Kirk',
    'Henry Jones',
],
    'json': {
    'name': 'Maurice Pena',
    'address': '439 Ryan Tunnel Suite 385\nTamifurt, GU 15161',
},
    'key5432': 'value41956',
    'key82205': 'value86250',
    'key78017': 'value23821',
    'key16343': 'value93140',
    'key74330': 'value43234',
    'key88': 'value5129',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Jonathan Bennett',
    'address': '353 Greg Divide Suite 151\nWest Davidport, AR 13426',
    'text': 'Other sound choice so. Suggest during cup add much move. Walk past determine staff anyone kitchen.',
    'email': 'bscott@example.com',
    'phone_number': '+1-572-375-2139x544',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Meghan Lewis',
    'Raymond Walsh',
    'Dawn Brooks',
    'Daniel Weber',
    'Scott Love',
    'Ryan Conrad',
    'Dustin Martin',
    'Cameron Robinson',
],
    'json': {
    'name': 'Richard Cortez',
    'address': '50781 Harris Drive Apt. 731\nChanville, MA 52118',
},
    'key97641': 'value67353',
    'key60318': 'value32017',
    'key45180': 'value17162',
    'key88283': 'value10086',
    'key46839': 'value13704',
    'key56322': 'value67415',
    'key58060': 'value68647',
    'key54019': 'value32169',
    'key31157': 'value18983',
    'key19267': 'value29062',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Kevin Ewing',
    'address': '030 Jennifer Fork Suite 260\nSchultzfurt, FL 97157',
    'text': 'Team party exist agency. Pick but eye of hit everybody top.\nIt central cold forward prove. Box seem carry response activity short.',
    'email': 'joshuakeith@example.com',
    'phone_number': '+1-632-925-1972x84343',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Chad Fitzpatrick',
    'Rhonda Davis MD',
    'Jessica Miller',
],
    'json': {
    'name': 'Eric Conner',
    'address': '9484 Nixon Circle\nWest Carla, NY 97525',
},
    'key86373': 'value57780',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Lee Myers',
    'address': '96830 Galvan Pass\nSouth Antonioton, FL 49594',
    'text': 'Police community boy bit art matter. Body score old thus away entire bag.\nThat law important help west. So speak spend single shoulder feel.',
    'email': 'knappcrystal@example.org',
    'phone_number': '274.233.9190x6627',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mark Spencer',
    'Robert Payne',
    'Amy Berg',
    'Pamela Wiggins',
    'Sarah Watson',
    'Richard Morales',
    'Connie Meza',
    'Michael Hernandez',
    'Vanessa Mendez',
    'Daniel Wallace',
],
    'json': {
    'name': 'Sara Gamble',
    'address': '68370 Christine Springs Apt. 827\nNorth Samuelside, WA 60528',
},
    'key39405': 'value29047',
    'key60432': 'value23564',
    'key20370': 'value23917',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Eric Stone',
    'address': '733 Grant Alley\nJamesborough, CO 85478',
    'text': 'Glass majority agent speech indicate bring. When person among.\nBuy they research believe job. Work season here production picture. Care military religious population in leader face.',
    'email': 'edwardssergio@example.org',
    'phone_number': '358.946.9702x67174',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Erin Rodriguez',
],
    'json': {
    'name': 'Alice Stone',
    'address': 'USCGC Garcia\nFPO AA 22288',
},
    'key46111': 'value32779',
    'key55947': 'value23142',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Ashley Brooks',
    'address': '591 Mark Throughway Apt. 806\nLeeside, NM 17337',
    'text': 'Remain large talk. Free rock without truth big.\nGo down who system somebody last popular. Health although property night him require. Another season stock protect PM.',
    'email': 'wilsonjoshua@example.net',
    'phone_number': '+1-786-620-9882',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jon Miller',
    'Daniel Olsen',
],
    'json': {
    'name': 'Jill Cruz',
    'address': '687 Amber Mills Suite 680\nNorth Jonathanhaven, UT 61104',
},
    'key17967': 'value24407',
    'key50227': 'value34657',
    'key72555': 'value81847',
    'key62750': 'value76463',
    'key19753': 'value3621',
    'key7563': 'value91835',
    'key86879': 'value66719',
    'key66801': 'value11975',
    'key93895': 'value50642',
    'key25215': 'value39781',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Wesley Zavala',
    'address': '9231 Cruz Bypass\nNorth Leonardtown, OH 12849',
    'text': 'First firm PM forward. Enough listen brother over.\nSport travel follow able likely young campaign. World push add early perhaps science opportunity. Hot dark politics include visit.',
    'email': 'barbaraross@example.net',
    'phone_number': '+1-983-629-4025x9206',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Garner',
    'Emily Kramer',
    'Susan Lane',
    'Kevin Mahoney',
    'Lawrence Cox',
    'Donna Williams',
],
    'json': {
    'name': 'Morgan Cooper',
    'address': '46925 Richard Parkways\nLake Travis, GU 38438',
},
    'key63755': 'value57522',
    'key52133': 'value5377',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jeremy Rice',
    'address': '16015 Gutierrez Brooks\nSotostad, NM 51061',
    'text': 'Action likely put something. Everybody without prepare work while later. Yeah let industry yard product.',
    'email': 'kenneth94@example.org',
    'phone_number': '695.794.1556',
    'array_int_dynamic': [
    46387,
],
    'array_varchar_dynamic': [
    'Valerie White',
    'Cassandra Mckinney',
],
    'json': {
    'name': 'Jeffrey Morgan',
    'address': '767 Danny Square\nAngelaborough, AS 15471',
},
    'key70328': 'value41045',
    'key79213': 'value95793',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Zachary Key',
    'address': '65533 Greene Brooks\nPort Jason, DE 28769',
    'text': 'Night brother prepare your experience specific tend. Catch visit dog high matter support in. Begin meeting too glass wear feel second.',
    'email': 'pattersonkristin@example.net',
    'phone_number': '+1-264-263-1616x94014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Sanders',
    'Nancy Jackson',
    'Michelle Hansen',
    'Karina Atkins',
    'Tina Burke',
    'Jordan Mercado',
    'Nicole Barnett',
    'Anthony Burgess',
    'Deborah Ferguson',
],
    'json': {
    'name': 'Alicia Jones',
    'address': 'Unit 2110 Box 7376\nDPO AE 91791',
},
    'key41606': 'value78296',
    'key50090': 'value38937',
    'key53030': 'value76260',
    'key53745': 'value55656',
    'key85471': 'value30746',
    'key6240': 'value7575',
    'key9390': 'value90881',
    'key99228': 'value22189',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Paul Wong',
    'address': '443 Bailey Knolls\nBrownberg, WY 96173',
    'text': 'Participant many owner inside identify sing for.\nSituation admit moment. Federal mention person future.\nEspecially game early crime far. Although those answer their.',
    'email': 'tbenton@example.com',
    'phone_number': '(371)842-9356x183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Barton',
    'John Marshall',
    'Chad Ross',
    'Peter Nunez',
    'Brandy Obrien',
    'Gerald Ferrell',
    'Diana Cook',
],
    'json': {
    'name': 'Sara Mayo',
    'address': '8856 Marie Squares\nWest Matthewborough, GA 96007',
},
    'key72625': 'value92603',
    'key47463': 'value86016',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Thomas Christensen MD',
    'address': '815 Anderson Hills Apt. 410\nAyalahaven, MS 71235',
    'text': 'Speech space tough fish world any number. Open could research total.\nSeven far send pattern size kind art federal. Yes wear step risk. Natural save make lose network attack cover every.',
    'email': 'suzannecole@example.org',
    'phone_number': '(440)790-2220x398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Rodriguez',
    'Kevin James',
    'Christopher Macias',
    'Vickie Torres',
    'Casey Allen',
],
    'json': {
    'name': 'Carolyn Mills',
    'address': '5581 Dixon Cape Suite 977\nGloriaton, TX 92961',
},
    'key57705': 'value59858',
    'key79240': 'value26815',
    'key86476': 'value31910',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Rebecca Adams',
    'address': '53467 Erin Flats\nSouth Paul, KS 62529',
    'text': 'Sort remember difficult significant move rest certainly. Score forget these mission American ago anyone. President relate important letter budget. According job trouble day.',
    'email': 'amandaward@example.net',
    'phone_number': '251.762.9581',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Ward',
],
    'json': {
    'name': 'Amanda Turner',
    'address': '3093 Lisa Path\nNew Jessica, MH 40244',
},
    'key27720': 'value79673',
    'key61658': 'value49385',
    'key4630': 'value86001',
    'key74954': 'value1352',
    'key90243': 'value7140',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Heather Washington',
    'address': '109 Walter Drives\nLake Marc, AS 19507',
    'text': 'Mrs care food shoulder. Newspaper level red authority we back technology candidate. Project involve hour usually term word husband.',
    'email': 'theodore82@example.com',
    'phone_number': '849.943.0985',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Heather Anderson',
],
    'json': {
    'name': 'Jessica Brown',
    'address': 'PSC 4162, Box 3205\nAPO AA 83492',
},
    'key57860': 'value15183',
    'key22147': 'value2131',
    'key8112': 'value65808',
    'key24547': 'value50984',
    'key88599': 'value65093',
    'key59083': 'value17518',
    'key41113': 'value78668',
    'key83935': 'value52026',
    'key63960': 'value28225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Caitlin Morgan',
    'address': '34644 Ronnie Trace\nGilbertton, AR 63341',
    'text': 'Yeah effect reduce single ok sound. Ok best kid claim skill middle. Have he likely edge sort.\nNo color oil card. Writer interesting south inside yourself hope. Instead chair what quite instead.',
    'email': 'simsallison@example.org',
    'phone_number': '001-661-267-5576',
    'array_int_dynamic': [
    4547,
],
    'array_varchar_dynamic': [
    'Sarah Smith',
    'Glen Johnson',
    'Melanie Simon',
    'Kimberly Ray',
    'Nicole Wu',
],
    'json': {
    'name': 'Richard Page',
    'address': '6473 Ricky Extension\nNorth Briannafort, IN 48345',
},
    'key68715': 'value25063',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Donna Hayes',
    'address': 'Unit 0500 Box 9245\nDPO AP 45193',
    'text': 'Herself own sell. Rather suddenly blood leg southern.\nList work difficult use man. Go something pretty capital dream thousand hear public. Go stock friend wind third bed.',
    'email': 'xhunter@example.com',
    'phone_number': '001-930-284-2097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Wendy Hutchinson',
    'Gabriel Case',
    'Lori Warren',
    'Scott Neal',
    'Michael Ferguson',
    'Wendy Barrett',
    'Joy Smith',
],
    'json': {
    'name': 'Julie Buchanan',
    'address': 'PSC 0540, Box 3147\nAPO AE 23148',
},
    'key30084': 'value92095',
    'key91005': 'value8749',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Rhonda Martinez',
    'address': '6854 Rodriguez Circle Apt. 617\nBrooksview, MP 35589',
    'text': 'Material camera business make thank some beautiful. Success administration wife behavior. Once ahead same share house.',
    'email': 'edwardhughes@example.com',
    'phone_number': '+1-778-924-1305x5241',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Claudia Ferguson',
    'Jennifer Frederick DDS',
    'Eric Munoz',
    'Sarah Daniels',
],
    'json': {
    'name': 'Amy Welch DVM',
    'address': '1622 Cory Village\nSharontown, PA 74557',
},
    'key99103': 'value87333',
    'key52981': 'value20779',
    'key59428': 'value22487',
    'key47845': 'value74290',
    'key64285': 'value40417',
    'key32777': 'value7236',
    'key86052': 'value70172',
    'key88817': 'value55820',
    'key34322': 'value55289',
    'key26872': 'value39828',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Ricky Smith',
    'address': '6816 Rodriguez Garden\nDavisview, AK 28466',
    'text': 'Decision decision add first. Their dog control all.\nOfficer occur agency follow surface.\nHappen foreign prove Congress become. Body player also medical carry conference try.',
    'email': 'petersheather@example.net',
    'phone_number': '585.939.5776x9824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brian Carlson',
    'Kevin Chan',
    'Hannah Thornton',
    'Victoria Harrison',
    'Kathy Nielsen',
],
    'json': {
    'name': 'Kim Thompson',
    'address': 'USS Bartlett\nFPO AA 92704',
},
    'key61190': 'value5469',
    'key22955': 'value99989',
    'key64585': 'value72903',
    'key55784': 'value10514',
    'key56983': 'value91882',
    'key25679': 'value74173',
    'key7326': 'value39861',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Kathleen Mata',
    'address': 'Unit 7551 Box 7500\nDPO AP 28561',
    'text': 'The Republican value off watch.\nWithout remain successful especially. Writer field note stop participant possible over.',
    'email': 'hconrad@example.com',
    'phone_number': '360-522-7704',
    'array_int_dynamic': [
    84090,
],
    'array_varchar_dynamic': [
    'Justin Shaw',
    'Donald Humphrey',
    'Crystal Jennings',
    'Julia Blair',
    'Kelly Lopez',
    'Michelle Woodard',
],
    'json': {
    'name': 'Caroline Collins',
    'address': '61604 Natasha Ferry\nWest Matthewshire, WY 33266',
},
    'key47249': 'value50629',
    'key99007': 'value5057',
    'key46125': 'value23722',
    'key99830': 'value69588',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Justin Snyder',
    'address': '86434 Abbott Walks\nParsonsborough, NM 64671',
    'text': 'Moment wear authority two church degree least. From group artist east memory analysis account. Guy director agree reveal bill set.\nMiddle million night nor book. Keep even affect.',
    'email': 'mdudley@example.org',
    'phone_number': '8242095711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Scott Martin',
    'Michael Velasquez',
    'Amber Chung',
    'Brittney Saunders',
    'Amanda Bolton',
    'Ryan Diaz',
    'Angela Hill',
    'Rodney Dunn',
    'Jennifer Sutton',
],
    'json': {
    'name': 'John Jenkins',
    'address': '5856 Diane Island\nSouth John, NC 89584',
},
    'key29491': 'value3040',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Gabriel Wright',
    'address': '29023 Glover Meadow Apt. 320\nNew Janicemouth, TX 21644',
    'text': 'But view speak carry stuff. Eight let for those everything. His either thousand challenge speak adult improve.\nGreat sell light interesting citizen moment every. Likely per large job customer PM.',
    'email': 'holly48@example.com',
    'phone_number': '457-384-2846x362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mr. James Ramsey',
],
    'json': {
    'name': 'Michael Richards',
    'address': '306 Amanda Course Apt. 220\nWest Jasonland, HI 98264',
},
    'key21343': 'value93747',
    'key18933': 'value54308',
    'key57113': 'value70784',
    'key70563': 'value76482',
    'key55149': 'value11226',
    'key65655': 'value68106',
    'key22331': 'value42620',
    'key64648': 'value10960',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Denise Reeves',
    'address': '216 Barnes Squares\nAustinfurt, KY 96665',
    'text': 'Prove series involve learn her protect go week. Entire least final rise.\nNotice message wear office trip. Purpose sure light move. Better stay law probably situation room.',
    'email': 'cheryl81@example.org',
    'phone_number': '292-209-1417',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Anderson',
    'Janet Nicholson',
],
    'json': {
    'name': 'Matthew Montoya',
    'address': '27396 Lori Plain\nJimmyhaven, MI 19000',
},
    'key54777': 'value70042',
    'key60844': 'value7215',
    'key68484': 'value81582',
    'key23042': 'value1050',
    'key43416': 'value87632',
    'key88267': 'value18574',
    'key51824': 'value23287',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Timothy Daniel',
    'address': '79744 Roberts River Apt. 177\nNorth Monica, MP 93594',
    'text': 'Can miss charge pick few quickly. Base or support end blood factor. Later almost PM rest study anything.',
    'email': 'hillbrianna@example.org',
    'phone_number': '5925199946',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Pham',
    'Megan Long',
    'James Collier',
],
    'json': {
    'name': 'James Peters',
    'address': '88606 Dominic Parkway\nPort Jennifershire, NH 04191',
},
    'key3224': 'value12033',
    'key22306': 'value58464',
    'key2958': 'value98269',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'William Ramos',
    'address': '118 William Groves\nTylerburgh, MA 42587',
    'text': 'Very cut study create need indeed. Reach get factor check control brother local. Ahead local business simple. As spring measure board better.',
    'email': 'dhorn@example.com',
    'phone_number': '+1-919-359-7681x20970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Wesley Neal',
    'Nicole Berg',
    'Stephen Avila',
    'Sarah Anderson',
    'Sara Walker',
    'Regina Smith',
    'Sarah Skinner',
    'Angela Taylor MD',
    'Jessica Kelley',
    'Patricia Henry',
],
    'json': {
    'name': 'Luis Yates',
    'address': '26482 Alexa Hill Suite 233\nKathleenborough, KS 06843',
},
    'key19980': 'value44908',
    'key73357': 'value78893',
    'key69177': 'value67902',
    'key49060': 'value34278',
    'key8612': 'value29943',
    'key7474': 'value62430',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Daniel Zuniga',
    'address': '1095 Timothy Green Suite 064\nEast Kevinburgh, PR 13364',
    'text': 'Drive rather small these position important though. Condition whether official wind. Lay pretty particularly.',
    'email': 'rubiojessica@example.com',
    'phone_number': '(264)476-4269x176',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Susan Friedman',
    'Craig Odonnell',
    'Lisa Park',
    'Yvette Martin',
    'Robert Gordon',
    'Sylvia Frederick',
    'Peter Snyder',
    'Dr. Stacy Sawyer',
    'Jeffery Wallace',
    'Erin Daniels',
],
    'json': {
    'name': 'Nancy Burton',
    'address': '81155 Henry Wells\nDickersonside, KS 44907',
},
    'key9951': 'value82330',
    'key74319': 'value99526',
    'key83127': 'value86035',
    'key12382': 'value6236',
    'key70620': 'value64880',
    'key9493': 'value18539',
    'key89401': 'value77437',
    'key31280': 'value30834',
    'key7783': 'value22706',
    'key20588': 'value6977',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Tonya Chavez',
    'address': '70271 Shepard Squares\nLake Kelly, FM 85763',
    'text': 'Enter always idea. From these long week bit.\nArm court laugh event test someone. Measure they mouth management another station which letter.',
    'email': 'cynthialester@example.net',
    'phone_number': '599.619.5632',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Victor Phillips MD',
    'Miss Carrie Petersen',
    'Anthony Scott',
],
    'json': {
    'name': 'Caleb Lopez',
    'address': '775 Scott Ford Apt. 316\nBrewerside, TN 74332',
},
    'key78849': 'value63423',
    'key48497': 'value12713',
    'key37554': 'value41590',
    'key14273': 'value85737',
    'key47468': 'value71726',
    'key33033': 'value31075',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Taylor Walker',
    'address': '72064 Savage Causeway Apt. 497\nLake Lisastad, HI 96077',
    'text': 'Mention bag fear present movement. Certainly since those.\nLittle building medical enjoy.\nDown anyone recently page fly message. Voice difficult culture some seek.',
    'email': 'newtonhector@example.org',
    'phone_number': '+1-276-555-4751x4884',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Adrian Guzman',
],
    'json': {
    'name': 'Luke Wood',
    'address': '7610 Lane Knolls Suite 242\nKathleenland, DE 57849',
},
    'key32228': 'value52494',
    'key73680': 'value30584',
    'key85354': 'value61366',
    'key47322': 'value34440',
    'key66959': 'value48132',
    'key55828': 'value98499',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jonathan Mendoza',
    'address': '1636 Villarreal Dam\nLake Joanna, MI 10364',
    'text': 'Call last nothing. Data listen movie need.\nLow east attention which. A today mother page poor again remain political. Site left federal during.',
    'email': 'croberts@example.net',
    'phone_number': '852-422-4789x36849',
    'array_int_dynamic': [
    9451,
],
    'array_varchar_dynamic': [
    'Carol Gay',
    'Mrs. Heather Cole',
    'John Buchanan',
    'Ashley Patton',
    'William Gardner',
    'Tina Estrada',
    'David Vasquez',
    'Julie Garcia',
],
    'json': {
    'name': 'Amy Sims',
    'address': '505 Hines Forest Apt. 041\nLake Donnaberg, OH 68332',
},
    'key49052': 'value77390',
    'key64998': 'value6133',
    'key9962': 'value91070',
    'key23735': 'value31372',
    'key56689': 'value96013',
    'key85320': 'value33110',
    'key38113': 'value49992',
    'key85609': 'value66613',
    'key18753': 'value18139',
    'key28891': 'value96063',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Kenneth Martinez',
    'address': '37362 Hayes Lakes Apt. 489\nSouth Amanda, LA 45981',
    'text': 'Physical at final training son. Still while painting still check.\nHome big discussion west eye. Read where the language next know.',
    'email': 'howardelizabeth@example.net',
    'phone_number': '336-391-5693',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Darrell Walker',
    'Kelly Taylor',
    'Mark Patel',
    'Jacqueline Armstrong',
    'Donna Salas',
    'Gregory Dunn',
    'Chase Jones',
],
    'json': {
    'name': 'John Brown',
    'address': '9121 Alexandra Place Apt. 836\nWest Jermainemouth, TN 72203',
},
    'key99020': 'value45693',
    'key91921': 'value24018',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Tiffany Smith',
    'address': '701 Cook Creek\nEast Kristinaville, NV 76703',
    'text': 'Production other book. Provide sign authority seven.\nForget charge turn.\nPicture admit action second rise low media. Wife feel walk student.',
    'email': 'jimmy82@example.org',
    'phone_number': '+1-335-229-1340x8490',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Heather Adams',
],
    'json': {
    'name': 'Charles Harvey',
    'address': 'USNV Anderson\nFPO AE 99633',
},
    'key4807': 'value10304',
    'key93355': 'value46234',
    'key46002': 'value42728',
    'key59909': 'value24156',
    'key16482': 'value95684',
    'key50944': 'value69847',
    'key29018': 'value46196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Bradley Cain',
    'address': '171 Joseph Orchard Suite 488\nFitzgeraldville, TX 82828',
    'text': 'Audience serve believe such crime turn whole various. And ability anything rest. Tell big term might alone media.',
    'email': 'hunter13@example.org',
    'phone_number': '300-992-5842',
    'array_int_dynamic': [
    12221,
],
    'array_varchar_dynamic': [
    'Brandon Taylor',
],
    'json': {
    'name': 'Mr. Aaron Chan',
    'address': '9401 Martinez Street\nShepherdview, NH 46899',
},
    'key78408': 'value93736',
    'key62929': 'value92346',
    'key60760': 'value241',
    'key14218': 'value82198',
    'key58325': 'value14781',
    'key64545': 'value23281',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Kevin Lopez',
    'address': '614 Aaron Ridges Apt. 771\nPort Laura, NV 57264',
    'text': 'Financial analysis heavy step strong woman what same. Fund age her spring. Budget soldier field be result enjoy.\nMaybe hot soon fire drug no beat. Indicate such yard box there include parent.',
    'email': 'michael67@example.com',
    'phone_number': '001-812-740-7826x54297',
    'array_int_dynamic': [
    82154,
],
    'array_varchar_dynamic': [
    'Eugene Lowe',
    'James Johnson',
],
    'json': {
    'name': 'Reginald Proctor',
    'address': '7649 Bailey Shore Suite 776\nNorth Stanleybury, MN 49232',
},
    'key76920': 'value15016',
    'key55052': 'value58570',
    'key41456': 'value24830',
    'key40542': 'value46446',
    'key52878': 'value7990',
    'key22663': 'value90475',
    'key52716': 'value78517',
    'key96927': 'value24892',
    'key60467': 'value69477',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Richard Burgess',
    'address': '80508 Duncan Shoals Suite 944\nKristinachester, OR 83205',
    'text': 'He about politics board hair. Food choose behavior strategy take cause yet bed. Laugh final radio actually color.',
    'email': 'ahouse@example.org',
    'phone_number': '(307)311-4320x84431',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Harrison',
    'Michaela Patton',
    'Monique Guzman',
    'Christopher Riley',
    'Courtney Gonzalez MD',
    'Bonnie Smith',
    'William Clay',
    'Derrick Simpson',
],
    'json': {
    'name': 'Meghan Allen',
    'address': '752 Russell Pass\nPrinceborough, CO 52056',
},
    'key87028': 'value37725',
    'key85534': 'value89153',
    'key32823': 'value49762',
    'key63911': 'value98354',
    'key80274': 'value66350',
    'key4502': 'value59683',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Shirley Stanley',
    'address': '40667 Lane Point Suite 993\nEast Shane, ND 57135',
    'text': 'Fish space require chair fill east. Our various find side marriage contain pull. North rich must walk music give production leg. Smile relationship get against somebody series think.',
    'email': 'tayloramy@example.org',
    'phone_number': '001-898-209-3293x10978',
    'array_int_dynamic': [
    80676,
],
    'array_varchar_dynamic': [
    'Robert Reynolds',
    'Austin Frye',
    'Margaret Castaneda',
    'Dylan Torres',
    'Linda Wu',
    'Rebekah Medina',
    'Linda Todd',
    'Andrea Gilbert',
    'Roger Romero',
],
    'json': {
    'name': 'Stephanie Collins',
    'address': '2352 Gallagher Meadow\nStevenfort, PW 04293',
},
    'key50231': 'value35319',
    'key42728': 'value46919',
    'key29004': 'value27909',
    'key16249': 'value54706',
    'key71243': 'value66590',
    'key8900': 'value14039',
    'key7230': 'value55284',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kevin Davis',
    'address': '0437 Rebecca Course Suite 102\nWest Andrea, IN 33006',
    'text': 'Bag decade pretty environmental. Time hand boy return glass debate.\nBegin player whole crime. New Republican baby line degree team.',
    'email': 'michaelrodriguez@example.net',
    'phone_number': '881-544-0420x552',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kristie Cardenas',
    'Scott Gallegos',
    'Allen Olson',
    'Samuel Dawson',
    'Madison Zamora',
],
    'json': {
    'name': 'Mr. Ryan Reed',
    'address': '83797 Ramirez Estate Suite 847\nPetersmouth, SC 80295',
},
    'key94450': 'value46',
    'key98066': 'value59709',
    'key95593': 'value39503',
    'key46925': 'value37585',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'David Shea',
    'address': '230 Garrett Flats Apt. 209\nSouth Erika, VT 79057',
    'text': 'Vote together network often thank either buy. Know step power civil little.\nSort soon possible either. City strong your similar.',
    'email': 'uruiz@example.org',
    'phone_number': '507.765.8802',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Jacobson',
    'Richard Perez',
    'Courtney Silva',
    'Edward Munoz',
],
    'json': {
    'name': 'Shirley Hernandez',
    'address': '80017 Goodwin Via\nDelgadoville, KS 45040',
},
    'key56294': 'value98531',
    'key7304': 'value63881',
    'key46130': 'value28498',
    'key1807': 'value94168',
    'key86135': 'value63902',
    'key50832': 'value38877',
    'key3418': 'value11541',
    'key31954': 'value4552',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Nicole Brown',
    'address': '02101 Smith Fall\nKennethstad, KY 48989',
    'text': 'Spring individual despite deal.\nOrganization evening seven necessary message.\nWho sense someone war reach feel. Level available you civil here.',
    'email': 'fanderson@example.com',
    'phone_number': '346-411-4482x58095',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'John Coleman',
    'Rebecca Hurley',
    'Jacob Taylor',
    'Eric Black',
    'Mark Tucker',
    'Tracy Flynn',
],
    'json': {
    'name': 'Taylor Howe',
    'address': '919 Miller Burgs\nPort Kimfurt, AZ 84422',
},
    'key98831': 'value49650',
    'key9669': 'value66703',
    'key3632': 'value7284',
    'key74578': 'value75331',
    'key46259': 'value79423',
    'key81851': 'value9077',
    'key62252': 'value54353',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Daniel Mccormick',
    'address': 'PSC 7103, Box 6744\nAPO AA 61893',
    'text': 'Step most conference. Opportunity structure interest.',
    'email': 'cindy01@example.net',
    'phone_number': '578.509.3353x4977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Harris',
    'Zachary Gilbert',
    'Richard Huynh',
    'Ryan Jones',
    'Cindy Jackson',
    'Shawn Jackson',
],
    'json': {
    'name': 'Karen Smith',
    'address': '2559 Johnson Wall Suite 974\nEast Diane, GU 01717',
},
    'key31284': 'value72388',
    'key64632': 'value9946',
    'key23227': 'value27331',
    'key63391': 'value12684',
    'key65353': 'value28142',
    'key26227': 'value21123',
    'key24178': 'value66183',
    'key26670': 'value76908',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Rachel Frazier',
    'address': 'PSC 8541, Box 4523\nAPO AA 74261',
    'text': 'Crime discussion bad me. Minute what unit vote accept. Good forget over building daughter than write allow.',
    'email': 'christina84@example.org',
    'phone_number': '337-781-4362x484',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Erica Price',
    'Christopher Rangel',
    'Nancy Obrien',
],
    'json': {
    'name': 'Sandra Romero',
    'address': '98159 Smith Estate\nMitchellbury, AL 19514',
},
    'key86078': 'value78007',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Laura Baker',
    'address': '896 Rowland Fort\nSarahshire, AR 43761',
    'text': 'Piece population final rather national. Three speech begin various rest share.\nTop against grow present. Top very best Mr.\nPush hit ten. Fact environmental on hospital customer.',
    'email': 'xreed@example.org',
    'phone_number': '001-777-663-9858x27344',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jim Dixon',
    'Elizabeth Davis',
    'Michelle Mccormick',
    'Thomas Jackson',
    'Anna Malone',
    'Cassandra Estes',
    'Scott Johnson',
    'Luis Bradley',
    'Jason Welch',
],
    'json': {
    'name': 'Eric Mills',
    'address': '1255 Amanda Drive\nNew Jessica, FM 99185',
},
    'key68119': 'value98669',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Rebecca West',
    'address': '265 Betty Junctions\nKarastad, NJ 13249',
    'text': 'Common final improve next camera. Dream listen force evening party.\nImpact understand minute leg fast day teacher. Degree big short heavy enough.',
    'email': 'astanley@example.com',
    'phone_number': '(861)974-3218x3891',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Sullivan',
    'Darryl Morgan',
    'William Hickman',
    'James Richard',
    'Derek Hill',
    'Michelle Hendrix',
    'Mary Burnett',
    'Thomas Hutchinson',
    'Kimberly Eaton',
    'Brett Compton',
],
    'json': {
    'name': 'Connie Anderson',
    'address': '861 Maureen Roads\nLake Tanyamouth, LA 69349',
},
    'key71589': 'value65286',
    'key9969': 'value22843',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'John Benton',
    'address': '844 John Gardens\nPort Ericaborough, MN 36548',
    'text': 'Person life professor church size bag than. Generation cultural or. Bring same will interview see senior.',
    'email': 'brianspencer@example.com',
    'phone_number': '+1-205-357-9318x0392',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Burns',
    'Stacy King',
    'Stephanie Burton',
    'Erin Soto',
    'David Perez',
    'Angel Cervantes',
    'Christopher Wood',
    'Peter Kelley',
],
    'json': {
    'name': 'Hunter Lopez',
    'address': '03021 David Point\nNew Kristine, NM 53067',
},
    'key32143': 'value60755',
    'key3135': 'value6036',
    'key67213': 'value8923',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Miranda Bailey',
    'address': '1864 Erika Ville\nJessicatown, AL 24854',
    'text': 'Defense wind bill management. Expert imagine authority soon change summer. Stop quality film even. End second include remember.\nData able be land interview back. Money store physical represent.',
    'email': 'omitchell@example.net',
    'phone_number': '873-971-6023',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Traci Cole PhD',
    'Jeffery Marks',
    'Kelly Rowland',
    'James Davis',
    'Mr. Jeremy Foley',
    'Roberta Houston',
],
    'json': {
    'name': 'Sarah Gordon',
    'address': '33738 Rice Fall Suite 505\nWest Donaldport, MN 15793',
},
    'key18017': 'value57676',
    'key57684': 'value75255',
    'key74705': 'value14058',
    'key42060': 'value5933',
    'key77623': 'value19325',
    'key99577': 'value81902',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Mark Richardson',
    'address': '97767 Tyler Plains Apt. 894\nWallaceville, LA 63424',
    'text': 'Current describe speech statement usually management. Scientist any east commercial must from.',
    'email': 'johnstonsuzanne@example.org',
    'phone_number': '+1-614-766-3346x042',
    'array_int_dynamic': [
    92302,
],
    'array_varchar_dynamic': [
    'Amanda Watson',
],
    'json': {
    'name': 'Amanda Burton',
    'address': '2260 Lawson Islands\nKingmouth, IA 38329',
},
    'key84072': 'value27955',
    'key11044': 'value5848',
    'key31967': 'value4955',
    'key61872': 'value86954',
    'key72147': 'value59563',
    'key85946': 'value93662',
    'key49801': 'value9859',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Maria Hernandez',
    'address': '8721 James Harbors\nMerrittmouth, NJ 34544',
    'text': 'Economic happy trial training. Compare want fall discuss talk. That business art represent.\nMention check teach. Road occur lead yourself as yourself product major.',
    'email': 'fbradley@example.org',
    'phone_number': '7976209240',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Denise Costa MD',
],
    'json': {
    'name': 'Lisa Reyes',
    'address': '1076 Ronald Throughway Suite 607\nPort Anthony, FM 28411',
},
    'key66447': 'value11654',
    'key16792': 'value40366',
    'key57662': 'value70014',
    'key58274': 'value39714',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Cynthia Morris',
    'address': '1562 Breanna Glens\nEast Mollyborough, GA 25975',
    'text': 'Happy road raise now speak religious. Operation manage green resource mother agreement lose. Apply million clear job remember purpose see. Ability factor other natural many appear.',
    'email': 'johnsonjoanna@example.org',
    'phone_number': '(909)354-3763x96109',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Gomez',
    'Caleb Fletcher',
    'Amy Campbell',
    'Brian Lewis',
],
    'json': {
    'name': 'Dennis Romero',
    'address': '184 Smith Avenue\nMarthaburgh, MS 62151',
},
    'key55956': 'value36668',
    'key56323': 'value67595',
    'key96697': 'value30336',
    'key80619': 'value37682',
    'key34636': 'value92876',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Mary Schultz',
    'address': '33506 Green Shoal Suite 638\nMartinezberg, WY 08541',
    'text': 'Government Congress assume high pressure music you. Police the bring area necessary.\nJob effect glass wife. For yard per better magazine son. Keep local different her next test.',
    'email': 'mgentry@example.org',
    'phone_number': '359-869-5000',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jesus Quinn',
    'Christina Oliver',
    'Brian Combs',
    'Vanessa Solis',
    'Katelyn Marshall',
    'Sarah Vazquez',
    'Brenda Wade',
    'Melanie Jones MD',
    'Kyle Robbins',
    'Shane Huynh',
],
    'json': {
    'name': 'Jason Mathews',
    'address': '478 Frey Fields Apt. 282\nWest Kellyport, RI 71219',
},
    'key4031': 'value27617',
    'key91860': 'value29840',
    'key9142': 'value65517',
    'key12983': 'value87906',
    'key71767': 'value79686',
    'key10199': 'value40231',
    'key60013': 'value31212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Thomas Gonzalez',
    'address': '141 Kimberly Cliff\nEast Tinatown, PA 49039',
    'text': 'Court fire laugh. Enter cost still however officer thing. Executive her note worry.\nExist manager husband should.\nHealth second experience moment same million method. Say record fast out.',
    'email': 'scottreeves@example.net',
    'phone_number': '383.796.9483x45461',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Pittman',
    'Cassandra Miller',
    'Steven Glass',
    'Mrs. Nancy Martinez',
    'Jennifer Patel',
    'Michael Turner',
    'Jeff Duncan',
    'Judith Flores',
],
    'json': {
    'name': 'Jennifer White',
    'address': '147 Kim Mission Suite 283\nPalmerfurt, RI 96254',
},
    'key80227': 'value8506',
    'key3781': 'value42192',
    'key61915': 'value11204',
    'key18892': 'value7398',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Steven Sandoval',
    'address': '2083 Kristin Mount\nBlackburnland, KS 47743',
    'text': 'Cold show join. Force kitchen former kid stuff should easy. Paper population effort what still nature rock.\nPerhaps prove design. Bar environmental house activity.',
    'email': 'moorerobert@example.org',
    'phone_number': '+1-799-948-7956x8028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Wilson DDS',
],
    'json': {
    'name': 'Denise Kim',
    'address': 'Unit 2972 Box 5382\nDPO AP 06372',
},
    'key51093': 'value22385',
    'key98895': 'value25354',
    'key67244': 'value31815',
    'key36482': 'value78184',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Patrick Santiago',
    'address': '739 Amanda Road Apt. 287\nMarkburgh, MH 44103',
    'text': 'Game none beyond indeed. Control pick really you key.\nSpeak laugh our door.\nExpert front end remember anyone. Heart assume structure situation.',
    'email': 'fdiaz@example.org',
    'phone_number': '+1-837-913-2148x5723',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Stevens',
    'Karen Owens',
],
    'json': {
    'name': 'Patricia Wood',
    'address': '24565 Victor Springs Apt. 123\nAndreaview, MP 97132',
},
    'key40849': 'value46601',
    'key24842': 'value93860',
    'key15325': 'value88493',
    'key71506': 'value18418',
    'key30637': 'value44410',
    'key44844': 'value72275',
    'key32943': 'value64660',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Jacob Walker',
    'address': '20868 Marquez Hill\nSouth Amandaside, CO 84261',
    'text': 'Central air at bed. Image story hard least quality medical.\nForm piece agent past. Rock security dog year future hair. A college take trade across bar.',
    'email': 'angelasullivan@example.com',
    'phone_number': '984.538.0654',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Jones',
    'Ashley Martinez',
    'Jodi Velasquez MD',
    'Madeline Perry',
],
    'json': {
    'name': 'Wendy Grimes',
    'address': '15232 Arnold Stream\nContrerashaven, OH 13041',
},
    'key49368': 'value63497',
    'key72969': 'value61889',
    'key20755': 'value16566',
    'key57082': 'value2675',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Michelle Schwartz',
    'address': '61465 Summer Hills Suite 340\nLake Philip, IN 66654',
    'text': 'Pattern southern activity right. Cup energy they make concern.\nFront beyond challenge today allow recently move. Concern establish bag. Suggest she three deep kid her decision skin.',
    'email': 'elizabethshaffer@example.org',
    'phone_number': '462-714-1772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brian Morton',
    'Kylie Watson',
    'Gabriel Torres',
    'Rachel Stewart',
    'Teresa Vaughn',
    'Catherine Barnett',
    'John Cain',
    'Gary Salazar',
],
    'json': {
    'name': 'Theresa Young',
    'address': 'USNS Mccann\nFPO AE 44856',
},
    'key1771': 'value24760',
    'key10706': 'value3769',
    'key40193': 'value9312',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Troy Morris',
    'address': '832 Whitehead Corners Apt. 910\nCynthiachester, OK 95932',
    'text': 'Tonight protect key camera six. Big man wind last national structure.\nMovie be improve chance. Assume management not happy. Nor claim occur public a response everybody.',
    'email': 'julie88@example.org',
    'phone_number': '883.487.7279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Lin',
    'Angela Booker',
    'Holly Beck',
    'Brandon Brown',
    'Perry Fischer',
    'Todd Buckley',
],
    'json': {
    'name': 'Ashley Stewart',
    'address': '70651 Amber Corner Suite 819\nBrianborough, CO 26657',
},
    'key3100': 'value57580',
    'key9962': 'value43200',
    'key1018': 'value86233',
    'key81687': 'value95821',
    'key67799': 'value7480',
    'key14141': 'value72274',
    'key31016': 'value89747',
    'key40470': 'value23279',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Gina Pham MD',
    'address': '148 Anthony Fall Apt. 967\nPort Henry, NE 52859',
    'text': 'Office popular student mind central list month. Probably cut scientist tend maintain down prepare tonight. Work discuss firm establish.',
    'email': 'nicolelittle@example.org',
    'phone_number': '(847)322-0849x63945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Adam Franklin',
    'Mr. Charles Griffin',
    'Yvonne Johnson',
    'Matthew Hansen',
    'Angel Wilson',
    'Mark Hoover',
    'Brenda Short',
    'Alexander Smith MD',
    'Matthew Campbell',
],
    'json': {
    'name': 'John Kerr',
    'address': '14514 Anderson Forks\nNorth Erikmouth, NC 21097',
},
    'key8613': 'value95811',
    'key78075': 'value49991',
    'key34916': 'value44229',
    'key58708': 'value31251',
    'key67426': 'value22103',
    'key25603': 'value56728',
    'key28031': 'value59894',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Francis Castro',
    'address': 'USNS Colon\nFPO AE 70292',
    'text': 'Describe through population also build store. Edge tax development over voice institution smile.',
    'email': 'wrasmussen@example.com',
    'phone_number': '726.847.0367',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Carter',
    'Brandon Thomas',
    'Jennifer Villarreal',
    'Deborah Webb',
    'Molly Levy',
    'Brian Suarez',
    'Erika Taylor',
    'Trevor Gonzales',
],
    'json': {
    'name': 'Terry Garcia',
    'address': '558 Hunter Grove Suite 262\nNicholasport, RI 78530',
},
    'key58741': 'value56006',
    'key72853': 'value47059',
    'key86681': 'value16620',
    'key42317': 'value59623',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Emily Crosby',
    'address': '4256 Villanueva Spring\nEast Phillipstad, IA 56151',
    'text': 'Nearly PM quality decide reason whom employee. Measure language news. Worker hear tree worker list relationship. Campaign condition difficult what.\nEat weight action onto television read.',
    'email': 'todd47@example.org',
    'phone_number': '001-717-443-5849x779',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Knight',
    'Michael Murray',
    'Annette Nixon',
    'Michelle Davis',
    'Jacob Nelson',
],
    'json': {
    'name': 'Heidi Fox',
    'address': 'Unit 9977 Box 5081\nDPO AE 98724',
},
    'key18733': 'value87041',
    'key82114': 'value26388',
    'key53909': 'value70300',
    'key86191': 'value82194',
    'key98971': 'value96641',
    'key92631': 'value57249',
    'key34124': 'value21416',
    'key43029': 'value21021',
    'key1137': 'value59716',
    'key95479': 'value55326',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Anthony Wheeler',
    'address': '5373 Anna Stravenue\nBradleytown, MO 25931',
    'text': 'How economic nation amount growth nearly point. Past girl sister arrive Mr training rise.\nDraw me get draw morning half reason. Per quickly amount often final politics.',
    'email': 'juarezchristopher@example.net',
    'phone_number': '(793)801-8028x482',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Richard Bryant',
    'Derrick Hunter',
    'Jaime Cantu',
    'Jennifer Buchanan',
    'Brandy Cummings',
],
    'json': {
    'name': 'James Watson',
    'address': '03509 Levine Loop\nNew Lance, GU 27177',
},
    'key64103': 'value6750',
    'key90531': 'value86408',
    'key18708': 'value88117',
    'key55677': 'value50599',
    'key70099': 'value92360',
    'key83268': 'value78478',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Rhonda Rasmussen',
    'address': '319 Rivera Meadows\nLake Heather, MS 45612',
    'text': 'Likely wide and management relate. Nice if care know meeting police. Sea modern fear huge source.\nCompany trip radio our woman product assume. Imagine away everything along wonder white different.',
    'email': 'dwise@example.com',
    'phone_number': '956.668.5815x4205',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Anna Tran',
    'John Carr',
    'Linda Hernandez',
    'Stacey Todd',
    'William Roberts',
],
    'json': {
    'name': 'Joshua Pham',
    'address': '0642 Williams Fords Suite 749\nAustinland, MA 54407',
},
    'key64428': 'value95903',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Jody Lewis',
    'address': '83931 Roberts River\nSouth Michael, OH 74332',
    'text': 'Seat college wind choose before. Determine exactly yourself meeting fly find.\nMillion attack staff little safe. Effort vote keep reduce under outside.',
    'email': 'walkerjohn@example.net',
    'phone_number': '313.341.8626x2825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Wilson',
    'April Smith',
    'Melvin Jackson',
    'Leslie Fischer',
],
    'json': {
    'name': 'Amy Byrd',
    'address': 'USS Davis\nFPO AA 57711',
},
    'key75381': 'value92582',
    'key99445': 'value4022',
    'key18160': 'value28035',
    'key92748': 'value88392',
    'key37274': 'value71771',
    'key24544': 'value89024',
    'key54435': 'value30769',
    'key72142': 'value90085',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Thomas Cobb',
    'address': '56333 Garcia Islands Apt. 196\nScottfort, WV 31134',
    'text': 'Technology deal once daughter environment energy social. Oil seven stock whole agreement money improve attorney. Speech perform apply nice.',
    'email': 'jennifer45@example.org',
    'phone_number': '210.232.7970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tina Williams',
    'Patricia Weeks',
    'Brianna Washington',
    'Rachel Paul',
    'Michelle Walker',
    'Patrick Meyer',
    'Jacob Green',
    'Nicholas Moore',
    'Nicole Brown',
    'Wanda Cain',
],
    'json': {
    'name': 'Crystal Rivera',
    'address': '53563 Brown Village\nBradymouth, UT 27206',
},
    'key1425': 'value64057',
    'key91523': 'value36574',
    'key88890': 'value97990',
    'key95788': 'value90637',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Michelle Daugherty DDS',
    'address': '8863 Joseph Walk Apt. 836\nNelsonbury, SC 34816',
    'text': 'Hit third method better recently require help final. Fear Democrat amount market really discover. Amount Mrs tend fear hard quality.',
    'email': 'castanedadarrell@example.com',
    'phone_number': '(606)526-6149x9661',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Heather Ross',
    'Deborah Walker',
    'Raymond Adkins',
    'Mary Boyd DVM',
    'Jeremy Herrera',
    'Jennifer Ellis',
    'Richard Gentry',
    'Omar Murphy',
],
    'json': {
    'name': 'Tammy Stephens',
    'address': '85486 Sanchez Pine\nPort Stephanieton, TN 27060',
},
    'key35418': 'value75910',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Brett White',
    'address': 'PSC 7432, Box 2818\nAPO AP 77995',
    'text': 'Attention start likely operation trade. Certain street bed candidate. Reality instead simple across course.',
    'email': 'eatonmichelle@example.com',
    'phone_number': '5783729911',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Smith',
    'Mary Obrien',
    'David Cameron',
],
    'json': {
    'name': 'Angela Smith',
    'address': 'USCGC Smith\nFPO AA 93235',
},
    'key84656': 'value78817',
    'key54764': 'value88748',
    'key46263': 'value16898',
    'key23029': 'value91532',
    'key61013': 'value40038',
    'key53910': 'value33535',
    'key1211': 'value28648',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Michael Mejia',
    'address': '2663 Hutchinson Ridges Apt. 943\nJustinview, NJ 95346',
    'text': 'Actually according involve recent hotel out. Why point attention rate. Someone attorney share.\nThrow another administration place beyond win. Their challenge story wear test.',
    'email': 'jennifersmith@example.net',
    'phone_number': '(838)466-5516x6024',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Newman',
    'Edward Beck',
],
    'json': {
    'name': 'Timothy Simmons',
    'address': '1879 Debra Orchard\nEast Thomas, NM 52628',
},
    'key83407': 'value12406',
    'key5664': 'value61120',
    'key67437': 'value94847',
    'key69048': 'value29249',
    'key30530': 'value81989',
    'key26095': 'value47479',
    'key13475': 'value40316',
    'key82942': 'value44916',
    'key43436': 'value5860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Benjamin Tyler',
    'address': '176 Morris Meadows\nDyertown, VA 22983',
    'text': 'Piece must may cost agent.\nSection less him. Them heavy board million build skin. Ground his billion better prove source.',
    'email': 'zlowe@example.org',
    'phone_number': '001-373-261-9590x69496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tyrone Garcia',
    'Sarah Cochran',
    'Sarah Drake',
    'Thomas Rodriguez',
    'Shawn Hughes',
    'Ashley Berry',
    'Matthew Powers',
    'Brandon Jones MD',
    'Rhonda Huber',
],
    'json': {
    'name': 'Gary Collier',
    'address': '967 Kenneth Mission Apt. 528\nNew Laurabury, WV 24893',
},
    'key52074': 'value90695',
    'key50955': 'value11458',
    'key52497': 'value99313',
    'key86611': 'value75610',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Bianca Monroe',
    'address': '52903 Wood Lane\nWest Amandaborough, HI 32433',
    'text': 'That finish only theory another. Series relationship attention cut my indeed.\nDirection power off spring call. Artist evening school each.',
    'email': 'nortonashley@example.com',
    'phone_number': '796.271.0457',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mason Shah',
    'Carrie Miller',
    'Curtis Allen',
    'Emily Mayer',
],
    'json': {
    'name': 'Abigail Gallegos',
    'address': '68930 Samuel Plains\nSouth Robertland, PR 02977',
},
    'key77631': 'value92402',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Scott Estrada',
    'address': '74688 Patrick Drive\nGonzalesshire, AK 88529',
    'text': 'Could season sign major. Learn three because close finally.\nBefore dog example become actually truth bed generation. Spring author could son. Ask well such reality.',
    'email': 'rickymcdonald@example.org',
    'phone_number': '622-591-5891x7440',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Barrett',
    'Heather Sullivan',
    'Thomas Simmons',
    'Bethany Johnson',
    'Kathryn Cortez',
    'Robert Jenkins',
    'Julia Ferguson',
    'Sherry Fernandez',
    'Alicia Madden',
],
    'json': {
    'name': 'Jose Gray',
    'address': '133 Austin Union\nNew Matthewton, LA 00735',
},
    'key57194': 'value50526',
    'key48996': 'value34920',
    'key58256': 'value46651',
    'key97235': 'value78516',
    'key91089': 'value32571',
    'key45819': 'value59408',
    'key136': 'value89968',
    'key45014': 'value19642',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Karen Hanson DVM',
    'address': '164 Brian Freeway\nSouth Williamstad, IA 27589',
    'text': 'Site voice sure movie. Teacher some when today knowledge.\nMoney red site word such interest. Brother they increase.\nSomebody song fear economic central within follow. How cut court receive both.',
    'email': 'dustin54@example.org',
    'phone_number': '+1-980-257-1058x66315',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Winters',
    'Michael Martin',
    'Daniel Lindsey',
    'Robert Oconnor',
],
    'json': {
    'name': 'Thomas Gonzales',
    'address': '8092 Murray Drives\nNorth Patrickshire, ME 46529',
},
    'key85274': 'value37812',
    'key81392': 'value73100',
    'key95426': 'value81010',
    'key21277': 'value63445',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Stacie Rice',
    'address': '424 Gallagher Forks\nNew Adrian, WA 83276',
    'text': 'Analysis player deep authority factor television. Yourself member tell away like western win. Present travel figure agency anyone hit similar.',
    'email': 'vanessa55@example.com',
    'phone_number': '+1-316-348-5872x5972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mark Wells',
    'Tyrone Gutierrez',
    'David Miller DVM',
    'Mackenzie Rivera',
],
    'json': {
    'name': 'Anita Webb',
    'address': '5917 Bonnie Manor\nRamirezhaven, LA 24002',
},
    'key65558': 'value90170',
    'key19774': 'value51928',
    'key60034': 'value66442',
    'key33940': 'value9047',
    'key8316': 'value60864',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Richard Campbell DDS',
    'address': '22766 Rebecca Common\nNatashaburgh, FL 71544',
    'text': 'Source newspaper same various single pass.\nAt democratic six number soon all police. High door leg imagine certain rock specific. Popular itself study store along miss much money.',
    'email': 'susan74@example.com',
    'phone_number': '001-488-482-7318x7434',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gary Ross',
    'Kevin Browning',
    'Peggy Miller',
],
    'json': {
    'name': 'Joseph Ramos',
    'address': '15444 Danielle Street Apt. 877\nCookfort, LA 32900',
},
    'key65541': 'value95006',
    'key61406': 'value78568',
    'key66473': 'value34338',
    'key3120': 'value71565',
    'key4726': 'value59768',
    'key83557': 'value59782',
    'key1538': 'value82672',
    'key5361': 'value48006',
    'key92766': 'value14398',
    'key61692': 'value70922',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Jacob Mejia',
    'address': 'Unit 1682 Box 4336\nDPO AE 15849',
    'text': 'Yet sister nor during level today certain poor. Parent budget their cover either might police professional.\nCompare next meet while believe. House less dinner close book ago.',
    'email': 'rachelpage@example.com',
    'phone_number': '(215)336-5119x740',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Warren',
    'Jessica Lang',
    'Kelly Francis',
    'Christopher Lewis',
    'Angela Williams',
    'Ruth Palmer',
    'Melissa Barnett',
    'Kim Sullivan',
    'Karen Marshall',
],
    'json': {
    'name': 'Dr. Walter Lloyd',
    'address': 'USS Moore\nFPO AE 78740',
},
    'key12215': 'value83591',
    'key16925': 'value84008',
    'key13218': 'value77053',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Devin Warren',
    'address': '50553 Logan Well\nJeffreyshire, HI 56448',
    'text': 'Table within want talk. Beyond probably one whole picture bag.\nScore bit small bit. Record perhaps top around. Night miss data agreement want result federal vote. Message behind free paper end.',
    'email': 'zgraham@example.org',
    'phone_number': '+1-364-943-8376x3142',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Tran',
    'Victoria Smith MD',
    'Michelle Lane',
    'Rebecca Krause',
    'Paul Powell',
    'Mrs. Kim Brown MD',
],
    'json': {
    'name': 'Philip Manning',
    'address': '85554 Wade Pass Apt. 392\nWest Heather, MS 99538',
},
    'key72240': 'value34554',
    'key22814': 'value30788',
    'key4893': 'value63784',
    'key98818': 'value48894',
    'key47683': 'value3014',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Daniel Adams',
    'address': '5676 Ann Fork\nEast Madison, AZ 89846',
    'text': 'Adult decision save commercial same themselves. Bed who choice quality key feeling that. Born line bad which.\nClear hospital technology. Painting ahead town minute professor way question surface.',
    'email': 'jbrown@example.com',
    'phone_number': '947.326.5856x386',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alicia Frank',
    'Christine Patel PhD',
],
    'json': {
    'name': 'Yolanda Rodriguez',
    'address': '915 Brooke Flats Suite 105\nClarkville, VA 64035',
},
    'key38144': 'value19847',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Alexis Bray',
    'address': 'PSC 6572, Box 8883\nAPO AP 58808',
    'text': 'Population defense player sit thank list laugh.\nRealize to successful Democrat small with. Claim natural build painting here.',
    'email': 'knightfred@example.org',
    'phone_number': '(227)458-9210',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Knight',
    'Jessica Bruce',
],
    'json': {
    'name': 'Diamond Owens',
    'address': '818 Jonathan Rue\nSouth James, IA 38412',
},
    'key21097': 'value62384',
    'key33377': 'value41333',
    'key28212': 'value79112',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Robert Allen',
    'address': '60530 Thomas Drive\nWest Jessicaville, WY 98080',
    'text': 'Left table attention wish because quickly. Court better one. Onto film Democrat lead business least event market. Scene number soon mission too.\nFront show fight mouth.',
    'email': 'shuffman@example.net',
    'phone_number': '564.432.8506',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michaela Kramer',
    'Deborah Robinson',
    'Mr. Joseph Fields',
    'Teresa Pena',
    'Glen Ramirez',
],
    'json': {
    'name': 'Chloe Tran',
    'address': '9483 Rachel Dale Suite 750\nSouth Rogerhaven, TN 34439',
},
    'key64968': 'value50846',
    'key3923': 'value26032',
    'key66089': 'value47874',
    'key9101': 'value49835',
    'key18149': 'value86479',
    'key13155': 'value24595',
    'key33929': 'value52506',
    'key87055': 'value11232',
    'key51023': 'value49160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Justin Rodriguez',
    'address': '615 Nelson Fork\nSouth Kathrynburgh, IL 44405',
    'text': 'Expect race sometimes. Tough usually it defense officer rock speech or.\nBar big approach together clear again artist. Child ten low cell.',
    'email': 'ihunter@example.net',
    'phone_number': '(640)961-6254',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Suzanne Roberts',
    'Amy Parks',
    'Kimberly Hunter',
    'Richard Mejia',
    'Samantha Baker',
    'Jesse Murphy',
    'William Mckee',
    'Erin Frost',
    'Blake Nichols',
],
    'json': {
    'name': 'Aaron Gonzalez',
    'address': '790 Felicia Forest\nTonyport, MN 05080',
},
    'key64514': 'value99836',
    'key10171': 'value62247',
    'key7221': 'value47385',
    'key14794': 'value56884',
    'key51025': 'value17431',
    'key43087': 'value45751',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jeffery Blackwell',
    'address': '3827 Morales Camp Apt. 780\nCowanville, DC 66175',
    'text': 'Third individual Democrat strategy amount grow great. Hundred Congress away run table for continue. Side life artist play.',
    'email': 'ealexander@example.net',
    'phone_number': '851.803.4674x99809',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kim Torres',
    'Tara Olsen',
    'Lisa Bray',
    'Daniel Cox',
    'Carmen Moreno',
    'Kevin Jackson',
    'Robin Francis',
],
    'json': {
    'name': 'Ann Miller',
    'address': '9159 Jones Forges\nPort Mariafort, AL 22709',
},
    'key75851': 'value85210',
    'key17120': 'value45436',
    'key98259': 'value61281',
    'key65561': 'value5288',
    'key48475': 'value52875',
    'key33298': 'value49039',
    'key33948': 'value1177',
    'key76495': 'value14295',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'David Gutierrez',
    'address': '8914 James Summit Suite 286\nMyersbury, LA 83453',
    'text': 'Attention out task summer to whole political. Sound allow need onto heart growth.',
    'email': 'michael13@example.com',
    'phone_number': '224.276.0753x19771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Cory Pope',
    'Aaron Ayala',
    'Tiffany Barnes',
    'Tiffany Allen',
    'John Berger',
],
    'json': {
    'name': 'Latasha Wilson',
    'address': '902 Troy Courts\nDenisestad, NV 33728',
},
    'key95128': 'value54582',
    'key38213': 'value93897',
    'key4915': 'value46625',
    'key69593': 'value41726',
    'key64771': 'value32985',
    'key68842': 'value24599',
    'key35449': 'value14370',
    'key17288': 'value4371',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Ashlee Vincent',
    'address': '06116 Barbara Pines Apt. 240\nSouth Alexanderborough, CO 20085',
    'text': 'Good lot network wall court. Process already party your.\nTeam where large raise site quickly nature.',
    'email': 'ryanalexander@example.com',
    'phone_number': '(272)704-4623',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Julie Adkins',
    'Kimberly Keller',
    'Alejandro Adams',
    'Keith Wallace',
    'Jeremy Compton',
],
    'json': {
    'name': 'Stephen Richard',
    'address': '96784 Torres Field\nMichaelborough, NC 57781',
},
    'key77697': 'value19852',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Dillon Grimes',
    'address': '55992 Daisy Lock Suite 553\nNew Jacob, CO 95524',
    'text': 'Return window pressure church. Similar live success describe.\nArrive early smile media.\nRepresent through serious ground. Lead treatment peace investment administration.',
    'email': 'eric03@example.org',
    'phone_number': '(237)219-1698x20114',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Davis',
    'Christopher Young',
    'Sara Ballard',
    'Nicole Perez',
    'Lauren Benson',
    'Tina Santos',
    'Carlos Gross',
],
    'json': {
    'name': 'Jerome Sparks',
    'address': 'USS Pruitt\nFPO AA 83718',
},
    'key85752': 'value89296',
    'key28404': 'value95404',
    'key45655': 'value91564',
    'key39431': 'value92017',
    'key18637': 'value67543',
    'key37172': 'value49757',
    'key91392': 'value72617',
    'key93371': 'value98945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Sarah Barron',
    'address': '5644 Short Falls Apt. 768\nSouth Sherryport, MD 31555',
    'text': 'Candidate visit strong individual commercial shake set kind. Idea state night summer. Happen reason firm direction.',
    'email': 'whiteseth@example.org',
    'phone_number': '4788351727',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Thompson',
    'Marie Gross MD',
    'Erin Bradley',
],
    'json': {
    'name': 'Laura Malone',
    'address': '04264 Perkins Cove Apt. 588\nTrevorville, IL 33674',
},
    'key58098': 'value86608',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Nicholas Gray',
    'address': '38133 Bradley Mountains\nCastillostad, NC 01818',
    'text': 'Modern recent exactly movement stock get whether. Appear nice movie suffer. Loss quickly when deal million.',
    'email': 'kylegibson@example.com',
    'phone_number': '6245819841',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Mueller',
    'Jacob Lang',
    'Nathaniel Coleman',
    'Lisa Gutierrez',
    'Jessica Cruz',
    'Richard Harris',
],
    'json': {
    'name': 'Cody Smith',
    'address': '66524 Rachel Terrace Suite 257\nWest Karen, MS 12388',
},
    'key88166': 'value10715',
    'key36782': 'value21208',
    'key16099': 'value339',
    'key77170': 'value37875',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Alexandria Calderon',
    'address': '621 Gloria Expressway\nNorth Tylerburgh, PR 54101',
    'text': 'Similar capital movie film specific will sister well. Police authority specific base attorney education wide at. Feel foreign sure system friend money cut.',
    'email': 'susanvargas@example.com',
    'phone_number': '001-722-597-9634x9119',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Humphrey DDS',
    'Tiffany Blanchard',
],
    'json': {
    'name': 'Julie Case',
    'address': '91487 Cassandra Via\nWest Timothy, MD 72009',
},
    'key63891': 'value21726',
    'key25471': 'value65936',
    'key4179': 'value10135',
    'key35787': 'value88653',
    'key74049': 'value7212',
    'key42141': 'value26899',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Tara Crane',
    'address': '489 Raymond Drives Suite 220\nAllenside, DC 88906',
    'text': 'Food expect little heart local little.\nMouth line single. Rise political detail meeting performance night but personal. Debate range boy probably best scientist Republican realize.',
    'email': 'mcculloughsandra@example.net',
    'phone_number': '(338)299-5311x6655',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Geoffrey Alvarez',
    'Kristen Jones',
    'Kristina Brown',
    'Eddie Rogers',
    'Michele Becker',
    'Joseph Rasmussen',
],
    'json': {
    'name': 'Nicholas Barnes MD',
    'address': '92877 Allen Forges Apt. 984\nNew Anthony, VT 70342',
},
    'key65107': 'value36695',
    'key66680': 'value41824',
    'key29324': 'value83969',
    'key60796': 'value2272',
    'key80507': 'value49741',
    'key3627': 'value42158',
    'key5352': 'value16001',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Michael Johnson',
    'address': '1118 Gonzalez Squares\nPort Michaelport, LA 75037',
    'text': 'Theory buy say according eat trip family alone. Happy tell voice mind campaign.\nSport writer team determine fight whom. Guess goal kid I.',
    'email': 'matthew32@example.com',
    'phone_number': '4066914420',
    'array_int_dynamic': [
    57432,
],
    'array_varchar_dynamic': [
    'Karina Miles',
    'Priscilla Frye',
    'Gabriella Silva',
    'Benjamin Baker PhD',
    'Joseph Oliver',
    'Keith James',
    'Kyle Faulkner',
    'Amber Wiley',
    'Andrew Castro',
],
    'json': {
    'name': 'Jessica Winters',
    'address': 'PSC 7799, Box 3920\nAPO AE 30628',
},
    'key94758': 'value66686',
    'key66960': 'value84390',
    'key95783': 'value57186',
    'key3025': 'value93803',
    'key56598': 'value57878',
    'key73491': 'value44954',
    'key17886': 'value15089',
    'key95728': 'value76908',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jeffery Lynch',
    'address': 'USS Watkins\nFPO AP 08934',
    'text': 'Price better phone moment young girl. Fight network ready information sea. Especially hold fund who.',
    'email': 'jessica90@example.com',
    'phone_number': '8673737288',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Baker',
    'James Clark',
    'Michael Williams',
    'Amy Miller',
    'Kevin Montgomery',
    'Sarah Carroll',
    'Sarah Robertson',
    'Nicole Ortega',
    'Christine Smith',
],
    'json': {
    'name': 'Kristi Johnson',
    'address': 'USCGC Ramsey\nFPO AA 58212',
},
    'key35683': 'value35191',
    'key99846': 'value40985',
    'key53010': 'value19264',
    'key71468': 'value97010',
    'key57556': 'value49732',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'James Martinez',
    'address': '39620 Carol Loaf Suite 684\nSouth Shannon, ID 41363',
    'text': 'Sea direction goal prevent. Short you wish involve want central. Let administration language heavy.\nCheck data see cause leader poor small. Especially son mention recently.',
    'email': 'hillcharles@example.net',
    'phone_number': '713-885-1747x481',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kristina Garrett',
    'Erin Ayala',
    'Adam Aguilar',
    'Dawn Cobb',
    'Jeffrey Carlson',
    'Mark Johnson',
    'David May',
    'Kimberly Wall',
],
    'json': {
    'name': 'David Parrish',
    'address': '520 Michael Villages\nSouth Shannonhaven, GU 88825',
},
    'key5353': 'value47417',
    'key49664': 'value54625',
    'key58955': 'value26030',
    'key35137': 'value46624',
    'key59050': 'value69009',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Haley Frye',
    'address': 'USCGC Herring\nFPO AA 98261',
    'text': 'Move anything father gas senior hundred. Anyone then administration leader world. Player true small region.\nAhead east in open camera run. Parent never probably subject. Evidence appear main.',
    'email': 'kaylachristian@example.com',
    'phone_number': '(688)401-3160',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Evelyn Hurley',
    'John Anderson',
],
    'json': {
    'name': 'Joshua Coleman',
    'address': '230 Scott Shores\nMartinstad, TX 33249',
},
    'key98713': 'value27971',
    'key65991': 'value43568',
    'key35075': 'value7194',
    'key10072': 'value69909',
    'key84330': 'value14161',
    'key46200': 'value47217',
    'key58306': 'value72724',
    'key80659': 'value52416',
    'key458': 'value55458',
    'key31725': 'value11725',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Stacy Nichols',
    'address': '44027 Daniel Walk Suite 345\nSouth Patrickside, RI 45146',
    'text': 'Wind activity born main stuff dream.\nMean fly shake. Can exist financial ahead could assume hold medical.',
    'email': 'tannermatthew@example.com',
    'phone_number': '+1-389-370-8373x926',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Hannah Nelson',
    'Dylan Davis',
    'Joseph Mejia',
    'Joshua Schultz',
    'Eric Powell',
    'Brian Shaw',
    'Heather Pena',
    'Matthew Knight',
],
    'json': {
    'name': 'Victor Schneider',
    'address': '502 Dawson Common Suite 377\nAngelastad, AL 36516',
},
    'key10446': 'value1881',
    'key87507': 'value4103',
    'key84529': 'value15098',
    'key23679': 'value17847',
    'key2816': 'value9156',
    'key24000': 'value46842',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Michael Mullins',
    'address': '66540 Sarah Streets\nLake Amyfurt, TN 77298',
    'text': 'Trade hear painting her total.\nWrong reach these debate eye. Student follow center perhaps surface leave. Describe else around last old shake.',
    'email': 'pmacias@example.com',
    'phone_number': '001-900-385-4139x82474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Paul Mcdonald',
    'James Hancock',
    'Christopher Vasquez',
    'Kathryn Hendricks',
],
    'json': {
    'name': 'Michael Wiggins',
    'address': '0077 Christine Turnpike\nEast Heather, SD 21849',
},
    'key9432': 'value71812',
    'key41300': 'value87311',
    'key5325': 'value60204',
    'key75341': 'value44532',
    'key81173': 'value70755',
    'key77230': 'value59273',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Andrew Lyons',
    'address': '540 Guerra Landing\nNew Melanieville, ND 77653',
    'text': 'Look remain that large debate laugh moment. Leave accept school effect fish town dream.\nOnto prove under me evening. Plan stay nor often discuss down music state.',
    'email': 'kpalmer@example.org',
    'phone_number': '001-353-642-5536x8544',
    'array_int_dynamic': [
    50150,
],
    'array_varchar_dynamic': [
    'Christopher Jones',
    'Nicole Edwards',
    'Jennifer Lloyd',
    'Lisa Lopez',
    'Ashley Acevedo',
],
    'json': {
    'name': 'Richard Hancock',
    'address': '8267 Kline Springs Suite 582\nNorth Brittanychester, FL 90549',
},
    'key77360': 'value77925',
    'key6654': 'value99689',
    'key34721': 'value80995',
    'key97955': 'value58375',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Rodney Brewer',
    'address': '79632 Crawford Meadows Suite 261\nBuchananborough, NV 00781',
    'text': 'Door until part ask strong take. To imagine country structure many fall.\nCut build Democrat. Standard position meet material important foreign figure dark.',
    'email': 'dfloyd@example.net',
    'phone_number': '648.986.5989x014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Morris',
    'Joshua George',
    'Robert Blair',
    'Bradley Gross',
    'Julie Rivera',
],
    'json': {
    'name': 'Tiffany Clark',
    'address': '40903 Rachael Loaf Suite 152\nKristaview, NJ 92987',
},
    'key36164': 'value26875',
    'key47408': 'value32679',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Laura Garcia',
    'address': 'Unit 7799 Box 9639\nDPO AE 41118',
    'text': 'Box Congress structure idea prove case. What describe room possible child hospital. Start traditional place writer explain treat.',
    'email': 'eric89@example.net',
    'phone_number': '871.659.9240',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Monique Oneill',
    'Heather Le',
],
    'json': {
    'name': 'Melanie Strickland',
    'address': '4753 Kelly Via\nAlexanderside, CO 47514',
},
    'key2209': 'value18714',
    'key41865': 'value45531',
    'key71811': 'value7540',
    'key57937': 'value90632',
    'key10823': 'value1328',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Samuel Ortega',
    'address': '8565 Fuller Mill Apt. 988\nWest John, MI 65252',
    'text': 'Wrong property chair sign let recently mean who. Performance marriage choice wonder husband action what. Mother would effort within.\nAdult account second. Tax small push whose ok consumer away.',
    'email': 'cunninghamolivia@example.org',
    'phone_number': '+1-837-467-9620x3229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Ray',
    'Yvonne Myers',
    'David Willis',
    'Clinton Gilbert',
    'Holly Mitchell',
    'Scott Brown',
    'Kathleen Thomas',
    'Jessica Smith',
    'Mark Williams',
    'Casey Hall',
],
    'json': {
    'name': 'Alexis Robinson',
    'address': 'Unit 7596 Box 4114\nDPO AA 04061',
},
    'key25159': 'value42945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Erin Schmidt',
    'address': '95171 Michael Union\nBenjaminmouth, GU 60210',
    'text': 'Feeling list read air manager institution true last. Fact write gun which some institution.\nSing management ahead form newspaper project. Indeed later rock organization good follow build nearly.',
    'email': 'johncampbell@example.net',
    'phone_number': '956.713.2823x577',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kristopher Navarro',
    'Micheal Sullivan',
    'Alison Watkins',
    'Mary Clark',
    'Cheryl Carter',
    'Suzanne Williamson',
    'Ruben Winters',
    'Corey White',
    'Kimberly Shaw',
],
    'json': {
    'name': 'James Johnson',
    'address': 'Unit 9971 Box 5647\nDPO AP 14660',
},
    'key72579': 'value78574',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Jordan Bennett',
    'address': '858 Drake Trace\nLake Jennifer, DC 53441',
    'text': 'Woman sound hair contain. Forget thing position again. Law future product political television.',
    'email': 'keithsalinas@example.org',
    'phone_number': '333.949.7749',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Willie Conrad',
    'Samantha Jones',
    'Garrett Rivas',
    'Darren Barnett',
    'Darren Simon',
    'John Taylor',
    'Cassandra Delgado',
    'Gregory Carson',
    'Angela Holland',
],
    'json': {
    'name': 'Barbara Foster',
    'address': '92626 Gina Well Suite 619\nNew Chad, NV 44095',
},
    'key99646': 'value86616',
    'key540': 'value11472',
    'key74172': 'value24939',
    'key66422': 'value32300',
    'key16731': 'value81788',
    'key38807': 'value37565',
    'key66410': 'value35593',
    'key74274': 'value26676',
    'key96096': 'value69614',
    'key71798': 'value47687',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Anthony Henderson',
    'address': '49532 Megan Plaza Apt. 982\nEast Ann, CO 93309',
    'text': 'Nation range there avoid reality significant situation. Attorney lawyer half many. Century nearly start personal.\nHis avoid article local performance. I contain song everyone talk not Congress.',
    'email': 'pacemarcus@example.org',
    'phone_number': '001-670-330-3303x8989',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Ramirez',
    'Mitchell Benton',
    'Christina Harris',
],
    'json': {
    'name': 'David Walls',
    'address': '4065 Mccoy Union\nMatthewfurt, AZ 07879',
},
    'key46760': 'value40777',
    'key72684': 'value63924',
    'key99305': 'value86849',
    'key41116': 'value88488',
    'key41897': 'value26855',
    'key63750': 'value70726',
    'key85494': 'value31153',
    'key3438': 'value33034',
    'key57269': 'value42234',
    'key62671': 'value77083',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Angela Henderson',
    'address': 'PSC 6289, Box 8157\nAPO AP 59280',
    'text': 'Pretty foreign compare would expect fill citizen. Others maintain boy pressure. Arrive leader probably ask couple.\nAgree Republican machine economy shake but. Hold of able short be crime so.',
    'email': 'adamgarrett@example.net',
    'phone_number': '948-739-6238x297',
    'array_int_dynamic': [
    49988,
],
    'array_varchar_dynamic': [
    'Teresa Sandoval',
    'Madison Mccarthy',
    'Lacey Wilson',
],
    'json': {
    'name': 'Theresa Scott',
    'address': '03347 Weaver Rue\nNew Terry, ID 98004',
},
    'key6266': 'value51151',
    'key57402': 'value82383',
    'key5808': 'value21819',
    'key8999': 'value66173',
    'key48642': 'value44329',
    'key14335': 'value46041',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Joseph Lester',
    'address': '93058 Jennifer Branch\nKeithville, PA 48161',
    'text': 'Yeah message various without national letter. Significant send city activity or some sit chance. Picture avoid admit along certainly leave.',
    'email': 'normanalex@example.net',
    'phone_number': '(370)271-7800x652',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Griffin',
    'Alan Phillips',
],
    'json': {
    'name': 'Sandra Richardson',
    'address': '0192 James Freeway Apt. 322\nLorettaport, AS 30630',
},
    'key52808': 'value93587',
    'key80964': 'value60770',
    'key30714': 'value40398',
    'key63199': 'value90420',
    'key94626': 'value17015',
    'key58390': 'value89478',
    'key10420': 'value64028',
    'key39849': 'value17694',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Alex Andrade',
    'address': 'USNS Ramirez\nFPO AP 58632',
    'text': 'Usually vote station cultural spend the operation smile. Us party window picture either well. Ability positive simply eight.',
    'email': 'steelesusan@example.com',
    'phone_number': '+1-526-753-3723x56605',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Johnson',
    'Adrian Vasquez',
    'Steven Webb',
    'Timothy Rice',
    'Dr. Amy Clark',
    'Donna Rodriguez',
    'Philip Mercer',
],
    'json': {
    'name': 'Whitney Rogers',
    'address': '03621 Daniel Brooks\nCassidyton, CT 80564',
},
    'key84390': 'value59333',
    'key15868': 'value4175',
    'key23074': 'value95277',
    'key44039': 'value7869',
    'key22293': 'value5569',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Sarah Ware',
    'address': '398 Anderson Shore Apt. 022\nVictorside, NM 78038',
    'text': 'Security man rock. Market capital at stand fear.\nTurn establish apply understand raise. Remember address pick my how cup. Federal though attack gas all imagine.',
    'email': 'wharmon@example.org',
    'phone_number': '809.549.3700',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tony Mann',
    'Jack Moore',
    'Joseph Merritt',
    'Laura Decker',
    'Seth Johnson',
    'Jeremiah Poole',
    'Amanda Smith',
    'Travis Carrillo',
    'Johnathan Edwards',
    'Matthew Marshall',
],
    'json': {
    'name': 'Ronnie Hughes',
    'address': '58628 Adams Corners\nNorth Tiffanytown, CA 78296',
},
    'key48588': 'value79941',
    'key71751': 'value77733',
    'key71093': 'value62436',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jonathan Brown',
    'address': '11141 Daryl View\nNew Randystad, MS 35356',
    'text': 'Cost back as consumer owner. Notice style dream stuff six their.\nTurn put maybe financial senior produce. Be want several security rich small bring.',
    'email': 'elliottjanet@example.net',
    'phone_number': '+1-442-239-5128x55089',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Angela Reynolds',
],
    'json': {
    'name': 'Michelle Obrien',
    'address': '210 Jenkins Underpass\nWest Jonport, MA 34721',
},
    'key93756': 'value44283',
    'key54340': 'value88561',
    'key96745': 'value75645',
    'key36605': 'value59830',
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
    'RequestId': '0ee70e94-62f1-11f0-be42-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_00_232356WVzixqFd',
    'filter': '10+20 <= uid < 20+30',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'phone_number',
    'name',
    'email',
    'json',
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



    def test_request_3(self):
        """测试请求 3 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '082d7d8f-62f1-11f0-b4f9-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_00_232356WVzixqFd',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-10+20 <= uid < 20+30]_1752744792.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrue1020Uid20301752744792Json()
    test.run_tests()
