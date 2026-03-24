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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752744805_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752744805.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUidIn12341752744805Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752744805.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752744805.json"
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
    'RequestId': '1029119b-62f1-11f0-ac34-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_13_625134efFzgqXt',
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
    'RequestId': '1347a185-62f1-11f0-9a37-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_13_625134efFzgqXt',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Karen Howard',
    'address': '20890 Tanya Glens Suite 222\nNorth Derekfurt, MH 06903',
    'text': 'Beyond thus into morning.\nCondition game material word anything. Expect memory cause receive explain bad send might. Financial she knowledge offer.',
    'email': 'smoore@example.net',
    'phone_number': '001-641-465-5597',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Phillips',
    'Ashley Young',
    'Jennifer Thomas',
    'Cheryl Adams',
    'Maria Gonzalez',
    'Sara Singleton',
    'Anna Nicholson',
],
    'json': {
    'name': 'Amber Stewart',
    'address': '1124 Hinton Crossroad Apt. 616\nVargasport, AR 54698',
},
    'key39359': 'value74124',
    'key95276': 'value68728',
    'key8347': 'value88241',
    'key83143': 'value84530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Christopher Livingston',
    'address': '5543 Carter Radial Apt. 488\nLake Sethchester, CA 50736',
    'text': 'Nor middle be wrong rate. Public baby trip great try. Sure risk history card.\nWorker morning red. Beat firm talk them.\nOk majority son relationship. Card guess include between right world.',
    'email': 'gabrielmoore@example.net',
    'phone_number': '8388462695',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Travis Steele',
    'James Garcia',
    'Charles Cole',
    'James Carroll',
],
    'json': {
    'name': 'David Lucas',
    'address': '33329 Samantha Meadows\nEast Gary, UT 59629',
},
    'key80256': 'value47215',
    'key17597': 'value44715',
    'key26007': 'value72434',
    'key48290': 'value81044',
    'key24854': 'value49606',
    'key36177': 'value76639',
    'key91431': 'value54910',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Eric Garcia',
    'address': '350 Lynn Bridge\nNorth Robertborough, NC 12086',
    'text': 'Indicate media people specific have article hand. Fine early decide among hear population news risk.\nHere soldier miss. See level not among.',
    'email': 'xrodgers@example.com',
    'phone_number': '001-534-515-5380',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Phyllis Gutierrez',
    'Kevin Thornton',
    'Bruce Castillo',
    'Michael Scott',
],
    'json': {
    'name': 'Courtney Harris',
    'address': '9129 Sexton Village\nRayfurt, RI 92759',
},
    'key90073': 'value18769',
    'key62174': 'value69785',
    'key39781': 'value39987',
    'key24451': 'value90208',
    'key60702': 'value86705',
    'key46747': 'value23154',
    'key72672': 'value96293',
    'key40202': 'value86577',
    'key54465': 'value97334',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jacob Pena',
    'address': '28553 Andrea Coves Apt. 206\nPort Alexanderville, AZ 57326',
    'text': 'Around as kind boy probably. End front watch region alone service.\nShow hospital billion face. Light two including until plant person. Gun eye keep staff factor media century.',
    'email': 'jenkinsjustin@example.org',
    'phone_number': '(700)439-3130x7773',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Rick Anthony',
    'David Willis',
    'Nicholas Mckinney',
    'Robin Salinas',
    'Christopher Obrien',
    'Chad Garza',
    'Sarah Pope MD',
    'Lauren Malone',
],
    'json': {
    'name': 'Sabrina Becker',
    'address': '6457 Larry Station Apt. 754\nNew Williamchester, GA 28281',
},
    'key22956': 'value86355',
    'key49684': 'value99254',
    'key41454': 'value99142',
    'key3225': 'value81176',
    'key35618': 'value84402',
    'key39324': 'value44834',
    'key42260': 'value22200',
    'key66015': 'value27971',
    'key41400': 'value44963',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Michael Wagner',
    'address': '03661 Mcfarland Passage Apt. 801\nLake Dawn, DC 92518',
    'text': 'Behavior treat edge tree exist order. Visit almost feel less. Respond left think traditional work score allow.\nCenter black huge. Wrong design real design ok reflect.\nEach seat think to small eye.',
    'email': 'moorescott@example.org',
    'phone_number': '+1-516-904-3683x7697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Angel Perry',
    'Heidi Miller',
],
    'json': {
    'name': 'Joseph Fleming',
    'address': '68268 Rodriguez Glen Apt. 629\nLake Dylan, MD 88086',
},
    'key22684': 'value88634',
    'key88914': 'value11371',
    'key66778': 'value19093',
    'key4844': 'value47238',
    'key80892': 'value27057',
    'key41239': 'value26412',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Melanie Owens',
    'address': '9733 Sean Tunnel Apt. 355\nEast Tammy, MN 44989',
    'text': 'Authority information Democrat magazine Congress social thought. Pressure clear rise authority current physical sport. Study station business end experience gun officer.',
    'email': 'nicholas25@example.com',
    'phone_number': '424.912.2228x4213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Aguilar',
],
    'json': {
    'name': 'Kyle Robinson',
    'address': '290 Daniel Club\nLake Maria, KY 84663',
},
    'key78958': 'value49498',
    'key13318': 'value77347',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Steven Bennett',
    'address': '746 Dawn Unions Suite 851\nWest Stephanieland, AL 80304',
    'text': 'Either consider challenge report sort. Model about thing wait role form heavy.\nEnergy speak movement help without book. Leader activity once once without friend nation.',
    'email': 'robertaharris@example.org',
    'phone_number': '(452)428-0784x827',
    'array_int_dynamic': [
    2819,
],
    'array_varchar_dynamic': [
    'Lindsey Watson',
    'Jeffery Rodriguez',
    'Andrew Pope',
    'Michael Mitchell',
    'Justin Watson PhD',
    'Bradley Porter',
    'Amber Conway',
    'Carl Adams',
],
    'json': {
    'name': 'Emily Wagner',
    'address': '8523 Stafford Drive\nNew Jeremy, AZ 40599',
},
    'key17024': 'value3247',
    'key98314': 'value87704',
    'key11049': 'value40452',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Joe Reid',
    'address': '3592 Schroeder Prairie\nNew Andrea, MS 14909',
    'text': 'Series matter court people together various. Identify despite anything mention sister wind worry. Their base century score according yourself significant.',
    'email': 'emilyreeves@example.net',
    'phone_number': '001-901-630-3033x362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lori Perry',
    'Brooke Walker',
],
    'json': {
    'name': 'Ian Butler',
    'address': '2812 Owens Underpass Apt. 081\nSouth Anthony, AK 46686',
},
    'key56017': 'value83163',
    'key22939': 'value12344',
    'key69123': 'value57544',
    'key10823': 'value50597',
    'key46950': 'value58172',
    'key93232': 'value81043',
    'key67369': 'value69506',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Robyn Scott',
    'address': '6373 Buchanan Row Apt. 991\nEast Michael, ND 49159',
    'text': 'Hot many town try possible. Bag national result hard animal Mr. Resource fact population commercial chair main time.',
    'email': 'aanderson@example.com',
    'phone_number': '+1-230-261-8951x948',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alan Edwards',
    'Yesenia Foster',
    'Cynthia Kennedy',
    'Marcus Martinez',
    'Kathleen Brandt',
    'Jack Murray',
    'Kevin Gilmore',
    'Lauren Johnson',
],
    'json': {
    'name': 'Steven Woods',
    'address': '1071 Lisa Row Apt. 338\nMichaelburgh, GU 01848',
},
    'key48862': 'value42741',
    'key53336': 'value10716',
    'key51939': 'value92909',
    'key60167': 'value47980',
    'key97618': 'value5028',
    'key42587': 'value22748',
    'key10970': 'value75141',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Daniel Graham',
    'address': '36241 Lee Pass\nSouth Francisco, RI 28123',
    'text': 'Per another policy material on himself bar debate. He life just war beat you anything. White find born use maybe.',
    'email': 'johngonzalez@example.org',
    'phone_number': '854.220.6503x49298',
    'array_int_dynamic': [
    31322,
],
    'array_varchar_dynamic': [
    'Peter Johnson',
    'Patricia Williams',
],
    'json': {
    'name': 'Kristi Schmidt',
    'address': 'USNV Burnett\nFPO AP 98007',
},
    'key67746': 'value66571',
    'key17965': 'value78851',
    'key40290': 'value27791',
    'key33549': 'value46684',
    'key71360': 'value74178',
    'key18240': 'value73164',
    'key29655': 'value26044',
    'key56274': 'value48966',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Benjamin Johnson',
    'address': '949 Gonzalez Rue\nSheilaside, IA 01475',
    'text': 'Need prove long. Free whom baby set every sister red. Against law indicate name stand front.\nHome last within not discover. Throw site miss.',
    'email': 'sanchezcharles@example.net',
    'phone_number': '001-511-496-1405x7715',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Macias',
],
    'json': {
    'name': 'Kimberly Rose',
    'address': '96073 Sanders Drives Suite 857\nLake Jaredburgh, MN 61136',
},
    'key39259': 'value44297',
    'key2915': 'value23010',
    'key82447': 'value49995',
    'key10331': 'value63498',
    'key2194': 'value81669',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Roger Barnett',
    'address': '3555 David Spring\nSouth Kelli, PR 94157',
    'text': 'Whether nation general miss of people. Left piece college rock itself. Sister difference out sometimes could television itself.',
    'email': 'jennyweaver@example.net',
    'phone_number': '945.254.5472x220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Chad Cuevas',
    'Peter Stephens',
    'Jillian Robinson',
    'Abigail Cameron',
    'Mark Gray',
    'Rachel White',
    'Joseph Novak',
    'Amanda Murray',
    'Joseph Fisher',
    'Daniel Villa',
],
    'json': {
    'name': 'Amanda Brown',
    'address': '562 Jeff Mountains Apt. 601\nWest Dustin, AS 45820',
},
    'key98563': 'value94992',
    'key76718': 'value6851',
    'key79515': 'value6763',
    'key77325': 'value31879',
    'key58226': 'value46495',
    'key13499': 'value34297',
    'key91378': 'value25464',
    'key60773': 'value38758',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Christopher Parsons',
    'address': '1153 Green Motorway\nGibsonton, IL 76097',
    'text': 'Class evening add respond none travel. Trial this number say interesting growth sort. Half resource somebody light production act.',
    'email': 'brownalfred@example.org',
    'phone_number': '(329)555-8400',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alison Smith',
    'Lisa Chavez',
    'Alexander Smith',
],
    'json': {
    'name': 'Tyler Richard',
    'address': '69593 Gutierrez Turnpike Suite 327\nAmymouth, GA 56400',
},
    'key70604': 'value15382',
    'key40404': 'value7515',
    'key96066': 'value77322',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Victor Parker',
    'address': '82077 Samuel Junction Apt. 528\nRamoshaven, VI 52659',
    'text': 'Wrong evidence expert career hold bar. Television tonight issue reduce item condition party prepare. Nation between thought interesting nature possible.',
    'email': 'williamscarly@example.net',
    'phone_number': '866-254-1600',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jimmy Aguilar',
    'William Harrison',
    'Kelly Wood',
    'Betty Roberts',
    'Daniel Moore',
    'Brian Wilkerson',
    'Nancy Jennings',
    'Jacqueline Bradshaw',
    'Brittany Lam',
    'Sarah Harrington',
],
    'json': {
    'name': 'Amber Jones',
    'address': '9688 Wilson Fall Suite 893\nMichaelburgh, IA 86769',
},
    'key60639': 'value51022',
    'key46203': 'value5467',
    'key15090': 'value19738',
    'key78642': 'value64432',
    'key57850': 'value99750',
    'key94392': 'value1289',
    'key81127': 'value14813',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Tracy Simpson',
    'address': '38240 Donald Fort\nNew Jerome, PW 46372',
    'text': 'Take simple reason go surface American might. Action hope writer issue couple difference role.',
    'email': 'jenkinsdanny@example.net',
    'phone_number': '+1-659-827-7763x6825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'David Willis',
    'Carlos Bailey',
    'Tara Jordan',
    'Megan Gonzalez DVM',
    'Derrick Yoder',
    'Destiny Lucero',
    'Evan Patterson',
    'Raymond Huang',
    'Thomas Leach',
],
    'json': {
    'name': 'Brooke Castaneda',
    'address': '522 Jenny Forks Suite 904\nWest Pamelatown, AL 88316',
},
    'key38869': 'value72931',
    'key62192': 'value9816',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Barbara Fitzpatrick',
    'address': '9990 Lawson Highway\nMorganberg, CA 99475',
    'text': 'Again pull relationship power field place. Car audience box. Position data per human become instead leader generation.',
    'email': 'reevessarah@example.net',
    'phone_number': '+1-384-590-1080x1997',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Hector Williams',
    'Kimberly Reese',
    'Teresa Mcbride',
    'Louis Moreno',
    'Ashley Rogers',
    'Jordan Schmidt',
    'Anna Oliver',
    'Timothy Robinson',
    'Anna Young',
],
    'json': {
    'name': 'Sherry Martinez',
    'address': '439 Marquez Rue\nLake Troychester, DE 98093',
},
    'key87414': 'value13893',
    'key33254': 'value74020',
    'key75361': 'value91092',
    'key4472': 'value36352',
    'key89426': 'value46979',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Jonathon Brown',
    'address': '279 Hale Wells\nSouth Tina, OH 38286',
    'text': 'For fall evening. We cut institution establish including product surface.',
    'email': 'uyoung@example.org',
    'phone_number': '557.685.4394x72535',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Connie Bennett',
    'Brianna Baldwin',
    'Katherine Rodriguez',
    'Christopher Jensen',
    'Dakota Robinson',
    'Juan Parker',
    'Robert Adams',
    'Joseph Garcia',
    'Shannon Frank',
],
    'json': {
    'name': 'Hailey Ramirez',
    'address': '653 Long Place\nWigginsshire, MS 98112',
},
    'key10145': 'value45530',
    'key12589': 'value83168',
    'key95826': 'value2822',
    'key95438': 'value89430',
    'key88324': 'value86472',
    'key22135': 'value57016',
    'key38159': 'value65030',
    'key61061': 'value85906',
    'key99756': 'value88785',
    'key90502': 'value90499',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'James Johnson',
    'address': '9667 Young Corners\nSouth Kennethmouth, OK 38722',
    'text': 'By those blue appear. Law performance my force traditional report lead. Might along more century.',
    'email': 'whitejeffery@example.org',
    'phone_number': '001-760-275-1767x39269',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Reginald Hawkins',
    'Rachel Jones',
    'Clayton Chavez',
    'Jennifer Holmes',
],
    'json': {
    'name': 'Sean Chapman',
    'address': 'PSC 9386, Box 2903\nAPO AE 41565',
},
    'key81639': 'value7074',
    'key89774': 'value20090',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Jared Walker',
    'address': '27026 Black Drives Apt. 265\nNew Susanburgh, FL 30617',
    'text': 'Mouth beat free attack form defense. Play some seven history. Those plant among possible.\nPm high yard before seven country. Within hand such travel up.\nSecurity long citizen pressure he member.',
    'email': 'graveslauren@example.com',
    'phone_number': '264-286-7284x179',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Hayes',
    'John Greer',
    'Chad Blake',
    'Christopher Torres',
    'Sandra Carroll',
    'Anthony Bennett',
    'Alan Goodwin',
],
    'json': {
    'name': 'Roger Chung',
    'address': '498 Carroll Drive\nWest Robert, MT 78355',
},
    'key31891': 'value91128',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jade Baker',
    'address': '6555 Hale Junction Apt. 876\nNew Lauraside, MO 55929',
    'text': 'Company good relationship police. Scientist subject finish study history single Democrat need. Role save begin professor.',
    'email': 'nhood@example.org',
    'phone_number': '737.496.1211',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kristina Robinson',
    'Mr. David Mckinney',
    'Paul Perez',
    'Marisa King',
    'Michelle Griffin',
    'Christopher Johnson',
    'Joseph Tran',
    'Tyler Hall',
    'Madison Knight',
],
    'json': {
    'name': 'Brandon Reid',
    'address': '2901 Hester Ford\nGarzafurt, AZ 33802',
},
    'key64515': 'value22127',
    'key3087': 'value73562',
    'key25641': 'value17146',
    'key38922': 'value65912',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Lauren Mccoy',
    'address': '38607 Roger Point\nLake Justin, GU 38035',
    'text': 'Allow machine moment activity less middle social. Partner reflect customer article each suffer. No heavy campaign choose worry. Option pick our nature not sing past they.',
    'email': 'steven32@example.com',
    'phone_number': '616.864.4602x680',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Heath',
    'Steven Mitchell',
    'Megan Bowman',
],
    'json': {
    'name': 'Benjamin Sutton',
    'address': '205 Kenneth Keys Suite 191\nNew Raymondfort, PR 59831',
},
    'key25554': 'value95360',
    'key50135': 'value66165',
    'key37494': 'value24559',
    'key61632': 'value20147',
    'key72864': 'value47832',
    'key78500': 'value84094',
    'key3000': 'value49862',
    'key35515': 'value82100',
    'key83906': 'value78977',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jesse Lewis',
    'address': '563 Kathleen Grove Suite 264\nSouth Erica, CT 87397',
    'text': 'Smile worry leader sound build action. You campaign anything edge dream college executive. Million standard imagine strong anything.\nOnto yes from program year step lose.',
    'email': 'knightkristine@example.net',
    'phone_number': '(386)824-0407x1572',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Laura Bryan',
    'Christine Giles',
    'Darryl Hall',
],
    'json': {
    'name': 'Paul Mendez',
    'address': '032 Richard Spurs\nBranchhaven, PW 54490',
},
    'key92899': 'value93309',
    'key80516': 'value68691',
    'key33281': 'value86862',
    'key55811': 'value37644',
    'key98257': 'value22547',
    'key38653': 'value24565',
    'key9796': 'value97895',
    'key87386': 'value1373',
    'key30869': 'value33936',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Jeffrey Mccoy',
    'address': '51885 Clay Camp Apt. 890\nWest Jesus, CO 53749',
    'text': 'Dog spend produce. Deal then doctor.\nAct do month lose. Realize garden card Mr employee above take. Significant business green there check plant everyone.',
    'email': 'karl38@example.org',
    'phone_number': '(280)507-2323x1116',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Harvey',
    'Michelle Daugherty',
    'April Parker',
],
    'json': {
    'name': 'Zachary Nguyen',
    'address': '4270 Patricia Tunnel Apt. 106\nOrtizhaven, WI 82005',
},
    'key27745': 'value57182',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Abigail Brooks',
    'address': '7980 Cooper Walk\nLeeborough, NM 25849',
    'text': 'Partner front catch away rather decade two. Attention best floor institution bank. Card major federal six girl. Worker certainly along around rather imagine.',
    'email': 'dmccoy@example.com',
    'phone_number': '001-807-998-1289x5367',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Gabriel Mann',
    'Ashley Jackson',
    'Joseph Sanchez',
    'Kimberly Clark',
    'Joshua Peterson',
    'Karina Green',
    'Heather Carpenter',
    'David Ford',
    'Natalie Potts',
    'John Alexander',
],
    'json': {
    'name': 'Debbie Ray',
    'address': '658 Taylor Cliffs Suite 930\nSouth Drewstad, VT 66039',
},
    'key19265': 'value24138',
    'key88074': 'value46711',
    'key69073': 'value41513',
    'key92561': 'value68662',
    'key67506': 'value2214',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Vanessa Randall',
    'address': '01619 Donald Views Apt. 982\nTheresaburgh, PR 24842',
    'text': 'Hundred hit environmental off measure resource care. Least west act major what place find.\nAhead business child less. Fact difference picture rate. Whole line concern miss edge something.',
    'email': 'sarah08@example.net',
    'phone_number': '(678)472-8232x1759',
    'array_int_dynamic': [
    73925,
],
    'array_varchar_dynamic': [
    'Paula Peck',
    'Lauren Martinez',
    'Jenna Wilson',
    'Amanda Herman',
    'Maurice Rivera',
    'Vanessa Miranda',
],
    'json': {
    'name': 'Daniel Martin',
    'address': '02790 Richard Point\nSouth Courtneyville, MO 71479',
},
    'key27522': 'value15685',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Martin Moreno',
    'address': '378 Jeffrey Ports Suite 772\nNorth Joseside, MO 98743',
    'text': 'Our experience issue go capital. Discussion prove probably people man clearly.\nMoney bad try information prevent physical. Product hit range idea week as.',
    'email': 'gardnervictor@example.org',
    'phone_number': '346-978-9642x358',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Jenkins',
    'Katherine Washington',
    'James Norton',
    'Kevin Ross',
],
    'json': {
    'name': 'Regina Jackson',
    'address': '38061 Peterson Radial\nLake Angel, OR 08417',
},
    'key52008': 'value55815',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jennifer Koch',
    'address': '210 Morris Terrace\nPort Michelleborough, CA 60568',
    'text': 'Military remain why so prove leave difficult peace. Picture more decide democratic. Sea low perhaps general religious.',
    'email': 'bperry@example.net',
    'phone_number': '(531)887-9575x897',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Garcia',
    'Kevin Murphy',
    'Claire Lopez',
    'Ryan Rasmussen',
    'Justin Reed',
    'John Peck',
    'Kayla Miranda',
],
    'json': {
    'name': 'Chad Barron',
    'address': 'USCGC Harrison\nFPO AP 23145',
},
    'key94630': 'value19579',
    'key46074': 'value49607',
    'key42571': 'value49047',
    'key60645': 'value5704',
    'key8432': 'value42067',
    'key98336': 'value54790',
    'key15859': 'value9294',
    'key50345': 'value51158',
    'key51348': 'value76113',
    'key66814': 'value14343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Corey Olson',
    'address': '128 Michael Curve Suite 257\nWest Kimberly, VA 34483',
    'text': 'Game on rock Mr third film. Couple with prove citizen save trouble stage. Son beyond cover ahead tend every somebody. Day environment dark nature return.\nBody prevent base I forward.',
    'email': 'williamsmith@example.com',
    'phone_number': '9378642342',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Love',
    'Daniel Edwards',
    'Desiree Greene',
    'Leah Garcia',
    'Anthony Goodman',
    'Christina Carpenter',
],
    'json': {
    'name': 'Michael Diaz',
    'address': '8771 Stephanie Mountains Apt. 399\nLorifort, MP 97188',
},
    'key4747': 'value10482',
    'key18716': 'value72981',
    'key97913': 'value27530',
    'key58647': 'value85455',
    'key58': 'value52517',
    'key4220': 'value65779',
    'key77635': 'value24080',
    'key38017': 'value23890',
    'key82310': 'value79761',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Cory Hays',
    'address': 'USNV Stewart\nFPO AP 19433',
    'text': 'Meeting couple strong company woman small feeling. Money scientist customer work.\nSeat yeah everybody effort medical ready. Whatever expert serve international common together civil.',
    'email': 'tvalenzuela@example.net',
    'phone_number': '3689566856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Haley Brandt',
    'Rachel Page',
    'Stephanie Bradley',
    'Dennis Smith',
    'James Watson',
    'Leslie Jones',
    'Elizabeth Sharp',
    'Derek Hudson',
    'Aaron Gray MD',
    'Ms. Brenda Turner',
],
    'json': {
    'name': 'Mark Gardner',
    'address': '6470 Rogers Alley Apt. 394\nPort Robert, DC 12621',
},
    'key11300': 'value33385',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Andre Odonnell',
    'address': '61728 Blankenship Hill Suite 679\nWest Ryanmouth, IL 28310',
    'text': 'Ball south candidate lay. Increase believe tree morning arrive herself.\nPattern different president generation ago. Discussion possible other make.',
    'email': 'lozanorobert@example.org',
    'phone_number': '773.870.9389x9426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kent Mckinney',
    'David Hurst',
],
    'json': {
    'name': 'Alexandria Hill',
    'address': '34437 Timothy Isle\nWest Aprilchester, ID 97722',
},
    'key86493': 'value39796',
    'key57045': 'value65771',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Michael Nichols',
    'address': '72840 Salas Garden Apt. 120\nRebekahshire, OH 18414',
    'text': 'Health feel large because check. Make wish street election surface will they worry. Environment last life question education fly.',
    'email': 'keithdixon@example.com',
    'phone_number': '869.338.0265x507',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Collins',
    'Stephen Rubio',
    'Jimmy Burke',
    'Stephen Alvarado',
    'Jacob Brown',
    'James Armstrong',
    'Ronald Barajas',
    'Richard Hall',
    'Megan Sawyer',
],
    'json': {
    'name': 'Billy Ochoa',
    'address': '6427 Simmons Heights\nWoodsland, WA 95259',
},
    'key98741': 'value52975',
    'key12451': 'value24273',
    'key34922': 'value79314',
    'key21161': 'value55939',
    'key87803': 'value89313',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Alexander Brennan',
    'address': '6735 Rivera Field Apt. 144\nNew Jessica, FL 33785',
    'text': 'Avoid service maybe throw. Section husband image trial medical. Music long factor production.\nPut successful window sport eight push onto. Stage hand song list political tough.',
    'email': 'mclaughlinmarvin@example.com',
    'phone_number': '+1-240-638-1864x806',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Carroll',
],
    'json': {
    'name': 'Amy Sanchez',
    'address': '4134 Miguel Hills\nNorth Tamaramouth, NM 64079',
},
    'key77777': 'value69248',
    'key10487': 'value9365',
    'key12238': 'value81152',
    'key57266': 'value55079',
    'key15841': 'value115',
    'key4938': 'value96844',
    'key8568': 'value71713',
    'key23599': 'value16078',
    'key61406': 'value97773',
    'key78603': 'value70308',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Angela Lopez',
    'address': 'PSC 7583, Box 8866\nAPO AA 75595',
    'text': 'So even customer around offer. Fire though section will agreement should.\nDesign camera forward. Enter up often reality analysis.',
    'email': 'ian38@example.com',
    'phone_number': '871.557.2401x2748',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michele Cobb',
    'Stephanie Barrett',
    'Olivia Dyer',
    'Jacqueline Quinn',
    'David Orr',
    'Sarah Ewing',
    'Daniel Jackson',
    'Anthony Solomon',
    'Steven Morgan',
],
    'json': {
    'name': 'Veronica Peters',
    'address': '63142 Rivera Forks Apt. 516\nVaughanstad, MS 05184',
},
    'key89212': 'value36204',
    'key53019': 'value95475',
    'key96109': 'value70367',
    'key90131': 'value31648',
    'key17649': 'value56695',
    'key55979': 'value83824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Nancy Watson',
    'address': '1017 Rebecca Ridge Suite 489\nPrincetown, ND 51153',
    'text': 'Result he explain west when hotel reflect. At style anything rule lead over. Speech material career once set determine.\nAppear three seven author food improve. Subject international friend physical.',
    'email': 'travismichelle@example.com',
    'phone_number': '(567)854-8246',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Darin Jones',
    'Melissa May',
],
    'json': {
    'name': 'Whitney Snow',
    'address': '70264 Robert Road Apt. 236\nDeniseside, VI 64840',
},
    'key76380': 'value45911',
    'key78167': 'value45857',
    'key85745': 'value80449',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'William Coleman',
    'address': '51515 Barber Fall Suite 754\nWest Thomas, NH 78822',
    'text': 'Old daughter detail cup live always poor. Reality since threat create sign. Article past thank here ability tend so new.',
    'email': 'bryan25@example.net',
    'phone_number': '631-804-2076x59236',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Diana Andrade',
    'John Griffin',
    'Deborah Moon',
    'David Smith',
    'Gabriel Garcia',
    'Candace Yates',
    'Carrie Freeman',
    'Jonathan Dillon',
    'Michael Wright Jr.',
],
    'json': {
    'name': 'Alexandria Bennett',
    'address': '1559 Sherry Lake Apt. 338\nDanielbury, ME 44287',
},
    'key9177': 'value51859',
    'key41642': 'value73319',
    'key9434': 'value42191',
    'key8298': 'value25885',
    'key84366': 'value98734',
    'key97265': 'value28975',
    'key47306': 'value43386',
    'key51075': 'value54534',
    'key19390': 'value59355',
    'key73043': 'value86942',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Daniel Bell',
    'address': '3083 Hayes Curve\nStonestad, TX 54092',
    'text': 'Book individual poor you modern get. Type reflect always rise meet. During material tell rather city require.',
    'email': 'jonesdiana@example.org',
    'phone_number': '+1-786-217-1280x876',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Rose',
    'Joshua Rodriguez',
    'Timothy Smith',
    'Wendy Wells',
    'Lisa Morales',
    'Jeremy Carson',
    'George Ponce',
],
    'json': {
    'name': 'Leslie Carr',
    'address': '0683 David Falls Suite 085\nThompsonbury, MA 11658',
},
    'key29277': 'value51783',
    'key76631': 'value79666',
    'key2993': 'value77379',
    'key9281': 'value37066',
    'key46940': 'value13030',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Walter Moore',
    'address': '370 Kenneth Track\nWest Matthew, VI 99523',
    'text': 'Ball into program power. Bring billion simple put.\nLeave school ok none body. System share free future defense poor top house. Reveal candidate form specific air whom or.\nBuild short say if.',
    'email': 'rlewis@example.org',
    'phone_number': '001-847-317-1540x9724',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Brianna Marshall',
    'Amber Waters',
    'Mr. Allen Collins',
    'Clinton Walker',
],
    'json': {
    'name': 'John Wilson',
    'address': 'USCGC Guzman\nFPO AP 85926',
},
    'key92607': 'value97156',
    'key5878': 'value17861',
    'key45664': 'value92373',
    'key49866': 'value99768',
    'key16168': 'value70068',
    'key9601': 'value34667',
    'key75557': 'value25233',
    'key44908': 'value88054',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Kenneth Anderson',
    'address': '4246 Jessica Run Apt. 958\nSouth Tiffanyshire, DE 28334',
    'text': 'Garden on generation just easy again. Ready technology result success try important push. Including although movie international light must.\nSimply sport movie long movement serve. Good spring try.',
    'email': 'zrandall@example.org',
    'phone_number': '+1-637-758-6014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jason Schneider',
    'Robert Smith',
    'Michael Morris',
    'Juan Torres',
    'Patricia Thomas',
    'Elizabeth Bowers',
    'Christopher Fernandez',
],
    'json': {
    'name': 'Sherry Bauer',
    'address': '51702 Sean Place Apt. 546\nChristinabury, RI 90249',
},
    'key10373': 'value34189',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Carlos Woods',
    'address': '4967 Chelsea Dam Suite 154\nNicoleview, RI 17670',
    'text': 'Population face while actually end remain. Magazine for sing author dog win child action.\nBelieve sport drive crime will peace budget. Before car which month book.',
    'email': 'danielrobinson@example.org',
    'phone_number': '001-329-382-5814',
    'array_int_dynamic': [
    44503,
],
    'array_varchar_dynamic': [
    'Natasha Gross',
    'Peter Perkins',
    'Jordan Burgess',
    'Bryan Hall',
],
    'json': {
    'name': 'Nicole Garza',
    'address': '0131 Harmon Manor\nAlisonberg, MP 96287',
},
    'key95653': 'value95764',
    'key90805': 'value32111',
    'key78083': 'value61405',
    'key19688': 'value73888',
    'key367': 'value93889',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Lisa Garrett',
    'address': 'USCGC Rosales\nFPO AP 86436',
    'text': 'International American weight beyond foreign. Energy also culture charge. Use arrive stock market environment.',
    'email': 'timothy12@example.net',
    'phone_number': '589.450.7215x32812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Marc Walker',
    'Lori Hurst',
    'Sarah Ramirez',
    'Evan Nichols',
    'Tiffany Taylor',
    'Monica King',
    'Elizabeth Garner',
    'Lynn Osborne',
    'Randy Boyer',
    'Katherine Mills',
],
    'json': {
    'name': 'Frederick Waters',
    'address': '96465 Jo Isle\nNorth Emily, NV 72896',
},
    'key22137': 'value39481',
    'key5025': 'value89870',
    'key25591': 'value85132',
    'key86929': 'value36222',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Nicole Bush',
    'address': '1206 Hughes Ports Suite 853\nMurphyberg, OH 25361',
    'text': 'Information edge find same traditional night.\nFew put option dog couple major area. Middle capital unit.',
    'email': 'beckwarren@example.org',
    'phone_number': '(241)832-7817x02824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Haley Woods',
    'Angela Flores',
],
    'json': {
    'name': 'Megan Vincent',
    'address': '256 Michael Track Apt. 857\nSouth John, DC 69242',
},
    'key653': 'value74528',
    'key33946': 'value65659',
    'key22751': 'value91796',
    'key31060': 'value88975',
    'key39488': 'value62665',
    'key69410': 'value67466',
    'key26213': 'value9490',
    'key59816': 'value78734',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Angela Ellis',
    'address': '6730 Alvarado Pine\nEast Ianview, NM 96763',
    'text': 'Might decide measure question whole another choose. Spend southern pattern improve feel.\nIf arm mother that soldier already. Consider prevent position statement exactly final street PM.',
    'email': 'knightdaniel@example.net',
    'phone_number': '223-211-2180',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Julia Myers',
],
    'json': {
    'name': 'Robin Andrews',
    'address': '16351 Alexis Course\nEast Hannah, FL 98663',
},
    'key60537': 'value91179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Alexandria Atkins',
    'address': '67791 Reyes Overpass\nRaymondview, AK 36410',
    'text': 'Tend give become economy behavior support. Person life professor owner accept film simple executive. Later of money similar either region stay.',
    'email': 'anthony19@example.com',
    'phone_number': '+1-942-605-9356x263',
    'array_int_dynamic': [
    59709,
],
    'array_varchar_dynamic': [
    'Jacob Colon',
    'Ryan Murray',
    'Jeffery Thomas',
    'Diana Moody',
    'Robert Reese',
    'Crystal Jackson',
    'Jack Fisher',
    'David Brown',
    'James Davis',
],
    'json': {
    'name': 'Andrea Andrews',
    'address': '7882 Jeffrey Gateway Apt. 367\nPedroton, AR 26107',
},
    'key6017': 'value43135',
    'key88519': 'value79017',
    'key19442': 'value53389',
    'key48774': 'value35505',
    'key3336': 'value2292',
    'key70332': 'value59232',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'John Martinez',
    'address': '539 Kane Cliffs\nNorth Michaelberg, CT 29817',
    'text': 'Expect follow executive best so show. Drop exist on public provide kind.\nReveal happen could. Make recognize than before.',
    'email': 'amymoore@example.net',
    'phone_number': '001-287-683-4390',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Autumn Molina',
    'Justin Parker',
    'John Valencia',
],
    'json': {
    'name': 'Lee Shelton',
    'address': '0394 Gabriel Divide\nDanielland, CO 31363',
},
    'key86339': 'value92239',
    'key9463': 'value32184',
    'key70665': 'value38265',
    'key50789': 'value38418',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Todd Farmer',
    'address': '265 Cruz Prairie\nSouth Christophermouth, IA 90814',
    'text': 'Phone action present officer machine cultural. As education purpose. Life suddenly may attention hard prepare rest. Shoulder what our voice range if college.',
    'email': 'samanthasimmons@example.net',
    'phone_number': '(497)330-1402x4684',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Lopez',
    'Charles Lewis',
    'Aaron Pacheco',
    'Jonathan Acosta',
],
    'json': {
    'name': 'Sherry Shannon',
    'address': '454 Oliver Trace\nWest Lisa, PA 02061',
},
    'key62967': 'value84669',
    'key22794': 'value88733',
    'key98072': 'value53226',
    'key73360': 'value20283',
    'key7048': 'value86020',
    'key98750': 'value27149',
    'key66376': 'value63501',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Samantha Olson',
    'address': '8652 Dylan Junctions\nNorth Donald, WA 72455',
    'text': 'Loss many executive you role interview event. Through politics prove window. Finally get must dark.\nSuccess case involve. Yet billion medical soldier beautiful west evening.\nHead exactly center.',
    'email': 'matthewsmathew@example.com',
    'phone_number': '806-710-1113',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Gallagher',
    'Patricia Eaton',
    'Kimberly Martinez',
    'Tina Leach',
    'Thomas Henderson',
    'David Mccann',
    'Lisa Warren',
],
    'json': {
    'name': 'Victoria Diaz',
    'address': '7033 Coleman Path Apt. 500\nLake Stacieshire, GU 29433',
},
    'key17893': 'value24776',
    'key14746': 'value56190',
    'key29225': 'value20522',
    'key80651': 'value36179',
    'key20546': 'value81980',
    'key77982': 'value94590',
    'key50637': 'value94263',
    'key4332': 'value7919',
    'key67418': 'value79065',
    'key71685': 'value511',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Karen Bell',
    'address': '9428 Amy Glens Apt. 650\nPort Sarah, SC 35779',
    'text': 'Ten series share page yard. They west culture street let.\nValue increase away. Media oil use run prove.',
    'email': 'jonesjon@example.net',
    'phone_number': '671.303.9455x89029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Renee White',
    'Christopher Joseph',
    'Kyle Mcdaniel',
],
    'json': {
    'name': 'Peter Hatfield',
    'address': '7035 Susan Cliffs Apt. 708\nGarciaside, PW 46534',
},
    'key36967': 'value32722',
    'key9899': 'value2728',
    'key36700': 'value90181',
    'key47188': 'value66935',
    'key86614': 'value63708',
    'key79158': 'value38291',
    'key50388': 'value37087',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'April Atkinson',
    'address': '561 Hubbard Islands Apt. 177\nMariomouth, FM 80210',
    'text': 'Teacher argue picture current. Shoulder whatever national able.\nBlack teach up decide rule. Key computer available blue nice recently. Central appear kid paper outside although beyond.',
    'email': 'pgarcia@example.com',
    'phone_number': '897.684.8982',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'John Edwards',
    'Ryan Olsen',
    'Joel Simmons',
    'Samantha Mcdonald',
    'Sydney Miller',
    'Kristi Gates',
    'April Bryant',
    'Stacey Wiley',
    'Lisa Norton',
],
    'json': {
    'name': 'Lindsey Roberts',
    'address': 'USNS Garcia\nFPO AP 21465',
},
    'key720': 'value91236',
    'key1682': 'value60363',
    'key75542': 'value42323',
    'key93819': 'value43625',
    'key75645': 'value34460',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Ashley Evans',
    'address': '3231 Christopher Orchard\nSamanthaview, NM 96256',
    'text': 'Arm grow nearly they check fish cell and. Manage lay fund performance on.\nRather place lawyer particular. Through north half upon approach young. Responsibility public cover property.',
    'email': 'tracy04@example.org',
    'phone_number': '290.956.3732',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Brown',
    'Alexandria Cabrera',
    'Amy Miller',
],
    'json': {
    'name': 'Luke Solis',
    'address': '0355 April Fort Suite 524\nPort Austin, MI 77569',
},
    'key33920': 'value58912',
    'key62577': 'value72156',
    'key3400': 'value81712',
    'key23251': 'value88709',
    'key85766': 'value58017',
    'key13021': 'value33950',
    'key56813': 'value30028',
    'key70187': 'value41726',
    'key28749': 'value55372',
    'key14699': 'value30486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Karen King',
    'address': 'Unit 7222 Box 7465\nDPO AP 69226',
    'text': 'History although major carry campaign.\nPretty including type indicate democratic economic alone. Various foot security cause personal yeah purpose option. Against it information.',
    'email': 'ryanbenjamin@example.com',
    'phone_number': '476-329-3930',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Richard Carpenter',
    'Jamie Fuller',
    'Dylan May',
    'Jesse Smith',
    'Annette Hall',
    'Christopher Smith',
    'Kim Hudson',
    'Nancy Hodge',
    'Donald Gomez',
],
    'json': {
    'name': 'Monique Brown',
    'address': '761 Justin Trace\nKristenbury, ND 07717',
},
    'key72037': 'value4512',
    'key97680': 'value9676',
    'key91558': 'value34165',
    'key31231': 'value67046',
    'key27818': 'value59513',
    'key83683': 'value97627',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Anthony Jennings',
    'address': '748 Wilson Locks Suite 944\nAngelabury, NC 96185',
    'text': 'Safe meet only. Building offer without affect or receive.\nWhen trip decision woman pressure. Career character allow. Most like bad place care.\nWife activity your citizen against.',
    'email': 'timothy76@example.org',
    'phone_number': '001-332-876-0669x281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mary Alexander',
],
    'json': {
    'name': 'Denise Carter',
    'address': '5599 Orozco Course Apt. 698\nLake Amberstad, WV 55552',
},
    'key55757': 'value95757',
    'key68576': 'value18860',
    'key53977': 'value41354',
    'key42617': 'value74756',
    'key28805': 'value29650',
    'key61233': 'value18484',
    'key79412': 'value85922',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Joshua White',
    'address': '27018 Alvarado Orchard\nWest Reginaport, IA 65713',
    'text': 'Candidate skin ground force risk word lot. Health we ability green.\nSee standard prove add lot arm main. Partner water mother black occur.\nMovement actually guess oil. Kid hundred will catch finally.',
    'email': 'matthew25@example.net',
    'phone_number': '9507900723',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Haley Turner',
    'Victoria Smith',
    'Nicholas Hodge',
    'Austin Thomas',
    'Laura Galvan',
    'Thomas Phillips',
],
    'json': {
    'name': 'Brooke Richardson',
    'address': '6610 Archer Land\nMorganburgh, MN 31894',
},
    'key72760': 'value89480',
    'key76626': 'value27448',
    'key6241': 'value10309',
    'key4479': 'value13763',
    'key6213': 'value37353',
    'key1644': 'value95018',
    'key75745': 'value30017',
    'key4058': 'value99320',
    'key10504': 'value60516',
    'key86377': 'value55749',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Allen Lucas',
    'address': '4538 Tanner Terrace\nPowellmouth, TX 37285',
    'text': 'Account baby student close election herself the evidence. Eye together decide wide I range friend.\nMilitary fund medical bad. Sometimes medical wish first. Send address body leg agree tree.',
    'email': 'terryjoshua@example.com',
    'phone_number': '(758)228-0398x3530',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brian Brewer',
    'Colleen Smith',
    'Jeffrey Murillo',
    'Isabella Watkins',
    'Tyler Martinez',
    'Eric Thomas',
],
    'json': {
    'name': 'Brian Gill',
    'address': 'Unit 9004 Box 2566\nDPO AE 68991',
},
    'key49970': 'value98318',
    'key46843': 'value51747',
    'key29945': 'value89489',
    'key48740': 'value20870',
    'key48999': 'value94284',
    'key69267': 'value26163',
    'key74818': 'value5465',
    'key82500': 'value29725',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'James Romero',
    'address': '568 Bishop Garden Suite 591\nNorth Danielleville, IL 58940',
    'text': 'Early human development. Summer toward lead.\nModern too smile.\nJob full official figure food. On last prepare good real open sound whether.\nList more arm charge image seven. That might good.',
    'email': 'gbush@example.com',
    'phone_number': '241.770.4457x43889',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Mendoza',
    'Molly Alexander',
    'Ross Briggs',
    'Craig Nicholson',
    'Cindy Davis',
    'Alison Brown',
    'Hayley Cunningham',
    'Bruce Turner',
    'Gary Campbell',
    'Kimberly Obrien',
],
    'json': {
    'name': 'Barry Davis',
    'address': '09243 Brian Stravenue\nEast Whitneyport, IA 49825',
},
    'key55823': 'value20648',
    'key19786': 'value15078',
    'key69945': 'value95011',
    'key48062': 'value98285',
    'key63934': 'value6921',
    'key49992': 'value10851',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Dylan Rosales',
    'address': '2106 Calhoun Terrace\nJohnside, ID 48662',
    'text': 'Turn reduce person. Law TV billion wife.\nFish baby song Republican sometimes mention method.\nRelationship until food.',
    'email': 'justin84@example.net',
    'phone_number': '+1-558-313-4459',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Frey',
    'Shawn Williams',
    'Kelly Graham',
    'Alexandra Smith',
    'Natalie Greene',
    'Terry Williams',
    'Kristen Thomas',
    'Mark Collins',
    'Daniel Molina',
],
    'json': {
    'name': 'William Johnson',
    'address': '1345 Adams Neck Suite 976\nSantoshaven, NM 66930',
},
    'key28476': 'value89104',
    'key59637': 'value68439',
    'key18098': 'value27747',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Julia Mitchell',
    'address': '8314 Christensen Mall Apt. 953\nRobertland, KS 23563',
    'text': 'Population floor land five trade charge. Among stop show book me machine. Company will so several detail.',
    'email': 'erinblackwell@example.org',
    'phone_number': '411-280-5499x289',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Sandoval',
    'Allison Larsen',
    'Randy Hunter',
    'Antonio Novak',
    'Donna Meyer',
    'Karen Turner',
    'Taylor Scott',
    'Alisha Griffith',
    'Karen Hernandez',
    'Caitlin Johnston',
],
    'json': {
    'name': 'Michael Cox',
    'address': '100 Cook Stravenue Apt. 011\nTammyville, PR 09388',
},
    'key22182': 'value41290',
    'key68500': 'value71157',
    'key1988': 'value39364',
    'key96113': 'value8976',
    'key96546': 'value53753',
    'key90294': 'value75588',
    'key44549': 'value84459',
    'key65327': 'value76960',
    'key14953': 'value50764',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Michael Long',
    'address': '2205 Monica Flats Apt. 561\nArnoldshire, AR 35760',
    'text': 'Again far charge product. Notice her window check safe condition event trouble. Record boy good news democratic degree.\nField risk ahead quality. Should ago source already.',
    'email': 'hflowers@example.org',
    'phone_number': '534-804-1825x2557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Angela Hall',
],
    'json': {
    'name': 'John Cannon',
    'address': '1707 Underwood Fall Apt. 777\nJohnsonstad, IN 71387',
},
    'key32883': 'value3677',
    'key99404': 'value22764',
    'key2039': 'value48440',
    'key97006': 'value44215',
    'key87323': 'value85531',
    'key23597': 'value45699',
    'key60287': 'value36821',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Tracy Ingram',
    'address': '61180 Gibson Motorway Suite 845\nTorresbury, MS 29170',
    'text': 'Street stage hospital least third business his. Huge her fact plant. On assume later prepare letter consumer action six.',
    'email': 'alison71@example.net',
    'phone_number': '(843)282-9959x217',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Richard Miles',
    'Rachel Swanson',
    'Drew Gutierrez',
    'Kimberly Jackson',
    'Misty Harris',
    'Jennifer Brennan',
    'Daniel Hernandez',
    'Traci James',
    'Douglas Mccullough',
],
    'json': {
    'name': 'Karen Fuentes',
    'address': '13025 Katherine Creek\nNorth Williamtown, NC 83004',
},
    'key30944': 'value72875',
    'key5461': 'value1486',
    'key80153': 'value23692',
    'key10310': 'value86118',
    'key55519': 'value81569',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Joseph Perkins',
    'address': '54515 Savannah Run\nDannyfurt, MO 01009',
    'text': 'Place opportunity for oil reveal wide. Call program administration. All hard position choice too.\nStill traditional fine glass. Protect each recent white specific of large.',
    'email': 'mharris@example.net',
    'phone_number': '618.730.1067x417',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Roy Mullins',
    'Joshua Davis',
    'Megan West',
    'Patricia Kirk',
    'Christian Anthony',
    'Nicholas Hill',
    'Jennifer Robinson',
],
    'json': {
    'name': 'Julie Thomas',
    'address': '9272 Edward Square Apt. 886\nNew Annaberg, PA 72294',
},
    'key53368': 'value94077',
    'key57693': 'value32575',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Ebony Hernandez',
    'address': '721 Hawkins Lights Suite 015\nSouth Angelamouth, MT 87514',
    'text': 'Address writer huge recognize fall. These along surface child rise though. Sometimes participant later most through themselves beautiful.',
    'email': 'bgraham@example.net',
    'phone_number': '3795236331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Renee Davis MD',
    'Jeffery Chen',
    'Johnny Shah',
    'Sarah Butler',
    'Danielle Miller',
    'Dennis Rivera',
    'Daniel Bowman',
],
    'json': {
    'name': 'Katherine Giles',
    'address': '747 David Avenue Suite 951\nSouth Christinaton, SC 85181',
},
    'key55089': 'value66098',
    'key50739': 'value80599',
    'key15091': 'value56134',
    'key16896': 'value81524',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Carl Hernandez',
    'address': '5420 Allison Shores\nNew Bradleymouth, OH 80030',
    'text': 'Measure practice head first. Election able lay effect concern fight hundred. Year also plan its charge success.\nDrop about social hit. Community since ago catch lose enough.',
    'email': 'philipwilcox@example.net',
    'phone_number': '001-322-696-8124x30461',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Francis',
    'April Williams',
    'Gary Bryant',
    'Benjamin Flores',
    'Hailey Mullins',
    'Lauren Rodriguez',
    'John Burke',
],
    'json': {
    'name': 'Robert Clark',
    'address': '078 Finley Circle\nSouth Johnberg, MD 77470',
},
    'key23037': 'value77288',
    'key97879': 'value25181',
    'key20418': 'value42129',
    'key68731': 'value12851',
    'key87590': 'value35786',
    'key68859': 'value34400',
    'key64587': 'value62139',
    'key95390': 'value15563',
    'key26276': 'value33762',
    'key49720': 'value2028',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'James Brown',
    'address': '89879 Mclean Isle\nZacharyview, DE 44908',
    'text': 'Mouth since court movie. Be prepare necessary billion. Well say year life exactly.\nPolice check card. Material water board become. Turn build challenge one serious TV.',
    'email': 'colerobyn@example.com',
    'phone_number': '956-500-1992x1574',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Beck',
    'Donna Osborne',
    'Melissa Davis',
    'Gloria Dougherty',
    'Sara Edwards',
    'Christopher Shepard',
    'Sharon Steele',
],
    'json': {
    'name': 'Teresa Williams',
    'address': '497 Robinson Rue\nLewisland, NY 56204',
},
    'key77367': 'value45503',
    'key56133': 'value78176',
    'key55045': 'value70619',
    'key94551': 'value51299',
    'key10425': 'value66845',
    'key57372': 'value41360',
    'key49534': 'value46431',
    'key66189': 'value82005',
    'key83467': 'value91857',
    'key16504': 'value86401',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Daniel Molina',
    'address': '049 Amanda Corner\nAaronland, TX 93734',
    'text': 'Major upon feeling such. Compare degree again we foot trade since. Us because enjoy push defense fill.\nWe item under. Work paper education bad never day six west.',
    'email': 'joseph28@example.com',
    'phone_number': '(766)957-2871x20593',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sean Blackwell',
    'Joseph Black',
    'Kimberly Garcia',
    'Mark Long',
],
    'json': {
    'name': 'Derek Morgan PhD',
    'address': '8895 Mcfarland Garden\nJesseberg, DE 48052',
},
    'key42457': 'value37050',
    'key72524': 'value48660',
    'key74945': 'value98997',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Kelsey Harris',
    'address': '98770 Anderson Views\nNorth Felicia, SD 55967',
    'text': 'At stage standard fast enough sign maybe. Oil forget court protect expert new back.',
    'email': 'ogaines@example.net',
    'phone_number': '452-335-0552x058',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mary Sanchez',
    'Douglas Lin',
    'Eric Reed',
    'Stephanie Hopkins',
    'Diane Mosley',
    'Shannon Le',
    'Kevin Henson',
    'Shawn Romero',
    'Michael Young',
],
    'json': {
    'name': 'Michael Schmidt',
    'address': '04736 Poole Plains Suite 196\nEast Brittanychester, AK 46926',
},
    'key22643': 'value21003',
    'key61279': 'value5185',
    'key93368': 'value12048',
    'key40447': 'value27189',
    'key89840': 'value21979',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Angela Martinez',
    'address': 'Unit 3366 Box 9209\nDPO AA 56383',
    'text': 'Response tax guy bag deep. Over simple indeed kitchen inside.\nDiscover big record maintain. Film member daughter media easy.',
    'email': 'anthonyestrada@example.com',
    'phone_number': '523.752.8158',
    'array_int_dynamic': [
    3533,
],
    'array_varchar_dynamic': [
    'Alison Peterson',
    'Seth Fischer',
    'Mary Zimmerman',
    'Dawn Marshall MD',
    'Christopher Thompson',
    'Scott Miller',
],
    'json': {
    'name': 'Scott Carter',
    'address': '6685 Lee Loaf\nCraigville, CT 44735',
},
    'key81826': 'value81817',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Pamela Bauer',
    'address': '7238 Acosta Junctions Apt. 986\nJeremyfort, GA 38223',
    'text': 'Risk establish difficult case professor develop believe. Long eye by participant similar budget quite. To energy prepare peace note magazine short. Strong project enough particularly.',
    'email': 'anthony40@example.org',
    'phone_number': '+1-217-325-9756',
    'array_int_dynamic': [
    78087,
],
    'array_varchar_dynamic': [
    'Tyler Nelson',
    'Dr. Frank Phillips',
    'Rachel Neal',
],
    'json': {
    'name': 'Sandra Prince',
    'address': '7377 Page Junction Apt. 764\nPort Mackenzieton, FM 74215',
},
    'key78800': 'value72560',
    'key10098': 'value48000',
    'key6349': 'value99740',
    'key17855': 'value94725',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Peggy Jones',
    'address': '1443 Diana Oval\nLake Laura, NY 44405',
    'text': 'Government analysis painting ago purpose bad exactly also. By decade can capital improve lead south political. Hour quickly defense research road.',
    'email': 'keith81@example.net',
    'phone_number': '347.915.0157x9043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Short',
    'Mary Jones',
    'Michael Levy',
    'Kristen Moore',
    'Brittney Wright DVM',
    'John Wolfe',
    'David Rojas',
    'Shannon Simmons',
    'Dr. Joan Schneider',
],
    'json': {
    'name': 'George Molina',
    'address': '611 Robert Port\nJordantown, VA 66877',
},
    'key75402': 'value74032',
    'key91931': 'value42831',
    'key68727': 'value63788',
    'key99069': 'value18217',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Amanda Jordan',
    'address': '0328 Blackburn Fall\nJohnside, MO 74475',
    'text': 'Level no large believe. Understand teach chair young me middle adult.\nSection share score sea. Hand public boy. Stop bed once girl west. Scene eight order industry able safe beat.',
    'email': 'ywoods@example.org',
    'phone_number': '001-735-662-4739x501',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Leonard',
    'Roger Gardner',
    'Joshua Smith',
    'Kimberly Anderson',
    'Lisa Barron',
    'Caitlyn Wells',
    'Emily Cox',
    'Mary Gonzalez',
],
    'json': {
    'name': 'Jeffrey King',
    'address': '836 Hodge Street Suite 387\nLisastad, WY 39727',
},
    'key83320': 'value26227',
    'key30901': 'value76409',
    'key68541': 'value9182',
    'key32404': 'value72486',
    'key38717': 'value23408',
    'key3767': 'value41712',
    'key63697': 'value20906',
    'key65107': 'value83102',
    'key85966': 'value66052',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Michael Walls',
    'address': '0614 Williams Pass\nPort Debraview, AZ 76335',
    'text': 'Second create physical wind church. Represent finally whether camera. Recently decide call language other last player.',
    'email': 'dennisaustin@example.org',
    'phone_number': '793.996.1251',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Smith',
    'Ashley Elliott',
    'Todd Moore',
    'Jessica Baker',
    'Jill Briggs',
    'John Vaughan',
    'Mark Vega',
    'Allison Miller',
    'Dwayne Schneider',
    'Teresa Rogers',
],
    'json': {
    'name': 'Diana Mendoza',
    'address': '5960 Kirk Dam\nJamesmouth, FM 53388',
},
    'key62527': 'value95889',
    'key44810': 'value58207',
    'key4726': 'value78780',
    'key5379': 'value16835',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'James Garcia',
    'address': '7465 Eric Lakes Apt. 415\nCaseyborough, TX 03645',
    'text': 'Either blood join six not matter. Raise traditional argue until.\nDecision move recently fly. Smile decade current face none mention. Win town anyone account.',
    'email': 'bchavez@example.org',
    'phone_number': '001-804-419-3028x2240',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sydney Stewart',
    'Christine Ramos',
    'Krista Davis',
    'Briana Wilson',
    'Tracy Kelley',
    'Timothy Lopez',
    'Mark Bowman',
    'Mr. Andrew Jones',
    'Dylan Swanson',
],
    'json': {
    'name': 'Sandra Simmons',
    'address': '48358 Caroline Street\nLake Valerie, FL 89504',
},
    'key22518': 'value2779',
    'key5826': 'value46973',
    'key19757': 'value86512',
    'key40643': 'value10172',
    'key95445': 'value18942',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Elizabeth Fisher',
    'address': '13245 Carpenter Knoll\nRioschester, NM 61934',
    'text': 'Give page sign country. Environmental seek focus leave meet financial throw. Far check area process successful style station.\nFirm much month the. Service debate wish box again.',
    'email': 'moraleschloe@example.org',
    'phone_number': '697-652-4472',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Luke Mckenzie',
],
    'json': {
    'name': 'Lori Campbell',
    'address': '563 Jerry Ridges\nNorth Charlesburgh, IA 52487',
},
    'key47473': 'value30123',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'James Roy',
    'address': '74626 Riley Key\nSandershaven, IL 59556',
    'text': 'Address eye walk letter whatever ten. Everything sit rock half pass training.\nIndividual decision inside evening fine. Agree forward rise police.',
    'email': 'chelseasanchez@example.net',
    'phone_number': '605.289.2973x46076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Baker',
    'Paul Smith',
    'Jenna Grant',
    'Joan Walker DVM',
    'Pamela Espinoza',
    'Kaitlyn Dunn',
    'Michael Ali',
    'Patricia Larson',
    'Catherine Rodriguez',
    'Craig Flores',
],
    'json': {
    'name': 'Robert Haynes',
    'address': '766 Crystal Square\nLindashire, WI 12965',
},
    'key65365': 'value5778',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Robert Morales',
    'address': '3944 Mariah Land\nNorth Georgehaven, MI 99822',
    'text': 'Current difference within economic enjoy claim under change. Outside card speech do recently relate crime. Executive paper build message significant every. Coach despite space mother.',
    'email': 'richardpowers@example.org',
    'phone_number': '001-484-970-8444x3160',
    'array_int_dynamic': [
    32796,
],
    'array_varchar_dynamic': [
    'Evan Allen',
    'Sara Hernandez',
    'Zachary Johnson',
],
    'json': {
    'name': 'Pamela Martin',
    'address': '9316 Mendez Stravenue Suite 692\nJoyceburgh, MH 29459',
},
    'key55372': 'value46558',
    'key61325': 'value14475',
    'key20736': 'value16409',
    'key85607': 'value43444',
    'key10825': 'value18382',
    'key40521': 'value11426',
    'key93008': 'value72194',
    'key4227': 'value12530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Lisa Rodriguez',
    'address': '8410 Paul Street\nNew Carolynview, CT 63228',
    'text': 'Fear finish at hope expert hour. City yeah economy cell debate vote charge. Attention middle room common market.\nLarge college although might. Nothing yes whatever exactly quickly what.',
    'email': 'cgutierrez@example.org',
    'phone_number': '7032396166',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Shawna Jordan DDS',
    'Victoria Andrade',
    'Marissa Brown',
    'George Parker',
    'Mitchell Simon',
    'Scott Russell',
    'Sandra Hernandez',
    'Rodney Warner',
    'Ray Michael PhD',
    'Donna Martin',
],
    'json': {
    'name': 'Amanda Hicks',
    'address': '88149 Flores Island Suite 055\nOrtizmouth, WV 52975',
},
    'key77337': 'value70719',
    'key27046': 'value7283',
    'key62433': 'value83529',
    'key85576': 'value21495',
    'key25328': 'value14779',
    'key60243': 'value38978',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Faith Maldonado',
    'address': '64316 Melissa Rest\nAllisonfurt, PW 70490',
    'text': 'Skill financial one especially dream she money.\nSay who capital rather account exist section. Myself image main. Traditional worry consider citizen big at.',
    'email': 'snyderlevi@example.com',
    'phone_number': '+1-455-212-1540x094',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Stacy Smith',
    'Omar Golden',
    'Jesus Nelson',
],
    'json': {
    'name': 'Carrie Robinson',
    'address': '9211 Kaitlyn Pike\nStevenshire, VT 88400',
},
    'key38703': 'value80051',
    'key1105': 'value90356',
    'key32277': 'value83556',
    'key17334': 'value71799',
    'key8928': 'value93555',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Charles Romero',
    'address': '26923 Fisher Path\nAngelastad, WI 82475',
    'text': 'Tree six close various north.\nSeries church success challenge. He act part where hold series. Rule until occur subject.',
    'email': 'rickynorman@example.net',
    'phone_number': '+1-993-508-3047x67705',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Schneider',
    'Sonya Martinez',
    'Damon Church',
],
    'json': {
    'name': 'Bethany Keller',
    'address': '281 Meadows Dam Suite 722\nThomasville, GA 99848',
},
    'key96694': 'value33319',
    'key62876': 'value31642',
    'key2061': 'value57921',
    'key97304': 'value52130',
    'key52939': 'value46688',
    'key50982': 'value50773',
    'key31411': 'value59617',
    'key31113': 'value65466',
    'key55591': 'value44535',
    'key51128': 'value35622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Cheryl Gonzalez',
    'address': 'USCGC Sanchez\nFPO AA 10101',
    'text': 'Until less late reduce. Half when drop technology it that.',
    'email': 'kaufmanjulian@example.net',
    'phone_number': '904-798-4801x129',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Hanson',
    'Christopher Garcia',
],
    'json': {
    'name': 'Maurice Nash',
    'address': '486 Black Extensions Suite 690\nSouth Melodybury, VI 13343',
},
    'key51308': 'value6446',
    'key59519': 'value78507',
    'key38165': 'value27963',
    'key22107': 'value2842',
    'key8346': 'value94652',
    'key38801': 'value1262',
    'key54794': 'value94614',
    'key98775': 'value67518',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Dana Jones',
    'address': '57289 Romero Island\nHalemouth, CA 84057',
    'text': 'Entire color country small. Meeting people ground live economic value lawyer. Ever source area some discussion drop.',
    'email': 'samantha42@example.net',
    'phone_number': '759-839-1959x5796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Justin Kerr',
    'Kevin Small',
    'Brett Cooke',
    'Tina Butler',
    'Kyle Oneill',
    'Taylor Hernandez',
    'Peter Shaw',
    'Bradley Pearson',
],
    'json': {
    'name': 'Michelle Taylor',
    'address': '8070 Williams Garden\nJessicabury, WI 82263',
},
    'key84996': 'value43385',
    'key24137': 'value84143',
    'key9039': 'value58416',
    'key39595': 'value76511',
    'key20374': 'value95097',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Ryan Smith',
    'address': 'Unit 5167 Box 1996\nDPO AE 01604',
    'text': 'Reason above short tree. Company why particularly summer defense.\nSpend leave miss cultural. Main value statement more serious. New provide more position.',
    'email': 'phillipsjose@example.net',
    'phone_number': '443-891-2057',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Carrie Wilson',
    'Mary Palmer',
    'Christopher Tate',
    'Jose Austin',
    'Frances Morgan',
    'Chad Richards',
    'Leah Peters',
    'Tanya Price',
],
    'json': {
    'name': 'Anthony Hebert',
    'address': '443 Davis Causeway\nMichaelfort, AS 59396',
},
    'key96585': 'value37007',
    'key12175': 'value85065',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Elizabeth Rodriguez',
    'address': '82850 Angel Crossroad Apt. 359\nEast Beverlyside, VA 51981',
    'text': 'Today identify seek. Manage grow activity commercial.\nTrouble PM law institution four road. Mouth political however society. Reason center water yard watch form.',
    'email': 'alex33@example.net',
    'phone_number': '865-963-7252x136',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christine Fletcher',
    'John Herrera',
    'Danielle Neal',
    'Kenneth Pugh',
    'Bailey Pitts',
    'Michael Mason',
    'Brandon Joyce',
    'Amy Tapia',
    'Michael Jones',
],
    'json': {
    'name': 'Dana Fox',
    'address': 'Unit 5969 Box 8511\nDPO AA 85632',
},
    'key95147': 'value96567',
    'key9908': 'value69996',
    'key11717': 'value25376',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Carmen Hernandez',
    'address': '79173 Daniel Isle\nJonesshire, AK 93551',
    'text': 'Accept card prove source dream. Role bill at piece recent dream.\nMajor moment write current walk up enjoy. Senior wall many eight ask modern read.',
    'email': 'tylermoran@example.org',
    'phone_number': '(696)312-9728x58455',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Lindsey',
    'Richard Rios',
    'Angela Rivera',
    'Sarah Kim',
    'Samantha Russell',
    'Matthew Gonzalez',
    'Logan Robbins',
],
    'json': {
    'name': 'Kristen Proctor',
    'address': 'Unit 2717 Box 8137\nDPO AE 97398',
},
    'key89070': 'value35850',
    'key93722': 'value6474',
    'key94978': 'value61416',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Lori Brown',
    'address': '87256 Walker Turnpike Apt. 424\nThompsonmouth, UT 01088',
    'text': 'Officer adult early throw expect physical upon. Cultural window key.\nShow tend employee meet. Can mouth place board somebody.\nRepublican sense key. Ten college continue property hear thought.',
    'email': 'bgrant@example.org',
    'phone_number': '+1-237-866-0277x3474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Theresa Ross',
    'Robert Case',
    'Alexandra Lawrence',
    'Cynthia Williams',
    'Audrey Wells',
],
    'json': {
    'name': 'Nicole Walker',
    'address': 'Unit 4518 Box 3374\nDPO AE 94506',
},
    'key90286': 'value77763',
    'key76609': 'value21175',
    'key64781': 'value92878',
    'key26219': 'value58463',
    'key62838': 'value21967',
    'key28059': 'value61655',
    'key77339': 'value11982',
    'key4250': 'value66450',
    'key68041': 'value71726',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Ronnie Collins',
    'address': '3513 Santiago Path Suite 064\nFullerton, VA 61314',
    'text': 'Government college evidence range when in shake. Person tend toward several charge. Computer apply anyone.\nDecision exactly car that green. Brother skin society get could behavior future.',
    'email': 'vhester@example.net',
    'phone_number': '430.595.0067x21438',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Glenn',
    'Christopher Hunter',
    'Andrea Figueroa',
    'Micheal Simmons',
    'James Banks',
    'Colleen Williams',
    'Ryan Ruiz',
    'Cristina Robinson',
    'Justin Anderson',
],
    'json': {
    'name': 'Mr. Robert Ritter',
    'address': 'Unit 8501 Box 5963\nDPO AP 53686',
},
    'key2265': 'value81940',
    'key96572': 'value79870',
    'key85582': 'value24452',
    'key22498': 'value94627',
    'key76775': 'value22932',
    'key69097': 'value83887',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Robert Stewart',
    'address': '2122 Wright Harbors\nManntown, NV 99705',
    'text': 'Success least school explain either ability. Imagine plan better history.\nSecond per around doctor everything. Even offer team phone college.\nFar yeah miss remain teacher court reality wait.',
    'email': 'robyntyler@example.net',
    'phone_number': '579.725.6591x18323',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Paul Peterson',
    'James Alexander',
],
    'json': {
    'name': 'Brian Coleman',
    'address': '300 Rose Road Suite 209\nSouth Christian, NJ 88744',
},
    'key43305': 'value4932',
    'key28704': 'value87594',
    'key87596': 'value85594',
    'key4185': 'value48395',
    'key49017': 'value58996',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Adam Dennis',
    'address': '459 Michael Park Suite 758\nPort Mark, NH 93580',
    'text': 'We sister major street charge movie bank. College meeting news.\nCitizen such small option PM. Toward many measure. Act event know its. Stuff book Mr yeah necessary Republican training seem.',
    'email': 'bflores@example.net',
    'phone_number': '220-453-8902x565',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Allison Kerr',
    'James Anderson',
    'Stephanie Montgomery',
    'Maureen Mendez',
    'Victoria Robinson',
    'Michael Thompson',
    'Tyler Villanueva',
    'David Moses',
],
    'json': {
    'name': 'Sherry Torres',
    'address': '60839 Taylor Ways\nBenjaminstad, MH 87012',
},
    'key76251': 'value62892',
    'key66150': 'value22222',
    'key99472': 'value5390',
    'key44923': 'value6595',
    'key47460': 'value49235',
    'key77055': 'value91460',
    'key53740': 'value31070',
    'key21409': 'value92994',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'David Brown',
    'address': '5932 Jane Trail\nYoungbury, ND 77430',
    'text': 'After drug sign knowledge where hot age.\nMove attention member husband. Able democratic late return identify head foot.\nFinancial message community customer church six process mouth.',
    'email': 'leestone@example.org',
    'phone_number': '001-832-722-2552x583',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Melanie Perez',
],
    'json': {
    'name': 'Laura Holmes',
    'address': '533 Cynthia Wall Apt. 433\nLake Victoriamouth, MS 09095',
},
    'key70798': 'value50872',
    'key50862': 'value41444',
    'key71412': 'value66754',
    'key46039': 'value31312',
    'key60699': 'value57283',
    'key84862': 'value18290',
    'key22720': 'value35126',
    'key39897': 'value81307',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'David Turner',
    'address': '37687 Kara Burg\nNew Zacharyton, DC 77405',
    'text': 'Successful mouth list. Quite he we production boy whole four. Old analysis sort follow success class big head.',
    'email': 'madisonrichmond@example.net',
    'phone_number': '946.493.3451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steven Davenport',
    'Nichole Long',
],
    'json': {
    'name': 'Nancy Yates',
    'address': '9395 Brock Turnpike\nSouth Jacob, NV 22422',
},
    'key98130': 'value2194',
    'key69895': 'value50111',
    'key59159': 'value61521',
    'key63741': 'value5572',
    'key44728': 'value92618',
    'key50686': 'value23094',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Richard Olson',
    'address': '2528 Lauren Flats\nEast Nicolemouth, NJ 61709',
    'text': 'Clearly do difference north. Very summer establish too role discover thank. Offer hope amount most professional energy ability.',
    'email': 'dorothyfinley@example.com',
    'phone_number': '(391)672-4349x9467',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jill Shields',
    'Jesus Lucas',
    'Steven Ellison',
    'Amanda Shannon',
    'Alicia Brown',
    'Amanda Olson',
    'Dr. Megan Hunter',
    'Lisa Peters',
],
    'json': {
    'name': 'Kevin Copeland',
    'address': '727 Jacobs Knoll\nWest Connie, GU 57464',
},
    'key14924': 'value22166',
    'key74342': 'value87929',
    'key99337': 'value21453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Brandon Smith',
    'address': '5372 Lacey Motorway Suite 163\nHernandezport, CO 77710',
    'text': 'Soldier agreement senior animal material old decision.\nFund quite land policy.',
    'email': 'heidicurtis@example.net',
    'phone_number': '667.554.3744',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Nichole Gentry',
    'Christina Bell',
    'Cindy Erickson',
    'Victor Richardson',
    'Danielle Macdonald',
],
    'json': {
    'name': 'Stephanie Lee',
    'address': '00959 Colin Fords\nSouth Cassidy, PR 26788',
},
    'key1713': 'value33279',
    'key30928': 'value38551',
    'key71378': 'value77796',
    'key16250': 'value93846',
    'key59724': 'value10839',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Crystal Knight',
    'address': '6806 Olivia Circles\nAmandabury, OH 33204',
    'text': 'Capital politics day thousand. Choose industry arm work alone one deep.\nMarriage suggest husband. Citizen drop better Mrs nothing agree believe. Call quality since.',
    'email': 'sklein@example.com',
    'phone_number': '001-460-267-2876x13870',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Perez',
    'Elizabeth Roberson',
    'Thomas Forbes',
    'Lisa Hutchinson',
    'Richard Lopez',
    'William Jackson',
    'John Thompson',
    'Katherine Garcia',
    'Gail Brown',
    'Stephanie Rowland',
],
    'json': {
    'name': 'Scott Cox',
    'address': 'PSC 8732, Box 8412\nAPO AA 72298',
},
    'key74172': 'value93536',
    'key71006': 'value86801',
    'key92078': 'value62398',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'John Brewer',
    'address': '44203 Allen Summit Suite 822\nBrooksbury, SD 17978',
    'text': 'Administration bank term interview control everything. Such should chance reality mouth. Rock push accept marriage imagine body capital city.\nMarriage school decade billion against morning yourself.',
    'email': 'fordjessica@example.com',
    'phone_number': '986-968-5844x2027',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Nelson',
    'Christina Henderson',
    'Krystal Lopez',
],
    'json': {
    'name': 'Jill Jones',
    'address': '816 Reed Mews\nOliviaport, MP 33568',
},
    'key32132': 'value68453',
    'key53797': 'value45865',
    'key13762': 'value38426',
    'key50801': 'value27750',
    'key11960': 'value51995',
    'key35787': 'value59104',
    'key97656': 'value90505',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Amy Davis',
    'address': '5584 Bowen Circle\nEast Kathrynhaven, NC 76805',
    'text': 'Church too reflect allow. Read religious goal address star reality war.\nGoal other far affect. Rest when magazine third newspaper hope. Body house recently back act head yard.',
    'email': 'ralph91@example.com',
    'phone_number': '+1-743-972-3342x921',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Heidi Lewis',
    'Michael Gutierrez',
    'Alexis Velazquez',
    'Debra Davis',
    'Christian Taylor',
],
    'json': {
    'name': 'Tiffany Espinoza',
    'address': '381 Arnold Parkway\nDeannabury, MH 16947',
},
    'key99464': 'value51117',
    'key24716': 'value62282',
    'key87391': 'value4708',
    'key85540': 'value40696',
    'key58814': 'value75613',
    'key90860': 'value99447',
    'key70764': 'value93262',
    'key5791': 'value39042',
    'key38375': 'value64441',
    'key53769': 'value6775',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Randall Martinez',
    'address': '472 Stephanie Passage Apt. 121\nLake Theresaton, HI 56542',
    'text': 'Nature ago space pass old. Individual poor hand weight indeed.\nBefore return since talk imagine likely. Final feeling staff relationship. Stay government add.',
    'email': 'chenvictoria@example.org',
    'phone_number': '388.682.8073',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kathy Williams',
    'Brenda Holt',
],
    'json': {
    'name': 'Timothy Wilson',
    'address': '27182 Graham Walks Suite 769\nHermantown, PW 16192',
},
    'key12180': 'value81946',
    'key81722': 'value79447',
    'key32649': 'value69111',
    'key88945': 'value36636',
    'key56387': 'value27601',
    'key47017': 'value36886',
    'key63652': 'value98114',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Kyle Keller',
    'address': 'USNV Hall\nFPO AA 03854',
    'text': 'Upon relationship head yard enter drop whether. Act message during director push start relationship measure.',
    'email': 'charles62@example.com',
    'phone_number': '001-694-224-2507x269',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Robert Baker',
],
    'json': {
    'name': 'Matthew Benton',
    'address': '1996 Wolfe Garden Apt. 340\nWest Kimberly, GA 45724',
},
    'key6486': 'value9747',
    'key69873': 'value18351',
    'key68353': 'value53386',
    'key28397': 'value34469',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Sarah Schwartz',
    'address': '5824 John Crescent\nAdrianville, SC 30199',
    'text': 'Rest teacher leave. Week something future campaign. Far feel reality character avoid certainly pressure. Water yet site age box support decade.',
    'email': 'mccanntodd@example.org',
    'phone_number': '623-871-8513x221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Melanie Anderson',
    'Heather Miller',
    'Keith Robinson',
    'Mark Carpenter',
    'Sheila Small',
    'Brandon Kelly',
],
    'json': {
    'name': 'Patricia Avila',
    'address': '3525 Collins Center\nNew Patricia, WY 60889',
},
    'key13316': 'value24949',
    'key93860': 'value83341',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Robert Chambers',
    'address': '6552 Jon Islands\nCohenhaven, OR 99084',
    'text': 'Although artist wrong back tree authority. Let fight true key. Itself memory hair executive glass instead official.\nGive new design none wonder trouble. Whom guess race seat green moment.',
    'email': 'sarah68@example.net',
    'phone_number': '(578)435-1382x273',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Berger',
    'Denise Shelton',
    'Kimberly Herrera',
    'Edward Thompson',
    'Carl Moore',
    'Nicholas Webster',
    'Lisa Frazier',
    'Melissa Vaughn',
],
    'json': {
    'name': 'Mr. Michael Gutierrez DDS',
    'address': '297 Owens Isle\nSouth Dale, MP 17864',
},
    'key28051': 'value54191',
    'key87069': 'value51445',
    'key60584': 'value4155',
    'key55649': 'value25702',
    'key73557': 'value18741',
    'key81665': 'value72166',
    'key13750': 'value38405',
    'key55382': 'value95168',
    'key57224': 'value33770',
    'key69100': 'value40380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Calvin Lopez II',
    'address': '1162 Peterson Stravenue Apt. 425\nGreenchester, MS 13481',
    'text': 'Name catch available executive important. Movie true all research physical development. Ball process board all understand form direction. Hotel against guy.',
    'email': 'jparsons@example.net',
    'phone_number': '380-911-2396x629',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Santos',
    'William Hudson',
    'Timothy Garcia',
    'Jonathan Rodriguez',
    'Rachel Allen',
    'Michael Lee',
],
    'json': {
    'name': 'Lisa Rocha',
    'address': '325 Elizabeth Groves\nEvanfort, FM 09158',
},
    'key49979': 'value68962',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Cassandra Myers',
    'address': '23717 Palmer Walks\nBryanbury, SC 54317',
    'text': 'Bank create sound positive. Dog event conference rich learn smile industry arm. Foot such senior long local.\nMake woman save show significant chance during.',
    'email': 'zholland@example.org',
    'phone_number': '+1-894-248-5550x6665',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Robinson',
    'Matthew Lee',
    'Mckenzie Brown',
    'Ethan Nelson',
    'Chad Warner',
],
    'json': {
    'name': 'George Murphy',
    'address': '779 Jensen Square Suite 629\nNew Chelseatown, DE 47843',
},
    'key54192': 'value15875',
    'key13682': 'value4833',
    'key38525': 'value20827',
    'key37040': 'value62290',
    'key5098': 'value93561',
    'key62079': 'value50327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Alvin Hebert',
    'address': '8864 Anthony Forge Apt. 411\nKendraland, VA 88520',
    'text': 'Game avoid instead second. Catch Mrs among building family discover door.\nTrue responsibility rock program Mrs rest. Adult number argue look after.\nQuite rate only loss. Start here set per social.',
    'email': 'wrightbrandon@example.net',
    'phone_number': '(334)269-2340x93149',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Bailey',
    'Tracy Woods',
    'Paula Allen',
    'Laura Becker',
    'Monica Miller',
    'Yolanda Castillo',
    'Jason Gibson',
    'Christopher Walsh',
],
    'json': {
    'name': 'Ronald Collier',
    'address': '8313 Klein Fort\nSabrinamouth, SC 45189',
},
    'key16197': 'value45627',
    'key20994': 'value8653',
    'key13823': 'value87424',
    'key69612': 'value62792',
    'key92979': 'value81155',
    'key84940': 'value65828',
    'key12177': 'value22285',
    'key92610': 'value67452',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Stacy Richards',
    'address': 'PSC 1023, Box 6297\nAPO AA 01282',
    'text': 'Science relate identify low beautiful right. Reality similar account civil nature.',
    'email': 'misty29@example.org',
    'phone_number': '(921)339-5162x0097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Garrett Black',
    'Patrick Knight',
    'Angela Brooks',
],
    'json': {
    'name': 'Brian Dickson',
    'address': '78242 Solis Centers Suite 728\nKarenmouth, GU 54594',
},
    'key45665': 'value91880',
    'key2296': 'value4095',
    'key23415': 'value83463',
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
    'RequestId': '16e1a269-62f1-11f0-86a7-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_13_625134efFzgqXt',
    'filter': 'uid in [1,2,3,4]',
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
    'RequestId': '1029119b-62f1-11f0-ac34-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_13_625134efFzgqXt',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752744805.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUidIn12341752744805Json()
    test.run_tests()
