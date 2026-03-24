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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752744832_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752744832.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid01752744832Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752744832.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752744832.json"
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
    'RequestId': '2017135c-62f1-11f0-bdea-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_40_350775VufEEPlg',
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
    'RequestId': '233721a5-62f1-11f0-a6df-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_40_350775VufEEPlg',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Sarah Roberts',
    'address': '4806 Sandoval Fork Suite 783\nBrownstad, CO 21678',
    'text': 'Necessary listen notice attack card pattern everybody well. Suddenly strong region art take service member garden.',
    'email': 'shanedavis@example.net',
    'phone_number': '+1-984-784-6222',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Armstrong',
    'Kristen Ayers',
    'Christian Hines',
    'Regina Bell',
    'Craig Turner',
    'Steven Johnson',
    'Darrell Rodriguez',
    'Wayne Manning',
],
    'json': {
    'name': 'Tracy Garrett',
    'address': '01769 Welch Stream Apt. 614\nPort Joannville, WY 01416',
},
    'key2166': 'value48450',
    'key35425': 'value31745',
    'key96842': 'value58691',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Savannah Olson',
    'address': '62933 James Fords Apt. 148\nStevenstad, VT 40908',
    'text': 'Law watch us physical event eight. Save both the. Those most order go animal focus.\nKnowledge raise pretty agreement try. Recently article wait open.',
    'email': 'matthewbenitez@example.net',
    'phone_number': '001-563-798-9109',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shane Miller',
    'Ashley Banks',
    'Teresa Collins',
    'Jose Tate',
    'Daniel Foley',
    'Kayla Nichols',
    'Benjamin Davis',
    'Jason Newton',
],
    'json': {
    'name': 'Mary Mahoney',
    'address': 'PSC 4678, Box 8093\nAPO AE 70982',
},
    'key90784': 'value19621',
    'key98649': 'value82002',
    'key27240': 'value76573',
    'key41988': 'value74318',
    'key66759': 'value90555',
    'key91584': 'value51310',
    'key9927': 'value61430',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Lisa Carroll',
    'address': 'Unit 2903 Box 0665\nDPO AA 40890',
    'text': 'For determine agency keep son consider himself. Scene ago drive seat history last any.\nEarly well organization minute. Purpose seek treatment method near pressure individual fight.',
    'email': 'matthew53@example.org',
    'phone_number': '679.575.2393x14776',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Casey Long',
    'Brandi Craig',
    'Vincent Jones',
    'Timothy Atkinson',
    'Thomas Martin',
    'Daniel Cabrera',
],
    'json': {
    'name': 'Gregory Simmons',
    'address': '475 Walker Circles\nPort Richard, MH 89416',
},
    'key57406': 'value96298',
    'key80092': 'value60414',
    'key66351': 'value18436',
    'key1210': 'value54023',
    'key11779': 'value6259',
    'key98084': 'value58345',
    'key47066': 'value16236',
    'key63622': 'value58438',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Kyle Davis',
    'address': '901 William Island\nNorth Larry, NV 60163',
    'text': 'During apply conference early. To rich modern hospital them board forget prevent. Site it product American.',
    'email': 'rtaylor@example.org',
    'phone_number': '+1-417-863-4668x2532',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Robert Alvarez',
    'John Bird',
    'Katie Smith',
    'Stephanie Rogers',
    'Aaron Carlson',
    'Wendy Rogers',
    'Donald Patterson',
    'Danielle Barnes',
],
    'json': {
    'name': 'Carrie Schultz',
    'address': '2412 White Crossing Apt. 656\nScotttown, FM 82026',
},
    'key85727': 'value76114',
    'key51163': 'value34473',
    'key3955': 'value54012',
    'key18434': 'value24871',
    'key87056': 'value78397',
    'key88827': 'value76058',
    'key29450': 'value84778',
    'key4047': 'value89231',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Matthew Stanton',
    'address': '89623 Jordan Road\nPort Kayleefort, MN 71927',
    'text': 'Kind environmental newspaper. Get enough company plant. Where still energy behind might national industry foot.\nRemain baby everything.',
    'email': 'samantha54@example.org',
    'phone_number': '001-464-355-8248x3717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Rivers',
    'Judy Schmitt',
    'Gregory Cochran',
    'Michael Berry',
    'Haley Orozco',
    'Matthew Martin',
    'Rose Davis',
],
    'json': {
    'name': 'Charles Church MD',
    'address': '469 Michelle Fords\nWest Kelly, MI 05893',
},
    'key9477': 'value71693',
    'key93568': 'value31845',
    'key18711': 'value64944',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Tara Woodard',
    'address': '344 Wade Stravenue\nLopezland, GA 23389',
    'text': 'Several action mean company for vote become. Movement resource among then usually cell.\nFloor office executive. Particular hotel save employee American. Military painting true Republican.',
    'email': 'willisandrew@example.net',
    'phone_number': '951-433-9129x0889',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Donna Burton',
    'Michael Vargas',
    'Connor Lutz',
    'George Harrington',
    'Gary Hardy DDS',
],
    'json': {
    'name': 'Dominic Ryan',
    'address': '4242 Rhodes Hill\nLake Jason, IL 81172',
},
    'key26205': 'value10342',
    'key8243': 'value94823',
    'key87058': 'value52501',
    'key60959': 'value21281',
    'key83940': 'value15380',
    'key41965': 'value92365',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Bonnie Mitchell',
    'address': '276 Williams Landing Apt. 180\nPort Juanville, WA 84281',
    'text': 'Answer we smile business answer consider.\nKnow age get we tough. Amount everyone open me her treat. Ground region worry son support system answer.\nPower city truth within identify leave.',
    'email': 'ernestray@example.org',
    'phone_number': '8609939686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Wagner',
],
    'json': {
    'name': 'Kyle Smith',
    'address': '63125 Eric Views\nLake Thomasberg, DC 73900',
},
    'key34478': 'value89799',
    'key41761': 'value17808',
    'key89541': 'value2073',
    'key87282': 'value39460',
    'key38360': 'value67658',
    'key72469': 'value28831',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'James Berg',
    'address': '7378 Ford Dam Suite 241\nMarkhaven, AK 60353',
    'text': 'Rock town position garden. Stay truth model activity. Heavy consider research fast mention director off soldier.',
    'email': 'gracesutton@example.org',
    'phone_number': '(399)500-3945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Dr. David Austin',
    'Christopher Boyd',
    'Amanda Johnson',
    'Charles Evans',
    'Terry Hanna DDS',
    'Anthony Hubbard',
    'Terry Chase',
],
    'json': {
    'name': 'Steven Robinson',
    'address': '401 Carlos Cliff Suite 531\nNew Marie, CA 00647',
},
    'key53667': 'value74204',
    'key17750': 'value64728',
    'key47126': 'value69585',
    'key38356': 'value88397',
    'key26953': 'value10165',
    'key10314': 'value91996',
    'key84577': 'value47513',
    'key39431': 'value28404',
    'key12573': 'value66473',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Patricia Bell',
    'address': '42883 Luis Lake Suite 393\nEast Christina, AR 07641',
    'text': 'Capital prevent something debate letter. Pull choose heavy drop season act national.\nStudy pull language well food. Special better somebody play billion after.',
    'email': 'paulaharris@example.org',
    'phone_number': '231.839.7744',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Chapman',
    'Christopher Liu',
    'John Arellano',
    'Juan Davis',
    'Bonnie Taylor',
    'Kayla Summers',
    'Stephen Tucker',
],
    'json': {
    'name': 'Scott Perez',
    'address': '95624 Garner Shoal\nMolinaville, AZ 99940',
},
    'key8545': 'value38175',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Robert Mccarty',
    'address': '924 Nathan Pass Suite 842\nWigginsshire, GU 98642',
    'text': 'Far also station sea.\nFull I suffer reduce style agency commercial. Take stage oil despite understand relate special.',
    'email': 'jameshines@example.com',
    'phone_number': '001-680-485-5240x59580',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Marshall',
    'Susan Sanchez',
    'Anne Gomez',
    'Erika Stone',
    'Kelly Montoya',
    'Joshua Waller',
    'Johnny Jackson',
    'Max Mercer',
    'Jonathan Ramsey',
    'Melissa Thomas',
],
    'json': {
    'name': 'Alexander Miller',
    'address': '927 Rachel Pass\nWest Kelly, UT 04059',
},
    'key76034': 'value12426',
    'key44954': 'value36368',
    'key74612': 'value72995',
    'key85257': 'value80372',
    'key56539': 'value81192',
    'key88799': 'value3318',
    'key33391': 'value10537',
    'key27733': 'value73165',
    'key70021': 'value10841',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Suzanne Delgado',
    'address': '28585 Greene Camp\nPort Micheleton, UT 49626',
    'text': 'Officer act wish. Whether say morning budget during whole network fall. Style agency scene perhaps will read you record.',
    'email': 'powersrandy@example.org',
    'phone_number': '600.215.7419',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Oconnell',
    'Vincent Stuart',
    'Dustin Holloway',
    'Jill Reid',
    'Cody Brewer',
    'Katie Castro',
    'Antonio Franklin',
    'Michael Rivera',
],
    'json': {
    'name': 'Peggy Glenn',
    'address': '2870 Davis Streets Suite 315\nAndersonburgh, PW 17228',
},
    'key75660': 'value10862',
    'key10722': 'value17841',
    'key99504': 'value95927',
    'key52575': 'value38918',
    'key66441': 'value89823',
    'key66398': 'value57442',
    'key67353': 'value7492',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Eric Whitaker',
    'address': '33257 Daniel Mountain Suite 915\nEast Rebekahhaven, SC 33386',
    'text': 'Represent so never growth. Some space number scientist must pass. Under red safe in free include against similar.\nResponsibility star will why edge fire. Data late by move.',
    'email': 'caitlin99@example.net',
    'phone_number': '586-441-6315',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tiffany Smith',
    'Randy Gray',
    'Daniel Marquez',
    'Mrs. Angel Yu',
    'Jeffrey Cooper',
    'Mark Nichols',
],
    'json': {
    'name': 'Christopher Vargas',
    'address': '410 Kelsey Forest\nSouth Loganview, TN 59944',
},
    'key38891': 'value37188',
    'key30443': 'value3189',
    'key43355': 'value70259',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Denise Cruz',
    'address': '039 Adams Vista\nLake Danny, ID 72652',
    'text': 'Itself thought kitchen music almost boy perform. Seven carry fight order quickly name race thought.',
    'email': 'ujackson@example.net',
    'phone_number': '640-792-7083x9332',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Smith',
    'Jessica Gonzalez',
    'Thomas Gordon',
    'Wendy Hall',
    'Elizabeth Mcdonald',
    'Eric Lindsey',
    'Chelsey Logan',
],
    'json': {
    'name': 'Kathleen Pratt',
    'address': '0658 David Square\nJustinton, ME 98339',
},
    'key87484': 'value50099',
    'key64739': 'value2848',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Ricardo Gross',
    'address': '53751 Jodi Manor\nEast Alison, MT 53653',
    'text': 'Green specific treatment near. Central movement form. Long clearly still.\nBad garden medical. Feel throughout ready high still community fast.',
    'email': 'philip11@example.com',
    'phone_number': '(213)634-5379x56177',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jason Lopez',
    'Joshua Walker',
    'Alicia Morrison',
    'Joshua Cain',
],
    'json': {
    'name': 'James Baker',
    'address': '0967 Gina Points Suite 613\nWardview, ND 15450',
},
    'key94472': 'value67898',
    'key38262': 'value23165',
    'key72166': 'value7659',
    'key50869': 'value71400',
    'key40073': 'value77754',
    'key72512': 'value61570',
    'key29001': 'value44209',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Andrea Neal',
    'address': '66847 White Stravenue Apt. 689\nRobertmouth, MP 39175',
    'text': 'Position time rise risk. Figure respond to protect southern already me attack. Want her human phone.\nAvoid rich citizen treat ten. Republican serve writer which culture.',
    'email': 'ryan85@example.net',
    'phone_number': '518-697-4790x58731',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Young',
    'Stacey Molina',
    'Jennifer Carpenter',
    'Noah Williams',
    'Jamie Johnson',
    'Angela Evans',
    'Kimberly Lawrence',
    'Kevin Spencer',
    'Jason Dixon',
    'Todd Castro',
],
    'json': {
    'name': 'Krystal Pearson',
    'address': '22453 Anderson Pass Apt. 742\nNew James, IL 96252',
},
    'key63027': 'value2466',
    'key10922': 'value12188',
    'key19302': 'value61921',
    'key12131': 'value92556',
    'key78683': 'value42712',
    'key13336': 'value43612',
    'key79304': 'value95468',
    'key54773': 'value30004',
    'key20683': 'value19122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jerry Walls',
    'address': '9939 Tracy Villages\nWest Pamelamouth, CA 96341',
    'text': 'Information network dinner still. Cold fund agent sell school interesting action. Under involve white less.\nDrop certainly recent. Poor glass they foot likely theory chair focus.',
    'email': 'nharrison@example.org',
    'phone_number': '001-737-344-2512x18251',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joyce Ellis',
    'James Collins',
    'Thomas Strickland',
    'Mark Lester',
    'Reginald Leon',
    'Wanda Robinson',
    'Steven Holland',
    'Matthew Williams',
    'Rebecca Allen',
    'Jonathan Stein',
],
    'json': {
    'name': 'David Savage',
    'address': '8438 Mary Lock\nNew Jacob, MI 20534',
},
    'key67018': 'value58021',
    'key57413': 'value29876',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Beth Reed',
    'address': '025 Jeffrey Drive\nWest Shelley, DC 81430',
    'text': 'Develop environmental wall upon heavy type probably. Consider conference recognize expert. Today seem visit dark nice.',
    'email': 'april49@example.org',
    'phone_number': '+1-948-302-8604x16515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Anna Underwood',
    'Melissa Carter',
    'Martha Mckee',
    'Andrew Sanchez DDS',
    'Michael Cantrell',
    'Brian Strickland',
    'Paige Patterson',
    'Dale Newton',
    'David Rich',
],
    'json': {
    'name': 'Craig Brown',
    'address': '8258 Love Springs\nEast Kelli, MD 11834',
},
    'key37901': 'value76565',
    'key26370': 'value43069',
    'key69095': 'value20798',
    'key25813': 'value77024',
    'key30333': 'value41596',
    'key75543': 'value25178',
    'key33221': 'value77042',
    'key22252': 'value87839',
    'key26500': 'value70280',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Christine Kelly',
    'address': '5217 Watkins Greens Suite 154\nStaceyfurt, NJ 34367',
    'text': 'Charge environmental statement parent. Game according customer else five.\nChoice pattern large chair city attack agreement. Director foreign lawyer evening. Three with reveal time.',
    'email': 'edwardmurphy@example.com',
    'phone_number': '881.517.2552x496',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Francis Turner',
    'Jeremy Perez',
    'Andrew Lee',
],
    'json': {
    'name': 'James Miller',
    'address': '78488 Rice Street\nEast Johnfurt, KY 96152',
},
    'key45166': 'value68303',
    'key36479': 'value44151',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Lori Rice',
    'address': '6816 Jennifer Way Suite 409\nNew Kimberly, NJ 69570',
    'text': 'Somebody kitchen material candidate. Itself whom million seem.\nSuccessful top government. Purpose fly few act training shake. Cut player none two far trip.',
    'email': 'ebrooks@example.net',
    'phone_number': '(898)497-7632x77281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Martin',
    'Michael Holder',
    'Matthew Harris',
    'Jeremy Sanders',
    'Michele Reed',
    'Mark Henderson',
],
    'json': {
    'name': 'Ann Nelson',
    'address': '8815 Jennings Club\nNew Anitashire, WV 64839',
},
    'key79548': 'value65851',
    'key12240': 'value6020',
    'key1800': 'value38387',
    'key53083': 'value33080',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Tanya Arnold',
    'address': '441 Melissa Burg Apt. 804\nNorth Katherinehaven, NM 46659',
    'text': 'Turn threat song control. Result later catch decision which both finally. Special sure whom support.\nConsider magazine energy way. Account society TV upon song determine.',
    'email': 'kaylawinters@example.net',
    'phone_number': '249-586-2728x8378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Richard Gutierrez',
    'Lisa Tran',
    'Joshua Jenkins',
    'Christopher Hancock',
    'Vanessa Pierce',
    'Hannah Long',
    'Patricia Anderson',
],
    'json': {
    'name': 'James Morris',
    'address': '924 Alex Curve\nLaurenburgh, CA 63534',
},
    'key87773': 'value13167',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Victoria Schmidt',
    'address': '429 Amanda Mountains Suite 530\nPort Diana, GU 13113',
    'text': 'Ability across rule life. Off author keep focus wonder. Also guy run dinner.\nPer other without central once whose. Suffer recent time mind dark article.',
    'email': 'vernongonzalez@example.net',
    'phone_number': '337-926-8692x0384',
    'array_int_dynamic': [
    71291,
],
    'array_varchar_dynamic': [
    'Brenda Wheeler',
    'Hannah Knight',
    'Traci Jones',
    'Zachary Yates',
    'Jasmin James',
    'Tyrone Patterson',
    'Jennifer Lewis',
    'Andrew Ramirez',
],
    'json': {
    'name': 'Jesse Larsen',
    'address': '578 Holland Points\nWest Nicolemouth, KS 08894',
},
    'key47495': 'value82745',
    'key32659': 'value88193',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Randy Ortiz',
    'address': '4786 Hamilton Drive\nNew Raymouth, SC 03154',
    'text': 'Future responsibility for rock try lose choice. Tell agent party yes rock heart.\nHave hotel air wrong. These significant run address product each difficult.',
    'email': 'emilymiller@example.net',
    'phone_number': '(246)735-0940',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Kaiser',
    'Scott Crosby',
    'Lisa Morrow',
    'Blake Spencer',
],
    'json': {
    'name': 'Robert Black',
    'address': '632 Richard Ridge\nPort Donnaburgh, OK 66720',
},
    'key42363': 'value73585',
    'key37612': 'value89224',
    'key52513': 'value57942',
    'key81098': 'value24529',
    'key54494': 'value91936',
    'key76237': 'value94525',
    'key36930': 'value25077',
    'key75655': 'value76791',
    'key43675': 'value65079',
    'key94974': 'value10448',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Rachel Stokes',
    'address': '74831 Garza Mission\nPort Sharon, CA 21335',
    'text': 'Imagine operation teach tax together. Rule want main week attention they. Chance test rule receive.',
    'email': 'christopherbond@example.com',
    'phone_number': '372-397-9277',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Susan Jones',
    'Travis Hill',
],
    'json': {
    'name': 'Whitney Dodson',
    'address': '585 Douglas Inlet Apt. 041\nJenniferchester, OH 20431',
},
    'key37439': 'value96849',
    'key14532': 'value20523',
    'key95856': 'value75432',
    'key6525': 'value6074',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Nicholas Townsend',
    'address': '7944 Linda Prairie\nWest Justin, AL 63403',
    'text': 'Visit rate almost citizen down early policy. He help friend particular quickly travel.',
    'email': 'heatherschmidt@example.com',
    'phone_number': '(866)829-9224x169',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tonya Stephenson',
    'Michele Robinson',
    'Charles Wall',
],
    'json': {
    'name': 'Elizabeth Davis',
    'address': '3157 Lee Corners Suite 374\nCraigport, LA 76227',
},
    'key67291': 'value54125',
    'key24151': 'value25764',
    'key99054': 'value48871',
    'key73033': 'value53810',
    'key6464': 'value94895',
    'key54983': 'value99288',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Cynthia Rodriguez',
    'address': '78533 Kelly Viaduct Apt. 933\nEast Michael, ND 16203',
    'text': 'Range choice film support. Lot green accept before take.\nFear full network. Drop source however recent.\nImagine strategy quickly world occur. Really another so training type you probably.',
    'email': 'bmiller@example.com',
    'phone_number': '(751)275-4887',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Wilson',
    'Gabriel Hunter',
    'David Nolan',
    'Adam Snyder',
    'Kelly Mccarthy',
    'Sue Jackson',
    'Miss Amanda Gross',
    'Richard Wright',
    'Steven Marquez',
    'Sonya Cox',
],
    'json': {
    'name': 'Brandon Baxter',
    'address': '6336 Kelly Cove\nLisaberg, CO 77841',
},
    'key8596': 'value72929',
    'key33949': 'value70135',
    'key97511': 'value24440',
    'key10412': 'value70097',
    'key32237': 'value71767',
    'key90734': 'value19713',
    'key59598': 'value42380',
    'key87920': 'value36604',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Jill Martin',
    'address': '819 Kevin Spur\nChristyland, SD 85255',
    'text': 'Store the nor interview speak without century after. Few feel record win color beyond life. Nothing agreement where I hour identify majority.',
    'email': 'daniel78@example.org',
    'phone_number': '(504)974-0962',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Johnson',
    'Corey Watkins',
    'Joshua Nelson',
    'Ms. Linda Boone',
    'Destiny Green',
    'Tammy Malone',
    'Krystal Montes',
    'Alexandra Smith DDS',
    'James Thomas',
],
    'json': {
    'name': 'Tiffany Smith',
    'address': '4918 Yoder Lights\nMariafurt, MT 04559',
},
    'key66240': 'value5214',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Martha Carson',
    'address': '51234 Jenkins Square Apt. 336\nWest Candicefort, NC 25751',
    'text': 'This team we owner. Son fly term around thus chance another.\nPlay side address. Before major fear moment.\nThroughout religious perform collection. Turn subject international meeting among real other.',
    'email': 'robinsonchristine@example.net',
    'phone_number': '864-863-7963x170',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brianna Riley',
    'Patrick Mills',
    'John Ross',
    'Damon Werner',
    'Paula Henderson',
    'Shelby Long',
    'Molly Parker',
    'Cheyenne Williamson',
    'Zachary Sanchez',
    'Richard Mcknight',
],
    'json': {
    'name': 'Kristen Brown',
    'address': '43093 Gibbs Place Apt. 200\nLake Tyroneside, SC 16228',
},
    'key5371': 'value12420',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Matthew Braun',
    'address': '05560 Barnes Trafficway\nEast Jakeland, AS 89369',
    'text': 'While consumer something run unit current there specific. Leader science last study hundred today movement. Rock all interesting certain physical smile a.',
    'email': 'curtis06@example.org',
    'phone_number': '783-865-3193x19934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Claire Thompson',
    'Brooke Nunez',
    'Kathleen Nelson',
    'Alyssa Medina',
    'Stephanie Watson',
    'Adrienne Walters',
],
    'json': {
    'name': 'Patrick Lee',
    'address': '53381 Jacob Run\nDunnmouth, VI 50889',
},
    'key6291': 'value31450',
    'key67493': 'value20835',
    'key37344': 'value82302',
    'key65705': 'value46409',
    'key82171': 'value20811',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Joseph Castro',
    'address': 'PSC 3397, Box 6298\nAPO AA 54968',
    'text': 'Different child meet through Mr candidate view operation. Today name million present. Like enter when by house team provide.\nThrow less charge you anything show season. Yourself not argue.',
    'email': 'hannahhull@example.org',
    'phone_number': '+1-802-564-1765x4970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Linda Henderson',
    'Melissa Wilson',
    'Kenneth Mann',
    'Sheila Vargas',
    'Janice Abbott',
    'Richard Smith',
    'Christopher Smith',
    'Robert Chen',
],
    'json': {
    'name': 'Robert Snyder',
    'address': 'PSC 1427, Box 8378\nAPO AA 79177',
},
    'key72947': 'value15112',
    'key26198': 'value1102',
    'key1942': 'value84347',
    'key90351': 'value80992',
    'key96162': 'value72738',
    'key47376': 'value18842',
    'key36407': 'value85802',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Dr. Michelle Page',
    'address': '6383 Schaefer Fall\nThomasport, RI 49614',
    'text': 'Land concern they tell why power address. Process produce student mother girl many impact.\nPlan right owner. Take none parent among material any only.',
    'email': 'foxdesiree@example.org',
    'phone_number': '868-980-7442',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Karen Jordan',
    'Jamie Lam',
    'Benjamin Robinson',
    'Jacob Sanders',
    'Timothy Stanley',
    'Joshua Johnston',
],
    'json': {
    'name': 'Ronald Carson',
    'address': '622 Sierra Mount\nSouth Arthur, IN 75577',
},
    'key41254': 'value95459',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Heather Lynch',
    'address': '956 Webb Walk\nWest Matthew, AK 69667',
    'text': 'Open since light many. Different science letter represent. Tell health to sell protect finally.',
    'email': 'hugheshannah@example.com',
    'phone_number': '(792)332-6204',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Julie Shaffer',
    'Jessica Sullivan',
    'Douglas Jones',
],
    'json': {
    'name': 'Angela Ortiz',
    'address': '2100 Dunn Corners Apt. 400\nSouth Jennifer, MN 81407',
},
    'key80309': 'value12058',
    'key12556': 'value5974',
    'key12785': 'value828',
    'key14769': 'value37378',
    'key23624': 'value50428',
    'key29278': 'value17095',
    'key35125': 'value12270',
    'key39005': 'value26336',
    'key97409': 'value81188',
    'key70599': 'value20870',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'James Parker',
    'address': 'USNV Gilbert\nFPO AA 30491',
    'text': 'Draw even become exactly many list worry ask. Memory energy remain understand. Address chance apply region.',
    'email': 'jerrywood@example.org',
    'phone_number': '+1-342-387-7742',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jasmin Matthews',
    'Charles Wilson',
    'Jimmy Thomas',
    'James Rogers',
    'Aaron Benson',
    'Tammy Murphy',
],
    'json': {
    'name': 'Matthew Moore',
    'address': '3491 Angela Road Suite 916\nNew Mirandaton, LA 51675',
},
    'key25933': 'value47627',
    'key83750': 'value34651',
    'key58528': 'value93456',
    'key5753': 'value60779',
    'key3419': 'value66533',
    'key99789': 'value69544',
    'key69507': 'value91677',
    'key19956': 'value38318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Thomas Williams',
    'address': '058 Anderson Hollow Apt. 834\nGoodshire, SD 31096',
    'text': 'Third name develop eye meeting believe ten because. Threat animal not.\nUse news necessary. When leg run reach suffer. Live event defense school bar.',
    'email': 'hoganvanessa@example.org',
    'phone_number': '+1-918-247-2664x4022',
    'array_int_dynamic': [
    73347,
],
    'array_varchar_dynamic': [
    'Kelli Bates',
    'Monica Hernandez',
    'James Garcia',
    'Katherine Evans',
    'Amy Stewart',
],
    'json': {
    'name': 'John Patton',
    'address': '255 Andre Pine Suite 594\nNew Frances, FM 04281',
},
    'key86034': 'value17389',
    'key31121': 'value39320',
    'key76380': 'value2223',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Dr. Seth Hubbard',
    'address': 'USNS Nguyen\nFPO AE 09564',
    'text': 'Success decision responsibility tough seek anyone. Able word tell blood cell response positive.',
    'email': 'vincentwilliam@example.org',
    'phone_number': '207-891-5818',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michael Miles',
    'Clarence Hicks',
    'Debra Fisher',
    'Michael Bowen',
    'Jennifer Dixon',
    'Justin Gomez',
    'Jeffrey Olson',
    'Cindy Thomas',
    'Jesse Stewart',
    'Brian Martinez',
],
    'json': {
    'name': 'Daniel Guerrero',
    'address': '49362 Robinson Gardens\nNelsonchester, MS 71386',
},
    'key70004': 'value94673',
    'key99401': 'value77732',
    'key1520': 'value95209',
    'key13156': 'value9771',
    'key80647': 'value37111',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Albert Lee',
    'address': '545 Linda Prairie\nAmyport, GU 86897',
    'text': 'Special level establish production exactly institution simple. Control while establish list. Media coach have score.\nAttorney per determine feel note note.',
    'email': 'victoriabaxter@example.org',
    'phone_number': '7144313429',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Paul Garza',
    'Brian Shepherd',
    'Joshua Robinson',
    'Susan Roberts',
    'Andrew Campos',
    'Brendan Reed',
    'Cindy Caldwell',
],
    'json': {
    'name': 'Alyssa Walker',
    'address': '5862 King Pike\nLopezland, WI 40422',
},
    'key82093': 'value29222',
    'key50057': 'value38627',
    'key64614': 'value90730',
    'key67719': 'value86664',
    'key83178': 'value46113',
    'key23543': 'value78175',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Matthew Cohen',
    'address': '137 Michael Terrace Apt. 487\nNorth Penny, MN 35593',
    'text': 'Yard act recent different. American nature support provide choose dark window. Cup yes pretty public identify difficult and.',
    'email': 'james15@example.com',
    'phone_number': '+1-238-696-5992x97282',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Ali',
    'Maurice Gilbert',
],
    'json': {
    'name': 'John Martinez',
    'address': '7180 Kaitlyn Freeway\nMcconnellchester, ND 58643',
},
    'key59563': 'value36331',
    'key4923': 'value45909',
    'key75735': 'value69775',
    'key54720': 'value9231',
    'key15833': 'value83444',
    'key17359': 'value91946',
    'key4336': 'value94512',
    'key68391': 'value65781',
    'key96565': 'value31191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Dr. Timothy Nichols',
    'address': '38560 Williams Mountains\nTylermouth, VI 06643',
    'text': 'End coach state production machine. Clear begin politics be size there. Picture decade reduce wife ahead.\nAll team who third expert into PM. Political watch decision.',
    'email': 'parkercourtney@example.org',
    'phone_number': '001-261-660-1773x365',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Hall',
    'Kristin Swanson',
    'Gina Holt',
    'James Edwards',
    'Brandon Adams',
    'Katelyn Turner',
    'Anna Crane',
],
    'json': {
    'name': 'Daniel Fernandez',
    'address': '1248 Julia Greens Apt. 375\nWilsonhaven, MT 07498',
},
    'key73209': 'value45437',
    'key96366': 'value10132',
    'key12605': 'value42684',
    'key61202': 'value63397',
    'key56289': 'value86760',
    'key67583': 'value28224',
    'key30480': 'value78437',
    'key2843': 'value56477',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Thomas Tucker',
    'address': 'Unit 6563 Box 1361\nDPO AA 25169',
    'text': 'Security real they mean especially find style particular. Kitchen learn nearly nation.\nSecond page stock run. Modern give bank ever investment give. Treat there source yard benefit cultural.',
    'email': 'pjones@example.net',
    'phone_number': '912-360-3071',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Jimenez',
    'Scott Rose',
    'Christopher Lopez',
    'Melinda Torres',
    'Justin James',
    'Sarah Burton',
],
    'json': {
    'name': 'Rhonda Yates',
    'address': '66391 Baldwin Trafficway\nNorth Latasha, IN 07893',
},
    'key77494': 'value44146',
    'key57631': 'value69864',
    'key96312': 'value11868',
    'key93695': 'value57744',
    'key59392': 'value64410',
    'key79358': 'value8898',
    'key54390': 'value14403',
    'key75472': 'value93795',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Alicia Palmer',
    'address': '6546 Dodson Burgs\nSouth Baileyside, VT 35373',
    'text': 'Left company action. Economy ground remain off.\nAudience near reality very front event after. Capital realize cost beyond positive common adult. On pressure investment beyond current guess rich case.',
    'email': 'vho@example.com',
    'phone_number': '+1-690-647-4278',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Larson',
    'Cindy Walsh',
    'Jacob Velazquez',
    'James Hernandez',
    'Gregory Murphy',
    'Michael Rogers',
    'Susan Hale',
    'Lauren Maxwell',
],
    'json': {
    'name': 'Richard Ferguson',
    'address': 'Unit 4907 Box 0648\nDPO AA 07005',
},
    'key47021': 'value43612',
    'key53334': 'value99317',
    'key2278': 'value93334',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Sarah Martinez',
    'address': '535 Nelson Street\nSouth Nicole, DC 46402',
    'text': 'Avoid soon recently interesting word. Street prove idea better opportunity check. Understand alone dinner message her. Soldier majority human environmental notice mouth.',
    'email': 'cunninghamjohn@example.net',
    'phone_number': '690-853-8156x295',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sean Johnson',
    'Joseph Smith',
    'Jennifer Gay',
    'Angela Harris',
    'Kenneth Dean',
    'Brenda Higgins',
    'Melissa Cannon',
    'Brian Krueger',
    'Brian Reynolds',
],
    'json': {
    'name': 'Evan Joseph',
    'address': '15979 Miller Loaf Apt. 007\nSouth Christinaport, VI 41710',
},
    'key99365': 'value38838',
    'key51492': 'value13923',
    'key33692': 'value4457',
    'key67383': 'value39802',
    'key42631': 'value71840',
    'key42399': 'value91003',
    'key1459': 'value83699',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Carol Alexander',
    'address': '857 Tina View\nNew Mitchellville, UT 41991',
    'text': 'Yet theory world. Guess station happen.\nMain now rather actually never probably.\nTen artist perhaps affect. Beat point try bar ok operation.\nSeek hit choice size the interest. She shake front would.',
    'email': 'suzanneharris@example.net',
    'phone_number': '001-300-462-4212',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tamara Ramirez',
    'Lisa Rivera',
    'Robin Richardson',
    'Alexandra Charles',
    'Laura Powers DVM',
    'Jeffrey Hammond',
    'Jennifer Archer',
    'Anthony Pratt',
    'Vincent Cruz',
],
    'json': {
    'name': 'Paula Craig',
    'address': '11069 Max Skyway\nBrandimouth, NY 86215',
},
    'key46830': 'value95390',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Justin Brown',
    'address': '488 Berry Station\nCatherineton, UT 53383',
    'text': 'Occur hour field friend leave itself turn. Language later industry. Share expert whether reality.\nMethod hope from write. Class simply business specific. A idea project program special.',
    'email': 'franklinlarry@example.org',
    'phone_number': '001-766-217-8199x4379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Philip Rodriguez',
    'Adam Nguyen Jr.',
    'Patricia King',
    'Sarah Armstrong',
    'Anna Preston',
    'Travis Haynes',
],
    'json': {
    'name': 'Amber Baker',
    'address': '70066 Baker Drive Apt. 188\nWilliamsborough, RI 98372',
},
    'key60921': 'value44841',
    'key48093': 'value18950',
    'key82378': 'value45917',
    'key81659': 'value54548',
    'key51497': 'value14760',
    'key12917': 'value34037',
    'key42876': 'value3176',
    'key99216': 'value87496',
    'key88076': 'value66334',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Shannon Arnold',
    'address': '2584 Michelle Corner\nEast Joseph, RI 98661',
    'text': 'Nearly technology open break music. Answer kind town special land various race. Really would industry ten.\nHappen training his herself there despite require.',
    'email': 'qmartinez@example.com',
    'phone_number': '+1-924-768-6506x2046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Bates',
    'Cameron Wong',
    'Dr. Sandra Perry',
    'Crystal Dunn',
    'Joseph Mitchell',
    'Karen Perez',
    'Ricky Powell',
],
    'json': {
    'name': 'David Williams',
    'address': '33741 Michael Shores\nCookville, UT 71949',
},
    'key69540': 'value16112',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Stephen White',
    'address': '918 Roberto Bridge Apt. 812\nHoshire, AK 22974',
    'text': 'Notice benefit energy smile within laugh. Group son similar international share center. Ten off box whom. Situation up across time.',
    'email': 'obenson@example.org',
    'phone_number': '801-845-9840',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Shaw',
    'Anthony Sampson',
    'Joel Torres',
],
    'json': {
    'name': 'Jessica Powell',
    'address': '15749 Patel Forges\nLeonardport, WI 18052',
},
    'key27711': 'value24096',
    'key21927': 'value70430',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Miguel Wilson',
    'address': '3789 Brianna Plaza Suite 561\nKarahaven, ME 79100',
    'text': 'Specific rule majority summer class health task. Give choose defense activity. Board soldier represent reveal.\nOk hotel join responsibility. Idea affect usually action social.',
    'email': 'alvarezlinda@example.com',
    'phone_number': '+1-558-478-3356',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Justin Lee',
    'Brittany Peters',
    'Scott Reyes',
    'Katie Roy',
    'Nicole Atkinson',
],
    'json': {
    'name': 'Jordan Jenkins',
    'address': '1958 Dawn Brooks Apt. 621\nDavidborough, PR 60780',
},
    'key189': 'value41057',
    'key47603': 'value45255',
    'key52979': 'value60318',
    'key16280': 'value61699',
    'key71898': 'value64677',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Alicia Williamson',
    'address': '24328 Katie Pike\nSherrybury, NH 13978',
    'text': 'List record another. Performance can every special against often interesting.\nProvide floor reason wife reduce staff. Wind factor world. Produce conference lay.',
    'email': 'ustewart@example.net',
    'phone_number': '947.944.6072x30479',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stacey Turner',
    'Jason Trevino',
    'Courtney Wall',
    'James Lowe',
],
    'json': {
    'name': 'James Brown',
    'address': '82226 Davis Brooks Suite 867\nEast Davidmouth, VI 23124',
},
    'key11571': 'value15738',
    'key63639': 'value53837',
    'key66728': 'value28879',
    'key97829': 'value81043',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Jennifer Wilson',
    'address': '72207 Kimberly Crest\nLake Amy, WA 79500',
    'text': 'Process discover against talk use according perform join. Exist light effort big call.\nMorning seem probably through suffer beyond group industry. Debate hit series phone will grow.',
    'email': 'arthurnelson@example.net',
    'phone_number': '460-901-3307x2178',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Singleton',
    'Dr. Sarah Hampton DVM',
    'Jacob Smith',
    'Sylvia Mays',
    'Amy Ruiz',
    'William Wang',
    'David Munoz',
    'Rodney Clarke',
],
    'json': {
    'name': 'James Fernandez',
    'address': '659 Martinez Drives\nJaymouth, TN 89289',
},
    'key35410': 'value99001',
    'key92080': 'value23419',
    'key1026': 'value83548',
    'key52191': 'value68051',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Jason Ali',
    'address': '63556 Justin Loop\nEast Thomaston, WI 76616',
    'text': 'Decade sing to past compare. Crime as commercial fish today true population. Cost glass notice course road page.',
    'email': 'cheryl87@example.net',
    'phone_number': '001-976-580-6760x458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Daisy Bruce',
    'Penny Hudson',
    'Brandy Anderson',
    'Travis Casey',
    'Amanda Smith',
],
    'json': {
    'name': 'Michael Brown',
    'address': '2458 Martin Park\nEast Scott, MI 85709',
},
    'key56315': 'value47577',
    'key66386': 'value18413',
    'key58856': 'value93649',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Timothy Freeman',
    'address': '499 Lopez Fort\nSonyastad, AS 90682',
    'text': 'Partner start subject administration. Free make decade hair hold play not civil.\nEverybody week provide man management. Eat pattern view loss.',
    'email': 'dspence@example.net',
    'phone_number': '(894)339-8315',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Vincent Padilla',
    'Miranda Williams',
    'Lisa Lopez',
    'William Johnson',
    'Laura Wright',
],
    'json': {
    'name': 'Amanda Freeman',
    'address': '7862 Anthony Shoals Apt. 540\nEast Nicole, AR 07564',
},
    'key8178': 'value87220',
    'key96783': 'value17489',
    'key24594': 'value84158',
    'key96664': 'value92042',
    'key50353': 'value67292',
    'key34278': 'value25150',
    'key77719': 'value41256',
    'key43104': 'value45573',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Amanda Roberts',
    'address': '867 Bradley Land Suite 920\nCindyborough, WY 49259',
    'text': 'About always claim step just. While trouble over mind prove police challenge.',
    'email': 'dbarnes@example.net',
    'phone_number': '256-905-4359x92244',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Frank Thomas',
    'Belinda Cline',
    'John Price',
    'Jason Stokes',
    'Johnathan Meyer',
    'Taylor Reyes',
    'Julie White',
],
    'json': {
    'name': 'Austin Parrish',
    'address': '41634 Rebecca Corner\nJeffreymouth, CO 39008',
},
    'key74084': 'value55765',
    'key78114': 'value90791',
    'key23781': 'value12952',
    'key65837': 'value62236',
    'key13439': 'value76643',
    'key2756': 'value31651',
    'key66588': 'value43223',
    'key87184': 'value39828',
    'key21921': 'value81455',
    'key96044': 'value14306',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Michael Hayes',
    'address': '22556 Erin Islands\nNorth Joshua, WV 68433',
    'text': 'Ten tough year forward. Act deep break air eat score.\nShow happen task.',
    'email': 'williamlewis@example.com',
    'phone_number': '+1-551-789-2006x657',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Moore',
    'Dr. Victoria Brooks',
    'Anthony Pittman',
    'Dennis Simmons',
    'Corey Baker',
    'Paul Brown',
    'Benjamin Horton',
    'Christina Craig',
    'Terri Day',
    'Michelle Whitaker',
],
    'json': {
    'name': 'Sierra Baker',
    'address': 'Unit 3719 Box 2154\nDPO AA 16232',
},
    'key50139': 'value73707',
    'key93387': 'value88820',
    'key15201': 'value37702',
    'key27268': 'value28248',
    'key90059': 'value65304',
    'key33780': 'value84930',
    'key33788': 'value98704',
    'key53539': 'value28905',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Melinda Guzman',
    'address': '48324 Williams Corners Suite 617\nWilsonbury, PR 55804',
    'text': 'Generation site friend book. Throughout history rock region. Might truth win pass through.\nRise add great pull.',
    'email': 'emmalyons@example.com',
    'phone_number': '+1-937-537-8296x2435',
    'array_int_dynamic': [
    47401,
],
    'array_varchar_dynamic': [
    'Walter Sanchez',
    'Sally Lang',
],
    'json': {
    'name': 'Jeff Wade',
    'address': '048 Potts Street\nGarciaburgh, NM 90328',
},
    'key13338': 'value82346',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Ronald Williamson',
    'address': '801 Dixon Mills Apt. 372\nNorth Corey, IA 71240',
    'text': 'Study beautiful thus community avoid class born teacher. Yard cover hope week check dream finish. Eight range ground manager.',
    'email': 'rubenweaver@example.com',
    'phone_number': '+1-519-387-1685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Angela Young',
    'Erin Cox',
    'John Carroll',
    'Laura Anderson',
    'Paula Hogan',
    'Daniel Day',
    'Jose Rodriguez',
    'James Davis',
],
    'json': {
    'name': 'Steven Parker',
    'address': '118 White Stream Apt. 268\nChristopherville, NC 65856',
},
    'key16891': 'value97660',
    'key71597': 'value94238',
    'key2630': 'value21576',
    'key95168': 'value77622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Michael Whitaker',
    'address': '99434 Brennan Drive\nBrewerton, KS 64865',
    'text': 'Environment low according sell them environmental trip growth. Dream nor kind. Star full three partner from else why west.',
    'email': 'seth91@example.com',
    'phone_number': '338-767-2159x4181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Scott',
    'Collin Anderson',
    'Samuel Taylor',
],
    'json': {
    'name': 'David Simon',
    'address': '18985 Jennifer Keys Apt. 071\nTeresaville, CA 73758',
},
    'key13864': 'value93367',
    'key5106': 'value48814',
    'key43715': 'value7004',
    'key94654': 'value10095',
    'key44992': 'value56855',
    'key96100': 'value41508',
    'key1015': 'value77345',
    'key33934': 'value30',
    'key78591': 'value60202',
    'key8273': 'value21953',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Mary Harris',
    'address': '71584 Jason Well Suite 308\nBrockhaven, GA 53204',
    'text': 'To low with. Seem certainly seat father want health.\nSpend visit main capital. Necessary federal campaign land kind remain street.\nHear win build throw find. Table gun up sign.',
    'email': 'xwest@example.net',
    'phone_number': '+1-937-946-0172x03012',
    'array_int_dynamic': [
    47316,
],
    'array_varchar_dynamic': [
    'Matthew Martinez',
    'Melissa Pacheco',
    'Steven Richardson',
    'Sarah Williams',
    'Chad Lopez',
    'Michael Garcia',
    'Devin Jackson',
    'Tammy Kane',
    'Gordon Rowe',
    'Ryan Lewis',
],
    'json': {
    'name': 'Patricia Porter',
    'address': '580 Lee Estate Apt. 226\nGreenchester, NJ 99586',
},
    'key97127': 'value21956',
    'key6408': 'value82843',
    'key46006': 'value25303',
    'key64239': 'value2719',
    'key2563': 'value71895',
    'key40450': 'value60079',
    'key96098': 'value84129',
    'key17582': 'value42755',
    'key63547': 'value20149',
    'key6596': 'value70821',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Allison Richards',
    'address': '344 John Canyon\nNicoleside, OK 51617',
    'text': 'Long probably always executive administration past hit. During set anything campaign.\nLight boy decision answer base tax course. Report drive those ok attorney news war.',
    'email': 'pkim@example.com',
    'phone_number': '343.267.7774x185',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Santiago',
    'Karen Patterson',
    'Jose Alexander',
    'Danielle Holmes',
    'Andrew Kelly',
    'Kathleen Hill',
    'Greg Lyons',
],
    'json': {
    'name': 'Jason Chung',
    'address': '9689 Patrick Garden Apt. 599\nHarrisside, IN 63334',
},
    'key30637': 'value53098',
    'key23506': 'value26425',
    'key65615': 'value65235',
    'key21483': 'value90444',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Anthony Simmons',
    'address': '58468 Ivan Run\nLake Katherinebury, OK 42987',
    'text': 'Spring already somebody animal station rather vote. Capital only around bed hold unit.\nTonight bank network religious family lay. Range reveal enter section ability all.',
    'email': 'brownjoe@example.com',
    'phone_number': '5606217373',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Henderson',
    'Todd Ford',
    'Michael Johnson',
    'Brian Harrington',
    'Susan Sanchez',
    'Amanda Hill',
    'Blake Lawrence',
    'Kevin Waters',
    'Kaylee Cunningham',
],
    'json': {
    'name': 'Brett Carpenter',
    'address': '970 Russell Fords Suite 452\nHarrisburgh, AR 46777',
},
    'key83895': 'value15190',
    'key84004': 'value68723',
    'key21625': 'value54723',
    'key45600': 'value49516',
    'key72502': 'value54391',
    'key57480': 'value44121',
    'key73906': 'value50833',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Leah Coleman',
    'address': '1648 Parrish Gardens Apt. 738\nSouth Erika, DE 43103',
    'text': 'Would through song attorney. Possible then drive decision. Might cover relate leader much despite practice. Reason alone forward forward ok nothing relate.',
    'email': 'kyle26@example.org',
    'phone_number': '673.523.6960x44035',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Barry Morales',
],
    'json': {
    'name': 'Kristen Powell',
    'address': '688 Donna Land Suite 809\nJeremiahville, ME 54539',
},
    'key37879': 'value17664',
    'key6203': 'value36641',
    'key14638': 'value22369',
    'key31511': 'value96376',
    'key86173': 'value50502',
    'key41766': 'value7419',
    'key8639': 'value33426',
    'key907': 'value52958',
    'key35902': 'value64087',
    'key94452': 'value81622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jesse Yates',
    'address': '561 Hodges Mountains\nSarahmouth, AS 48118',
    'text': 'Listen head feel part face similar draw. Author word place first lead stuff. Material energy Congress personal population prepare.',
    'email': 'sandraadams@example.org',
    'phone_number': '576-590-3682x6766',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Bright',
],
    'json': {
    'name': 'Kevin Tapia',
    'address': '675 Scott Forge Apt. 382\nStephanietown, IL 44898',
},
    'key88245': 'value59421',
    'key38969': 'value12974',
    'key70825': 'value9550',
    'key21775': 'value96972',
    'key22089': 'value51523',
    'key98999': 'value93606',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Hayley Bryan',
    'address': '91813 Ross Square Apt. 787\nBradstad, ND 70734',
    'text': 'Business mention exist central computer write goal. Method wife available relationship game skill.\nMember culture yes thought. Sister compare so foreign oil.',
    'email': 'jharris@example.net',
    'phone_number': '683-967-9072x75666',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mark Walters',
    'Rodney Holmes',
    'Andrea Boyer',
    'John Riggs',
    'Cindy Erickson',
    'Brittany Kaufman',
    'Jason Carroll',
    'Thomas Lee',
],
    'json': {
    'name': 'Steven Meyer',
    'address': '49644 Moore Locks\nNorth Jenniferville, ME 58341',
},
    'key58783': 'value79156',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jennifer Alvarado',
    'address': '05345 Lee Springs Suite 541\nEast Tammy, NH 21080',
    'text': 'Worker traditional music so or rest under raise. Rather reality include town beat level sound.\nRich TV than alone. Phone individual many husband.',
    'email': 'amy27@example.net',
    'phone_number': '456.355.9808',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Martin',
    'Eric Porter',
    'Donna Edwards',
    'Caleb Hall',
    'Marcia Nixon',
    'Andrew Short',
    'Juan Hoffman',
    'Suzanne Scott DDS',
],
    'json': {
    'name': 'Christopher Gardner',
    'address': '337 Peter Square\nWest Seanview, MD 34956',
},
    'key6637': 'value24422',
    'key63042': 'value47725',
    'key9069': 'value18770',
    'key32980': 'value34843',
    'key14378': 'value26968',
    'key81305': 'value9136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'John Leonard',
    'address': '2788 Jimenez Expressway Apt. 036\nLake Rebecca, CT 14871',
    'text': 'Generation employee case condition data street win. And particular beat occur.',
    'email': 'kingethan@example.net',
    'phone_number': '310.802.4095',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Logan',
    'Jeremy Robinson II',
    'Leslie Summers',
    'Franklin Dudley',
    'Shane Henry',
    'Melanie Lawrence',
],
    'json': {
    'name': 'Randy Benson',
    'address': '53504 Courtney Meadows Apt. 258\nJacobsshire, SC 87264',
},
    'key88108': 'value74135',
    'key52912': 'value9367',
    'key83790': 'value92134',
    'key44685': 'value55565',
    'key93911': 'value7328',
    'key61376': 'value22891',
    'key32066': 'value97938',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Frederick Baker',
    'address': 'PSC 3211, Box 1020\nAPO AE 48213',
    'text': 'Know market sit third physical another. Year thus response month maybe notice. New bill theory any.\nHave stage personal ask could.',
    'email': 'cynthiaroach@example.net',
    'phone_number': '001-734-789-1525x22219',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Wesley Gonzalez',
    'Jessica Thompson',
    'Patrick Gonzalez',
    'Jason James',
    'Elizabeth King',
    'Matthew Evans',
    'Casey Davis',
    'Nathaniel Giles',
    'Christopher Morrison',
],
    'json': {
    'name': 'Angela Castro',
    'address': '7699 Donna Common\nEast Andremouth, MT 74132',
},
    'key94816': 'value19606',
    'key28340': 'value91395',
    'key8259': 'value32234',
    'key35011': 'value45929',
    'key14800': 'value24124',
    'key97758': 'value56821',
    'key426': 'value81553',
    'key6726': 'value58407',
    'key91381': 'value61271',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Latasha Phillips',
    'address': '8963 Boyd Vista\nLake Frank, AR 95487',
    'text': 'City piece month science carry than management. Find recognize agency senior special point. Agent loss measure difference.\nWho may board baby. Believe environmental ability especially power.',
    'email': 'cjefferson@example.com',
    'phone_number': '622.650.7263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Michael Mata',
    'Joshua Meza',
    'Dean Edwards',
    'Heather Dean',
    'Rachel Wood',
    'Joshua Weiss',
],
    'json': {
    'name': 'Jennifer Zimmerman',
    'address': '5670 Cameron Crest Apt. 373\nPort Jamiemouth, MO 08668',
},
    'key9775': 'value35151',
    'key77112': 'value42955',
    'key87196': 'value40719',
    'key59849': 'value80532',
    'key48407': 'value23502',
    'key2851': 'value88723',
    'key20009': 'value3678',
    'key54384': 'value83442',
    'key82300': 'value30477',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Walter Dickerson',
    'address': '5955 Joshua Ramp\nPort Williamberg, VA 31141',
    'text': 'Tax artist seek guy learn movement. Edge run level require traditional consider. Yeah too today risk high gun prove.\nWhose week travel century nice.\nConcern lawyer long exactly ask sound money.',
    'email': 'jenniferacosta@example.com',
    'phone_number': '602-670-5878x6939',
    'array_int_dynamic': [
    7436,
],
    'array_varchar_dynamic': [
    'Linda Barnes',
    'Brandy Sanford',
    'Walter Johnston',
    'John Ayala',
    'Mark Fleming',
    'Nicole Franco',
    'Patricia Bonilla',
    'Courtney Manning',
    'Jose Smith',
],
    'json': {
    'name': 'Angela Turner',
    'address': '09607 Jennings Drive Suite 649\nTammyfurt, AS 23939',
},
    'key55707': 'value24171',
    'key31313': 'value1835',
    'key77257': 'value73119',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Matthew Pearson',
    'address': '546 Hester Causeway Suite 611\nJohnsonland, NM 46855',
    'text': 'Use important job someone attention. Economic receive moment matter expert air.\nDiscussion safe probably go. Commercial theory sport story hear buy yeah.',
    'email': 'xjackson@example.com',
    'phone_number': '(546)265-1179x6796',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Rodriguez',
    'Michael Mills',
    'Stephanie Wise',
    'Brett Smith III',
    'Monique Boyd',
    'Adam Lloyd',
],
    'json': {
    'name': 'Heather Nelson',
    'address': '80266 Robert Squares Apt. 562\nCoreyside, ME 73877',
},
    'key13596': 'value74679',
    'key74232': 'value92773',
    'key47887': 'value32869',
    'key74758': 'value58049',
    'key79190': 'value4471',
    'key21774': 'value89931',
    'key27746': 'value38336',
    'key24958': 'value20858',
    'key93070': 'value53015',
    'key7213': 'value69302',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Melissa Cole',
    'address': '4542 Livingston Squares Suite 568\nWest Michaelchester, MI 25942',
    'text': 'Meeting under walk race. Health choose film detail realize. A use federal dark collection college.',
    'email': 'jenniferhardy@example.com',
    'phone_number': '001-354-270-7164',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Martin',
    'Jessica Sanders',
    'Matthew Smith',
    'Martin Dickerson',
    'Beth Moore',
    'Carmen Duncan',
    'David Alvarez',
],
    'json': {
    'name': 'Sonya Romero',
    'address': '661 Derek Estates Apt. 406\nNorth Victoria, NM 67975',
},
    'key45456': 'value16933',
    'key65198': 'value11833',
    'key68506': 'value51374',
    'key46775': 'value27958',
    'key18005': 'value37088',
    'key1190': 'value99375',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Cynthia Walker',
    'address': '1874 Green Pike Suite 452\nMorganland, NE 25575',
    'text': 'Letter around budget consumer door night. Assume build information into all. Tell west record heart case meet arrive.',
    'email': 'fnunez@example.net',
    'phone_number': '(458)375-4976',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dustin Hamilton',
    'Sonya Beltran',
    'Alfred Stout',
    'Patricia Fitzpatrick',
    'Richard Lawson',
],
    'json': {
    'name': 'Monica Cook',
    'address': '791 Andrew Parkway Suite 764\nAlexisfurt, PR 15475',
},
    'key45856': 'value39383',
    'key93216': 'value98444',
    'key92373': 'value87795',
    'key9644': 'value34212',
    'key42507': 'value33069',
    'key63087': 'value62049',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Chelsea Lowe',
    'address': 'Unit 0149 Box 9450\nDPO AA 13225',
    'text': 'Out back bag dream compare face teach. Environment home cost report street child leader. Understand serious event specific home onto.',
    'email': 'james18@example.com',
    'phone_number': '927.648.2253x2742',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Foster',
    'Gary Leon',
    'Kara Jenkins',
    'Samuel Wilson',
    'Shannon Henderson',
],
    'json': {
    'name': 'Kimberly Miller MD',
    'address': '69313 Roberts Turnpike\nNorth Susan, IN 53885',
},
    'key20314': 'value32579',
    'key35627': 'value88562',
    'key2003': 'value57100',
    'key33406': 'value63907',
    'key39200': 'value38735',
    'key67133': 'value67842',
    'key38757': 'value39195',
    'key31908': 'value70247',
    'key34498': 'value98211',
    'key25220': 'value19479',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Tiffany Gordon',
    'address': 'USNS Rogers\nFPO AP 95568',
    'text': 'Stop performance main billion parent medical on. Century letter stuff explain center. Chair popular down goal.',
    'email': 'parnold@example.net',
    'phone_number': '412.425.9946',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jermaine Weber',
],
    'json': {
    'name': 'Steven Fernandez',
    'address': '15609 Gregory Islands\nEast Lauraton, KS 01910',
},
    'key39056': 'value43835',
    'key94962': 'value42316',
    'key41222': 'value93055',
    'key12729': 'value74081',
    'key3647': 'value94354',
    'key96925': 'value10018',
    'key23931': 'value88910',
    'key87428': 'value28962',
    'key86264': 'value35018',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jennifer Torres',
    'address': '4687 Adams Park\nLake Teresamouth, GU 95058',
    'text': 'Change one team fill conference. Too he serious imagine material light. Per mean defense baby clear.\nWait alone candidate she support. Factor away cut wear more.',
    'email': 'brucethompson@example.com',
    'phone_number': '2686926687',
    'array_int_dynamic': [
    16576,
],
    'array_varchar_dynamic': [
    'Ryan Castillo',
    'Bradley Baker',
    'Kevin Martinez',
],
    'json': {
    'name': 'Christopher Diaz',
    'address': 'USS Howell\nFPO AE 83887',
},
    'key31332': 'value30598',
    'key66855': 'value96861',
    'key51298': 'value67428',
    'key31414': 'value81498',
    'key83844': 'value33331',
    'key10052': 'value75044',
    'key13142': 'value66875',
    'key50444': 'value35676',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Brianna Le',
    'address': '361 Huff Forge Apt. 904\nHessburgh, RI 24406',
    'text': 'Ten bill study money performance onto. Claim thus use good follow sea. Appear generation building.',
    'email': 'theresatodd@example.org',
    'phone_number': '411-538-7541x41378',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Max Davis',
    'William James',
    'Adam Bailey',
    'Eric Ramirez',
    'Rebecca Davis',
    'Michael Smith',
    'Robert Murray',
    'Kevin Nicholson',
],
    'json': {
    'name': 'Tracy Thomas',
    'address': '7888 Woods Ford Suite 834\nLake Seanport, IL 31690',
},
    'key57580': 'value26458',
    'key44155': 'value14343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Blake Spencer',
    'address': '40801 Burch Port\nMathewstown, GA 65125',
    'text': 'May appear seven audience.\nSkill deal often. Industry part level might.',
    'email': 'robinsonrobert@example.net',
    'phone_number': '364.559.8828',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Scott Bradford',
    'Heather Morgan',
    'Julie Nguyen',
    'Kayla Patel',
    'Suzanne Brooks',
    'Matthew Anderson',
    'Eric Ferguson',
],
    'json': {
    'name': 'Amber Rogers',
    'address': '235 Elizabeth Pike Apt. 573\nTownsendshire, IA 49834',
},
    'key52890': 'value71737',
    'key25327': 'value7750',
    'key40063': 'value25270',
    'key87534': 'value32703',
    'key54390': 'value31407',
    'key61323': 'value77815',
    'key69855': 'value545',
    'key3276': 'value47511',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Joseph Gross',
    'address': '634 Clark Harbors Suite 283\nPort Angel, IN 91316',
    'text': 'These reduce maintain certainly truth contain. Pressure eat now now most issue. Poor job stock should.',
    'email': 'ashleywatson@example.org',
    'phone_number': '001-359-683-3404x1252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Debbie Rogers',
    'Joseph Olson',
    'Christian Parker',
    'Zachary Hall',
    'Richard Taylor',
    'Benjamin White',
    'Catherine Gomez',
    'Jennifer Palmer',
    'Alexis Miranda',
    'Margaret Knight',
],
    'json': {
    'name': 'Timothy Campbell',
    'address': '729 Fox Ferry\nWest Kimberly, VA 15921',
},
    'key16085': 'value23933',
    'key82206': 'value28703',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Tyler Smith',
    'address': '7832 Yoder Tunnel Apt. 595\nNorth Nicholas, AK 31103',
    'text': 'End call put side report check call. Southern trial dinner activity nothing low same.\nKid as age big. Daughter feel model way weight remain meet wear. I government start. Technology day fine table.',
    'email': 'erinmartin@example.com',
    'phone_number': '(855)488-2934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Abigail Stark',
    'Melanie Kirby',
    'Mark Downs',
    'Leslie Nguyen',
    'Frances Morrow',
    'Rebecca Meyer',
    'Catherine Nolan',
    'Dr. Noah Brown',
],
    'json': {
    'name': 'Jonathan Mcbride',
    'address': '1139 Elizabeth Lakes Suite 786\nKevinton, VT 77970',
},
    'key2144': 'value64407',
    'key50499': 'value40095',
    'key8373': 'value68100',
    'key91045': 'value15054',
    'key59726': 'value87548',
    'key12141': 'value19458',
    'key56551': 'value72572',
    'key59264': 'value24509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Calvin Mcclure',
    'address': '35791 Hansen Points\nNew Melissaville, AZ 41707',
    'text': 'Lawyer assume third someone city day. Less most around season. There drug region office without weight.',
    'email': 'jason77@example.net',
    'phone_number': '(363)754-9501x99543',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tina Henson',
    'Sean Thompson',
    'Ellen Wilson',
    'Mark Holmes',
    'Carrie Scott',
    'Katrina Harper',
    'Terry Moreno',
    'Patricia Everett',
],
    'json': {
    'name': 'Heather Lin',
    'address': '137 Javier Lakes\nLoriburgh, VA 38817',
},
    'key73620': 'value28442',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Raymond Pena',
    'address': '93092 Maynard Motorway Apt. 321\nJennaville, KS 11896',
    'text': 'Capital lawyer hour third time news. Debate four third over dinner surface participant.',
    'email': 'ebutler@example.org',
    'phone_number': '(210)460-9140x2795',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Rebekah Buchanan',
    'Scott Nash',
],
    'json': {
    'name': 'Frank Stephens DVM',
    'address': '5826 Flores Drive\nNorth Christopher, AS 58699',
},
    'key2167': 'value64726',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Stephen Donovan',
    'address': '30459 Dunn Squares\nGarrettfort, OK 92874',
    'text': 'Rule cause door meeting star action clear. Cause maintain western.\nRecently push class amount rather. Forward matter summer song. White between responsibility whom company while.',
    'email': 'sharon90@example.org',
    'phone_number': '001-598-910-9760x09996',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shane Keith',
    'William Russell',
    'Amy Sims',
    'Megan Livingston',
    'Ruth Adams',
    'Brandon Simmons',
    'James Duran',
    'Deborah Page',
    'Joshua Gomez',
],
    'json': {
    'name': 'Tommy Flores',
    'address': '5495 Banks Ferry\nEast Brittanyside, CA 54506',
},
    'key25102': 'value45023',
    'key32105': 'value75895',
    'key59870': 'value62911',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Michael Paul',
    'address': '585 James Way\nTroybury, ND 70414',
    'text': 'Treat government recently. Part west and truth. Blue option plan nearly.\nCoach sound blue through fall others feeling.',
    'email': 'molly30@example.com',
    'phone_number': '468-590-3280x05525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Austin Smith',
    'Krystal Camacho',
    'Kathleen Goodman',
    'Christopher Gilbert',
    'Shannon Nicholson',
    'Jessica Velasquez',
    'Tiffany Vega',
    'Debra Smith',
],
    'json': {
    'name': 'James Hall',
    'address': '5924 Debbie Square\nRyanport, MP 39164',
},
    'key7972': 'value41009',
    'key93895': 'value90070',
    'key4949': 'value44234',
    'key5731': 'value83730',
    'key24640': 'value12978',
    'key64784': 'value29729',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Sandra Ferguson',
    'address': '7232 Greer Summit Suite 290\nNorth Danielmouth, CO 29482',
    'text': 'Store rock factor debate. Actually cup well significant perform.',
    'email': 'brewerdebra@example.net',
    'phone_number': '230.545.6311',
    'array_int_dynamic': [
    31838,
],
    'array_varchar_dynamic': [
    'Kathryn Smith',
],
    'json': {
    'name': 'Alan Palmer',
    'address': '69748 Coffey Tunnel Suite 738\nLake Donnaton, ID 49019',
},
    'key34057': 'value32797',
    'key67221': 'value26717',
    'key81500': 'value40595',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Michael Rivas',
    'address': '62146 Amanda Way Apt. 466\nLake Tracey, AK 22021',
    'text': 'Material together walk huge police toward.\nCivil learn design audience during story manager. Tell leg subject all soldier impact summer. Perhaps increase executive against.',
    'email': 'edavid@example.com',
    'phone_number': '(443)405-7112',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Clifford Frank',
    'Anthony Strong',
    'Andrea Schneider',
    'Kimberly Klein',
    'Jessica Allen',
],
    'json': {
    'name': 'Tabitha Coleman',
    'address': '732 Peter Loop Suite 339\nNorth Roberttown, MA 20516',
},
    'key13379': 'value53604',
    'key70964': 'value60660',
    'key24968': 'value65470',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Travis Collins',
    'address': '114 Miller Rue Apt. 884\nSouth Robert, MA 01020',
    'text': 'Power clearly lot collection color produce turn top. Tough bed out quickly.',
    'email': 'gregoryandrews@example.net',
    'phone_number': '450.448.0225',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Erin Horn',
    'Sandra Scott',
    'Ruth Lee',
    'Brandon Long',
    'Deborah Adams',
],
    'json': {
    'name': 'Michael Thomas',
    'address': '7402 Melissa Manors Suite 929\nCampbellland, NC 57511',
},
    'key96788': 'value63525',
    'key90770': 'value43753',
    'key33933': 'value40488',
    'key32313': 'value18566',
    'key45272': 'value37572',
    'key77424': 'value35513',
    'key13269': 'value41813',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sheryl Sims',
    'address': '19009 Hunter Vista\nEast Kendrafurt, MH 88322',
    'text': 'Than method series say every. Direction station meet student deal would treat.\nSave need mother. Choice meet provide establish news. Institution film assume member.',
    'email': 'carlsonphilip@example.com',
    'phone_number': '946.369.3686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Caitlin Arias',
    'Sandra Chan',
],
    'json': {
    'name': 'David Schneider',
    'address': '2637 Gina Lake\nSteelebury, OR 22756',
},
    'key43002': 'value87442',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Michelle Foster',
    'address': '2914 Mcpherson Tunnel Suite 075\nTurnerstad, MD 64338',
    'text': 'Identify could seem.\nCongress situation song they out nothing. Way knowledge support score full. Turn truth situation area.',
    'email': 'tanya81@example.net',
    'phone_number': '+1-335-906-9008x466',
    'array_int_dynamic': [
    35958,
],
    'array_varchar_dynamic': [
    'Amy Long',
    'Dakota Reid',
    'Kyle Powers',
    'Brittany Armstrong',
    'Caleb Riley',
    'Ryan Wood',
    'Henry Phillips',
    'Dalton Carson',
],
    'json': {
    'name': 'Craig Parrish',
    'address': '92171 Fleming Turnpike Suite 748\nYvonneburgh, AZ 62890',
},
    'key82654': 'value80271',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Carly Douglas',
    'address': '288 Johnson Square Suite 391\nEast Victoriachester, NM 93444',
    'text': 'Institution suddenly rule view military.\nSpecific must total discuss national customer. Policy seat leader consider.',
    'email': 'douglasjacob@example.com',
    'phone_number': '6945369296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Hendricks',
    'Lance Fry',
    'Douglas Wong',
],
    'json': {
    'name': 'Derek Pierce',
    'address': 'Unit 3233 Box 2097\nDPO AA 94446',
},
    'key9195': 'value7729',
    'key29227': 'value38135',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Michael Pearson',
    'address': '4715 Daniel Drives\nZunigatown, RI 10972',
    'text': 'Capital move really later purpose option market professor. Partner health since prove contain business heart. Make hour campaign ability face answer education.',
    'email': 'hollyhansen@example.org',
    'phone_number': '+1-907-637-0633x7980',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jake Osborne',
    'John Barnes',
],
    'json': {
    'name': 'Melissa Cain',
    'address': '230 Matthew Pines Suite 716\nPort James, MT 30400',
},
    'key12626': 'value91945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Travis Horn',
    'address': '221 Johnson Pike\nEast Benjaminshire, UT 20526',
    'text': 'Hit impact necessary live popular next growth. Responsibility including her step paper police.\nInstead ask walk which fish need goal become. Simply soon plant important.',
    'email': 'kathy31@example.net',
    'phone_number': '001-925-764-9794x194',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christina Thompson',
    'Mr. Francisco Nelson MD',
    'Jennifer Freeman',
    'Luis Stevens',
    'Michael West',
    'Mary Porter',
    'Erik Anderson',
    'Casey Sims',
    'Randall Brown',
],
    'json': {
    'name': 'James Lang',
    'address': '937 Miller Trafficway\nNorth Randy, PR 89125',
},
    'key14542': 'value92662',
    'key51815': 'value89349',
    'key2642': 'value82270',
    'key17433': 'value55209',
    'key55268': 'value78042',
    'key85304': 'value81611',
    'key35309': 'value27640',
    'key36516': 'value6940',
    'key68286': 'value50265',
    'key91690': 'value91103',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Michael Robinson',
    'address': '67241 Hamilton Branch Apt. 762\nPort Mirandashire, MS 65004',
    'text': 'Factor agency most fact development. Safe computer always exist along.\nFast gas prevent adult relationship story.\nAll those again. Speak person professor there. Who at owner we area skin.',
    'email': 'nicole58@example.net',
    'phone_number': '+1-966-446-4146x1363',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Johnson',
    'Mary Anderson',
    'David Berry',
    'Mark Dunn Jr.',
    'Brenda Booker',
    'Keith House',
    'Mary Martinez',
    'Rebecca Torres',
    'Michael Kerr',
    'Karen Murphy',
],
    'json': {
    'name': 'Corey Gardner',
    'address': '07559 Jason Brooks Apt. 868\nAshleystad, MS 30810',
},
    'key92004': 'value52572',
    'key76090': 'value98089',
    'key17358': 'value19694',
    'key28544': 'value46841',
    'key4198': 'value80746',
    'key65377': 'value29641',
    'key52610': 'value6065',
    'key9689': 'value1195',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Heather Barron',
    'address': '85660 Robin Field\nCalebfort, VI 58260',
    'text': 'Kitchen hour energy president seven. Nearly significant whether challenge music up admit. Conference them international.\nBecome body letter strategy who born. Believe trouble society.',
    'email': 'milesjamie@example.org',
    'phone_number': '001-212-387-2074x239',
    'array_int_dynamic': [
    20473,
],
    'array_varchar_dynamic': [
    'Matthew Carter',
    'Donna Salazar',
    'Crystal Brown',
    'Vincent Smith',
    'Diana Peterson',
],
    'json': {
    'name': 'John Williams',
    'address': '5759 Barrett Expressway\nEast Robert, MT 94777',
},
    'key15073': 'value71910',
    'key47679': 'value23115',
    'key74393': 'value55059',
    'key67033': 'value7406',
    'key26932': 'value43400',
    'key73768': 'value26968',
    'key67802': 'value36689',
    'key25577': 'value72693',
    'key91485': 'value13579',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Charlotte Robinson',
    'address': '09289 Parker Knoll\nSalazarburgh, AL 23655',
    'text': 'Store be short federal realize reveal trouble. Because paper people drop. Return black old child last necessary another.',
    'email': 'nbarr@example.com',
    'phone_number': '(287)664-6520x233',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Young',
],
    'json': {
    'name': 'Gregory Flores',
    'address': '715 Gerald Court\nEast Jacobside, IN 12306',
},
    'key71675': 'value93214',
    'key40779': 'value85243',
    'key5016': 'value64415',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Nathan Bennett',
    'address': '1845 Barker Spur\nWest Leonard, AZ 41819',
    'text': 'Pressure business house heavy move region.\nNational knowledge see successful field stop network accept. Your computer no professor investment. Ability behavior page safe.',
    'email': 'whitethomas@example.org',
    'phone_number': '+1-574-435-0221x46707',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Craig Daugherty',
    'Fernando Nelson',
    'Michelle Day',
    'Yesenia Johnson',
    'Michael Watson',
    'Brandon Martinez',
    'Angela Lane',
    'Megan Sanchez',
    'Gary Meyer',
],
    'json': {
    'name': 'Erik Thompson',
    'address': '8927 Austin Drive\nSouth Mariaberg, ND 68984',
},
    'key25237': 'value83351',
    'key37641': 'value90527',
    'key71343': 'value46595',
    'key28136': 'value58198',
    'key75504': 'value10909',
    'key18087': 'value13058',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Casey Stokes',
    'address': '5771 Lee Ville Suite 276\nMichaelmouth, SD 14746',
    'text': 'Space music opportunity despite small culture a enough. Ten operation address mouth item. Certain recent fill newspaper perform often.',
    'email': 'mortonevelyn@example.net',
    'phone_number': '+1-239-851-7499x948',
    'array_int_dynamic': [
    84626,
],
    'array_varchar_dynamic': [
    'Mathew Garcia',
    'Andrew Washington',
    'Ashley Murphy',
    'Brandy Cook',
    'Spencer Mccarty',
    'Cynthia Stone',
    'Colton Bass',
],
    'json': {
    'name': 'Molly Bowen',
    'address': '538 Steven Mill\nWest Jesse, RI 17038',
},
    'key9469': 'value76602',
    'key86957': 'value33553',
    'key63812': 'value71444',
    'key62561': 'value43718',
    'key6918': 'value49121',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Paul Flores',
    'address': '3874 Morgan Parkways\nCabreraport, OK 05699',
    'text': 'Quite wait rock. Four individual response owner of.\nResearch both identify media. Produce why moment picture. Economic choice agency fire key kid.',
    'email': 'kingcraig@example.net',
    'phone_number': '921.338.6759x31231',
    'array_int_dynamic': [
    87107,
],
    'array_varchar_dynamic': [
    'Amanda Lucas',
    'Michael Ward',
    'Gabriela Briggs',
    'Jennifer Hamilton',
    'Shannon Kennedy',
    'Molly Bowen',
    'Deborah Robinson',
],
    'json': {
    'name': 'Brandon Martin',
    'address': '844 Jeffrey Spurs\nNorth Susanton, IA 18873',
},
    'key79295': 'value17680',
    'key62835': 'value7597',
    'key47319': 'value71084',
    'key73632': 'value53650',
    'key23456': 'value736',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Jonathan Henson',
    'address': '082 Kathleen Heights Suite 468\nSalazarport, IN 55653',
    'text': 'Cause find citizen boy phone identify. Near everyone policy. Power decision my green kind participant it civil.',
    'email': 'zbrooks@example.org',
    'phone_number': '(501)884-9988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Thompson',
    'Kevin Lewis',
    'Christian Patel',
    'Jacob Robinson',
    'Christopher Johnson',
    'Alexander Gould',
    'Shannon Diaz',
],
    'json': {
    'name': 'Anthony Walter',
    'address': '19700 Victoria Pike Suite 723\nPort Denise, WA 26412',
},
    'key99652': 'value21079',
    'key50892': 'value25329',
    'key56866': 'value35512',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Anna Parker',
    'address': '244 Andrew Light\nWest John, MN 72442',
    'text': 'Agreement arrive radio. Become store a thousand smile. Charge apply game available everybody explain fight.\nWhen thing director she security become executive. Tax tend sense Republican market enough.',
    'email': 'johnchoi@example.com',
    'phone_number': '987.890.0942',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jillian Wong',
    'Noah Conrad',
    'James Martinez',
    'Brent Nunez',
    'Lisa Ford',
    'Leslie Livingston',
    'Kathleen Snyder',
    'Melissa Turner',
    'Amanda Garza',
],
    'json': {
    'name': 'Heather Kramer',
    'address': '9514 Quinn Falls Apt. 515\nNew Margaretshire, NJ 29793',
},
    'key19856': 'value13384',
    'key75811': 'value97114',
    'key57946': 'value70476',
    'key93839': 'value1582',
    'key8738': 'value72734',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Sara Rivera',
    'address': '5879 Vasquez Lodge Suite 766\nNorth Michaelfort, SD 85058',
    'text': 'Expect cover line want.\nStrong hard why stage arm. Fill mean reflect analysis strategy partner consider.\nCharge safe do car too. Offer light type. Meeting within fill.',
    'email': 'danielleswanson@example.org',
    'phone_number': '001-976-533-1916x22741',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alejandro Stafford MD',
    'Michelle Bishop',
    'Angela Jones',
    'Timothy Lawrence',
    'Meghan Oneill',
    'Yolanda Jones',
    'Brooke Brown',
    'Teresa Hoover',
    'Brad Cook',
],
    'json': {
    'name': 'Joseph Werner',
    'address': '59329 Emily Rapid\nCartershire, IN 72180',
},
    'key15652': 'value35838',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Anthony Rasmussen',
    'address': '6576 Austin Fields Suite 482\nLeebury, NY 79392',
    'text': 'Something lawyer arm grow. Role bit not enjoy police.\nWindow matter doctor. Create guess fast opportunity subject. Arm accept anything above remember your.\nBill law everything hospital improve.',
    'email': 'allenjamie@example.org',
    'phone_number': '788.738.2112x76617',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Allen Bell',
    'Sandra Maynard',
    'Ronald Salazar',
    'Dr. Thomas Bullock',
    'Raymond Owens',
    'Amanda Donovan',
    'Troy Conway',
    'Rachel Young',
],
    'json': {
    'name': 'Malik Carney',
    'address': '652 Brandy Place Suite 903\nPort Karenchester, OH 13476',
},
    'key7628': 'value46033',
    'key33106': 'value72119',
    'key38279': 'value23352',
    'key76270': 'value64120',
    'key58952': 'value42952',
    'key9406': 'value980',
    'key85326': 'value50867',
    'key668': 'value51780',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'John King',
    'address': 'Unit 1316 Box 9152\nDPO AP 02687',
    'text': 'Civil service baby begin bring. Put growth bag safe. Star shoulder kid loss.\nCover alone north agency tell. Our sell exactly Congress how challenge. Central be from.',
    'email': 'rivasrebecca@example.org',
    'phone_number': '944.288.4776x198',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Goodman',
    'Clayton Hicks',
    'Jeffrey Powell',
],
    'json': {
    'name': 'Emily Payne',
    'address': '70609 Jason Hill Suite 881\nSouth Kaylahaven, CO 32398',
},
    'key5103': 'value1882',
    'key40418': 'value9156',
    'key57893': 'value66925',
    'key36399': 'value42866',
    'key3109': 'value79569',
    'key59496': 'value61484',
    'key68851': 'value81293',
    'key99936': 'value92762',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'James Tran',
    'address': '169 White Landing Apt. 151\nThompsonstad, SD 48462',
    'text': 'That reflect more agree. Successful particular hot food improve. Turn manager off surface me identify fly.\nEntire plan something cause.\nJoin southern probably not either.',
    'email': 'youngronald@example.org',
    'phone_number': '+1-910-665-5608x9028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robert Buckley',
    'Lauren Elliott',
    'Olivia Larson',
    'Charles Powell',
    'Alejandro Rios',
    'Juan Wise',
    'Christopher Hayes',
    'Brenda Warner',
],
    'json': {
    'name': 'Tamara Williams',
    'address': '26259 Dennis Brook\nCalderonview, CO 96190',
},
    'key9299': 'value45969',
    'key20201': 'value86169',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Matthew Koch',
    'address': '473 Thompson Street\nWest Codyview, RI 98167',
    'text': 'With across later out message certainly land. Response both stage sure.\nCentral heart recent wait shoulder safe finish. Leg small rather. During social development perhaps information who.',
    'email': 'anthony45@example.org',
    'phone_number': '740.568.7839x784',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Karen Brown',
    'Amy Scott',
    'Alicia Richmond',
    'Monica Faulkner',
    'Robert Smith',
    'Martin Castillo',
    'Susan Richardson',
    'Joshua Mcclain',
    'Robert Brown',
    'Cynthia Peters',
],
    'json': {
    'name': 'Sheryl Davis',
    'address': '2251 Oliver Mountain\nElizabethville, FM 54756',
},
    'key13978': 'value63715',
    'key78336': 'value72601',
    'key62533': 'value50798',
    'key43550': 'value51000',
    'key10498': 'value3377',
    'key16679': 'value39504',
    'key15048': 'value76928',
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
    'RequestId': '26d2036f-62f1-11f0-bfb4-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_40_350775VufEEPlg',
    'filter': 'uid >= 0',
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
    'RequestId': '2017135c-62f1-11f0-bdea-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_40_350775VufEEPlg',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid >= 0]_1752744832.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid01752744832Json()
    test.run_tests()
