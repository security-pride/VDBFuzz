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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752744887_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752744887.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUidIn12341752744887Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752744887.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752744887.json"
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
    'RequestId': '3ff28764-62f1-11f0-9d3d-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_33_798339UWqQwkjW',
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
    'RequestId': '43126368-62f1-11f0-90ad-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_33_798339UWqQwkjW',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'James Chang',
    'address': '861 Nolan Street\nKelseymouth, VT 27159',
    'text': 'New allow time arm. Room to garden table must second.\nWish whole every hold drive. Consider forward hospital sure personal. Improve body rock issue main.\nBox seat interview main ago.',
    'email': 'fpetersen@example.com',
    'phone_number': '717.302.9232x14525',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Holly Brown',
    'Kristine Miller DDS',
    'Jose Johnson',
    'Meredith King DDS',
    'Danielle Wells',
    'Joseph Larson',
    'Amber Obrien',
],
    'json': {
    'name': 'Dennis Garrett',
    'address': '9290 Ellis Green\nKathleenbury, WI 98722',
},
    'key69881': 'value70230',
    'key70379': 'value9007',
    'key41339': 'value50724',
    'key76649': 'value39386',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Mitchell Hernandez',
    'address': '49236 Robert Glen\nNorth Jamesfort, AL 40509',
    'text': 'By side public middle push development enter number. General year would evidence at number meeting important.',
    'email': 'fisherjessica@example.net',
    'phone_number': '(437)884-8059',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Anderson',
    'Dustin Parker',
    'Theresa Garcia',
    'Robert Andrade',
],
    'json': {
    'name': 'Stephanie Baxter',
    'address': '92149 Graham Motorway Suite 702\nDaniellestad, HI 62702',
},
    'key85178': 'value59522',
    'key3945': 'value26547',
    'key76115': 'value35131',
    'key66315': 'value32460',
    'key15045': 'value55450',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Jordan Davis',
    'address': '1421 Meyer Circles Apt. 705\nWest Peter, WI 29448',
    'text': 'Medical them soldier benefit. May matter involve various hotel.\nBreak identify various hospital. Same time rich still. Memory already long couple with when. Each home much administration per PM.',
    'email': 'paulaweeks@example.com',
    'phone_number': '903-515-3848x6287',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joe Craig',
    'Brandon Ibarra',
    'Erin Anderson',
    'Dylan Schmidt',
    'Jeff Vance',
],
    'json': {
    'name': 'Edwin Cameron',
    'address': '288 Hoffman Forges Suite 417\nStevenfurt, GA 09684',
},
    'key34651': 'value3949',
    'key70104': 'value16858',
    'key93687': 'value89387',
    'key87644': 'value48085',
    'key39828': 'value10399',
    'key31836': 'value19065',
    'key9546': 'value41919',
    'key5894': 'value74440',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Richard Adams',
    'address': '5714 Rice Light\nNew Brett, IA 17912',
    'text': 'Customer system although training form. Full drug listen. Something decide beat develop.\nHour involve improve realize a. Inside thus movement theory tree before. Senior out it save plan.',
    'email': 'stephenhudson@example.net',
    'phone_number': '(808)520-4557x99162',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Alexis Carter',
    'Karen Robinson',
    'Brianna Taylor',
    'Amanda Rhodes',
    'George Kane',
    'Lori Smith',
    'Mrs. Stacy Wall MD',
    'Gabriel Melendez',
],
    'json': {
    'name': 'Troy Erickson',
    'address': '7244 Ramirez Trail\nColemanbury, LA 53109',
},
    'key28362': 'value70061',
    'key20257': 'value94949',
    'key23446': 'value87700',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Gabriella Gonzalez',
    'address': '30952 Brandon Summit Suite 089\nKentfurt, VT 00695',
    'text': 'While physical ground have election sea. Reason else color where shoulder be mouth.',
    'email': 'nbutler@example.com',
    'phone_number': '001-561-877-1420x197',
    'array_int_dynamic': [
    37091,
],
    'array_varchar_dynamic': [
    'Alex Allen',
    'James Rodriguez',
    'Deborah Holt',
    'Tanya Palmer',
],
    'json': {
    'name': 'Michelle Cummings',
    'address': 'Unit 1166 Box 1613\nDPO AE 70795',
},
    'key48641': 'value89131',
    'key71159': 'value73895',
    'key18864': 'value36541',
    'key23067': 'value62522',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Dalton Williams',
    'address': '618 Robert Highway Suite 440\nNorth Ricky, MI 57344',
    'text': 'Member court Democrat picture enter take. Again against lay. Television market our enter care know.\nMouth avoid able space standard catch. Thank candidate color room southern front politics.',
    'email': 'lynn75@example.com',
    'phone_number': '444-213-0542x64926',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lori Simmons',
],
    'json': {
    'name': 'Martha Baxter',
    'address': '719 Steven Stravenue Apt. 422\nLake Oliviamouth, WI 24675',
},
    'key4977': 'value65460',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kristina Newton',
    'address': '91564 Martin Fork\nPatriciaton, IL 06656',
    'text': 'Positive firm where I. Market money contain.\nDaughter charge white box oil. Successful spend air. Main everything moment among.',
    'email': 'laura55@example.net',
    'phone_number': '+1-461-744-4029',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Miller',
    'Jason Watkins',
    'David Gomez',
    'Juan Ramirez',
    'Amanda Burgess',
    'Kathryn Haney',
    'Michael Nolan',
    'David Morris',
],
    'json': {
    'name': 'Brian Park',
    'address': '440 Beth Court Suite 581\nWrightbury, NC 60341',
},
    'key71816': 'value76512',
    'key24257': 'value93796',
    'key96307': 'value73671',
    'key22709': 'value33053',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Melissa Gray',
    'address': '735 Young Divide Suite 811\nConnerbury, MA 35842',
    'text': 'Interesting strategy use word. Artist reach spend Democrat mind. Contain PM song decision another.\nBeautiful stop final fly politics. Church computer experience every home well bit trade.',
    'email': 'vwilliams@example.org',
    'phone_number': '(440)937-2065x08820',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Jackson',
    'Michael Bradford',
    'Shelby Mann',
    'Dominic Diaz',
    'Jane Johnson',
],
    'json': {
    'name': 'Hunter Anderson',
    'address': '44753 David Greens\nCookberg, WI 51108',
},
    'key77448': 'value49541',
    'key61916': 'value6084',
    'key55776': 'value17922',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'John Ramirez',
    'address': 'USNS Watson\nFPO AA 64592',
    'text': 'Main the front local military. Debate answer if deep. National cause language never. Piece have production sport choose.\nFuture great add walk industry. Between trouble add yet building.',
    'email': 'weberthomas@example.com',
    'phone_number': '758-241-4584',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Regina Dawson',
    'Christopher Owens',
    'Taylor Drake',
    'Bradley Coffey',
    'Brian Hancock',
    'Donald White',
    'Lindsay Willis',
    'Alexander Sanders',
],
    'json': {
    'name': 'Susan Stone',
    'address': '084 David Causeway Apt. 159\nCheyennemouth, WI 05753',
},
    'key70203': 'value13510',
    'key81077': 'value34239',
    'key66372': 'value48936',
    'key35042': 'value27085',
    'key88166': 'value68913',
    'key76645': 'value15105',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Patricia Hughes',
    'address': '33287 Baker Lake\nMartineztown, OR 30388',
    'text': 'Former total seem risk every but. Worker research wear human simple send game. Arm give language. Magazine act similar cultural economic water nor.',
    'email': 'alexandervargas@example.org',
    'phone_number': '(531)879-2432x1536',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Leah Rodriguez',
    'Emily Sanders',
    'Chelsey Orozco',
    'Whitney Diaz',
    'Jamie Shelton',
],
    'json': {
    'name': 'David Mcdonald',
    'address': '4054 Edgar Islands Suite 449\nBrowntown, WY 16436',
},
    'key66739': 'value90950',
    'key52424': 'value88213',
    'key40148': 'value35162',
    'key2273': 'value83812',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Kathleen Roman',
    'address': '284 Kline Freeway Suite 639\nWilliambury, IN 62549',
    'text': 'Land support capital board charge spend go.\nKnowledge wait across adult woman. Budget policy expert thank ago such enough. Enjoy protect teacher perform still.',
    'email': 'thomasmurillo@example.org',
    'phone_number': '001-477-588-2314x7893',
    'array_int_dynamic': [
    40175,
],
    'array_varchar_dynamic': [
    'Briana Robinson',
    'John Donovan',
    'Steven Daniels',
    'Elizabeth Dyer',
    'Tyler Farmer',
    'Shelly Rodriguez',
    'Evan Lowery',
],
    'json': {
    'name': 'Michael Good',
    'address': '4250 Brown Forest Suite 820\nJenniferview, AS 05359',
},
    'key45139': 'value51610',
    'key94571': 'value80186',
    'key22318': 'value37479',
    'key64468': 'value73144',
    'key90603': 'value62468',
    'key19483': 'value31542',
    'key34679': 'value92128',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Victor Dodson',
    'address': '4003 Frederick Place\nPort James, NJ 70682',
    'text': 'Administration case recent late step north town. Of anything executive. Allow ten trip sing live.\nSometimes deal test husband store. Film if high build attack.',
    'email': 'lopezkelly@example.com',
    'phone_number': '972.699.9860',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'James Perry',
],
    'json': {
    'name': 'Susan Lee',
    'address': '5286 Stewart Glen Suite 330\nTonyafurt, SD 94466',
},
    'key22248': 'value41688',
    'key11300': 'value40363',
    'key73672': 'value78415',
    'key82609': 'value91471',
    'key8808': 'value97500',
    'key78241': 'value59168',
    'key65300': 'value70565',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Tina Stone',
    'address': '745 Mendez Camp\nChristensenville, ND 68269',
    'text': 'Wind specific four end participant thousand field. Inside pay to adult hotel party two property. Beautiful door career use dog.',
    'email': 'daniel93@example.com',
    'phone_number': '488-498-4221',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Laura Baker',
],
    'json': {
    'name': 'Deborah Swanson',
    'address': '8605 Adams Shore\nEast Michael, NE 87659',
},
    'key31413': 'value18994',
    'key71383': 'value42067',
    'key454': 'value11290',
    'key88433': 'value7730',
    'key51068': 'value543',
    'key70109': 'value74363',
    'key7260': 'value71227',
    'key17609': 'value38142',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Luke Garrett',
    'address': '70294 Christine Forest\nLake Chadborough, DE 94329',
    'text': 'If under main goal. Ready matter serious high.\nNice event important six. Easy again either attention issue provide.',
    'email': 'jcervantes@example.com',
    'phone_number': '6242381717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alexis Mitchell',
    'Christopher Gibson',
    'Christopher English',
    'Rhonda Solis',
    'Linda Lee',
    'Kristen Riley',
    'Karla Parker',
],
    'json': {
    'name': 'Kelly Watkins MD',
    'address': '044 Compton Hills\nWest Sarah, MS 52747',
},
    'key83648': 'value26975',
    'key29525': 'value47671',
    'key38578': 'value56317',
    'key62429': 'value49256',
    'key94723': 'value88828',
    'key86526': 'value33148',
    'key23358': 'value42045',
    'key49456': 'value2751',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Amanda Nguyen',
    'address': '9607 Sullivan Cape Apt. 125\nGregoryside, NH 07849',
    'text': 'Serve wish rate tough. Purpose nice meet.\nRealize reflect later shoulder feel would management chair. Response claim interesting prepare.',
    'email': 'michelle68@example.net',
    'phone_number': '+1-717-270-0347x646',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stacey Shepherd',
    'Beverly Tyler',
    'Jeremy Daniel',
    'Richard Parsons',
    'Stephen Chandler',
    'Nathan Martin',
    'Curtis Smith',
    'Christopher King',
],
    'json': {
    'name': 'Julia Nguyen',
    'address': '0110 Jared Freeway\nBenjaminport, MI 78234',
},
    'key4196': 'value29425',
    'key90366': 'value67992',
    'key77506': 'value22752',
    'key85934': 'value90106',
    'key60678': 'value94991',
    'key61661': 'value51784',
    'key29505': 'value62056',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jeff Lane',
    'address': '3050 William Crescent\nWest Shannon, VT 19335',
    'text': 'Style physical send. Argue expect relationship who meeting think late.\nWithin community become show travel voice point. Strategy really according particular body everyone market.',
    'email': 'patrick68@example.net',
    'phone_number': '(503)637-5865x709',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Heather Meadows',
    'Christina Hopkins',
    'Brandi Flores',
],
    'json': {
    'name': 'Laurie Weber',
    'address': '4517 Kim Pine Apt. 600\nMarkshire, NC 87566',
},
    'key62320': 'value32416',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Ashley Smith',
    'address': '220 Justin Run\nAmberchester, WA 25709',
    'text': 'General make try focus southern ten. Foot prevent least personal.\nMeeting article approach oil during see story. Practice establish like get generation.',
    'email': 'tanya54@example.org',
    'phone_number': '(705)896-5786x3826',
    'array_int_dynamic': [
    74272,
],
    'array_varchar_dynamic': [
    'Michael Taylor',
    'Steve Jacobs',
    'Alexandra King',
],
    'json': {
    'name': 'Matthew Moore',
    'address': 'USCGC Jenkins\nFPO AA 10064',
},
    'key53472': 'value62590',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Olivia Bolton',
    'address': '086 Callahan Village\nLake Cassandrabury, AZ 71900',
    'text': 'Game stuff cup cultural stage another member. Accept specific item feeling. Man now itself move.',
    'email': 'lanejoann@example.org',
    'phone_number': '437.826.6867x74669',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Wilkinson',
    'Frank Colon',
],
    'json': {
    'name': 'John Allen',
    'address': 'PSC 2466, Box 3704\nAPO AP 07555',
},
    'key27322': 'value92898',
    'key68339': 'value38555',
    'key64601': 'value19120',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Jennifer Maldonado',
    'address': '999 Mariah Passage Suite 040\nAngelaborough, CO 20170',
    'text': 'Turn season why arm certain market. During long fine raise provide street later.\nTo here road several at.\nStill start current bar consumer. Practice education life data season instead somebody.',
    'email': 'saraharmstrong@example.org',
    'phone_number': '001-921-911-2438',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Todd Blanchard',
],
    'json': {
    'name': 'Joshua Reyes',
    'address': '9255 Jones Corners\nNorth Timothy, TX 22993',
},
    'key45029': 'value51134',
    'key45079': 'value28991',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Christopher Taylor',
    'address': '187 Danielle Trafficway Apt. 046\nWest Nicholasbury, WI 03022',
    'text': 'Senior the fish resource paper. Car indicate million toward.\nVoice operation page.',
    'email': 'urocha@example.net',
    'phone_number': '(632)406-3201x5889',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christina Curtis',
],
    'json': {
    'name': 'Brian Holmes',
    'address': '814 Marks Plains\nDavidbury, LA 29337',
},
    'key77111': 'value52272',
    'key5374': 'value56521',
    'key63912': 'value35971',
    'key61250': 'value5606',
    'key74775': 'value13144',
    'key77962': 'value10961',
    'key30680': 'value40530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Kristen Evans',
    'address': '5738 Moore Courts\nSanchezhaven, NC 05714',
    'text': 'Wall might simply control particular positive form. Century up natural friend kind executive church. Admit plant law number many meet character.',
    'email': 'joshuacowan@example.org',
    'phone_number': '+1-465-385-4426',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Charles Cabrera',
    'Megan Chambers',
    'Troy Kelly',
    'Tanya Porter',
    'Hunter Parsons',
],
    'json': {
    'name': 'Melissa Terry',
    'address': '71270 William Station Apt. 496\nPort Barrychester, MI 96182',
},
    'key23568': 'value45904',
    'key83206': 'value82909',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Jesus Johnson',
    'address': '1807 Evans Prairie Apt. 066\nCervantesville, MH 17980',
    'text': 'Impact energy policy section before establish identify. That friend challenge against focus fall hair. This bit trial special.',
    'email': 'anthonycastillo@example.org',
    'phone_number': '(269)816-7370x57484',
    'array_int_dynamic': [
    36044,
],
    'array_varchar_dynamic': [
    'Miss Tara Underwood',
    'Ana Brennan',
    'Steven Richardson',
    'Michele Parker',
    'Stephanie Riley',
],
    'json': {
    'name': 'Leslie Schultz',
    'address': '43670 Camacho Rapids Suite 113\nNorth Steven, MI 84511',
},
    'key96195': 'value47643',
    'key57013': 'value8586',
    'key54058': 'value53837',
    'key68207': 'value29589',
    'key65280': 'value1533',
    'key48418': 'value94934',
    'key39067': 'value38055',
    'key69437': 'value14523',
    'key28628': 'value30981',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Tyrone Peterson',
    'address': '40262 Coleman Course Suite 950\nLeonfurt, WI 35327',
    'text': 'Thank officer certain perhaps imagine strategy girl. You some piece economy.\nName condition until land at Mr. No hard pick cost everything left.',
    'email': 'phillipsmichael@example.org',
    'phone_number': '624-613-3397x06509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Roy Hanson',
],
    'json': {
    'name': 'Henry Davis',
    'address': '8028 Velasquez Run\nTanyaport, NJ 78265',
},
    'key50235': 'value59033',
    'key84435': 'value491',
    'key11822': 'value31688',
    'key68611': 'value74317',
    'key18389': 'value83579',
    'key63604': 'value13661',
    'key93296': 'value3686',
    'key22074': 'value64205',
    'key27669': 'value58229',
    'key85152': 'value67243',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jennifer Keith',
    'address': '370 Jones Valley Suite 575\nEricville, MP 45588',
    'text': 'Popular its chance black area between yard music.\nRealize drug scene drop offer morning.',
    'email': 'josephcarpenter@example.com',
    'phone_number': '942.832.4225x6586',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kristine Parker',
    'Jeremiah Cochran',
    'Anna Bates',
    'Justin Rodriguez',
    'Andrea Scott',
    'Crystal Brown',
    'Tanya Thomas',
    'Deborah Alvarez',
    'Edward White',
    'Mary Carter',
],
    'json': {
    'name': 'John Lewis',
    'address': '91355 Hart View Apt. 047\nChaseberg, NV 07415',
},
    'key80024': 'value97416',
    'key74432': 'value26650',
    'key66327': 'value50273',
    'key2569': 'value59204',
    'key35968': 'value94264',
    'key16010': 'value39713',
    'key99719': 'value44044',
    'key25031': 'value96945',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Katherine Wilson',
    'address': '0777 Krista Orchard Suite 745\nChristineport, MP 88766',
    'text': 'Discuss yeah free. Once onto least short.\nImage everything best few. Painting suddenly career show time key.',
    'email': 'uwright@example.org',
    'phone_number': '631.676.5862x183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Tucker',
    'Douglas Hunt',
    'John Bryan',
    'Alexa Powers',
    'James Warner',
    'Sarah Nelson',
    'Katelyn Murillo',
    'Nicholas Little',
    'Nathaniel Morris',
],
    'json': {
    'name': 'Raymond Carlson',
    'address': '9318 Cynthia Cape Apt. 588\nMeadowsland, SD 04675',
},
    'key26051': 'value19036',
    'key45228': 'value41642',
    'key31973': 'value19138',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Kimberly Garrison',
    'address': '84109 Little Mills\nLaurenfort, MT 25225',
    'text': 'Find work mission chance last. Available take lose a box management marriage today.\nHeart this stuff above eight back. Center program cultural water. Career yeah form parent full dog bar.',
    'email': 'djackson@example.com',
    'phone_number': '+1-981-683-1013x827',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steven Patterson',
    'Ashley Johnson',
    'Leslie Anderson',
    'Lisa Allen',
    'George Stewart',
    'Brad Jackson',
    'Lisa Bowman',
    'Heather Gray',
],
    'json': {
    'name': 'Dylan Carter',
    'address': '1882 Hawkins Passage\nNorth Georgeburgh, AS 61536',
},
    'key19353': 'value99915',
    'key4436': 'value37547',
    'key67305': 'value19456',
    'key24952': 'value19695',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Sherry Ruiz',
    'address': '3404 Jessica Cliff Suite 180\nRomanborough, IN 57623',
    'text': 'Cut girl from no tend police beautiful. Less fight learn hour job war idea.',
    'email': 'jacquelinecarter@example.com',
    'phone_number': '664.560.7082',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Anderson',
    'Ashley Anderson',
    'Michael Williams',
],
    'json': {
    'name': 'Andrea Escobar',
    'address': '58403 Martin Ridge\nAntonioton, MA 65294',
},
    'key41243': 'value15864',
    'key24749': 'value28368',
    'key71091': 'value42182',
    'key39468': 'value93172',
    'key77521': 'value86656',
    'key23842': 'value18318',
    'key33084': 'value81929',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Joshua Collier MD',
    'address': '56189 Christopher Stream Apt. 631\nVeronicaborough, PA 24512',
    'text': 'Television civil north may training. Network someone success.\nChange investment week different true media push. Structure above behavior already team movement include.',
    'email': 'smitheric@example.org',
    'phone_number': '954-702-7938x7854',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Adam Garcia',
    'Dawn Wright',
    'Shawna Butler',
    'Megan Phillips',
],
    'json': {
    'name': 'Theresa Thompson',
    'address': '47838 Bryant Curve Suite 608\nLake Joseland, ID 38896',
},
    'key11947': 'value72263',
    'key79635': 'value41720',
    'key16769': 'value60651',
    'key22203': 'value28817',
    'key49385': 'value25065',
    'key93010': 'value21797',
    'key22995': 'value77719',
    'key21951': 'value38257',
    'key31793': 'value83639',
    'key39681': 'value21354',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Nicole Bryant',
    'address': '1800 Howell Neck Suite 763\nNorth Eric, CA 09587',
    'text': 'Woman nothing instead tax student address later church. Service word huge.',
    'email': 'davidgould@example.net',
    'phone_number': '(555)630-7151',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Hawkins',
],
    'json': {
    'name': 'Briana Vasquez',
    'address': '4444 Mendez Burgs Suite 967\nWest Samuelberg, DE 51397',
},
    'key22498': 'value96585',
    'key70723': 'value44162',
    'key10388': 'value39757',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'James White',
    'address': '9591 Michael Junction Suite 428\nWilliamsville, NV 96687',
    'text': 'Finish scene pull easy reason. Another discussion employee travel.\nSummer student like accept carry within wife. Lot yeah fine away. Pick majority group herself. You cause simply step.',
    'email': 'lindajackson@example.net',
    'phone_number': '9933016018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Peterson',
    'Steven Shaw',
    'Lynn Murphy',
],
    'json': {
    'name': 'Barbara Harris',
    'address': '654 Matthew Way\nChristinaside, TX 88805',
},
    'key381': 'value17599',
    'key34918': 'value19059',
    'key5063': 'value23029',
    'key54162': 'value68487',
    'key23143': 'value32418',
    'key32771': 'value69646',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Amanda Sanchez',
    'address': '2927 Cooley Junctions\nJonesbury, AK 30061',
    'text': 'Nearly political democratic serve these investment. Think arrive thing decade despite accept. Color because mother sit this might.',
    'email': 'keith30@example.com',
    'phone_number': '851-744-6701x86451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Destiny Walker',
    'Krista Watkins',
    'Carolyn Davis',
    'Jennifer Weeks',
    'Ruth Johnson',
    'Thomas Norris',
    'Angela Tran',
    'Matthew Rios',
],
    'json': {
    'name': 'Carl Moore',
    'address': '165 Justin View\nJoyshire, UT 55432',
},
    'key81660': 'value68651',
    'key32148': 'value65145',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Mrs. Kimberly Parsons',
    'address': '08105 Carolyn Brooks Suite 176\nMaryburgh, PA 93946',
    'text': 'Name gun raise Mrs we huge a. Number represent generation high. Security with about dinner environment difference person.\nCenter simply pull mission decade. Whom while return act.\nGlass affect table.',
    'email': 'toninguyen@example.net',
    'phone_number': '746.765.0302',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Roberts',
    'Mary Owen',
    'Austin Snyder',
    'Connor Pena',
    'Randall Case',
    'Carly Murillo',
    'Curtis Campbell',
    'David Mitchell',
    'Anthony Bailey',
],
    'json': {
    'name': 'Jordan Archer',
    'address': '317 Lisa Mill Suite 285\nErikaland, HI 62506',
},
    'key46367': 'value38697',
    'key99056': 'value55241',
    'key89245': 'value45379',
    'key1197': 'value70351',
    'key84006': 'value19420',
    'key43579': 'value20662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Deborah Moreno',
    'address': '418 Samuel Vista\nCarlychester, ND 19998',
    'text': 'Fire marriage card recognize throughout window entire. Research enter street learn. Receive true citizen development.\nFew political next add or her choice. Discuss again them later.',
    'email': 'mcdonaldthomas@example.com',
    'phone_number': '+1-615-544-8885x559',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lawrence Estes',
    'Christopher Wheeler',
    'Amy Byrd',
    'Nicole Figueroa',
],
    'json': {
    'name': 'Jeremy Willis',
    'address': '9060 Mullen Street Apt. 567\nNorth Kristie, OK 01450',
},
    'key24754': 'value79064',
    'key38192': 'value1920',
    'key95490': 'value66372',
    'key13555': 'value48141',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Kristin Carlson',
    'address': '7474 Ashley Fall Apt. 233\nWest Haley, LA 57701',
    'text': 'Near gas share. For policy behavior free far.\nRemain stand truth. Study none add live foot walk.\nEvent box assume assume middle.',
    'email': 'soliskathy@example.org',
    'phone_number': '269.568.6236x43934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Darius Whitehead DDS',
    'Jose Black',
    'Matthew Davis',
    'Bethany Hart',
    'Matthew Chavez',
],
    'json': {
    'name': 'Jamie Galvan',
    'address': '66565 Margaret Flats Suite 827\nMeyersberg, VT 94203',
},
    'key35941': 'value64384',
    'key29552': 'value94325',
    'key59962': 'value10610',
    'key74541': 'value96900',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Michael Cherry',
    'address': '104 Duffy Ports\nSouth Terrybury, OH 52696',
    'text': 'Floor reduce treatment continue. Carry technology arm feel history list next. Test behavior ahead order put mouth rich.',
    'email': 'brittneyavila@example.org',
    'phone_number': '496-796-8398',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Lowe',
    'Sabrina Thomas',
    'Brenda English',
    'Brendan Cooper',
    'Kathy Lara',
    'Matthew Silva',
    'Sarah Clark',
    'Carl Webb',
    'Shari Salinas',
],
    'json': {
    'name': 'Donald Cortez',
    'address': '885 Brown Street Suite 450\nHeatherchester, IA 51135',
},
    'key61441': 'value60880',
    'key49374': 'value23668',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Jacob Morris',
    'address': '137 Chelsey Green\nKathrynbury, PW 86883',
    'text': 'Act seven than.\nWant figure fill treat these. West consumer star late modern worker.',
    'email': 'thomasregina@example.org',
    'phone_number': '+1-806-268-9386',
    'array_int_dynamic': [
    666,
],
    'array_varchar_dynamic': [
    'Lisa Miller',
    'Mark Fletcher',
    'Frank Rodriguez',
    'Michael Gray',
    'Brittany Powell',
    'Brittany Johnson',
    'Amy Mccarthy',
    'Amy Moore',
    'Jesse Kim',
    'Alicia Murphy',
],
    'json': {
    'name': 'Nicole Briggs',
    'address': 'USCGC Sullivan\nFPO AA 16975',
},
    'key5946': 'value24110',
    'key8009': 'value49804',
    'key59864': 'value37894',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'David Ramirez',
    'address': '1660 Michael Turnpike\nWest Hunter, VI 04161',
    'text': 'History follow finish main tough vote although. Benefit indeed cause Mr pick.\nThrough there owner full minute full. Tax financial floor far. Development politics daughter.',
    'email': 'vvasquez@example.com',
    'phone_number': '+1-890-328-8422',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Miller',
    'Vincent Griffin',
    'Brad Doyle',
    'Robert Chen',
],
    'json': {
    'name': 'Kevin Brewer',
    'address': '592 Rivera Parkways\nTimothyland, WA 49889',
},
    'key44296': 'value37509',
    'key22329': 'value41111',
    'key24835': 'value47929',
    'key27899': 'value87898',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Steven Glover',
    'address': '14136 Christopher Ford\nStanleychester, DC 23435',
    'text': 'Top kitchen meeting billion then continue know.\nAnd create fight bag year before. Again part growth. Reach bag enjoy control alone senior wide floor.',
    'email': 'mclark@example.net',
    'phone_number': '+1-856-729-1519x2772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Martin Smith',
    'Kevin Allen',
    'Michael Diaz',
    'Robert Reynolds',
    'Joseph Gordon',
],
    'json': {
    'name': 'Heather Harper',
    'address': '0439 Hall Mission Apt. 846\nRamirezmouth, KS 59403',
},
    'key50665': 'value9587',
    'key34900': 'value62396',
    'key21639': 'value22809',
    'key26741': 'value96640',
    'key90178': 'value12743',
    'key84432': 'value72890',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Christopher Haas',
    'address': '3819 Amber Walks Suite 873\nBooneview, GU 97230',
    'text': 'Radio message bed success never possible drug. Item him crime.\nSuch bit cost. Fly gun throw various. Safe special source bed word into.\nSubject ago tax condition.',
    'email': 'raven50@example.net',
    'phone_number': '+1-855-924-1992x77347',
    'array_int_dynamic': [
    58492,
],
    'array_varchar_dynamic': [
    'Brandon Moore',
    'Jon Marquez',
    'Edward Pittman',
    'Mike Wang',
    'Timothy Bean',
    'Shawn Lee',
    'Cory Arnold',
    'Andrea Hayes',
    'Robert Schwartz',
    'Cheryl Hayes',
],
    'json': {
    'name': 'Shawn Palmer',
    'address': '34502 Jay Locks Apt. 676\nLake Sandra, KY 57873',
},
    'key16172': 'value77206',
    'key25259': 'value63921',
    'key36239': 'value46581',
    'key9941': 'value31530',
    'key48623': 'value66494',
    'key25167': 'value69935',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Brett Bond',
    'address': '056 Ferguson Courts\nNew Candice, IN 04605',
    'text': 'Hour statement marriage. State sure without include religious care. Find director by loss score.\nThought federal save enjoy person population himself. Test opportunity front professor see.',
    'email': 'cory79@example.net',
    'phone_number': '861-477-6899x917',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Donna Thompson',
    'Ruth Hunter',
    'Nathaniel Kelley',
    'Michael Sanders',
    'Melissa Long',
    'Bryan Nguyen',
    'Kenneth Garza',
],
    'json': {
    'name': 'Anthony Hampton',
    'address': '5466 Smith Loop\nPort Rachelbury, VA 38058',
},
    'key30333': 'value69027',
    'key41389': 'value18300',
    'key11342': 'value39501',
    'key12058': 'value34714',
    'key79371': 'value64804',
    'key5758': 'value12209',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Laura Brown',
    'address': '183 Ashley Isle\nAmbershire, TX 38376',
    'text': 'Town ahead return main. There perform what life man paper throughout dog. Shoulder answer partner account section north near relationship.',
    'email': 'sruiz@example.com',
    'phone_number': '+1-448-784-0793',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Chelsea Randall',
    'Joshua Mckee',
    'Brandon Chandler',
    'Dawn Miller',
    'Kyle Rivera',
    'Jimmy Oliver',
    'Timothy Adkins',
],
    'json': {
    'name': 'Jessica Faulkner PhD',
    'address': '5372 Rogers Center Suite 793\nLake Leefort, HI 10978',
},
    'key47371': 'value66909',
    'key73009': 'value23537',
    'key59392': 'value66394',
    'key59126': 'value79529',
    'key11153': 'value39238',
    'key3155': 'value9421',
    'key15713': 'value30587',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jeffrey Nelson',
    'address': 'USCGC Clark\nFPO AA 44794',
    'text': 'Through street cause program. Interest nor sit better anything travel.\nDesign risk the along.',
    'email': 'elizabethhoward@example.com',
    'phone_number': '001-854-277-9846',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Russell',
    'Rhonda Wolf',
    'Joe Ochoa',
    'Kenneth Ryan',
    'Adam Blackburn',
    'Tommy Gilmore',
    'Billy White',
    'Alex Garrison',
    'Miss Sandra Wade DVM',
    'Erik Wilkins',
],
    'json': {
    'name': 'Monica Hayes',
    'address': '48815 Keller Mountain\nNew Michaelstad, NJ 23211',
},
    'key37233': 'value30237',
    'key22139': 'value30121',
    'key1412': 'value24066',
    'key23926': 'value7130',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Rebecca Kaiser',
    'address': '678 Michael Burgs\nAndersonbury, DE 37590',
    'text': 'Agreement best attorney minute shake. Seven degree plant.\nSend nice them pretty participant year establish.',
    'email': 'angelicadunlap@example.net',
    'phone_number': '965.536.3779x578',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Scott Miranda',
],
    'json': {
    'name': 'Brent Martinez',
    'address': '8385 Morgan Route Apt. 593\nAndersonshire, SD 08202',
},
    'key57483': 'value23456',
    'key11527': 'value71155',
    'key86546': 'value29026',
    'key56076': 'value47134',
    'key67452': 'value42126',
    'key68278': 'value79994',
    'key42081': 'value93142',
    'key93776': 'value72626',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'John Adams',
    'address': '7750 Richards Pass Suite 384\nSouth John, AL 49046',
    'text': 'Keep budget true our wrong pull every. Difficult PM pay decade style cover population nor. Probably since rock information assume test.',
    'email': 'rivaschristopher@example.net',
    'phone_number': '(702)298-8387x02164',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Vaughn',
    'Gary Hansen',
    'Stephanie Harmon',
],
    'json': {
    'name': 'Dean Huynh',
    'address': 'PSC 1002, Box 2118\nAPO AA 66125',
},
    'key22326': 'value93997',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Austin Sanchez',
    'address': '79677 Tina Squares\nNorth Alexander, AR 35422',
    'text': 'Body expect tonight. Large civil five central kid. Window bed station wonder difference activity have.\nState eight word outside research. Much however whatever fly stock share people.',
    'email': 'agriffin@example.net',
    'phone_number': '442.974.4983x675',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Donna Garrison',
    'Jack Johnson',
],
    'json': {
    'name': 'Dennis Mcclure',
    'address': '423 Jeremy Oval\nSouth Sueland, AS 42367',
},
    'key60737': 'value87013',
    'key18696': 'value9735',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Laura Campbell',
    'address': '92715 Lisa Garden Apt. 979\nEast Lisa, CO 92538',
    'text': 'Coach institution offer degree there memory. Study high improve style movie tonight. Late cultural important statement.',
    'email': 'hgoodwin@example.org',
    'phone_number': '589.379.8785x07308',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Scott Jones',
    'Chris Haney',
    'Anthony Dawson',
    'Bryan Stephens',
    'Brenda Rivera',
],
    'json': {
    'name': 'Kimberly Wood',
    'address': '95846 Lambert Inlet\nHartmanland, MT 32263',
},
    'key98688': 'value65135',
    'key93488': 'value67839',
    'key81224': 'value49950',
    'key6590': 'value25477',
    'key85981': 'value19593',
    'key79039': 'value58338',
    'key95069': 'value66980',
    'key43570': 'value67694',
    'key22176': 'value31320',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Kathryn Stephens',
    'address': '0592 Odonnell Loaf\nEmmachester, OR 23105',
    'text': 'Space sport beautiful particularly design fire ask. Economy matter experience.\nTurn eye environment trial kind behind anyone. Research behind necessary environment stay.',
    'email': 'webbstacy@example.org',
    'phone_number': '767.842.2039x703',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michele Vaughn',
    'David Rosario',
    'Jennifer Williams',
],
    'json': {
    'name': 'David Richardson',
    'address': '991 Evans Prairie Apt. 231\nPort Shirleyfort, UT 93994',
},
    'key98868': 'value23964',
    'key50343': 'value53846',
    'key3293': 'value10724',
    'key39435': 'value59047',
    'key48046': 'value90053',
    'key93188': 'value79038',
    'key28260': 'value32745',
    'key19844': 'value7190',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Mrs. Dawn Strong',
    'address': '035 Kevin Walk Suite 227\nPort David, TX 99718',
    'text': 'Organization body none represent gas billion might. Address quickly benefit idea. Here similar west dinner during.\nCover until role notice.\nConsider race agency head. Reality economic smile.',
    'email': 'castillomatthew@example.org',
    'phone_number': '001-558-955-0819',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Alyssa Cannon MD',
    'Troy Poole',
    'Kevin Gardner',
    'Dean Ferrell',
    'Barbara Lopez',
],
    'json': {
    'name': 'Veronica Young',
    'address': 'PSC 3659, Box 0991\nAPO AA 55949',
},
    'key26538': 'value56189',
    'key10488': 'value3787',
    'key74708': 'value72880',
    'key5607': 'value98182',
    'key15034': 'value34087',
    'key4917': 'value25103',
    'key53892': 'value40584',
    'key32472': 'value38431',
    'key15994': 'value46735',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Christy Steele',
    'address': '608 Wilson Stream\nParkerborough, WY 19101',
    'text': 'Change still kid between smile suddenly him participant. Determine anything high consumer even see. Leg civil upon base today religious home.',
    'email': 'parkergary@example.org',
    'phone_number': '907-954-1596',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Mendoza',
    'Garrett Nelson',
    'Alexander Casey',
    'Michelle Thomas',
    'Daniel Kelly',
    'Kimberly Villarreal',
    'Beth Martinez',
    'Robert Frye',
    'Martin Hester',
],
    'json': {
    'name': 'Ruth Salazar',
    'address': '3269 Perez View\nWilsonmouth, TN 64879',
},
    'key63657': 'value50016',
    'key95783': 'value28620',
    'key39705': 'value41338',
    'key43467': 'value45819',
    'key43791': 'value78391',
    'key43343': 'value9433',
    'key32481': 'value76809',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Stephanie Wallace',
    'address': '5798 Angela Valleys Suite 811\nNew Jenniferville, MT 48668',
    'text': 'Art difference physical subject challenge. Election one trip local center act.\nEnd sort kind continue citizen. Show white blue. Structure off dark central laugh our man.',
    'email': 'erichoward@example.net',
    'phone_number': '231.763.4085',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brittney Olson',
    'Brittany Stone',
    'Julie Holt',
    'Brittany Acevedo',
    'Rebekah Winters',
    'Alex Trevino Jr.',
    'Bradley Sims',
    'Luis Harrell',
],
    'json': {
    'name': 'Jasmine Hansen',
    'address': 'USNS Forbes\nFPO AE 54852',
},
    'key4920': 'value95393',
    'key5259': 'value22478',
    'key3704': 'value99789',
    'key71620': 'value69250',
    'key21015': 'value6595',
    'key75108': 'value94490',
    'key24852': 'value74542',
    'key50643': 'value74753',
    'key50781': 'value79164',
    'key81239': 'value88328',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Jillian Hamilton',
    'address': '4741 Bradley Summit Apt. 734\nMoralesburgh, NM 60304',
    'text': 'Always seem ten side state. North hope church prepare their indicate mention issue. Property worry court also.\nFour person recent son. Pull force president country notice.',
    'email': 'susandavis@example.org',
    'phone_number': '+1-297-852-2926x23499',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Julie Elliott',
    'Daniel Vasquez',
    'Nicholas Gentry',
    'Wendy Nichols DDS',
    'Matthew Santana',
    'Jamie Burton',
    'Courtney Adkins',
],
    'json': {
    'name': 'Amanda Stewart',
    'address': '416 Laura Mews Apt. 597\nEnglishchester, SC 28272',
},
    'key11107': 'value92605',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Lori Brown',
    'address': '61659 Rebecca Crescent\nSouth Christinaton, IN 19825',
    'text': 'Part believe situation until but. Nothing wrong cultural benefit common speech idea.',
    'email': 'brittanymcdonald@example.com',
    'phone_number': '(364)315-0163',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Eric Martinez',
    'Deborah Erickson',
    'Donald Shields',
    'Kyle Henry',
    'Brian Mcdaniel',
    'Thomas Waters',
],
    'json': {
    'name': 'Jessica Stevens',
    'address': '00015 Wesley Manors\nSouth Ericshire, IN 16220',
},
    'key81170': 'value45554',
    'key35933': 'value21179',
    'key8973': 'value95870',
    'key27627': 'value64390',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Stacy Chen',
    'address': '27171 Diaz Springs Suite 866\nJessicashire, OK 65917',
    'text': 'Professor take imagine bed blood. Should add could sure number.\nCause year coach involve hope instead skill. Ability crime bill important role now firm rich.',
    'email': 'josephanderson@example.org',
    'phone_number': '001-656-576-9215x60379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kendra Matthews',
    'Clayton Davis',
    'Daniel Baker',
    'Michael Wheeler',
    'Anthony Shaw',
    'Kevin Lee',
    'Lauren Bishop',
    'Morgan Cannon',
],
    'json': {
    'name': 'David Scott',
    'address': '830 Alexis Rapid\nEast Kimberly, MS 34953',
},
    'key44007': 'value93652',
    'key83223': 'value23292',
    'key3244': 'value78937',
    'key64061': 'value76596',
    'key60818': 'value70643',
    'key4185': 'value93516',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Antonio Ramirez',
    'address': '3139 Megan Views Apt. 267\nLake Kelly, VA 60250',
    'text': 'Cut well teach nearly standard game majority. Onto show tonight evidence major.\nReality push develop apply push part. Save right until section get camera.',
    'email': 'rayjessica@example.net',
    'phone_number': '(645)743-2730x122',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Long',
    'Linda Valdez',
    'Joseph Vargas',
],
    'json': {
    'name': 'Travis Williams',
    'address': '0608 Carol Park\nSouth Denise, OK 95473',
},
    'key8453': 'value36859',
    'key46415': 'value55956',
    'key6913': 'value28954',
    'key74425': 'value95850',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Garrett Morris',
    'address': 'Unit 5054 Box 9178\nDPO AP 17252',
    'text': 'Among low child school. Force red budget from prove use.\nYet manager less use prove. Art husband listen property young chance.',
    'email': 'allensonya@example.net',
    'phone_number': '736-940-1749x43983',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Brown',
    'Sheila Smith',
    'Summer Snyder',
    'Lindsay Wise',
    'Lee Sosa',
    'Bridget Mitchell',
    'Scott Cooper',
    'Jessica Sullivan',
    'Matthew Parrish',
    'Brandon Kennedy',
],
    'json': {
    'name': 'Charlene Benson',
    'address': '9302 Diane Streets Suite 976\nOrtegaberg, CA 40825',
},
    'key23472': 'value43203',
    'key44315': 'value20165',
    'key54257': 'value29901',
    'key52642': 'value28798',
    'key62746': 'value65903',
    'key55829': 'value68588',
    'key84155': 'value95907',
    'key66039': 'value53734',
    'key6202': 'value11020',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Allison Kirk',
    'address': '982 Clark Divide\nDouglasmouth, NC 89490',
    'text': 'Available role fast again main value. Movie crime small capital research assume dream. Size staff deep within.',
    'email': 'cevans@example.com',
    'phone_number': '+1-793-890-2187x50385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Rios MD',
    'Jody Moon',
    'Kenneth Morgan',
    'William Burgess',
    'James Stewart',
    'Aaron Mays',
    'Manuel Simmons',
    'Kathryn Palmer',
    'Benjamin Mejia',
    'Yolanda Anderson',
],
    'json': {
    'name': 'Jacqueline Clarke',
    'address': 'PSC 3310, Box 8018\nAPO AA 06543',
},
    'key68348': 'value94397',
    'key12830': 'value35303',
    'key55656': 'value48294',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Troy Lee',
    'address': '6809 Jennifer Plains Suite 270\nHouseburgh, LA 27600',
    'text': 'Capital throw health nothing hair. Down student approach tend population something keep who. Section customer heavy last true.',
    'email': 'jacobsjonathan@example.org',
    'phone_number': '001-666-514-0444',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Wayne Delacruz',
    'Christopher Swanson',
    'Mr. Michael Watkins',
    'Randy Taylor',
    'Melinda Michael',
    'Timothy Simmons',
],
    'json': {
    'name': 'Cynthia Vasquez',
    'address': '976 Chavez Mountain\nPort Gloriabury, NH 15359',
},
    'key88104': 'value48013',
    'key30969': 'value67034',
    'key23289': 'value25465',
    'key22532': 'value86528',
    'key31246': 'value29145',
    'key41507': 'value78461',
    'key23183': 'value47794',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Holly Moran',
    'address': '757 Wendy Street Apt. 013\nWilliamshaven, AL 59282',
    'text': 'Republican company theory least. Month game view happen.\nParticipant occur each imagine record. Street threat happy.',
    'email': 'robertsonpaul@example.org',
    'phone_number': '298.391.8672',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Black',
    'Maria Smith',
    'Debra Wolfe',
    'Kimberly Hawkins',
    'Timothy Martin',
    'Pamela Sullivan',
],
    'json': {
    'name': 'Linda Gates',
    'address': '65858 Kristen Dam Apt. 385\nJohnsonton, AZ 78582',
},
    'key26087': 'value62973',
    'key56391': 'value11204',
    'key69778': 'value16521',
    'key51227': 'value29671',
    'key93296': 'value55749',
    'key17467': 'value44202',
    'key99045': 'value96790',
    'key61810': 'value19213',
    'key64150': 'value16899',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Cody Gray',
    'address': '772 Jeremy Mission Apt. 634\nStaceyside, KS 50695',
    'text': 'Deal modern far include. Seek risk keep according approach put.\nProfessor gun financial. Decade they behind easy.',
    'email': 'odonnellmark@example.com',
    'phone_number': '001-549-429-5486x27646',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dana Taylor',
    'Phillip Cisneros',
    'Christina Newman',
],
    'json': {
    'name': 'Keith Ellis',
    'address': '557 Wendy Stravenue\nMarymouth, NY 40898',
},
    'key26059': 'value41394',
    'key88035': 'value53515',
    'key94341': 'value84614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Jermaine French',
    'address': '526 Jones Meadows Apt. 274\nNew John, FM 17712',
    'text': 'Soon safe series others. Executive image improve fire.\nThemselves accept thank treatment. Statement various must important responsibility rest. Answer hand treat this fund shake office.',
    'email': 'annandrews@example.org',
    'phone_number': '748-679-1668',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Moore',
    'Christina Sullivan',
    'David Williams',
    'Douglas Steele',
    'Tiffany Stanley',
],
    'json': {
    'name': 'Amy Hawkins',
    'address': '172 Kara Lock Suite 635\nPort Mirandamouth, KS 73388',
},
    'key91944': 'value42459',
    'key68655': 'value44932',
    'key2792': 'value90553',
    'key79804': 'value47316',
    'key49125': 'value12431',
    'key65313': 'value34390',
    'key66846': 'value43259',
    'key52757': 'value91339',
    'key25356': 'value57846',
    'key2260': 'value76470',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Jonathan Velazquez',
    'address': 'USNV Byrd\nFPO AA 38070',
    'text': 'Sport game letter Mrs whole. Across PM plant fall success save.\nLight can let eye six bank form. Know bill eat air sit together woman.',
    'email': 'rcollins@example.org',
    'phone_number': '328.452.4155x598',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Holly Lopez',
    'Tammy Hunt',
    'Mary Hill',
    'Leslie Cowan',
    'Christopher Wells',
    'Debra Mann',
    'Mr. Robert Smith',
    'Katelyn Gilmore',
    'Rachel Fitzpatrick',
    'Amanda Perry',
],
    'json': {
    'name': 'Shannon Wheeler',
    'address': 'PSC 3646, Box 9299\nAPO AP 46310',
},
    'key53246': 'value61535',
    'key1230': 'value85138',
    'key35768': 'value2130',
    'key69954': 'value29017',
    'key70091': 'value3295',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Alicia Myers',
    'address': '0975 Duane Meadows\nNorth Peter, CT 03529',
    'text': 'Most when continue management himself. Ok actually apply interest.\nWhom several here dream my store accept hand. Mouth rule likely important.',
    'email': 'lisa71@example.com',
    'phone_number': '(997)706-7340',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Robertson',
    'Elizabeth Lester',
    'Diana Adkins',
    'Frank Davies',
],
    'json': {
    'name': 'Michael Hoover',
    'address': '12999 Dyer Point\nBruceburgh, SC 38148',
},
    'key70870': 'value32297',
    'key55952': 'value37327',
    'key91310': 'value34459',
    'key71467': 'value27100',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Ms. Ashley Smith',
    'address': '9547 Paula Lane\nLake James, AL 27949',
    'text': 'War exactly agent run. Under doctor question agreement far. Person analysis industry main why.\nMinute activity what change. Party lead but sport back industry image. Join push three one board until.',
    'email': 'aarias@example.com',
    'phone_number': '9414978527',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Larsen',
    'Chad Williams',
    'Annette Pena',
    'Taylor Brown',
    'Jason Arnold',
    'Allison Nichols',
    'Frank Moore',
    'Marissa Johnson',
    'Chelsea Harris',
],
    'json': {
    'name': 'Raymond Bradley',
    'address': '160 Baker Forges Apt. 440\nSouth Joseph, PW 89767',
},
    'key14345': 'value38777',
    'key8934': 'value75215',
    'key67713': 'value5522',
    'key50169': 'value32673',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Jennifer Mcdonald',
    'address': '6217 Wilson Oval Suite 378\nLake Paulstad, ID 14549',
    'text': 'Its moment amount address anything rich event. Soldier decide serious population today. Wife necessary hand quickly into.\nOld conference business positive. Behavior challenge its guy.',
    'email': 'brittany36@example.org',
    'phone_number': '+1-699-285-4024x9220',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christina Bartlett',
    'Dana Murray',
    'Mrs. Jessica Wilson MD',
],
    'json': {
    'name': 'Lisa Fletcher',
    'address': '427 Sanchez Landing Apt. 141\nPort Heatherton, AS 75896',
},
    'key98006': 'value70223',
    'key16276': 'value66094',
    'key78835': 'value53152',
    'key47915': 'value52621',
    'key42959': 'value11124',
    'key54739': 'value1023',
    'key27140': 'value80404',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Terri Wood',
    'address': '641 Andrea Court\nReesetown, WA 81409',
    'text': 'Political speak official lay present campaign improve. After organization minute garden catch bar raise only.',
    'email': 'ustewart@example.com',
    'phone_number': '3909710432',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Brewer',
    'Rachael Copeland',
    'Andrew Lopez',
    'Alan King',
    'Justin Carter',
],
    'json': {
    'name': 'Antonio Chase',
    'address': '2640 Waller Shoal Suite 222\nEast Justin, MO 85658',
},
    'key45476': 'value57745',
    'key90430': 'value82169',
    'key89285': 'value17196',
    'key27582': 'value76488',
    'key7200': 'value33410',
    'key52299': 'value70475',
    'key93490': 'value13768',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Paula Edwards',
    'address': '02474 Rachel Hollow\nNew Kimberly, NC 43491',
    'text': 'Enough final affect interest science ask. Anything television total six up concern.',
    'email': 'christophermartin@example.com',
    'phone_number': '672-810-5989x99289',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Erin Kerr',
    'Lynn Ballard',
    'Cameron Lewis',
],
    'json': {
    'name': 'Jason Singleton',
    'address': '277 Beasley Knoll Suite 556\nBautistaside, CO 84215',
},
    'key28813': 'value98544',
    'key75756': 'value67884',
    'key783': 'value34598',
    'key63697': 'value52483',
    'key2391': 'value76026',
    'key48488': 'value10181',
    'key24673': 'value71527',
    'key64482': 'value49274',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Wanda Kelly',
    'address': '79703 Curtis Rapid\nEast Dennis, MD 16472',
    'text': 'Item property player kitchen score. Us science news vote exactly.\nAlone major yet market pressure. Understand under than tough. Chance deep could nearly value performance.',
    'email': 'cturner@example.com',
    'phone_number': '(227)399-7940x4212',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Robinson',
    'Nicholas White',
    'Pamela Webster',
    'Erica Lee',
    'Susan Johnson',
],
    'json': {
    'name': 'Sharon Larsen',
    'address': '5044 Gallegos Curve\nDyerview, MN 90186',
},
    'key82877': 'value3857',
    'key7023': 'value42352',
    'key48637': 'value77879',
    'key40677': 'value94378',
    'key96925': 'value16611',
    'key55118': 'value49605',
    'key68249': 'value43094',
    'key98490': 'value16447',
    'key97161': 'value89757',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Patricia Henderson',
    'address': '01454 Amanda Cliffs Suite 397\nRamirezfurt, MT 56697',
    'text': 'Crime year animal clear east fear. Public threat arrive place return right phone sit. The series name.\nSomething bar with expect among card education sea. Despite why his various note stop.',
    'email': 'alvaradorebecca@example.net',
    'phone_number': '463.413.1044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Brown',
    'Laura Galloway',
    'Tammy Burnett',
    'Amy Figueroa',
    'Jonathan Jackson',
    'Paul Leon',
    'Joseph Rodriguez',
    'Laura Foley',
    'Tammy Joseph',
    'Marvin Moore',
],
    'json': {
    'name': 'Tanya Salinas',
    'address': '3155 Chad Bypass\nBrianmouth, NV 01124',
},
    'key77545': 'value45694',
    'key55283': 'value22713',
    'key67788': 'value36813',
    'key99681': 'value67129',
    'key69130': 'value77487',
    'key93685': 'value27911',
    'key47634': 'value52852',
    'key97086': 'value19999',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'David Richardson',
    'address': '695 Garcia Viaduct Apt. 070\nSouth Jennifer, MD 20905',
    'text': 'Huge far all total long effect white. Leave they imagine international.',
    'email': 'nhunt@example.org',
    'phone_number': '436.792.5476x280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Brian Henderson',
    'Paul Williams',
    'Zachary Hamilton',
],
    'json': {
    'name': 'Laura Salas',
    'address': '21384 Delgado Crescent Apt. 705\nHallhaven, ME 15395',
},
    'key87718': 'value31012',
    'key29775': 'value8981',
    'key73260': 'value38937',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Robert Hall',
    'address': '030 Virginia Ridge\nMcdanielton, SD 40932',
    'text': 'Board rest author whole enjoy time. Describe back conference defense simple prepare. Institution behind together really wind general.',
    'email': 'mcgeemonica@example.com',
    'phone_number': '689.710.8971x549',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Bailey Hudson',
    'Patricia Hawkins DDS',
    'Madison Edwards',
    'Samuel Marsh',
    'Ryan Ferguson',
    'Dr. Robert Gordon Jr.',
    'Aaron David',
    'Anthony Morgan',
    'Sarah Kim',
],
    'json': {
    'name': 'Barbara Davis',
    'address': '499 Vargas Mills\nRebeccaberg, MA 85775',
},
    'key13425': 'value9207',
    'key76828': 'value36603',
    'key97047': 'value66152',
    'key2876': 'value88032',
    'key4117': 'value66570',
    'key94368': 'value6877',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Kathryn Roberts',
    'address': '71063 Jeffrey Wall Apt. 434\nEast Michaelhaven, IN 56707',
    'text': 'Buy institution decade. Possible attorney me. Process instead doctor speak environment.\nEast left environmental modern significant window six. Interview standard bring tough recognize strong.',
    'email': 'blackburnanthony@example.org',
    'phone_number': '+1-597-354-9014x245',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Connie Pierce',
    'Ryan Mccoy',
    'David Thomas',
    'Michael Townsend',
],
    'json': {
    'name': 'Sara Blair',
    'address': '8788 Timothy Way\nEast Rodney, GU 98869',
},
    'key73175': 'value51803',
    'key88433': 'value68643',
    'key99224': 'value50965',
    'key38373': 'value19204',
    'key85911': 'value88296',
    'key55053': 'value14160',
    'key90456': 'value37507',
    'key94168': 'value60227',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Sarah Austin',
    'address': '32186 Sarah Mill\nEast Katelyn, DC 04952',
    'text': 'Public manager seat soon. Learn south animal red. Hold either myself.\nProcess something last across. White least public scientist.',
    'email': 'williammccarthy@example.com',
    'phone_number': '462.528.4304',
    'array_int_dynamic': [
    88224,
],
    'array_varchar_dynamic': [
    'Brenda Pitts',
    'Anna Decker',
    'Justin Cunningham',
    'Maria Lynn',
    'Gail Mcguire DVM',
    'David Gomez',
    'Fernando Wheeler',
    'Jessica Diaz',
],
    'json': {
    'name': 'Brendan Jordan',
    'address': 'Unit 3005 Box 4617\nDPO AA 98657',
},
    'key66182': 'value48569',
    'key91529': 'value75783',
    'key48167': 'value59144',
    'key69761': 'value56775',
    'key49792': 'value93207',
    'key52941': 'value97237',
    'key73435': 'value82163',
    'key6909': 'value63075',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Javier Snyder',
    'address': '3023 Hall Club Suite 368\nJamestown, ID 49867',
    'text': 'Federal food different reason. Recent walk role stuff consider show us.\nWhole somebody east scene class story. Father onto go throughout.',
    'email': 'sthomas@example.com',
    'phone_number': '001-260-992-3178x536',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Adam Olson',
    'Kristin Harper',
    'Gwendolyn Robinson',
    'Amy Wilson',
],
    'json': {
    'name': 'Daniel Nichols',
    'address': '372 Jonathon Rapids Apt. 376\nEast Christina, GU 11836',
},
    'key98352': 'value88955',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Daniel Kelly',
    'address': '93892 Hughes Courts\nSouth Dustinville, UT 37161',
    'text': 'Particular activity pattern book executive onto.\nArea mind alone address who table rather. Page develop science teacher difference region leader. Herself respond pressure during improve kitchen PM.',
    'email': 'vlindsey@example.org',
    'phone_number': '(354)855-5766x771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jonathon Kelley',
    'Ronald Floyd',
    'Patricia Taylor',
    'Jennifer Baxter',
],
    'json': {
    'name': 'Melinda Serrano',
    'address': '445 Fischer Ranch Apt. 525\nNorrisshire, AZ 47817',
},
    'key69765': 'value34643',
    'key93351': 'value39065',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Michael Miller DDS',
    'address': '907 Kyle Groves\nDavistown, VT 93208',
    'text': 'Institution note she activity two mind somebody room. Lot unit care water itself. Market fine five surface process. Yet cut grow during necessary past available.\nAnything manage what law.',
    'email': 'trevor75@example.com',
    'phone_number': '001-293-558-5011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Stewart',
],
    'json': {
    'name': 'Timothy White',
    'address': '73289 Pratt Inlet Suite 927\nClarkfurt, TN 35267',
},
    'key7579': 'value18887',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Joseph Sheppard',
    'address': '458 Nathaniel Streets Apt. 714\nPort Dawnside, NE 56944',
    'text': 'Pm Democrat lawyer different remain less sign. Tough president describe hundred decade late.\nHot provide form. Very military under itself pick agent. Within hair he happy adult.',
    'email': 'allisonscott@example.com',
    'phone_number': '353-714-8302x75189',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Hernandez',
    'Willie Gregory',
    'John Jordan',
    'Randall Young',
    'Caitlin Wilson',
    'Calvin Gilbert',
    'Anita Shaffer',
    'Michael Gomez',
],
    'json': {
    'name': 'Aaron Fowler',
    'address': '7284 Alexandria Mews Suite 388\nHerrerafort, RI 78859',
},
    'key5689': 'value15842',
    'key85004': 'value6731',
    'key77950': 'value25606',
    'key7334': 'value62800',
    'key44226': 'value15462',
    'key59868': 'value82057',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Bradley Fernandez',
    'address': '089 Brandi Pines Suite 498\nJennifertown, MN 56306',
    'text': 'Ready stock doctor. Successful imagine behind usually whose. Moment oil recent pull may mean.',
    'email': 'emily89@example.org',
    'phone_number': '8377062331',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Frazier',
    'Cynthia Ewing',
    'Kelly Estrada',
],
    'json': {
    'name': 'Stephen Clark',
    'address': '39759 Tucker Union Apt. 027\nRobertchester, GA 24994',
},
    'key51682': 'value96364',
    'key51910': 'value74436',
    'key26686': 'value37601',
    'key96552': 'value25764',
    'key43940': 'value65832',
    'key31246': 'value95549',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Sara Gallegos',
    'address': '0037 Kara Burgs Suite 033\nGreentown, NY 06929',
    'text': 'Central right leader effect support.\nBar account program five hand evening. Bit entire learn that ever share. Relationship whole forward hit child once. General probably along clear present sign.',
    'email': 'jason27@example.com',
    'phone_number': '857-837-9218x14830',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Barr',
    'Jacob Williams',
    'Chris Vincent',
    'Tyler Barnes',
    'Alexander Carroll',
    'Kristy Stanton',
    'Micheal Baker',
],
    'json': {
    'name': 'Linda Sloan',
    'address': '3287 Hughes Union Suite 667\nVeronicafurt, WA 23117',
},
    'key78819': 'value51823',
    'key10131': 'value78838',
    'key516': 'value59349',
    'key80061': 'value89867',
    'key55120': 'value7479',
    'key37734': 'value25437',
    'key99010': 'value64549',
    'key84973': 'value48001',
    'key80325': 'value50082',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Judith Clark',
    'address': '1896 Obrien Circles\nWest Mariahville, IL 86578',
    'text': 'Laugh behind five number red agreement. Since understand drug visit discover lose story.\nHold create then help policy such keep.',
    'email': 'sullivanpatricia@example.com',
    'phone_number': '515.222.1112',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Donna Hanna',
    'Heather Thompson',
    'Rebecca Gonzales',
],
    'json': {
    'name': 'Thomas White',
    'address': '82574 Kristen Harbors Apt. 134\nMillershire, IA 63057',
},
    'key96148': 'value16010',
    'key4371': 'value42136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Heather Hale',
    'address': '9929 Christina Fork\nAmandaborough, NE 76229',
    'text': 'Statement new almost leave benefit one language. Enough sell front enjoy system would for.\nCharge my team position player. Difference accept fact support federal likely.',
    'email': 'rachelcohen@example.org',
    'phone_number': '+1-413-343-0842x23802',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Smith',
    'Tammy Lowe',
    'Austin Mckee',
    'Rebekah Davis',
    'Rachel Garcia',
    'Jerry Fernandez',
    'Troy Greer',
],
    'json': {
    'name': 'Natasha Hernandez',
    'address': '027 Mason Oval Apt. 730\nEast Dawnshire, WI 27091',
},
    'key21768': 'value58295',
    'key96185': 'value208',
    'key37847': 'value1533',
    'key23309': 'value15892',
    'key81149': 'value13346',
    'key43463': 'value96560',
    'key14834': 'value58512',
    'key87207': 'value20092',
    'key95120': 'value37435',
    'key25577': 'value72977',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Reginald Williams',
    'address': '7884 Harrington Plaza Suite 224\nSouth Christina, AS 11984',
    'text': 'Ask hair focus have natural chance. Here through vote source own start get. Part nice eat land nor.\nPart will field. None process stand share.',
    'email': 'rgonzalez@example.org',
    'phone_number': '709.898.5741',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Phillips',
    'Paige Rowe',
    'James Hamilton',
    'Brian Hayden',
    'Steven Roberts',
    'John Martinez',
],
    'json': {
    'name': 'Paul Jones',
    'address': '83762 Daniel Keys\nLake Lisa, PW 46008',
},
    'key91244': 'value9944',
    'key90141': 'value11384',
    'key81945': 'value31482',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Steven Robinson',
    'address': '552 Reyes Keys\nNorth Davidport, SD 00644',
    'text': 'One alone establish. Vote visit water peace.\nReflect talk himself fine region sing.\nName even western race. Avoid else claim reach add.',
    'email': 'brightricky@example.org',
    'phone_number': '991.334.0765',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David Young',
    'Erin Rodriguez',
    'Christine Daugherty',
    'Christine Woods',
    'Nathan Greene',
],
    'json': {
    'name': 'Theresa Jones',
    'address': '7475 Myers Oval Apt. 795\nSouth Rachelbury, AK 07598',
},
    'key79224': 'value49238',
    'key82551': 'value35394',
    'key86497': 'value97402',
    'key38038': 'value50989',
    'key58043': 'value27784',
    'key49456': 'value21640',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Jerry Peters',
    'address': '4248 Arnold Groves Apt. 353\nSouth Garyport, OR 06320',
    'text': 'Single really this manager inside sure. Institution good board interest serve series. Strategy ability show situation late significant resource.',
    'email': 'davidcook@example.net',
    'phone_number': '+1-560-219-1757x97093',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tom Spears',
    'Michael Watson',
],
    'json': {
    'name': 'Lorraine Lopez',
    'address': '89824 Felicia Square Suite 680\nKleinburgh, FL 26472',
},
    'key68644': 'value58034',
    'key58284': 'value41707',
    'key78057': 'value19235',
    'key94118': 'value51306',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Jamie Rose',
    'address': '613 Angela Neck\nWest Jessica, GU 45054',
    'text': 'Medical offer industry office feel. Surface manage sign road strong. Modern upon physical know population seek. Rest send trouble beat toward author.',
    'email': 'wgray@example.com',
    'phone_number': '536-999-8234',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Sara Figueroa',
    'Timothy Davis',
],
    'json': {
    'name': 'Ruben Davis',
    'address': '910 Martin Squares Apt. 215\nJamesmouth, HI 36472',
},
    'key68277': 'value61145',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Robert Gutierrez',
    'address': '10415 Sara Skyway Suite 090\nNicholaschester, NE 36386',
    'text': 'Worry southern meet artist. Season field heart against now describe politics. Account activity cut fact inside power during.\nMessage newspaper pull by door. For back push.',
    'email': 'gordonlaura@example.net',
    'phone_number': '+1-374-208-1930x518',
    'array_int_dynamic': [
    27439,
],
    'array_varchar_dynamic': [
    'Gabriela Page',
    'Angela Gutierrez',
    'Bryan Sanders DDS',
    'Lauren Morrison',
    'Alexis Ashley',
    'Amanda Morris',
    'Tabitha Powell',
    'Megan Rollins',
    'John Shepherd',
    'Michael Smith',
],
    'json': {
    'name': 'Ronald Bailey',
    'address': '292 Harrison Streets Suite 779\nNorth Meghanland, CT 22003',
},
    'key98940': 'value35823',
    'key50163': 'value44441',
    'key62802': 'value2910',
    'key46213': 'value89925',
    'key20842': 'value7575',
    'key94160': 'value37275',
    'key61571': 'value19193',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'William Lucas',
    'address': '58580 Lisa Track\nSmithstad, MP 15479',
    'text': 'Agent reduce yet possible outside series she. Look strong international receive.\nDefense response two former stuff shoulder drop. Move take government.',
    'email': 'alan23@example.org',
    'phone_number': '(275)929-7096x7795',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Perez',
    'Jeffrey Jackson',
],
    'json': {
    'name': 'Regina Pennington',
    'address': '68133 David Oval Apt. 775\nHayeschester, NY 08927',
},
    'key15861': 'value49678',
    'key78325': 'value58185',
    'key17805': 'value63329',
    'key38460': 'value68619',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Stacey Mcdonald',
    'address': '671 Price Station\nGomezland, IL 67309',
    'text': 'Industry difficult with particular. Word ahead happy involve play direction century.\nMeet win expect sort. Opportunity trial experience. Tax fact buy region.',
    'email': 'jacksonjonathan@example.com',
    'phone_number': '904.315.6045x530',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Malik Coleman',
    'Mrs. Deborah Wong',
    'Bradley Wang',
    'Aaron Brown',
    'Anna Nichols',
],
    'json': {
    'name': 'Brendan Thompson',
    'address': '08104 Mark Keys\nPort Jamestown, AR 36019',
},
    'key64782': 'value2847',
    'key82295': 'value30151',
    'key68559': 'value59889',
    'key2121': 'value41012',
    'key88087': 'value92264',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Juan Brown',
    'address': '6845 Williams Hills\nEast Scott, VI 26497',
    'text': 'Skill skill still affect tough born. Yet war feeling model shoulder partner age common.',
    'email': 'nbrown@example.org',
    'phone_number': '448-835-9704x500',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Cuevas',
    'Tracy Adams',
],
    'json': {
    'name': 'Steven Reid',
    'address': '8467 Amy Corner\nWhitneyberg, OR 37642',
},
    'key82959': 'value65797',
    'key91416': 'value11917',
    'key71329': 'value14902',
    'key89728': 'value41508',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Daniel Cole',
    'address': '05019 Haynes Creek Suite 820\nTracytown, WY 51996',
    'text': 'It room beat again strategy.\nFly couple world between today. Summer wrong including hand focus future region political. Around current leave likely government.',
    'email': 'riosbenjamin@example.com',
    'phone_number': '597-790-0393x98871',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Brown',
    'Angela Crawford',
    'Carla Spencer',
    'Joseph Collins',
    'Matthew Perez',
    'Elaine Ortiz',
],
    'json': {
    'name': 'Ryan Sanchez',
    'address': '741 Sims Lodge Suite 636\nDavisbury, DE 18706',
},
    'key99789': 'value58724',
    'key56152': 'value18438',
    'key13719': 'value60887',
    'key14558': 'value47761',
    'key48469': 'value12352',
    'key87006': 'value76599',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Jennifer Schneider',
    'address': '304 Kristen Trace Suite 769\nNorth Deborah, HI 41591',
    'text': 'Arm rule detail camera white enjoy those skill.\nImagine save night member hair world interesting. Fly executive security any.',
    'email': 'jacquelinesanchez@example.org',
    'phone_number': '(333)592-5776x439',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Valencia',
    'Morgan Hughes',
    'Aaron Gray',
    'Jamie Lopez',
    'Joseph Martinez',
    'Patricia Farmer',
    'William Solomon',
],
    'json': {
    'name': 'Lauren Brown',
    'address': '658 Robin Trail\nSouth Frank, NV 45238',
},
    'key78410': 'value79434',
    'key94465': 'value19581',
    'key74728': 'value71552',
    'key24627': 'value3226',
    'key25641': 'value32208',
    'key4798': 'value49256',
    'key72647': 'value26487',
    'key50987': 'value33211',
    'key42248': 'value95440',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Erica Zavala',
    'address': '58959 Kelly Curve\nLake Mark, CA 62773',
    'text': 'Range try take democratic magazine which. During star history author.\nRange article old though. Big impact war. Box despite itself. Form teach bed exactly network among.',
    'email': 'vkirby@example.com',
    'phone_number': '9018103078',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Willie Gardner',
    'Tiffany Elliott',
],
    'json': {
    'name': 'Juan Mccoy',
    'address': '009 Smith Underpass Apt. 906\nTimothyshire, FL 07609',
},
    'key48378': 'value16293',
    'key5604': 'value57775',
    'key91166': 'value11020',
    'key69450': 'value95296',
    'key59980': 'value23843',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Gabrielle Bennett',
    'address': '984 Jimenez Ville\nGregoryland, MP 12662',
    'text': 'Report store for take debate hospital. Thought language partner something city rock.\nGeneration doctor quickly daughter themselves church. System across art one provide but speak leader.',
    'email': 'mark77@example.com',
    'phone_number': '001-224-651-8603x34922',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Yvonne Jones',
    'Julie Archer',
    'Vicki Marshall MD',
    'Joshua Moore',
    'Vicki Robinson',
    'George Allen',
    'Gina Miller',
    'Elizabeth Rodriguez',
    'Vanessa Smith',
],
    'json': {
    'name': 'Robert Lewis',
    'address': '0623 Jeffrey Branch Suite 770\nHarveychester, MA 88853',
},
    'key11217': 'value79967',
    'key82901': 'value31542',
    'key548': 'value40753',
    'key31759': 'value58641',
    'key34182': 'value36014',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Eric Melton',
    'address': '0020 Bishop Port\nSloanbury, OR 68815',
    'text': 'Onto seat century choice use defense. Never realize wide lead better maybe newspaper.\nStation old well. Art ready not window accept thought TV. Power all industry reveal customer.',
    'email': 'lynn12@example.com',
    'phone_number': '(518)694-0972x964',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Melanie Burns',
    'Paula Galvan',
    'Shawn Foley',
],
    'json': {
    'name': 'Jean Perry',
    'address': '882 Perez Manor\nLake Tonishire, RI 92417',
},
    'key56140': 'value52965',
    'key52058': 'value97191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Gina Martin',
    'address': '79914 Kathleen Burgs\nRobertton, AR 72406',
    'text': 'Big with reflect represent win person. Teach role fund own.\nVery central personal different moment name foreign. You idea ahead all room laugh seem. Wide fund lot hard range.',
    'email': 'michaelwilliams@example.org',
    'phone_number': '+1-725-273-6641',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Vickie Williams',
    'Zachary Hall',
],
    'json': {
    'name': 'Joseph Phillips',
    'address': '6151 Mason Mission\nJenkinsstad, MD 50067',
},
    'key85977': 'value37620',
    'key94114': 'value770',
    'key36820': 'value67580',
    'key59579': 'value49545',
    'key2779': 'value17982',
    'key70636': 'value68451',
    'key55708': 'value74800',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Michael Melton',
    'address': '950 Kristi Curve\nOwensfurt, VI 09577',
    'text': 'Political candidate during. Civil leave safe service someone PM exist bring.\nPrevent suggest management bank successful movie eight per. Table hold her last defense.',
    'email': 'brooksisaac@example.net',
    'phone_number': '+1-760-772-6334x78214',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Brian Clark',
    'Elizabeth Huff',
    'Stacey Baker',
    'Thomas Strickland',
    'Tracey Taylor',
    'Mary Joseph',
    'Alisha Johnston',
],
    'json': {
    'name': 'April Wilson',
    'address': 'Unit 9021 Box 7127\nDPO AE 07011',
},
    'key57656': 'value95951',
    'key48572': 'value81371',
    'key35066': 'value65350',
    'key68980': 'value35373',
    'key55507': 'value17255',
    'key33253': 'value2410',
    'key39352': 'value46116',
    'key62460': 'value58706',
    'key41678': 'value380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Mary Howard',
    'address': '57690 Bell Locks Suite 191\nSmithfort, NJ 76628',
    'text': 'Hundred test difference travel including bad. Score per spend front.\nDaughter page best of expect trip new. Truth actually party adult behavior.',
    'email': 'lee35@example.org',
    'phone_number': '373-470-0266',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Riley Salas',
    'Joshua Wright',
    'Amy Green',
    'Debra Moore PhD',
    'James Humphrey',
    'Elizabeth Nunez',
    'Daniel Singh',
    'James Harper',
    'Vicki Thomas',
],
    'json': {
    'name': 'Caitlyn Stark',
    'address': '447 Gregory Villages\nVillastad, FM 93156',
},
    'key36423': 'value255',
    'key73577': 'value11264',
    'key8865': 'value30176',
    'key70629': 'value43820',
    'key15542': 'value91630',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Melissa Pena',
    'address': '01895 Monica Run\nNew Sharonville, AK 53538',
    'text': 'Throughout everybody level system project figure bar. He animal continue wide play discussion. College Democrat traditional great marriage wonder.',
    'email': 'mariahughes@example.org',
    'phone_number': '847-979-4138',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Solis',
    'John Rogers',
    'Christina Tate',
    'Jessica Walker',
    'Darin Huff',
],
    'json': {
    'name': 'Glenn Reyes',
    'address': '681 Christina Union Suite 881\nNorth Vanessaton, MT 51926',
},
    'key65486': 'value70679',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Valerie Haley',
    'address': 'USCGC Hudson\nFPO AE 45610',
    'text': 'She amount herself meeting writer she method. Just through sea project.\nOnto sport agreement table. Forward sea close reduce. Book performance for shake food enter leg.\nDeep your outside several he.',
    'email': 'howellkristin@example.net',
    'phone_number': '001-304-853-8189x6253',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Jones',
    'Jennifer Rogers',
    'Sean Williams',
    'Donna Logan',
    'Ms. Brandy Flores',
    'Robert Terry',
    'Jaclyn French',
    'Joseph Martinez',
],
    'json': {
    'name': 'Autumn Hernandez',
    'address': '722 Solomon Estate\nJulieshire, NH 58620',
},
    'key39791': 'value88799',
    'key20102': 'value18294',
    'key32806': 'value26625',
    'key89747': 'value3853',
    'key81549': 'value74256',
    'key54443': 'value54021',
    'key28990': 'value51493',
    'key7881': 'value32259',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Joshua Spencer',
    'address': '173 Jones Shore\nMaryfurt, FM 43311',
    'text': 'Wish out foreign girl color eye. Bad six team feel.\nItself share agreement effect the discuss. Far finish drop television may. It boy green live bill major hair.',
    'email': 'hollowayricardo@example.org',
    'phone_number': '(774)913-2116x5573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Turner',
    'Jennifer Bradshaw',
    'Jennifer Williams',
    'Mark Potter',
    'Elizabeth Olson',
    'Gary Richardson',
],
    'json': {
    'name': 'Richard Osborne',
    'address': '652 William Walks\nEast Lisa, ID 17428',
},
    'key10287': 'value56430',
    'key83586': 'value70377',
    'key81352': 'value15190',
    'key62049': 'value41187',
    'key67234': 'value42122',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Kristen Cox',
    'address': '31429 Bell Field Suite 907\nEast Jameschester, LA 14501',
    'text': 'Mean PM pretty. Hospital civil grow interest near. Matter list dream size month clear agreement.\nGroup them scientist enter. Likely most candidate tend. Fear exist whose reduce open appear.',
    'email': 'rodrigueznicole@example.org',
    'phone_number': '749.212.9214',
    'array_int_dynamic': [
    9970,
],
    'array_varchar_dynamic': [
    'Sean Stewart',
    'Chad Pacheco',
    'Jessica Campbell',
    'Diana Phillips',
    'Sean Bailey',
    'Edward Morales',
    'Miguel Collins',
    'Kelly Howard',
    'Christopher Rodriguez',
],
    'json': {
    'name': 'David Marshall',
    'address': '038 Sellers Forge Apt. 405\nSouth Nicole, SC 11197',
},
    'key53886': 'value31146',
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
    'RequestId': '46ac9a37-62f1-11f0-b741-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_33_798339UWqQwkjW',
    'filter': 'uid in [1,2,3,4]',
    'limit': 100,
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
    'RequestId': '474ab22c-62f1-11f0-9cb1-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_33_798339UWqQwkjW',
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
    'RequestId': '3ff28764-62f1-11f0-9d3d-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_33_798339UWqQwkjW',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid in [1,2,3,4]]_1752744887.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUidIn12341752744887Json()
    test.run_tests()
