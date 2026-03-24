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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-100-2]_1752744195_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-100-2]_1752744195.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId12810021752744195Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-100-2]_1752744195.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-100-2]_1752744195.json"
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
    'RequestId': 'aadc3cd3-62ef-11f0-8ffd-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_14_175023kmBnywSI',
    'dimension': 128,
    'primaryField': 'id',
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
    'RequestId': 'ab00b54c-62ef-11f0-b22a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_14_175023kmBnywSI',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Tanner Bennett',
    'address': '89917 Jeffery Lake Suite 734\nVargasberg, MS 27502',
    'text': 'Organization our owner also. Determine during something arm raise move.\nNor husband single hair produce cause.\nSome able whether year. Pattern degree analysis. Study democratic surface put when.',
    'email': 'laura11@example.com',
    'phone_number': '001-835-760-6657x2249',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brad Reed',
    'Holly Beltran',
    'Rachel Becker',
    'Lori Logan',
    'Shannon Hall',
],
    'json': {
    'name': 'Nicholas Kirby',
    'address': '041 Johnston Freeway\nNew Steven, UT 21339',
},
    'key99013': 'value96833',
    'key2539': 'value1742',
    'key37787': 'value97053',
    'key21935': 'value94506',
    'key95928': 'value75149',
    'key82564': 'value30784',
    'key31685': 'value37274',
    'key57711': 'value58532',
    'key71998': 'value5436',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Joseph Wilson',
    'address': '61480 Aaron Tunnel\nCraigport, GU 10520',
    'text': 'Everyone agency key three quite. Base although black example four.\nDrug house sometimes hour name choose. These to consumer director. Good government table camera little professional.',
    'email': 'rayedward@example.org',
    'phone_number': '+1-945-767-4910',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Watson',
],
    'json': {
    'name': 'Caleb Ward',
    'address': '88810 Davies Crest\nDeborahside, WA 87183',
},
    'key3204': 'value9626',
    'key57761': 'value8049',
    'key63389': 'value41349',
    'key91810': 'value4334',
    'key74053': 'value99230',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Dr. Anita Cummings',
    'address': '750 Flores Mission\nNelsonmouth, HI 18022',
    'text': 'Should above order we physical kitchen. Source race technology.\nTrade story star article. Tonight economy key. Consumer safe value tell executive third toward much.',
    'email': 'xfrazier@example.org',
    'phone_number': '751.331.5017',
    'array_int_dynamic': [
    25552,
],
    'array_varchar_dynamic': [
    'Cassandra Fleming',
],
    'json': {
    'name': 'Sabrina Turner',
    'address': '8049 Alice Vista\nPricemouth, IN 57768',
},
    'key91563': 'value5846',
    'key11864': 'value14969',
    'key41363': 'value40264',
    'key2220': 'value5511',
    'key84892': 'value29597',
    'key11221': 'value32952',
    'key82698': 'value38740',
    'key94639': 'value86207',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jacob Smith',
    'address': '397 Reynolds Locks Suite 443\nKingchester, AS 46685',
    'text': 'Individual animal air foot number data answer.\nWear authority require person father another into live.',
    'email': 'phillipsdeborah@example.net',
    'phone_number': '(415)623-2779x7076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Colin Romero',
    'Lucas Watson',
    'Pamela Cohen',
    'Angela Tyler',
    'Jeremy Hill',
    'Brian Holmes',
    'Evelyn Guzman',
    'Jessica Kelly',
],
    'json': {
    'name': 'Carlos Jordan',
    'address': '2785 Washington Garden Suite 872\nRayhaven, UT 08141',
},
    'key69552': 'value35438',
    'key18131': 'value66322',
    'key639': 'value67467',
    'key46851': 'value88701',
    'key75362': 'value34670',
    'key56662': 'value25377',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Brian Richards',
    'address': '0360 Wilson Park Apt. 352\nDaviston, NY 80020',
    'text': 'Green operation home cup team according. Nation evidence western enough all kind character.',
    'email': 'allen02@example.org',
    'phone_number': '999.426.6171x3983',
    'array_int_dynamic': [
    34665,
],
    'array_varchar_dynamic': [
    'Brian Schultz',
    'Jeremy Nguyen',
    'Alexis Berg',
    'Heather Gonzales',
    'Marcus Shaw',
    'Chad Rodriguez',
],
    'json': {
    'name': 'Erik Cochran',
    'address': '233 Robert Port Apt. 351\nSouth Kellyport, PW 32700',
},
    'key84840': 'value79797',
    'key73286': 'value23966',
    'key82203': 'value49615',
    'key16689': 'value38648',
    'key25304': 'value73555',
    'key64606': 'value77309',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Wayne Shaw',
    'address': '2286 Hampton Path Apt. 282\nLake Charles, IN 03078',
    'text': 'History camera newspaper first study. Offer onto leader doctor main concern according.\nClose whether toward office nature. Worry soldier successful.',
    'email': 'vanessa47@example.net',
    'phone_number': '+1-752-352-8619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Maria Ramirez',
    'Jaime Harris',
    'Jennifer Stewart',
],
    'json': {
    'name': 'Christopher Wong',
    'address': '601 Carrie Freeway Apt. 782\nDennisland, WA 71670',
},
    'key85526': 'value92067',
    'key13226': 'value76653',
    'key65025': 'value8798',
    'key44146': 'value51309',
    'key67137': 'value40890',
    'key45922': 'value72325',
    'key14715': 'value67951',
    'key62369': 'value38671',
    'key54625': 'value82542',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Carol Edwards',
    'address': '07090 Solomon Hills Suite 253\nMcdanielbury, RI 57009',
    'text': 'Course speak his list. Wait day memory whatever popular whose. Floor in fast read Mr.\nDrop total always consumer. Statement play everything same. West senior color election involve enough art agency.',
    'email': 'qrodriguez@example.org',
    'phone_number': '(723)397-4668x119',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Ortiz',
    'Ronald Ross',
    'Ms. Holly Crawford MD',
    'John Jennings',
    'Todd Young',
    'Maria Rodriguez',
    'Jennifer Gibbs',
    'John Gonzalez',
    'Sharon Buchanan',
],
    'json': {
    'name': 'Brian Hardin',
    'address': '9747 Timothy Rue Suite 042\nCollinsland, MS 57726',
},
    'key15409': 'value23825',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Alexander Jones',
    'address': '854 Melanie Curve\nEstradaport, SC 19192',
    'text': 'Inside idea stay during various main only. This help would federal. Expert your word if national later even.',
    'email': 'larry32@example.net',
    'phone_number': '(669)462-6631',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michele Owens',
    'Kathy Roberts',
    'John Butler',
    'Tina Hunt',
    'Helen Ellis',
    'Robert Johnson',
],
    'json': {
    'name': 'Bruce Anderson',
    'address': '8943 Bowers Rest Apt. 724\nRhondaland, AL 81311',
},
    'key38603': 'value49748',
    'key44929': 'value21116',
    'key2565': 'value28125',
    'key53143': 'value49853',
    'key22168': 'value18028',
    'key84627': 'value55390',
    'key52230': 'value82854',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Robert Henry',
    'address': '694 Adam Isle Apt. 823\nPort Peter, WA 57967',
    'text': 'Issue course scientist in.\nLikely similar hundred member seek.\nDevelop mention three. Tax mind within school six. Else will entire throughout sure stand.',
    'email': 'rachel04@example.net',
    'phone_number': '001-921-884-5550x5208',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Johnson',
    'Joseph Bennett',
    'Amanda Russell',
    'Douglas Young',
    'William Murphy',
    'Lauren Hawkins',
    'Cathy Stanley',
    'Christopher Johnson',
],
    'json': {
    'name': 'Gregory Ford',
    'address': 'USNV Fletcher\nFPO AA 00968',
},
    'key50376': 'value33167',
    'key24625': 'value4725',
    'key33480': 'value8259',
    'key59333': 'value30602',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Tracey Silva',
    'address': '575 Karen Haven Suite 776\nAlanburgh, MH 30852',
    'text': 'Although level state. Drug own stock easy space political economic. Medical conference look.\nAffect heavy student. Surface wear manage serve. Case buy about.',
    'email': 'joshua48@example.org',
    'phone_number': '+1-419-930-1144x0151',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Justin Henry',
],
    'json': {
    'name': 'Patrick Smith',
    'address': '08658 Rodriguez Lock\nScottborough, CA 40261',
},
    'key77853': 'value41251',
    'key60063': 'value80326',
    'key81859': 'value1686',
    'key11886': 'value34332',
    'key62603': 'value20073',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Devin Hayes',
    'address': '44646 Meyer Union\nBaxtermouth, TX 49033',
    'text': 'Want bad dark a lot let. Fill task really real movement. Budget human find.\nVote through now analysis collection democratic his. Effort save since market just rule whom.',
    'email': 'goodwinnancy@example.org',
    'phone_number': '603.864.1099',
    'array_int_dynamic': [
    26961,
],
    'array_varchar_dynamic': [
    'James Lawson',
    'Tracy West',
],
    'json': {
    'name': 'Calvin Keller',
    'address': '1032 Larson Dale Suite 094\nNew Markbury, MA 12233',
},
    'key24820': 'value30396',
    'key57694': 'value31784',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Gary Hensley',
    'address': '0514 Alexander Drive\nLopeztown, MS 18934',
    'text': 'Clearly finally necessary officer strategy service. Prevent plant bill.',
    'email': 'stevensbrian@example.org',
    'phone_number': '001-377-226-7674x702',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Chad Horton',
    'David Gardner',
],
    'json': {
    'name': 'George Mitchell',
    'address': '758 Charles Creek\nLake Ericaland, AZ 02252',
},
    'key89889': 'value99875',
    'key70506': 'value25619',
    'key64627': 'value21562',
    'key41240': 'value66616',
    'key61460': 'value71421',
    'key11935': 'value40934',
    'key18088': 'value57529',
    'key56543': 'value78123',
    'key57483': 'value70010',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Joseph Hicks',
    'address': '467 Marc Crossing\nRobinsonberg, AR 76939',
    'text': 'Military order likely discuss all here. Individual lot station child road. Common add speech truth summer.',
    'email': 'ufaulkner@example.org',
    'phone_number': '+1-774-923-0859',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jade Prince',
    'Travis Gomez',
    'Travis Davies',
    'Chris Freeman',
    'Andrea Mejia',
    'Nancy Mueller',
    'Mr. John House',
    'Kimberly Young',
    'James Miller',
    'Dr. Carl Turner',
],
    'json': {
    'name': 'Monica Fields',
    'address': '139 Wilkinson Springs Suite 763\nBrewerton, MP 66963',
},
    'key85579': 'value19571',
    'key23317': 'value95415',
    'key25150': 'value31125',
    'key1324': 'value3735',
    'key73134': 'value36088',
    'key36588': 'value3269',
    'key64600': 'value47254',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Ana Hawkins',
    'address': '0238 Klein Crest\nWest Tinafort, MH 41256',
    'text': 'Nation event draw. War system very try I fine alone. Star current there against cost.\nBetween difficult out speak particularly few eat then. Key change of of.',
    'email': 'ijohnson@example.net',
    'phone_number': '855-723-3313x39413',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Noah Brown',
    'Tricia Dunn',
    'Timothy Nelson',
    'Leah Carter',
    'David Bennett',
],
    'json': {
    'name': 'Matthew Carpenter',
    'address': '626 Bryan Spring\nNicolefurt, NV 12866',
},
    'key25007': 'value26550',
    'key64134': 'value63967',
    'key8242': 'value96513',
    'key46589': 'value89806',
    'key18011': 'value6622',
    'key18581': 'value66571',
    'key45502': 'value49982',
    'key9248': 'value19015',
    'key92173': 'value85096',
    'key63925': 'value18598',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Scott Raymond',
    'address': 'USNS Morgan\nFPO AP 35176',
    'text': 'Anyone realize standard message although occur relate. Them notice north central shake chair good experience.',
    'email': 'jessicathompson@example.com',
    'phone_number': '001-265-305-4750x19800',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lori Harris',
    'Destiny Sullivan',
    'James Watson',
    'Mrs. Shannon Cuevas DVM',
    'Brianna Pitts',
    'Shawn Hernandez',
    'Joshua Velasquez',
    'Daniel Ortiz',
    'Mikayla Hernandez',
],
    'json': {
    'name': 'Jodi Middleton',
    'address': '05751 Gonzalez Landing\nFullerfort, PA 18864',
},
    'key51699': 'value30817',
    'key91381': 'value8908',
    'key52187': 'value92566',
    'key33661': 'value95110',
    'key68623': 'value76169',
    'key41225': 'value61043',
    'key48230': 'value21989',
    'key15740': 'value25735',
    'key87995': 'value42618',
    'key68068': 'value87423',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Michael Figueroa',
    'address': '609 Gregory Landing Suite 965\nJohnland, NJ 22316',
    'text': 'Piece serious interview argue commercial agree kid executive. Present health establish office local.',
    'email': 'andrewnunez@example.org',
    'phone_number': '001-909-224-5689x2421',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Woods',
    'Brandy Mora',
    'Joshua Lang',
],
    'json': {
    'name': 'Steven Fernandez',
    'address': '9584 Jessica Highway\nJimmyview, GU 92171',
},
    'key5302': 'value29818',
    'key24139': 'value35933',
    'key86573': 'value11867',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Alyssa Johnson',
    'address': '831 Joshua Plains Apt. 860\nLake Maryview, KS 16571',
    'text': 'Necessary difference that image method woman seat. Check new federal support.\nPerform simple fill discover officer find. Our compare consumer type recognize.',
    'email': 'yorkanna@example.org',
    'phone_number': '001-651-619-7878',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Isaac Cooper',
    'Gabriel Anderson',
],
    'json': {
    'name': 'Kristi Conner',
    'address': '74087 Miller Keys Suite 802\nLake Christinaside, MH 18043',
},
    'key56348': 'value80193',
    'key96372': 'value33106',
    'key39116': 'value48482',
    'key49683': 'value39289',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Krista Wheeler',
    'address': '4988 Chase Crescent Apt. 027\nEast Shannon, KS 39098',
    'text': 'Her girl plan. Collection within employee follow hundred. Class player yeah final language.\nFoot health side. Else occur resource get something trial across.',
    'email': 'woodsandy@example.net',
    'phone_number': '444.828.4199x22408',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Michael Moss II',
    'Vincent Hale',
    'Lauren Clarke',
    'Bryan Nguyen',
],
    'json': {
    'name': 'Erin Johnson',
    'address': '5083 Michael Hills Apt. 851\nEast Edgar, OR 53385',
},
    'key68288': 'value51648',
    'key49836': 'value68899',
    'key60321': 'value20755',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Austin Lopez',
    'address': 'USCGC Clark\nFPO AA 84624',
    'text': 'Say result learn physical forward.\nStandard rather fear believe someone make school. Still past whom year. Medical physical mention TV.',
    'email': 'pkelley@example.com',
    'phone_number': '358.241.7411',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Donna Rivera',
],
    'json': {
    'name': 'Brett Nunez',
    'address': '898 Chase Villages Suite 152\nChristineville, TX 33882',
},
    'key37845': 'value27917',
    'key91645': 'value83020',
    'key83677': 'value30324',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Angela Preston',
    'address': 'USCGC Burns\nFPO AE 23013',
    'text': 'Lawyer drive social soldier street tough space your. Father hour people save.\nSuddenly pay already represent do bag. Read another military threat situation later.',
    'email': 'andre21@example.com',
    'phone_number': '+1-301-754-8254x95296',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Hogan',
    'Lisa Walker',
],
    'json': {
    'name': 'Richard Carter',
    'address': '90026 Crystal Estates\nLake Pattytown, LA 62875',
},
    'key62919': 'value66628',
    'key71856': 'value81248',
    'key60527': 'value39373',
    'key10733': 'value24078',
    'key31991': 'value92690',
    'key3549': 'value81580',
    'key4595': 'value94989',
    'key56809': 'value9061',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Daniel Holland',
    'address': '039 Keller Knoll\nCarlosfort, DE 97403',
    'text': 'Can cover many religious.\nEstablish institution develop head seek ball. Collection next purpose note strategy same receive environmental. Still cultural decide true.',
    'email': 'susan17@example.com',
    'phone_number': '(537)422-1192',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Paula Oconnor',
    'Timothy Soto',
    'Deborah Harris',
    'Lorraine Smith',
    'Michaela Everett',
    'Barry White',
    'Teresa Bates',
    'Courtney Lowe',
    'Tara Peck',
    'Meredith Nguyen',
],
    'json': {
    'name': 'Jacqueline Moreno',
    'address': '185 Gallegos Extension Apt. 909\nLaurieton, IL 40300',
},
    'key18725': 'value739',
    'key29807': 'value85739',
    'key68245': 'value34727',
    'key4563': 'value38392',
    'key24572': 'value31846',
    'key58181': 'value5243',
    'key84236': 'value91785',
    'key12247': 'value1128',
    'key74062': 'value30623',
    'key82513': 'value98001',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Robin Allen',
    'address': '77052 Crawford Highway Apt. 913\nRhondafurt, DC 83087',
    'text': 'Fight pretty American physical home these. Those skin year send hour book gas. Mouth usually somebody impact project exactly top.',
    'email': 'ochoajorge@example.net',
    'phone_number': '619.876.3862x623',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amber Ross',
    'Mindy Murray',
    'Nicholas Hickman',
    'Mark Hamilton',
    'Steven Perez',
    'Leonard Hoffman',
],
    'json': {
    'name': 'Alexander Clements',
    'address': '7688 Nicholas Knoll\nSherrytown, AK 29842',
},
    'key3142': 'value91553',
    'key32028': 'value7287',
    'key41919': 'value44379',
    'key17353': 'value61318',
    'key10109': 'value31688',
    'key96894': 'value18720',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Kathleen Vargas',
    'address': '948 Dudley Rapid\nPort Nicoleport, VA 23966',
    'text': 'Check explain tough movie moment process conference agent. Life success enough drive. Season interest politics mention.',
    'email': 'mark59@example.org',
    'phone_number': '435.420.3245',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Carson',
    'William Ellis',
    'Alexis Thomas',
    'Jessica Hill',
],
    'json': {
    'name': 'Jennifer Wilson',
    'address': '0505 Powell Spring Suite 275\nKevinborough, DE 76813',
},
    'key47719': 'value15021',
    'key83696': 'value98205',
    'key71313': 'value91761',
    'key63208': 'value35517',
    'key17316': 'value72506',
    'key42350': 'value37506',
    'key40843': 'value85476',
    'key75823': 'value77560',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Mr. Steven Mcdonald',
    'address': '374 Mendoza Vista Suite 182\nSouth Gerald, OH 81395',
    'text': 'Myself sort apply perform music end fast. Prepare meeting stock another beyond else simply.\nProperty enough court miss head past tax others. Three glass suffer.\nTraining body ten around sing radio.',
    'email': 'jamesmoore@example.net',
    'phone_number': '3746061263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Brooks',
],
    'json': {
    'name': 'William Ramirez',
    'address': '830 Julie Drive\nNorth Lisafurt, IA 65014',
},
    'key12721': 'value46556',
    'key91605': 'value22616',
    'key34415': 'value50556',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Jamie Smith',
    'address': '4492 Morrow Forest\nJoshuachester, HI 44773',
    'text': 'Could strategy from large low. Player detail fall security vote. Prepare majority maybe message.',
    'email': 'roachdonna@example.net',
    'phone_number': '608-566-0020x13181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Eduardo Gray',
    'Derek Quinn',
    'Allison Anderson',
    'Theresa Drake',
    'Christina Robles',
],
    'json': {
    'name': 'Brian Aguilar',
    'address': '5896 Karen Circles Apt. 481\nAnnaview, NH 17572',
},
    'key77940': 'value67836',
    'key66967': 'value62615',
    'key18857': 'value61115',
    'key79599': 'value96591',
    'key41928': 'value53294',
    'key43624': 'value89829',
    'key17042': 'value36375',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'William Banks',
    'address': 'PSC 6740, Box 6582\nAPO AP 55669',
    'text': 'Eye month result or. Success near hope three market. Remain top happy how owner shake.',
    'email': 'matthewbenson@example.org',
    'phone_number': '5665123835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Lee',
    'Logan Boyd',
    'Cheryl Scott',
    'Denise Parker',
    'Mark Sharp',
    'Tanya Williams',
],
    'json': {
    'name': 'Kathryn Blair',
    'address': '3996 Joseph Glens\nEast Robert, NJ 33806',
},
    'key64020': 'value89159',
    'key82043': 'value19652',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Sydney Williams',
    'address': '14201 Joseph Locks Suite 014\nEricfort, MA 60163',
    'text': 'Once bag arrive class would red suddenly according. Simple lawyer heavy out short laugh consider. Available listen account least law.',
    'email': 'james56@example.com',
    'phone_number': '001-791-885-9193x3940',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Susan Mendez',
    'Elizabeth Bauer',
    'Scott Willis',
    'Nicole Patel',
],
    'json': {
    'name': 'Kimberly Lewis',
    'address': '5054 Schroeder Spring\nDonnaberg, AR 23280',
},
    'key3934': 'value37504',
    'key90942': 'value5229',
    'key92666': 'value1687',
    'key29002': 'value50888',
    'key87730': 'value4529',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Justin Osborn',
    'address': '4407 Sarah Ridge Apt. 861\nPalmertown, MD 80099',
    'text': 'Happy single lay pressure. Fill yard mind wall other you too ability. Police both suggest newspaper.',
    'email': 'jsanders@example.org',
    'phone_number': '001-747-510-8464',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christian Schmidt',
],
    'json': {
    'name': 'Michael Sharp',
    'address': '83083 Nicholas Village Suite 678\nWest Debratown, MD 39289',
},
    'key24263': 'value95005',
    'key23917': 'value79676',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Juan Smith',
    'address': '415 Alvarez Glen\nRichardsonville, TX 25475',
    'text': 'Nothing president human away Mrs sing material. Image mean anything when. Society sing now south.\nStory table window. More old during.',
    'email': 'vgarcia@example.net',
    'phone_number': '+1-888-207-1497x7424',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tonya Hebert',
    'Ian Reeves',
],
    'json': {
    'name': 'Jackson Brooks',
    'address': '70783 Angela Landing\nNorth Krista, NC 85225',
},
    'key8352': 'value95573',
    'key68588': 'value38096',
    'key88895': 'value63382',
    'key33692': 'value41461',
    'key96008': 'value9218',
    'key431': 'value62850',
    'key12665': 'value79288',
    'key59943': 'value29378',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Latoya Ford',
    'address': '82431 Raymond Burgs Apt. 847\nSouth Darinburgh, SC 01909',
    'text': 'Board knowledge another. Play sell effect able kitchen wind.\nHowever admit fact factor.\nSign exist catch win require four theory. Game really ball research these.',
    'email': 'grantalyssa@example.net',
    'phone_number': '001-214-458-7729',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Eric Johnson',
    'Betty Perkins',
    'Ashley Olson',
    'Miranda Collier',
    'Deborah Glover',
    'David Clark',
    'William Lewis',
],
    'json': {
    'name': 'Cynthia Johnson',
    'address': '6725 Tina Centers\nSouth Garyton, PW 76643',
},
    'key64400': 'value64532',
    'key17860': 'value72585',
    'key51781': 'value50217',
    'key5389': 'value13685',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Jacqueline Gomez',
    'address': '565 Christine Well\nNorth Michaelville, IL 48208',
    'text': 'Far long than. Not free analysis this. Bit nothing professor factor agency.\nDaughter skin new. Everybody per strong total way. Catch event performance can four.',
    'email': 'xcarson@example.org',
    'phone_number': '+1-738-456-1069x3489',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Angela Brown',
    'Michelle Walker',
    'Jacob Smith',
],
    'json': {
    'name': 'Dustin Fry',
    'address': '851 Douglas Fields Suite 464\nLake Ronald, NY 99910',
},
    'key25042': 'value33981',
    'key79602': 'value419',
    'key72717': 'value86538',
    'key30806': 'value26634',
    'key22744': 'value88908',
    'key53914': 'value45537',
    'key31336': 'value98838',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Kristi Gibson',
    'address': '624 Robert Rapid\nLake Tammy, FM 26516',
    'text': 'Development determine know strategy. Share star nice during one democratic enjoy.\nAhead teach five kind appear population. Dog of poor hundred. Station thus than help back near.',
    'email': 'gracerobinson@example.net',
    'phone_number': '360-742-9456x252',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Mark Johnson',
    'Laurie Curry',
    'Shannon Brooks',
    'Joseph Carney',
    'Daniel Watkins',
    'Megan Munoz',
    'Danny Lynn',
    'James Mccormick',
    'Alicia Hurley',
],
    'json': {
    'name': 'Andrew Williams',
    'address': 'PSC 8328, Box 3010\nAPO AA 76376',
},
    'key48117': 'value81998',
    'key5537': 'value52680',
    'key92634': 'value6628',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Richard Potter',
    'address': '1270 Webster Drive Suite 544\nEast Phyllis, MD 68658',
    'text': 'Old way those station third trip. Office key deal commercial again gun. Program economy art marriage suggest again information. Much war she ready.',
    'email': 'kimberlyweber@example.org',
    'phone_number': '571.286.9498x508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Phillip Colon',
    'Eric Johnson',
    'Megan Macias',
    'Larry Bailey',
    'Michael Meza',
    'Melissa Lawrence',
    'Evan Atkinson',
    'Taylor Hahn',
],
    'json': {
    'name': 'Douglas Blankenship',
    'address': '444 Gabriel Run Apt. 094\nKingport, PA 74538',
},
    'key27060': 'value18022',
    'key28008': 'value91626',
    'key7766': 'value89532',
    'key55401': 'value73303',
    'key23903': 'value60073',
    'key92423': 'value46616',
    'key92240': 'value40131',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Richard Garrett',
    'address': '82889 Norton Place Apt. 918\nJohnsonton, PA 41853',
    'text': 'Address education thing dark add far any.\nOften agent make bar travel. Democrat southern traditional to foot. Find might face home.',
    'email': 'lauren20@example.com',
    'phone_number': '+1-529-786-6474x9607',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Janet Griffin',
    'Shannon Rosales',
    'Kevin Davis',
    'Jeffrey Armstrong',
    'Tara Carey MD',
    'Erica Lucas',
],
    'json': {
    'name': 'Luke West',
    'address': '4831 Fitzgerald Flats\nTonyaburgh, VI 04941',
},
    'key45909': 'value52557',
    'key61609': 'value14483',
    'key72008': 'value98740',
    'key26368': 'value2850',
    'key13618': 'value42072',
    'key36483': 'value28094',
    'key90292': 'value92114',
    'key35793': 'value53282',
    'key98274': 'value32419',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Dustin Weaver',
    'address': '8709 John Parkway\nNew Jose, IN 16657',
    'text': 'Huge husband serious car yes trouble. Exactly Mr above away already pressure artist. Sometimes family ok.',
    'email': 'griffithdavid@example.net',
    'phone_number': '240.735.2922x217',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Vaughn',
    'Matthew Ramsey',
    'Kathryn Lowe',
    'Brittany Strickland',
    'Anthony Campbell',
    'Rachel Murray',
],
    'json': {
    'name': 'Sandra Bishop',
    'address': 'PSC 9844, Box 8444\nAPO AA 06491',
},
    'key41564': 'value10712',
    'key76675': 'value37420',
    'key14662': 'value68586',
    'key69278': 'value35495',
    'key51197': 'value19084',
    'key30599': 'value58521',
    'key50757': 'value21660',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Sandra Turner',
    'address': '2563 Herrera Mountain Apt. 714\nJuanside, AK 06092',
    'text': 'Responsibility cover class expert. Congress produce theory else. Even town teach chance.\nSpend accept real. Data since carry future financial traditional institution.',
    'email': 'juanramsey@example.com',
    'phone_number': '(662)562-2029x755',
    'array_int_dynamic': [
    26415,
],
    'array_varchar_dynamic': [
    'Gary Summers',
    'Nicholas Robinson',
    'Olivia Collier',
    'Terry Ross',
    'Brendan Anderson',
    'David Saunders',
    'Luke Mayo',
    'Lori Cole',
],
    'json': {
    'name': 'Angel Sanchez',
    'address': '1292 William Expressway Apt. 826\nLindsayhaven, NJ 99457',
},
    'key36102': 'value47022',
    'key81645': 'value33885',
    'key29510': 'value10516',
    'key55453': 'value88016',
    'key76575': 'value72441',
    'key42300': 'value91428',
    'key84100': 'value83131',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Emily Arnold',
    'address': '1223 Sandra Cliff Apt. 203\nNorth Donna, AL 89400',
    'text': 'White treatment north life. Deep Democrat one make sister. Offer commercial church ground.\nSame fight good try establish special. Father election hotel worker never. Level there certain study.',
    'email': 'jimenezhannah@example.net',
    'phone_number': '242.874.0593x862',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Danielle Stevenson',
    'Kevin Jones',
    'Jesse Mcgee',
    'Michelle Johnson',
    'Bobby Lucas',
    'Kyle Taylor',
    'David Newton',
    'Austin Thomas',
    'Rachael Ortega',
    'Max Jones',
],
    'json': {
    'name': 'Benjamin Robinson',
    'address': '6584 Baird Spur\nLake Andrewfort, MP 46359',
},
    'key12263': 'value40063',
    'key15620': 'value80900',
    'key3893': 'value88111',
    'key80036': 'value66191',
    'key36720': 'value99903',
    'key63681': 'value51352',
    'key92656': 'value56535',
    'key98853': 'value36135',
    'key56930': 'value95184',
    'key9992': 'value60398',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Eddie Maldonado',
    'address': 'PSC 9470, Box 8271\nAPO AA 31638',
    'text': 'Around prevent role glass religious still. Success especially morning chance. Cup today everybody weight control hundred organization strategy.',
    'email': 'kyle79@example.net',
    'phone_number': '+1-641-798-6831x315',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Norman',
    'Bryan Sherman',
    'Cynthia Rivers',
    'Wesley Monroe',
    'Jamie Hebert',
    'Monica Barry',
    'Evelyn French',
    'Derek Nguyen',
    'Eddie Carpenter',
],
    'json': {
    'name': 'Mr. Martin Palmer',
    'address': '425 Rhodes Overpass Suite 354\nVelasquezchester, MT 84021',
},
    'key23092': 'value85921',
    'key99058': 'value82369',
    'key80571': 'value39184',
    'key41528': 'value74032',
    'key8238': 'value62936',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Darlene Mooney',
    'address': '26420 Bell Falls\nTimothybury, AL 54558',
    'text': 'Performance first stay per. Democrat bill range network figure newspaper. Usually shake key choose should seat.\nPresent range director soldier important. Cost and above.',
    'email': 'wyork@example.org',
    'phone_number': '375-640-2536x25293',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Todd Holder',
    'Theresa James',
    'Jeffrey King',
    'Michelle Cole',
    'Katherine Wall',
    'William Lopez',
    'Frank Jones',
    'Samantha Anderson',
    'Angela Hernandez',
    'Thomas Day',
],
    'json': {
    'name': 'Robert Thompson',
    'address': '201 Allen Point Suite 178\nSouth Kyle, DE 09662',
},
    'key60373': 'value13184',
    'key36214': 'value76969',
    'key73963': 'value82040',
    'key20199': 'value77243',
    'key64091': 'value65964',
    'key49252': 'value45946',
    'key87000': 'value81167',
    'key50889': 'value98552',
    'key90017': 'value41941',
    'key88621': 'value58571',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Mariah Ramirez',
    'address': '12711 Stewart Isle\nPhillipsfurt, LA 20184',
    'text': 'Nearly foot identify win. Drug report early significant today southern item pull. Doctor compare blood those.\nMilitary professor baby. Fast test physical situation machine.',
    'email': 'powelljacob@example.org',
    'phone_number': '(836)614-9295x005',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Singleton',
    'Matthew Hughes',
    'Sean Wagner',
    'Angela Jacobson',
    'Deborah Quinn',
    'Angela Browning PhD',
],
    'json': {
    'name': 'Natalie Guerrero',
    'address': '9174 Brown Junction Apt. 301\nWest Jeffery, AL 15680',
},
    'key53309': 'value43716',
    'key84652': 'value5118',
    'key16675': 'value84009',
    'key99346': 'value56368',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Scott Gregory',
    'address': '01565 Rhodes Mission Apt. 831\nNguyenside, MP 22917',
    'text': 'Significant chair plant by suddenly. Back cost better report break. Church explain mind dream morning.',
    'email': 'brittany71@example.com',
    'phone_number': '3364385761',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Richard Mccarthy',
    'Vicki Tapia',
    'Daniel Smith',
    'Jonathan Cross',
    'Cindy Cooke',
    'Kyle Adkins',
    'Mark Hensley',
    'Kevin Rogers',
    'Justin Sanchez',
    'Sarah Brewer',
],
    'json': {
    'name': 'Christina Franklin',
    'address': '880 Hannah Branch Apt. 657\nEricport, NC 05092',
},
    'key2453': 'value80386',
    'key32520': 'value23713',
    'key94298': 'value79164',
    'key98158': 'value79396',
    'key42763': 'value17646',
    'key56661': 'value99850',
    'key97447': 'value32524',
    'key68013': 'value12868',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Jessica Fields',
    'address': '709 Nunez Way Apt. 183\nPort Lancestad, MH 21105',
    'text': 'After difficult husband something. Visit choose inside begin far she on magazine. Tv somebody themselves economic dinner those. Wind move meet.',
    'email': 'foxteresa@example.net',
    'phone_number': '571-589-1543',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Rogers',
    'Alex Rodriguez',
    'John Bell',
    'James Matthews',
    'Jessica Holmes',
    'John Lowe',
],
    'json': {
    'name': 'Brian Harper',
    'address': '4239 Lee Pass Apt. 116\nAllisontown, LA 41366',
},
    'key29228': 'value59795',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Stacey Joseph',
    'address': '27450 Joel Green\nMaryview, GA 74294',
    'text': 'Coach various fire song rate TV. Imagine tell new visit. Gun new person hope base economic.\nMoney meet stay a building little. Read interview teacher away total.',
    'email': 'vsilva@example.com',
    'phone_number': '451-971-5080x11871',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Allen',
    'David Sherman',
    'Patricia Ali',
],
    'json': {
    'name': 'William Rivers',
    'address': '357 Terrell Radial\nLake Kevinfort, GU 02925',
},
    'key71555': 'value12276',
    'key87930': 'value96761',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Terrance Collins',
    'address': '08630 Brian Oval\nRioston, PW 72985',
    'text': 'Major what computer some few whole. Appear read trouble bar where. Determine much far western.',
    'email': 'james38@example.com',
    'phone_number': '339-633-0472x1741',
    'array_int_dynamic': [
    11960,
],
    'array_varchar_dynamic': [
    'Andrew Nelson',
    'Jennifer Hobbs',
],
    'json': {
    'name': 'Robert Khan',
    'address': '743 Moody Well Apt. 993\nHodgesmouth, IA 61245',
},
    'key89717': 'value81927',
    'key98680': 'value49968',
    'key4662': 'value9786',
    'key64881': 'value25878',
    'key90675': 'value88133',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Alan Fitzgerald',
    'address': '895 Andrea Summit\nDouglasmouth, AL 70505',
    'text': 'Manage way already need understand almost. Southern blue tree PM manager. See remain book control.\nBrother base personal American. Protect say it attack.',
    'email': 'warddaniel@example.net',
    'phone_number': '001-253-956-6033x259',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Lin',
    'Nicole Johnson',
    'Jacob Cooper',
    'Dr. Sharon Higgins',
    'Katherine Castro',
    'Michael Brown',
    'Andrea Dorsey',
],
    'json': {
    'name': 'Mary Chavez',
    'address': '1891 Lewis Harbor\nNorth Raymondton, NV 86969',
},
    'key22626': 'value17822',
    'key56273': 'value16249',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Corey Figueroa',
    'address': 'USCGC Durham\nFPO AE 76360',
    'text': 'Their budget simple. Interest bit technology two position pay.\nDiscussion dark one million painting. Return memory yourself best.',
    'email': 'xsullivan@example.net',
    'phone_number': '+1-301-385-9897',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Miller',
    'Jonathan Jackson',
    'Drew Nunez',
    'Timothy Edwards',
    'Daniel Walton',
    'Justin Richards',
    'Paula Singleton',
    'Denise Zamora',
    'Amanda Andrews',
],
    'json': {
    'name': 'Joseph Oconnor',
    'address': '19840 Cole Square\nGeorgeton, VI 76108',
},
    'key25621': 'value82883',
    'key76999': 'value13448',
    'key26125': 'value10698',
    'key19832': 'value8650',
    'key27097': 'value90325',
    'key53281': 'value50145',
    'key10293': 'value87141',
    'key2594': 'value1929',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Calvin Martinez',
    'address': '35776 Ashley Ford\nRichardbury, CT 90718',
    'text': 'Actually whose successful law practice.',
    'email': 'abbottkevin@example.com',
    'phone_number': '608.268.3877x4845',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Steven Beltran',
    'Jordan Smith',
    'Logan Roman',
    'Edward Jones',
],
    'json': {
    'name': 'Kelly Kennedy',
    'address': '9727 Montgomery Isle Apt. 653\nChristopherborough, MO 36602',
},
    'key14543': 'value36088',
    'key82570': 'value91740',
    'key22683': 'value30329',
    'key41141': 'value29231',
    'key21804': 'value87633',
    'key38346': 'value21109',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Danielle Herring',
    'address': '009 Walker Glen Suite 468\nPort Tiffanyfurt, MH 74366',
    'text': 'Easy world care audience. Evidence author power certain fly value.\nHotel level serious information heart spend get yet. Game large her quality boy drop.',
    'email': 'greenjonathan@example.org',
    'phone_number': '+1-259-911-2035x891',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Connor Bright',
    'Eric Peck',
    'Brian Young',
    'Jimmy Stevenson',
    'Natasha Miller',
    'Michael Silva',
    'Katie Beck',
    'Justin Marshall',
    'Gloria Rivas',
    'Paul Mitchell',
],
    'json': {
    'name': 'David Kemp',
    'address': '56642 Kimberly Streets Apt. 979\nJenniferfort, MO 96524',
},
    'key90386': 'value30220',
    'key44467': 'value1937',
    'key61821': 'value47600',
    'key6960': 'value54273',
    'key52225': 'value89720',
    'key41356': 'value58691',
    'key16787': 'value60342',
    'key74573': 'value97493',
    'key24354': 'value88358',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Jeffrey Moore',
    'address': '76117 Bennett Ferry Suite 990\nScottstad, IL 83644',
    'text': 'Throw identify of take arrive parent final. Father should treatment record open.\nThat size country pull media. Unit management learn. Dog skin role expect affect from son foot.',
    'email': 'tinaphillips@example.org',
    'phone_number': '353-554-2475x9657',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Robert Wilson',
    'Carolyn Gutierrez',
    'Brett Estrada',
    'Joseph Smith',
    'Emily Montgomery',
    'Denise Li',
    'Kristin Johnson',
    'Alyssa Mendez',
    'Chris Blackburn',
    'Alan Hoffman',
],
    'json': {
    'name': 'Sarah Logan',
    'address': '88922 Parker Lock\nJasonville, FM 56332',
},
    'key23337': 'value91558',
    'key29364': 'value68277',
    'key17089': 'value81640',
    'key72822': 'value49833',
    'key43713': 'value832',
    'key11196': 'value80934',
    'key91039': 'value73163',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Robert Forbes',
    'address': '3881 Reynolds Road Apt. 355\nCrawfordville, MO 03571',
    'text': 'College fear bring cold. Cup number picture day huge general.\nOthers room main alone effort fly. Religious bit cause seem it forward.',
    'email': 'catherine22@example.org',
    'phone_number': '(751)602-2832x1072',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michael Haynes',
    'Alisha Doyle',
    'Mrs. Cheryl Contreras',
    'Amy Estes',
    'Angel Hunt',
    'Thomas West',
    'Ruben Morgan',
    'Douglas Thomas',
    'Courtney Watts',
],
    'json': {
    'name': 'Stacy Walter',
    'address': '5045 Powell Route\nEast Robertmouth, FL 31758',
},
    'key18686': 'value24566',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Patricia Lloyd',
    'address': '5312 Cowan Brook\nEast Sarahstad, TN 21201',
    'text': 'Main cut artist month space. World plan nice single. Thought event read particularly. Lead door program nearly know dream everybody.',
    'email': 'xroberts@example.net',
    'phone_number': '+1-396-348-5358x21812',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Micheal Jackson',
    'Lisa Clark',
    'Chad Shaw',
    'Dr. Tammy Doyle',
],
    'json': {
    'name': 'Gary Vaughn',
    'address': '90507 Erica Harbor\nPort Jacob, IN 19382',
},
    'key14353': 'value77146',
    'key17374': 'value42470',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Robert Graves',
    'address': '017 Cooper Ridges Apt. 307\nNorth Warrenton, TX 99427',
    'text': 'Future up remain TV paper. Law practice tax serve degree result west.',
    'email': 'beltranleah@example.com',
    'phone_number': '9035031134',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Travis Lewis',
    'Dana Hodges',
    'Tiffany Brown',
    'Alexis Chen',
    'Dylan Dodson',
    'Michael Massey',
],
    'json': {
    'name': 'Jeremiah Kennedy',
    'address': '670 Watson Flats\nCynthiaberg, FL 43583',
},
    'key36408': 'value13563',
    'key39880': 'value40170',
    'key90703': 'value61850',
    'key29564': 'value92033',
    'key73432': 'value16274',
    'key33194': 'value40405',
    'key58130': 'value77742',
    'key11516': 'value70541',
    'key68141': 'value26775',
    'key61504': 'value7150',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Carol Kelly',
    'address': 'USCGC Stone\nFPO AA 32147',
    'text': 'Number six eat training help health truth place. Media want write use.\nSee bad try foot fear short sign.\nHand tough sister hold story. Table this hold agency season lot soon.',
    'email': 'nathangonzalez@example.net',
    'phone_number': '592-336-7789x089',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Keith Conley',
    'Jennifer Greer',
    'Jared Ward',
],
    'json': {
    'name': 'Christine Obrien',
    'address': '091 Erica Loop Suite 846\nNew Colinchester, ND 56475',
},
    'key67274': 'value69209',
    'key53057': 'value82488',
    'key4285': 'value96045',
    'key20936': 'value81832',
    'key63041': 'value98223',
    'key26930': 'value80967',
    'key90417': 'value63577',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Rebecca Smith',
    'address': '176 Johnson Key\nSolomonmouth, UT 54470',
    'text': 'Agency especially loss during full win. Manage set month deep lot early senior.\nBlack local science foot. Sure raise firm control close focus.',
    'email': 'donaldsonlynn@example.net',
    'phone_number': '(746)904-8469x12606',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Jennings',
    'Matthew Brown',
    'Sylvia Barber',
    'Nicole Snyder',
    'Jennifer Dickson',
    'William Williams',
    'Lindsey Martin',
    'Megan Mitchell',
    'Caitlin Brooks',
    'Mercedes Cook',
],
    'json': {
    'name': 'Michael Hoffman',
    'address': '8314 Roy Flats Apt. 851\nJacksonfurt, MP 63308',
},
    'key22411': 'value29468',
    'key92810': 'value38862',
    'key7294': 'value77883',
    'key63448': 'value58087',
    'key69529': 'value94557',
    'key60526': 'value99014',
    'key13886': 'value7395',
    'key55783': 'value8628',
    'key85168': 'value56448',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Denise Mckee',
    'address': '6033 Travis Wall\nEast Amyport, AL 32956',
    'text': 'So government room million direction anything recently party.\nOk same response together room. Crime rise parent father.',
    'email': 'rhart@example.com',
    'phone_number': '+1-888-848-5249',
    'array_int_dynamic': [
    78570,
],
    'array_varchar_dynamic': [
    'Anne Bradford',
    'Jacqueline Hughes',
    'April Houston',
],
    'json': {
    'name': 'Roger Huff',
    'address': '8075 Thompson Divide Apt. 538\nNorth Danielchester, MH 59550',
},
    'key91920': 'value69660',
    'key32632': 'value9754',
    'key42160': 'value19964',
    'key39168': 'value89488',
    'key95828': 'value52387',
    'key71767': 'value34306',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Megan Wilson',
    'address': '53896 Johnson Turnpike\nNorth Brett, IA 38627',
    'text': 'Detail crime process identify. Under people top show who goal what. Manager unit different.\nRecent month bit program friend future hand political. Break medical such growth information listen.',
    'email': 'jillian67@example.com',
    'phone_number': '001-507-404-8302x2277',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Darrell Huber DDS',
    'Vincent Brooks',
    'Cynthia Howell',
    'Rachel Waters',
    'Jeremy Davis',
    'Shelby Terry',
    'Mary Lynn',
    'Nicole Mills',
    'Vincent Johnson',
    'Kenneth Haley',
],
    'json': {
    'name': 'Tyler Johnson',
    'address': '10228 Crystal Pine\nAshleyhaven, MT 85148',
},
    'key77336': 'value47339',
    'key25224': 'value13572',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Bonnie Webb',
    'address': '076 Kelly Station\nWest Brittanybury, WA 30207',
    'text': 'Writer economic reach later mind own green. Style tonight evidence visit.\nDevelop provide age resource. Poor amount degree research miss activity.',
    'email': 'chris70@example.org',
    'phone_number': '001-747-951-5741x3843',
    'array_int_dynamic': [
    97316,
],
    'array_varchar_dynamic': [
    'Eric Griffith',
    'Brian Morris',
    'Jeremy Johnson',
    'Olivia Miller',
    'Melanie Anderson DDS',
    'Adam White',
    'Nathan Wilkins',
    'Joyce Ward',
    'Robert Richardson',
    'Melissa Jones',
],
    'json': {
    'name': 'Felicia Molina MD',
    'address': '5128 Nathan Meadow\nPort Michaelborough, MT 33720',
},
    'key67977': 'value7188',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Gregory Smith Jr.',
    'address': 'Unit 4729 Box 8523\nDPO AA 92115',
    'text': 'Drug company involve ground avoid lot past. Write movement fish bill rule bill. Almost it exactly above smile.\nBeautiful executive eye area name ball. Foreign staff son with few kid.',
    'email': 'geraldduncan@example.net',
    'phone_number': '6156618824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Lucas',
    'Andrea Evans',
    'Corey Salas',
    'Justin Carroll',
],
    'json': {
    'name': 'Jon Stephens',
    'address': '557 Katherine Plains\nSouth Laurenmouth, VT 55624',
},
    'key85621': 'value97992',
    'key61178': 'value39488',
    'key23312': 'value55480',
    'key96123': 'value935',
    'key72294': 'value28607',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Kristen Thomas',
    'address': '754 Johnson Shoal\nWest Jessicafort, OH 29101',
    'text': 'Event feeling finally media ground strong carry. Candidate audience media trade design. Hit network son heart.',
    'email': 'xward@example.net',
    'phone_number': '(479)470-6568',
    'array_int_dynamic': [
    50281,
],
    'array_varchar_dynamic': [
    'Joseph Wright',
    'Julie Baird',
    'Carrie Brown',
    'Thomas Alvarez',
    'Audrey Zamora',
    'Joseph Cuevas',
    'Kathryn Bishop',
    'Sydney Hill',
],
    'json': {
    'name': 'Stanley Lucero',
    'address': '814 Branch Ways Suite 020\nJohnsonhaven, NE 28372',
},
    'key91317': 'value91639',
    'key26768': 'value85941',
    'key41274': 'value75497',
    'key14696': 'value56127',
    'key26177': 'value26655',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Karen Robertson',
    'address': '674 Debra Burg\nNew Miranda, MI 15477',
    'text': 'Happen change place life western full.\nAsk would second issue.\nQuality ability Mrs through arm about. Agency way school. Record machine mother wonder for.',
    'email': 'parkerbrandon@example.net',
    'phone_number': '001-924-759-7403x6467',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Debra Bruce',
    'Stephanie Kelly',
],
    'json': {
    'name': 'Joseph Long',
    'address': 'Unit 3014 Box 7724\nDPO AP 35021',
},
    'key34704': 'value19395',
    'key39769': 'value71704',
    'key7581': 'value60847',
    'key31252': 'value42976',
    'key8289': 'value6433',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Amanda Walsh',
    'address': '359 Shane Forks\nAudreyport, MO 00771',
    'text': 'Stage high find long. Agent kind million law each sign attention. Support against draw investment break.',
    'email': 'yangkayla@example.net',
    'phone_number': '936.430.2192x505',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Lori Pham MD',
    'April Garrett',
    'Ann Garrett',
],
    'json': {
    'name': 'Michael Murphy',
    'address': '421 Murphy Summit Suite 816\nSouth Kathyport, OR 14677',
},
    'key76991': 'value24654',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Courtney Cunningham',
    'address': '231 Tyler Valley Suite 105\nNorth Henryport, VA 18966',
    'text': 'Anyone fish less and second get condition security. Player question television run staff time. Maybe wife represent actually.',
    'email': 'marc33@example.net',
    'phone_number': '301.610.7098x25008',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Erin Henry',
    'George Navarro',
],
    'json': {
    'name': 'Amanda Jones',
    'address': '1688 Perry Landing\nPort Kimberlyfort, FL 92470',
},
    'key84048': 'value65595',
    'key24725': 'value85619',
    'key4700': 'value21359',
    'key80288': 'value65208',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Susan Cruz',
    'address': '0459 Smith Forge\nWest Patricia, TX 18312',
    'text': 'Position forward between answer present suffer no wish. Doctor education policy four. Administration mouth machine interview federal million believe measure.',
    'email': 'mbrown@example.net',
    'phone_number': '(655)355-4008',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Chelsea Lewis',
    'Corey Jones',
    'David Daniels II',
    'Keith Lawson',
    'Molly Weaver',
],
    'json': {
    'name': 'Brandon Rush',
    'address': '61185 Joseph Prairie Apt. 743\nKingshire, VA 35623',
},
    'key11710': 'value18648',
    'key42098': 'value34100',
    'key34748': 'value37269',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Kenneth Castro',
    'address': '1540 Buck Neck Suite 224\nParkerville, WI 33838',
    'text': 'Eight position less expert accept speech. Theory either central property about model American. Sound risk home state number owner against.',
    'email': 'allison54@example.com',
    'phone_number': '+1-976-703-2913x4886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'David Yoder',
    'Nicole Ward',
    'Andrew King',
    'Edward Ortiz',
],
    'json': {
    'name': 'Marissa Wallace',
    'address': '80450 Gonzalez Meadows Apt. 337\nBurchbury, RI 64332',
},
    'key17289': 'value89272',
    'key25465': 'value6931',
    'key48675': 'value23219',
    'key14541': 'value70414',
    'key97758': 'value7371',
    'key37285': 'value89610',
    'key38528': 'value99003',
    'key29255': 'value67494',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Whitney Fuller',
    'address': 'PSC 8732, Box 8313\nAPO AA 95949',
    'text': 'Trouble three staff. Physical region could during wind.\nCentury member believe dog allow. Indicate appear think you agency keep executive. Around same leave try.',
    'email': 'williamsmichael@example.com',
    'phone_number': '931.272.9801',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Williams',
    'Jason Marks',
    'William Lewis',
    'Jordan Gonzales',
    'Thomas Price',
    'Terry Adams',
    'Daniel Ho',
    'Breanna Edwards',
    'Rebecca Edwards',
    'Joseph Irwin',
],
    'json': {
    'name': 'Matthew Johnson',
    'address': '361 Martin Island\nSanchezbury, MP 04720',
},
    'key23691': 'value66629',
    'key63847': 'value68580',
    'key40567': 'value29314',
    'key92406': 'value59686',
    'key35982': 'value25585',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Rita Myers',
    'address': '54849 Paula Locks Apt. 421\nOconnellview, VT 95621',
    'text': 'Author mind space design hit executive real political. Add wall certain although.',
    'email': 'craig13@example.org',
    'phone_number': '(543)457-9604',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'William Johnson',
    'Anthony White',
],
    'json': {
    'name': 'David Rivera',
    'address': '1764 Cox Cove\nEast Kathryn, DC 78905',
},
    'key9688': 'value16706',
    'key89611': 'value15230',
    'key71712': 'value44692',
    'key83876': 'value48419',
    'key94886': 'value86001',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'George Young',
    'address': '4821 Kim Forge Suite 611\nChristopherstad, KS 49520',
    'text': 'Clear girl fall feel move contain evening.\nWithin late perhaps administration key. Chair heavy you modern. After wonder soldier whole class learn.\nRange rule together subject do hard.',
    'email': 'sara76@example.net',
    'phone_number': '889.767.0151x6713',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Katie Evans',
    'Paul Smith',
    'Kristina Hernandez',
    'Kristin Hill',
    'Anthony Thompson',
],
    'json': {
    'name': 'Omar May',
    'address': '58639 Andrew Track\nHudsonton, AS 78591',
},
    'key99810': 'value59167',
    'key19217': 'value99191',
    'key19706': 'value77537',
    'key76817': 'value274',
    'key1484': 'value17536',
    'key48247': 'value88754',
    'key99082': 'value56240',
    'key22145': 'value54578',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Susan Burton',
    'address': '5828 Grace Centers\nAshleybury, ND 83439',
    'text': 'Center voice bag young machine. Executive coach whatever great table water more show.\nInformation seat past. Social walk Republican billion during professional.',
    'email': 'watkinsrichard@example.net',
    'phone_number': '+1-407-833-4908',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Donald Gregory',
    'Todd Vaughan',
    'Eric Swanson',
    'Paul Johnson',
    'Timothy Keller',
    'Christopher Valencia',
    'Marc Jones',
    'Denise Reynolds',
],
    'json': {
    'name': 'Douglas Howard',
    'address': '26772 Brianna Court\nMeyerschester, IN 36412',
},
    'key79953': 'value43588',
    'key80628': 'value38298',
    'key82807': 'value42952',
    'key74500': 'value41845',
    'key35430': 'value71348',
    'key1010': 'value6739',
    'key99810': 'value24299',
    'key29299': 'value42532',
    'key84587': 'value71394',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Audrey Mathis',
    'address': '72276 Page Pines\nSmithberg, AL 68513',
    'text': 'Brother if early son.\nFigure record thank gas message. Size attorney that pick. Quickly seven try work. Environment knowledge within maintain big many popular identify.',
    'email': 'goulderic@example.com',
    'phone_number': '001-276-446-7180x046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brittney Sullivan',
],
    'json': {
    'name': 'Brian Smith',
    'address': 'USNS Lee\nFPO AE 51246',
},
    'key68620': 'value39037',
    'key27763': 'value83125',
    'key38932': 'value99212',
    'key30450': 'value96137',
    'key16990': 'value69451',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Rhonda Dunn',
    'address': '7635 Donna Road\nWilliamsmouth, OH 95369',
    'text': 'Dream itself common second fill next question. Yard medical pass coach decide.\nExpect better always let security. Cut human start deep model use state.',
    'email': 'jacob19@example.net',
    'phone_number': '+1-604-554-6338x62595',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Chelsea Brown',
    'Taylor Mata',
    'Sara Waters',
    'James Clark',
    'Terrance Hooper',
    'Stephanie Rogers',
    'Carol Martinez',
    'Brandon Gregory',
    'Amanda Graham',
],
    'json': {
    'name': 'Thomas Davis',
    'address': '08557 Jones Viaduct Suite 873\nLake Tammy, UT 52628',
},
    'key14643': 'value75257',
    'key22689': 'value98931',
    'key24114': 'value26699',
    'key10331': 'value26507',
    'key2870': 'value73958',
    'key85019': 'value31557',
    'key11175': 'value20686',
    'key36816': 'value37734',
    'key32374': 'value46988',
    'key99875': 'value71957',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Michael Moss',
    'address': '9604 Kristen Lodge Apt. 970\nCastanedaville, MI 62890',
    'text': 'Hope believe affect security official administration. Too imagine natural. Report rock several fight particularly drive.\nAbout small now ready sense husband.',
    'email': 'omartinez@example.com',
    'phone_number': '858-913-9452x4502',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Bishop',
    'James Harris',
    'Angel Moore',
    'Denise Villa',
    'Candice Trujillo',
    'Lisa Crawford',
    'Lisa Smith',
    'Stephen Jones',
    'Amy Martin',
],
    'json': {
    'name': 'Scott Roberts',
    'address': 'USNV Lopez\nFPO AP 59474',
},
    'key63052': 'value65230',
    'key49773': 'value472',
    'key39180': 'value9459',
    'key57516': 'value1044',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Anthony Patterson',
    'address': '446 Elizabeth Springs\nSouth Natalietown, VT 49116',
    'text': 'Moment one upon whether great. Court into mean.\nEvent simply realize able. Society stuff through lay tax main government. Agent nothing around model.',
    'email': 'sherri27@example.net',
    'phone_number': '674-325-4139',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Ball',
    'Katrina Rich',
    'Alexis Miranda',
    'Angel Smith',
    'Devin Randall',
    'Michele Deleon',
    'Keith Wells',
    'Nicole Carter',
],
    'json': {
    'name': 'Katherine Schmidt',
    'address': '912 Shields Camp Apt. 268\nRiddleborough, VA 16031',
},
    'key51127': 'value45141',
    'key78762': 'value26575',
    'key14597': 'value38770',
    'key4210': 'value28980',
    'key32504': 'value38167',
    'key98106': 'value8482',
    'key45555': 'value79535',
    'key1814': 'value37518',
    'key86027': 'value46692',
    'key61589': 'value45864',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Michael Murphy',
    'address': '283 Kendra Trafficway\nWest Cynthia, OH 45237',
    'text': 'However center newspaper tonight create likely. Speak miss risk free we final.\nKeep region camera result. Right industry off.',
    'email': 'josephpark@example.org',
    'phone_number': '(455)881-2238x504',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Terrance Burton',
    'Tammy Marsh',
    'Jim Reed',
    'Kimberly Holmes',
    'Alex Clayton',
    'Brett Riley',
    'Carrie Glover',
    'Joseph Jordan',
    'Ashley Gross',
],
    'json': {
    'name': 'Thomas Moreno',
    'address': '7958 Shaw Forges\nHolthaven, NE 87574',
},
    'key18657': 'value58214',
    'key98374': 'value5799',
    'key96146': 'value59153',
    'key46724': 'value43070',
    'key78101': 'value54736',
    'key51620': 'value46761',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Monica Jenkins',
    'address': '6587 Jackson Brooks\nRojasborough, MO 71437',
    'text': 'Him challenge send whose. Best trouble manage painting tell.\nEasy after her majority institution. Recently always up couple light attention. Law interesting beautiful final true culture phone.',
    'email': 'christopher93@example.com',
    'phone_number': '(652)493-5326x05573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Wiggins',
    'Michael Dougherty',
    'Jessica Phillips',
    'Mr. Gary Hicks',
    'Robert Love',
    'Jeffrey Roy',
    'Deborah Davis',
    'Amy Sandoval',
    'Christy Bautista',
],
    'json': {
    'name': 'Melanie Harmon',
    'address': '970 Julie Ridges Apt. 946\nBrendafurt, MO 92263',
},
    'key97049': 'value63989',
    'key16409': 'value26099',
    'key95285': 'value72455',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Omar Hall',
    'address': '537 Adams Mews\nRobbinsfort, AL 78842',
    'text': 'House thus customer letter none maybe including. Majority whose quickly expert reflect seat. Some rule never left. South add speech floor organization citizen scientist.',
    'email': 'gcarpenter@example.com',
    'phone_number': '001-853-757-8238x843',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Dominguez',
    'Sandra Grant',
    'Julie Hodges',
    'Jennifer Graham',
],
    'json': {
    'name': 'Christopher Nguyen',
    'address': '88520 Calvin Forge\nKellymouth, AR 68445',
},
    'key98801': 'value85730',
    'key40878': 'value41289',
    'key35856': 'value75738',
    'key40880': 'value7465',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Jason Collins',
    'address': '3278 Garcia Turnpike\nNicholsburgh, RI 87047',
    'text': 'Relate over occur study game maintain nation. Local page nice language economic little experience. Consumer sort change bad tell parent. Able election yard quality maintain.',
    'email': 'luissmith@example.net',
    'phone_number': '923.213.6209x704',
    'array_int_dynamic': [
    95571,
],
    'array_varchar_dynamic': [
    'Kenneth Chan',
    'Tyler Santana',
],
    'json': {
    'name': 'Daniel Porter',
    'address': '572 Carlson Greens Suite 785\nHerreratown, MO 44046',
},
    'key48939': 'value99451',
    'key20417': 'value72857',
    'key3943': 'value61251',
    'key26552': 'value75499',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Andrew Carter',
    'address': '207 Davenport Station\nBassstad, NV 22759',
    'text': 'Newspaper feel on phone. Value trade such room state. Sometimes whatever economic argue design perhaps. Director child too involve.',
    'email': 'robertgates@example.com',
    'phone_number': '910-331-3517',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Howard',
    'Lance Hess',
    'Catherine Smith',
    'William Shelton',
    'Charles Phillips',
    'Daniel Martinez',
],
    'json': {
    'name': 'Michael Hernandez MD',
    'address': '71256 Brenda Wells Apt. 589\nMichaelberg, GU 41931',
},
    'key17303': 'value93336',
    'key18985': 'value29964',
    'key28245': 'value25487',
    'key89489': 'value98335',
    'key62152': 'value35411',
    'key23818': 'value62614',
    'key40252': 'value59159',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Victoria Petty',
    'address': '8770 John Shoal\nEast Catherine, NC 83747',
    'text': 'Woman view some eat. Organization idea case I factor necessary. Lay white a her three.\nAgency management allow stage true. Seven low offer quickly blood toward section mention.',
    'email': 'ortegajohn@example.com',
    'phone_number': '226-789-9981x316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Hutchinson',
    'Heather Velazquez',
    'Joseph Miller',
    'Thomas Jackson',
],
    'json': {
    'name': 'John Garcia',
    'address': '891 Young Point\nSouth Pam, MP 42945',
},
    'key30532': 'value61477',
    'key78110': 'value71845',
    'key12101': 'value91633',
    'key80882': 'value61909',
    'key83093': 'value35198',
    'key12854': 'value31606',
    'key34482': 'value67387',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Sara Guzman',
    'address': '397 Campbell Path\nCarsonbury, MN 49728',
    'text': 'Through wish night loss teach consider include. Lot benefit yet southern into fall section.\nHouse north whatever think goal feeling never. Quality address on air.',
    'email': 'fbush@example.net',
    'phone_number': '(781)401-5018',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Martin Lynch',
    'Jesse Hill',
],
    'json': {
    'name': 'Heather Wright',
    'address': '489 Williams Island Apt. 951\nHarrisberg, NV 39064',
},
    'key38523': 'value15610',
    'key17863': 'value31255',
    'key94677': 'value59259',
    'key31938': 'value5315',
    'key384': 'value15738',
    'key98597': 'value13180',
    'key35450': 'value95702',
    'key40396': 'value74719',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Michael Copeland',
    'address': '563 Kennedy Squares Suite 282\nLake Shane, MS 14152',
    'text': 'Choose dinner service side town left dream necessary. Reflect then simply development development fast give. Friend affect law go table policy.',
    'email': 'sarahsmith@example.org',
    'phone_number': '(249)915-1556',
    'array_int_dynamic': [
    73313,
],
    'array_varchar_dynamic': [
    'Anthony Dunlap',
    'Rodney Lopez',
],
    'json': {
    'name': 'Cindy Sanders MD',
    'address': '7974 Johnson Coves Suite 627\nGlendafort, OH 54710',
},
    'key73831': 'value4509',
    'key22290': 'value28078',
    'key67743': 'value30039',
    'key62142': 'value14362',
    'key86300': 'value44549',
    'key19537': 'value77261',
    'key38621': 'value5359',
    'key90196': 'value84981',
    'key79641': 'value94465',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Cheyenne Webb',
    'address': '1928 Shannon Trace\nEast Kayleeberg, AS 03011',
    'text': 'Capital year yeah provide would. Way down others leader. Heart whether next significant.\nWhose effect condition age. Live drive chair treat.',
    'email': 'joan09@example.com',
    'phone_number': '682-837-9299',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Adam Pierce',
    'Jerome Glenn',
    'Michael Calhoun PhD',
    'Anthony Johnson',
    'Michael Chen',
],
    'json': {
    'name': 'Stacey Mccarthy',
    'address': '4068 Mata Mills\nPort Donnaport, WV 48174',
},
    'key1425': 'value54366',
    'key14545': 'value93141',
    'key48769': 'value42887',
    'key80307': 'value64096',
    'key38302': 'value7574',
    'key4848': 'value40335',
    'key99866': 'value41250',
    'key80521': 'value45835',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Evan Turner',
    'address': '43425 Erin Greens Suite 297\nWest Brian, MO 39847',
    'text': 'Community line pass than staff cell. Property identify amount attack feel.',
    'email': 'debbieschwartz@example.com',
    'phone_number': '001-392-431-8624',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Bonilla',
    'Jason Lee',
    'Tiffany Gamble',
    'Thomas Lynn',
],
    'json': {
    'name': 'Angie Pearson',
    'address': '1668 Darlene Place\nNew Williamberg, AS 36830',
},
    'key24761': 'value51451',
    'key91771': 'value69877',
    'key10687': 'value90460',
    'key26176': 'value30165',
    'key46841': 'value34257',
    'key88016': 'value53297',
    'key42858': 'value69328',
    'key18050': 'value42268',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Sherry Richardson',
    'address': '63957 Zimmerman Centers Apt. 941\nPort Julia, NY 89015',
    'text': 'Environment according tend spend it region go impact. Beat network tax lose position man. Teacher decade happen newspaper beautiful first election.',
    'email': 'yorkapril@example.net',
    'phone_number': '410-320-9795x079',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Brown',
    'Ann Werner',
    'Kimberly Sims',
    'Bryan Kidd',
    'William Woods Jr.',
    'Matthew Watson',
    'Edwin Newman',
    'Maria Warner',
    'Tracy Crawford',
    'Jon Parsons',
],
    'json': {
    'name': 'Heather Beck',
    'address': '71154 Ashley Junctions Apt. 106\nKaylastad, AL 13866',
},
    'key44096': 'value38304',
    'key42266': 'value10321',
    'key11835': 'value76038',
    'key90916': 'value20925',
    'key90339': 'value6652',
    'key53084': 'value65955',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Charles Salas',
    'address': '53800 Hardy Ferry Apt. 839\nNew Angel, LA 97433',
    'text': 'Tonight admit pressure bar education mother. Address cost lead late player.\nPositive friend question air future tonight catch. Environmental side picture heart strategy face brother foot.',
    'email': 'chall@example.com',
    'phone_number': '557.249.3099x263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Derrick Collins',
    'Angela Johnston',
    'Tammy Crawford',
],
    'json': {
    'name': 'Stephanie Martin',
    'address': '71825 Sarah Centers Apt. 971\nHaroldhaven, MN 61163',
},
    'key44716': 'value89515',
    'key53145': 'value88536',
    'key53213': 'value48999',
    'key17719': 'value93787',
    'key5445': 'value32461',
    'key23612': 'value20463',
    'key9572': 'value70074',
    'key14312': 'value32251',
    'key54126': 'value18858',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Grant Williams',
    'address': '4585 Hall Skyway Suite 296\nNorth Amandaside, KS 63650',
    'text': 'Describe control individual might interview. Become imagine door bring field.\nTake exist think information money. Record add purpose which gun many.',
    'email': 'pprice@example.net',
    'phone_number': '959.445.2508x2917',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Karen Adams',
    'Dana Fowler',
    'Linda Newman',
    'Austin Miller',
    'Melissa Cooley',
    'Mary Hartman',
    'Sara Rios',
    'Cody Farrell',
    'Stephanie Garcia',
],
    'json': {
    'name': 'Andrew Henderson',
    'address': '8763 Alexis Streets Suite 608\nMooremouth, DC 06148',
},
    'key83016': 'value21022',
    'key73058': 'value25805',
    'key59270': 'value39918',
    'key16358': 'value30734',
    'key86773': 'value59351',
    'key3657': 'value57665',
    'key9505': 'value37733',
    'key10706': 'value83884',
    'key2392': 'value54828',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Michael Parker',
    'address': '0522 Joshua Road\nLeefort, NC 25616',
    'text': 'Above science yes. Major strategy appear body from civil. Hit many address together.\nOften individual would side somebody hundred. Career consider reason describe long shoulder several.',
    'email': 'hodgejerome@example.org',
    'phone_number': '(745)635-4352x856',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Robert Matthews',
    'Christine Rodriguez',
    'Kimberly Davis',
    'Shane Vega',
    'Megan Smith',
    'Caleb Warren',
    'David Black',
    'John Murray',
    'Alice Pineda',
],
    'json': {
    'name': 'Melissa Roberts',
    'address': '75243 Haynes Island Suite 075\nNorth Andrew, TX 73760',
},
    'key52221': 'value77736',
    'key78459': 'value283',
    'key74580': 'value29592',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Kristine Anderson',
    'address': '62990 Rhonda Rest Apt. 591\nLake Sara, NM 92729',
    'text': 'Safe play ok her bill. Key position what view sell anyone want.\nPolice can wait phone it. Strategy everything possible trouble list seem. All professional line program.',
    'email': 'smithrebecca@example.net',
    'phone_number': '(316)346-7481x075',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Steven Allen',
    'Leslie Bean',
],
    'json': {
    'name': 'Terri Clark',
    'address': '37591 Tapia Ways\nMichelleshire, IA 39834',
},
    'key2385': 'value78856',
    'key21415': 'value79137',
    'key27542': 'value93347',
    'key46852': 'value11582',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Bridget Wilson',
    'address': '596 April Vista\nGallegoston, NV 34730',
    'text': 'Concern test name strong consider believe. Also about brother.\nWriter word require policy. Particularly to our big nothing. Create onto your speak back form.\nAccept production method trip.',
    'email': 'floreslori@example.com',
    'phone_number': '(302)259-7489x451',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Trevor Jones',
    'David Roberts',
    'John Ross PhD',
    'Richard Barnes',
    'Allison Williams',
    'Christopher Wood MD',
    'Jessica Cook',
    'Lauren Park',
    'Kevin Rice',
],
    'json': {
    'name': 'Michael Bradley',
    'address': '887 Jordan Lane\nMonicaland, GA 21363',
},
    'key82765': 'value44595',
    'key96575': 'value91628',
    'key75160': 'value39624',
    'key79911': 'value86194',
    'key16505': 'value79182',
    'key38498': 'value2209',
    'key65377': 'value35056',
    'key38703': 'value78609',
    'key56112': 'value13225',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'William Crawford',
    'address': 'USCGC Banks\nFPO AP 54856',
    'text': 'Place why art high. Theory worker sign structure rest benefit now protect. Will maybe people report indicate serve good.',
    'email': 'benjaminroberts@example.org',
    'phone_number': '+1-322-601-9017x4063',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Amy Villarreal',
    'Keith Ford',
    'Lindsay Carrillo',
    'Ana Hull',
],
    'json': {
    'name': 'Mary Campos',
    'address': '4151 Norman Gateway Apt. 343\nMorrisland, RI 45704',
},
    'key20688': 'value48368',
    'key46727': 'value918',
    'key31716': 'value17423',
    'key64504': 'value40531',
    'key29360': 'value96663',
    'key4465': 'value48530',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Adam Dean',
    'address': '75640 Ryan Shore\nLeeton, OK 81964',
    'text': 'Force project up town alone evidence into. Magazine last when property local organization different.\nDog simply mean reason. Myself ability seven tough.\nStand right else health eye church second.',
    'email': 'kevin89@example.org',
    'phone_number': '745.419.2167x209',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Morris',
    'Steve Vargas',
    'Michelle Nielsen',
    'Lori Fernandez',
],
    'json': {
    'name': 'Donald Rose',
    'address': '34979 Wise Ford Apt. 795\nFloresview, MH 69965',
},
    'key26256': 'value88431',
    'key60397': 'value58353',
    'key32743': 'value59509',
    'key41522': 'value68207',
    'key13743': 'value69372',
    'key26846': 'value73911',
    'key24962': 'value50098',
    'key98432': 'value14896',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Phillip Johnson',
    'address': '68312 Tyler Common\nGarciafort, VA 41197',
    'text': 'Vote late staff show. Plan only black oil at. Simple if listen fly.\nKey relate suddenly.\nMovie provide everyone Congress after itself. Mention magazine who else. Bring that decade work style war.',
    'email': 'lphelps@example.com',
    'phone_number': '318.620.8884',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Drake',
    'Peter Fowler',
    'Patricia Haynes',
],
    'json': {
    'name': 'Stephanie Ford',
    'address': '969 Diane Spurs\nPaulport, SD 34418',
},
    'key34308': 'value30591',
    'key45818': 'value61355',
    'key36758': 'value82466',
    'key50050': 'value58140',
    'key38791': 'value64136',
    'key1616': 'value6081',
    'key28438': 'value51039',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Stephen Harris',
    'address': '968 Irwin Junction Suite 853\nRebeccaburgh, VT 82040',
    'text': 'What large mention street beyond run decade.\nSeries like weight bank nearly service industry. Hear movie family staff bit state year.',
    'email': 'joseph52@example.org',
    'phone_number': '(275)457-2383',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brandi Fuller',
    'Andrew Carroll',
    'Tiffany Lewis',
    'Jesse Cabrera',
    'Jason Gonzales',
    'Matthew Jackson',
    'Anthony Sanders',
    'Jonathon Mendoza',
    'John Hanson',
    'Michael Luna',
],
    'json': {
    'name': 'Lauren Pennington',
    'address': 'Unit 7120 Box 5001\nDPO AA 73873',
},
    'key29652': 'value1638',
    'key26310': 'value16620',
    'key84732': 'value23275',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Vanessa Martin',
    'address': '8522 Harrison Stravenue\nAshleeton, OK 86107',
    'text': 'Everybody however affect at. Try military activity ok hope around live player.\nHer guy coach government nice our. All authority author week.',
    'email': 'smithnicole@example.org',
    'phone_number': '986.735.6843x180',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Parks',
    'John Hall',
    'Carla Holloway',
    'Dustin Benson',
    'William Frazier',
    'Rebecca Craig',
    'Leon Ellis',
    'Kathryn Drake',
],
    'json': {
    'name': 'Kelli Hernandez',
    'address': '768 William Rapids Suite 420\nWendyfurt, AR 87109',
},
    'key38603': 'value140',
    'key50724': 'value95171',
    'key70077': 'value62179',
    'key40860': 'value19946',
    'key56837': 'value85911',
    'key17349': 'value96395',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Brittany James',
    'address': '650 Evan Gateway Apt. 393\nKaitlinport, WY 18216',
    'text': 'Responsibility thought face part drug four. Relate laugh floor your data finally.',
    'email': 'karennovak@example.net',
    'phone_number': '+1-781-673-4100x95126',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Paul Bennett',
    'Kathleen Johnson',
    'Kathryn Young',
    'Ann Gonzalez',
    'Sandra Bryant',
    'Adam Thomas',
    'Kelsey Bender',
    'Brandon Porter',
    'Holly Saunders',
],
    'json': {
    'name': 'Joseph Lee',
    'address': '2577 Heath Landing\nWest Tinafort, PA 83204',
},
    'key19368': 'value8296',
    'key46839': 'value99554',
    'key94586': 'value40884',
    'key61108': 'value42816',
    'key63994': 'value71994',
    'key68546': 'value45590',
    'key39411': 'value21549',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Marc Richardson',
    'address': '39185 Levine Cape Apt. 014\nClaytonfort, MH 39710',
    'text': 'Prepare establish Democrat experience it seem face. Measure tough religious house ability. Several around blood environment prepare summer physical magazine.',
    'email': 'johnstonmary@example.com',
    'phone_number': '(265)327-8124x419',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Eric Gibbs',
    'Donald Curry',
    'Mary Guzman',
    'Pamela Donaldson',
    'Heather Davis',
    'Vickie Ramirez',
    'Mrs. Tiffany Turner',
],
    'json': {
    'name': 'David Johnson',
    'address': '72548 Vazquez Track\nPort Scott, TX 39210',
},
    'key1619': 'value26722',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Michele Summers',
    'address': '221 Alex Terrace Suite 666\nSouth Adam, CO 13323',
    'text': 'Public author answer true campaign me. Line above seven these. Me avoid develop simply huge everything since town.',
    'email': 'dorothysparks@example.org',
    'phone_number': '+1-611-367-6995x6117',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Davis',
    'Cheryl Faulkner',
    'Jennifer Chandler',
    'John Moore',
    'Leslie Robinson',
    'Stephanie Hopkins',
    'Anthony Torres',
],
    'json': {
    'name': 'Joyce Ortega',
    'address': '015 Downs Lights Suite 899\nEast Colleen, DC 21920',
},
    'key98885': 'value63133',
    'key387': 'value71553',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Joseph Scott',
    'address': '1391 Steven Hill Apt. 467\nSamanthaville, TX 06865',
    'text': 'Phone it likely as. Suffer garden test end.\nTry understand physical necessary. Option risk shake feel heart from.',
    'email': 'cole20@example.org',
    'phone_number': '(584)238-8312x5397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Hernandez',
    'Lindsay Jackson',
],
    'json': {
    'name': 'Samantha Gonzalez',
    'address': '60543 Alexis Hill Apt. 199\nNew Kayla, MP 43471',
},
    'key74283': 'value47116',
    'key97073': 'value50142',
    'key17901': 'value7707',
    'key14995': 'value33198',
    'key39868': 'value91293',
    'key3475': 'value81592',
    'key88959': 'value50561',
    'key44553': 'value75792',
    'key61263': 'value94067',
    'key51443': 'value319',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Brian Humphrey',
    'address': '884 Amy Villages\nVeronicaville, MN 01136',
    'text': 'Participant short general order lead. Area like like accept onto science. Phone summer out why.',
    'email': 'johnbrown@example.com',
    'phone_number': '(524)266-9928x52414',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Arellano',
    'Zachary Jones',
    'Edward Morgan',
],
    'json': {
    'name': 'Tina Cooper',
    'address': '9783 Joshua Light Apt. 421\nAngelabury, OR 61939',
},
    'key85449': 'value59242',
    'key51207': 'value29007',
    'key28513': 'value84534',
    'key52144': 'value4922',
    'key18810': 'value17789',
    'key78620': 'value93206',
    'key45854': 'value22407',
    'key66918': 'value31672',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Kevin Schneider',
    'address': '5356 Pamela Ports Suite 175\nEast Emily, GU 04528',
    'text': 'Ago month perform American available.\nTv change new simple so. Defense determine family country think student exactly receive.',
    'email': 'robertmarshall@example.org',
    'phone_number': '(922)623-7288x2807',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Nelson',
    'Jason Silva',
    'Jessica Pittman',
    'Joseph Pennington MD',
    'Troy Cox',
    'Stephanie Johns',
    'Norma Shaw',
    'William Potts',
    'Tanya Medina',
],
    'json': {
    'name': 'Andrew Jones',
    'address': '3093 Mora Well\nDavidton, WA 28021',
},
    'key61790': 'value95458',
    'key68508': 'value39792',
    'key42413': 'value42793',
    'key41507': 'value48398',
    'key35855': 'value33595',
    'key89257': 'value71125',
    'key83369': 'value5050',
    'key93603': 'value80635',
    'key25032': 'value79777',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Emily Ruiz',
    'address': '702 Rodney River Suite 191\nSparksstad, KY 40881',
    'text': 'Give possible successful only protect produce else. Take population everybody.\nPerform case father city need follow anything. Day spend me issue.\nMouth in measure art too. Reason you nor continue.',
    'email': 'timothybird@example.net',
    'phone_number': '9712463462',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Simpson',
    'Kendra Weiss',
    'Devon Murphy',
    'Ashley Thomas',
    'Christopher White',
],
    'json': {
    'name': 'Sheri Larsen',
    'address': '10963 Davila Freeway\nNorth Chelseaview, VA 22978',
},
    'key11853': 'value79238',
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
    'RequestId': 'aadc3cd3-62ef-11f0-8ffd-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_14_175023kmBnywSI',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-128-100-2]_1752744195.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId12810021752744195Json()
    test.run_tests()
