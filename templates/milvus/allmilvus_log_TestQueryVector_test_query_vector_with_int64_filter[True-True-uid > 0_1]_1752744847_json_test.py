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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_1]_1752744847_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_1]_1752744847.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid011752744847Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_1]_1752744847.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_1]_1752744847.json"
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
    'RequestId': '280f8453-62f1-11f0-8bf0-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_53_722999BfOwoAvv',
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
    'RequestId': '2b2e12d2-62f1-11f0-9815-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_53_722999BfOwoAvv',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Michael Harris',
    'address': '856 Molly Fords\nWest Darrellview, UT 33062',
    'text': 'Clear color sing work little read word community. Affect rich continue knowledge government stay. Specific game image magazine despite.',
    'email': 'kathleenlarson@example.net',
    'phone_number': '(798)265-9084x74451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Elliott',
    'Edward Chang',
],
    'json': {
    'name': 'Andrea Smith',
    'address': '1314 Taylor Motorway Suite 273\nKellerstad, AL 46871',
},
    'key5914': 'value24056',
    'key85531': 'value7615',
    'key86026': 'value3844',
    'key92365': 'value80158',
    'key78546': 'value62682',
    'key10459': 'value66000',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Sally Jimenez',
    'address': 'USCGC Lee\nFPO AE 96030',
    'text': 'Media save reason fly.\nMuch market newspaper tough tax. Fly agency debate tree summer group blood. Eye color example choice.',
    'email': 'mochoa@example.net',
    'phone_number': '(647)611-2247x80613',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Thomas',
    'Tiffany Roberts',
    'Marcia Young',
    'Michael Guerrero',
    'Rebecca Dunn',
    'Devin Castro',
    'Sara Lucero',
],
    'json': {
    'name': 'Juan Russell',
    'address': '4840 Alyssa Valleys\nDaisyfort, CA 72842',
},
    'key75719': 'value6558',
    'key82331': 'value48189',
    'key2384': 'value1943',
    'key40608': 'value93431',
    'key49213': 'value15583',
    'key63909': 'value72982',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Brandon Rice',
    'address': '1821 Kirk Creek\nLake Cindyborough, IL 41856',
    'text': 'Rule parent memory do. Note protect like than sea.\nDraw lose of seek study partner participant. Rich when join work above. Thing page land lot like material Congress you.',
    'email': 'ricardomay@example.net',
    'phone_number': '2548734836',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Laura Walker',
    'Natasha Wilson',
    'Joseph Stephens',
    'Kathryn Garza',
    'Christopher Wolfe',
    'Benjamin Hobbs',
],
    'json': {
    'name': 'Gary Townsend',
    'address': '95136 Miller Drive Suite 014\nNew Zachary, AL 66104',
},
    'key98147': 'value14079',
    'key90456': 'value1124',
    'key60314': 'value49105',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Victoria Mason',
    'address': '780 Blankenship Court Apt. 034\nPort Edwardchester, ID 15088',
    'text': 'Third lot ok about discover seven condition. Road three positive.\nAgency quickly address condition culture campaign. Produce husband certainly citizen eat out account pretty. Theory law line.',
    'email': 'osmith@example.net',
    'phone_number': '217-586-9055x623',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Lutz',
    'Ryan Roberts',
    'Sean Mcdaniel',
    'Erica Taylor',
    'Richard Nguyen',
],
    'json': {
    'name': 'Crystal Mason',
    'address': '7343 Palmer Walks Apt. 188\nJosefort, WV 96037',
},
    'key51722': 'value35818',
    'key55360': 'value43931',
    'key80192': 'value47608',
    'key28817': 'value43964',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Rhonda Foster',
    'address': '116 Deborah Grove\nWest Willieport, OK 51478',
    'text': 'Against beautiful late successful thank quality property. Down after daughter center this southern recent.\nThat affect hospital final. Class offer stock production people prevent. Yes own kid air.',
    'email': 'christinaelliott@example.com',
    'phone_number': '289-435-7430',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alexandria Garrett',
    'Angela Beard',
    'Jennifer Briggs',
    'Elizabeth Rodgers',
    'James Brown',
    'Edward Ward',
    'Sarah Sanchez',
    'Madison Molina',
    'Patricia Rivas',
],
    'json': {
    'name': 'Jennifer Jones',
    'address': '75992 Williams Estate Suite 109\nGonzalesberg, NE 34440',
},
    'key23430': 'value18135',
    'key24063': 'value6963',
    'key25589': 'value2553',
    'key44217': 'value53319',
    'key33559': 'value74017',
    'key11549': 'value51395',
    'key97685': 'value94037',
    'key32248': 'value25047',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Diana King',
    'address': '5330 Taylor Dale\nWest Heather, MH 37424',
    'text': 'Way accept dark point. Mean board nature word test party good.\nHere quite listen economy. Result PM who rather already help or nice. Available future oil catch article land.',
    'email': 'morganallison@example.net',
    'phone_number': '(823)462-8774x126',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Shepard',
    'Miguel Noble',
    'Stephanie Carlson',
    'Patricia Dillon',
    'Brandon Kirk',
    'Scott Herrera',
    'Shane Wright',
    'Courtney Harrington',
    'Stephen Molina',
],
    'json': {
    'name': 'Harry Bruce',
    'address': 'USNV Jones\nFPO AP 03175',
},
    'key70764': 'value5707',
    'key14141': 'value35483',
    'key25219': 'value94673',
    'key47442': 'value72418',
    'key46220': 'value49679',
    'key41495': 'value73810',
    'key12437': 'value62916',
    'key3268': 'value47089',
    'key84053': 'value31292',
    'key13524': 'value12125',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Jeffrey Bender',
    'address': '19297 Jessica Points Apt. 431\nPowellburgh, NC 26257',
    'text': 'Water responsibility energy around soon west career. Wall society current take education. Tend force plan always thank military three.',
    'email': 'mwilson@example.com',
    'phone_number': '001-898-533-8608x865',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Marissa Cobb',
    'Michelle Harmon',
    'Jacob Vega',
    'Kyle Cox',
    'Paula Johnson',
    'Patty Carr',
],
    'json': {
    'name': 'Madison Blair',
    'address': '98413 Eric Port Apt. 956\nNew Cynthia, PA 02118',
},
    'key90665': 'value51738',
    'key74727': 'value45280',
    'key7294': 'value35397',
    'key9290': 'value51877',
    'key45898': 'value97806',
    'key52623': 'value85682',
    'key28903': 'value71871',
    'key87106': 'value57313',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Nancy Mckay',
    'address': '98969 Salazar Place\nOrrberg, NY 57394',
    'text': 'Once per home true red go so. Similar effort join price plant leg newspaper.\nStage customer discuss society machine. Establish stay run attack. Keep society similar participant close painting what.',
    'email': 'joseph55@example.net',
    'phone_number': '939-962-4712',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brian Snyder',
    'Courtney Garcia',
    'Karen Cortez',
    'Carolyn Singh',
    'Megan Francis',
    'Kristina Guerra',
    'Larry Brown',
    'Mr. Brandon James',
    'Michael Gray',
    'Jason Zavala',
],
    'json': {
    'name': 'Brenda Cruz',
    'address': '729 Moore Pines\nLake Melissaland, NM 04976',
},
    'key97722': 'value54009',
    'key25923': 'value8170',
    'key77980': 'value28097',
    'key57394': 'value45442',
    'key20337': 'value55536',
    'key10500': 'value9148',
    'key7452': 'value37182',
    'key92132': 'value62990',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Mary Randolph',
    'address': '57007 Adam Ferry\nJasonview, IN 30312',
    'text': 'At miss dark great hotel stage thank. Them together piece drop leg.\nBoard partner during citizen. Everyone other cover. Trip night vote expert quickly which add myself.',
    'email': 'johnbell@example.net',
    'phone_number': '680-893-0481x0948',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Burgess',
    'Julie Cummings',
    'Christopher Watkins',
    'Mary Walker',
    'Brian Parsons',
    'Mark Anderson',
    'Joyce Page',
    'Alexander Morales',
    'Jeanne Green',
    'Kimberly Davis MD',
],
    'json': {
    'name': 'Autumn Duncan',
    'address': 'PSC 0370, Box 5220\nAPO AE 02797',
},
    'key66608': 'value12606',
    'key67746': 'value16687',
    'key2127': 'value56731',
    'key72975': 'value77682',
    'key8187': 'value28462',
    'key44244': 'value53722',
    'key21796': 'value81874',
    'key18019': 'value9394',
    'key42049': 'value90971',
    'key33471': 'value17472',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Marie Benson',
    'address': '856 Tamara Coves Apt. 037\nWest Danny, WY 01484',
    'text': 'President region reason recognize meeting whatever. Trip life police hundred television line deep. Employee process some.\nClass chair be up between. Music culture through.',
    'email': 'zcruz@example.net',
    'phone_number': '871.534.3023x1775',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brandon Goodwin',
    'Willie Le',
    'Jennifer Anthony',
    'Lance Hobbs',
    'Michael Saunders',
    'Meghan Brown',
],
    'json': {
    'name': 'Tammy Martinez',
    'address': '55756 Dodson Heights Suite 851\nTammyberg, MD 03626',
},
    'key5919': 'value57436',
    'key60559': 'value11804',
    'key55655': 'value63217',
    'key54214': 'value81623',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Denise Sanchez',
    'address': '43762 Scott Plaza\nNew Thomas, MS 37077',
    'text': 'Program policy speech bed picture view. Attention last course hotel.\nBeautiful inside meeting both group agree well never. Meeting area partner. Program three forward bit writer little.',
    'email': 'davidsoncarolyn@example.org',
    'phone_number': '455.546.2155',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marc Williams',
    'Anne Davis',
    'Kimberly Wiley',
    'Chris Park',
    'Mark Smith',
    'James White',
    'Sierra Vaughan',
    'Maria Lopez',
],
    'json': {
    'name': 'Brenda Perez',
    'address': '3120 Perkins Green Suite 509\nMichaelaview, AS 94515',
},
    'key71225': 'value1373',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Christopher Mata',
    'address': '53652 Jennifer Fords\nPort Richard, DC 13652',
    'text': 'Attack foot order whose marriage thus. Almost move mention back place nation machine.\nAbility nature in kitchen talk pretty. Box give similar serve ago. Pretty option poor hold nice successful back.',
    'email': 'bgonzalez@example.com',
    'phone_number': '(332)798-2887',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Wesley Daniels',
    'Steven Henderson',
],
    'json': {
    'name': 'Joseph Kennedy',
    'address': 'USCGC Miller\nFPO AA 73305',
},
    'key5383': 'value86726',
    'key20696': 'value45695',
    'key24641': 'value64623',
    'key49175': 'value20289',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'James Booth',
    'address': '5848 Benjamin Square Suite 757\nNew Thomasfurt, MH 59349',
    'text': 'Low member strategy body improve sense political. Good town clearly course. White family wait light she great herself little.',
    'email': 'newmanmichael@example.com',
    'phone_number': '+1-895-726-8718x3717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Trevor Weaver',
    'Anna Smith',
],
    'json': {
    'name': 'Tim Carlson',
    'address': '901 David Ford Apt. 239\nMcguireland, UT 01700',
},
    'key99839': 'value37667',
    'key54488': 'value97872',
    'key45362': 'value88000',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Teresa Berry',
    'address': '5456 Monique Heights Suite 906\nWest Karenland, PR 85058',
    'text': 'Use somebody great leader medical letter. Tv marriage investment subject from range. Human property middle hot ok television better find.\nSeat show author. Personal many line health Mrs.',
    'email': 'pcox@example.com',
    'phone_number': '618-656-4156',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Moore',
    'Hannah Love',
    'John Murray',
],
    'json': {
    'name': 'Nicole Lyons',
    'address': '2110 Timothy View\nSarastad, AZ 26523',
},
    'key39677': 'value6398',
    'key80740': 'value3229',
    'key1899': 'value78207',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Dylan Dalton',
    'address': '07831 Jesse Spring\nSouth Brendafort, AL 79562',
    'text': 'Find before amount might foreign. Child day detail red. Personal trial would care why point owner year.\nMean hundred determine probably by TV account.',
    'email': 'igray@example.com',
    'phone_number': '001-906-685-4210x985',
    'array_int_dynamic': [
    69455,
],
    'array_varchar_dynamic': [
    'Deborah White',
    'James Jordan',
    'Frank Lopez',
],
    'json': {
    'name': 'Donald Estrada',
    'address': '11285 Montgomery Tunnel\nNew Jenniferberg, MI 59604',
},
    'key94104': 'value82474',
    'key48764': 'value71209',
    'key18607': 'value17924',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'James Munoz',
    'address': '997 Steven Coves Suite 924\nWashingtonfurt, NY 84263',
    'text': 'Reason both fly chance north bad reality approach. Option sister area few bad picture.\nHear stock bring high. More cover soon security throw everything.',
    'email': 'bakerronald@example.com',
    'phone_number': '(632)537-3042x024',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Karl Schwartz',
    'James Cummings',
    'Olivia Perez',
    'Matthew Hill',
    'Paula Gibson',
    'Gregory Parks',
    'Phillip Morrison',
    'Mark Taylor',
],
    'json': {
    'name': 'Wendy Martin',
    'address': 'PSC 5220, Box 6064\nAPO AA 20722',
},
    'key66246': 'value49540',
    'key41381': 'value39999',
    'key38105': 'value89272',
    'key38070': 'value63762',
    'key57415': 'value82107',
    'key1217': 'value68473',
    'key84869': 'value89792',
    'key48650': 'value72455',
    'key36812': 'value20341',
    'key99521': 'value4724',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Angela Powell',
    'address': '5426 Benjamin Ridges Apt. 052\nSouth Ryan, IA 52754',
    'text': 'Player magazine evidence ability book feeling if quality. Fall white language miss. Physical officer last.',
    'email': 'washingtondanielle@example.org',
    'phone_number': '001-365-847-1775x414',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'William Miller',
    'Clarence Kent',
    'Lisa Peterson',
    'Brandi Lynn',
],
    'json': {
    'name': 'Connie Robinson',
    'address': '50494 Paul Canyon\nLake Raymond, SC 59224',
},
    'key3160': 'value19946',
    'key51604': 'value8643',
    'key87897': 'value5855',
    'key79309': 'value72751',
    'key97634': 'value93588',
    'key24857': 'value7131',
    'key20496': 'value31706',
    'key52179': 'value59734',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Kaitlin Murray',
    'address': '445 David Inlet\nNorth Michael, GA 79753',
    'text': 'Need recent talk account until. Lay water door community reality author.\nCertain step message adult. Subject somebody newspaper fine into moment brother.\nTurn seat picture.',
    'email': 'brian89@example.net',
    'phone_number': '661.653.8755x4677',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'William Johnson',
],
    'json': {
    'name': 'Craig George',
    'address': '05520 Jorge Mission\nLake Justinmouth, VA 26839',
},
    'key11998': 'value40009',
    'key8124': 'value78813',
    'key35302': 'value22952',
    'key99982': 'value55626',
    'key45119': 'value90594',
    'key48955': 'value46111',
    'key98904': 'value15879',
    'key84097': 'value67106',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Christopher Brennan',
    'address': '362 Kylie Land Suite 878\nMartinport, MT 95577',
    'text': 'Beyond special behind property. Degree some create happen lay activity movement. Perhaps action nearly full. Team room situation foreign game president across church.',
    'email': 'michael00@example.com',
    'phone_number': '829.311.7026x22450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Carpenter',
    'Linda Johnson',
    'Nicholas Webb',
    'Beverly Bowman',
    'Kevin Finley',
    'Joshua Trujillo',
    'Jessica Guzman',
    'James Rodriguez',
],
    'json': {
    'name': 'Tracey Ross',
    'address': '53706 Fleming Square\nEast Brittanyburgh, OH 04755',
},
    'key40193': 'value26617',
    'key63210': 'value45626',
    'key10126': 'value86439',
    'key49919': 'value94986',
    'key75904': 'value33404',
    'key21769': 'value81427',
    'key19181': 'value20815',
    'key77445': 'value51962',
    'key389': 'value74976',
    'key87309': 'value67082',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Anthony Melendez',
    'address': '891 Hayley Isle\nDavidshire, DE 18032',
    'text': 'Tough serious chair fight as response beyond national. Suddenly there feeling form step recently.',
    'email': 'travissims@example.com',
    'phone_number': '359.834.1801x33354',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Glenn',
    'Maria Davis',
    'Mark Johnson',
    'Michelle Perez',
    'Amanda Bell MD',
    'Daniel Levy',
    'Christina Watts',
    'Elizabeth Yoder',
    'Diana Rhodes',
],
    'json': {
    'name': 'Thomas Sawyer',
    'address': '2376 Jennifer Shoals\nSouth Virginia, SC 41025',
},
    'key70272': 'value56902',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Frank Zavala',
    'address': '50722 Richard Mountain Suite 496\nMarkfort, CO 85452',
    'text': 'Create responsibility various candidate paper. Base another everyone despite. Here become why as.\nUs political two series or. Produce throw develop.',
    'email': 'millerlee@example.com',
    'phone_number': '001-977-508-0468x5332',
    'array_int_dynamic': [
    38078,
],
    'array_varchar_dynamic': [
    'Dawn Miller',
],
    'json': {
    'name': 'Anne Perez',
    'address': 'Unit 0633 Box 7076\nDPO AP 72886',
},
    'key78355': 'value44630',
    'key27181': 'value6016',
    'key75837': 'value97685',
    'key94273': 'value90716',
    'key4229': 'value19035',
    'key28173': 'value22993',
    'key91833': 'value88502',
    'key62358': 'value94628',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'John Davidson',
    'address': '1869 Erica Meadow\nGarciafort, CA 80293',
    'text': 'Several purpose different population. Population event democratic political pick.',
    'email': 'tiffany19@example.com',
    'phone_number': '001-955-835-3047x95083',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Beard',
    'Ruth Cameron',
],
    'json': {
    'name': 'Stephanie Smith',
    'address': '6855 Sarah Knoll\nCervantesborough, NY 22127',
},
    'key36394': 'value84426',
    'key14961': 'value32268',
    'key25693': 'value1757',
    'key28722': 'value61150',
    'key60355': 'value78093',
    'key72476': 'value73071',
    'key37434': 'value28808',
    'key62196': 'value30344',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Theresa Wheeler',
    'address': 'PSC 9752, Box 7594\nAPO AA 33697',
    'text': 'Poor hot rest east recognize life his. Nor kind describe either yes Mr religious. Senior major brother by own analysis.',
    'email': 'chris05@example.com',
    'phone_number': '470-892-3861x587',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alex Landry',
    'Martin Mendez',
    'Susan Perry',
    'Cody Miller',
],
    'json': {
    'name': 'Linda Frank',
    'address': '29210 Faulkner Summit\nMichaelberg, OK 57834',
},
    'key27850': 'value31729',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Emily Farley',
    'address': '84293 Wheeler Inlet Suite 077\nThomasmouth, KS 80307',
    'text': 'Send section middle everyone drug describe professional. Treat million decide thing measure. Red cultural soldier everyone company computer.',
    'email': 'lisa08@example.net',
    'phone_number': '552-748-3243x452',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Ellis',
    'Judith Barnes',
    'Leah Green',
    'Donald Jefferson',
    'Joshua Goodman',
],
    'json': {
    'name': 'Jason Booth',
    'address': '4726 Carol Stravenue Apt. 245\nTerriside, SC 42120',
},
    'key64031': 'value15932',
    'key75077': 'value14770',
    'key16495': 'value50723',
    'key50506': 'value67323',
    'key26598': 'value96331',
    'key20555': 'value36697',
    'key93672': 'value87924',
    'key9317': 'value34183',
    'key81739': 'value13534',
    'key55997': 'value83189',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Jon Lindsey',
    'address': '00844 Tammy Cape\nWest Calebchester, TN 33304',
    'text': 'Happy everybody owner.\nSimilar position if election hour without safe. Art bad source suddenly training capital system. Seven method about sign beat far yes main.',
    'email': 'qpark@example.com',
    'phone_number': '3145217106',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Fisher',
    'Scott Davis',
    'Daniel Brooks',
],
    'json': {
    'name': 'Dean Riddle',
    'address': '17311 Michelle Spurs\nLake Angela, WI 94771',
},
    'key98844': 'value42124',
    'key31877': 'value80819',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Richard Walsh',
    'address': '231 Barker Trace Apt. 161\nSarahside, AS 41395',
    'text': 'Response growth stock add shoulder power. Some quickly affect personal hair. Full hair meeting nation there commercial shoulder someone. Culture fact wear effect might PM.',
    'email': 'leonarddonald@example.com',
    'phone_number': '001-886-731-9201x152',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Peck',
    'Diana Moran',
    'Monica Matthews',
    'Timothy Stewart',
    'Donna Wright',
    'Tonya Burton',
],
    'json': {
    'name': 'Kayla Wilkins',
    'address': '50220 Nicole Path\nEast Steven, MD 27378',
},
    'key32272': 'value88387',
    'key82305': 'value96859',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Julie Gonzalez',
    'address': '27161 Kathy Isle\nWest Nathan, ND 78277',
    'text': 'Town evening some grow floor great TV.\nOnce sign chair yes around food still. Member single bring where star music. Meet class ago we right couple allow. Phone side husband.',
    'email': 'johnsonregina@example.org',
    'phone_number': '949.875.5170',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Snyder',
    'Frederick Green',
    'Jeffrey Lewis',
    'Robert Fletcher',
    'Kimberly Mendoza',
    'Betty Anthony',
    'James Johnson',
],
    'json': {
    'name': 'Stacy Hall',
    'address': '88212 Theresa Ridge Suite 818\nLake Ryanside, MA 09662',
},
    'key25401': 'value91236',
    'key60887': 'value17376',
    'key67317': 'value61904',
    'key83263': 'value11560',
    'key36262': 'value65395',
    'key11064': 'value70949',
    'key71280': 'value51226',
    'key38167': 'value26477',
    'key62779': 'value69811',
    'key9957': 'value81585',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Chad Reyes',
    'address': '399 Perez Vista Suite 708\nEast Dianashire, MN 81219',
    'text': 'Together serve born local newspaper. Feeling manage office main become rise attention.\nChild then soldier partner. Fall relate thought to wall beat watch. Training article choice take turn I tell.',
    'email': 'shannon30@example.com',
    'phone_number': '7759306665',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Lee',
    'Brett Quinn',
    'Bobby Powell',
    'Catherine Ramirez',
    'Melissa White',
    'Alexandra Watkins',
    'Amanda Lopez',
    'Tracey Griffin',
],
    'json': {
    'name': 'Kristopher Roman',
    'address': '27981 Roberta Trace Apt. 095\nKellyview, WA 79608',
},
    'key14226': 'value33194',
    'key52632': 'value89257',
    'key52220': 'value34618',
    'key22039': 'value77686',
    'key81826': 'value59544',
    'key55459': 'value70126',
    'key73591': 'value56765',
    'key3826': 'value59959',
    'key61846': 'value58571',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Gregory Bond',
    'address': '540 Potter Camp Apt. 546\nPort Jefferyborough, NE 81369',
    'text': 'Some small would memory area. American involve art relate.\nWord young before miss. Assume development word when though best speak. Subject debate from actually at must chance.',
    'email': 'garciagabriel@example.com',
    'phone_number': '001-418-789-0298x716',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mary Velazquez',
],
    'json': {
    'name': 'Danielle Combs',
    'address': '2657 White Row Suite 442\nFergusonside, MT 54783',
},
    'key90580': 'value7740',
    'key83338': 'value4220',
    'key44329': 'value36305',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Kevin Kennedy',
    'address': '954 Bridget Turnpike Suite 913\nPort Michaelville, HI 21458',
    'text': 'Themselves positive specific. State information least part decide cell. South consumer similar wrong source.\nUnit direction direction coach seem defense black.',
    'email': 'ymoyer@example.com',
    'phone_number': '443-986-1729x46542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jason Lee',
    'Rachel Klein',
    'Katherine Wall',
    'Lori Palmer',
    'Rachel Medina',
    'Heather Sherman',
    'Karen Rodriguez',
],
    'json': {
    'name': 'Thomas Hawkins',
    'address': '98588 Linda Rue Apt. 564\nPricetown, NV 42720',
},
    'key72294': 'value3663',
    'key67847': 'value32339',
    'key19444': 'value97090',
    'key47089': 'value61427',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Katherine Hart',
    'address': '9374 King Parkways Suite 169\nYoungburgh, MT 76229',
    'text': 'Within exist car task expect. Leave against here land down.\nStuff move control since Mr information. Tell home feeling with.',
    'email': 'heathersharp@example.com',
    'phone_number': '(273)736-2979x47095',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jenna Rangel',
    'Kimberly Scott',
    'Christopher Nguyen',
],
    'json': {
    'name': 'Julia Bush',
    'address': '91087 Glenda Springs Apt. 989\nLake Anthonymouth, VA 56854',
},
    'key69140': 'value86738',
    'key11840': 'value57863',
    'key7287': 'value93114',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Brad Graham',
    'address': '67307 David Track Apt. 038\nParkerfurt, MP 39026',
    'text': 'Traditional religious could worker. Thing organization trial these statement add very.\nNews ability attorney mother civil factor. My feel even whom financial shoulder beat modern.',
    'email': 'matthew09@example.org',
    'phone_number': '(613)873-2648x0100',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Cook',
    'William Huang',
    'Paul Brown',
    'Kristin Marquez',
    'Kristen Clark',
    'Kristen Guzman',
    'Marvin Greene',
    'Belinda Garcia',
],
    'json': {
    'name': 'Jessica Castillo',
    'address': '26035 Tiffany Unions Suite 943\nMendozaborough, FM 38733',
},
    'key41844': 'value58500',
    'key44330': 'value16028',
    'key62491': 'value47132',
    'key4241': 'value80122',
    'key14934': 'value25541',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Michael Fernandez',
    'address': '55273 Smith Throughway Apt. 356\nWest Christopher, PA 48735',
    'text': 'Top live wrong natural third. Yeah society kid through.\nShare sound dog door that. Safe Congress per late.\nOffer particular traditional number short no bank.\nAttack represent in store than beautiful.',
    'email': 'brian70@example.net',
    'phone_number': '949.813.6371x1504',
    'array_int_dynamic': [
    15582,
],
    'array_varchar_dynamic': [
    'Travis Lopez',
    'Angel Shelton',
    'Spencer Singh',
    'Mary Martin',
    'John Torres',
],
    'json': {
    'name': 'Mr. Eric Neal',
    'address': '5454 David Spring Suite 002\nSouth Miranda, GA 62846',
},
    'key16563': 'value92923',
    'key23974': 'value33965',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Sharon Shaw',
    'address': '558 Ethan Mount\nJoshuaport, AR 07037',
    'text': 'Whether behavior commercial admit her teach almost bad. Chair west white specific growth.',
    'email': 'karen63@example.net',
    'phone_number': '(783)531-8489x436',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Noah Jimenez',
    'Deborah Franklin',
    'Robert Ochoa',
],
    'json': {
    'name': 'Tyler Gonzalez',
    'address': '637 Crystal Extensions Apt. 936\nWest Haleyburgh, CT 14150',
},
    'key25563': 'value11351',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Patricia Jensen',
    'address': 'USCGC Buckley\nFPO AA 10884',
    'text': 'Someone century difficult sense candidate according care. National top offer add manage mission phone trial.\nOrder scene black operation information reality. Thank cost serious step woman right.',
    'email': 'floresanne@example.com',
    'phone_number': '949-483-4840',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Harrison',
    'Michele Johnson',
    'John Carter',
    'Cynthia Carter',
],
    'json': {
    'name': 'Gregory Jones',
    'address': '18119 Sandra Ports\nNorth Sandramouth, OK 04270',
},
    'key21380': 'value29626',
    'key99306': 'value48033',
    'key34272': 'value72420',
    'key5545': 'value90539',
    'key39549': 'value4089',
    'key24911': 'value39953',
    'key77469': 'value83330',
    'key9308': 'value69650',
    'key86608': 'value68668',
    'key27036': 'value92837',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Michele Matthews',
    'address': '45975 Jackson Run\nJacquelineview, MT 76090',
    'text': 'Question huge fill drug. Certain method technology.\nBuild quickly cup. Describe small choose. Rest sit compare play wall.',
    'email': 'westjason@example.org',
    'phone_number': '3555816836',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Morgan Reid',
    'Brett Ramirez',
    'David Hull',
    'Tina Ellison',
    'Katherine Robinson',
    'Susan Hernandez',
    'Sarah Obrien',
    'Monica Morton',
    'John Rowland',
    'Darren Richards',
],
    'json': {
    'name': 'Kathleen Rosales',
    'address': '2986 Lisa Fords Suite 124\nWest Amy, VT 30994',
},
    'key2433': 'value62402',
    'key77800': 'value88307',
    'key73927': 'value44991',
    'key4233': 'value90786',
    'key60820': 'value13735',
    'key23898': 'value59971',
    'key1247': 'value79009',
    'key23303': 'value26557',
    'key99010': 'value57843',
    'key15378': 'value78576',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Mr. Brady Young',
    'address': '3874 Miller Island\nMillermouth, DC 36035',
    'text': 'Result build final simple shake. Only tree laugh news them bag agency.',
    'email': 'barronjeremy@example.net',
    'phone_number': '961.638.7255',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Charles Payne',
    'Michael Mclean',
    'Wendy Riddle',
    'Deborah Hansen',
    'Hunter Fisher',
    'Diana Fisher',
    'Kelly Hood',
    'Amber Armstrong',
    'Tina Miller',
],
    'json': {
    'name': 'Anita Delgado',
    'address': '061 Gary Road\nNew Kevin, MN 87218',
},
    'key79216': 'value96328',
    'key72789': 'value78784',
    'key21566': 'value98654',
    'key86161': 'value45430',
    'key42706': 'value73780',
    'key23362': 'value44889',
    'key31261': 'value32912',
    'key19621': 'value5852',
    'key10628': 'value13912',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Corey Moore',
    'address': '9883 Porter Wells Suite 875\nMaldonadofort, MT 76111',
    'text': 'List support trial federal next. Section event ask my.\nSport able baby should.\nThird smile fear why those last. Certain bank from local place management fund. Information with Democrat out region.',
    'email': 'awiley@example.org',
    'phone_number': '(318)388-3505',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Lane',
    'Mark Waters',
    'Steven Turner',
    'Maurice Acosta',
    'Joseph Webb',
    'Mike Rosario',
    'Robert Gonzalez',
],
    'json': {
    'name': 'Samuel Mckee',
    'address': '15945 James Streets Suite 382\nCharlesborough, AS 74296',
},
    'key48341': 'value75044',
    'key19709': 'value21604',
    'key88986': 'value28097',
    'key55870': 'value13566',
    'key41641': 'value15592',
    'key4957': 'value14484',
    'key36558': 'value67684',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Lisa Mora',
    'address': '1702 Snow Squares\nMayerborough, FM 39054',
    'text': 'Know third yet area century. Attention relationship enjoy visit fish discussion worker. Your senior yes choose offer.',
    'email': 'pharris@example.com',
    'phone_number': '(208)359-9691x0679',
    'array_int_dynamic': [
    58220,
],
    'array_varchar_dynamic': [
    'Ashley Jordan',
    'Robert Hunt',
    'Jack Reynolds',
    'Gary Johnson',
    'Jeffrey Jackson',
],
    'json': {
    'name': 'Shawn Larson',
    'address': '461 Smith Cliff Apt. 955\nChandlerburgh, CA 60371',
},
    'key50404': 'value88160',
    'key64419': 'value93100',
    'key31864': 'value99572',
    'key6901': 'value8021',
    'key41504': 'value36176',
    'key83095': 'value70281',
    'key93910': 'value80461',
    'key65890': 'value96572',
    'key81644': 'value31339',
    'key59878': 'value56136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Robert Wilson',
    'address': '1931 Parker Trafficway Suite 086\nPort Anthony, AL 78667',
    'text': 'Project instead lot lose on the late. Push investment box technology smile far economy. Ball read seven process computer send clear.',
    'email': 'mbrooks@example.com',
    'phone_number': '7493356274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Deanna Webster',
    'Amber Smith',
    'John Hunter',
    'Michael Bailey',
    'Thomas Powell',
    'Misty Reeves',
    'Sheena Burton',
    'Lisa Long',
],
    'json': {
    'name': 'Debra Fitzgerald',
    'address': '9260 Schultz Spring Apt. 181\nLake Ronaldside, NJ 87638',
},
    'key94927': 'value63276',
    'key13731': 'value18288',
    'key48144': 'value31206',
    'key94638': 'value93275',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Joshua Howard',
    'address': '1811 Julie Ramp Apt. 873\nNew Traciemouth, PR 42254',
    'text': 'Manager understand production less section generation. Most art production see bad.\nFrom chance help issue protect. Painting debate pass free truth.',
    'email': 'richardsingh@example.com',
    'phone_number': '327.931.0087',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Ingram',
    'Jessica Love',
    'William Hawkins',
    'Pamela Woodard',
    'Sandra Torres',
    'Timothy Boyd',
],
    'json': {
    'name': 'Daniel Jackson',
    'address': '113 Navarro Gardens\nSouth Kristina, MN 88679',
},
    'key85353': 'value87085',
    'key2651': 'value10453',
    'key66362': 'value1372',
    'key66457': 'value74897',
    'key46484': 'value9371',
    'key1439': 'value54524',
    'key35039': 'value45171',
    'key61262': 'value94079',
    'key38248': 'value32107',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Frank James',
    'address': '45943 Martinez Mall\nCamachoville, MH 68613',
    'text': 'Eye relate position world way include back. Improve Democrat white thought never my. Event north concern.',
    'email': 'wellssandra@example.org',
    'phone_number': '001-349-282-3765x15770',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Marks',
    'Tammy Savage',
    'Joshua Hoffman',
    'Eric Martinez DDS',
    'Andrew Dunn',
    'Heather Barnett',
],
    'json': {
    'name': 'William Bean',
    'address': '834 Castillo Point Suite 178\nNew Nicole, VT 63303',
},
    'key88426': 'value96826',
    'key86174': 'value62553',
    'key14909': 'value31318',
    'key75789': 'value17131',
    'key91369': 'value58082',
    'key12843': 'value2930',
    'key64681': 'value21122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Rodney Moreno',
    'address': '221 Clark Canyon Apt. 584\nCatherineberg, NJ 01990',
    'text': 'Rule late green behavior. Vote western reach let radio.\nSound paper development. Tax environmental detail responsibility certain reduce. There base audience protect wind Mrs particular.',
    'email': 'mariah20@example.com',
    'phone_number': '9698860352',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mark Lucas',
    'Jonathan Johnson',
    'Kaylee Carter',
    'Sydney Hamilton',
    'Ruben Delgado',
    'Dr. Amy Guzman',
    'Nicole Yoder',
    'April Hawkins',
    'Brett Robbins',
],
    'json': {
    'name': 'Austin Clayton',
    'address': '49299 Michael River\nSouth Erika, WY 86635',
},
    'key74323': 'value50412',
    'key66382': 'value46245',
    'key34616': 'value83311',
    'key44742': 'value66403',
    'key3163': 'value685',
    'key91912': 'value51957',
    'key12577': 'value22390',
    'key47083': 'value15542',
    'key61414': 'value76799',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Mark Bell',
    'address': '590 Amy Burg\nSouth Keithville, MO 79445',
    'text': 'Dark opportunity against week energy health. Important bill claim avoid road continue. Building media fine write fight stage election.',
    'email': 'nicole94@example.org',
    'phone_number': '473.868.5666',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Reed',
],
    'json': {
    'name': 'Jonathan Ross',
    'address': '38313 Eric Fork\nPort Joshua, IL 06064',
},
    'key17284': 'value80876',
    'key79329': 'value3962',
    'key47914': 'value31179',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Jade Lyons',
    'address': 'Unit 1994 Box 2690\nDPO AP 35437',
    'text': 'Big white large line alone property rule. War out official best speech return area.\nAttorney hope between within accept.\nDetermine enough discover guess our blood. Occur that add.',
    'email': 'ghughes@example.com',
    'phone_number': '+1-640-314-2213x1565',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Olson',
    'Janet Hughes',
],
    'json': {
    'name': 'Elizabeth Miles',
    'address': '44804 Williams Hollow\nWoodsmouth, WA 69686',
},
    'key26346': 'value75226',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Mr. William Henderson',
    'address': '346 Amber Streets\nRileyview, NY 51600',
    'text': 'Investment have off nation easy current myself. Five tough machine point.\nAlso figure one into. Cell develop yard challenge anyone room. Spring wear prevent responsibility same.',
    'email': 'radams@example.org',
    'phone_number': '941-652-1609x8184',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Carr',
    'Penny Harris',
    'Crystal Herring',
    'Jennifer Davis',
    'Amber King',
],
    'json': {
    'name': 'Mrs. Karen Gomez',
    'address': '42488 Matthew Course Suite 761\nNew Tim, NJ 73740',
},
    'key68913': 'value97444',
    'key61325': 'value98544',
    'key82923': 'value85952',
    'key9411': 'value95153',
    'key10188': 'value4900',
    'key54648': 'value95538',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Scott Mcgrath',
    'address': '6883 Williams Greens Suite 944\nSouth Mark, OH 58701',
    'text': 'Including chance church present test. All claim decade speak according. Enjoy especially low player create language direction.',
    'email': 'glopez@example.net',
    'phone_number': '+1-387-740-5067',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Norma Thomas',
    'Jasmine Rojas',
    'Claudia Mccoy',
    'Gary Griffin',
    'Evan Morris',
    'Julia Ramirez',
    'Brian Hernandez',
    'Megan Jordan',
    'Tanya Garza',
],
    'json': {
    'name': 'Jeremy Smith',
    'address': '97853 Norman Stream\nAngelaview, GU 60005',
},
    'key83158': 'value6995',
    'key6047': 'value84834',
    'key86491': 'value33636',
    'key38318': 'value55052',
    'key80475': 'value19966',
    'key66520': 'value71643',
    'key79676': 'value62104',
    'key43673': 'value92241',
    'key82750': 'value37909',
    'key65791': 'value45353',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Wendy Reyes',
    'address': '963 Kevin Locks\nBallport, MP 31720',
    'text': 'You sort somebody decade reveal. Among garden their benefit true Mr citizen. Though course note especially party assume.',
    'email': 'vanessa11@example.net',
    'phone_number': '(545)886-1606x27473',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Luke Hudson',
    'Juan Ballard',
    'Jeffery Powell',
    'Margaret Villegas',
],
    'json': {
    'name': 'Lori Holmes',
    'address': '2053 Young Drives\nNorth Tannerview, FM 87255',
},
    'key55970': 'value75192',
    'key37208': 'value69259',
    'key61288': 'value31000',
    'key6905': 'value49417',
    'key57416': 'value82501',
    'key51840': 'value96839',
    'key99840': 'value71226',
    'key37173': 'value5123',
    'key17043': 'value14804',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Christopher Reyes',
    'address': '643 Craig Bypass\nNew Barbara, MN 16910',
    'text': 'Answer return maintain hard party later note. North speech maybe husband.\nWorld data enter able professor carry must. Seek study might beautiful agreement attention. She join town western.',
    'email': 'lisa02@example.net',
    'phone_number': '241-534-0361',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Renee Shields',
],
    'json': {
    'name': 'Mary Turner',
    'address': '9081 Julie Lodge Suite 819\nLake Joseborough, NH 55238',
},
    'key36689': 'value87393',
    'key71011': 'value64665',
    'key54357': 'value7306',
    'key60646': 'value78199',
    'key85196': 'value27664',
    'key90330': 'value36593',
    'key11612': 'value62842',
    'key97774': 'value53437',
    'key63144': 'value20180',
    'key28117': 'value97085',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Cynthia Jordan',
    'address': '113 Timothy Gateway Suite 204\nMaynardton, HI 55789',
    'text': 'Somebody member wide country reduce environmental try believe. After this discover. Apply brother wrong conference budget high kid.',
    'email': 'david74@example.net',
    'phone_number': '467.986.1542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sara Ford',
    'Vickie Norman',
    'Cole Smith',
    'Paula Cruz',
    'Teresa Singh',
    'Kelli Mitchell',
    'James Manning',
    'Jessica Dudley',
    'Terry Cole',
],
    'json': {
    'name': 'Kevin Munoz',
    'address': 'USS Santiago\nFPO AE 35822',
},
    'key89546': 'value70916',
    'key21821': 'value34332',
    'key14253': 'value19291',
    'key77258': 'value56532',
    'key31110': 'value45055',
    'key12806': 'value63225',
    'key65227': 'value35306',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Joel Martinez',
    'address': '79049 Zachary Spurs\nWest Amandaborough, RI 78117',
    'text': 'Son blue guy stop from garden. Town development real law. Answer agency behind return. Else reveal back use.',
    'email': 'breanna40@example.net',
    'phone_number': '246.801.3548x14784',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Jimenez',
    'Tony Moses',
    'Tammy Rodriguez',
    'Laura Mooney',
    'Samantha Ibarra',
    'Michelle Mayer',
    'Erin Chavez',
    'Stephen Obrien',
],
    'json': {
    'name': 'Jesse Kerr',
    'address': '190 Becker Shoal Apt. 136\nMatthewsstad, PW 73930',
},
    'key34271': 'value81953',
    'key39123': 'value9812',
    'key96437': 'value27499',
    'key38054': 'value67101',
    'key46664': 'value3255',
    'key99465': 'value72333',
    'key83311': 'value50327',
    'key13067': 'value67747',
    'key52627': 'value82117',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Barry Barnes',
    'address': '513 Cook Springs\nGeoffreyland, PR 53331',
    'text': 'Sort father but when most child. Try method protect cost finish human issue organization.\nItem memory along system item. Huge test man almost southern agree.',
    'email': 'jhansen@example.org',
    'phone_number': '506.581.8589x4644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Karen Harper',
    'Jessica Smith',
    'Ashley Khan',
    'Caitlin Diaz',
    'Timothy Mcknight',
    'Mrs. Gina Lopez',
    'Sabrina Brown',
    'Nicholas Adams',
    'Jon Rodriguez',
],
    'json': {
    'name': 'Brett Wood',
    'address': '379 Beard Way\nButlerstad, WI 90460',
},
    'key38880': 'value99290',
    'key20628': 'value22901',
    'key40736': 'value86591',
    'key54847': 'value79008',
    'key31632': 'value80191',
    'key58753': 'value91532',
    'key75072': 'value35421',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Samantha Dixon',
    'address': '81236 Hall Islands\nSherrichester, NV 73830',
    'text': 'Three toward state rock per city effort. Onto address third try recently. Test month movie.',
    'email': 'castilloalison@example.net',
    'phone_number': '818-346-8082x14348',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Hart',
    'Theodore Valdez',
    'Mallory Taylor',
    'Matthew Odom',
],
    'json': {
    'name': 'Andrea Alexander',
    'address': '7197 Carol Station\nManuelport, AL 29496',
},
    'key37496': 'value77046',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Joseph King',
    'address': '527 Tammy Point Suite 851\nLake Luis, NC 94246',
    'text': 'Sister property technology away.\nLaw hot high view.',
    'email': 'jordancynthia@example.org',
    'phone_number': '359.927.5261x868',
    'array_int_dynamic': [
    38165,
],
    'array_varchar_dynamic': [
    'Janice Clark',
    'Christian Roberts',
    'Rebecca Odonnell',
    'Justin Johnson',
    'Eric Turner',
    'Christine Quinn',
    'Michael Rogers',
    'Cindy Wilson',
    'Kenneth Rodriguez',
],
    'json': {
    'name': 'Maureen Hicks',
    'address': '36547 Mark Plains Apt. 134\nEast Tracy, NC 38747',
},
    'key75471': 'value33444',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'David Smith',
    'address': '74945 Charles Underpass\nGoodmanside, AK 14686',
    'text': 'Film teacher modern among look. Tough choice pass hot compare contain technology. Author power hope food civil similar challenge similar. Dark direction outside take he building receive.',
    'email': 'williamsbrian@example.com',
    'phone_number': '001-764-723-4762x15555',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Velasquez',
    'Kimberly Taylor',
],
    'json': {
    'name': 'Jill White',
    'address': '3900 Mark Stravenue\nLake Christophertown, PA 44452',
},
    'key47535': 'value13015',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Jasmin Allison',
    'address': 'USS Sullivan\nFPO AP 50570',
    'text': 'Admit affect decide business. Focus young next fish short truth.\nNews expert interesting work simple huge hotel space. Some this explain ball now as. Product old threat ok forward back drug.',
    'email': 'kelly33@example.org',
    'phone_number': '928-556-0398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'William Gonzales',
    'Mr. Thomas Hudson',
    'Michael Holland',
],
    'json': {
    'name': 'Alec Peters',
    'address': '07827 Jessica Village\nStevenhaven, NH 26666',
},
    'key36394': 'value13026',
    'key95305': 'value4417',
    'key63882': 'value76543',
    'key78734': 'value65544',
    'key17194': 'value29905',
    'key2040': 'value24516',
    'key72416': 'value88685',
    'key38222': 'value70662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Christine Hess',
    'address': '124 Robert Estate\nLake Michelefurt, KS 57370',
    'text': 'Plan simple catch natural. Smile also civil receive have marriage. Everything page become short.',
    'email': 'justin23@example.net',
    'phone_number': '001-862-680-6068x9633',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marc Soto',
    'Leon Garcia',
    'James Ball',
    'Gene Harris',
],
    'json': {
    'name': 'Jonathan Velez',
    'address': '3569 Robert Islands Apt. 147\nPaulborough, ND 26605',
},
    'key92406': 'value91730',
    'key56338': 'value24511',
    'key99515': 'value87486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Colton Collins',
    'address': 'Unit 6488 Box 9748\nDPO AP 12883',
    'text': 'Unit prove beautiful everything. Who tonight program less series agency turn. Nature season evening heavy protect include moment.',
    'email': 'rjenkins@example.net',
    'phone_number': '001-257-579-8815x9562',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stacey Schaefer',
    'Keith Salinas',
    'Brian Olson',
    'Thomas Harrison',
    'Jill Johnson',
    'Kristin Pena',
    'Jared Pena',
    'Norman Gonzales',
],
    'json': {
    'name': 'Michelle Fitzgerald',
    'address': '4567 Foster Camp Suite 342\nMarissaview, UT 20183',
},
    'key83171': 'value34539',
    'key54599': 'value63985',
    'key20446': 'value94682',
    'key35846': 'value66322',
    'key56338': 'value74904',
    'key9960': 'value57622',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Brent Cain',
    'address': '9840 Mckay Park Apt. 470\nWest Josephburgh, AZ 42754',
    'text': 'Total gun explain though continue meeting participant. Partner we receive ever easy affect week. Long team might success.\nOrder quite both loss plan. Now brother claim mean building note way.',
    'email': 'jennifercohen@example.net',
    'phone_number': '001-280-961-1849',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Charles Gill',
    'Anthony Rodriguez',
    'Angela Trujillo',
    'Christopher Trevino',
    'Jose Orr',
    'Tracy Moss DDS',
    'Sean Warren',
    'Laurie Mendoza',
    'Abigail Wiley',
    'Michael Thompson PhD',
],
    'json': {
    'name': 'Alisha Mckinney',
    'address': '272 Lisa Stream Suite 003\nWest Sylviabury, CT 93052',
},
    'key23128': 'value55006',
    'key89095': 'value93440',
    'key31678': 'value56980',
    'key42860': 'value45635',
    'key26587': 'value22421',
    'key96467': 'value5916',
    'key24552': 'value32246',
    'key32113': 'value92732',
    'key51932': 'value26587',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Amy Mitchell',
    'address': '1919 Cooper Prairie\nLake Heatherland, NV 75047',
    'text': 'Make fund quality southern there yes marriage account. Any concern computer several. Place evidence course possible scientist.',
    'email': 'chris55@example.com',
    'phone_number': '+1-958-986-6777',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Curry',
    'Stephen Jackson',
    'Jennifer Parker',
    'Christopher Bennett',
    'Taylor Arroyo',
    'Jerome Lin',
],
    'json': {
    'name': 'Allison Rasmussen',
    'address': '50135 Erin Parks\nJacksonberg, PW 80472',
},
    'key49645': 'value14032',
    'key73406': 'value36189',
    'key87511': 'value36534',
    'key15819': 'value73109',
    'key41385': 'value52480',
    'key11184': 'value90503',
    'key62814': 'value25767',
    'key15791': 'value63122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Nicholas Moore',
    'address': '019 Christina Brook\nSouth Crystalmouth, WV 41614',
    'text': 'Type general will network live. Military argue oil thank. Nice relationship list bring.\nCommon play bed others give. Power tend poor one.',
    'email': 'rosalesjustin@example.org',
    'phone_number': '(354)561-5281x7977',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Boyer',
    'Candice Odom',
    'Karen Murray',
    'Jasmine Young DVM',
],
    'json': {
    'name': 'Crystal Rojas',
    'address': '4634 Melinda Crescent\nPort Theodore, MN 21125',
},
    'key55154': 'value2545',
    'key62604': 'value44490',
    'key50107': 'value65784',
    'key74703': 'value40947',
    'key65698': 'value74712',
    'key96164': 'value74073',
    'key73985': 'value88727',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Scott Walker',
    'address': '5375 Joshua Island\nJoseview, NH 25428',
    'text': 'Career mean exist alone late physical. Water season stuff may seem this professor.\nPolice make person notice. Both under reveal most next buy. Kid beyond what.',
    'email': 'ryan09@example.org',
    'phone_number': '(763)216-0005',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Victor Ramirez',
    'Christopher Cook',
    'Jacqueline Porter',
],
    'json': {
    'name': 'Robert Erickson',
    'address': '918 Sanders Trail\nNew Timothy, NH 78221',
},
    'key28984': 'value8215',
    'key62593': 'value26518',
    'key20034': 'value1606',
    'key92457': 'value70299',
    'key31574': 'value7951',
    'key10633': 'value75633',
    'key17121': 'value73320',
    'key96018': 'value78698',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Stacy Preston',
    'address': 'USNS Lee\nFPO AP 70076',
    'text': 'Rather citizen gas pull serve nothing include. Medical you least long hotel station whole.\nLarge management shake task operation degree. Let best cost local.',
    'email': 'johnhodges@example.com',
    'phone_number': '+1-809-485-5284x912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brian Stevens',
    'Bethany Harper',
    'Gwendolyn Bush',
    'Brittney Clark',
    'Edward Soto',
],
    'json': {
    'name': 'Christina Nielsen',
    'address': '4482 Kimberly Garden Suite 302\nHallside, PR 70077',
},
    'key83356': 'value19983',
    'key22309': 'value19438',
    'key52894': 'value61162',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Daniel Holloway',
    'address': '9661 Bates Roads Suite 458\nKelleymouth, GA 63981',
    'text': 'Picture there option street across short. Election fast each risk argue few. Total follow stay consider.\nHit citizen theory. Reveal protect rather up capital care.',
    'email': 'brownabigail@example.com',
    'phone_number': '662-820-7007',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Connie Brooks',
    'Crystal Benson',
    'Kevin Mack',
    'Marie Jones',
    'Kyle Chandler',
    'Erin King',
],
    'json': {
    'name': 'Jennifer Allen',
    'address': '62020 Stewart Rapid Apt. 508\nPort Troymouth, AS 46516',
},
    'key26146': 'value90301',
    'key21302': 'value27766',
    'key67101': 'value45690',
    'key46169': 'value75173',
    'key14239': 'value8659',
    'key14771': 'value19026',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Rhonda Nelson',
    'address': '9699 John Bridge Suite 129\nLake Christopher, NJ 18090',
    'text': 'Positive relate fact popular difference. Plan senior as smile attorney how safe. Wait international add bank event.',
    'email': 'robert95@example.org',
    'phone_number': '530.766.3861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Dakota Velazquez',
    'Tyler Hernandez',
],
    'json': {
    'name': 'David Roy',
    'address': '43074 David Creek\nAbigailshire, NH 71482',
},
    'key33961': 'value14401',
    'key19502': 'value5084',
    'key43830': 'value1029',
    'key96244': 'value6966',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Travis Oneill',
    'address': '297 Nancy Views Apt. 374\nPort Raymondhaven, FL 58995',
    'text': 'Into Congress unit respond. Month with chair particular control among board.\nMedia control thought special every. Someone behind drive. Term take red dog deal difficult. Heart carry again several.',
    'email': 'qbarker@example.com',
    'phone_number': '256-339-0044x6112',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Rocha',
    'Andrew Bennett',
    'Kiara Middleton',
    'Amanda Wilcox',
    'James Salazar DDS',
    'Jeremy Rodriguez',
    'Susan Smith',
],
    'json': {
    'name': 'Stephen Jennings',
    'address': '01662 Kara Run Apt. 691\nRollinsmouth, IN 78222',
},
    'key70325': 'value60109',
    'key56361': 'value76065',
    'key1867': 'value8787',
    'key49615': 'value78996',
    'key65963': 'value56983',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Randy Alvarez',
    'address': '0426 Thomas Square\nAlexanderfort, WY 99496',
    'text': 'Then husband language save training conference night. Different party team thousand. Lead member together gas story story.',
    'email': 'lsmith@example.net',
    'phone_number': '820-618-1082',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Vaughan',
],
    'json': {
    'name': 'Alexander Perry',
    'address': '9433 Hughes Locks\nKnightchester, NM 17593',
},
    'key71024': 'value31981',
    'key2827': 'value52293',
    'key20781': 'value10841',
    'key97134': 'value92113',
    'key20112': 'value89300',
    'key18496': 'value26663',
    'key83472': 'value10696',
    'key9956': 'value80208',
    'key83870': 'value66929',
    'key92278': 'value75520',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Stephanie Walker',
    'address': '974 Jill Ferry Apt. 830\nHarrisberg, KY 73424',
    'text': 'Thing ahead direction less whatever. May win need. Along method marriage laugh enjoy already.',
    'email': 'chad60@example.org',
    'phone_number': '472.640.3681x9925',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Diaz',
    'Brenda Klein',
    'Andrea Gibson',
    'Tracy Sanchez',
    'Steven Lucas',
    'Daniel Miranda',
    'Vanessa Duarte',
],
    'json': {
    'name': 'Andrea Nolan',
    'address': '526 Michelle Curve\nRichardfurt, ND 01995',
},
    'key15013': 'value87252',
    'key16752': 'value80770',
    'key72760': 'value51895',
    'key754': 'value35066',
    'key77916': 'value21265',
    'key10385': 'value26053',
    'key17102': 'value74319',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Caitlin Wilson',
    'address': '9328 Manuel Square Apt. 686\nDaviston, WA 43815',
    'text': 'Almost condition international this live particularly argue dream. Wife stuff company. Reason service stuff as.',
    'email': 'rodney39@example.org',
    'phone_number': '308-989-9835x277',
    'array_int_dynamic': [
    87564,
],
    'array_varchar_dynamic': [
    'Steven Sutton',
    'Gerald Snyder',
    'Ashley Jones',
    'Anthony Aguilar',
    'Jared Clark',
    'Joseph Reed',
],
    'json': {
    'name': 'Ashley Rodriguez',
    'address': '017 Ortiz Gardens Suite 540\nNorth Doris, UT 65823',
},
    'key19559': 'value69575',
    'key51123': 'value95621',
    'key77204': 'value61947',
    'key55427': 'value68860',
    'key37172': 'value68421',
    'key36287': 'value10830',
    'key38385': 'value30059',
    'key12700': 'value26901',
    'key93631': 'value39474',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jessica Cohen',
    'address': '04912 Gina Square Suite 422\nHerreraview, MN 13172',
    'text': 'Condition friend approach throw million four value. Own weight suddenly talk ever support general line. Old section hair car boy turn. And management catch sort draw site tax majority.',
    'email': 'rwest@example.net',
    'phone_number': '731-616-8949x60814',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Trevor Williams',
    'Adam White',
    'April King',
    'Timothy Cox',
    'Vincent Mccann',
    'Darlene Brown',
    'Michael Rose',
],
    'json': {
    'name': 'Kristopher Simpson',
    'address': '523 Parrish Burg\nWhitneyton, MS 81528',
},
    'key19032': 'value17583',
    'key55532': 'value81866',
    'key28729': 'value99296',
    'key72711': 'value12931',
    'key60600': 'value76381',
    'key5616': 'value5289',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Albert Hughes',
    'address': 'PSC 0671, Box 9931\nAPO AP 15850',
    'text': 'Painting very tough use. Very pretty green professor.\nHear resource everything fund national. State crime usually never cell here. Manager leader officer never alone summer then movement.',
    'email': 'djohnson@example.net',
    'phone_number': '3206781937',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Solomon',
    'Lauren Harper',
    'James Young',
    'Tammy Thompson',
    'Linda Pacheco',
    'Kyle Harrison',
],
    'json': {
    'name': 'Casey Chavez',
    'address': '91049 Garcia Plain\nConnerview, MD 37485',
},
    'key72522': 'value64701',
    'key79557': 'value69242',
    'key9785': 'value87253',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Jennifer Morales MD',
    'address': '379 Reyes Squares\nNorth Emily, FM 27188',
    'text': 'Raise stand old light leave look far.\nCreate will I interesting movement. Responsibility any those team factor treat.\nKitchen firm player hospital car ask source.',
    'email': 'ryan18@example.com',
    'phone_number': '+1-414-918-2369x730',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kelli Alexander',
    'Derrick Mendoza',
    'Tina Lee',
    'Donna Davis',
    'David Perez',
    'Mr. Ricky Francis',
    'Ann Wheeler',
    'Adam Burns',
    'Benjamin Gomez',
],
    'json': {
    'name': 'Kevin Ferguson',
    'address': '71523 Petty Knolls Suite 135\nCaitlinview, HI 65767',
},
    'key43264': 'value63742',
    'key40377': 'value71938',
    'key61313': 'value79699',
    'key69550': 'value19339',
    'key11496': 'value73527',
    'key65815': 'value557',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Theresa Dalton',
    'address': '3109 Quinn Extension Suite 396\nEast Brandybury, TN 72761',
    'text': 'Marriage second phone reality often quickly. Agent save act less.',
    'email': 'qschaefer@example.org',
    'phone_number': '526-940-0029x1089',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Patrick',
    'John White',
],
    'json': {
    'name': 'James Rogers',
    'address': 'Unit 5756 Box 4995\nDPO AA 73287',
},
    'key83258': 'value23812',
    'key52771': 'value23985',
    'key36600': 'value36896',
    'key31984': 'value84009',
    'key33626': 'value50258',
    'key6287': 'value26752',
    'key89780': 'value66417',
    'key39234': 'value58336',
    'key39885': 'value12885',
    'key14419': 'value59914',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Kenneth Williams',
    'address': '0057 Meyer Junction Apt. 949\nMcfarlandhaven, TX 73825',
    'text': 'Another thank us sister successful during left some. Seven price manager grow.\nBit notice attention water back buy exactly. Stuff most lead late oil friend floor.',
    'email': 'jennifer32@example.com',
    'phone_number': '001-206-253-0697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth James',
],
    'json': {
    'name': 'Brad Nelson',
    'address': '66908 Traci Ridges\nGreenmouth, SC 06450',
},
    'key2395': 'value60529',
    'key44908': 'value70131',
    'key1290': 'value77078',
    'key73022': 'value58635',
    'key9952': 'value47447',
    'key3668': 'value97999',
    'key96152': 'value71141',
    'key1345': 'value46817',
    'key45002': 'value1420',
    'key91120': 'value29753',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Vanessa Gates',
    'address': '19534 Alicia Garden\nNew Linda, IA 15484',
    'text': 'Style ability from five owner expect relate. General agreement north.\nHold family lose she visit dog simple. Skin behavior will consider doctor.',
    'email': 'michael17@example.com',
    'phone_number': '001-989-217-2334x596',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Peterson',
    'Michael Bradley',
    'Christine Bowen',
],
    'json': {
    'name': 'Rachel Wiley',
    'address': '390 Megan Crossroad Apt. 929\nNew Cindyton, IL 48471',
},
    'key85338': 'value98456',
    'key45927': 'value18104',
    'key69307': 'value25169',
    'key25207': 'value86377',
    'key25789': 'value61796',
    'key5542': 'value24132',
    'key69068': 'value48738',
    'key52690': 'value65383',
    'key60119': 'value89492',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Jonathan David',
    'address': '963 Mcgrath Squares Suite 950\nLaurieland, SD 51732',
    'text': 'Try citizen trip increase service rule. Magazine local may every piece class. Impact avoid according lawyer future argue.',
    'email': 'ibarrakimberly@example.org',
    'phone_number': '959-990-7780x060',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christina Martinez',
    'Gregory Barton',
    'Richard Webb',
    'Antonio Oconnor',
    'Katie Travis',
    'Laurie Lester',
    'Angela Meyer',
    'Charles Robinson',
    'Kristy Garcia',
],
    'json': {
    'name': 'Kevin Mcdaniel',
    'address': '26847 Joshua Groves Suite 545\nTamarachester, GU 80890',
},
    'key16497': 'value60307',
    'key63821': 'value12501',
    'key44009': 'value15501',
    'key39840': 'value73753',
    'key32662': 'value1189',
    'key10981': 'value50599',
    'key98133': 'value60111',
    'key57009': 'value78908',
    'key93980': 'value63350',
    'key3185': 'value85091',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Rebecca Smith',
    'address': '562 Jason Parkways Apt. 457\nSmithville, VI 10772',
    'text': 'Put than design. Draw loss green action American attack great exist. White popular will forward thus per. Piece catch law throughout main interview.',
    'email': 'stevencantu@example.org',
    'phone_number': '+1-955-764-7152x527',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Thompson',
    'Miss Crystal Gonzalez',
    'Cynthia Johnson',
    'Sarah Clark',
],
    'json': {
    'name': 'Jennifer Moore',
    'address': '7036 Christine Village Suite 301\nDavisville, TX 79448',
},
    'key19784': 'value92250',
    'key50029': 'value46216',
    'key68500': 'value12691',
    'key71094': 'value68127',
    'key52636': 'value21106',
    'key30684': 'value2652',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Matthew Rodriguez',
    'address': 'PSC 9250, Box 2352\nAPO AA 40509',
    'text': 'Writer control anyone policy. Sea wife heart. Best condition adult student. Forget gas seek newspaper environmental minute someone.',
    'email': 'amanda13@example.net',
    'phone_number': '410.982.4371x201',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Todd Henderson',
    'Julie Rice',
    'Garrett Perkins',
    'Donald Galloway',
    'Anthony Dawson',
    'Janet Welch DDS',
    'Tammy Brown',
    'Kaitlin Mcintosh',
    'Andrea Thompson',
    'Philip Brooks',
],
    'json': {
    'name': 'Isaiah Martin',
    'address': '229 Owens Heights\nSouth Carolfort, UT 00572',
},
    'key77332': 'value72992',
    'key81302': 'value20433',
    'key44247': 'value78725',
    'key61944': 'value64282',
    'key30752': 'value66804',
    'key34287': 'value76037',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Kristi Smith',
    'address': '07741 Amanda Flats\nEast Candace, KY 90884',
    'text': 'Drug season story certain war somebody. Rate hot boy push will.\nCongress become pattern himself another behavior scientist. Today scientist understand. Build represent music then without along pass.',
    'email': 'caleb96@example.net',
    'phone_number': '001-235-754-0670x4742',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sydney Rose',
    'Leslie Mckinney',
    'Julie Cruz',
    'James Werner',
    'Matthew Johnson',
    'Mindy Cox',
    'David Adams',
    'Erica Flores',
    'Christopher Freeman',
],
    'json': {
    'name': 'Benjamin Lyons',
    'address': '95184 Lindsey Run Suite 050\nSouth Stephen, NC 82636',
},
    'key95704': 'value82237',
    'key41655': 'value54748',
    'key83419': 'value12659',
    'key86346': 'value57726',
    'key64086': 'value89353',
    'key45794': 'value41620',
    'key9272': 'value43860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Willie Lopez',
    'address': '3185 Shelly Streets Apt. 297\nAprilville, MH 10539',
    'text': 'Candidate wife international protect. Worry foreign campaign quite stop position. Activity go address hot impact.\nRespond suffer minute tend care want world. Thus company although indeed buy know.',
    'email': 'andrew32@example.org',
    'phone_number': '+1-863-890-3024x808',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Roman',
    'Carly Macdonald',
],
    'json': {
    'name': 'Stacey Tapia',
    'address': '27696 Ray Greens Suite 821\nEast Joel, MP 20106',
},
    'key45929': 'value95542',
    'key21037': 'value11945',
    'key71142': 'value42856',
    'key93679': 'value35952',
    'key71725': 'value17396',
    'key86298': 'value1792',
    'key28741': 'value58319',
    'key97563': 'value76642',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Denise Singh',
    'address': 'USCGC Turner\nFPO AA 51474',
    'text': 'Bed everyone race generation. Raise oil fund participant company. For quickly those relationship fly strategy.',
    'email': 'simmonssandra@example.com',
    'phone_number': '368-806-8352',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Newton',
    'Philip Allen',
    'Douglas Francis',
    'Russell Clark',
    'Gregory Williams',
    'Lawrence Patterson',
    'Ashley Torres',
    'Jacqueline Davies',
],
    'json': {
    'name': 'Karen Bryan',
    'address': '7187 Grace Mount Apt. 840\nNew Amandafort, OR 64475',
},
    'key7473': 'value33985',
    'key72552': 'value43218',
    'key23359': 'value29643',
    'key53165': 'value8615',
    'key64962': 'value55738',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Katherine Morgan',
    'address': '70322 Katie Center Apt. 718\nSouth Aaron, KS 85927',
    'text': 'Pattern significant knowledge writer value and hair stuff. Hard help better happen activity spend enjoy single.',
    'email': 'gary06@example.com',
    'phone_number': '2596610386',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Susan Harrington',
    'Heather Gray',
    'Kayla Buckley',
    'Kevin Harris',
    'John Anderson',
    'Todd Smith',
    'Jennifer Smith',
    'Justin Jones',
],
    'json': {
    'name': 'Randall Perez',
    'address': '842 Ernest Gardens Apt. 518\nRuthtown, KY 45240',
},
    'key21871': 'value87314',
    'key58727': 'value44333',
    'key10172': 'value75428',
    'key59691': 'value23188',
    'key62343': 'value9336',
    'key36358': 'value3956',
    'key99188': 'value61795',
    'key44941': 'value91879',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Kristen Hernandez',
    'address': '71321 Joann Cliff\nPort Jack, OK 20389',
    'text': 'Fish firm nearly necessary choice particular. About some away any could. So second son child material TV.\nLawyer challenge garden unit investment. Civil of bring ten.',
    'email': 'susanjohnson@example.com',
    'phone_number': '6549398003',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Johnson',
    'Connie Adams',
    'Pamela Arroyo',
    'Calvin Smith',
    'Elizabeth Williams',
],
    'json': {
    'name': 'Catherine Rowe',
    'address': '966 Stephenson Stravenue\nWest Krystalmouth, OK 41485',
},
    'key5743': 'value17776',
    'key12780': 'value20609',
    'key4501': 'value13995',
    'key59897': 'value88981',
    'key30698': 'value88348',
    'key99679': 'value80418',
    'key14884': 'value46891',
    'key13855': 'value10954',
    'key36853': 'value12626',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Katie Mooney',
    'address': '623 Troy Heights Suite 067\nDanielton, OH 94025',
    'text': 'Probably agent nearly effort agree. Data cold student. Senior political cell ball guess before specific.\nMain perform south discuss on true opportunity learn. During role however charge.',
    'email': 'hayeskathleen@example.com',
    'phone_number': '(249)739-3547',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Cruz',
    'Dalton Barton',
    'Paul Nelson',
    'Dawn Steele',
    'Brandi Hernandez',
    'Lisa Thomas',
    'Amy Barker',
    'Troy Wood',
    'Lauren Rodriguez',
    'Donald Robinson',
],
    'json': {
    'name': 'Michelle Pittman',
    'address': '1250 William Green Suite 984\nKristimouth, ID 62372',
},
    'key27692': 'value81763',
    'key20222': 'value81532',
    'key15425': 'value34680',
    'key32334': 'value54403',
    'key20413': 'value36175',
    'key71782': 'value27406',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Michael Obrien',
    'address': '714 Joyce Pass Apt. 770\nLake Chelseamouth, MH 34163',
    'text': 'Up box thank draw. Doctor type win certain.\nLead town hear before strong figure this. Eight network despite even rule that public.',
    'email': 'gwarren@example.com',
    'phone_number': '(241)629-8035x566',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Rowe',
    'Emily Branch',
    'Dominic Evans',
],
    'json': {
    'name': 'Brian Mcgrath',
    'address': '63845 John Divide\nLake Pamelabury, SC 63315',
},
    'key68648': 'value94520',
    'key34713': 'value82775',
    'key25144': 'value33300',
    'key73102': 'value77407',
    'key18391': 'value22972',
    'key61048': 'value57848',
    'key81555': 'value85763',
    'key97750': 'value54080',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Linda Bowman',
    'address': '59100 Kristen Mews\nAbbottberg, NC 24872',
    'text': 'Environment us special western if. Everything wear beat mind.\nStep within sister past series. Smile arm in trouble.\nTruth notice explain. Anything pattern anything. Exist small do arrive ball.',
    'email': 'mary95@example.org',
    'phone_number': '6677432591',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sean Thornton',
],
    'json': {
    'name': 'Jordan West',
    'address': '436 Austin Freeway\nAndersonbury, MA 58391',
},
    'key23211': 'value14299',
    'key71974': 'value79243',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Thomas Williams',
    'address': '9761 Angela Greens\nNorth Nathanhaven, ND 96240',
    'text': 'Staff across perform street age with. Compare sister almost add bit population.\nCondition fly standard serve each history. Movement agent thus.',
    'email': 'butlerbrittany@example.net',
    'phone_number': '425-395-8555',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Richard Vazquez',
    'Jeffrey Long',
    'Robert York',
    'Ashley Martin',
    'Barry Clements',
    'Joshua Meyer',
    'Natalie Vaughn',
    'Ronnie Wilson',
],
    'json': {
    'name': 'Erika Jones',
    'address': '49740 Melissa Park Suite 904\nJosephbury, VA 77128',
},
    'key61734': 'value50289',
    'key79534': 'value59868',
    'key95686': 'value76463',
    'key95988': 'value48990',
    'key58983': 'value73045',
    'key43676': 'value80922',
    'key91486': 'value74795',
    'key139': 'value45016',
    'key48780': 'value1471',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Jeffrey Cole',
    'address': 'PSC 4103, Box 1819\nAPO AP 93009',
    'text': 'Maintain owner just deal upon. For above town.\nMay soon range white development. Any industry detail require where.',
    'email': 'andersonbrandon@example.net',
    'phone_number': '001-309-472-5158',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Oscar Smith',
    'Monique Wright',
    'Luis Bird',
    'Patrick Gonzalez',
],
    'json': {
    'name': 'Sarah Walters',
    'address': '660 Randall River\nDonaldside, ND 34765',
},
    'key50736': 'value24885',
    'key11432': 'value43762',
    'key65574': 'value96175',
    'key6537': 'value98858',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Elizabeth Alexander',
    'address': '1712 Shawn Pine Suite 967\nMckinneymouth, NC 86553',
    'text': 'Stay term issue big season. Suddenly wind speak age company.\nShould fund million see record. Talk activity must else. Near hundred push then feeling receive writer interesting.',
    'email': 'frankbowman@example.org',
    'phone_number': '948.525.3101x16792',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Franco',
    'Brian Fields',
    'Nicholas Mendoza',
    'Brandy Matthews',
    'Daniel Wolf',
    'Mark Wyatt',
    'April Curry',
],
    'json': {
    'name': 'Morgan Walker',
    'address': '7937 Long Spurs\nDavidburgh, AL 46022',
},
    'key79554': 'value1345',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Alicia Berry',
    'address': '78649 Garrett Plains\nDavidton, SC 19139',
    'text': 'Fear wonder list. Have phone current argue price. Between conference when decade reveal fight form make.\nParent move whatever I get life laugh drive. Beyond black opportunity.',
    'email': 'johnsonjake@example.net',
    'phone_number': '611-809-2516',
    'array_int_dynamic': [
    34515,
],
    'array_varchar_dynamic': [
    'Lucas Hernandez',
    'Jesse Foster',
    'David Matthews',
    'Stephanie Johnson',
    'Michelle Wilson',
],
    'json': {
    'name': 'Erin Zhang',
    'address': '02664 Luis Lodge\nSosabury, MA 50643',
},
    'key95406': 'value2970',
    'key87107': 'value4889',
    'key93060': 'value43474',
    'key79545': 'value43783',
    'key81274': 'value67908',
    'key77984': 'value56496',
    'key16144': 'value21397',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'John Wallace',
    'address': '29287 Duncan Terrace\nTiffanyhaven, MT 95048',
    'text': 'Charge believe economy. Indicate create decide crime another arrive can though. Him above tonight certainly reveal month yes attention.',
    'email': 'blairjohn@example.com',
    'phone_number': '377-847-8875x18092',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Morgan',
    'Melissa Perkins',
    'Walter Flynn',
    'Scott Lewis',
    'Stacie Guerrero',
    'Samuel Lucas',
    'Joseph Fernandez',
],
    'json': {
    'name': 'Joshua Ortiz',
    'address': '66815 Davis Pine Suite 076\nYoungside, MA 51346',
},
    'key12305': 'value63598',
    'key93892': 'value22905',
    'key16920': 'value14907',
    'key51691': 'value56495',
    'key93091': 'value20325',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Jamie Warner',
    'address': '2544 Barton Rapid\nNew Pamelamouth, CT 73891',
    'text': 'Maintain measure politics positive college development. Expect begin walk.\nTry at vote deep be. Exist lead mission within recently future.',
    'email': 'qmoss@example.com',
    'phone_number': '944.781.4495x15686',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Melinda Jones',
    'Heather Singleton',
    'Wayne Green',
    'Melissa Erickson',
    'Diane Thompson',
    'Linda Bruce',
    'Sheri Smith',
    'Sherry Dougherty',
    'Mary Cobb',
    'Jennifer Munoz',
],
    'json': {
    'name': 'Mackenzie Mueller',
    'address': '181 Scott Harbors Apt. 752\nPort Michaelfort, RI 10783',
},
    'key38358': 'value9818',
    'key11033': 'value14274',
    'key72316': 'value10944',
    'key76162': 'value94220',
    'key84927': 'value643',
    'key38330': 'value70443',
    'key98703': 'value64205',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Jessica Martin',
    'address': '2941 Cook Parkways\nLopezburgh, NV 52826',
    'text': 'Thing may staff property. Occur law recently win. Than hotel participant. Ago attorney financial wall mission.',
    'email': 'ortegabenjamin@example.org',
    'phone_number': '+1-988-621-2049x072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Erickson',
    'Heidi Lamb',
    'Brandi Phillips',
    'John Harrison',
    'Harold Long',
],
    'json': {
    'name': 'Candace Salazar',
    'address': '22843 Hicks Land Suite 560\nNorth Andrew, CO 75498',
},
    'key26310': 'value7663',
    'key68230': 'value98007',
    'key97319': 'value80548',
    'key58013': 'value33121',
    'key44764': 'value99908',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Helen Jones',
    'address': '89281 Johnson Summit Suite 477\nEast Michaelland, NC 87192',
    'text': 'Dinner effort form music artist. Interesting may pattern democratic quite.\nLand place western admit never fight. Network again place base.',
    'email': 'kathrynstone@example.com',
    'phone_number': '797-677-1043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Hanna',
],
    'json': {
    'name': 'Robert Summers',
    'address': '1231 Julie Radial\nLake Chadshire, AL 81536',
},
    'key21685': 'value34132',
    'key7530': 'value99181',
    'key24542': 'value85111',
    'key72838': 'value84206',
    'key65673': 'value74778',
    'key57350': 'value36142',
    'key13855': 'value66588',
    'key75011': 'value13863',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Angela White',
    'address': '260 Pearson Meadow\nBurnsborough, AS 51413',
    'text': 'Level house plan. Interest compare through box cost drop arrive.\nSomebody stock reduce market somebody. Others ok believe board choice.',
    'email': 'elizabeth82@example.com',
    'phone_number': '001-520-506-5954',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Taylor',
    'Brooke Hicks',
    'Justin Craig',
    'Jesse Hughes',
    'Mr. Joseph Harper PhD',
    'Judy Buckley',
],
    'json': {
    'name': 'Julie Olson',
    'address': '8264 White Shoals Apt. 569\nAustintown, UT 47323',
},
    'key54438': 'value26198',
    'key41172': 'value41831',
    'key58454': 'value19562',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Judy Peterson',
    'address': '230 Jessica Land\nPort Antonio, ND 82590',
    'text': 'Responsibility couple several similar beat baby. Fire gun focus moment. Out citizen certain article because free too.',
    'email': 'melissagolden@example.com',
    'phone_number': '001-212-839-8693x7834',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Cook',
    'Andrew Adams',
    'Robert Miller',
    'Jessica Bell',
    'Alicia Taylor',
    'Taylor Cervantes',
],
    'json': {
    'name': 'Edward Gonzales',
    'address': '80606 Howe Skyway\nNew Amberton, WA 48114',
},
    'key88143': 'value93251',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Charles King',
    'address': '162 Taylor Centers\nVanessaborough, AZ 09998',
    'text': 'Official already stand bag. Nation program task over seek model cultural.\nWait sometimes other pass. Feel surface seven cost white evening program dream.',
    'email': 'mtaylor@example.org',
    'phone_number': '289-966-1113',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Todd Anderson',
    'John Love',
    'Jack George',
    'Mr. Michael Walker DDS',
    'Steven Jimenez',
],
    'json': {
    'name': 'Emily Roach',
    'address': '797 Tanner Bridge Suite 361\nPort Heatherberg, IN 50176',
},
    'key35030': 'value88299',
    'key44696': 'value98740',
    'key99082': 'value80216',
    'key16531': 'value11953',
    'key36758': 'value46894',
    'key41848': 'value28624',
    'key75179': 'value79614',
    'key12825': 'value22875',
    'key4749': 'value85547',
    'key18168': 'value65486',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Ashley Hernandez',
    'address': '01134 Ashlee Shore\nHornmouth, PR 67304',
    'text': 'Item into shake between second believe. Attack full lose customer left fill political key. Wish purpose work present.\nBad phone several activity person. Hit while manager star notice ago.',
    'email': 'bobby64@example.org',
    'phone_number': '436.575.0400x13791',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Tran',
    'Leah Brown',
    'Charles Allen',
],
    'json': {
    'name': 'Daniel Martinez',
    'address': '30614 Norma Cove\nWest Travisborough, OK 77541',
},
    'key8193': 'value58090',
    'key56056': 'value82509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Emily Stewart',
    'address': 'PSC 1478, Box 5755\nAPO AA 23282',
    'text': 'Bad as ahead movie. Skin series gas real left. Fall play meet law especially.\nReveal theory statement along yeah. Top kitchen especially down.\nCapital father edge media. Become level drop sea.',
    'email': 'garzatina@example.com',
    'phone_number': '4638447766',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Allen Clayton',
    'Louis Mullen',
    'Traci Kerr',
    'Sara Frederick',
    'Mitchell Floyd',
    'Jesse Wallace',
    'Kelly Barber',
    'Nathan Flores',
    'Veronica Stanley',
],
    'json': {
    'name': 'Thomas Miller',
    'address': '13150 Cochran Shore\nRalphtown, MI 05456',
},
    'key64963': 'value20228',
    'key84617': 'value14064',
    'key94013': 'value45173',
    'key14577': 'value18747',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Christina Mcknight',
    'address': '509 Davis Plains Suite 032\nPort Ronald, ME 15393',
    'text': 'Reduce company energy democratic turn wait get. Senior number mean rich kid statement. Research only performance often market none.',
    'email': 'michele59@example.org',
    'phone_number': '001-323-940-1532x04580',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Montoya',
    'Mitchell Ryan',
    'April Brady',
],
    'json': {
    'name': 'Carolyn Johnson MD',
    'address': '147 Stephanie Freeway Apt. 706\nColeshire, VT 79827',
},
    'key55317': 'value79928',
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
    'RequestId': '2ec780f6-62f1-11f0-af3f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_53_722999BfOwoAvv',
    'filter': 'uid > 0',
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
        """测试请求 3 - POST http://172.17.0.5:23210/v1/vector/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': '2f66080c-62f1-11f0-a9a8-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_53_722999BfOwoAvv',
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
    'RequestId': '280f8453-62f1-11f0-8bf0-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_33_53_722999BfOwoAvv',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid > 0_1]_1752744847.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUid011752744847Json()
    test.run_tests()
