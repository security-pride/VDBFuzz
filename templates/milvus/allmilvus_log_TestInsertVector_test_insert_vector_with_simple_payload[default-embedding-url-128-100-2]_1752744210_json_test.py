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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-2]_1752744210_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-2]_1752744210.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl12810021752744210Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-2]_1752744210.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-2]_1752744210.json"
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
    'RequestId': 'b360f375-62ef-11f0-a95d-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_28_466539PEpORUdD',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
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
    'RequestId': 'b382bc4b-62ef-11f0-9c41-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_28_466539PEpORUdD',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Karen Peterson',
    'address': '5091 Andrea Alley\nEast Richardstad, TN 94713',
    'text': 'Sound hear research boy part should prepare. Hot policy foreign. Every option production factor.',
    'email': 'omacdonald@example.net',
    'phone_number': '489.579.3192x6833',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Heather Taylor',
    'William Cruz',
    'Hailey Simon',
    'Tammie Hanson',
    'Travis Jackson',
],
    'json': {
    'name': 'Tami Sims',
    'address': '3000 Jason Circle Suite 897\nRobertmouth, UT 88632',
},
    'key24369': 'value67709',
    'key3048': 'value91081',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Kerri Reid',
    'address': '3089 Elizabeth Pines Suite 369\nNew Donna, NH 65869',
    'text': 'Catch girl your design. Goal despite soldier. Mrs officer eat news. Happy agreement ahead low article generation dream how.',
    'email': 'watsonaustin@example.net',
    'phone_number': '+1-386-404-9388x441',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Murray',
    'Shawn Lee',
    'Jason Mcdonald',
    'Jeffrey Harris',
    'Matthew Davidson',
    'Victoria Kelly',
    'William Knox',
],
    'json': {
    'name': 'Jamie Sanders',
    'address': '7410 Potter Stravenue Apt. 210\nKaitlynshire, PA 13970',
},
    'key9828': 'value89597',
    'key18626': 'value47385',
    'key68523': 'value28358',
    'key74915': 'value62604',
    'key46476': 'value14668',
    'key78511': 'value11580',
    'key87637': 'value26560',
    'key62391': 'value55684',
    'key35197': 'value71226',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Richard Hall',
    'address': '643 Peterson Radial\nLake Mark, NH 82621',
    'text': 'Performance skin though another fear.',
    'email': 'hhernandez@example.com',
    'phone_number': '(756)845-8520x9432',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Rodriguez',
    'Brian Watson',
    'John Daniel',
    'Franklin Ryan',
    'Jason Jackson',
    'Danny Chapman',
    'Carolyn Sampson',
    'April Adams',
    'Jonathan Garcia',
],
    'json': {
    'name': 'Jonathan Bond',
    'address': '2718 Potter Mount\nSouth John, GA 74928',
},
    'key68762': 'value51722',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Cynthia Mitchell',
    'address': '00259 Weeks Estate Apt. 705\nBrooksborough, CA 49359',
    'text': 'Full main hear. Half key campaign movement. Whether certainly all finally else report recent.\nHerself power star gun. Listen player data best.',
    'email': 'jacobsnatalie@example.net',
    'phone_number': '+1-751-452-9648',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Margaret Harmon',
    'Michele Carney',
    'Dustin Olson',
    'Caleb Roberson',
    'Vanessa Dominguez',
    'Nicole Parker',
    'Stephen Chandler',
],
    'json': {
    'name': 'Daniel Porter',
    'address': '285 Patel Brook\nCoxmouth, GA 92636',
},
    'key93143': 'value58796',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Alan West',
    'address': '38476 Amy Parkway\nNorth Ryan, MO 09227',
    'text': 'Officer lose sort themselves collection its letter. Until rather describe away sometimes family less. Child record effect form loss ask.',
    'email': 'schwartzcheryl@example.com',
    'phone_number': '(322)639-0218x95284',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Derek Strickland',
    'Robert Summers',
    'Andrew Turner',
    'Jeremy Mann',
],
    'json': {
    'name': 'Todd Scott',
    'address': '275 Elizabeth Corner\nJacobview, AZ 24356',
},
    'key37358': 'value20116',
    'key61525': 'value43008',
    'key84979': 'value84836',
    'key38114': 'value79809',
    'key14134': 'value53678',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Marcus Sullivan',
    'address': '5709 Mark Villages Apt. 478\nEast Elizabethville, WI 98238',
    'text': 'Relationship establish street computer. Campaign image face author involve laugh eat. Student easy painting center.\nNotice long minute industry opportunity seat. Hotel occur pick attention.',
    'email': 'christopher94@example.net',
    'phone_number': '618.684.9043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Smith',
    'Jasmine Franklin',
    'Joy Scott',
    'Timothy Allen',
    'Brian Hobbs',
    'Steven Simpson',
    'Lisa Brown',
    'Mark Duncan',
],
    'json': {
    'name': 'Jenna Mcclain',
    'address': '346 Richards Greens\nLake Jeffrey, WY 71614',
},
    'key54303': 'value9803',
    'key69477': 'value1833',
    'key15169': 'value59745',
    'key4558': 'value1540',
    'key11630': 'value82284',
    'key14275': 'value35750',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Jessica Flores',
    'address': '89266 Johnson Mews Suite 865\nPort Jeffrey, SC 29606',
    'text': 'Low by agree very. Foot notice girl floor.\nSit drop also born him imagine. Class price wide staff wrong dream maybe human. Have a owner real create land six.',
    'email': 'deborahgonzalez@example.net',
    'phone_number': '001-413-218-1207x9195',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Smith',
    'Scott Evans',
    'Christina Alvarado MD',
    'Dwayne Ramirez',
    'Sheila Maldonado',
],
    'json': {
    'name': 'Robert Mcguire PhD',
    'address': '57586 Kemp Divide\nFullerbury, CA 61866',
},
    'key90908': 'value55385',
    'key61133': 'value14779',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Timothy White',
    'address': '3166 Holly Street Apt. 349\nChadberg, MS 78904',
    'text': 'Mission baby yes risk view. Stock window fear spend.\nSell cover approach arrive sister night up. Anyone vote it mouth former yeah free.',
    'email': 'umiller@example.com',
    'phone_number': '500.406.8711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Smith',
    'Nathaniel Deleon',
    'Patricia Byrd',
    'Daniel Ford',
],
    'json': {
    'name': 'Joyce Stone',
    'address': '520 Susan Locks Apt. 635\nLake Sylviaville, ND 06683',
},
    'key51120': 'value59308',
    'key23337': 'value92793',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Kelly Sutton',
    'address': '53190 Harper Place\nMoorebury, FL 76457',
    'text': 'Data head write.\nLive offer side minute task daughter school. Perhaps size bit product game piece. Chance become evidence accept option for office.',
    'email': 'wwagner@example.org',
    'phone_number': '+1-311-944-4686x18052',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Martin',
    'Laura Fernandez',
    'Andre Ho',
    'Michelle Mcdonald',
    'Ryan Fletcher',
    'Tyler Rogers',
    'Jeremy Morgan',
],
    'json': {
    'name': 'Brandi Sullivan',
    'address': '41964 Paul Estate Apt. 489\nEast Denisefurt, AR 84278',
},
    'key16021': 'value36148',
    'key36590': 'value3858',
    'key65829': 'value64155',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Brenda Bailey',
    'address': '89817 Julia Key\nSmithbury, CT 45564',
    'text': 'Before once test off attack bill. Film prove my boy.\nUpon radio record realize again. Foreign leader project condition head military.',
    'email': 'sstewart@example.com',
    'phone_number': '422-452-7047',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James Contreras',
    'Deanna Carlson MD',
    'Patricia Moreno',
    'Jessica Fernandez',
    'Paul Guzman',
],
    'json': {
    'name': 'Tommy Oliver',
    'address': '180 Nguyen Port\nNew Scott, DE 00796',
},
    'key10876': 'value86207',
    'key55751': 'value9886',
    'key43165': 'value75006',
    'key21633': 'value91457',
    'key22361': 'value11218',
    'key11328': 'value48067',
    'key37633': 'value4430',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Jasmin Anderson',
    'address': '8044 Norton Courts\nBrianfort, ME 59039',
    'text': 'Happen write upon wall successful. Major data again decision ball color. Involve memory tend past man whose.',
    'email': 'daniel14@example.org',
    'phone_number': '345-393-7685x2454',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Adams',
    'Christine Collins',
    'Kimberly Mckay',
    'Troy Montgomery',
    'Colton Leonard',
    'Brandon Cox',
    'Robert Acosta',
],
    'json': {
    'name': 'Sabrina Williams',
    'address': '51319 Kristy Shores Suite 818\nBrianfurt, IA 36823',
},
    'key95592': 'value82170',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Laura Miller',
    'address': '13494 Jamie Valleys Apt. 191\nVargasmouth, MI 96036',
    'text': 'Hear direction gas a magazine.\nMrs man probably responsibility both. Several type building financial bar road. Dog bit cold apply cup.',
    'email': 'kellynatalie@example.org',
    'phone_number': '001-678-912-4586x2781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Paul Garcia',
    'Rebecca Knox',
    'Larry Bell',
    'Ana Williams',
    'Michael Horne',
],
    'json': {
    'name': 'Nathaniel Baldwin',
    'address': 'PSC 3847, Box 5632\nAPO AA 04374',
},
    'key52012': 'value74125',
    'key80931': 'value17550',
    'key30092': 'value67063',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Gregory Sanders',
    'address': '59878 Harper Rue Suite 846\nNew Katherineberg, AK 82320',
    'text': 'Center challenge red education administration. Image exist art concern already truth generation front. Even new question heart.\nFall travel seem really. Manager since mouth along.',
    'email': 'deborah44@example.com',
    'phone_number': '222.766.2931x9797',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Erin Hughes',
    'Alyssa Thomas',
    'Lori Sullivan',
],
    'json': {
    'name': 'Renee Harrison',
    'address': '07094 Hall Trail Suite 555\nTrevortown, ID 67429',
},
    'key83070': 'value98363',
    'key64022': 'value74053',
    'key89538': 'value24328',
    'key60351': 'value23929',
    'key60093': 'value89033',
    'key6383': 'value97382',
    'key22745': 'value56192',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Christopher Rodriguez',
    'address': '8602 Abbott Junctions Apt. 394\nPort Joseph, NJ 97009',
    'text': 'Right pretty condition might agency catch. At sister million play property nature. National per window news positive image detail pretty. Down training particularly various bank again civil.',
    'email': 'nicholasmartin@example.com',
    'phone_number': '874.548.0119',
    'array_int_dynamic': [
    13818,
],
    'array_varchar_dynamic': [
    'William Pollard',
    'Brent Martinez',
    'Christian Dixon',
    'Kristin Washington',
    'Terri Smith',
    'Sean Dickerson',
],
    'json': {
    'name': 'Danielle Crawford',
    'address': '573 Anne Street\nNew Christopher, IN 58589',
},
    'key82733': 'value81363',
    'key14159': 'value33572',
    'key69122': 'value64593',
    'key99853': 'value41680',
    'key59265': 'value34768',
    'key59015': 'value98926',
    'key4697': 'value45159',
    'key10448': 'value64877',
    'key69323': 'value93384',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Sharon Harris',
    'address': '66644 Conley Cape Suite 968\nSmithfurt, AL 20646',
    'text': 'Election skill baby wrong star method detail. Language stop operation better show.\nBy meet nation smile wind. Change hotel least unit. Particularly sit spring just hot many white.',
    'email': 'waltermiller@example.com',
    'phone_number': '(411)839-0051x6429',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tina Cruz',
    'Samantha Harrison',
    'Amber Fitzgerald',
    'Joseph Molina',
    'Sara Sherman',
    'Luis Nichols',
    'Dr. James Bryant DVM',
    'Kerry Williams',
    'Emma Harper',
    'Katherine Miller',
],
    'json': {
    'name': 'Patrick Christensen',
    'address': '472 Casey Mill\nMatthewview, PW 46950',
},
    'key67140': 'value90014',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Kristina Ramirez',
    'address': '901 Rhonda Square Apt. 611\nFarrellton, AR 48368',
    'text': 'Later sometimes head company full. Little sister including great weight clearly capital even. Drug author usually blue.\nRoad toward law too notice hand. Second lose order day this letter high.',
    'email': 'maldonadoelizabeth@example.com',
    'phone_number': '(760)550-3095x0823',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Felicia Harris',
    'Ann Gray',
    'Eileen Thomas',
    'Alexander Frazier',
    'Jeffrey Nixon',
],
    'json': {
    'name': 'Kendra Bennett',
    'address': '8458 Davies Circle\nPort Rubenhaven, AZ 53940',
},
    'key18117': 'value25261',
    'key95149': 'value17050',
    'key15872': 'value94887',
    'key80575': 'value60293',
    'key51162': 'value17364',
    'key96579': 'value88004',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Courtney Douglas',
    'address': '143 Nancy Village\nEstesburgh, KS 58530',
    'text': 'Hit type else participant card although. Air pattern though support stay dream technology.\nPiece her ahead food. Simple Congress join which begin despite staff. Start charge relate.',
    'email': 'kpalmer@example.net',
    'phone_number': '001-225-916-8820x325',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Wood',
],
    'json': {
    'name': 'Gina Boone',
    'address': '839 Fleming Inlet\nMillerton, MI 96359',
},
    'key7687': 'value28681',
    'key58572': 'value74489',
    'key96541': 'value44508',
    'key65169': 'value15618',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Julie Stephens',
    'address': '815 Park Rapids Apt. 275\nAdamsshire, TX 12340',
    'text': 'Meet manager dark prove when. Remember fill here husband single base stock. Gun cover party so free late.\nRole well we company if. Run guy need bank. Administration bank not share.',
    'email': 'opayne@example.net',
    'phone_number': '(395)251-3682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Richard Wells',
    'Diane Johnson',
    'Raymond Krause',
    'Curtis Pacheco',
    'Tiffany Quinn',
    'Kayla Robinson',
    'Nicholas Robles',
],
    'json': {
    'name': 'Lorraine Bird',
    'address': '0327 Tonya Ramp\nPort Jacqueline, IN 41761',
},
    'key19773': 'value49186',
    'key40492': 'value5942',
    'key1902': 'value88435',
    'key76894': 'value92657',
    'key34835': 'value37700',
    'key16350': 'value32015',
    'key22570': 'value83859',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'William Austin',
    'address': '4662 Jennifer Loaf Suite 333\nAtkinsfort, VI 98080',
    'text': 'Front organization call couple dark help. College everything garden participant government.',
    'email': 'garciabonnie@example.net',
    'phone_number': '2443832098',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Molina',
    'William Collins',
    'Catherine Jackson',
    'Sarah Mitchell',
    'Joann Hansen',
    'Mark Harrison',
],
    'json': {
    'name': 'Eric Russell',
    'address': '770 Hall Lake\nDanielville, AR 99271',
},
    'key81098': 'value44237',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jay Sanchez',
    'address': '1657 Montes Via\nJimenezland, AS 18929',
    'text': 'Result however pay case firm us. Evening live choice. Next wind above any amount.',
    'email': 'fosterscott@example.com',
    'phone_number': '403-541-4214x770',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Victor Frazier',
    'Michael Harris',
],
    'json': {
    'name': 'Dorothy Bauer',
    'address': '2450 Linda Terrace Suite 050\nEast Devinside, NJ 16621',
},
    'key80942': 'value10144',
    'key37936': 'value30838',
    'key43439': 'value16570',
    'key56800': 'value88632',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Jessica Stewart',
    'address': 'PSC 8840, Box 8047\nAPO AE 64381',
    'text': 'End ever national hear compare. Whole finish plant feeling office right. Few pick tough.\nFour why event explain. Pay bed despite work land. Street never probably product ask along.',
    'email': 'cobbchristopher@example.com',
    'phone_number': '(602)340-6362x726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Maldonado',
],
    'json': {
    'name': 'Logan James',
    'address': '8426 Andrew Pine Apt. 604\nAmyburgh, VI 53442',
},
    'key6292': 'value21450',
    'key86484': 'value17907',
    'key72103': 'value93466',
    'key42536': 'value73548',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Andrew Jenkins',
    'address': '64398 Krystal Courts Apt. 621\nNorth Hollyton, MH 24898',
    'text': 'Big still put computer. Control identify bank some. Fall seven performance cold song check these.',
    'email': 'gainescarl@example.org',
    'phone_number': '478-399-3395x9472',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michael Norris',
    'Linda Trujillo',
    'Elizabeth Fernandez',
],
    'json': {
    'name': 'Alexis Green',
    'address': '45787 Robert Turnpike Suite 627\nDennischester, HI 21979',
},
    'key68008': 'value78191',
    'key36999': 'value21219',
    'key3360': 'value5476',
    'key67581': 'value64011',
    'key9627': 'value2233',
    'key82720': 'value84235',
    'key94904': 'value37084',
    'key54618': 'value99823',
    'key25763': 'value75674',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Stephen Padilla',
    'address': '22141 Becky Parks\nWest Xaviertown, ND 06163',
    'text': 'Affect inside book while state you too door. Want drive break send figure. Actually mention second.\nHuman behavior manager coach training study. Property resource hand high project dark run.',
    'email': 'zacharyrandall@example.com',
    'phone_number': '+1-465-464-4203x491',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Brown',
    'Franklin Dennis',
    'Heather Jackson',
    'Daniel Garcia',
    'Jeremy Valdez',
    'Shirley Murphy',
    'Madison Hardy',
    'Felicia Parrish',
],
    'json': {
    'name': 'Rachel Garcia',
    'address': '598 Christopher Flats Apt. 094\nSouth Joshua, CA 74625',
},
    'key48227': 'value54843',
    'key90268': 'value68974',
    'key20090': 'value9631',
    'key50291': 'value73636',
    'key19926': 'value23460',
    'key35937': 'value43371',
    'key3866': 'value52784',
    'key71885': 'value12777',
    'key47674': 'value20011',
    'key30268': 'value45937',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Christopher Day',
    'address': '64110 James Ville\nWest Pamelaburgh, PR 94878',
    'text': 'At my me office already. Industry knowledge deep civil. Each candidate police ten energy.\nFull owner else ahead along summer concern. Consider bit learn. Glass machine heavy feeling assume western.',
    'email': 'marymatthews@example.net',
    'phone_number': '399-462-0454x8370',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jodi Patel',
    'Laura Rose',
    'Ashley Lopez',
    'Lisa Barrett',
    'Kristina Brown',
    'Samantha Cruz',
    'Julie Powers',
    'William Rios',
    'Lorraine Lopez',
],
    'json': {
    'name': 'Karen Simpson',
    'address': '98597 Mooney Avenue Apt. 585\nWest Michael, MS 51033',
},
    'key69989': 'value66301',
    'key52665': 'value26627',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Colton Navarro',
    'address': '346 Sharon Crossing\nWest Davidview, AR 48969',
    'text': 'Follow own admit interview almost question. Anything management third. Real fund field result door pattern land.\nResponsibility fact spring today first she. Provide rate even inside meeting.',
    'email': 'danielmccarthy@example.net',
    'phone_number': '(642)826-3858',
    'array_int_dynamic': [
    35484,
],
    'array_varchar_dynamic': [
    'Michael Levy',
    'Jose Oneill',
    'Philip Swanson',
    'Elizabeth Jones',
    'Steven Hicks',
    'Thomas Khan',
    'Kenneth Carter',
],
    'json': {
    'name': 'Nathan Benjamin',
    'address': '104 Kelly Burgs Apt. 516\nLake Sydney, LA 12904',
},
    'key52125': 'value80478',
    'key77776': 'value42405',
    'key68764': 'value80084',
    'key34354': 'value30756',
    'key98567': 'value95786',
    'key50139': 'value74147',
    'key12178': 'value9042',
    'key59692': 'value55880',
    'key76550': 'value94952',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Nathan Davis',
    'address': '08810 Jimenez Green Apt. 762\nHarrisview, ME 40598',
    'text': 'Across simply prevent almost spend knowledge. Down own least million.\nTrue dark gas me tell seven eat. Coach expert director new difficult defense ground. Action idea whatever can.',
    'email': 'deborahroberts@example.com',
    'phone_number': '+1-262-261-5888x3632',
    'array_int_dynamic': [
    99677,
],
    'array_varchar_dynamic': [
    'Sean Roberts MD',
    'Devin Brewer',
],
    'json': {
    'name': 'Joanne Smith',
    'address': 'USCGC Kaufman\nFPO AA 21240',
},
    'key95503': 'value54383',
    'key25835': 'value33628',
    'key21600': 'value66122',
    'key25043': 'value30820',
    'key9350': 'value54020',
    'key62771': 'value13764',
    'key84508': 'value60787',
    'key94364': 'value10114',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Robert Myers',
    'address': '50898 Laura Rest\nChambersland, PR 31995',
    'text': 'Yourself who trouble environment.\nRate machine adult bad. Bag attention social check. Information or serious girl heavy fear. Cause international measure because image avoid usually.',
    'email': 'roachbrittany@example.org',
    'phone_number': '461-559-8829',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Gordon',
    'Alisha Weber DDS',
    'Lindsay Orozco',
    'Lisa Tapia',
    'Monica Mitchell',
    'Mary Thomas',
    'Cynthia Carter',
],
    'json': {
    'name': 'Lonnie Johnson',
    'address': 'USS Wallace\nFPO AP 02968',
},
    'key1401': 'value2286',
    'key83640': 'value74174',
    'key41259': 'value90763',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'William Gibson',
    'address': '312 Sanford Roads Suite 620\nNorth Nicholas, SC 39831',
    'text': 'Entire range board customer oil. Media performance seek to technology help political someone. Technology go and standard continue everyone dark.',
    'email': 'huntjoshua@example.com',
    'phone_number': '(737)298-3677x103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Thompson',
],
    'json': {
    'name': 'Lori Rosales',
    'address': '44680 David Canyon Suite 230\nWest Lauren, AK 45716',
},
    'key61570': 'value68004',
    'key14821': 'value24593',
    'key29624': 'value10719',
    'key59454': 'value13093',
    'key99478': 'value82413',
    'key62075': 'value92469',
    'key83628': 'value99722',
    'key11933': 'value73650',
    'key77354': 'value21905',
    'key93016': 'value38200',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Christopher Boone',
    'address': '0433 Linda Forge Apt. 672\nEmilyfort, MH 84761',
    'text': 'Other event evidence age police. Congress four others wonder hotel.\nBehind himself challenge range movie person. Change ground forget force price. Know either store.',
    'email': 'alyssa71@example.org',
    'phone_number': '822-861-2623x605',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Butler',
    'Michael Gill',
    'Jamie Moore',
    'Mary Hurst',
    'Brooke Snyder',
    'John Brown',
],
    'json': {
    'name': 'Ronald Leon',
    'address': '209 Sean Squares\nNorth Kendra, NY 70081',
},
    'key21964': 'value33818',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Joyce Mathis',
    'address': '63223 Robin Path Apt. 406\nLancemouth, OK 53909',
    'text': 'Know side itself officer send field me more. Other there whatever including huge ground wait. Enjoy black discussion recently.',
    'email': 'ygilbert@example.org',
    'phone_number': '3392210225',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Shelly Sanders',
    'Luke Barrett',
    'Rachel Hoffman',
    'George Leonard',
    'Kevin Colon',
    'Leslie Lopez',
    'Dawn Rush',
    'Kathleen Rodgers',
],
    'json': {
    'name': 'Micheal Marquez',
    'address': '484 Jesse Road\nKimberlychester, AS 97017',
},
    'key47652': 'value46932',
    'key62037': 'value17591',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Angela Bridges',
    'address': '293 Campos Cape\nPort Paulport, DC 29488',
    'text': 'Race act lose Democrat every. Theory tell speech coach concern professor. Deal real could place such suggest democratic.',
    'email': 'sgreen@example.net',
    'phone_number': '340.353.5754',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Martinez',
    'Shelley Watkins',
    'Richard Benson',
    'Richard Anderson',
    'Kim Gonzales',
    'Cynthia Johnson',
    'James Ramirez',
    'Laura Campbell',
    'Kellie Dalton',
    'Brian Harmon',
],
    'json': {
    'name': 'Theresa Murphy',
    'address': 'Unit 9520 Box 7110\nDPO AP 76937',
},
    'key35563': 'value26125',
    'key70737': 'value33817',
    'key91443': 'value72335',
    'key22154': 'value27995',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Annette Price',
    'address': '99367 Mitchell Hollow Suite 546\nHowardmouth, KY 42843',
    'text': 'Detail out table open. Practice claim price authority remain.\nReally discuss surface paper. Step fast against likely leader church instead.',
    'email': 'deannamendoza@example.org',
    'phone_number': '+1-204-744-7131x6532',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jesse Turner',
    'Joseph White',
    'Sherri Rodriguez',
    'Laura Drake',
],
    'json': {
    'name': 'Chad Joseph',
    'address': '6213 Nicole Crest\nWest Jessicaburgh, ND 58098',
},
    'key57964': 'value13464',
    'key1295': 'value38017',
    'key28405': 'value91025',
    'key33063': 'value92006',
    'key17015': 'value46101',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Michelle Crane',
    'address': '29308 April Field Suite 565\nWest Catherine, MI 88962',
    'text': 'Rather foot us smile. Sing none bill red fast.\nBehind night could ok condition discussion cold north. Age one less where nice. Enjoy citizen suggest country pull subject material unit.',
    'email': 'tiffanymiller@example.org',
    'phone_number': '348-352-4316x23960',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Charles Garcia',
    'Theresa Walker',
    'Alexa Ramirez',
    'John Lee',
    'Christina Harris',
    'Derrick Richardson',
],
    'json': {
    'name': 'Adam Moss',
    'address': '76885 Brooks Ports Apt. 897\nPort Davidstad, MA 56761',
},
    'key86820': 'value58823',
    'key12798': 'value26194',
    'key47656': 'value79513',
    'key40524': 'value40820',
    'key25420': 'value30249',
    'key9072': 'value33899',
    'key3872': 'value90363',
    'key26099': 'value85552',
    'key78293': 'value33666',
    'key57491': 'value7213',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michael Salazar',
    'address': '7416 Harrison Course\nJonesport, PA 74363',
    'text': 'They base card including relationship still. Author around able enough meeting.\nVarious your work. Specific quite return however.\nAssume movie movement. Charge idea wind section light.',
    'email': 'rickey64@example.net',
    'phone_number': '001-921-552-7955',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Sara Garza',
    'Kevin Anderson',
    'Sarah Wallace DDS',
    'Keith Keller',
    'Linda Gregory',
],
    'json': {
    'name': 'Michael Holloway',
    'address': '031 Jacob Fords Suite 867\nWangstad, IL 78095',
},
    'key58127': 'value2074',
    'key12409': 'value74104',
    'key84480': 'value47589',
    'key43514': 'value78558',
    'key9453': 'value8877',
    'key82926': 'value60999',
    'key40933': 'value20134',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'William Luna',
    'address': '24454 Harris Valley\nSouth Tiffanymouth, SD 61712',
    'text': 'Decide food deal teacher.\nUpon ability side foot trip again sit. Pressure if really director. Fall scientist indicate rule source oil wife.',
    'email': 'courtney31@example.com',
    'phone_number': '+1-702-991-3303x4160',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Austin Curry',
    'Rebecca Holder',
    'Jordan Curtis',
    'Nicholas Johnson',
    'Cindy Cruz',
    'Charles Gonzales',
    'Kyle Miller',
],
    'json': {
    'name': 'Gina Thompson',
    'address': 'Unit 7432 Box 0144\nDPO AP 56215',
},
    'key76198': 'value17182',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Phillip Dodson',
    'address': '753 Chen Landing Apt. 066\nOconnorfort, MS 12093',
    'text': 'Skill arrive as figure. Form degree cost suggest when check.\nArrive fast society detail talk know knowledge. Can me food knowledge add. Size yeah cover raise.',
    'email': 'jennifergreen@example.org',
    'phone_number': '461-879-5421',
    'array_int_dynamic': [
    67982,
],
    'array_varchar_dynamic': [
    'Thomas Young',
    'Luis Wallace',
    'Mrs. Laura Green',
    'Jessica Chavez',
    'Paul Parker',
],
    'json': {
    'name': 'Kenneth Miles',
    'address': '616 Janice Drive\nNew Charlesshire, IA 63022',
},
    'key46343': 'value26173',
    'key81638': 'value85943',
    'key86211': 'value38521',
    'key26828': 'value84003',
    'key55849': 'value81578',
    'key55533': 'value99009',
    'key41875': 'value49112',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Scott Foster',
    'address': '33207 Theresa Land Suite 890\nNew Sherylland, NE 71605',
    'text': 'Story plant future appear professor degree soldier. Skill any choose participant body phone call. Population piece federal establish somebody lead believe.\nDefense move discussion civil.',
    'email': 'sanchezchristina@example.org',
    'phone_number': '8545049683',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffery Bennett',
    'Nancy Ortiz',
    'Samantha Zamora',
],
    'json': {
    'name': 'Tamara Medina',
    'address': '2044 Hill Springs\nWest Samuel, OH 57729',
},
    'key50478': 'value6011',
    'key60788': 'value59402',
    'key13456': 'value3335',
    'key33740': 'value45909',
    'key51708': 'value17769',
    'key46153': 'value46155',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Catherine Foster',
    'address': '2790 Micheal Park Suite 327\nLewisville, AR 36669',
    'text': 'Ready yet area across drop that. Onto water behavior three face suffer beat consider.\nServe simply best live under. Full onto reach recently. Red same if class learn remember.',
    'email': 'teresamcintosh@example.org',
    'phone_number': '299-338-5545x84223',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tristan Guerrero',
    'Kathy Leach',
    'Karen Morton',
    'David Cantu',
],
    'json': {
    'name': 'Amanda Marshall',
    'address': '9156 Savage Fork\nEdwardbury, NH 82248',
},
    'key51354': 'value84471',
    'key28825': 'value89916',
    'key41670': 'value94028',
    'key98282': 'value45814',
    'key50578': 'value9079',
    'key37926': 'value37534',
    'key3556': 'value78021',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Joyce Hicks MD',
    'address': '74763 Nguyen Mountains Suite 230\nKathyville, MN 09076',
    'text': 'Glass despite recent student current sea. Imagine how opportunity network.\nFive still teacher will. Certainly thus yourself still.',
    'email': 'mark64@example.net',
    'phone_number': '(366)702-5730x4550',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Benjamin',
],
    'json': {
    'name': 'Laura Matthews',
    'address': '555 David Cape Apt. 245\nDavidland, WA 08576',
},
    'key62450': 'value25184',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Casey Hernandez',
    'address': '17717 Higgins Estate\nLoriville, AR 48731',
    'text': 'Fight sing still draw through behind. See middle table forget example price most start. Group past race election meeting enter wrong. Quickly century source early manager six at.',
    'email': 'brooksrachel@example.com',
    'phone_number': '5396056843',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Bryant',
    'Laurie Hardin',
    'Jeffrey Hunt',
    'Nathan Payne',
    'Denise Webster',
    'Miss Courtney Bell DDS',
    'Eric Martinez PhD',
    'Troy Wilkinson',
],
    'json': {
    'name': 'Tracey Ortega',
    'address': 'USNV Avila\nFPO AE 86073',
},
    'key50676': 'value50844',
    'key76328': 'value42822',
    'key10783': 'value25274',
    'key73703': 'value91624',
    'key31073': 'value15900',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jason Burke',
    'address': 'USS Ortega\nFPO AA 89564',
    'text': 'South fill reality sound offer inside. Care mother list face sea work wonder. Miss store pattern standard.\nTalk American question audience fast big our. Science morning them beautiful.',
    'email': 'mahoneyalan@example.net',
    'phone_number': '414-670-5947',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Julie Shepherd',
],
    'json': {
    'name': 'Gina Miller',
    'address': '4561 Davis Springs Apt. 016\nMeganport, OK 03383',
},
    'key16686': 'value25453',
    'key38161': 'value27944',
    'key84386': 'value41582',
    'key71433': 'value33115',
    'key48538': 'value88621',
    'key10923': 'value26506',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Elizabeth Graham',
    'address': '1256 Alejandro Roads\nThompsonside, NH 70787',
    'text': 'Purpose necessary represent order understand report. Analysis party share.',
    'email': 'zchase@example.com',
    'phone_number': '(961)432-1989x35457',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Tina Alvarado',
    'Sean Howard',
    'Juan Macias',
    'William Fox',
    'Sylvia Rodriguez',
],
    'json': {
    'name': 'Todd Carroll',
    'address': '585 Alvin Parks\nEast Timothyfurt, MP 77801',
},
    'key17615': 'value15360',
    'key84590': 'value9186',
    'key64590': 'value4923',
    'key10711': 'value75951',
    'key22535': 'value43531',
    'key65903': 'value96513',
    'key72400': 'value75965',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Daisy Vasquez',
    'address': '812 Quinn Pass Suite 461\nPort Ronaldstad, WV 07300',
    'text': 'Usually decide deep believe. Scientist left responsibility American relate.\nPrepare success soldier edge any available left training. Home either land security public. House article somebody.',
    'email': 'lorraine93@example.net',
    'phone_number': '+1-755-773-6954',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Melanie Wallace',
    'Paul Tyler',
],
    'json': {
    'name': 'Meghan Fox',
    'address': '71980 Jones Isle\nSouth Brooke, TX 66557',
},
    'key63027': 'value40151',
    'key78524': 'value30566',
    'key35481': 'value52290',
    'key47299': 'value64339',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Jennifer Costa',
    'address': '3757 Jones Fords Suite 735\nNicholaschester, WV 36816',
    'text': 'Else way game.\nOwn science concern whole. Speech floor risk artist drive after. Network job side suddenly ground.',
    'email': 'todd94@example.org',
    'phone_number': '+1-946-388-2236x0111',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'John Garcia',
    'Jesse Turner',
    'Jordan Rodriguez',
    'Caitlin Smith',
    'Bridget Douglas',
    'Maurice Davis',
    'Christopher Espinoza',
    'Tracy Stewart',
],
    'json': {
    'name': 'Morgan George',
    'address': '19508 Crystal Crescent Apt. 290\nLake Alexisburgh, MH 65204',
},
    'key65711': 'value51369',
    'key57203': 'value40574',
    'key33794': 'value23717',
    'key67999': 'value24951',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Haley Johnson',
    'address': 'USS Orozco\nFPO AE 62582',
    'text': 'Month show none bag keep spring never act. Rich father billion foreign campaign town.\nWe indicate space. Street program of seat.\nStudent eye plan since. Financial receive either information.',
    'email': 'vanessa78@example.net',
    'phone_number': '(591)552-1805x75141',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Richardson',
    'Rachel Young',
    'Alan Bauer',
    'Ann Lewis',
    'Mario Butler',
    'William Johnson',
    'Sean Leach',
],
    'json': {
    'name': 'Joshua Gonzalez',
    'address': '440 Fischer Stream Suite 779\nLake Jeremyview, KY 69516',
},
    'key41506': 'value36924',
    'key12899': 'value2496',
    'key95879': 'value13494',
    'key56675': 'value71337',
    'key34173': 'value22131',
    'key30307': 'value51370',
    'key90317': 'value69458',
    'key55667': 'value25672',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Dr. Daniel Davis',
    'address': '60257 Thomas Plain Suite 283\nLake Briantown, TX 89486',
    'text': 'Personal sit week. Never another movement age nice. Research ask allow yet prove nice.\nLast sometimes personal apply protect of should. Doctor box can.',
    'email': 'tiffany54@example.net',
    'phone_number': '498-950-4103x56310',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Hannah Beck',
    'Amber Anderson',
    'Charles Galloway',
    'Lauren Brown',
    'Maurice Lewis',
],
    'json': {
    'name': 'Tyler Pollard',
    'address': '473 Scott Rapid\nAlanstad, OH 49195',
},
    'key30817': 'value60959',
    'key38436': 'value43819',
    'key50540': 'value35122',
    'key40090': 'value6908',
    'key97788': 'value35185',
    'key8955': 'value79137',
    'key51265': 'value16828',
    'key1277': 'value20605',
    'key70563': 'value49870',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Steven Powers',
    'address': '3323 Faulkner Avenue Apt. 005\nNorth Williamstad, ME 46785',
    'text': 'Decide opportunity pay bring human surface well. Career understand size day continue. Above woman rich would pass for laugh son.',
    'email': 'jsandoval@example.org',
    'phone_number': '294-349-4434',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amber Stephens',
],
    'json': {
    'name': 'Denise Martinez',
    'address': '992 Martin Cliffs\nCampbellburgh, ME 08647',
},
    'key5863': 'value36085',
    'key16630': 'value54480',
    'key53550': 'value74497',
    'key39501': 'value26041',
    'key34492': 'value88686',
    'key67175': 'value30909',
    'key91645': 'value45322',
    'key69969': 'value20274',
    'key98210': 'value73541',
    'key92467': 'value99134',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Susan Wade',
    'address': '714 Charles Mountains Apt. 912\nSouth Austin, NE 19442',
    'text': 'Day fall religious represent break pick myself. Drive wish brother would maintain way laugh.\nEspecially take theory push again minute region. Wonder and cultural issue rate computer.',
    'email': 'middletontravis@example.org',
    'phone_number': '001-695-851-3305x4810',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Garcia',
    'Deanna Glover',
    'Joseph Mcmillan',
],
    'json': {
    'name': 'Dustin Martin',
    'address': '05601 Glenda Haven Suite 376\nPatriciaview, MA 55513',
},
    'key7798': 'value72735',
    'key42486': 'value57209',
    'key3895': 'value60207',
    'key25484': 'value58662',
    'key66493': 'value25892',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Wendy Mckenzie',
    'address': '079 Diamond Pike\nLake Gerald, AZ 90381',
    'text': 'Inside itself network far eat wife investment. Inside entire newspaper shoulder could. Tough community beat.',
    'email': 'ericgillespie@example.com',
    'phone_number': '(915)877-4964',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Richard Anderson',
    'Carl Bowman',
    'Timothy Rose',
    'Todd Nelson',
],
    'json': {
    'name': 'Shannon Cook',
    'address': '8529 Daniel Streets Suite 078\nJamesfort, DC 53241',
},
    'key9659': 'value14229',
    'key39869': 'value56588',
    'key65218': 'value13647',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Jennifer Hobbs',
    'address': '83563 Mendez Loaf Apt. 959\nJonberg, AS 46979',
    'text': 'Continue management gas part allow account bring finally. Ok actually finally trip responsibility.\nThey possible relationship. Region middle southern.',
    'email': 'lewisjennifer@example.net',
    'phone_number': '536.984.2637x073',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jason Barr',
    'Cassandra Hartman',
    'Chris Winters',
    'Sonia Dyer',
    'Evelyn Benjamin',
    'Lisa Ray',
    'Evelyn Chandler',
    'Jackson Lucero',
],
    'json': {
    'name': 'Steven Hamilton',
    'address': '455 Sarah Valleys\nDanielton, OH 51755',
},
    'key64351': 'value88160',
    'key36850': 'value29653',
    'key21950': 'value67448',
    'key19328': 'value59664',
    'key86777': 'value80874',
    'key50522': 'value42730',
    'key72802': 'value22766',
    'key46383': 'value18950',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Mary Smith',
    'address': '353 Phillips Prairie Suite 088\nClarkland, DC 17488',
    'text': 'Seat particular foot hard total world many. Local now through. Team I whose town Congress economic able term.',
    'email': 'kristingardner@example.com',
    'phone_number': '(244)724-2573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'John Martinez',
    'Jessica Crawford',
    'Joseph Powers',
],
    'json': {
    'name': 'Joseph Stephens',
    'address': '629 Jennifer Common\nNorth Debbieview, VT 99927',
},
    'key25410': 'value2367',
    'key88347': 'value14691',
    'key9771': 'value24914',
    'key70212': 'value70218',
    'key33813': 'value32057',
    'key6170': 'value25581',
    'key65688': 'value83986',
    'key14046': 'value76552',
    'key22723': 'value7152',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Glenn Wilson',
    'address': '9503 Erin Fords Apt. 826\nNew Michaelchester, AS 01681',
    'text': 'Past but someone first college tough. Beat manager discussion meet. Sea clearly stand a collection.',
    'email': 'nancyparker@example.com',
    'phone_number': '855.409.3874x616',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Cindy Mooney',
    'Shannon Clements',
    'Carlos Rios',
    'Adam Ramirez',
    'Stacy Bradley',
    'Robert Simpson',
    'Mark Martin',
    'Kathryn Castillo',
],
    'json': {
    'name': 'Allison Mills',
    'address': '928 Lisa Route\nNew Danielborough, PA 74731',
},
    'key53957': 'value90296',
    'key74674': 'value15262',
    'key18328': 'value4343',
    'key26444': 'value69935',
    'key33211': 'value62312',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Zachary Owens',
    'address': '5256 Turner Springs Suite 609\nTinashire, IL 30128',
    'text': 'Individual month democratic car economy then. Top matter anything address short raise. War spring hospital artist school trip turn.',
    'email': 'davislevi@example.org',
    'phone_number': '(841)605-0731x743',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Garrett Owens',
    'Eric Davis',
    'Cameron Wilson',
    'Ronald Clark',
    'Brian Beck',
],
    'json': {
    'name': 'Andrew Moore',
    'address': '1309 Peter Shoal\nPort Wendy, AS 63376',
},
    'key1745': 'value26473',
    'key38085': 'value39534',
    'key32576': 'value9862',
    'key9148': 'value4666',
    'key35677': 'value10533',
    'key59326': 'value19557',
    'key1280': 'value48765',
    'key39030': 'value45961',
    'key41187': 'value5006',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Kathryn Garcia',
    'address': '68833 Palmer View Suite 596\nNorth William, NY 90171',
    'text': 'Can until affect even model authority. Lose eat leg.\nForget federal woman myself. Night across crime also. Move thousand real child sign example source.',
    'email': 'andrea70@example.net',
    'phone_number': '853-969-1556',
    'array_int_dynamic': [
    52323,
],
    'array_varchar_dynamic': [
    'Angelica Jones',
    'Ian Grant',
    'Mrs. Tammy Floyd',
    'Steven Moreno',
    'Arthur Howe',
    'Scott Webster',
    'Ronald Davis',
    'Melissa Horton',
],
    'json': {
    'name': 'Anne Brooks',
    'address': '20529 Justin Spur\nNew Robertmouth, MP 38887',
},
    'key24945': 'value37749',
    'key65159': 'value29297',
    'key65678': 'value72294',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Angela Thomas',
    'address': '9593 Matthew Road\nNew Gloria, FM 37332',
    'text': 'Best on then floor book east itself. From discover have hard although center car choice.',
    'email': 'jonessteven@example.net',
    'phone_number': '+1-483-462-1169x2044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christine Marquez',
    'Justin Conway',
    'Sharon Moss',
    'Jeffrey Curtis',
    'Michael Davis',
    'Kaylee Carr',
    'Brad Johnson',
],
    'json': {
    'name': 'James Rose',
    'address': 'Unit 9794 Box 5597\nDPO AP 65762',
},
    'key85076': 'value21874',
    'key43084': 'value95053',
    'key44120': 'value37270',
    'key60540': 'value72513',
    'key38800': 'value39016',
    'key16881': 'value3430',
    'key97985': 'value19568',
    'key60235': 'value24919',
    'key43653': 'value52295',
    'key73178': 'value97516',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Samantha Mckenzie',
    'address': '945 Tina Orchard\nLake Ernest, AZ 43003',
    'text': 'Personal foot movie quite rate understand. First that word guy to whatever.\nHouse mention something center.\nPm pick down gas from. Woman not require under might. At law people tree.',
    'email': 'psalas@example.net',
    'phone_number': '966.849.9798x4533',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Johnson',
    'Victoria Bell',
    'Benjamin Ramirez',
    'Brittany Murphy',
    'Mary Lin',
    'Julie Wilson',
    'Anthony Arnold',
    'Joshua King',
    'Kathy Wright',
    'Christy Mack',
],
    'json': {
    'name': 'Joyce Fritz',
    'address': '2785 Brennan Mountains Apt. 304\nGrantside, MA 93180',
},
    'key81647': 'value60950',
    'key61844': 'value51272',
    'key30556': 'value75702',
    'key94041': 'value49955',
    'key3896': 'value62472',
    'key88585': 'value7261',
    'key8130': 'value43030',
    'key64626': 'value11234',
    'key22014': 'value17596',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Beth Osborne',
    'address': '4264 Crystal Ranch Apt. 877\nBrennanton, OK 15516',
    'text': 'Next really team seat road similar ability. Bag establish interest. Sure those member hour offer service specific.\nNational down cell notice. Reality push war.\nGoal might difficult memory Mr other.',
    'email': 'elizabethhuang@example.net',
    'phone_number': '788-767-0736',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Luis Little',
    'David Kaufman',
    'Valerie Odonnell',
    'Seth Crosby',
    'Dr. Rita Boyle',
    'Jill Davis',
    'Karina Huynh',
],
    'json': {
    'name': 'Brenda Turner',
    'address': '5353 Winters Rapids\nDouglasborough, AR 43549',
},
    'key90898': 'value34618',
    'key98483': 'value836',
    'key49205': 'value81772',
    'key90175': 'value94894',
    'key35358': 'value35907',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Melissa Preston',
    'address': '07150 Jason Street Suite 585\nGibsonfort, WV 48804',
    'text': 'Decade cup hard reduce why inside back official. Reason seek economic party.\nRun professional exist medical from late. Building data particular dream tough.',
    'email': 'davismartin@example.org',
    'phone_number': '541.523.4836x792',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Brown',
],
    'json': {
    'name': 'Andrew Vega',
    'address': '861 Alan Villages Apt. 977\nRaymondfort, NH 15152',
},
    'key61490': 'value23655',
    'key73468': 'value76831',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Lawrence Lee',
    'address': 'PSC 3992, Box 0113\nAPO AP 87827',
    'text': 'Force throughout stand clearly door purpose operation. Adult camera traditional its example.',
    'email': 'rebeccaharris@example.net',
    'phone_number': '+1-819-667-3420x797',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Clark',
    'John Ramos',
    'Brian Brown',
    'Alexandra Fields',
    'Elizabeth Mccarthy',
    'Ashley Sandoval',
    'Victor Phillips',
    'Cassandra Mccann',
    'Julie Diaz',
],
    'json': {
    'name': 'Scott Todd',
    'address': '34748 Janice Forks\nEast Stephanieborough, ND 47794',
},
    'key43046': 'value66212',
    'key26971': 'value39127',
    'key17365': 'value76249',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Mallory Glenn',
    'address': '438 Carlson Trace Apt. 394\nNew Cheryl, IN 30967',
    'text': 'Performance above whole seat. Professor recent wish place impact theory explain. Building shake sea production.\nSmile fight or business. Power these environmental true trade.',
    'email': 'michaelwong@example.com',
    'phone_number': '952-855-0269x45146',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amy Lopez',
    'Stephanie Conley DVM',
    'Timothy Lane DDS',
    'Stephen Scott',
],
    'json': {
    'name': 'Richard Adams',
    'address': '50621 Robert Park\nKleinmouth, MN 52028',
},
    'key78848': 'value4609',
    'key40328': 'value29465',
    'key75801': 'value71888',
    'key22021': 'value97863',
    'key44103': 'value32501',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Stephanie Garcia',
    'address': 'PSC 8379, Box 4140\nAPO AA 77565',
    'text': 'Race answer cell identify force. Develop common evening heart.\nWorker explain large condition system order major before. Glass answer perform stop item court tree.',
    'email': 'joelbriggs@example.com',
    'phone_number': '+1-663-605-3147x10183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Mitchell',
    'Erik Rogers',
],
    'json': {
    'name': 'Monica Brown',
    'address': '925 Sarah Island\nDavidmouth, VT 97942',
},
    'key94821': 'value28218',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Melissa Sutton',
    'address': '6428 Sherry Falls\nMarytown, WV 57486',
    'text': 'Modern side heavy that. Social different factor second first data. The look writer late.',
    'email': 'skeith@example.com',
    'phone_number': '(306)426-3154',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Katrina Smith',
    'Shannon Aguirre',
    'Cynthia Anderson',
    'Amanda Rodriguez',
    'Ryan Garcia',
    'Michael Glass',
],
    'json': {
    'name': 'Darlene Henry',
    'address': '124 Mark Well\nNew Nancyborough, CA 90337',
},
    'key57806': 'value7755',
    'key92956': 'value30754',
    'key90273': 'value54110',
    'key42481': 'value15793',
    'key43472': 'value41761',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Richard Martinez',
    'address': '9968 Michael Trail\nParrishville, MD 74400',
    'text': 'Center foot fine statement pay bar front fight. Over day play tend road.\nHot word song reason already agent. Particularly maybe direction little thank this statement.',
    'email': 'samanthaweber@example.net',
    'phone_number': '289-985-5832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Diane Nelson',
    'Linda Barrett',
    'Morgan Spence',
    'William Collier',
],
    'json': {
    'name': 'Caroline King',
    'address': '6195 Lee Mission Suite 990\nWilliamsfurt, MA 75348',
},
    'key41230': 'value7261',
    'key63470': 'value74222',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Steven Bates',
    'address': '78835 Patricia Keys Apt. 085\nJohnsonfort, TX 08356',
    'text': 'Assume trouble hold attention happen. Identify everybody however approach. Over sit laugh identify near.',
    'email': 'blanchardwilliam@example.com',
    'phone_number': '001-682-459-1857x627',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Heather Figueroa',
    'Paul Mccormick',
    'Courtney Landry',
    'Vanessa Huffman',
],
    'json': {
    'name': 'Shelly Sullivan',
    'address': '00728 Amanda Station Apt. 519\nNew Gabriel, MN 71890',
},
    'key96192': 'value41054',
    'key82174': 'value84440',
    'key48439': 'value24689',
    'key35548': 'value36038',
    'key28687': 'value46428',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Nichole Rivas',
    'address': '299 Schmidt Groves\nNorth Jasminefurt, CT 64200',
    'text': 'Well energy opportunity test game ask. Choice teacher perhaps such be standard.\nCharge up society professional.',
    'email': 'robertford@example.com',
    'phone_number': '(355)970-8741x5151',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Jackson',
    'Debra Adkins',
    'Joshua Lutz',
    'Charles Arnold',
    'Melissa Pruitt',
],
    'json': {
    'name': 'Matthew Adams',
    'address': '2407 Wilson Brook Apt. 934\nJohnchester, MI 71606',
},
    'key69086': 'value64377',
    'key70005': 'value4393',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Nicole Garcia',
    'address': '67946 Kelly Corners Suite 695\nWest Taylor, TX 38147',
    'text': 'Serve south family money. Son him could discuss discussion respond heart. Congress owner whole yeah not.\nLot carry store kind lay. Amount something factor toward American especially.',
    'email': 'yruiz@example.com',
    'phone_number': '001-296-800-4256',
    'array_int_dynamic': [
    99122,
],
    'array_varchar_dynamic': [
    'Kathleen Williams',
    'Craig Weber',
    'William Castillo',
    'William Payne',
    'Christopher Frye',
    'Christine Lane',
    'Patricia Ortiz',
    'Heather Davis',
],
    'json': {
    'name': 'Gabriel Cook',
    'address': 'PSC 9324, Box 5998\nAPO AP 91362',
},
    'key10847': 'value90431',
    'key84616': 'value41497',
    'key37101': 'value18300',
    'key3': 'value3035',
    'key34154': 'value595',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Noah Meyer',
    'address': '7980 Victoria Springs Suite 466\nWest Virginiaberg, LA 06257',
    'text': 'Character on from history surface ready. Turn check data change again young.',
    'email': 'adkinsmalik@example.net',
    'phone_number': '+1-498-699-7034x619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Davis',
    'Lisa Miller',
    'Daniel Ross',
    'Scott Guerrero',
    'Billy Hill',
    'Christina Bailey',
],
    'json': {
    'name': 'Anthony Morgan',
    'address': '4772 Smith Junction\nStephanieton, WI 63597',
},
    'key40189': 'value76396',
    'key46549': 'value87847',
    'key27896': 'value49502',
    'key11249': 'value26799',
    'key91849': 'value31437',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Heather Moody',
    'address': '8025 Jason Forge\nAnafort, MT 29053',
    'text': 'Republican store painting like need. Meeting reveal new activity yard. Brother specific relationship high feeling.\nCenter so push movement. Serious family trade just. Teacher identify still ago seat.',
    'email': 'gambledonna@example.org',
    'phone_number': '001-522-972-3807x544',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Heather Boyle',
    'Mary Burns',
    'Danny Watts',
    'Randall Terry',
    'Timothy Hodge PhD',
],
    'json': {
    'name': 'Summer Rivera',
    'address': '0259 Oneal Courts\nWest Allisonfurt, ME 01678',
},
    'key51401': 'value51288',
    'key72248': 'value18004',
    'key997': 'value82492',
    'key93599': 'value65655',
    'key67710': 'value11401',
    'key20766': 'value22582',
    'key70426': 'value73234',
    'key61631': 'value38428',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Laura Ritter',
    'address': '1421 Catherine Camp Suite 202\nEast Mariatown, NH 96281',
    'text': 'Stage series generation different skin beautiful expert person. Policy rock actually change power they employee up. Establish Republican concern election.\nWriter low truth.',
    'email': 'annettegibson@example.net',
    'phone_number': '600-511-4761x8521',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Warren',
    'Sarah Haley',
    'Ashley Bates',
],
    'json': {
    'name': 'Mrs. Amanda Fox',
    'address': '256 Phillips Route\nJohnmouth, NE 87900',
},
    'key53364': 'value61725',
    'key30422': 'value93007',
    'key86936': 'value85127',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Angel Ward',
    'address': '12405 Hernandez Ferry Apt. 476\nLake Cynthia, NC 09901',
    'text': 'Language throw theory east. Image whom industry kind environmental.\nPossible without bed easy. No add include artist others ready five.\nTeach season decade drug line.',
    'email': 'steven79@example.net',
    'phone_number': '(979)378-3051x9104',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Heather Hawkins',
    'Jeffrey Suarez',
    'Pamela Michael',
],
    'json': {
    'name': 'Gregory Frye',
    'address': '640 Barber Station Apt. 546\nBlakefort, MI 01621',
},
    'key10332': 'value82720',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Todd Baird',
    'address': '38868 Hall Shores\nDavidtown, MH 20289',
    'text': 'Sing six night mind. Alone series carry attorney. Walk good state fight use.\nIndicate may investment cut low the guy.\nCould pull mention child. Power just source address practice.',
    'email': 'aguirrerobert@example.net',
    'phone_number': '+1-423-453-4242x371',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Rodney Fowler',
    'Austin Hall',
    'Steven Morgan',
],
    'json': {
    'name': 'Susan Gray',
    'address': '31051 Campbell Vista\nKaneport, OK 55467',
},
    'key43878': 'value82763',
    'key21594': 'value78259',
    'key67652': 'value39884',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Kevin Jimenez',
    'address': '44085 Nancy Highway\nNguyenside, WY 62485',
    'text': 'Expect use hold picture student. Want eight necessary rock religious rock on.',
    'email': 'chavezangela@example.com',
    'phone_number': '378-933-8826x07410',
    'array_int_dynamic': [
    81251,
],
    'array_varchar_dynamic': [
    'Brittany Anderson',
    'Joshua Fritz',
    'Jennifer Lopez',
    'Sandra Hunter',
    'Aaron Smith DDS',
],
    'json': {
    'name': 'Jeffrey Pratt',
    'address': '15521 Little Locks Apt. 385\nEast Rebecca, OR 79666',
},
    'key18370': 'value42625',
    'key42425': 'value74697',
    'key64291': 'value85787',
    'key73946': 'value59173',
    'key87558': 'value25636',
    'key51179': 'value99954',
    'key6139': 'value77879',
    'key38864': 'value72600',
    'key9994': 'value46903',
    'key38357': 'value94350',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Mark Phillips',
    'address': '5872 Erik Heights\nJoseside, OR 00871',
    'text': 'Arrive movement do technology face. Article start ok save pretty control reflect.\nSafe soon least memory choice free. Item with avoid grow visit.\nForget heart manager age. Kid value bit small seat.',
    'email': 'jamie35@example.net',
    'phone_number': '(511)302-9080x34225',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Vincent Boyd',
],
    'json': {
    'name': 'Thomas Hernandez',
    'address': '40210 Joseph Way\nSherifort, NY 32841',
},
    'key20283': 'value86123',
    'key58120': 'value64838',
    'key89291': 'value70593',
    'key47683': 'value66374',
    'key85940': 'value66377',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Melissa Guzman',
    'address': '10363 Erin Gateway\nNew Katrina, IL 86088',
    'text': 'Get spring detail maintain. Film phone expert system ready into hear thing. Arrive art professor network inside. Step look case remember my avoid.\nDegree tell mind. Need myself southern add drive.',
    'email': 'wilsoncourtney@example.org',
    'phone_number': '001-695-696-6455x4386',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Carrillo',
    'James Sherman',
    'Isabel Miranda',
    'Craig Nolan',
    'Andrew Logan',
    'Jason Shepherd',
    'Nicole Wilson',
    'Christina Garcia',
    'David Ford',
],
    'json': {
    'name': 'Deanna Le',
    'address': '54520 Heather Fields\nWest Leonshire, AL 40749',
},
    'key55987': 'value84403',
    'key86119': 'value35472',
    'key31325': 'value49853',
    'key954': 'value27262',
    'key32711': 'value94342',
    'key58522': 'value63878',
    'key56094': 'value68874',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Cathy Wall',
    'address': '9946 Martin Parkway Apt. 076\nNew John, FM 70946',
    'text': 'What lawyer common song north analysis. Ever entire red education six.\nThought attack simple recent. Everyone something throughout magazine world. Since ball require skill top.',
    'email': 'jennifer32@example.org',
    'phone_number': '(381)782-2750',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James Oliver',
    'Chase Moore',
    'Daryl Buckley',
    'Dale Bell',
    'James Johnson',
],
    'json': {
    'name': 'Joseph Morris',
    'address': '6877 Shelby Spur Suite 271\nLake Brandytown, WV 51599',
},
    'key28166': 'value72775',
    'key86590': 'value39969',
    'key72398': 'value75525',
    'key24045': 'value37968',
    'key57545': 'value84105',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Joseph Sherman',
    'address': '22230 Linda Keys Suite 812\nJohnsonstad, GA 68999',
    'text': 'Project table majority development new six degree. Western early fly this seek.\nPoor evening Mrs bring. Onto different individual teach.\nToo including music section edge daughter site short.',
    'email': 'erikapeck@example.com',
    'phone_number': '972.321.5170x72545',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Justin Reynolds',
    'Rebecca Lambert',
    'Angela Roberts',
    'Jeffery Simpson',
    'Ann Bautista',
    'Timothy Smith',
    'Caroline Johnson',
],
    'json': {
    'name': 'Kara Howard',
    'address': '3406 Tiffany Squares Apt. 073\nHammondmouth, MD 97942',
},
    'key34732': 'value28161',
    'key8483': 'value34458',
    'key68070': 'value18595',
    'key11218': 'value61800',
    'key32056': 'value41609',
    'key94717': 'value95822',
    'key60448': 'value88723',
    'key51728': 'value91348',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'John Horton',
    'address': '76772 Bailey Walk Suite 632\nMorrisbury, AZ 74798',
    'text': 'Food industry finish day star option. Type step serve challenge appear management media. Recent receive choice better hope. Purpose apply kid tend.',
    'email': 'kennethmendoza@example.net',
    'phone_number': '(642)698-0008x1122',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Morris',
    'Miranda Brown',
    'Jill Lee',
    'Kimberly Waters',
    'Melanie Jenkins',
    'Jill Ford',
    'Kyle Robertson',
    'Austin White',
    'Bruce Garcia',
    'Larry Walter',
],
    'json': {
    'name': 'Linda Castillo',
    'address': 'PSC 3062, Box 7043\nAPO AP 95255',
},
    'key24842': 'value44781',
    'key56028': 'value49666',
    'key91932': 'value12693',
    'key41141': 'value55014',
    'key89742': 'value841',
    'key81202': 'value13666',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Marcus Bailey',
    'address': 'Unit 0168 Box 7884\nDPO AA 08807',
    'text': 'Write knowledge late decision. Fall sell technology. Land condition husband discuss east far.',
    'email': 'adamskristine@example.org',
    'phone_number': '(581)888-8282',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alex Washington',
    'Michael Sanchez',
    'Shawn Mckinney',
],
    'json': {
    'name': 'Elizabeth Pierce',
    'address': '022 Jerry Loaf Suite 295\nStevenmouth, AR 41784',
},
    'key65193': 'value18803',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Helen Delgado',
    'address': '047 John Circle\nLake Alexisville, FM 65466',
    'text': 'Market nor father focus important this.\nCommunity when door. Step per their now you three star when.\nAssume impact on could offer be. Bank director with important mention.',
    'email': 'jonesmichelle@example.org',
    'phone_number': '473.243.3034x1305',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Ballard',
    'Leslie Shaw',
    'Cathy Webb',
    'Steven Arellano',
],
    'json': {
    'name': 'Aaron Ryan DVM',
    'address': '575 Shah Plain\nSamanthabury, GU 92579',
},
    'key22889': 'value7320',
    'key46958': 'value77938',
    'key36656': 'value37032',
    'key10466': 'value98945',
    'key81157': 'value77935',
    'key35292': 'value24916',
    'key29344': 'value39989',
    'key71528': 'value45054',
    'key20701': 'value38327',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Cindy Hernandez',
    'address': '05071 Franco Shoal\nWest Tasha, ND 41708',
    'text': 'Everyone someone paper policy become describe. Well some firm argue economy through society. Nature according management education thing.',
    'email': 'pgentry@example.org',
    'phone_number': '+1-507-220-8248',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Grace Foley',
    'Mia Bates',
    'Jeffrey Lambert',
    'Nicole Miller',
    'Tanner Adams',
    'Stephen Lyons',
    'Caitlin Clements',
],
    'json': {
    'name': 'Joel Best',
    'address': '5314 Julie Summit\nNorth Sydney, CO 16052',
},
    'key71276': 'value76149',
    'key33428': 'value98828',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Rachel Williams',
    'address': '2643 Burns River Apt. 837\nMarialand, VI 49320',
    'text': 'Base point garden high certainly professor language. Vote concern music likely.',
    'email': 'douglasramirez@example.com',
    'phone_number': '(215)818-0288x6730',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Rios DDS',
    'Sean Mayo',
    'Russell Wright',
    'Kimberly Bell',
    'Brenda Brown',
    'Marc Murray',
    'Timothy Peterson PhD',
],
    'json': {
    'name': 'Ryan Preston',
    'address': '339 Vaughn Village\nLake Krista, WV 04838',
},
    'key35546': 'value71718',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Nicole White',
    'address': '583 Maria Lock\nPort Colleen, AS 41420',
    'text': 'Guy sister treatment mission expert message get sure. Sound site technology bad score exactly.\nMorning high we among. Security be others decide whom him realize. Name production maintain.',
    'email': 'lconner@example.com',
    'phone_number': '+1-519-913-5031x56957',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Stephenson',
    'Cynthia Johnson',
    'Larry Porter',
],
    'json': {
    'name': 'Charles Daniels',
    'address': '758 Daniel Vista Apt. 080\nBryanchester, IN 42652',
},
    'key35834': 'value73070',
    'key60077': 'value52556',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Lynn Terry',
    'address': '68761 Peterson Square Apt. 126\nLake Kerrytown, LA 33010',
    'text': 'Environment name every play make yourself him. Start recently fact hotel amount idea position.\nDinner least world. Behavior attention provide visit learn. Possible hit between name.',
    'email': 'eowens@example.org',
    'phone_number': '+1-453-971-5547x17978',
    'array_int_dynamic': [
    75705,
],
    'array_varchar_dynamic': [
    'Miguel Chang',
    'Autumn Hughes',
    'Stephanie Anderson',
    'James White',
    'Juan Villegas',
    'Krystal White',
],
    'json': {
    'name': 'Sarah Casey',
    'address': 'PSC 2712, Box 9521\nAPO AA 41906',
},
    'key3044': 'value99983',
    'key82358': 'value73386',
    'key45604': 'value43762',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Justin Bentley',
    'address': '2994 Brooks Radial Suite 519\nRebeccaport, AK 12975',
    'text': 'Drive social should on question. Hit become political. Forget market scientist remain.\nNecessary require this idea right must relate understand.',
    'email': 'wsilva@example.org',
    'phone_number': '546-960-9570',
    'array_int_dynamic': [
    46157,
],
    'array_varchar_dynamic': [
    'Erica Wells',
    'William Johnson',
    'Danielle Rodriguez',
    'Veronica Horn',
    'Jerry Jackson',
],
    'json': {
    'name': 'Nicole Harrison',
    'address': 'Unit 7349 Box 9279\nDPO AP 82384',
},
    'key71140': 'value92977',
    'key32332': 'value74540',
    'key70184': 'value58614',
    'key38463': 'value52864',
    'key91144': 'value75640',
    'key51606': 'value82792',
    'key96696': 'value32285',
    'key97086': 'value82719',
    'key67814': 'value82483',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Dustin Rivera',
    'address': '721 Anderson Ford Suite 946\nPort Jamesborough, CO 26974',
    'text': 'Much white house whole. Protect commercial small message news statement participant front.\nCheck study plant management development hit. Imagine star full worry.',
    'email': 'vanessapena@example.com',
    'phone_number': '597.709.1299x26912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ernest Wheeler',
    'Susan Baker',
    'Aaron Shaffer',
    'Matthew Smith',
    'Dr. Shawn Acosta',
    'Ariana Lopez',
],
    'json': {
    'name': 'Kim Douglas',
    'address': '10841 Briggs Trail\nBenjaminstad, NH 61586',
},
    'key93957': 'value19995',
    'key34860': 'value25933',
    'key54465': 'value29862',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'David Meyer',
    'address': '5996 Kelly Expressway\nLake Dustin, MP 15687',
    'text': 'Turn sit sort environmental full gas. Lot especially sign language newspaper event total. During water tend energy stop note wrong think.',
    'email': 'ana08@example.net',
    'phone_number': '710-206-4263x8128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Diane Beasley',
    'Jacqueline Anderson',
    'Chris Kent',
    'Krista Oneill',
],
    'json': {
    'name': 'Elizabeth Tate',
    'address': '002 Danielle Locks Apt. 984\nSouth Brandon, WV 27254',
},
    'key90513': 'value81690',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'David Patel',
    'address': '1077 Jared Fields Suite 278\nNew Ericburgh, OH 08787',
    'text': 'Let friend that stand ground enough light. Citizen clearly account nice.\nFast rich perform possible think agree with. Street present ten prepare serve cover.',
    'email': 'james61@example.com',
    'phone_number': '400.759.7928x825',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jeremy Porter',
    'Valerie Poole',
],
    'json': {
    'name': 'Leslie Zamora',
    'address': '6404 Kathryn Streets Apt. 954\nSamanthachester, PW 60122',
},
    'key27143': 'value95208',
    'key57844': 'value85796',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Bianca Harvey',
    'address': '2947 Sanders Run Apt. 596\nRandytown, GA 84362',
    'text': 'Myself person civil again blood success wish several. Able social response up strategy. According music around there support recently.',
    'email': 'william36@example.net',
    'phone_number': '249-712-6228x59677',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gilbert Williams',
    'Ann Miller',
    'Christopher Cannon',
    'Lisa Mercado',
    'Angela Anderson',
    'Amy Jones',
    'Lisa Ramos',
    'Patrick Barr',
],
    'json': {
    'name': 'Shane Johnson',
    'address': '80425 Kristen Avenue\nRichardside, IN 81251',
},
    'key81748': 'value24627',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'David Warner',
    'address': '4320 Ryan Prairie\nCurtismouth, GU 99224',
    'text': 'And action animal recently. Successful sign understand. Exactly artist college cause age image lead.',
    'email': 'kathryn72@example.com',
    'phone_number': '(766)727-8719x5379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Keith Arnold',
    'Patrick Williams',
    'Lee Clay',
    'Amber Diaz',
],
    'json': {
    'name': 'Sherri Moore',
    'address': '7836 Melanie Fork Suite 193\nBrookemouth, HI 87144',
},
    'key70441': 'value68356',
    'key43397': 'value5235',
    'key67358': 'value27004',
    'key51766': 'value96768',
    'key53910': 'value34967',
    'key70797': 'value32962',
    'key26626': 'value95165',
    'key37751': 'value45402',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Logan Wood',
    'address': '994 Thompson Locks Suite 617\nMooreview, SC 67159',
    'text': 'Congress a maybe data. These idea visit television.\nKid PM few leave to door.\nMy growth itself top appear improve. Beautiful line effort song.',
    'email': 'adamscarlos@example.org',
    'phone_number': '+1-724-598-2194x35725',
    'array_int_dynamic': [
    75085,
],
    'array_varchar_dynamic': [
    'Austin Mcdowell',
    'Lauren Horton',
    'Ryan French',
    'Scott Patrick',
    'Elizabeth Hill',
    'Matthew Davis',
    'James Ramos',
],
    'json': {
    'name': 'Cathy Brown',
    'address': '13756 Hudson Shoal\nPort Amber, CT 70097',
},
    'key10279': 'value13113',
    'key82894': 'value4179',
    'key65146': 'value82855',
    'key54047': 'value12180',
    'key82782': 'value11613',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Jordan Jackson',
    'address': '58189 Dave Coves Apt. 915\nMichaelside, AZ 15765',
    'text': 'Parent table only air stage second fact. Choice record term though air community change. Decade hand either.',
    'email': 'taylorbrian@example.com',
    'phone_number': '(372)910-2336',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Duane Dodson',
    'Ellen Wright',
    'Benjamin Moore',
    'Donald Walters',
    'Mr. David Klein DVM',
    'David Perry',
    'Deborah Khan',
    'Stephen Coleman',
    'Eric Wallace',
],
    'json': {
    'name': 'John Alexander',
    'address': '6717 Lucas Islands Apt. 349\nRossport, PR 37928',
},
    'key26022': 'value57925',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Ashley Lee',
    'address': '92340 Fuentes Street\nDrakefurt, NC 25538',
    'text': 'Agent above arm individual tell. Box do more research factor.\nSome alone address suggest look. Language imagine describe operation law whether.',
    'email': 'jgarner@example.net',
    'phone_number': '(525)239-4054x99990',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Smith',
    'Scott Simmons',
    'Dana Ramos',
    'Scott Cervantes',
    'Todd Smith',
    'Paul Jackson',
    'Shawn Logan',
    'Jessica Mcdonald',
    'Gary Davidson',
],
    'json': {
    'name': 'Cheryl Kirby',
    'address': '0879 Karen Loaf\nSouth Vincentmouth, SD 08825',
},
    'key89725': 'value64015',
    'key65373': 'value35690',
    'key77475': 'value90973',
    'key82498': 'value92709',
    'key50119': 'value50795',
    'key37722': 'value66381',
    'key85301': 'value36552',
    'key27419': 'value29496',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Dr. Jennifer Scott MD',
    'address': '58994 Larry Springs Apt. 590\nNicolebury, GU 56426',
    'text': 'Still western today her treat. Institution century administration car cup worry send maybe.\nArm level allow truth. Last television experience stuff house term good.',
    'email': 'robertbell@example.net',
    'phone_number': '612.876.3349x217',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lorraine Jones',
    'Ana Harding',
    'John Wang',
    'Rebecca Ayala',
    'Juan Wilson',
],
    'json': {
    'name': 'Jonathon Jackson',
    'address': '56754 David Park Apt. 240\nJosephberg, LA 82936',
},
    'key11047': 'value66407',
    'key62844': 'value85956',
    'key795': 'value34158',
    'key74656': 'value38075',
    'key49493': 'value15366',
    'key20567': 'value36045',
    'key39334': 'value53260',
    'key28633': 'value90169',
    'key21665': 'value55743',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Robin Combs',
    'address': '78767 Butler Freeway\nNorth Stevenview, MI 24630',
    'text': 'Amount fly natural indicate. Consumer under term enter. Shake more difficult writer similar forward.\nCampaign remain increase add between performance.',
    'email': 'lindaharris@example.com',
    'phone_number': '629.903.3710x8449',
    'array_int_dynamic': [
    26594,
],
    'array_varchar_dynamic': [
    'Jeff Walker',
    'Alexis Schultz',
    'Glenn Koch',
    'Allen Parker',
    'Olivia Copeland',
    'Manuel David',
    'Matthew Tanner',
    'Roberto Perez',
    'John Smith',
    'William Austin',
],
    'json': {
    'name': 'Dr. Lauren Sosa',
    'address': '42308 Flores Drive\nPort Cynthia, HI 18303',
},
    'key2205': 'value30336',
    'key19972': 'value90407',
    'key89371': 'value46353',
    'key79648': 'value90977',
    'key90116': 'value5921',
    'key77140': 'value86445',
    'key9534': 'value7116',
    'key71176': 'value85178',
    'key98919': 'value76241',
    'key98451': 'value28645',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Tyler Duke',
    'address': 'PSC 5719, Box 9952\nAPO AE 84882',
    'text': 'Win moment everyone stand west argue. Her foot quite.\nHerself candidate size recently hand. Late also week speak kitchen feel opportunity.',
    'email': 'francis42@example.com',
    'phone_number': '997-633-9137',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Karen Crawford',
],
    'json': {
    'name': 'Stacey Kirby',
    'address': '8820 Day Ports\nKyletown, NE 73917',
},
    'key26318': 'value2742',
    'key20344': 'value25682',
    'key52446': 'value17504',
    'key449': 'value65803',
    'key59823': 'value76521',
    'key88762': 'value67663',
    'key76582': 'value69684',
    'key20073': 'value9786',
    'key40718': 'value94631',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Logan Smith',
    'address': 'USNS Harris\nFPO AE 56106',
    'text': 'Mission look dream wall.\nNice situation next forward. Always will skill. Involve soldier front effect threat rich size tend. Walk animal strong tough.',
    'email': 'joseph59@example.org',
    'phone_number': '7533235279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Olsen',
    'Charles Gomez',
    'Megan Wilson',
    'Eric Jones',
    'Katherine Ward',
    'Matthew Edwards',
    'Christopher Smith',
    'Aaron York',
],
    'json': {
    'name': 'Michael Armstrong',
    'address': '32738 Christian Coves\nJacquelinefort, IL 06589',
},
    'key12282': 'value25595',
    'key42333': 'value91171',
    'key53430': 'value88978',
    'key14855': 'value72212',
    'key12732': 'value22844',
    'key92849': 'value85876',
    'key5333': 'value50844',
    'key6998': 'value7784',
    'key81510': 'value77180',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Brian James',
    'address': '98626 Cindy Inlet Suite 640\nLake Jonathan, SD 65161',
    'text': 'Nature tough believe increase notice field. Soon pass person help back outside nature. Card particularly economic really across particular one.',
    'email': 'annakennedy@example.net',
    'phone_number': '+1-336-687-9275x20968',
    'array_int_dynamic': [
    24992,
],
    'array_varchar_dynamic': [
    'Gene Maldonado',
    'David Garrison',
],
    'json': {
    'name': 'Kimberly Howard',
    'address': '9820 Hudson Dam\nBarbaraborough, MP 48096',
},
    'key82167': 'value36812',
    'key58478': 'value85739',
    'key8464': 'value40057',
    'key5320': 'value57394',
    'key47272': 'value33834',
    'key96916': 'value67808',
    'key96276': 'value98377',
    'key35433': 'value42652',
    'key17110': 'value43397',
    'key51727': 'value43695',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Mark Holloway',
    'address': '214 Jeffrey Turnpike Apt. 956\nAnthonybury, IA 92475',
    'text': 'Treat although physical live walk.\nReceive war treat approach affect open without themselves. Book natural before. Practice court task seat region.',
    'email': 'jason61@example.com',
    'phone_number': '(399)220-1337',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Karen Morton',
    'Alison Turner',
    'David Vincent',
    'Wanda Gibson',
    'Andrew Ruiz',
],
    'json': {
    'name': 'Deanna Miller',
    'address': '3840 Cantrell Isle\nKatieburgh, FM 47639',
},
    'key64774': 'value26527',
    'key98049': 'value62544',
    'key76717': 'value45440',
    'key70048': 'value306',
    'key25289': 'value29549',
    'key45907': 'value72073',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Robert Palmer',
    'address': '3799 Gordon Keys Suite 621\nDavidland, NY 22894',
    'text': 'Reason use case easy attention.\nReflect year make treat. Country behind man strategy turn.\nFeeling bank it within.',
    'email': 'scotttommy@example.org',
    'phone_number': '001-603-728-4429x13387',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Gary Miller',
],
    'json': {
    'name': 'Amber Reed',
    'address': '91977 Sandra Highway Apt. 439\nLake Catherine, MN 54204',
},
    'key91594': 'value37319',
    'key80443': 'value6725',
    'key4631': 'value5076',
    'key58202': 'value36432',
    'key85657': 'value81336',
    'key81530': 'value39104',
    'key96354': 'value7472',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Mitchell Martinez',
    'address': '173 Jamie Hills Suite 004\nRyantown, DE 99385',
    'text': 'Letter main already. Behind debate quite identify get very church. Prevent loss able message head defense.\nSince dog end less.',
    'email': 'wmason@example.org',
    'phone_number': '6122140182',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Jackson',
    'Seth Hill',
    'Joseph Mcconnell',
    'Terry Garner',
    'Theresa Simmons',
    'Joseph Anderson',
    'Laura Melton',
    'Norman Ramirez',
],
    'json': {
    'name': 'Chelsea Carter',
    'address': '092 Meghan Hill Suite 507\nLake John, NM 74973',
},
    'key97658': 'value58636',
    'key74657': 'value71570',
    'key30288': 'value44905',
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
    'RequestId': 'b360f375-62ef-11f0-a95d-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_28_466539PEpORUdD',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-128-100-2]_1752744210.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl12810021752744210Json()
    test.run_tests()
