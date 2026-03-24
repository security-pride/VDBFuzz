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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-2]_1752744167_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-2]_1752744167.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId12810021752744167Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-2]_1752744167.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-2]_1752744167.json"
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
    'RequestId': '99e56c05-62ef-11f0-a460-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_45_713937MVfOiivb',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
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
    'RequestId': '9a05b750-62ef-11f0-b6da-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_45_713937MVfOiivb',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Michelle Mcknight',
    'address': '803 Schwartz Mountains\nFloresfort, AK 85751',
    'text': 'Six recent method education gun. Live one low. Create note issue live memory course course.\nMan become beat learn big. Report true simple age off security model soon.',
    'email': 'tracy75@example.org',
    'phone_number': '203-236-0492x15259',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Connor Cook',
    'Jeanette Walker',
    'Renee Estrada',
    'Tanya Ortiz',
],
    'json': {
    'name': 'Justin Gordon',
    'address': '838 Hall Rapid Apt. 969\nJohnsontown, NV 56064',
},
    'key97492': 'value758',
    'key21776': 'value83803',
    'key1374': 'value699',
    'key56610': 'value97323',
    'key20820': 'value8435',
    'key28835': 'value9456',
    'key63219': 'value9510',
    'key97310': 'value24974',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Debra Mckee',
    'address': '2241 Wyatt Street\nRyanton, UT 84406',
    'text': 'Debate their type simply certainly new necessary. Arrive event yet safe candidate onto.\nShoulder current according into stock drop. High thing attorney information vote.',
    'email': 'stephanie51@example.net',
    'phone_number': '667-499-7957',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca White',
    'Sara Weaver',
    'Ryan Thomas',
    'Christopher Johnson',
],
    'json': {
    'name': 'Rhonda Rivera',
    'address': '047 Hernandez Plain Apt. 086\nPatriciafort, MP 15491',
},
    'key37029': 'value54721',
    'key55238': 'value59151',
    'key25994': 'value38883',
    'key10671': 'value64752',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jamie Fox',
    'address': '112 Coleman Dam\nChristinabury, PR 30364',
    'text': 'Policy some country employee than issue red. Fund where face break exist.\nEnvironment kind meet past for parent network option.\nFirm fish serious. Might forget green product weight break response.',
    'email': 'xlawson@example.net',
    'phone_number': '223-290-8575',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Lewis',
],
    'json': {
    'name': 'Christopher Brown',
    'address': '35894 Sanchez Orchard Suite 020\nNew Emily, MA 02057',
},
    'key70258': 'value51953',
    'key9332': 'value16222',
    'key13139': 'value3803',
    'key66193': 'value59741',
    'key19855': 'value29871',
    'key23715': 'value7978',
    'key22457': 'value42377',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Scott White',
    'address': '22646 Marks Keys Apt. 532\nStevensville, MO 06221',
    'text': 'Each seem sell share without personal. Simply important open past which career.\nRecent employee way several mind. Former carry during cover.',
    'email': 'pavila@example.com',
    'phone_number': '948-364-3499x9131',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Terri Patterson',
    'Brittany Mcknight',
    'Steven Oneal',
    'Renee Johnson',
    'Thomas Rivera',
    'Charles Buckley',
    'Pamela Griffith',
],
    'json': {
    'name': 'Amanda Jacobson',
    'address': '825 Rachel Turnpike\nNew Adrianland, RI 49811',
},
    'key86192': 'value37227',
    'key88458': 'value98529',
    'key97348': 'value90628',
    'key27305': 'value73889',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Matthew Mayo',
    'address': '49371 Nguyen Summit Apt. 056\nMatthewshaven, MD 51768',
    'text': 'Describe everything special give huge education. Difficult think color base indicate. Build agree around provide short eight know.\nNow get lose enter chance.',
    'email': 'samanthathomas@example.org',
    'phone_number': '460-491-1634x28165',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Donna Mckay',
    'Jessica Bryant',
],
    'json': {
    'name': 'David Jacobson',
    'address': '84735 Solis Underpass\nLanetown, TN 50920',
},
    'key91650': 'value35750',
    'key46890': 'value44059',
    'key97448': 'value33785',
    'key12238': 'value58102',
    'key58409': 'value30054',
    'key59405': 'value38586',
    'key19170': 'value27072',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Richard Huff',
    'address': '240 Lang Park\nEast Catherine, IL 45092',
    'text': 'Summer record ever occur. Dog heavy tree policy movement people professor.\nWhose day total cup four local which. Movie career prepare office agency try maybe.',
    'email': 'asingh@example.com',
    'phone_number': '+1-281-201-7273x78213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Burns',
    'Amy Cameron',
    'Mark Oliver',
    'Christopher Li',
    'Amy Cochran',
    'Michelle Chandler',
    'Steven Duncan',
    'Megan Andrews',
],
    'json': {
    'name': 'Karen Turner',
    'address': '974 Cook Walk Suite 769\nTeresaview, KS 28938',
},
    'key86558': 'value89365',
    'key58365': 'value21588',
    'key50787': 'value18591',
    'key51113': 'value79633',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Paula Stone',
    'address': '89766 Powell Cliff Apt. 227\nSouth Susan, MT 09886',
    'text': 'Factor grow both doctor return meet today. Participant section finish. Body most alone indeed. Idea also sit nature world someone tonight.\nSide left economy young education how land.',
    'email': 'deborahali@example.net',
    'phone_number': '+1-565-333-3072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steven Cooper',
    'Patrick Moore',
    'Nicole Spears',
    'Patricia Young',
    'Denise Garcia',
    'Sarah Wilcox',
    'Kayla Brennan',
    'David Gonzalez',
    'Vickie Peters',
],
    'json': {
    'name': 'Sally Barnes',
    'address': '6623 Henderson Avenue\nLivingstonshire, NE 21267',
},
    'key30819': 'value78627',
    'key48370': 'value52066',
    'key91161': 'value15229',
    'key53240': 'value36062',
    'key59715': 'value31097',
    'key2377': 'value41216',
    'key8496': 'value94016',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Steven Williams',
    'address': '0545 Evans Mountain\nEast Martin, WI 40776',
    'text': 'Lay tonight focus contain key exactly. Course ball school large.\nMany no before value compare loss which fact. Officer foot western though half anyone. Include kitchen low or voice north health.',
    'email': 'wendybell@example.com',
    'phone_number': '700-578-9370x96899',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Craig',
    'Jacqueline Ramirez',
    'Jeremy Gonzalez',
    'Regina Johnson',
    'Cory Rodriguez',
    'Melissa York',
],
    'json': {
    'name': 'Olivia Brown',
    'address': '332 Brenda Circles\nSouth Pamela, NM 93084',
},
    'key18785': 'value83862',
    'key53378': 'value56983',
    'key61633': 'value58532',
    'key22589': 'value76452',
    'key10838': 'value39632',
    'key82492': 'value57097',
    'key88990': 'value32727',
    'key43818': 'value43964',
    'key23682': 'value8528',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Michael Nielsen',
    'address': '48705 Donna Turnpike\nWest Markberg, AR 45807',
    'text': 'Medical bad charge should herself election individual nature. Language contain customer impact.',
    'email': 'brittanysmith@example.net',
    'phone_number': '001-423-692-5408x655',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Fernandez',
],
    'json': {
    'name': 'Nicholas Barnes',
    'address': '1866 Theresa Summit Suite 636\nEast Kevinview, ND 18888',
},
    'key27540': 'value26988',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Molly Meyers',
    'address': '566 Michael Unions Apt. 936\nTriciashire, SD 83949',
    'text': 'Partner else adult sense yet tell. Pay member only. Central everyone outside base mouth according individual defense.',
    'email': 'millerdarlene@example.net',
    'phone_number': '723.777.6595',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Ana Lopez DDS',
    'Patrick Martin',
    'Susan Chapman',
    'Glenda Johnson',
    'Kristin Bean',
],
    'json': {
    'name': 'Debbie Wright',
    'address': '416 Edward Crest Suite 416\nRollinsshire, NY 04024',
},
    'key62724': 'value7401',
    'key42864': 'value47087',
    'key45339': 'value78462',
    'key55173': 'value27530',
    'key70118': 'value89433',
    'key72414': 'value87008',
    'key16851': 'value3016',
    'key15933': 'value21373',
    'key10721': 'value17152',
    'key85065': 'value66551',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Todd Lee',
    'address': '050 Brady Burg Suite 191\nNorth Michellemouth, GU 76455',
    'text': 'Girl reach before full government work. Live population hold address community. Management anything understand smile half pressure woman light.',
    'email': 'danielespinoza@example.org',
    'phone_number': '961-236-6295x60816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sara Butler',
    'Ronald Thomas',
    'Richard Harris',
    'Karen Hernandez',
    'Victoria Ball',
    'Jack Gonzalez',
    'Ryan Fisher',
    'Anthony Brown',
    'Peter Cline',
],
    'json': {
    'name': 'Austin Baker',
    'address': '9266 Taylor Alley\nHayesburgh, MS 51244',
},
    'key14528': 'value7496',
    'key75399': 'value51662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Robert Martinez',
    'address': '45943 Rodriguez River Suite 533\nGrimesstad, OR 74668',
    'text': 'Right one though detail season under policy. Expect million rather while. Weight nothing skill.\nPass population foreign than seek recognize threat. Hand and scientist myself by affect.',
    'email': 'dennis05@example.net',
    'phone_number': '001-946-281-4788x000',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Laura Lewis',
],
    'json': {
    'name': 'Jenna Banks',
    'address': '826 Miles Turnpike\nRamosmouth, OK 12756',
},
    'key70344': 'value63540',
    'key23422': 'value76447',
    'key30625': 'value19629',
    'key61814': 'value30874',
    'key64230': 'value27578',
    'key62270': 'value53810',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Charles Myers',
    'address': '514 Roy Harbor Apt. 802\nPort Sheila, FM 04738',
    'text': 'Interesting girl resource leader. On order mind meeting support character. Whole occur space they group need only.',
    'email': 'jamestaylor@example.com',
    'phone_number': '+1-213-940-8034x9004',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Debra Sanders',
    'Tina Williams',
    'Sandra Gray',
],
    'json': {
    'name': 'Thomas Torres',
    'address': '6337 Davis Walks\nSouth Stephen, UT 28723',
},
    'key84345': 'value90758',
    'key72261': 'value46044',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Hector Gonzalez',
    'address': 'PSC 1326, Box 5219\nAPO AA 24787',
    'text': 'Cultural another main tonight perform year. Necessary although quite appear military develop interesting full. Sister strategy rest father science specific. Else officer management late.',
    'email': 'amynewman@example.org',
    'phone_number': '(873)201-8473x25816',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alex Black',
    'Dr. Ellen Martinez',
    'Yolanda Pena',
    'James Simmons',
    'Jeremy Krueger',
    'Brenda Hansen',
],
    'json': {
    'name': 'James Stevens',
    'address': '39649 Matthew Via Suite 513\nWest Tammie, MI 57307',
},
    'key65841': 'value40459',
    'key70540': 'value65813',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Thomas Zuniga',
    'address': '4226 Graham Squares Apt. 570\nCharlesburgh, AR 34614',
    'text': 'Scientist federal work board yeah top statement. Effort today add scientist. Computer certain party talk situation.',
    'email': 'chloe90@example.net',
    'phone_number': '9754185004',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Griffin',
    'Jason Burton',
],
    'json': {
    'name': 'Christopher Shelton',
    'address': '9613 Davis Brook Suite 176\nPeterstown, WY 50734',
},
    'key91259': 'value37325',
    'key98515': 'value15031',
    'key95344': 'value86254',
    'key8429': 'value32991',
    'key8065': 'value58988',
    'key84025': 'value98974',
    'key26913': 'value63232',
    'key667': 'value57119',
    'key15405': 'value55814',
    'key41913': 'value345',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Alexandra Silva',
    'address': '4853 Harrington Drives\nVictoriachester, MI 95803',
    'text': 'Treatment what fund necessary. Public leg ball pretty other.\nStand pretty stop five tell phone our. Yard particular pretty top back.',
    'email': 'othompson@example.com',
    'phone_number': '001-900-663-4242x0972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Randy Avila',
    'Danielle Sheppard',
    'Christina Walker',
],
    'json': {
    'name': 'David Morris',
    'address': '063 Davidson Lake\nEast Bethanyburgh, WV 32170',
},
    'key14502': 'value92123',
    'key89336': 'value91846',
    'key94035': 'value97338',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Mark Harris',
    'address': '100 Hayes Valleys Apt. 617\nBergerborough, SD 16316',
    'text': 'Nearly former recognize explain pull another. Attack organization training little recent eat.',
    'email': 'mariawhite@example.org',
    'phone_number': '372.968.1760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tina Sandoval',
    'Mrs. Patricia Rivera',
    'Justin Holland',
    'Nicole Middleton',
    'Robert Mcknight',
    'Lori Robinson',
    'Kristin Crawford',
    'Jessica Le',
],
    'json': {
    'name': 'Jeffrey Meyer',
    'address': '23534 Cole Key\nNew Helenchester, MT 96918',
},
    'key97234': 'value89034',
    'key74418': 'value3332',
    'key96515': 'value55026',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Shannon Johnson',
    'address': '957 Holland Extensions\nShellyberg, AS 75214',
    'text': 'Reduce run theory adult. Move ready woman. Possible way last simple may example.\nGive test me wonder. Here dog forward.\nDifference play this over model help break. Long enjoy often office kid.',
    'email': 'snyderhenry@example.org',
    'phone_number': '+1-622-525-1543x92880',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Johnston',
    'Tracy Dixon',
    'Glen Mckee',
    'Rachel Lynch',
    'Andrew Jarvis',
    'Elizabeth Smith',
    'Stephanie Moore',
],
    'json': {
    'name': 'Jennifer Brown',
    'address': '21162 Moon Crest Apt. 866\nNew Hannah, TX 37692',
},
    'key94800': 'value97825',
    'key5666': 'value51093',
    'key73484': 'value21969',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Juan White',
    'address': '71898 Lauren Loop\nEast Melissatown, FM 71960',
    'text': 'Lawyer major discussion door loss stock sing. Wall benefit call fly doctor ahead.\nMaterial commercial side catch. Figure source avoid late.',
    'email': 'brownethan@example.com',
    'phone_number': '793-900-3178x36882',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Angela Woods DVM',
    'Abigail Carson',
    'Erica Fields',
    'Laura Morris',
],
    'json': {
    'name': 'Daniel Gonzalez',
    'address': '5465 Soto Lakes\nNorth Michelle, DC 33873',
},
    'key79846': 'value39280',
    'key20166': 'value26411',
    'key59892': 'value39353',
    'key86209': 'value77515',
    'key47310': 'value14195',
    'key95990': 'value22249',
    'key1102': 'value38980',
    'key20889': 'value58649',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Lisa Obrien',
    'address': '2401 Acosta Crescent Apt. 024\nLake Alexandra, AK 82924',
    'text': 'Allow foot me possible anything face break. If offer entire than you age environment situation. Indicate instead race.',
    'email': 'hudsonlaura@example.org',
    'phone_number': '(655)455-5242',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Rodriguez',
    'Martin Osborne',
    'Kenneth Stewart',
],
    'json': {
    'name': 'Kristi Velasquez',
    'address': 'Unit 1463 Box 9256\nDPO AE 99425',
},
    'key12151': 'value20824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Steven Wright',
    'address': '2640 George Inlet Apt. 969\nKellyland, OR 93833',
    'text': 'Plant meeting use. Town group institution kid difference. Great arm meeting chair play whole sell.\nOfficer hard according. Value crime probably. Again about once protect computer point.',
    'email': 'gboyd@example.com',
    'phone_number': '(586)919-3584x99856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Doyle',
    'Theresa Smith',
    'Tracy Macdonald',
    'Wayne Johnson',
    'Sarah Gonzalez',
    'John Davis',
],
    'json': {
    'name': 'Sarah Reed',
    'address': '784 Sherry Parkways\nBlevinsborough, UT 34498',
},
    'key45468': 'value64161',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Tamara Cox',
    'address': '493 Blair Locks Apt. 483\nVictoriaberg, IL 24189',
    'text': 'But court worker share pretty piece leg. Response house seat.\nBill own different recognize. Cause discussion lot condition moment. Six strategy management language seat road.',
    'email': 'stephaniepeterson@example.com',
    'phone_number': '382-793-2066',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Holmes',
    'Mia James',
    'Larry Jacobs',
],
    'json': {
    'name': 'Katie Miller',
    'address': '2834 Larsen Ridge\nElizabethfurt, IL 59130',
},
    'key3294': 'value70514',
    'key85626': 'value94551',
    'key25732': 'value76871',
    'key6769': 'value85259',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Kayla Gray',
    'address': '136 Kevin Islands Apt. 963\nLopezside, IA 26361',
    'text': 'Method simply visit since present.\nDirection wait couple least best. Without police strategy former yard nearly.',
    'email': 'eross@example.com',
    'phone_number': '001-678-274-5913x65210',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Leon Williams',
    'Wendy Allen',
    'Diana Lester',
    'Mary Mcdonald',
    'Mark Cook',
    'Rebecca Kane',
    'Adam Mcmahon',
    'Henry Watts',
],
    'json': {
    'name': 'Jon Smith',
    'address': '23891 Steven Parkway\nPamelaport, AL 35696',
},
    'key53690': 'value41654',
    'key34400': 'value5981',
    'key70502': 'value61814',
    'key252': 'value84431',
    'key32698': 'value58263',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jacqueline Howard',
    'address': '4685 Elaine Corners Suite 142\nWoodardport, CO 73326',
    'text': 'With nation pass board yourself. Ahead born treat.\nTeacher miss black growth knowledge indeed. Responsibility majority wife half.',
    'email': 'anita26@example.org',
    'phone_number': '001-836-827-5578x46835',
    'array_int_dynamic': [
    85407,
],
    'array_varchar_dynamic': [
    'Beth Morris',
    'Tammie Taylor',
    'Edward Lewis',
],
    'json': {
    'name': 'Barry Kelly',
    'address': '22644 Bauer Falls\nWilliamshaven, NC 65699',
},
    'key13401': 'value94518',
    'key51801': 'value73186',
    'key51': 'value53134',
    'key46752': 'value11966',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Mary Peters',
    'address': '64286 Gina Pine\nKevinberg, DE 85724',
    'text': 'Physical identify chance sing low kind. List up life structure people individual.',
    'email': 'richardscheryl@example.org',
    'phone_number': '772.615.1897',
    'array_int_dynamic': [
    63161,
],
    'array_varchar_dynamic': [
    'Samantha Burgess',
    'Richard White',
    'Megan Martin',
    'David Patterson',
],
    'json': {
    'name': 'Stephen Roberts',
    'address': '087 Sherman Plaza\nEast Matthewhaven, NE 10885',
},
    'key73152': 'value25455',
    'key73106': 'value91886',
    'key56251': 'value53066',
    'key98074': 'value68913',
    'key38449': 'value92478',
    'key86889': 'value58502',
    'key70031': 'value15322',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Kenneth Cortez',
    'address': '6275 Tiffany Unions\nMccoyview, MN 23336',
    'text': 'Soon shake score picture tell arm. Crime develop city huge front.\nCivil together after economy assume according. Choose he start happy full.',
    'email': 'christopheraguilar@example.org',
    'phone_number': '001-732-603-2974x54938',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Maria Thompson',
],
    'json': {
    'name': 'Amber Owens',
    'address': '9063 Johnson Forks Suite 185\nBondhaven, TN 94781',
},
    'key66075': 'value39326',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Garrett Clark',
    'address': '16766 Jeffrey Courts\nBrownshire, MS 35961',
    'text': 'Same everybody pull. Participant provide head change themselves. Former back person probably. Effort international yet voice so wind.\nAuthority sometimes health forward.',
    'email': 'mullinsdavid@example.net',
    'phone_number': '+1-288-221-3237x477',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Keith Randall',
],
    'json': {
    'name': 'Logan Rodriguez',
    'address': '0792 Clark Radial Apt. 859\nAndrefurt, AR 09123',
},
    'key96752': 'value26089',
    'key11672': 'value32153',
    'key37330': 'value95053',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Christine Hinton',
    'address': '22750 Sherri Keys\nBriannafort, RI 87036',
    'text': 'Information south smile within turn yes offer. Plant production response.\nThose song reflect make ready admit interesting sound. Section thought attorney road.',
    'email': 'kathrynnicholson@example.net',
    'phone_number': '001-901-349-1111x814',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lawrence Bell DVM',
    'Andrea Fernandez',
    'Cheyenne Fisher',
    'Adam Kim',
    'Kim Price',
    'Michael Diaz',
    'Donna Miller',
    'Amanda Phillips',
],
    'json': {
    'name': 'Emma Faulkner',
    'address': '32553 Cindy Rue\nHickschester, PR 09134',
},
    'key81053': 'value89082',
    'key26825': 'value68501',
    'key65374': 'value54950',
    'key51117': 'value57734',
    'key56562': 'value77737',
    'key72878': 'value30088',
    'key96803': 'value90354',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Angelica Hernandez',
    'address': 'Unit 6330 Box 0098\nDPO AP 97079',
    'text': 'Bank society between focus Republican sell type left. Husband TV out decide successful allow return.',
    'email': 'foconnor@example.net',
    'phone_number': '(996)550-5467x244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Charles Rogers',
    'Timothy Rodriguez',
    'Eric Contreras',
    'Patrick Sims',
    'Joanna Jenkins',
],
    'json': {
    'name': 'Melissa Brown',
    'address': 'PSC 8836, Box 3147\nAPO AA 46005',
},
    'key89638': 'value32442',
    'key70739': 'value62140',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Kyle Oneill',
    'address': '000 Stewart Ford\nRoberttown, PR 56214',
    'text': 'Particular order PM can. Deal meet follow need describe body.\nIncluding woman since enter inside. And set great protect feeling. Up method occur true man wall.',
    'email': 'fosterkristine@example.net',
    'phone_number': '549.614.6655x7433',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sheila Cardenas',
    'Kelly Mooney',
    'Alex Gray',
    'Kevin Lopez',
    'Shawn Martin',
    'Ryan Barker',
    'Kevin Davis',
    'Christopher Barajas DVM',
],
    'json': {
    'name': 'Robert Jones',
    'address': 'Unit 9319 Box 6158\nDPO AA 47600',
},
    'key87504': 'value51794',
    'key49984': 'value87312',
    'key71515': 'value76442',
    'key75375': 'value88273',
    'key42758': 'value26375',
    'key3367': 'value58186',
    'key25158': 'value52266',
    'key43406': 'value19590',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'George Gray',
    'address': '08739 Montoya Stream\nManningstad, TN 03647',
    'text': 'Save same focus interest strategy rock when morning. Voice player director lead try put south.\nHalf conference ground wall green information move. Cultural write within assume today series economy.',
    'email': 'ahines@example.org',
    'phone_number': '(762)903-6335x72780',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Penny Lyons',
    'Kristin Daniel',
    'Samuel Lee',
    'Michael Ruiz',
    'Alison Bullock',
    'John Bridges',
    'Mary Baxter',
    'Holly Anderson',
],
    'json': {
    'name': 'Jennifer Taylor',
    'address': '984 Austin Canyon\nRobertshire, CT 74011',
},
    'key35896': 'value1431',
    'key89809': 'value83166',
    'key20565': 'value77824',
    'key48913': 'value11624',
    'key52054': 'value57978',
    'key41198': 'value5492',
    'key70417': 'value82567',
    'key43479': 'value83933',
    'key49192': 'value33857',
    'key2270': 'value67811',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Bruce Ortiz',
    'address': '9745 Wagner Lock\nSouth Alexanderfurt, NC 27492',
    'text': 'Activity allow community even visit prepare. Best impact hard rather offer technology.\nMethod likely lead American research usually describe. Drive amount travel indicate. Mouth each our project.',
    'email': 'lanelatoya@example.com',
    'phone_number': '716-633-0178x84610',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Gilbert',
    'Lynn Johnson',
    'Jennifer Dixon',
    'Sharon Shaffer',
    'Allen Lopez',
    'Anita King',
    'Randy Vargas',
],
    'json': {
    'name': 'Monica Owens',
    'address': '3804 Martinez Junction Suite 082\nNorth Jeremy, WA 48940',
},
    'key69839': 'value67097',
    'key21650': 'value72256',
    'key84069': 'value48359',
    'key21203': 'value43191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Brent Hall',
    'address': '499 Gonzalez Road Apt. 234\nNew Joseph, MO 65696',
    'text': 'Figure lose finish week leader kind. Too pick computer open race suddenly shake. Serve should though anything us brother arm add. High recognize free though send.',
    'email': 'ehartman@example.com',
    'phone_number': '258.236.4761',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Warren Payne',
    'Barbara Morgan',
    'Judy Wiggins',
    'Bill Simmons',
],
    'json': {
    'name': 'Michael Ponce',
    'address': '61070 Ashley Grove Apt. 675\nPort April, IA 85691',
},
    'key56725': 'value91714',
    'key67463': 'value28863',
    'key4381': 'value87496',
    'key12497': 'value31932',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Derek Brooks',
    'address': '792 Gonzalez Camp\nPort Austin, NM 65409',
    'text': 'Course Democrat first coach recently produce. Door democratic thus art discuss market talk.\nStage every fill once chance. Him bag my time.',
    'email': 'joseph14@example.com',
    'phone_number': '(228)296-2674',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Fernandez',
    'Kylie Franklin',
    'Donald Patel',
    'Heather Hall',
    'Matthew Mayo',
    'Blake Marshall',
    'Keith Rodriguez',
    'Catherine Marsh',
],
    'json': {
    'name': 'Nancy Clark',
    'address': '1494 Ricky Trail\nSouth Danieltown, NM 80819',
},
    'key83697': 'value33286',
    'key84362': 'value72963',
    'key19317': 'value78199',
    'key63495': 'value531',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'James Buchanan',
    'address': '1622 James Estate\nPort Caleb, OH 77607',
    'text': 'Early political fill bar newspaper still. No there reality life phone agree treatment.\nSurface this begin window anyone claim close. Career rate stuff world.',
    'email': 'montoyacory@example.com',
    'phone_number': '228-921-1447',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christine Jensen',
    'Lynn Williams',
    'Danielle Singh',
    'Ricky Moore',
    'Nathan Bartlett',
    'Tracy Myers',
    'Dean Mcintosh MD',
    'Alicia White',
],
    'json': {
    'name': 'Kelly Johnson',
    'address': '705 Leonard Village\nEast Mark, MO 46747',
},
    'key63085': 'value47409',
    'key52263': 'value74547',
    'key34856': 'value54911',
    'key73843': 'value28007',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Samuel Mckinney',
    'address': '385 Scott Valleys Suite 353\nCoffeybury, NY 62574',
    'text': 'A effect no increase suddenly administration. Church fast owner sound action art key. Travel present detail five course.\nEven listen participant tell. Local to drive offer finally stock.',
    'email': 'santostiffany@example.com',
    'phone_number': '001-361-319-9159x416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Barnes',
    'Donna Tapia',
    'Nathan Contreras',
    'Michelle Callahan',
    'Jennifer Bell',
    'Daniel Ward',
    'Frank White',
    'William Schneider',
    'Heather Cole',
    'Emily Moore',
],
    'json': {
    'name': 'Anna Turner',
    'address': '5892 Megan Lights\nNew Jennifer, ME 38575',
},
    'key30811': 'value87142',
    'key32473': 'value90231',
    'key68135': 'value61252',
    'key54891': 'value57238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Dr. Linda Jordan',
    'address': '89754 Carlson Springs\nWilliamsberg, NH 07101',
    'text': 'Religious building past rather side property I. Almost action environmental edge argue production. Final environment plan.',
    'email': 'deborah53@example.com',
    'phone_number': '5194385847',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Smith',
    'Tyler Moore',
    'Michael Hernandez',
],
    'json': {
    'name': 'Tammy Scott',
    'address': '0423 Diana Burg\nLake Michaelland, IL 86830',
},
    'key22332': 'value26820',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Cassandra Jackson',
    'address': '2432 Alexander Fork Apt. 358\nLake Phillip, IA 05282',
    'text': 'Rule give actually shoulder its no character. Accept beat stand network major say main.\nFriend air blood fly me.',
    'email': 'suzanneanthony@example.net',
    'phone_number': '339.744.8833',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Charles Hall',
    'Elizabeth Jenkins',
],
    'json': {
    'name': 'Manuel Miller',
    'address': '1516 Thornton Rest\nWest Shannonberg, GU 40434',
},
    'key64723': 'value76183',
    'key7046': 'value31893',
    'key54824': 'value62546',
    'key37646': 'value69611',
    'key2512': 'value41869',
    'key83118': 'value77106',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Chad Matthews',
    'address': '20696 Samuel Camp\nPort Roberthaven, PA 93387',
    'text': 'Paper begin plan lawyer. Just serious both become century left mission. Character let manager second woman.\nAt upon accept. Choice region bar loss it truth field.',
    'email': 'erik82@example.net',
    'phone_number': '001-289-933-6027x60548',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joe David',
    'Michael Taylor',
    'David Sloan',
    'Tony Parker',
],
    'json': {
    'name': 'Stacy Patton',
    'address': '075 Michelle Junctions\nYvonnefurt, VI 61670',
},
    'key54639': 'value7812',
    'key59940': 'value32750',
    'key83929': 'value91063',
    'key60810': 'value56935',
    'key4946': 'value33070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Michael Thornton',
    'address': '2786 Ruiz Green Suite 141\nThomasport, SD 47556',
    'text': 'Government ball teach break thus summer. Rise note under deal week despite.\nFollow through high. Go miss people four response provide tell while. Ask computer leave cell decision be man item.',
    'email': 'briggskim@example.org',
    'phone_number': '(990)761-7831',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Peters',
    'Sabrina Wells',
    'Sylvia George',
    'Mark Blankenship',
],
    'json': {
    'name': 'Vincent Petersen',
    'address': '43027 Garcia Roads Suite 295\nSouth Savannah, WI 97659',
},
    'key86353': 'value68888',
    'key58551': 'value49565',
    'key11561': 'value40049',
    'key73611': 'value15696',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Marilyn Armstrong',
    'address': '74374 Olson Extensions\nBrendaland, DC 01058',
    'text': 'Institution staff the yourself speak. Reflect crime four close focus perhaps action. Success mention likely.',
    'email': 'sanchezthomas@example.com',
    'phone_number': '835.759.5574x67152',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Murray',
    'Richard Murphy',
    'Kimberly Gardner',
    'Erica Lyons',
    'Stephen Fleming',
    'Cory Franklin',
    'Emily Martinez',
    'Brooke Hoover',
],
    'json': {
    'name': 'Melanie Garcia',
    'address': '92008 Jesse Throughway Apt. 317\nKellyfurt, FL 76712',
},
    'key44736': 'value37106',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Kevin Brown',
    'address': 'USCGC Bailey\nFPO AP 27497',
    'text': 'Born each news customer low watch unit. Name apply organization without stock with nor. Democrat hand rule remember whole public.\nProve argue health music authority special something.',
    'email': 'donna40@example.com',
    'phone_number': '(662)747-2281x54926',
    'array_int_dynamic': [
    62012,
],
    'array_varchar_dynamic': [
    'Jose Pierce',
],
    'json': {
    'name': 'Brian Shaffer',
    'address': '72390 Brittney Mews Suite 881\nVincentmouth, IN 10251',
},
    'key10422': 'value93161',
    'key33298': 'value91164',
    'key55073': 'value92837',
    'key21540': 'value50203',
    'key26261': 'value91526',
    'key46410': 'value16722',
    'key66030': 'value52517',
    'key83001': 'value14276',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Gregory Murray',
    'address': '977 Patricia Course\nAmymouth, MO 41727',
    'text': 'Our to true interest they. Tonight ahead draw allow understand their important.\nOnce campaign full a assume result. Care see me address role raise. Without few show again behind discussion play.',
    'email': 'bflynn@example.org',
    'phone_number': '+1-796-995-1963x25444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Paige Floyd',
    'Kelly Smith',
    'Marcus Strickland',
    'John Rogers',
    'Jenny Tran',
    'Robert Torres',
    'Dustin Wiley',
    'Nancy Owens',
],
    'json': {
    'name': 'Kathy Brown',
    'address': '3197 Katrina Mountain\nEast William, WV 82700',
},
    'key98884': 'value85159',
    'key50280': 'value52467',
    'key31105': 'value95451',
    'key53279': 'value24333',
    'key3383': 'value52275',
    'key70939': 'value98288',
    'key79716': 'value96751',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Christopher Chase',
    'address': '8311 Carly Ville Suite 733\nCrosbyhaven, AZ 48528',
    'text': 'Year camera provide yourself town gas recognize. Stage space know.\nPrevent easy prove whatever. Especially rock understand know rate evening rate.',
    'email': 'abrowning@example.org',
    'phone_number': '+1-897-710-1249x75729',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brianna Hopkins',
    'Laura Horn',
    'Joel Jackson',
    'Michael Boone',
    'Tina Brown',
    'Heather Mann',
    'Frank Sullivan',
    'Herbert Carlson',
    'Nathaniel Robbins',
],
    'json': {
    'name': 'Sara Smith',
    'address': '9685 Hernandez Garden Suite 089\nWest Jacob, LA 82067',
},
    'key19996': 'value52589',
    'key74272': 'value96885',
    'key88082': 'value61668',
    'key26022': 'value16462',
    'key6021': 'value17626',
    'key67581': 'value42813',
    'key66184': 'value42890',
    'key91961': 'value74889',
    'key7427': 'value64646',
    'key73859': 'value97643',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Gregory Guerra',
    'address': '133 Collier Light\nLopeztown, LA 40906',
    'text': 'Against character three current store director check. Bad budget morning religious whose even. Color too bring high day music because according.',
    'email': 'james08@example.com',
    'phone_number': '443-930-8778x19584',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Duane Marsh',
    'Tina Juarez',
    'Nancy Callahan',
    'Laura Ferguson',
    'Kyle Griffin',
    'Dawn Diaz',
    'Ashley Wilson',
    'Sharon Lee',
],
    'json': {
    'name': 'Christopher Torres',
    'address': '5721 Lester Square Suite 027\nLake Rebeccaview, NE 05378',
},
    'key49915': 'value54035',
    'key84343': 'value69042',
    'key49403': 'value91599',
    'key62907': 'value79332',
    'key61336': 'value16070',
    'key74688': 'value77880',
    'key3817': 'value98457',
    'key70330': 'value78823',
    'key67422': 'value46307',
    'key363': 'value4053',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Laura Shelton',
    'address': '011 Porter Mill Suite 009\nSouth Wendy, MO 99358',
    'text': 'Wear continue majority in. Partner early bit itself.\nSo hand boy open health time decide. Choose single article.\nThem force improve low collection shoulder. People cold area we worker rate hope.',
    'email': 'kelleyrenee@example.com',
    'phone_number': '7234110653',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kelsey Rogers',
    'James Hutchinson',
    'Jennifer Lewis',
    'Beverly Smith',
    'Kelsey Fleming',
    'Margaret Thompson',
    'Lisa Perez',
    'Rebecca Edwards',
    'Jasmin Johnson',
    'Michael Morse',
],
    'json': {
    'name': 'Claudia Walters',
    'address': '302 Martin Point\nLake Jacquelineborough, ME 41553',
},
    'key65913': 'value25533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Kerry Harris',
    'address': '67133 Jesse Groves Apt. 905\nPort Trevor, KY 70826',
    'text': 'Heavy skill year together effect road. Dream first act its financial arrive customer arrive.\nEast like financial mouth each. Phone language which.',
    'email': 'csellers@example.com',
    'phone_number': '+1-830-466-0170x413',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Edward Conway',
    'Christopher Gordon',
    'Carol Walter',
    'Tabitha French',
    'Alexis Bradley',
    'Raven Smith',
    'Christopher Hernandez',
],
    'json': {
    'name': 'Joshua Evans',
    'address': '54658 Moss Overpass Suite 233\nEast Matthewshire, IA 81175',
},
    'key11807': 'value6350',
    'key53737': 'value91729',
    'key98172': 'value60487',
    'key21853': 'value92560',
    'key5093': 'value14421',
    'key87024': 'value39035',
    'key26653': 'value70610',
    'key43383': 'value89861',
    'key74272': 'value47467',
    'key69617': 'value17774',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Melvin Miller',
    'address': '537 Mitchell Bypass\nWest Stacey, TN 31303',
    'text': 'Friend plant these through member item. Decade whose somebody sea magazine.',
    'email': 'salazareric@example.com',
    'phone_number': '001-273-543-8253x5062',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Regina Mack',
],
    'json': {
    'name': 'Vicki Whitaker',
    'address': '1085 Maria Center\nWest Nicholas, FM 84228',
},
    'key85389': 'value83152',
    'key42274': 'value82603',
    'key32372': 'value49901',
    'key9417': 'value95389',
    'key74984': 'value1587',
    'key63433': 'value31035',
    'key23374': 'value4097',
    'key9122': 'value20292',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'James Herrera',
    'address': '930 Castillo Road Apt. 436\nPetersentown, VI 49268',
    'text': 'Down have eye fear yeah task when. Current cut share place maybe leader energy.',
    'email': 'larry67@example.com',
    'phone_number': '001-644-411-0321',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Banks',
    'Adam Alvarez',
    'Walter Vang',
    'Samantha Wilson',
],
    'json': {
    'name': 'Katie Harper',
    'address': '43437 Brandon Path Apt. 528\nPort Ivantown, DE 30764',
},
    'key30405': 'value40192',
    'key83913': 'value31979',
    'key74316': 'value9987',
    'key97109': 'value48290',
    'key64212': 'value77781',
    'key24369': 'value17071',
    'key20265': 'value60442',
    'key47029': 'value29917',
    'key94521': 'value18791',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Natalie Dorsey',
    'address': '0806 Edward Park\nSouth Andresside, ND 85325',
    'text': 'Score enjoy machine. Big peace data live million stop hotel.\nHeart happen wish support behind. Decision social between section again note yard make.',
    'email': 'destinybrewer@example.net',
    'phone_number': '(917)990-4577',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Randy Ryan',
    'Joseph Sanchez',
    'Brian Garcia',
    'Andrew Phillips',
    'Gabriel Tanner',
    'Keith Williams',
    'John Gross',
    'Destiny Novak',
    'Sara Carter',
],
    'json': {
    'name': 'Kenneth Sanchez',
    'address': '7071 Reed Locks Apt. 780\nPaulaton, ID 71879',
},
    'key7280': 'value87109',
    'key56255': 'value13698',
    'key22088': 'value32852',
    'key28492': 'value99399',
    'key21445': 'value90530',
    'key24898': 'value10836',
    'key43893': 'value39126',
    'key81600': 'value10847',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Christopher Nixon',
    'address': '206 Craig Groves\nWest Jillian, WV 84930',
    'text': 'Go difficult million employee. Player fill end skill too.\nQuite tax maybe special. Baby candidate letter young education writer. Yet mean future service on stock onto glass.',
    'email': 'amber19@example.com',
    'phone_number': '(387)514-1651',
    'array_int_dynamic': [
    67202,
],
    'array_varchar_dynamic': [
    'Brittany Garcia',
    'Mr. Richard Rubio DDS',
    'Kathleen White',
    'Jason Small',
    'Michelle Franklin',
],
    'json': {
    'name': 'Sarah Hernandez',
    'address': '9358 Edwards Hills\nNorth Robertmouth, NV 04295',
},
    'key99788': 'value39931',
    'key33518': 'value69936',
    'key14068': 'value9759',
    'key91416': 'value36017',
    'key46635': 'value74794',
    'key89445': 'value56037',
    'key65779': 'value52700',
    'key40043': 'value80990',
    'key98764': 'value22736',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Nicole Trujillo',
    'address': '32711 Donna Trafficway Suite 527\nSusanbury, WA 77851',
    'text': 'Try pay day response notice design station. Box response resource live his. Rate suffer special yard similar student return throw. Author effort artist top play still.',
    'email': 'webblaura@example.com',
    'phone_number': '6082084396',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Quinn',
    'Todd Wood',
    'Anne Montgomery',
    'Abigail Burns',
    'Max Lowery',
],
    'json': {
    'name': 'Sherri Cox MD',
    'address': 'PSC 4810, Box 1092\nAPO AA 59743',
},
    'key67500': 'value24449',
    'key93059': 'value69030',
    'key70263': 'value72517',
    'key25041': 'value70117',
    'key3881': 'value98568',
    'key55275': 'value32800',
    'key71118': 'value91723',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Virginia Powell',
    'address': '65647 Bean Spur\nBushbury, WY 46024',
    'text': 'Keep avoid network. Lose board speech control young. Example fill movement order ability important good.',
    'email': 'morrowmichael@example.org',
    'phone_number': '+1-470-999-0802x52486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Davis',
    'Yolanda Jenkins',
    'Jeffrey Vasquez',
    'Linda Larson',
    'Donald Duran',
    'Mr. James Murphy',
    'Martin Duffy',
    'Heather Cunningham',
    'Kenneth Parker',
    'Nicole Collier',
],
    'json': {
    'name': 'John Long',
    'address': '5660 Mia Trail Apt. 729\nNorth Mary, ME 89468',
},
    'key32618': 'value60529',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Jeffrey Simon',
    'address': '253 Washington Drive Apt. 944\nNorth Michael, MA 07416',
    'text': 'Statement step voice participant catch talk. Toward recognize meeting sign piece tax. American even rich myself.\nCause less research. Interesting himself remember people peace law performance at.',
    'email': 'parkereduardo@example.org',
    'phone_number': '453-346-8310',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Scott Guzman',
    'Barbara Ruiz',
    'Austin Guerra',
    'Jeremy Lawson',
    'Darrell Sweeney',
    'Elizabeth Burke',
    'Melanie Obrien',
],
    'json': {
    'name': 'Emily Stanton',
    'address': '07690 Brittany Tunnel\nGreenstad, MT 06451',
},
    'key63090': 'value66740',
    'key61308': 'value29220',
    'key14370': 'value72379',
    'key224': 'value7344',
    'key84012': 'value89657',
    'key95847': 'value93257',
    'key30919': 'value13364',
    'key70262': 'value23155',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Julie Conrad',
    'address': '678 Brown Points Apt. 352\nRichardton, ID 39708',
    'text': 'Already prove member cost open media. Draw bar generation six third final.\nRed light right. Accept east over affect.\nControl up arrive tough government trip common shoulder.',
    'email': 'martinharrell@example.net',
    'phone_number': '868.797.0775x3644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brian Hoffman',
    'Dawn Gonzales',
    'Danielle Brown',
    'Dwayne Walls',
    'Molly Silva',
],
    'json': {
    'name': 'Jessica Bell MD',
    'address': 'Unit 9829 Box 8609\nDPO AA 76722',
},
    'key5842': 'value80596',
    'key38974': 'value81720',
    'key21809': 'value98780',
    'key99987': 'value84315',
    'key78264': 'value62918',
    'key19955': 'value72053',
    'key30319': 'value21806',
    'key30133': 'value46190',
    'key64005': 'value40307',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Joel Bishop',
    'address': '227 Fox Roads Apt. 958\nMaryfort, VT 55238',
    'text': 'Visit budget federal growth difficult red represent. Let sign finally position policy. Skin stop or some last. Throw size skin professional own hard.',
    'email': 'atkinscarmen@example.com',
    'phone_number': '(640)561-2685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Powers',
    'Brian Torres',
    'Jeffery Lindsey',
    'Kevin Cruz',
    'Ashley Jackson',
    'Danielle Nichols',
    'Sydney Santos',
    'Sean Chang',
    'Jason Summers',
    'Jerry Lopez',
],
    'json': {
    'name': 'Keith Gibson',
    'address': '59148 Hampton Pines Suite 968\nGrantstad, IN 48807',
},
    'key36592': 'value44539',
    'key6299': 'value24312',
    'key45135': 'value341',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Steven Hernandez',
    'address': '52818 Ross Haven\nNorth Sydneyton, NV 53276',
    'text': 'Mr would glass goal will write record. Appear process rather full.\nYourself generation today next knowledge boy. Yard important game sign effort nation size old.',
    'email': 'matthewphillips@example.org',
    'phone_number': '+1-959-955-1199x61607',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Geoffrey Davis',
    'Tim Cline',
],
    'json': {
    'name': 'Karen Bell',
    'address': '253 Powell Branch Apt. 355\nMillerbury, MT 58058',
},
    'key12680': 'value74093',
    'key62063': 'value40241',
    'key85885': 'value32625',
    'key24954': 'value36384',
    'key6718': 'value13438',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Patricia Miller',
    'address': '753 Willis Loop\nSpencerview, MD 12665',
    'text': 'Far campaign describe financial speech edge full. Draw nor include everyone decide quickly nothing.\nRest argue heart management camera. Difference room since great with. Strong prove test try.',
    'email': 'rgriffin@example.com',
    'phone_number': '649.755.3941',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Brown',
    'Judith Armstrong',
],
    'json': {
    'name': 'Sandra Stewart',
    'address': '248 Dylan Overpass\nEmilystad, DC 57077',
},
    'key66302': 'value11896',
    'key89501': 'value45412',
    'key2555': 'value4442',
    'key97419': 'value38618',
    'key28754': 'value25797',
    'key17924': 'value79606',
    'key53737': 'value90160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Albert Paul',
    'address': 'Unit 9984 Box 1949\nDPO AA 29851',
    'text': 'Mrs lose evening without policy. Someone this police nothing may wind investment concern. Artist my far several trial much owner.',
    'email': 'blakekatie@example.com',
    'phone_number': '660-488-9175',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Howard',
    'Kevin Brown',
    'Ronald Miller',
    'Andrea Thompson',
    'Jenny Ayala',
    'Mary Smith',
],
    'json': {
    'name': 'Thomas Smith',
    'address': '8361 Robertson Village Apt. 063\nHeatherborough, NE 71112',
},
    'key41125': 'value81961',
    'key94230': 'value86858',
    'key48323': 'value42917',
    'key24029': 'value30308',
    'key265': 'value19431',
    'key54674': 'value66116',
    'key39235': 'value47728',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Alexander Blair',
    'address': '4345 Hale Fall\nOlivermouth, VI 74117',
    'text': 'Call natural different should sister remember full. When laugh figure suffer assume drug artist deep. Add other teacher form put floor.\nRange carry reason number head. Let form throughout sort drug.',
    'email': 'marshjessica@example.org',
    'phone_number': '630.438.1643x92639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Ramirez',
    'Gina Porter',
    'Benjamin Chambers',
    'Stephanie Williams',
    'Ryan Murray',
    'Susan Rich',
    'Samantha Davis',
],
    'json': {
    'name': 'Natalie Lee',
    'address': '3509 Williams Ridge\nNew Haleyberg, MP 49732',
},
    'key16133': 'value45129',
    'key93197': 'value9292',
    'key43291': 'value43642',
    'key24462': 'value39197',
    'key6410': 'value21501',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Molly Anderson',
    'address': '890 Allen Circle\nSaraville, MS 97338',
    'text': 'Once class everyone environmental check short right us. Beautiful soon away performance office campaign. Thank arm along become.',
    'email': 'hsmith@example.com',
    'phone_number': '(714)694-0692',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Erica Garcia',
    'Carl Johnson',
    'Jessica Decker',
    'Mark Turner',
    'Kevin James',
    'David Hernandez',
    'Kimberly Miller',
],
    'json': {
    'name': 'Heather Armstrong',
    'address': 'Unit 2875 Box 8728\nDPO AP 29236',
},
    'key15459': 'value75655',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Kevin Hill',
    'address': '3315 Nicholas Manors\nEast Deniseport, MP 01421',
    'text': 'Usually describe hand. Season believe Republican. Enough by you company discuss describe himself century. Act natural staff human drive.',
    'email': 'charlene10@example.net',
    'phone_number': '5746980822',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Karen Rojas',
],
    'json': {
    'name': 'Julia Walsh',
    'address': '31204 Stephenson Stream\nNew Tammy, NJ 82960',
},
    'key2294': 'value31502',
    'key21301': 'value71759',
    'key17298': 'value63194',
    'key54907': 'value57723',
    'key216': 'value47431',
    'key7748': 'value19658',
    'key47179': 'value32435',
    'key31534': 'value52320',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Melissa Mckenzie',
    'address': '6243 Alexis Cliff\nWest Jeffreyfurt, ME 79715',
    'text': 'Lay actually use all look several tend. Interview beautiful bed option money trouble.',
    'email': 'robertguzman@example.net',
    'phone_number': '468-920-4072x773',
    'array_int_dynamic': [
    98157,
],
    'array_varchar_dynamic': [
    'Charles Gonzalez',
    'Derek Jackson',
],
    'json': {
    'name': 'Kathy Brooks',
    'address': '123 Suzanne Plaza Suite 350\nWest Jasonview, PW 86227',
},
    'key84783': 'value37105',
    'key4740': 'value38524',
    'key43118': 'value90538',
    'key56144': 'value9094',
    'key19860': 'value52380',
    'key59685': 'value4078',
    'key55084': 'value59393',
    'key87145': 'value51195',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Margaret Foster',
    'address': '4505 Walters Crescent Suite 111\nCynthiabury, WI 20120',
    'text': 'Film of property should process agreement air strategy. Stand rock system sing say. Garden fund expert but really.\nHusband own lawyer east help operation where. Recent size worry whose.',
    'email': 'kevin67@example.com',
    'phone_number': '(378)324-4172x52456',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Troy Hendricks',
    'Ann Knight',
    'Mary Harmon',
    'Nichole Parsons',
    'Crystal Martinez',
],
    'json': {
    'name': 'Martha Reed',
    'address': '533 Hart Plains Apt. 842\nPort Deannatown, RI 82660',
},
    'key73876': 'value76854',
    'key64159': 'value60675',
    'key96767': 'value98689',
    'key14611': 'value53996',
    'key93292': 'value58312',
    'key98287': 'value89154',
    'key58637': 'value25687',
    'key58843': 'value31435',
    'key96501': 'value23491',
    'key45071': 'value28854',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Aaron Dixon',
    'address': '1691 Molly Cove\nEmilyport, AS 63373',
    'text': 'Must program defense population. Offer just ago many model cover nothing. Weight cold real billion over trouble.\nCase want small. Management professional protect although upon trip news.',
    'email': 'brittneymckenzie@example.net',
    'phone_number': '413-902-4601',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Haynes',
    'Kimberly Saunders',
    'Sophia Johnson',
],
    'json': {
    'name': 'Charles Campbell',
    'address': '458 Brown Station\nLake Johnfurt, NH 75562',
},
    'key26790': 'value40269',
    'key61793': 'value17331',
    'key62843': 'value75327',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'David Gonzalez',
    'address': '68020 Laura Mill Apt. 521\nLaurastad, AR 41454',
    'text': 'Everything network yet lead action without serious. Radio oil national character blue city and strong. Hot go series board certain.\nQuestion dog provide. He special kitchen none throw interest.',
    'email': 'andreadunlap@example.com',
    'phone_number': '715-913-2661x7666',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Keith Rodriguez',
    'Latoya Elliott',
    'Brian Simmons',
    'Richard Ingram',
],
    'json': {
    'name': 'Christina Black',
    'address': '374 Delacruz Underpass Apt. 456\nSouth Wanda, FL 87503',
},
    'key75174': 'value35625',
    'key35330': 'value22392',
    'key99402': 'value88007',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Ryan Baker',
    'address': 'Unit 8358 Box 0694\nDPO AE 95912',
    'text': 'On city standard parent two. Discuss wall like.\nNear among including likely. May religious list figure from. Set work try old listen purpose rule.',
    'email': 'hannahcameron@example.org',
    'phone_number': '+1-454-617-4145x636',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Travis Valenzuela',
    'Christopher Sims',
    'Jesse Martinez',
    'Michael Martin',
    'Christopher Gonzalez',
    'Steven Bishop',
    'Shannon Ryan',
    'Scott Johnson',
],
    'json': {
    'name': 'Phillip Hendrix',
    'address': '909 Johnson Ranch Suite 299\nEast Steven, GU 80399',
},
    'key33976': 'value36533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Michael Riddle',
    'address': '4683 Catherine Field Apt. 527\nRamosmouth, CO 91549',
    'text': 'All program process station. Win about region me before avoid.',
    'email': 'melissagray@example.com',
    'phone_number': '336.731.6828',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amy Walton',
    'Robert Miller',
    'Beth Hall',
    'Shane Hobbs',
    'Patricia Reed',
    'Douglas Adams',
    'Jordan Murphy',
    'Joseph Trevino',
],
    'json': {
    'name': 'Jose Alexander',
    'address': '06847 Kevin Island Apt. 231\nPort Taylor, PW 63129',
},
    'key45424': 'value98903',
    'key95807': 'value32937',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Richard Hunter',
    'address': '385 Jessica Cape\nLake Jesse, NJ 23861',
    'text': 'Professor arm number before dog well growth. Both land little quality stay skill.\nSport box management news method recognize. Month professional toward.',
    'email': 'ytucker@example.net',
    'phone_number': '8296770523',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Janet Smith',
    'Jonathan Lee',
    'Caroline Wood',
    'Barbara Gordon',
    'Spencer Brown',
    'Jose Padilla',
    'Gary Gamble',
    'Jeff Kim',
],
    'json': {
    'name': 'Lisa Parsons',
    'address': '36006 Matthew Creek\nPort Charlesberg, WV 22692',
},
    'key32937': 'value23238',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jessica Anderson',
    'address': '590 Rogers Circle Suite 174\nSouth Jacobton, ID 34888',
    'text': 'Book dinner such from make industry professor. East effect thank American sell. Bill figure institution school always general heart. Anyone work what.',
    'email': 'jacobolson@example.com',
    'phone_number': '+1-691-384-4222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Murray',
    'Ashlee Clark',
    'John Collins',
    'Rick Booth',
    'Mr. Randy Hernandez',
    'Denise Henderson',
    'Leah Klein',
    'Brandon Crane',
    'Dr. Dylan Brown',
],
    'json': {
    'name': 'Nathaniel Weaver',
    'address': '78671 Angela Wells Apt. 312\nNorth Rachelburgh, AR 03560',
},
    'key57489': 'value82971',
    'key99977': 'value12296',
    'key55645': 'value87782',
    'key16533': 'value31438',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Terrance Jackson',
    'address': '575 West Parkways\nPort Lisa, NY 71835',
    'text': 'Clear top company over customer your debate.\nTell follow current medical play pass drug game. Lose mean party rule.\nThing between Mrs some. Specific law always.\nAcross information involve together.',
    'email': 'alexa72@example.org',
    'phone_number': '524.637.2855',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sheri White',
    'Ronald Vega',
    'Tina Black',
    'Mary Stanley',
    'Kathryn Hunter',
    'Charles Jones',
    'James Thompson',
],
    'json': {
    'name': 'Daniel Ramsey',
    'address': '52744 Kenneth Trace\nBeverlyview, AS 59676',
},
    'key25961': 'value12005',
    'key76089': 'value20144',
    'key75979': 'value48622',
    'key30159': 'value20857',
    'key21713': 'value49480',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Rebecca Ramirez',
    'address': 'USCGC Stout\nFPO AA 69668',
    'text': 'Mind girl a information court kitchen sister. Movement step particularly actually to pay book street. Nation beyond bag bad would. Avoid have upon may.',
    'email': 'johnsonwillie@example.com',
    'phone_number': '545.867.6231x88805',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Chris Sanchez',
    'Sean Solis',
    'Bryan Flores',
    'Sandra Walker',
    'Michelle Silva',
],
    'json': {
    'name': 'Sandra Wright',
    'address': '9984 Jones Freeway Suite 573\nEast Stevenmouth, PR 63896',
},
    'key31506': 'value10031',
    'key24463': 'value73403',
    'key38215': 'value6853',
    'key39674': 'value39744',
    'key58324': 'value1019',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Robin Johnson',
    'address': '9288 Mallory Bridge Apt. 479\nNicholastown, MP 35512',
    'text': 'Newspaper president magazine mother environmental policy. Evening good yes life camera own movement series. Officer suffer owner teacher.',
    'email': 'ashley08@example.org',
    'phone_number': '(267)970-2036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tina Padilla',
    'Tyler Mitchell',
    'James Olson',
    'John Brooks',
    'Kenneth Baker',
],
    'json': {
    'name': 'Brian Baker',
    'address': 'Unit 4043 Box 5771\nDPO AA 60868',
},
    'key75554': 'value66864',
    'key91641': 'value86048',
    'key38398': 'value38185',
    'key81759': 'value94439',
    'key25981': 'value10635',
    'key94113': 'value69100',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Michael Wilkinson',
    'address': '71482 Stokes Points\nAarontown, NY 09968',
    'text': 'Wish figure evening nice. Apply identify purpose view.\nSeat specific new indeed some. Exist under if meeting draw seat yourself. Same decade south.',
    'email': 'watsondustin@example.net',
    'phone_number': '801.462.9856x08661',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Wilson',
    'Thomas Parker',
],
    'json': {
    'name': 'Sheila Adams',
    'address': '34233 Michelle Glens\nNorth Maryport, MD 90373',
},
    'key29814': 'value71287',
    'key42149': 'value16447',
    'key3991': 'value19150',
    'key66369': 'value45710',
    'key23609': 'value38362',
    'key4393': 'value50258',
    'key62385': 'value19924',
    'key88534': 'value74311',
    'key99015': 'value29241',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Roger Young',
    'address': '192 Anderson Land\nMartinezton, WA 04010',
    'text': 'Fill central music last. Kitchen adult race our participant environmental. Produce great receive approach service argue garden visit.',
    'email': 'natasha72@example.net',
    'phone_number': '923.454.2483x8142',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Barry',
],
    'json': {
    'name': 'Helen Allison',
    'address': '753 Laura Brook\nEmilyville, NV 37797',
},
    'key12380': 'value53870',
    'key74047': 'value9153',
    'key18457': 'value87692',
    'key31787': 'value29542',
    'key67347': 'value53317',
    'key24809': 'value59636',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Kathleen Santiago',
    'address': '97727 Peter Courts Apt. 654\nLorettaside, NY 23351',
    'text': 'Image politics rule better. Road task interest environment.\nAssume himself care guy. Nation catch almost how grow. Commercial spend there player together left east. Board my dinner question.',
    'email': 'ellisdavid@example.org',
    'phone_number': '001-957-375-4040',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Young MD',
    'Jorge Flores',
    'Dorothy Garcia',
    'George Harris',
    'Edward Kemp',
    'Steven Reeves',
    'William Hayes',
    'Eric Diaz',
    'Joseph Wallace',
],
    'json': {
    'name': 'Lisa Miller',
    'address': '591 Cummings Landing\nSouth Teresa, MH 76294',
},
    'key57044': 'value46080',
    'key23244': 'value35702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Christopher Wallace',
    'address': '416 Debra Spring Apt. 203\nSouth Johnathan, KY 19381',
    'text': 'Budget Mr director great hand. Majority describe officer study however reduce. Specific his watch town home provide receive.',
    'email': 'kimberly81@example.org',
    'phone_number': '+1-773-881-2217x39188',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Arthur Brooks',
    'Jocelyn Harris',
    'Robert Smith',
],
    'json': {
    'name': 'Charlene Cook',
    'address': '75009 Deborah Courts\nNorth Danielhaven, NJ 27328',
},
    'key52745': 'value95846',
    'key30244': 'value75462',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Paul Beltran',
    'address': '1386 Mary Brooks\nDixonport, AL 88696',
    'text': 'Its experience support side national major agree. Guess side happy into. Take clear rest activity.\nNothing which tree. Compare case pretty south vote civil project.',
    'email': 'jill51@example.org',
    'phone_number': '740-546-7842',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Meyer',
    'Barbara Porter',
    'Sarah Norton',
    'Ryan Newton',
    'Melissa Gomez',
    'Darrell Garrett',
    'Nichole Jackson',
    'Cynthia Shannon',
],
    'json': {
    'name': 'Jorge Martin',
    'address': '801 Payne Dam\nNicolestad, OH 64099',
},
    'key25763': 'value64977',
    'key85917': 'value26579',
    'key32182': 'value75678',
    'key46524': 'value57375',
    'key27562': 'value33393',
    'key83661': 'value63299',
    'key16914': 'value57980',
    'key41482': 'value44632',
    'key94646': 'value30081',
    'key30789': 'value16481',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Stacy Grimes',
    'address': 'Unit 1406 Box 4614\nDPO AP 42415',
    'text': 'Second hour board pass value. Gun argue center young style court bag. Range class response it leave somebody either.\nSpecial detail his red once. Alone start me.',
    'email': 'cummingsvictoria@example.org',
    'phone_number': '314-636-2062',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lucas Wilson',
    'Melissa Gonzalez',
],
    'json': {
    'name': 'Timothy Medina',
    'address': '74777 Evans Pike Suite 775\nRichardshire, PR 09598',
},
    'key93122': 'value38118',
    'key15923': 'value36187',
    'key57196': 'value40733',
    'key21186': 'value55175',
    'key61468': 'value7481',
    'key65005': 'value26690',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Amy Jackson',
    'address': '23999 Knight Mission\nGarciaborough, TN 56397',
    'text': 'Customer TV relate ahead compare. National build improve suggest item. Many generation power field impact military build. Identify hit number treatment eat amount.',
    'email': 'sean57@example.org',
    'phone_number': '3655409980',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Hampton',
    'Shannon Rodriguez',
    'Natalie Roach',
    'Jeremy Huber',
    'Taylor Ferrell',
    'Leslie Munoz',
    'Melanie Thornton',
    'Patricia Wilson',
    'Michael Bird',
],
    'json': {
    'name': 'Zachary Taylor',
    'address': '4529 Garcia Points Suite 260\nDakotaville, WV 44215',
},
    'key38774': 'value11774',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Kimberly Short',
    'address': '308 Deborah Branch Suite 611\nGreerchester, SD 99386',
    'text': 'Wind win leave season. Something much thing military card seek. Stage art woman role fly.\nAudience gun own their nothing.\nValue break significant require cultural.',
    'email': 'matthew92@example.net',
    'phone_number': '254-507-5951',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Linda Randall',
    'John Holden',
    'Ashley Roberson',
],
    'json': {
    'name': 'Jill Horne',
    'address': '450 Kristina Viaduct\nWest Kimberly, AK 66299',
},
    'key16666': 'value31565',
    'key45495': 'value18763',
    'key50379': 'value78329',
    'key21678': 'value13606',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Victoria Dunn',
    'address': '740 Drake Springs Apt. 055\nTiffanyshire, PW 04003',
    'text': 'Start strong control cold. Yard ball sea right their. Send magazine door others state foot behind. Tv until money way me religious.',
    'email': 'jay49@example.com',
    'phone_number': '844.902.6144',
    'array_int_dynamic': [
    87619,
],
    'array_varchar_dynamic': [
    'Jennifer Shaw',
    'James Brown',
],
    'json': {
    'name': 'David Hunt',
    'address': '872 Kelly Estate Apt. 762\nKarenport, AZ 61085',
},
    'key84509': 'value15479',
    'key97038': 'value75943',
    'key67198': 'value69581',
    'key19409': 'value57070',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Ronnie Williams',
    'address': '1549 Miller Walks Apt. 195\nNicoleburgh, MO 18084',
    'text': 'Enjoy these national turn. Process on reveal season green political. Reality since interview price house street know arrive.\nIssue face true none process those certain. Property reveal growth until.',
    'email': 'brittany59@example.com',
    'phone_number': '+1-388-708-9461',
    'array_int_dynamic': [
    55916,
],
    'array_varchar_dynamic': [
    'Alexander Simmons',
    'Jennifer Rodgers',
    'Hannah Padilla',
    'Eric Edwards',
    'Abigail Robinson',
    'Kirk Smith',
    'Tracy Moreno',
],
    'json': {
    'name': 'Victoria Richard',
    'address': '620 Johnson Village\nLake Robert, NV 27943',
},
    'key24223': 'value36693',
    'key45734': 'value10265',
    'key56674': 'value29857',
    'key70011': 'value33862',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Desiree Davis',
    'address': '8237 Rivas Lake\nPort Brooke, LA 58188',
    'text': 'American seven environment much. Sort his conference ten gas test happy.\nCentral meeting different must international everybody. System off special yes. Fear feeling employee describe resource.',
    'email': 'kvasquez@example.org',
    'phone_number': '(743)510-3431x764',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Morgan Burgess',
    'Michael Herrera',
],
    'json': {
    'name': 'Michael Orr',
    'address': '6623 Ford Walk\nWest Jessicaside, KY 75407',
},
    'key76516': 'value13105',
    'key3731': 'value5805',
    'key15298': 'value73715',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Brittany Johnson',
    'address': '3019 Gross Groves\nNew Dustinhaven, NJ 55321',
    'text': 'Speech throw notice. Along account grow computer. Exactly our then property turn.\nWatch themselves guess end long. Card oil teacher. Deep sister rise daughter remain sit.',
    'email': 'adamsjohn@example.net',
    'phone_number': '+1-440-959-2094x287',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Harmon',
    'Adrian Lee',
    'Janet Hicks',
],
    'json': {
    'name': 'Austin Colon',
    'address': '383 Emma Locks Suite 878\nWest Stanleymouth, CO 96282',
},
    'key61763': 'value24053',
    'key3632': 'value48769',
    'key89396': 'value66735',
    'key1876': 'value28929',
    'key16059': 'value22800',
    'key60921': 'value86684',
    'key83780': 'value42557',
    'key10808': 'value47550',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Kevin Tran',
    'address': '14654 Sanchez Streets\nSouth Jacobburgh, KY 48016',
    'text': 'Company road leg right idea any four look. Thus happen strong assume major lose. Sound too industry.\nPurpose executive natural manager. Nor term lot attention enter southern.',
    'email': 'mglenn@example.com',
    'phone_number': '914.693.6364x2669',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tony Ruiz',
    'William Holmes',
    'Caleb Ball',
    'Michelle Jones',
    'Elizabeth Benson',
    'Rebecca White',
    'Thomas Jacobson',
    'Dana Dudley',
    'Lynn Thomas',
    'Tiffany Nielsen',
],
    'json': {
    'name': 'Anthony Olson',
    'address': '181 Keith Grove Apt. 674\nSouth Sherylfort, ME 52654',
},
    'key51065': 'value5139',
    'key20433': 'value15293',
    'key72402': 'value61783',
    'key13618': 'value10976',
    'key79829': 'value49161',
    'key25828': 'value98391',
    'key37781': 'value47458',
    'key6542': 'value23483',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Becky Duffy',
    'address': '73366 Eric Park\nNorth Ashleytown, MO 62852',
    'text': 'Someone reduce significant themselves. Wait likely soon shoulder animal. Other fire analysis laugh brother. Decide officer follow evening pay.\nRoom herself yet manage. Loss authority develop down.',
    'email': 'elynch@example.net',
    'phone_number': '652.874.9686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Watkins',
    'David Shannon',
    'Kathy Chase',
],
    'json': {
    'name': 'Jonathan Collins',
    'address': '5477 Smith Neck Apt. 017\nChaveztown, NV 91520',
},
    'key99145': 'value90737',
    'key85013': 'value82732',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Katherine Garner',
    'address': '4031 Alvarado Fort Suite 746\nLake Ryanville, WA 42780',
    'text': 'None its interview add walk. Report begin seem forward toward service treat despite. East show learn age. Economic energy wide ten.\nBeat from some state. Why born couple.',
    'email': 'jherman@example.net',
    'phone_number': '(227)825-1132x1793',
    'array_int_dynamic': [
    82755,
],
    'array_varchar_dynamic': [
    'James King',
    'Joseph Nguyen',
    'Nicholas Smith',
    'Stacy Baker',
    'Kristin Mcconnell',
],
    'json': {
    'name': 'Wesley Johnson',
    'address': '967 Ritter Station Apt. 765\nSouth Kimberly, ID 15762',
},
    'key55361': 'value34812',
    'key1778': 'value83043',
    'key8774': 'value94340',
    'key41643': 'value63376',
    'key60774': 'value73075',
    'key71992': 'value55092',
    'key76556': 'value96488',
    'key58514': 'value761',
    'key50206': 'value97897',
    'key35723': 'value26478',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Kristina Butler',
    'address': '01988 Steven Mount\nNicolehaven, NJ 07312',
    'text': 'Join all table bring. Human plan executive. Interview cell finish site phone better speech common.',
    'email': 'floressamuel@example.org',
    'phone_number': '+1-879-620-2122',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Adam Anderson',
],
    'json': {
    'name': 'Dr. Amy Oneal',
    'address': '932 Jasmine Port\nTiffanyshire, DC 99211',
},
    'key1016': 'value39130',
    'key67940': 'value69122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Alisha Rose',
    'address': '60157 Leslie Plaza\nNorth Marcus, AS 48955',
    'text': 'Reduce team popular reality tell trip position. Late final fish listen month.\nStreet black and help once growth at determine.',
    'email': 'sandovalsarah@example.net',
    'phone_number': '(681)937-7977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Burnett',
    'Jenny Mejia',
    'Kelli Schmidt MD',
    'Andrew Greer',
    'Crystal Marsh',
    'Jonathan Dyer',
    'Ryan Bryant',
    'Brittany Beard',
    'Dana Drake',
],
    'json': {
    'name': 'Alicia Miller',
    'address': '5998 Robert Ville Apt. 721\nWest Curtis, FL 38454',
},
    'key46845': 'value60343',
    'key18441': 'value79491',
    'key65095': 'value67309',
    'key86493': 'value58651',
    'key96541': 'value14973',
    'key44498': 'value99640',
    'key74049': 'value86610',
    'key88104': 'value27092',
    'key44694': 'value91701',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Samantha Brandt',
    'address': '792 Daniel Glens\nRoseside, OK 96533',
    'text': 'Break senior cultural find. Recently across tell sometimes student.\nAlready tax fall herself particular. Toward despite guy growth situation. President compare key.',
    'email': 'edwardsdeanna@example.com',
    'phone_number': '393.372.7063x04201',
    'array_int_dynamic': [
    29688,
],
    'array_varchar_dynamic': [
    'Denise Kennedy',
    'Amanda Jensen',
    'John Harrison',
    'Crystal Richardson',
    'Rebecca Stanley',
    'Jennifer Johnson',
    'James Guzman',
    'Jaime Miller',
],
    'json': {
    'name': 'Nicholas Valencia',
    'address': '131 Taylor Center Apt. 624\nTommyport, OH 26289',
},
    'key16283': 'value28342',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Lawrence Bonilla',
    'address': 'USNS Torres\nFPO AP 13538',
    'text': 'Would building like opportunity. Decade add town simply control rock. Skill approach sea card.\nPhone deal blue hour indicate. Suggest relationship car himself weight. Forget modern red game.',
    'email': 'danielli@example.net',
    'phone_number': '706-482-1118',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Sherman',
    'William Parrish',
    'Brendan Moore',
    'Daniel Jones',
    'Nicholas Ramirez',
],
    'json': {
    'name': 'Andrea Erickson',
    'address': '32656 Toni Locks Apt. 760\nNew Kimberlytown, VT 30351',
},
    'key12505': 'value18495',
    'key77877': 'value27423',
    'key79682': 'value71615',
    'key16290': 'value77861',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Tony Rogers',
    'address': '0986 Donna Turnpike Suite 021\nNorth Jacob, VA 87542',
    'text': 'Political adult star big. Training would federal would. Model son clearly lawyer arrive wear card.\nSide evidence full body memory personal. The close weight often point attorney.',
    'email': 'bryanward@example.net',
    'phone_number': '(228)358-6533x447',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Delacruz',
    'David Mcmahon',
    'Tracy Ramirez',
    'Benjamin Gonzalez',
    'James Miller',
    'Alicia Whitehead',
    'Dr. Cathy French DVM',
    'Pam Vasquez',
    'Julie Smith',
    'Richard Lopez',
],
    'json': {
    'name': 'Lynn Sanchez',
    'address': '0427 Emily Union\nSaundersport, DE 48635',
},
    'key47501': 'value86457',
    'key92259': 'value10337',
    'key72044': 'value8527',
    'key79788': 'value78519',
    'key94847': 'value3719',
    'key73527': 'value82496',
    'key53736': 'value30927',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Paula Erickson',
    'address': '63623 Kline Lights\nAmyburgh, IN 71386',
    'text': 'Bring hospital might image property career east. Book show figure.\nData short say already suggest manage scientist.',
    'email': 'dana47@example.org',
    'phone_number': '+1-505-502-6828x7962',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Heather Ellis',
    'Richard Mckee',
],
    'json': {
    'name': 'Christopher Cobb',
    'address': '16519 Fisher Track Apt. 225\nEast Susan, NJ 36338',
},
    'key26387': 'value87555',
    'key89314': 'value85937',
    'key47053': 'value16506',
    'key14913': 'value91602',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Scott Phillips',
    'address': '33054 Timothy Plaza\nTonyaland, MT 43225',
    'text': 'Along happen but age. Agreement view single wall however economic international. Me around determine happy quite at.\nKid song experience. Continue themselves above who special low require.',
    'email': 'stricklandchristopher@example.net',
    'phone_number': '001-331-724-2255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Wong',
    'Kenneth Crawford',
    'Victoria Morris',
    'Ashley Scott',
    'William Bray',
    'Crystal Jones',
    'Kathryn Rodriguez',
    'Matthew Guzman',
    'Anthony Rice',
    'Angela Montgomery',
],
    'json': {
    'name': 'Brianna Reyes',
    'address': '310 Mitchell Parks\nKennethmouth, UT 25715',
},
    'key62798': 'value65403',
    'key28367': 'value71155',
    'key32845': 'value99601',
    'key92757': 'value29227',
    'key99780': 'value27861',
    'key19804': 'value34611',
    'key33931': 'value16729',
    'key96512': 'value56769',
    'key87652': 'value8042',
    'key41870': 'value31410',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'James Beard',
    'address': '54174 Jason Run Suite 909\nLake Dustinshire, MH 23835',
    'text': 'Million sell party knowledge. Positive time clearly his.\nTax me build may make. Continue old before agreement campaign.\nMajor teach politics fact. Feeling style girl sit pressure.',
    'email': 'andrewmoses@example.org',
    'phone_number': '723-544-4035',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Zimmerman',
    'Emily Kaufman',
    'Melanie Larson',
    'Melissa Gill',
    'Christina Little',
],
    'json': {
    'name': 'Melissa Small',
    'address': '19834 Campbell Row Apt. 011\nPort Christianview, OH 76364',
},
    'key69322': 'value52807',
    'key51120': 'value62319',
    'key92296': 'value23315',
    'key51223': 'value58632',
    'key38215': 'value67674',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Chelsea Prince',
    'address': '352 Dixon Trail\nWest Joseph, TX 27863',
    'text': 'Republican space possible central population bag. Area already consider.\nMake discussion then from act pretty. Road mouth guess what risk give section.',
    'email': 'cindy21@example.net',
    'phone_number': '5922618156',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Megan Carroll',
    'Patricia Mitchell',
    'Alex Morrow',
],
    'json': {
    'name': 'David Frost',
    'address': '8319 Curtis Squares Apt. 750\nNew David, PW 74014',
},
    'key33180': 'value60852',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Erin Walker',
    'address': '70416 Brian Crossroad Suite 050\nSavageshire, VT 42151',
    'text': 'Production others would reflect happen. Threat establish but home production memory road.\nHim nation professor near pass when institution better. Southern I yard turn.',
    'email': 'hectorsnow@example.net',
    'phone_number': '+1-397-828-8270x495',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Smith',
],
    'json': {
    'name': 'Jessica Williams',
    'address': '805 Thomas Courts Apt. 990\nCarpenterside, IL 80686',
},
    'key84196': 'value32975',
    'key42494': 'value50020',
    'key29882': 'value60919',
    'key43692': 'value19680',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Anna Jones',
    'address': '912 Diaz Corner\nJacksonmouth, NH 32809',
    'text': 'Necessary decide crime fact compare. Traditional air hard lose baby team support.\nSeason those sport. Sea consider food letter.',
    'email': 'williamsgary@example.net',
    'phone_number': '2768251312',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Felicia Mayo',
    'Barbara Phillips DVM',
    'Jennifer Ross',
    'Susan Cisneros',
    'Garrett Schroeder',
],
    'json': {
    'name': 'Tina Perry',
    'address': '01199 Ryan Ville Suite 916\nNorth Destinymouth, ND 14449',
},
    'key65482': 'value62026',
    'key55808': 'value2844',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Caleb Lang',
    'address': '072 Sanchez Shoals\nNorth Raymondbury, CO 28990',
    'text': 'Shake buy serious know provide such develop. Side skill main.\nTheir line discussion method place. Figure class argue ok much involve.',
    'email': 'morenopamela@example.net',
    'phone_number': '4289898165',
    'array_int_dynamic': [
    23770,
],
    'array_varchar_dynamic': [
    'Harold Robinson',
    'Molly Abbott',
    'Donna Cannon',
    'Catherine Reed',
    'Steven Levine',
    'Michael Green',
    'Paula Turner',
    'Tammy Casey',
],
    'json': {
    'name': 'Richard Church',
    'address': '3637 Osborne Dam Apt. 645\nPort Lisafurt, VT 78295',
},
    'key39624': 'value25190',
    'key38779': 'value67144',
    'key89841': 'value50498',
},
],
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



    def test_request_2(self):
        """测试请求 2 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '99e56c05-62ef-11f0-a460-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_45_713937MVfOiivb',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-100-2]_1752744167.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId12810021752744167Json()
    test.run_tests()
