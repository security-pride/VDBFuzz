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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-100-2]_1752744123_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-100-2]_1752744123.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl12810021752744123Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-100-2]_1752744123.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-100-2]_1752744123.json"
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
    'RequestId': '7fc25780-62ef-11f0-9603-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_01_863272SUvKqeMJ',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'vector',
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
    'RequestId': '7fe35d60-62ef-11f0-90b9-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_01_863272SUvKqeMJ',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Denise Marks',
    'address': '7644 Kelsey Locks\nNew Sethland, LA 41892',
    'text': 'Very public half while help land. Student tree place example right pick.\nMaterial general matter. Impact collection become bill program quality. Make start number like need party.',
    'email': 'gabrielle33@example.org',
    'phone_number': '+1-575-230-9332x32971',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Heather Thomas',
    'Danielle Hawkins',
    'Nicole Norris',
    'Erik Grant',
    'Edwin Sampson',
    'Daniel Mercer',
    'Kristen Sanders',
    'Jennifer Mitchell DVM',
    'Sabrina Gonzales',
    'Cory Hawkins',
],
    'json': {
    'name': 'Ashley Anderson',
    'address': '9268 Bailey Summit\nNorth Douglasview, FM 55026',
},
    'key85791': 'value24133',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Ashley Smith',
    'address': '77813 Black Lodge\nLake Matthew, VA 35139',
    'text': 'We here environmental fund expert into.\nAdministration fly management probably else and watch. Positive mention woman nature two under. Police once region nearly million well.',
    'email': 'ryanjerry@example.com',
    'phone_number': '976.868.1307x497',
    'array_int_dynamic': [
    12192,
],
    'array_varchar_dynamic': [
    'Christopher Ramirez',
    'Ryan Fox',
    'Yvonne Noble',
    'John Campbell',
    'Kristi Thompson',
    'Janet James',
    'Brittany Harmon',
    'Bridget Aguirre',
    'Jason Greer',
],
    'json': {
    'name': 'Patricia Ramirez',
    'address': '96274 Schneider Key Apt. 272\nLake Charles, CA 74773',
},
    'key11311': 'value25342',
    'key89744': 'value6316',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Stacey Simpson',
    'address': '9734 Tracy Falls Apt. 178\nPhelpsland, TX 19605',
    'text': 'Wish fill sort develop. Sign old any his enjoy both little. Become short north maintain others natural.\nData building letter car job. Dark purpose while number cut action. Gun eat cover see design.',
    'email': 'johnjones@example.net',
    'phone_number': '869-329-2002x607',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Alicia Bryant',
    'Jeremy Simpson',
    'Rebecca Carpenter',
    'Devin Farrell',
    'Mike Smith',
    'Patricia Brown',
    'Lori Barker',
    'Jessica Payne',
    'Mark Holder',
],
    'json': {
    'name': 'Terri Huffman',
    'address': '4887 Austin Parks\nButlerborough, NC 77696',
},
    'key47667': 'value23665',
    'key58694': 'value2575',
    'key39530': 'value70390',
    'key96220': 'value53929',
    'key80156': 'value76077',
    'key74047': 'value15764',
    'key22078': 'value69323',
    'key7181': 'value20932',
    'key28348': 'value67115',
    'key37038': 'value56638',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Kimberly Smith',
    'address': '324 Laurie Walks Suite 638\nWilliamstad, IN 27346',
    'text': 'Coach event seat involve garden chair. Pattern perhaps sign.\nShe effect cultural number party sit one. Month past establish pattern financial trade.',
    'email': 'vanderson@example.com',
    'phone_number': '+1-447-661-2252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Keith Castillo',
    'Aaron Cain',
    'Phillip Gardner',
    'Donna Carpenter',
    'Jessica Brown',
    'Maria Dean',
],
    'json': {
    'name': 'Anthony Ramirez',
    'address': '219 Brennan Causeway\nParkerburgh, FL 49868',
},
    'key99174': 'value5848',
    'key53962': 'value55974',
    'key30555': 'value26462',
    'key15767': 'value80791',
    'key22052': 'value42375',
    'key59496': 'value69828',
    'key87754': 'value76410',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Karen Freeman',
    'address': '639 Steven Plains Suite 976\nTarabury, MS 27982',
    'text': 'Source drop western science race local turn.\nItem far ground board over budget interesting. Make property others suffer likely pattern space. Along sister hear space. Authority event boy enough son.',
    'email': 'ygreen@example.org',
    'phone_number': '928-771-4187x33682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Horn',
    'Jamie Hawkins',
    'Stephanie Pittman',
    'Brittany Lopez',
    'Jennifer Porter',
],
    'json': {
    'name': 'Maurice Smith',
    'address': '4737 Mullen Meadows\nEast Adrienne, GU 88529',
},
    'key63870': 'value48184',
    'key99120': 'value8100',
    'key45325': 'value35602',
    'key54624': 'value12945',
    'key4926': 'value46990',
    'key77463': 'value84834',
    'key21303': 'value71610',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Haley Lynn',
    'address': '229 Wallace Street\nGordonland, MD 92599',
    'text': 'Month figure nation however. Big then however TV outside professor really.\nReality agreement watch above price break society.',
    'email': 'arroyovalerie@example.org',
    'phone_number': '989-997-9347x661',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mark Hunt',
    'Robert Lara',
    'Troy Frazier',
    'Brian Garcia DVM',
    'Erica Cardenas',
    'Samuel Johnson',
    'Joshua Wheeler',
    'James Davis',
],
    'json': {
    'name': 'Jason Weaver PhD',
    'address': '479 Makayla Mill Apt. 529\nJameston, NY 77673',
},
    'key96717': 'value86302',
    'key99990': 'value15095',
    'key53633': 'value50476',
    'key7124': 'value81247',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Michael Garner',
    'address': '646 Evans Lights\nKeithside, MD 19044',
    'text': 'Structure seek president. Every eye growth whom sign administration star.\nTend until as.\nEducation memory itself news ask law and. Family factor trial travel box. Do occur assume tax light.',
    'email': 'tlopez@example.com',
    'phone_number': '(645)523-7525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Chad Jenkins',
    'Jordan Wells',
    'Kimberly Clayton',
    'Logan Leonard',
    'Marc Gallegos',
    'Mr. Alan Boyd',
],
    'json': {
    'name': 'Cynthia Barnes',
    'address': 'Unit 1485 Box 5722\nDPO AE 88157',
},
    'key11543': 'value54830',
    'key84704': 'value50937',
    'key63595': 'value66525',
    'key9974': 'value34937',
    'key21250': 'value93785',
    'key35463': 'value29370',
    'key42947': 'value44432',
    'key37337': 'value98775',
    'key20775': 'value31984',
    'key67082': 'value65219',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Tina Foster',
    'address': '62782 Amanda Islands\nMichaelstad, WV 67579',
    'text': 'Subject relate want live fear. Music economy result many hotel. Support who truth story trade hand better.\nSecond baby sing according. Particularly know soon north effect behind community.',
    'email': 'grantwilliams@example.net',
    'phone_number': '(879)964-5409x339',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Parker',
    'Louis Rodriguez',
    'Glenda Bean',
    'Emily Baker',
    'Alexis Roberts',
    'Douglas Hunter',
    'Anthony Chaney',
    'Tristan Benitez',
],
    'json': {
    'name': 'Elizabeth Johnson',
    'address': '213 Cooley Stream\nFernandezton, OR 72054',
},
    'key93928': 'value48608',
    'key75349': 'value11940',
    'key72233': 'value88592',
    'key27404': 'value19622',
    'key99537': 'value59156',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Lori Turner',
    'address': '38322 Ortiz Mission\nTylerfurt, VI 55558',
    'text': 'Property reflect positive ask bed challenge gas even. Decision identify draw. Be read play.\nMemory financial product take follow energy. Month social doctor however.',
    'email': 'clifford28@example.net',
    'phone_number': '(761)481-5751x315',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Anderson',
    'Stephanie Burnett',
    'Calvin Peterson',
    'David Rivera',
    'Debbie Chen',
],
    'json': {
    'name': 'Ricky George',
    'address': '2012 Anderson Fields\nEllischester, ND 79749',
},
    'key98440': 'value46274',
    'key34380': 'value87310',
    'key36761': 'value37965',
    'key2352': 'value95398',
    'key47959': 'value45613',
    'key41046': 'value56414',
    'key433': 'value33688',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Justin Hayes',
    'address': '654 Emily Well Apt. 843\nFloreschester, SD 30075',
    'text': 'Interesting pay third painting simple especially certain. Realize food modern yet. Himself part rich dream one improve large. Recognize animal decision off threat cover same.',
    'email': 'ianmarshall@example.com',
    'phone_number': '(896)445-6502x443',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Robert Lopez',
    'Sarah Cole',
    'Lynn Leach',
    'Rose Hernandez',
    'Mary Garcia',
    'Robin Carter',
    'Dr. Maria Andrews',
    'Marc Wilson',
    'Mr. Raymond Gonzalez',
],
    'json': {
    'name': 'Dawn Griffin',
    'address': '075 Donald View Apt. 547\nAimeestad, VI 64682',
},
    'key58326': 'value83654',
    'key74019': 'value24617',
    'key73063': 'value59614',
    'key4678': 'value37181',
    'key21604': 'value78339',
    'key72009': 'value47422',
    'key13421': 'value30030',
    'key13379': 'value68199',
    'key19062': 'value70846',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Sydney Barr',
    'address': '5700 Paul Row\nPaulmouth, MP 37627',
    'text': 'With type fight consumer. Explain white life purpose indeed.\nAlways follow economy establish.',
    'email': 'callahannatalie@example.net',
    'phone_number': '(977)904-0734',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James Delacruz',
    'Christina Vega',
    'Heather Summers',
    'Timothy Thomas',
    'Benjamin Rodriguez',
    'Angela Jones',
    'Brian Marks',
],
    'json': {
    'name': 'John Burton',
    'address': '93307 Nguyen Summit Suite 257\nNew Kevin, ND 08997',
},
    'key57208': 'value59889',
    'key20232': 'value96086',
    'key84955': 'value78207',
    'key29568': 'value94710',
    'key27155': 'value33945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Gabrielle May',
    'address': '129 Brown Squares Apt. 747\nNorth Seanhaven, FM 20266',
    'text': 'Bill evidence cell apply civil as. Third policy up.\nMouth detail pressure us reveal despite world. Number serve too rise recognize keep.',
    'email': 'lewischase@example.net',
    'phone_number': '388.377.5304x90643',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jesus Allen',
    'Nathan Wright',
    'Karla Williams',
    'Cynthia Chen',
    'Katie Spencer',
    'Mary Ramirez',
    'Janice Hughes',
    'Arthur Moody',
],
    'json': {
    'name': 'Victoria Petersen',
    'address': '918 Brandi Haven\nEdwardsmouth, ME 54355',
},
    'key23946': 'value6086',
    'key58692': 'value42454',
    'key23053': 'value85396',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Michael Thornton',
    'address': 'Unit 6333 Box 1332\nDPO AA 22937',
    'text': 'Leave send happy either audience. Color key like month hear member.\nTotal speech be almost wide.\nPlan much write result raise leave consider baby. Explain most process let. Hour for build story.',
    'email': 'barmstrong@example.org',
    'phone_number': '6017801790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Annette Boyd',
],
    'json': {
    'name': 'Joseph Dixon',
    'address': '661 Carl Highway\nWest Anthony, PA 67169',
},
    'key86456': 'value66665',
    'key52525': 'value34542',
    'key29712': 'value79650',
    'key26251': 'value71341',
    'key30740': 'value76770',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Donna Castillo',
    'address': '650 Kyle Forks Suite 291\nNorth Michael, AR 68857',
    'text': 'Represent behavior design.\nProject break certain himself smile return. Continue space sit effort. Half treat traditional level head ok him work.',
    'email': 'davidbrown@example.org',
    'phone_number': '001-535-398-0758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Calvin Bradley PhD',
    'Crystal Perkins',
    'Rachel Rogers',
    'Logan Scott',
    'Lori Fischer',
    'Veronica Chambers PhD',
    'Carl Vega',
    'Douglas Shields',
    'Nicholas Smith',
],
    'json': {
    'name': 'Justin Maddox DDS',
    'address': '01409 Price Spur Apt. 284\nJosephton, DC 66713',
},
    'key16537': 'value26009',
    'key84155': 'value1277',
    'key10032': 'value54546',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Deborah Calhoun',
    'address': '02938 Wright Greens Apt. 828\nHallborough, WI 03443',
    'text': 'Can at continue window. Green former pull same federal degree word. Production suffer today gun.\nHard those worker out young. Husband its great.',
    'email': 'ygarza@example.org',
    'phone_number': '594-255-6275x362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Stanley Hodge',
],
    'json': {
    'name': 'Amy Jones',
    'address': '4551 Watson Brooks Apt. 814\nMooneyside, AK 75717',
},
    'key74969': 'value33975',
    'key92874': 'value76979',
    'key10007': 'value40782',
    'key2371': 'value17311',
    'key79884': 'value58244',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jacqueline Hansen',
    'address': '78231 Susan Inlet\nEast Tonifort, UT 35977',
    'text': 'Less miss how at general better. Cut window feeling move his ok.\nCourt art ahead seat nation pay wrong. Paper successful point beautiful.',
    'email': 'wstewart@example.org',
    'phone_number': '(618)460-0083',
    'array_int_dynamic': [
    86957,
],
    'array_varchar_dynamic': [
    'Deanna Payne',
    'Janet Duncan',
    'Brandon Lewis',
    'Reginald Smith',
    'Cheryl Ramsey',
],
    'json': {
    'name': 'John Jones',
    'address': '384 Taylor Square\nWest Daniellefurt, MH 67289',
},
    'key73880': 'value81698',
    'key42558': 'value5636',
    'key53766': 'value15938',
    'key21274': 'value67936',
    'key21827': 'value97175',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Christopher Horne',
    'address': '1269 Lisa Isle\nSouth Beth, IN 20785',
    'text': 'Laugh while film relationship explain take. Woman heavy feeling book around opportunity let. Perform minute everybody work.\nFind artist enough by threat finish.',
    'email': 'robert98@example.net',
    'phone_number': '001-223-829-8492x74925',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Estrada',
    'Christopher Brown',
    'Kelsey Holmes',
    'Karen Dixon',
    'Dr. Tony Singh',
    'Kendra Grimes',
    'Kevin Barry',
    'Kristina Scott',
    'Jose Wood',
],
    'json': {
    'name': 'Joseph Munoz',
    'address': '427 Christopher Isle Apt. 163\nSouth Barbaraport, MS 17537',
},
    'key59809': 'value88088',
    'key54905': 'value63258',
    'key17023': 'value9138',
    'key38160': 'value22530',
    'key56516': 'value50538',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Mrs. Anna Smith',
    'address': 'Unit 9645 Box 4379\nDPO AE 12770',
    'text': 'Hear return either account unit. Allow they day long book full. Our agent performance tough.\nJob main try. Pressure discuss coach. Threat six everything plant.',
    'email': 'nicole10@example.org',
    'phone_number': '557.555.3949x72946',
    'array_int_dynamic': [
    38508,
],
    'array_varchar_dynamic': [
    'Travis Clark',
    'Jessica Herrera',
    'Richard Myers',
    'Allison Ochoa',
    'Jessica Lynch',
],
    'json': {
    'name': 'Danny Rodriguez',
    'address': '62502 Armstrong Lake Apt. 675\nPort Samantha, IA 42144',
},
    'key86421': 'value13282',
    'key82752': 'value3723',
    'key28885': 'value71077',
    'key49977': 'value14691',
    'key36808': 'value20015',
    'key22432': 'value19762',
    'key67538': 'value17643',
    'key58913': 'value55016',
    'key55007': 'value2260',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Jimmy Smith',
    'address': '5321 Ross Village\nHernandezborough, NJ 23234',
    'text': 'Office call cover peace remain focus. Consumer probably rate like possible send. Hard or affect whose only.',
    'email': 'stephanie58@example.org',
    'phone_number': '+1-460-692-4772x5611',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Gay',
    'Alexandra Walker',
    'Angela Rodriguez',
    'Holly Thompson',
    'Angela Perez DDS',
    'Nancy Wilson',
    'Terry Hammond',
    'Timothy Vasquez',
    'Cindy Wood',
    'Cassandra Ball',
],
    'json': {
    'name': 'Melissa Moon',
    'address': '163 Seth Port Suite 670\nCollinsland, NC 12713',
},
    'key34374': 'value58554',
    'key54268': 'value12668',
    'key93878': 'value25634',
    'key27001': 'value42527',
    'key98160': 'value81867',
    'key88292': 'value63128',
    'key84130': 'value1348',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'James Jordan',
    'address': '47579 Thomas Expressway\nDanaburgh, NE 00655',
    'text': 'Choose media sing short second away term. Child popular clearly. Bar find high.',
    'email': 'joshua98@example.com',
    'phone_number': '909.642.3188x45781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Landry',
    'Timothy Ramirez',
    'Gerald James',
    'John Meadows',
    'Mrs. Rachel Bridges DVM',
    'Judith Riley',
    'Larry Bowman',
    'James Garcia',
],
    'json': {
    'name': 'Joseph Tran',
    'address': '99651 Lee Lane\nThomaschester, ME 70056',
},
    'key29496': 'value63102',
    'key60746': 'value44595',
    'key11033': 'value27897',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Darryl Mcdaniel',
    'address': '53737 Joseph Park\nNew Ronaldborough, WY 33889',
    'text': 'Friend poor especially claim participant assume. Option PM trouble skill event particular get.\nStudy benefit particular television piece. Off production fire control last issue.',
    'email': 'lindseyevans@example.org',
    'phone_number': '+1-385-905-8958',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Burke',
    'James Carlson',
    'Jordan Martin',
    'Kevin Roberts',
    'William Ramirez',
    'Larry Hernandez',
    'John Norris',
    'Dana Moss',
],
    'json': {
    'name': 'Dr. Bryan Smith',
    'address': '017 Roth Glens Apt. 697\nLake Brian, KS 52155',
},
    'key57549': 'value98635',
    'key43488': 'value95744',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Misty Martinez',
    'address': '7907 Cindy Causeway Suite 666\nDianeton, WV 83509',
    'text': 'True wear appear close. Involve do mouth. Next suddenly threat cultural far blue together.\nActually meet wide issue. His current fact alone great ten.',
    'email': 'martinjoshua@example.com',
    'phone_number': '631-342-2280x974',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Huber',
    'Darren Gallagher',
    'Melissa Archer',
    'Heather Strong',
    'Mark Shaffer',
],
    'json': {
    'name': 'Shawn Bowman',
    'address': '1009 Cassandra Light\nPort Cynthia, ID 14274',
},
    'key9011': 'value47993',
    'key88437': 'value73357',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Nicholas Perez',
    'address': '191 Cynthia Mountain Suite 108\nHillhaven, NY 39246',
    'text': 'People common hold fire production decision wish. White street today figure right. Respond table what they. Edge life sea south establish.\nExecutive process list well. Mention hour smile worry.',
    'email': 'bennettkaren@example.net',
    'phone_number': '596-400-2826',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Williamson',
    'Lisa Martin',
    'Samantha Cole',
    'Seth Young',
    'Adam Mullins',
    'Betty Hale DVM',
    'Michael Wheeler',
    'Sherri Finley',
],
    'json': {
    'name': 'Jeremy Wade',
    'address': '02969 Nelson Turnpike\nNew Steven, WV 32352',
},
    'key57066': 'value37648',
    'key3820': 'value1314',
    'key44344': 'value11706',
    'key5525': 'value15845',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Chase Smith',
    'address': '43059 Williams Plains\nDavidhaven, LA 77055',
    'text': 'Action condition I sign north maybe argue. Perform fight other true wear respond film.',
    'email': 'smithmatthew@example.com',
    'phone_number': '(580)604-2934x5091',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Santiago',
    'Brett Morris',
    'Jason Caldwell',
    'Larry Silva',
    'Ronald Lewis',
    'Miss Kimberly Davis',
],
    'json': {
    'name': 'Michael Johnson',
    'address': '15179 Brittany Fords\nLake Ashleyport, CA 77167',
},
    'key8907': 'value7942',
    'key43656': 'value39916',
    'key85799': 'value87167',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Meghan Gallegos',
    'address': 'USNS Baker\nFPO AE 72403',
    'text': 'Dinner gas question full. Suddenly window choose common nice.\nAdministration thank hit dog table item strategy deal. Product as matter everything usually.',
    'email': 'danawebb@example.org',
    'phone_number': '943-593-7089x469',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stacey Crawford',
    'Sarah Howard',
    'Jessica Deleon',
    'Shannon Gomez',
    'Tyler Lee',
    'William Mendoza',
    'Mr. James Henderson',
],
    'json': {
    'name': 'William Craig',
    'address': '1752 Patel Fall Suite 811\nNorth Mary, OK 67779',
},
    'key95250': 'value96961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Jeremy Black',
    'address': '5734 Jay Wall Apt. 448\nHarrismouth, KY 58401',
    'text': 'Return hit cost southern season whatever good spend. Professional the industry product real.\nName clearly provide project. Whose one travel they. Ready key treatment form age early contain.',
    'email': 'ricediana@example.org',
    'phone_number': '872-370-4901',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Emily Wall',
    'Stephanie Anthony',
    'Robin Smith',
    'Sarah Mercado',
],
    'json': {
    'name': 'Brianna Hunter',
    'address': '651 Kiara Oval Apt. 333\nRoberthaven, MA 83530',
},
    'key40900': 'value3764',
    'key50255': 'value64673',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Sandra Webb',
    'address': '1171 Moreno Pines Suite 641\nBryanfurt, NE 03870',
    'text': 'Poor character environmental administration. Fish trip reach there around live trip.',
    'email': 'xrios@example.org',
    'phone_number': '001-218-913-1543x8905',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tonya Griffith',
    'Theresa Terry',
    'James Sullivan',
],
    'json': {
    'name': 'Christopher Davis',
    'address': '1485 Theresa Harbor Apt. 584\nEast Steven, NH 30234',
},
    'key89138': 'value53452',
    'key34999': 'value91291',
    'key74858': 'value94225',
    'key2482': 'value49691',
    'key51055': 'value13027',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Teresa Martin',
    'address': '682 Julie Prairie\nSouth Savannahside, PR 22773',
    'text': 'Money fast option moment nature public organization. Fire despite north law save end morning. Development student against grow.\nRed growth never factor so. Ten personal strong south.',
    'email': 'xwheeler@example.com',
    'phone_number': '878-863-5890',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Smith',
    'Claire Chapman',
],
    'json': {
    'name': 'Daniel Young',
    'address': '7579 Mary Crossroad\nWest Lindafurt, FL 60770',
},
    'key63469': 'value71549',
    'key79201': 'value53178',
    'key16011': 'value30467',
    'key39443': 'value99889',
    'key24275': 'value43462',
    'key76959': 'value76381',
    'key31854': 'value76821',
    'key22916': 'value98530',
    'key49500': 'value11789',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Megan Nelson MD',
    'address': '864 Bryan Roads Suite 446\nCristianport, OH 66110',
    'text': 'Left election lawyer pull.',
    'email': 'brownlisa@example.org',
    'phone_number': '583-457-4032x3075',
    'array_int_dynamic': [
    19933,
],
    'array_varchar_dynamic': [
    'Wendy Johnson',
],
    'json': {
    'name': 'Tiffany Reynolds',
    'address': 'PSC 5472, Box 0621\nAPO AA 27457',
},
    'key71805': 'value18559',
    'key25772': 'value26172',
    'key91934': 'value17773',
    'key89256': 'value92366',
    'key29480': 'value16366',
    'key44077': 'value95336',
    'key63957': 'value34162',
    'key22122': 'value46768',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'David Edwards MD',
    'address': '669 Austin Track\nNorth Stacie, AS 67131',
    'text': 'Debate on use member. Industry couple whole simply best material. Begin important difference case support safe.\nCheck that continue accept agreement home able. Fill my if. Account price investment.',
    'email': 'alvarezjohn@example.com',
    'phone_number': '488-712-5081',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Laura Mcdaniel',
    'Sarah Perez',
    'Micheal Love',
    'Kevin Bishop',
    'Andrew Townsend',
    'David Williams',
],
    'json': {
    'name': 'Jeffrey Mann',
    'address': '2438 Mcguire Grove\nRiverafort, WA 95631',
},
    'key90687': 'value9256',
    'key38831': 'value63324',
    'key74851': 'value39023',
    'key5878': 'value54655',
    'key41256': 'value18594',
    'key76936': 'value84847',
    'key69503': 'value52542',
    'key91258': 'value44817',
    'key17852': 'value91092',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Jonathan Hall',
    'address': '057 Deborah Trafficway Apt. 339\nRomerotown, NE 81372',
    'text': 'News top show available pretty. Part they before will agency similar process. Good against defense.\nSouth try stock year. Think goal car yourself.',
    'email': 'jreed@example.org',
    'phone_number': '504.934.7809',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gail Larson',
    'Joseph Hansen',
    'Larry Stevens',
    'Karen Hernandez',
],
    'json': {
    'name': 'Savannah Murray',
    'address': '523 Price Highway\nAcevedoton, HI 86918',
},
    'key48391': 'value28301',
    'key35545': 'value53072',
    'key53659': 'value7338',
    'key43341': 'value75680',
    'key54256': 'value61614',
    'key78243': 'value58827',
    'key46213': 'value4565',
    'key59723': 'value52208',
    'key50080': 'value7455',
    'key13738': 'value42329',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Joshua Goodman',
    'address': '081 Jon Forest\nNew Taylorbury, AR 16075',
    'text': 'Red majority right police risk grow. Design film that present each method performance major.',
    'email': 'john04@example.net',
    'phone_number': '(927)914-7934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Jones',
    'Jaime Smith',
    'Robert Martin',
    'Derrick Case',
    'Taylor Castro',
    'Christine Pollard',
    'Cheryl Roberts',
    'Donald Perkins',
],
    'json': {
    'name': 'Kyle Moore',
    'address': '8478 Nunez Trail Apt. 837\nPort Marcusshire, VI 79311',
},
    'key46813': 'value91148',
    'key72992': 'value65079',
    'key22681': 'value34834',
    'key2220': 'value74865',
    'key14257': 'value64702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Jason Schroeder',
    'address': '0205 White Way\nTorresfort, PW 43381',
    'text': 'Fast prove education idea American. High challenge many trial.\nSimply role real. And instead senior young mean discover score air.',
    'email': 'kathleendawson@example.com',
    'phone_number': '+1-427-345-0254x53502',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Martin',
    'Jessica Jackson',
    'Gerald Wilson',
    'Ashley Liu DVM',
    'Rachel Walker',
    'Kara Warren',
    'Jeremy Franco',
],
    'json': {
    'name': 'Carl Wolf',
    'address': '0995 Porter Prairie Apt. 168\nEast Clifford, WY 86400',
},
    'key40195': 'value80186',
    'key55498': 'value9716',
    'key22311': 'value99145',
    'key32339': 'value458',
    'key44209': 'value65273',
    'key35237': 'value86474',
    'key78434': 'value76370',
    'key74944': 'value86172',
    'key67096': 'value76605',
    'key15217': 'value73774',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Jeremy Adams',
    'address': '87052 Edwards Landing\nWallaceview, OR 87943',
    'text': 'Until time owner wish. Car list help work technology. Five still create. Start gas like natural while worker read.\nFirm view book huge.',
    'email': 'rhonda43@example.org',
    'phone_number': '(572)347-9482x9978',
    'array_int_dynamic': [
    82924,
],
    'array_varchar_dynamic': [
    'Christopher Moore',
    'Patricia West',
    'Summer Callahan',
    'Melissa Price',
    'Jason Clark',
    'Douglas Armstrong',
    'Katie Riley',
    'Anthony Manning',
    'Justin Alexander',
    'William Mitchell',
],
    'json': {
    'name': 'Lori Jennings',
    'address': '016 Katie Ferry\nEbonystad, ND 46045',
},
    'key28961': 'value61481',
    'key2194': 'value42431',
    'key52974': 'value76947',
    'key48381': 'value92111',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Tracy Bruce',
    'address': '766 Lisa Course Apt. 484\nSouth Jordan, SD 91482',
    'text': 'Compare him very.\nDesign show world include machine pressure. Sometimes successful international industry sister. Almost to into race tonight investment particular.\nWife last religious teacher hair.',
    'email': 'josephwood@example.net',
    'phone_number': '660-404-5818x66497',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Gina Glenn',
    'Melissa Trujillo',
    'Kevin Perez',
    'William Lewis',
],
    'json': {
    'name': 'Dillon Newton',
    'address': '9716 Harper Mountain\nLake Angelaville, KY 17219',
},
    'key83766': 'value37110',
    'key21108': 'value58766',
    'key86608': 'value37167',
    'key65494': 'value39073',
    'key90676': 'value95046',
    'key81497': 'value16868',
    'key93435': 'value27584',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Leslie Miller',
    'address': '60054 Martinez Expressway Suite 659\nJessicafurt, PW 97819',
    'text': 'Line capital bad very result term not. Seat sign board maybe game wall.\nFish name author form. Now few blue realize letter sea middle. Beautiful together left court response.',
    'email': 'trevor59@example.net',
    'phone_number': '376-254-4724',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Johnson',
    'Jeffrey Bradley',
    'Mr. Glenn Fowler',
    'David Howe',
    'Howard Davis',
    'Michelle Lowe',
    'Shelby Floyd',
],
    'json': {
    'name': 'Heather Miller',
    'address': '80203 Elliott Summit\nJohnsonhaven, GA 41746',
},
    'key36194': 'value88276',
    'key66794': 'value55599',
    'key80155': 'value16119',
    'key56385': 'value69933',
    'key81589': 'value40352',
    'key60749': 'value14691',
    'key51490': 'value87405',
    'key66771': 'value31520',
    'key74816': 'value91921',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Kristina Willis',
    'address': '7788 Caleb Trail Suite 539\nGrahamfurt, VI 41386',
    'text': 'Table east hour guess everything person soon. Participant present face campaign American agency. Hot may take national draw long.',
    'email': 'murrayandrea@example.com',
    'phone_number': '001-574-761-1020x56222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Crosby',
    'Clifford Thompson',
    'Shane Brown',
    'Maria Douglas',
    'Adam Hill',
    'Kevin Holmes',
    'Shane Shaw',
    'Amy Rios',
    'Sean Lewis',
],
    'json': {
    'name': 'Patricia Williams',
    'address': '4991 Mack Parkway Suite 391\nPort Vanessatown, AL 91944',
},
    'key27201': 'value50203',
    'key95637': 'value64463',
    'key28505': 'value11551',
    'key50954': 'value21603',
    'key90065': 'value14700',
    'key70890': 'value21774',
    'key89953': 'value5587',
    'key52990': 'value45142',
    'key84815': 'value92218',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Alexander Salas',
    'address': '8767 Brewer Square\nHalltown, MI 02335',
    'text': 'Quickly million character item. Which financial support person future responsibility most police.\nPass still top source free. Attorney almost top health. Range source business.',
    'email': 'kristen19@example.net',
    'phone_number': '800.663.9825x9792',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Thornton',
    'Sarah Cooper',
    'Kevin Roach',
    'Amanda Jackson',
    'Elizabeth Murphy',
    'Melissa Hicks',
    'Andrea Stewart',
],
    'json': {
    'name': 'Gabriel Dixon',
    'address': '85139 Holden Ridge Apt. 889\nJamesstad, PR 25850',
},
    'key88676': 'value50466',
    'key41500': 'value2950',
    'key632': 'value69276',
    'key87943': 'value47673',
    'key1951': 'value34632',
    'key41791': 'value70130',
    'key45866': 'value58438',
    'key2826': 'value13516',
    'key64013': 'value4564',
    'key63415': 'value2322',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Joseph Vasquez',
    'address': '657 Mckinney Loop Apt. 733\nWest Sarahfort, PR 54263',
    'text': 'Yes per admit plant century sing green minute. Cost middle best surface for chair. Night chance sister gas pretty old themselves thus.',
    'email': 'ywillis@example.net',
    'phone_number': '770-650-4340x48014',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Linda Walters',
    'Donna Copeland',
    'Whitney Ball',
    'Kevin Jackson',
    'Ashley Porter',
    'Sandra Meyer',
    'Kayla Clark',
    'Rhonda Lewis',
    'Vincent Singleton',
    'Crystal Miller',
],
    'json': {
    'name': 'Justin Brown',
    'address': '2662 Rhonda Turnpike\nJacquelinetown, HI 93842',
},
    'key24534': 'value24799',
    'key41950': 'value8626',
    'key57641': 'value36771',
    'key75544': 'value94457',
    'key45924': 'value11570',
    'key37401': 'value41857',
    'key42215': 'value65258',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Carl Medina',
    'address': 'Unit 8499 Box 2865\nDPO AA 13912',
    'text': 'Expert audience assume often. About PM here fish these. Book according according. Hour institution measure western drop remain.',
    'email': 'chapmandiane@example.com',
    'phone_number': '(216)435-5761x0491',
    'array_int_dynamic': [
    27703,
],
    'array_varchar_dynamic': [
    'Marc Hunt',
    'Christina Sanchez',
    'Michelle Farrell',
    'Lisa Love',
    'Jorge Stewart',
],
    'json': {
    'name': 'Sharon Evans',
    'address': '6469 Xavier Center Apt. 608\nKellyland, IA 96362',
},
    'key59870': 'value56529',
    'key84707': 'value55823',
    'key68654': 'value40113',
    'key2325': 'value50181',
    'key98476': 'value9271',
    'key69258': 'value93816',
    'key66074': 'value71531',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jennifer York',
    'address': 'USS Webb\nFPO AP 98183',
    'text': 'School both from on good never also week. Power moment information none. Performance their by explain message success heart. Theory heavy we memory doctor answer.',
    'email': 'natalie48@example.net',
    'phone_number': '(912)470-6436x3390',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Carol Woodward',
    'Stephen Smith',
    'Joshua Ortiz',
    'Debra Roach',
    'Mr. Travis Pollard MD',
    'Katherine Elliott',
    'Ann Miller',
    'Brenda Robinson',
    'Kim Mcgee',
],
    'json': {
    'name': 'Jimmy Jones',
    'address': '634 Patrick Forest Suite 940\nJefferyville, CT 71151',
},
    'key43714': 'value3265',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Krista Brown',
    'address': '54525 Cruz Lane Apt. 994\nPort Michaelaton, MH 13034',
    'text': 'Now art road. Special sell civil Mrs. Artist statement relate nothing.\nArtist for focus painting it. Get job heavy anything defense. Order natural risk yeah.',
    'email': 'melissa71@example.com',
    'phone_number': '289.987.4315x303',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Carl Macias',
    'Eric Ayala',
    'Emily Thomas DVM',
    'Erin Keith',
    'Virginia Williams',
    'Dr. Peter Reilly',
    'David Hicks',
    'Jessica Mayer',
    'Melissa Ayala',
    'Paul Ramos',
],
    'json': {
    'name': 'Christopher Trujillo',
    'address': '6663 Adkins Stravenue\nNortonchester, CT 65058',
},
    'key16714': 'value71645',
    'key80619': 'value44107',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Wendy Kelley',
    'address': '871 Edward Trail Suite 141\nSouth Larry, MO 72262',
    'text': 'Knowledge change section try stay machine. Experience product theory eat treatment. Specific market the street participant public lot.',
    'email': 'etaylor@example.org',
    'phone_number': '+1-624-208-5556x023',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Donovan',
    'Sara Johnston',
    'Joshua Diaz',
    'Katherine Andrews',
    'Larry Morales',
    'Tracy Nguyen',
],
    'json': {
    'name': 'Antonio Hall',
    'address': '883 Patricia Knolls Apt. 617\nDavidhaven, OH 50932',
},
    'key60127': 'value34116',
    'key28513': 'value37006',
    'key8658': 'value78508',
    'key14005': 'value74997',
    'key35489': 'value73078',
    'key92254': 'value505',
    'key26931': 'value48069',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Blake Mendez',
    'address': '27618 Rodriguez Mountains Apt. 983\nThomasbury, PR 74994',
    'text': 'Various end parent general speech plant as program. Animal likely second behind himself drive.\nCan tax prevent eight.\nEach sense do week. Prepare phone into.',
    'email': 'james82@example.net',
    'phone_number': '+1-707-650-2941x0126',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Monica King',
    'Matthew Hall',
    'Alexander Lopez',
    'Alexandria Johns',
    'Donald Daniel',
    'Elizabeth Cooper',
    'Jessica Fields',
    'Teresa Decker',
],
    'json': {
    'name': 'April Silva',
    'address': '5238 Jeffery Club Suite 477\nPort Jesseside, GA 04222',
},
    'key61393': 'value23767',
    'key24121': 'value39537',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Lindsey Smith',
    'address': '29319 Greer Turnpike\nWest Christian, NY 05028',
    'text': 'Best reduce election mention prepare. Low play deal maintain situation middle mission statement. Meeting such method other consider behind edge.\nSeveral avoid again.',
    'email': 'jonathanvalencia@example.org',
    'phone_number': '001-722-711-2347',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Olivia Smith',
    'Jamie Hess',
    'Jillian Smith',
],
    'json': {
    'name': 'Heather Pearson',
    'address': '73398 Hernandez Court\nSouth Ericaburgh, ME 93699',
},
    'key57686': 'value77731',
    'key7096': 'value86581',
    'key67814': 'value86518',
    'key71979': 'value83140',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Miss Lisa Graham',
    'address': '375 Cruz Trace\nRogerside, CA 99357',
    'text': 'Bit space order page near. Able smile American cold example above. Value heart easy exist. Late I special nature.',
    'email': 'kbeltran@example.net',
    'phone_number': '821.421.3062x169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Tapia',
    'Adam Burton',
],
    'json': {
    'name': 'Christopher Jones',
    'address': '67870 Gillespie Pines\nAdamhaven, NE 49229',
},
    'key42856': 'value42065',
    'key29352': 'value72783',
    'key19917': 'value644',
    'key11664': 'value9074',
    'key55328': 'value71793',
    'key70210': 'value76846',
    'key68030': 'value23803',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Katie West',
    'address': 'USS Church\nFPO AA 00645',
    'text': 'Less off state. Listen serve then age away anything drop. Last everybody according study.',
    'email': 'nporter@example.net',
    'phone_number': '6832896311',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Douglas',
    'Duane Price',
    'Deanna Ward',
    'Emily Hernandez',
    'Samuel Bautista',
    'Chad Goodwin',
    'Hannah Gray',
    'Patrick Mcdonald',
    'Ashley Turner',
],
    'json': {
    'name': 'Miss Shelby Patterson',
    'address': '9095 Black Neck Suite 697\nPamelaside, MI 80429',
},
    'key99421': 'value60557',
    'key82437': 'value59727',
    'key78256': 'value96682',
    'key64521': 'value64518',
    'key29791': 'value54151',
    'key79921': 'value11970',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Joshua Garrett',
    'address': '70672 Noah Square Apt. 992\nEast Angela, FM 60508',
    'text': 'Always public peace former.\nScience church spend skin.\nBehavior into question production wide message kid. They ask college section address move nor.',
    'email': 'jordan82@example.net',
    'phone_number': '+1-894-762-1685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael King',
    'Melinda Johnson',
],
    'json': {
    'name': 'Gabriela Miller',
    'address': '013 Jessica Hill\nLake Mark, MH 69789',
},
    'key28832': 'value27953',
    'key31569': 'value91171',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Adam Phillips',
    'address': '00919 Hall Plaza\nHuntershire, AL 46038',
    'text': 'Bring science student knowledge conference. Phone event bill rule relate imagine mention believe.\nControl have majority capital mother.',
    'email': 'laurenjohnson@example.org',
    'phone_number': '966-614-5658x820',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Bennett',
    'Jesse Henderson',
    'Sarah Huffman',
    'Emily Jackson',
    'Hannah Kelly',
    'Monica Foster',
    'Emma Harrison',
],
    'json': {
    'name': 'Ana Martin',
    'address': '164 Noah Estate\nGainesfort, CO 71337',
},
    'key37459': 'value18675',
    'key28341': 'value37815',
    'key64321': 'value61767',
    'key72486': 'value53760',
    'key71098': 'value71624',
    'key68025': 'value11732',
    'key15998': 'value26383',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Terry Cain',
    'address': '11946 Mark Mountain\nNorth Paul, WA 68421',
    'text': 'Financial discussion sound indeed once. Later culture yourself arrive section produce.\nImportant use send garden room send. Both first might western. Nothing red movie executive law but.',
    'email': 'ojones@example.net',
    'phone_number': '912.796.6923x72945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Justin Castillo',
    'Dawn Young',
    'Eric Gonzalez',
    'Brian Johnson',
    'Noah Hernandez',
],
    'json': {
    'name': 'Lauren Stafford',
    'address': '3210 Ethan Lodge Suite 963\nFarrellview, DE 96064',
},
    'key76757': 'value8522',
    'key82581': 'value37776',
    'key13429': 'value74284',
    'key48196': 'value3115',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Brianna Ware',
    'address': '18164 Edward Views\nObrienfort, CO 45987',
    'text': 'Certain dark program ball million every among. Discover set deep appear keep scientist. Let eat positive tax page.',
    'email': 'vperez@example.net',
    'phone_number': '4288034354',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Harold Harris',
    'Patricia Vincent',
    'Ashley White',
    'Cynthia Powell',
    'Jessica Duncan',
    'Karen Perez',
    'Ian Drake',
    'Cameron Castro',
    'John Jenkins',
    'Sabrina Bauer',
],
    'json': {
    'name': 'Dana Vega',
    'address': '27281 Smith Viaduct\nMichellebury, MO 03644',
},
    'key65380': 'value72309',
    'key7667': 'value82191',
    'key57233': 'value42718',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Jennifer Hart',
    'address': '338 Jessica Greens\nStephensville, CA 49523',
    'text': 'Likely week building write member push. Mean than rate respond American during.\nFall have her watch. Poor develop support chance place maybe mention.\nWay across foot change continue say mother range.',
    'email': 'ingramsamuel@example.com',
    'phone_number': '2307942216',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Travis Howell',
    'Sharon Savage',
    'Dr. Donald May MD',
    'Marc Henson',
    'Rachel Gibbs',
    'Brian Dean',
    'Bradley Murillo',
    'Elizabeth Bright',
    'Kevin Gray',
    'Caleb Johnson',
],
    'json': {
    'name': 'Nicholas Johnson',
    'address': '391 Robert Islands\nNew Kennethshire, HI 62209',
},
    'key36543': 'value34968',
    'key77696': 'value3269',
    'key74810': 'value94821',
    'key40943': 'value2096',
    'key26578': 'value11070',
    'key98409': 'value73736',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'John Cross',
    'address': '324 Adam Common Apt. 799\nJimenezbury, NH 81704',
    'text': 'Response scientist part fly quality wish me. Full three media close entire system. Challenge professor police race leader.',
    'email': 'grogers@example.net',
    'phone_number': '759.781.2306x6742',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Paul Coleman',
    'Brandon Silva',
    'Brenda Norton',
    'Danielle James',
    'Danny Day',
    'Matthew Serrano',
    'Emily Brown',
    'Ian Ward',
    'Julie James',
],
    'json': {
    'name': 'Bobby Sanders',
    'address': '508 Hester Shoals Apt. 027\nWilliambury, MN 01099',
},
    'key48801': 'value37766',
    'key70127': 'value17685',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Audrey Atkins',
    'address': '3804 Wilkerson Harbors Suite 759\nBriannachester, CT 60058',
    'text': 'Measure quickly reduce wrong. Fear never trouble firm. Its true book upon.\nAs today never present reason decade. Either onto risk best.',
    'email': 'griffincheryl@example.net',
    'phone_number': '370-465-0651x29451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Riley Jones',
    'Donald Nguyen',
    'Beth Brown',
    'Lawrence Smith',
    'Brendan Ward',
    'Shelly Miller',
],
    'json': {
    'name': 'Anthony Sullivan',
    'address': '13949 Brian Street\nHoodshire, NY 95575',
},
    'key63794': 'value49974',
    'key83758': 'value56396',
    'key9207': 'value37489',
    'key47095': 'value24618',
    'key16477': 'value18481',
    'key15903': 'value57104',
    'key43193': 'value42330',
    'key61309': 'value65699',
    'key72493': 'value3338',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Jamie Johnson',
    'address': '9524 Rodriguez Trail\nPort Williamside, GU 02456',
    'text': 'Baby far control subject certain would eye. Art people put by.\nJoin card international sometimes. Western follow management remember political officer.',
    'email': 'christinaclark@example.net',
    'phone_number': '9954650920',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Richard Davis',
    'Mr. Charles Allen',
    'Teresa Cook',
    'Savannah Harrell',
    'Jodi White',
    'Jennifer Rogers',
    'Jerry Johnson',
],
    'json': {
    'name': 'John Wright DVM',
    'address': '149 Roberto Gardens\nFritzberg, ND 69693',
},
    'key26794': 'value49744',
    'key25168': 'value93547',
    'key45368': 'value78814',
    'key81802': 'value93549',
    'key36028': 'value85563',
    'key78544': 'value11310',
    'key19058': 'value74927',
    'key83577': 'value53587',
    'key1426': 'value63458',
    'key53519': 'value68305',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'John Swanson',
    'address': '0774 Carey Plaza\nPort Meganhaven, IN 99624',
    'text': 'Adult blue less nature item above figure benefit. Put anything fund situation never ground.',
    'email': 'schultztheodore@example.com',
    'phone_number': '001-854-238-1939x89917',
    'array_int_dynamic': [
    75604,
],
    'array_varchar_dynamic': [
    'Matthew Turner',
    'Fred Garcia',
    'Kevin Murphy',
    'Sandra Stephens',
    'Wendy Hall',
    'Andrew Green',
    'Kristine Hill',
    'Kevin Fowler',
    'Michael Smith',
],
    'json': {
    'name': 'Rebecca Perry',
    'address': '6625 Shelly Mountains Apt. 877\nKarenview, UT 77628',
},
    'key82284': 'value51319',
    'key7899': 'value36553',
    'key31938': 'value66163',
    'key34360': 'value82266',
    'key51697': 'value46205',
    'key96337': 'value58303',
    'key81929': 'value69955',
    'key48546': 'value75425',
    'key98560': 'value64070',
    'key74208': 'value86429',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Katie Stephens',
    'address': '57475 Timothy Parks\nDaniellefurt, CT 72325',
    'text': 'Their sister professional financial food. Democratic win begin whatever. Idea medical see. Whose admit door.',
    'email': 'buckleystacey@example.com',
    'phone_number': '+1-336-818-1226x1915',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Mercer',
    'Tracy Lynn',
    'Joseph Ellis',
    'Charles Calderon',
],
    'json': {
    'name': 'Dawn Byrd',
    'address': '1235 Bullock Turnpike\nLake Lisa, NC 65568',
},
    'key14568': 'value37575',
    'key15564': 'value54969',
    'key36590': 'value96985',
    'key76401': 'value84963',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Bethany Thomas',
    'address': '783 Peck Burg\nLake Jasonhaven, WY 30982',
    'text': 'Now interview record ground nothing meeting. Star bank country letter. Certainly daughter phone system history town occur.\nLine it pass any. Source including budget the until person idea.',
    'email': 'leslienguyen@example.org',
    'phone_number': '001-714-956-2968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Novak',
    'Terry Riley',
    'Blake Taylor',
    'Madison Morrison',
    'Justin Lopez',
    'Alicia Wilcox',
    'Alyssa Cole',
],
    'json': {
    'name': 'Scott Wallace',
    'address': '964 Laurie Divide\nWest Kaylaborough, AK 79635',
},
    'key88747': 'value91418',
    'key34750': 'value6472',
    'key86558': 'value16669',
    'key33390': 'value64306',
    'key67849': 'value29665',
    'key73295': 'value62122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jaime Mcmahon',
    'address': '5997 Mitchell Valley Apt. 120\nRickymouth, MP 66624',
    'text': 'Say result recent action. The name avoid water minute company.\nInformation herself positive radio. Song near service trip. Paper place situation return stay establish affect.',
    'email': 'frazierashley@example.org',
    'phone_number': '+1-367-628-0544x00239',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Paul Leonard',
    'Nathaniel Mckinney',
    'Richard Chang',
    'Russell Thomas',
    'Olivia Mejia',
    'Kayla Morales',
    'Monica Collins',
    'Lawrence Thomas',
],
    'json': {
    'name': 'Chelsea Jacobson',
    'address': '6231 Duarte Well\nSouth Joseph, RI 62104',
},
    'key82368': 'value1224',
    'key56156': 'value47789',
    'key95626': 'value19906',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Lance Sharp',
    'address': '163 Jason Place Apt. 029\nTammytown, LA 60234',
    'text': 'Mouth film we turn account financial all. Talk general since rather line west operation.\nUse ready civil prepare. Direction somebody issue practice market.\nBetter usually kitchen brother us hope.',
    'email': 'sshaw@example.org',
    'phone_number': '299-412-1919x253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kyle White',
    'James Anderson',
    'Matthew Butler',
    'Jeffrey Mcclain',
    'Billy Hodge',
    'Jessica Newman',
    'Kevin Hernandez',
    'Julie Ellison',
    'Jonathan Gonzalez',
    'Samantha Martin',
],
    'json': {
    'name': 'Victoria Page',
    'address': '4229 Danielle Common Suite 487\nNew Alexandermouth, KS 04624',
},
    'key55403': 'value36593',
    'key63756': 'value95274',
    'key33323': 'value57760',
    'key35272': 'value2952',
    'key89988': 'value75648',
    'key13492': 'value98553',
    'key86627': 'value6947',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Lacey Hernandez',
    'address': '8611 Steven Underpass\nKrystalborough, FM 41719',
    'text': 'General behavior meeting per by. Girl card today certain. Save next direction peace order.\nGuy hospital determine. Possible be edge opportunity. Laugh factor court thought name financial.',
    'email': 'gwinters@example.org',
    'phone_number': '+1-385-325-7090x666',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Larry Fletcher',
    'Jasmin Morgan',
    'Nicole Roy',
    'Kimberly Shields',
    'Curtis Garcia',
],
    'json': {
    'name': 'Daniel Smith',
    'address': '0069 Terri Locks\nSouth Courtney, VT 68837',
},
    'key13200': 'value81159',
    'key63577': 'value74527',
    'key83373': 'value588',
    'key64366': 'value2390',
    'key14863': 'value58900',
    'key53398': 'value76700',
    'key20039': 'value1293',
    'key25625': 'value66980',
    'key40838': 'value61564',
    'key4193': 'value81784',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'George Cunningham',
    'address': '790 Flynn Mount\nKevinland, KY 90314',
    'text': 'Reality already few else phone technology check. Player include glass hand huge beat thus. Poor about reflect idea benefit.',
    'email': 'abrown@example.net',
    'phone_number': '728.553.1821',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ann Sanchez',
    'Frank Hamilton',
    'Adrian Walton',
    'Misty Kelly',
],
    'json': {
    'name': 'Rebecca Johnson',
    'address': '2740 James Camp Suite 666\nEast Karenview, IL 84445',
},
    'key51523': 'value92578',
    'key704': 'value30940',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'George Sharp',
    'address': '4651 Andrew Divide Apt. 282\nBrandimouth, PA 88207',
    'text': 'Part despite figure significant act test east. Career page this amount stage piece. Work five significant imagine trade. Clear wall example difference.',
    'email': 'joshua30@example.com',
    'phone_number': '(713)246-8827',
    'array_int_dynamic': [
    1079,
],
    'array_varchar_dynamic': [
    'John Barton',
    'Gregory Hall',
    'Meghan Phillips',
    'Jessica Maldonado',
    'Peter Vasquez',
],
    'json': {
    'name': 'Leah Stephens',
    'address': '9216 Erin Shore\nOdommouth, AK 35225',
},
    'key50507': 'value90849',
    'key72688': 'value8027',
    'key43242': 'value90878',
    'key84703': 'value2598',
    'key17623': 'value9641',
    'key591': 'value47724',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Garrett Johnson',
    'address': '02919 Victor Knoll Suite 574\nMcgeemouth, MO 37920',
    'text': 'Heart could glass mission open. Can seat fish state culture.\nWithout near Mrs us often. Window total church.',
    'email': 'igordon@example.net',
    'phone_number': '(451)618-4969x5847',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Bailey',
    'Janet Thompson',
    'Jessica Sullivan',
    'Mary Landry',
    'Debra Byrd',
    'Anna Clark',
    'Sean Banks',
    'Jeffrey Maldonado',
    'Nathan Manning IV',
    'Shannon Salinas',
],
    'json': {
    'name': 'Matthew Stein',
    'address': '81985 Roman Crest Suite 919\nWest Stacy, GU 58496',
},
    'key26279': 'value41155',
    'key5484': 'value96559',
    'key3018': 'value40931',
    'key65023': 'value48321',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Jeremy Nguyen',
    'address': '5200 Wilson Prairie\nMichellefurt, OK 37318',
    'text': 'Real fast bill. Detail bring impact she week significant apply.',
    'email': 'stevenbrown@example.org',
    'phone_number': '+1-393-963-5833x349',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'James Patterson',
    'Brenda Mora',
    'Brenda Robles',
    'Pamela Reed',
    'Sharon Riley',
    'Kurt Young',
    'Courtney Lozano',
    'Emily Guerra',
    'William Chase',
],
    'json': {
    'name': 'Heather English',
    'address': '1755 Rice Passage\nSouth Matthew, TX 62749',
},
    'key62351': 'value32315',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Kelly Branch',
    'address': '074 Daniel Island Apt. 231\nWest Steventon, WY 64557',
    'text': 'Now stuff third class what eye foot. Late mean less nearly pressure fast important set. Moment share available force my professor.',
    'email': 'christopherpayne@example.com',
    'phone_number': '457.728.9945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christina Ward',
    'Stephen Phelps',
    'Craig Reyes',
    'Justin Castro',
    'Rachel Peters',
    'Carolyn Mills',
    'Ralph Rogers',
    'Travis Cabrera',
],
    'json': {
    'name': 'Karen Ortiz',
    'address': '989 Alvarez Drives\nMartinton, CO 30220',
},
    'key4924': 'value8126',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Julie Bruce',
    'address': '89823 Torres Burgs Apt. 462\nAnnaton, RI 92872',
    'text': 'Member information son former hour clear TV. Executive business focus tonight. Memory peace card society section mind.\nReach my source participant. Should those yet little.',
    'email': 'mcclureana@example.org',
    'phone_number': '001-224-410-9462x38989',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Donald Mcdonald',
    'Kristina Weaver',
    'James Chavez',
],
    'json': {
    'name': 'Katelyn Mendez',
    'address': '087 Robert Brooks Apt. 211\nMichaelbury, RI 02787',
},
    'key96393': 'value25156',
    'key20351': 'value39556',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Robert West',
    'address': '8203 Lindsay Land Suite 901\nJohnburgh, NC 32038',
    'text': 'White short world space into forget. Until power anyone deep road series enjoy.\nPolitical people speak rate. Or information try.',
    'email': 'stephenfuller@example.net',
    'phone_number': '001-856-848-0329x78511',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Miranda Mcgee',
    'Jason Morris',
    'Danielle Ramirez',
    'Mary French',
    'Brenda Fox',
    'Steven Johnson',
    'Kevin Miller',
    'Joseph Wise',
    'Michael Floyd',
    'David Jackson',
],
    'json': {
    'name': 'Chelsey Vasquez DVM',
    'address': 'PSC 5380, Box 0479\nAPO AA 80242',
},
    'key26688': 'value78188',
    'key24065': 'value44024',
    'key91839': 'value11472',
    'key71336': 'value42551',
    'key15639': 'value84714',
    'key41290': 'value66093',
    'key21234': 'value23315',
    'key11438': 'value79394',
    'key98135': 'value83434',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Tara Sosa',
    'address': 'Unit 3552 Box 7003\nDPO AP 23556',
    'text': 'Beat same bank body. Bit deep own main special before. Heart join management card recognize understand.\nOne miss so partner billion mean western. Nice president clearly accept.',
    'email': 'deanna82@example.org',
    'phone_number': '698.581.8829x8049',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Danny Burton',
    'William Joseph',
    'Brian Chambers',
    'Samuel David',
    'Danielle Russo',
    'Kimberly Schroeder',
    'Tina King',
],
    'json': {
    'name': 'Elizabeth Riley',
    'address': '1954 Archer Common Suite 840\nPort Johnhaven, AK 79827',
},
    'key46191': 'value97080',
    'key28369': 'value80883',
    'key3142': 'value17982',
    'key93101': 'value50937',
    'key89300': 'value2912',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Roy Ramirez',
    'address': 'PSC 9092, Box 3209\nAPO AP 90088',
    'text': 'Cause leader family once. Arm dream song way three almost.\nAcross form travel. Public game exist public throughout ask personal. Up rise Republican central although often all.',
    'email': 'kevinjohnson@example.com',
    'phone_number': '569.746.9975x2810',
    'array_int_dynamic': [
    18066,
],
    'array_varchar_dynamic': [
    'Edward Miranda',
    'Angela Love',
    'Steve Miller',
    'Maurice Zavala',
    'Keith Harvey',
    'Kent Roth',
    'Ronald Stewart',
    'Bobby Turner',
    'Kenneth Martinez',
],
    'json': {
    'name': 'Tyler King',
    'address': '652 James Row\nSouth Danielmouth, SC 18567',
},
    'key87541': 'value74488',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jose Hernandez',
    'address': '942 Brown Cliff\nBrianland, VA 01415',
    'text': 'Certainly represent about ahead black ready. Realize song pretty local. Build send on miss grow.\nManage worry country team station girl help.',
    'email': 'mcbridesabrina@example.com',
    'phone_number': '215-753-4994',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dana Wright',
    'John Rodriguez',
],
    'json': {
    'name': 'Justin Aguilar',
    'address': '5007 Lopez Cliff Suite 444\nBennettmouth, OR 06208',
},
    'key8288': 'value5668',
    'key68248': 'value45959',
    'key8269': 'value31499',
    'key96029': 'value66811',
    'key90569': 'value79656',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Randall Mayer',
    'address': '6706 Bernard Streets\nDaniellefurt, TN 71212',
    'text': 'Five news truth evening look less sport. Hold research on task. Apply challenge necessary media move heart.\nPolitical performance other. Until policy economy.',
    'email': 'perkinsbrian@example.net',
    'phone_number': '4069910413',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Wheeler',
    'Tamara Knapp',
    'Laura Roth',
    'Heather Beltran',
    'Kevin Munoz',
    'Melissa Bennett',
    'Wendy Jones',
    'Frank Smith',
    'Ryan Newton',
],
    'json': {
    'name': 'Heather Gonzalez',
    'address': '01799 Johnson Brooks\nSouth Christian, TX 98416',
},
    'key61675': 'value22687',
    'key41046': 'value5538',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Jessica Clarke',
    'address': '27118 Grimes Crossroad\nNorth Ryanborough, NJ 22321',
    'text': 'Ten financial since. Loss appear life past pressure feeling fear exactly.',
    'email': 'clawson@example.com',
    'phone_number': '886-357-4374',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robert White',
    'Jessica Stewart',
    'Ann Schroeder',
],
    'json': {
    'name': 'Richard Mills',
    'address': '0050 Leslie Ridges\nSouth Mark, TX 87319',
},
    'key83267': 'value2892',
    'key12137': 'value50002',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Jonathan Jordan',
    'address': '3691 Kelly Wall Apt. 357\nNorth Shelia, AK 68147',
    'text': 'Situation service seat prepare shoulder require radio trip.\nWonder want without rather. Sign guess away two decide management ahead picture. Point month writer each.',
    'email': 'timothyturner@example.com',
    'phone_number': '585-309-0983x680',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Devin Wood',
    'Allison Santiago',
    'Natasha Stokes',
    'William Little',
    'Kelly Johnson',
    'Kelsey Wheeler',
    'Sarah Erickson',
],
    'json': {
    'name': 'Joshua Zimmerman',
    'address': '62276 Pearson Landing Apt. 817\nStanleyview, VT 95556',
},
    'key60871': 'value12087',
    'key42672': 'value39334',
    'key5125': 'value97869',
    'key18286': 'value56539',
    'key75853': 'value92769',
    'key91920': 'value1247',
    'key73455': 'value12743',
    'key57585': 'value84330',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'James Wells',
    'address': '94125 Krystal Way\nWilliamsstad, MN 25811',
    'text': 'Yet ten detail effort. Professor weight ask east challenge reason exactly.\nHear position design social region life. Natural west suddenly happy. Within some per.',
    'email': 'michelle23@example.org',
    'phone_number': '(778)595-0809',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amber Marquez',
    'Kim Novak',
    'David Miller',
    'Megan Gonzalez',
],
    'json': {
    'name': 'Justin Johnson',
    'address': 'USNS Herrera\nFPO AE 08364',
},
    'key26262': 'value26211',
    'key27593': 'value46813',
    'key73199': 'value82014',
    'key88489': 'value32868',
    'key79772': 'value41251',
    'key98884': 'value33909',
    'key30678': 'value25875',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Meghan Stone',
    'address': '00725 Diaz View\nNew Jasonmouth, VI 82244',
    'text': 'Side this try present glass.\nScientist just our population. Strategy focus hold.\nCompare nor also support reflect item. Movement paper resource friend campaign toward detail.',
    'email': 'rileykayla@example.net',
    'phone_number': '001-301-418-4868x7731',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'John Reynolds',
    'James Wade',
    'Vincent Shaw',
    'Lisa Thompson',
    'Anthony Solomon',
],
    'json': {
    'name': 'Linda Burke',
    'address': '71642 Chase Loop Apt. 730\nNew Toddmouth, MP 55027',
},
    'key83219': 'value73012',
    'key43899': 'value64312',
    'key46278': 'value70214',
    'key33783': 'value31286',
    'key46118': 'value38281',
    'key38426': 'value90254',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Nathan Perry',
    'address': '098 Daniel Gateway\nPort Melindastad, VT 47742',
    'text': 'Important movement will center. Quite environment build receive sport ten side. By maybe office church.',
    'email': 'sboone@example.com',
    'phone_number': '+1-306-500-7617x2092',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Johnson',
    'Ashley Sanchez',
    'Sylvia Ramsey',
    'Joseph Chavez',
    'Susan Bernard',
    'Scott Rodriguez',
    'Christopher Davidson',
    'Ian Lopez',
    'Brenda Green',
    'Austin Harris',
],
    'json': {
    'name': 'Cynthia Brown',
    'address': 'PSC 8823, Box 4766\nAPO AE 43197',
},
    'key77256': 'value59028',
    'key91402': 'value85723',
    'key1384': 'value89773',
    'key10465': 'value54399',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Antonio Taylor',
    'address': '8678 Christopher Forest\nPort Christinabury, IL 22178',
    'text': 'Participant common plan test forget. List serious hope have shake the choice. Investment story particularly budget.\nAgo your but east write shake often carry. Wish international so wear girl.',
    'email': 'wrobbins@example.net',
    'phone_number': '(731)970-7183x0596',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Williams',
    'Henry Alvarado',
    'Devin Kelly',
    'Kevin Long',
],
    'json': {
    'name': 'Kristin Brown',
    'address': '1618 Willis Center Apt. 761\nPort Pamelaville, PR 63549',
},
    'key7040': 'value26755',
    'key88656': 'value52680',
    'key38726': 'value6317',
    'key26146': 'value38591',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Jennifer Wright',
    'address': 'USNV May\nFPO AP 19680',
    'text': 'Level bank school education grow. State me form inside question exist.\nMake book leave budget building radio none. Make modern life best over couple.',
    'email': 'djohnson@example.org',
    'phone_number': '001-345-765-4386x27203',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jonathon Ramirez',
    'Melissa Morris',
    'Melanie Davila',
    'Angela Barber',
    'Samantha Golden',
    'Lisa Brady',
],
    'json': {
    'name': 'Kyle Harris',
    'address': '54170 Charles Shoals Suite 729\nPort Leah, AS 86662',
},
    'key60313': 'value29797',
    'key88335': 'value83676',
    'key33438': 'value73869',
    'key91718': 'value72804',
    'key85293': 'value81027',
    'key77832': 'value69368',
    'key57954': 'value81809',
    'key25964': 'value95875',
    'key54564': 'value97384',
    'key69925': 'value56314',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Jillian Rangel',
    'address': '190 Conner Lakes\nChristopherport, AZ 10313',
    'text': 'Free hotel without. Possible heavy idea listen.',
    'email': 'lopezjennifer@example.org',
    'phone_number': '319-972-1411x428',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Lopez',
    'Brenda Frank',
],
    'json': {
    'name': 'Paul Bailey',
    'address': '4085 Travis Ridges Suite 306\nWademouth, PR 72804',
},
    'key49520': 'value45123',
    'key82876': 'value96081',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Bryan Andrews',
    'address': '0700 Sandra Haven\nCunninghamborough, NH 91864',
    'text': 'Yourself low instead weight help leader free. Low similar major. Idea wish help story simply involve.',
    'email': 'christyyates@example.org',
    'phone_number': '(206)990-8478',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Diana Jones',
    'Taylor Drake',
],
    'json': {
    'name': 'Nathaniel Jordan',
    'address': '480 Timothy Groves Suite 498\nEast Heathertown, MP 04511',
},
    'key83205': 'value30714',
    'key62010': 'value90179',
    'key51161': 'value29892',
    'key12825': 'value87827',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Cassidy Baker',
    'address': '37380 Burke Viaduct Suite 985\nJeremyborough, OH 24241',
    'text': 'Son figure hundred company. Help western forget serve key. Day when family radio create guess would.\nAccording specific great commercial.',
    'email': 'dholmes@example.org',
    'phone_number': '463-929-9606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Black',
    'Charles Taylor',
    'Jesse Jackson',
    'Jason Perry',
    'Christine Norton',
    'Dr. Brett Arnold III',
    'Sara Frazier',
    'Mrs. Crystal Tucker',
    'Scott Pena',
],
    'json': {
    'name': 'Paula Ray',
    'address': '31498 Blevins Drive\nSouth Karen, NY 35823',
},
    'key13614': 'value21390',
    'key80602': 'value85866',
    'key87314': 'value69927',
    'key1778': 'value63382',
    'key96461': 'value24765',
    'key93888': 'value95010',
    'key87023': 'value9369',
    'key971': 'value64297',
    'key76973': 'value87890',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Troy Anderson',
    'address': '901 Kathy Inlet\nPort Taylorshire, WA 88283',
    'text': 'Idea fill someone chance. Establish civil indicate drive. Heavy treatment sea meeting ok international.',
    'email': 'nguyenjason@example.net',
    'phone_number': '5528329919',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amber Gomez DDS',
    'Ethan Rodriguez',
    'Terry Figueroa',
    'Mary Stewart',
    'Alan Conrad',
    'Charles Maddox',
    'Nicholas Rodriguez',
],
    'json': {
    'name': 'Alyssa Brown',
    'address': '70401 Shannon Ridge Apt. 108\nJosephtown, ID 34893',
},
    'key81778': 'value28865',
    'key53572': 'value18186',
    'key11753': 'value81881',
    'key70371': 'value88516',
    'key80413': 'value44877',
    'key60841': 'value38666',
    'key97581': 'value83653',
    'key50192': 'value52126',
    'key76234': 'value3172',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Cory Roach',
    'address': '01347 Ashley Drive\nCruzstad, OR 28492',
    'text': 'Education red foreign church. Drive suffer either several.\nItself explain word spring kind leave sort. Quite read wife. Finally situation improve left.',
    'email': 'whitepamela@example.com',
    'phone_number': '427-414-9159x280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Reyes',
    'Brian Foster',
    'Amber Stewart',
    'Amy Wade',
    'Paul Tran',
    'Kelly Pham',
    'Mckenzie Robinson',
    'Emily Richards',
    'Mary Armstrong',
],
    'json': {
    'name': 'Kristy Yu',
    'address': '6383 Green Green Suite 509\nGutierrezshire, AL 90406',
},
    'key9257': 'value90740',
    'key69851': 'value25146',
    'key631': 'value99937',
    'key10948': 'value21248',
    'key2950': 'value54100',
    'key43651': 'value84230',
    'key70298': 'value76145',
    'key1179': 'value4792',
    'key83511': 'value93537',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'James Steele',
    'address': '202 Walton Rapid\nJordanview, NC 43009',
    'text': 'Opportunity bank give should majority market surface. Attorney month professional fish although. On effort must suggest else.\nSmall mother detail face data draw. Mention wrong wonder somebody never.',
    'email': 'tina98@example.org',
    'phone_number': '+1-873-662-3624x9629',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Peter Villarreal',
    'Jennifer Green',
],
    'json': {
    'name': 'William Hall',
    'address': '37006 Miller Fork\nSouth Carolineton, AS 24647',
},
    'key47326': 'value53205',
    'key13637': 'value77741',
    'key51632': 'value87317',
    'key53456': 'value5138',
    'key61096': 'value66802',
    'key52945': 'value51544',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Sarah Duran',
    'address': '04899 Margaret Dam Suite 741\nSinghmouth, NC 69797',
    'text': 'Region bag sense free. World skill any order also tough around.\nNearly can condition politics.\nSome note site subject. Anyone cup trial environmental down four.',
    'email': 'emccall@example.org',
    'phone_number': '949.891.0109x3988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Jordan',
    'Christina Meadows',
    'Tina Smith',
    'Colin Fernandez',
    'Terri Lopez',
    'Richard Jimenez',
    'Katherine Moss',
],
    'json': {
    'name': 'Steven Mitchell',
    'address': 'Unit 3581 Box 6030\nDPO AA 65888',
},
    'key51516': 'value82098',
    'key15263': 'value51797',
    'key59933': 'value9953',
    'key53715': 'value70751',
    'key57459': 'value78762',
    'key95671': 'value3312',
    'key93582': 'value99825',
    'key4089': 'value35066',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Isaiah Flores',
    'address': '8740 Trevor Drive Apt. 151\nCarlsonside, IN 86724',
    'text': 'Environment know pass family know stay however. Little economy expect where.\nResult of move response him agency example American. Let memory the worry road education court.',
    'email': 'adambarrera@example.org',
    'phone_number': '001-803-747-5672',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Riley',
    'Sara Murphy',
    'Miss Jacqueline Jones DDS',
    'Anthony Greene',
    'David White',
    'Joseph Norris',
    'James Mayer',
],
    'json': {
    'name': 'Heidi Thompson',
    'address': '83914 Kari Loop\nAmyville, DE 60710',
},
    'key41327': 'value30298',
    'key55184': 'value83767',
    'key36981': 'value8293',
    'key55293': 'value65706',
    'key81774': 'value450',
    'key89029': 'value29677',
    'key11062': 'value90469',
    'key53611': 'value26771',
    'key86157': 'value28804',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Marcus Wood',
    'address': '67112 April Road Suite 732\nLake Jason, HI 62596',
    'text': 'Eight however family executive story start risk. Economic forward response great house.\nStuff simply few heavy energy. Enter join environment challenge nature girl hundred.',
    'email': 'gyoung@example.org',
    'phone_number': '(798)629-5673x75097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jake Gonzalez',
    'Andrea Owens',
],
    'json': {
    'name': 'Jasmine Blankenship MD',
    'address': 'PSC 5737, Box 4989\nAPO AE 65480',
},
    'key1065': 'value20074',
    'key54469': 'value57068',
    'key6574': 'value11860',
    'key6922': 'value36320',
    'key78450': 'value60096',
    'key16746': 'value86750',
    'key30892': 'value71545',
    'key27828': 'value11774',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Kathleen Brady',
    'address': '617 Reginald Glens Apt. 560\nLake Terriport, TX 02678',
    'text': 'Community job must wall. Foreign computer happy near light. Together final here either west onto.\nFire herself network around cover wife. Could lose water.\nCapital safe mission note.',
    'email': 'scott56@example.org',
    'phone_number': '+1-708-501-0923x96060',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Graham',
    'Mary Perez',
    'Bryan Wood',
    'James Owens',
    'Andrew Wolfe',
    'James Wilson',
    'David Hall',
    'Jacob Smith',
    'Richard Perez',
],
    'json': {
    'name': 'Jessica Sanders',
    'address': '359 Colleen Forge\nTrevorton, LA 43485',
},
    'key96413': 'value97914',
    'key48288': 'value89774',
    'key44764': 'value91323',
    'key5966': 'value21167',
    'key28930': 'value62287',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Jay Pierce',
    'address': '9450 Johnson Stravenue\nSouth Matthewfurt, CO 93257',
    'text': 'Deep game eat final consumer. Number rest give threat open. Office some hard computer response. Page just soldier expert whose.\nStop quality rest open become lot get. Tv occur address story skin.',
    'email': 'alyssahart@example.com',
    'phone_number': '+1-407-449-3584x9990',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Taylor',
    'David Watts',
],
    'json': {
    'name': 'Margaret Kelly',
    'address': '9089 Rogers Isle Apt. 050\nSouth Joshuamouth, AK 30178',
},
    'key88561': 'value86851',
    'key14030': 'value3404',
    'key79811': 'value51351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Mr. Troy Bernard',
    'address': '847 Tyler Neck\nEdwardsmouth, PR 23544',
    'text': 'Practice forward ahead subject Mrs. Operation reduce trouble follow form indicate piece collection.',
    'email': 'tabitha56@example.org',
    'phone_number': '(957)972-0447x06019',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christina Petersen',
    'Cathy Roman',
    'Patrick Warner',
    'Justin Chan',
    'Carla Henry',
],
    'json': {
    'name': 'Matthew Rios',
    'address': '15367 David Pike\nKimberlyside, GA 52522',
},
    'key35616': 'value12506',
    'key1666': 'value98342',
    'key92234': 'value17842',
    'key32898': 'value11476',
    'key14298': 'value74904',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Timothy Shepherd',
    'address': '085 Cooper Junction Apt. 493\nLouisville, KY 60415',
    'text': 'Man sure only key everybody.\nHerself experience cover enter theory for. Your energy manager dark rock. Meeting likely member hard hand Mrs.',
    'email': 'eduardocopeland@example.org',
    'phone_number': '+1-848-964-8313x46303',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brian Johnson',
    'Ms. Megan Hawkins DDS',
    'Tyler Murray',
],
    'json': {
    'name': 'Dana Washington',
    'address': '4793 Thomas Roads Suite 831\nEast April, MI 43595',
},
    'key7979': 'value63677',
    'key34297': 'value14651',
    'key21096': 'value40224',
    'key9984': 'value1812',
    'key77791': 'value36810',
    'key17001': 'value92199',
    'key86679': 'value9548',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Darrell Fitzpatrick',
    'address': '32323 Rice Lakes\nCaitlinhaven, DE 12027',
    'text': 'Work focus green picture figure position. Analysis community start better various piece board.\nBoth economic truth central. Minute yourself sell various. Eye decade doctor hotel entire green.',
    'email': 'kevinwilson@example.org',
    'phone_number': '685.825.6338x8910',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Blake Smith',
    'Lynn Bryant',
    'Amanda Garcia',
    'Erica Love',
    'Frank Robinson',
    'Robin Le',
    'Kristin Robinson MD',
    'Kristy Turner',
    'Traci Hood',
],
    'json': {
    'name': 'David Howell',
    'address': '803 Michelle Prairie Apt. 546\nWheelerborough, PA 13169',
},
    'key99590': 'value13933',
    'key82471': 'value20220',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Mathew Roberts',
    'address': '70746 Kristy Centers Apt. 602\nSmithton, AS 56635',
    'text': 'Five local many especially half.\nLetter nature might one. Director officer prepare before direction black. Thus step property allow accept.',
    'email': 'xthompson@example.com',
    'phone_number': '958-298-9020x50435',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steven Phelps',
    'Maria Fisher',
    'Craig Vasquez',
    'Haley Ferguson',
],
    'json': {
    'name': 'Leslie Hanson',
    'address': '896 Brian Gardens Apt. 863\nCatherinemouth, ME 94508',
},
    'key42014': 'value18489',
    'key96441': 'value94750',
    'key53575': 'value59121',
    'key67933': 'value45578',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Mark Rosales',
    'address': '92436 Walker Pine\nWest Rachel, MO 31186',
    'text': 'My note me might value put. Necessary ground significant race only worker home. Current attorney away small subject push.\nDescribe billion military activity. Various receive indicate new top effect.',
    'email': 'deborahhuff@example.net',
    'phone_number': '001-989-212-0522',
    'array_int_dynamic': [
    34272,
],
    'array_varchar_dynamic': [
    'Joseph Gilbert',
    'Katherine Farmer',
    'Kristine Benitez',
    'Michelle Perez',
    'Marie Kelly',
    'Kathleen Grant',
    'Deanna Flores',
    'Kelsey Jackson',
    'Crystal Martin',
    'Elizabeth Evans',
],
    'json': {
    'name': 'Louis Armstrong',
    'address': '8023 Hammond Gateway Suite 461\nEast Anthonyhaven, AS 96368',
},
    'key32746': 'value83663',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Jeffrey Bailey',
    'address': 'PSC 3729, Box 2691\nAPO AA 74263',
    'text': 'Join factor rule without sing method resource. Fear music as likely mouth likely. Rise window hit hit be federal nearly any. Mission discussion meet career would put idea.',
    'email': 'andrea64@example.org',
    'phone_number': '001-968-915-5431x35882',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Rodriguez',
    'Tracy Anthony',
    'Makayla Mann',
    'Tina Evans',
    'Jessica Watkins',
    'Gregory Butler',
    'Megan Spencer',
    'Nicole Smith',
    'Derek Avila',
    'Nicole Combs',
],
    'json': {
    'name': 'James Holder',
    'address': '108 Kevin Loop Suite 636\nMichelleland, MD 81164',
},
    'key98302': 'value4723',
    'key37539': 'value12320',
    'key83124': 'value38072',
    'key74511': 'value28954',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Angel Miller',
    'address': 'Unit 2465 Box 8144\nDPO AE 22052',
    'text': 'Kind money color everyone history second. That president kitchen can.\nPick just choice couple ground today.',
    'email': 'robin77@example.net',
    'phone_number': '(353)621-8710x50969',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Julie Robinson',
    'Hunter Perkins',
],
    'json': {
    'name': 'Sarah Camacho',
    'address': '47690 Robinson Course Suite 413\nEast Michaelshire, DE 22114',
},
    'key64853': 'value42004',
    'key65439': 'value72066',
    'key90230': 'value64789',
    'key82778': 'value78987',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Melinda Price',
    'address': '937 Davis Course Apt. 408\nLake Brittany, KY 58929',
    'text': 'Name expect space onto notice dog now. Forget partner boy court more actually.\nSing happen reduce factor. Hair individual industry.',
    'email': 'heatherprince@example.net',
    'phone_number': '571-559-9668',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Ramsey',
    'Dr. Kathleen Oconnor',
    'Tammy Edwards',
],
    'json': {
    'name': 'Daniel Eaton',
    'address': '567 Tyler Street Apt. 328\nLake James, AR 05568',
},
    'key17437': 'value92915',
    'key89773': 'value43755',
    'key50741': 'value27804',
    'key82948': 'value11803',
    'key95275': 'value25857',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Chelsea Mcdaniel',
    'address': '296 Greene Bypass\nKristaberg, ID 80346',
    'text': 'Standard house become they beyond likely. Research size among store particular deep. If western include travel service also.',
    'email': 'ychen@example.com',
    'phone_number': '997.643.1445x37716',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mark Smith',
    'Emily Moreno',
    'Richard Robinson',
    'Keith Wright',
    'Margaret Hunter',
    'Denise Salas',
],
    'json': {
    'name': 'John Randolph',
    'address': 'PSC 7017, Box 9265\nAPO AE 88414',
},
    'key94437': 'value38192',
    'key79544': 'value85672',
    'key94721': 'value12822',
    'key89500': 'value12934',
    'key90813': 'value96508',
    'key94090': 'value72242',
    'key59456': 'value50056',
    'key81128': 'value70583',
    'key38318': 'value13938',
    'key16497': 'value70885',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Michael Holland',
    'address': '52950 Pittman Flats\nRobinsonshire, RI 07695',
    'text': 'Trial space term book affect worker treat. Article plan usually. We career table.\nOnly subject either building.',
    'email': 'steven35@example.org',
    'phone_number': '386-201-0438x554',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Randy Wright',
    'Joseph Edwards',
    'Mark Pierce',
    'Eric Mills',
    'Cynthia Marshall',
    'Richard Mendoza',
],
    'json': {
    'name': 'John Barker',
    'address': 'Unit 7714 Box 1670\nDPO AP 09804',
},
    'key44028': 'value6915',
    'key92265': 'value80499',
    'key52907': 'value10281',
    'key92515': 'value47795',
    'key97458': 'value74333',
    'key98973': 'value35541',
    'key12175': 'value60116',
    'key70115': 'value33066',
    'key15206': 'value58395',
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
    'RequestId': '7fc25780-62ef-11f0-9603-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_01_863272SUvKqeMJ',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'prod',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[prod-vector-url-128-100-2]_1752744123.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadProdVectorUrl12810021752744123Json()
    test.run_tests()
