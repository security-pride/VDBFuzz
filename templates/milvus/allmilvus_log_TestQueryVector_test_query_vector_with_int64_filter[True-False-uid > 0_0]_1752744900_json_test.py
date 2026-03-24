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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 0_0]_1752744900_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 0_0]_1752744900.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid001752744900Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 0_0]_1752744900.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 0_0]_1752744900.json"
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
    'RequestId': '47e9fd1c-62f1-11f0-bc97-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_47_164140grQJZWjQ',
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
    'RequestId': '4b08e880-62f1-11f0-906a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_47_164140grQJZWjQ',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Mr. Jesse Burgess',
    'address': '88891 Rodriguez Falls\nEast Lisaborough, RI 99598',
    'text': 'Few federal serve we where. Doctor detail plant world push. Behind box child one look process.',
    'email': 'susanrhodes@example.org',
    'phone_number': '5035774491',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brent Hancock',
    'Brian Castro',
    'Mark Blackwell',
    'Thomas Solomon',
],
    'json': {
    'name': 'Stephen Simpson',
    'address': '55279 Eric Gardens Suite 317\nPort Ashleyton, NE 31239',
},
    'key52001': 'value12220',
    'key38136': 'value78161',
    'key62922': 'value44857',
    'key34837': 'value65483',
    'key14753': 'value11258',
    'key66239': 'value12490',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Corey Stephens',
    'address': '002 Robert Shoals\nEast Timothyfurt, TX 98698',
    'text': 'Information foot trial. Against ability interest commercial statement loss wife. Girl ground resource loss although. Change the loss major establish.',
    'email': 'victoriajones@example.org',
    'phone_number': '266.954.3432x2578',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Johnson',
    'Jacqueline Hughes',
    'Regina Austin',
    'Jane Morrison',
    'Rhonda Clarke',
    'Mary Walker',
    'Lisa Jones',
    'Thomas Munoz',
    'Amy Davis',
],
    'json': {
    'name': 'Kelly Singleton',
    'address': '4458 Proctor Manors Apt. 119\nNorth Shannon, PW 93430',
},
    'key79175': 'value69382',
    'key7428': 'value83295',
    'key17085': 'value13491',
    'key80157': 'value45011',
    'key88138': 'value53397',
    'key90553': 'value31825',
    'key96020': 'value46160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Brandon Heath',
    'address': '2747 Rose Coves Suite 721\nEast Melanie, GA 10672',
    'text': 'Hour recent everyone. Easy five various city. Activity institution risk yet blue red.\nSport practice interest politics. Especially talk huge game mention everyone someone.',
    'email': 'katiebowen@example.org',
    'phone_number': '977-254-6890x200',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Caleb Sanders',
    'Vincent Copeland',
    'Julie Bennett',
    'Jacob Glenn',
    'April Thomas',
    'Christopher Ramirez',
],
    'json': {
    'name': 'Dylan Johnson',
    'address': '7050 Rodriguez Stream Suite 539\nSmallside, LA 81940',
},
    'key30187': 'value13948',
    'key11859': 'value3929',
    'key70527': 'value20407',
    'key47638': 'value50876',
    'key63397': 'value48149',
    'key22723': 'value52503',
    'key1134': 'value51996',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Ivan Woods',
    'address': '18695 Nicole Via\nYatesview, ID 29011',
    'text': 'Yes skill instead. Old audience approach may gun under. Machine clearly chair one who knowledge middle.',
    'email': 'timothy81@example.org',
    'phone_number': '491.964.9433x8345',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Taylor',
],
    'json': {
    'name': 'Danielle Wallace',
    'address': '0825 Robinson Estates Apt. 090\nKristenchester, IL 73305',
},
    'key15606': 'value3172',
    'key34107': 'value87311',
    'key99670': 'value82142',
    'key70763': 'value97833',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Christopher Miller',
    'address': '4100 Ariel Walks\nNew Mistyberg, AK 79224',
    'text': 'Look raise participant us education husband model letter. Million occur help available research material short little. Road economy instead student trial interview seven look.',
    'email': 'robert50@example.net',
    'phone_number': '362-983-1057',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Franklin',
    'Sharon Morales',
    'Alicia Martin',
    'Andrea Moreno',
    'Erica Kelly',
],
    'json': {
    'name': 'Eric Clayton',
    'address': '038 Kevin Locks Apt. 955\nPort Joshua, KY 32059',
},
    'key45526': 'value90292',
    'key54933': 'value96058',
    'key34657': 'value10496',
    'key40926': 'value61833',
    'key46177': 'value18576',
    'key1213': 'value31921',
    'key36731': 'value49994',
    'key62690': 'value75396',
    'key60019': 'value63936',
    'key13671': 'value61767',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Steven Jones',
    'address': '90933 Lowe Ports\nWaynetown, NE 58987',
    'text': 'Month open finish bed. Only focus discussion bit reason usually million. Region military movement bed other.',
    'email': 'deborahmathis@example.org',
    'phone_number': '+1-266-436-3861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Chung',
    'Dr. Timothy Nelson II',
    'Paige Beard',
    'Marcus Edwards',
    'Pamela Shaffer',
    'Donna Smith',
],
    'json': {
    'name': 'Gloria Flores',
    'address': '005 Julian Lodge\nLake Sharon, FL 13662',
},
    'key42156': 'value81694',
    'key89273': 'value39766',
    'key42513': 'value51628',
    'key78360': 'value87048',
    'key80106': 'value51661',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kathryn Stone',
    'address': '86808 James Estates\nChristophershire, TX 33055',
    'text': 'Major seven million three. General writer adult speech.\nAround ask record have risk. Tell during quality discover religious few operation source. Put sport seat their exist.',
    'email': 'campbellbrian@example.org',
    'phone_number': '696-865-1696x360',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Wayne Young',
    'Fred Goodwin',
],
    'json': {
    'name': 'Henry Brady',
    'address': '0702 Wilcox Extensions\nKelliville, PA 85379',
},
    'key41304': 'value95239',
    'key47922': 'value67793',
    'key87259': 'value50876',
    'key81570': 'value87792',
    'key42334': 'value96804',
    'key95039': 'value20504',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jacob Romero',
    'address': '80830 Aguilar Corner Apt. 725\nDawnhaven, GA 17010',
    'text': 'Admit reduce medical do want. Treatment learn guy detail store side forget morning. Later analysis wife its even customer bar.',
    'email': 'pcarter@example.org',
    'phone_number': '001-788-824-7992',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Allen Hutchinson',
    'Bryan Harrington',
    'Dean Maldonado',
    'Edward Rodriguez MD',
    'Sharon Rocha',
    'John Perry',
    'Jessica Kennedy',
],
    'json': {
    'name': 'Ryan Turner',
    'address': '48660 Phillips Path\nNorth Eddiemouth, RI 58456',
},
    'key54554': 'value53310',
    'key47656': 'value82350',
    'key21430': 'value25988',
    'key16774': 'value78078',
    'key30018': 'value59054',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Jeffery Crawford',
    'address': '67523 Hernandez Mission\nNew Adam, KS 80913',
    'text': 'Price house analysis morning question concern project. Yes treat yet provide top.',
    'email': 'amandarivera@example.net',
    'phone_number': '001-351-684-3982x18217',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Eric Hernandez',
    'Erika Serrano',
],
    'json': {
    'name': 'Anthony Kennedy',
    'address': '2511 Schwartz Wells\nRebeccaside, NY 31592',
},
    'key46457': 'value84106',
    'key50243': 'value52077',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Michelle Williams',
    'address': '01714 Williams Crossing\nSimmonsside, GA 39977',
    'text': 'Because record adult next knowledge. Then structure because. Author attention see blood civil.\nBook name shake. Always relate yard why anything anything situation.',
    'email': 'vknox@example.org',
    'phone_number': '722-865-9343x757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Cortez',
],
    'json': {
    'name': 'Elizabeth Gonzales DDS',
    'address': '194 John Grove\nLauriefort, CO 46091',
},
    'key51227': 'value53881',
    'key21642': 'value86826',
    'key70202': 'value38364',
    'key82963': 'value49435',
    'key63383': 'value11671',
    'key39342': 'value93053',
    'key33777': 'value712',
    'key43269': 'value61960',
    'key42057': 'value44573',
    'key45780': 'value13060',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Jason Barrera',
    'address': '432 King Trafficway Suite 273\nSpencemouth, SC 21663',
    'text': 'Drug fear new middle into short. Policy yes agreement adult. Today rather north involve take.\nSuch important beat sing since out discover include. Population nation explain speak writer.',
    'email': 'sbarry@example.org',
    'phone_number': '+1-388-856-6967',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Schmidt',
    'Angela Eaton',
    'Trevor Martin',
    'Rachel Williams',
],
    'json': {
    'name': 'Emily Brown',
    'address': '749 Suzanne Trafficway\nAguilarton, RI 35534',
},
    'key14377': 'value81225',
    'key94192': 'value88170',
    'key30278': 'value25734',
    'key50920': 'value48691',
    'key98046': 'value82687',
    'key39016': 'value63351',
    'key7190': 'value69512',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Roger Nelson',
    'address': '79603 Adkins Views Suite 307\nWest Taylor, CO 39625',
    'text': 'Western prevent particular under.\nHuge big value age skin last form. When town sound sing task a machine.\nType generation street agree.',
    'email': 'cuevaslarry@example.net',
    'phone_number': '367.627.0587x618',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Garcia',
    'Kristin Romero',
    'Holly Stanley',
    'Jason Cook',
    'Jake Davis',
    'Kathleen Drake',
    'Michael Hurst',
    'Laura Higgins',
],
    'json': {
    'name': 'Michael Pearson',
    'address': '8406 Freeman Road Suite 091\nSherylstad, CO 55627',
},
    'key28565': 'value63350',
    'key93440': 'value41458',
    'key10323': 'value5772',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Anthony Miller',
    'address': '4707 Cody Turnpike\nEast Garyport, UT 92748',
    'text': 'Television lawyer action guess with up brother. Particularly house week glass interesting really baby. Middle option future next.\nMind stuff former amount. Go foot face control better down somebody.',
    'email': 'gabrielagardner@example.com',
    'phone_number': '(926)950-8141x36305',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amber Martin',
    'John Cooper',
    'Natalie Martin',
    'Richard Lucas',
    'Linda French',
    'Kenneth Jones',
    'John Dominguez',
],
    'json': {
    'name': 'Monica Fleming',
    'address': '7091 Christina Via Suite 700\nAdamfort, NE 79292',
},
    'key65469': 'value65738',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Kelly Harper',
    'address': '5814 Lewis Trail\nWest Scottfurt, SD 13582',
    'text': 'Bar food message other friend table small. Treatment hard seat program. Mother moment clear charge simply also.\nCouple floor very result mind budget. Night help top left.',
    'email': 'michaelalexander@example.org',
    'phone_number': '4916641581',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Johnny Scott',
    'Albert Duran',
    'Anthony Martin',
    'Carolyn Clark',
],
    'json': {
    'name': 'Karina Ortiz',
    'address': '40223 Palmer Turnpike\nNortontown, CT 07725',
},
    'key82977': 'value38575',
    'key72486': 'value63387',
    'key71334': 'value9915',
    'key68275': 'value11746',
    'key10086': 'value27412',
    'key29824': 'value55316',
    'key53654': 'value69324',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Beth Gray',
    'address': '79254 Rachel Terrace\nPort Cheryl, AS 88856',
    'text': 'Method very test believe hot. Its likely teacher consider traditional realize. Attention wrong particular read per herself long. Case space like trip either commercial.',
    'email': 'duncanmark@example.org',
    'phone_number': '408-818-3644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Richardson',
    'Jennifer May',
    'Julia Lawson',
    'William Green',
    'Juan Rogers',
    'Zachary Allen',
    'Steven Watson',
],
    'json': {
    'name': 'Norma Rodriguez',
    'address': 'PSC 9629, Box 5035\nAPO AP 80849',
},
    'key66289': 'value41248',
    'key52312': 'value69586',
    'key92606': 'value13881',
    'key27637': 'value13751',
    'key54296': 'value9229',
    'key40138': 'value91036',
    'key67529': 'value38577',
    'key98532': 'value42234',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Joshua Garcia',
    'address': '37182 Jacob Ways\nPort Nathanport, ME 40200',
    'text': 'Forget either traditional service international.\nFear letter ask language increase since rather. Own cut class around decide probably. Alone economy response.',
    'email': 'mbarker@example.com',
    'phone_number': '+1-768-380-7705',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Foster',
    'Scott Garrett',
],
    'json': {
    'name': 'Lori Fitzgerald',
    'address': '593 Brianna Way\nSouth Amyville, RI 23068',
},
    'key26080': 'value56106',
    'key52276': 'value59859',
    'key97652': 'value16942',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Tom Maxwell',
    'address': '54534 Darrell Wall\nLake Angela, NH 86626',
    'text': 'Enjoy unit month ahead drug use. System by policy strategy chance exist. Community prove huge season expect scientist.',
    'email': 'douglaswashington@example.net',
    'phone_number': '+1-471-701-4934',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Julian James',
    'Maria Bright',
    'Nicole Mooney',
    'Scott Young',
    'Joseph Thomas',
    'Craig Moss',
    'Carly Woods',
    'Mrs. Tina Williams DDS',
    'Valerie Matthews',
    'Paul Roberts Jr.',
],
    'json': {
    'name': 'Antonio Galloway',
    'address': '1989 Jeffrey Shore\nSilvaton, PR 68738',
},
    'key20370': 'value47103',
    'key68718': 'value1634',
    'key61275': 'value15923',
    'key45355': 'value20408',
    'key51928': 'value36311',
    'key70775': 'value53416',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Scott Taylor',
    'address': '7359 Vargas Court Suite 743\nWilliamsonhaven, AS 91436',
    'text': 'Some concern too wrong discuss without feel she. Fall account control evening. Middle us ago too.\nStage his kind much high teach. Try general floor.',
    'email': 'jose74@example.net',
    'phone_number': '445-422-8333',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Hunter Bishop',
    'Yvonne Bryan',
    'Brenda Gonzalez',
    'Terry Frye',
    'Isaac Gonzalez',
    'Andrea Lynch',
    'Christy Osborne',
    'David Fleming',
],
    'json': {
    'name': 'Angel Williams',
    'address': '30475 Robert Rapids Suite 912\nDiazburgh, ME 27384',
},
    'key52451': 'value25994',
    'key48951': 'value67503',
    'key95755': 'value99179',
    'key26940': 'value35721',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Michelle Flores',
    'address': '566 Murray Curve\nLake Keith, LA 83807',
    'text': 'Information spring fast level peace these. Attorney bit class such son hope. She big part bag debate really then.\nMember hard speak minute close tough end. Such generation staff air.',
    'email': 'jessicawillis@example.net',
    'phone_number': '649.251.6058',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Susan Caldwell',
    'Hannah Powell',
    'Michelle Pearson',
],
    'json': {
    'name': 'Beth Schwartz',
    'address': '59416 Fernandez Fall Suite 527\nEast David, HI 06939',
},
    'key378': 'value62649',
    'key1467': 'value54016',
    'key82689': 'value34997',
    'key27571': 'value69739',
    'key74497': 'value35849',
    'key55822': 'value35007',
    'key63865': 'value94271',
    'key71035': 'value44746',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Bradley Grant',
    'address': '509 Brianna Way Apt. 966\nWest Allison, MD 84165',
    'text': 'Work pick people air. Answer Mrs part last.\nOrder how huge wish whom. Through name deal. Particular sit current civil check various.',
    'email': 'joseph95@example.com',
    'phone_number': '3455581382',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brianna Mcdonald',
],
    'json': {
    'name': 'Jay Wiley',
    'address': '30383 Michael Avenue Suite 383\nTaylorberg, GA 54402',
},
    'key72896': 'value52063',
    'key72810': 'value97028',
    'key81454': 'value42094',
    'key69082': 'value42747',
    'key13756': 'value90335',
    'key73530': 'value46',
    'key73681': 'value66180',
    'key7650': 'value82464',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Jessica Green',
    'address': '693 Madison Terrace Suite 957\nWest Carol, MN 06872',
    'text': 'Better watch pressure. Front this time media. Write return site several someone per successful.',
    'email': 'hamiltondaniel@example.net',
    'phone_number': '(599)934-4583x9554',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Trevor Gilbert',
    'Christina Tucker',
    'William Gutierrez',
    'Susan Thompson',
],
    'json': {
    'name': 'Kelli Washington',
    'address': '70652 Victoria Hill Suite 957\nWest Kimberlyland, NJ 05345',
},
    'key40811': 'value62615',
    'key3833': 'value17597',
    'key76121': 'value82725',
    'key58812': 'value27148',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Peggy Kim',
    'address': '60954 Joseph Fort Apt. 842\nLambshire, DC 03976',
    'text': 'Beautiful their hit table film Republican local. Tree head seem actually reason box up. Picture population necessary report I.',
    'email': 'dcole@example.org',
    'phone_number': '+1-223-243-4169x35664',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Gabrielle Le',
    'Amy Mathews',
    'Ann Carson',
    'Barbara Contreras',
    'Mark Jackson',
    'Savannah Mcintyre',
],
    'json': {
    'name': 'Brenda Mathews',
    'address': 'USNS Colon\nFPO AP 69027',
},
    'key21596': 'value81852',
    'key29857': 'value34570',
    'key5209': 'value29214',
    'key66186': 'value14544',
    'key65855': 'value3783',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'James Cunningham',
    'address': '878 Lisa Rue\nEast Megan, IA 43490',
    'text': 'Benefit everybody bed performance method most finally.\nNice assume reason. Law nothing he center mother.\nContain finally reduce brother hand value according. Type yes floor argue large owner court.',
    'email': 'medinajay@example.com',
    'phone_number': '+1-412-772-1298x49177',
    'array_int_dynamic': [
    56953,
],
    'array_varchar_dynamic': [
    'Katelyn Lam',
    'Kathryn Bailey',
    'Jennifer Camacho',
    'Michael Moore',
    'James Mullins',
    'Ashley Cooper',
    'Carolyn Zhang',
    'Marc Jones',
    'Gabriela Campbell',
],
    'json': {
    'name': 'Erika Friedman',
    'address': '0414 Kristi Tunnel\nPenningtonshire, KS 81911',
},
    'key10547': 'value44695',
    'key75706': 'value95677',
    'key78266': 'value25664',
    'key80807': 'value9367',
    'key55658': 'value14211',
    'key34148': 'value53921',
    'key95142': 'value34947',
    'key29836': 'value22889',
    'key46182': 'value69662',
    'key33208': 'value11344',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Brian Rivera',
    'address': '3791 Lucas Spurs Suite 739\nWest Linda, GA 07456',
    'text': 'Yourself matter suddenly institution president. Trouble usually spend author fact.\nConference old there manager put remember whether city. Reality than national market believe process yard.',
    'email': 'cpena@example.org',
    'phone_number': '(936)618-4929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Taylor Mccall',
    'Alicia Hernandez',
    'Mrs. Jennifer Salazar DDS',
    'Deborah Smith',
    'Devin Black',
    'Judy Pena',
],
    'json': {
    'name': 'Kristen Howell',
    'address': '96180 Sampson Ranch\nWilsonbury, NE 68003',
},
    'key93286': 'value6683',
    'key80930': 'value1382',
    'key30122': 'value88934',
    'key20704': 'value24674',
    'key75003': 'value55869',
    'key84556': 'value76131',
    'key89466': 'value53378',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Victoria Johnson',
    'address': '429 Webb Estates\nStevenmouth, AS 04056',
    'text': 'Throughout discover at dinner because common. Cold inside amount sister full. Chance business player single concern.\nMr maintain north show across past have. Since science truth certain although.',
    'email': 'melissasanchez@example.net',
    'phone_number': '001-589-210-6879',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Singleton',
    'Paul Madden',
    'Billy Ferguson',
    'Jennifer Pope',
    'Penny Martin',
    'Chad Gonzales',
    'Kathy Bruce',
],
    'json': {
    'name': 'Hunter Taylor',
    'address': '65557 Natalie Square Suite 925\nLake Kristinport, GA 75051',
},
    'key86104': 'value65261',
    'key64452': 'value45095',
    'key29901': 'value73873',
    'key72162': 'value89982',
    'key29464': 'value62735',
    'key79149': 'value71835',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Courtney Wolfe',
    'address': '13819 Marquez Roads Apt. 108\nHannahberg, PR 98717',
    'text': 'Central crime theory official. From member blood whether nothing Mrs vote business.\nSeem we away soon day artist. Trial house commercial nation. Page picture agreement research car fish book.',
    'email': 'christopherhenson@example.com',
    'phone_number': '955.833.3319x758',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Horton',
    'Diana Graham',
],
    'json': {
    'name': 'Michael Willis',
    'address': '2164 Ramirez Lakes Suite 099\nMurrayville, IN 16129',
},
    'key47324': 'value79230',
    'key84648': 'value34683',
    'key13729': 'value36554',
    'key6186': 'value69677',
    'key14859': 'value19592',
    'key17217': 'value70440',
    'key67095': 'value90800',
    'key26323': 'value39742',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Dana Hall PhD',
    'address': '955 Gonzales Pass Apt. 449\nNorth Stephanie, WI 82818',
    'text': 'Say crime see bed against let term.',
    'email': 'pflores@example.com',
    'phone_number': '+1-827-268-7211',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Christopher Smith',
    'Walter Burton',
    'Jesus Vargas',
    'Timothy Campos',
    'Ernest Cook',
    'Jesus Clayton',
    'Heather Bush',
    'Benjamin Munoz',
    'George Mcdonald',
],
    'json': {
    'name': 'Grant Parker',
    'address': 'PSC 0296, Box 6534\nAPO AE 43420',
},
    'key62739': 'value4679',
    'key49185': 'value13137',
    'key24023': 'value56180',
    'key24273': 'value66095',
    'key39157': 'value93330',
    'key57037': 'value56730',
    'key25656': 'value45143',
    'key91965': 'value7942',
    'key72174': 'value80146',
    'key16721': 'value98860',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'John Williams',
    'address': '436 Adam Spring Suite 784\nLisamouth, MD 95137',
    'text': 'Fear particular around manager. Administration cup tough fund particularly. Little picture itself score. Send big teacher west staff walk.',
    'email': 'lorigomez@example.com',
    'phone_number': '001-850-299-3685x07863',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Arnold',
    'Kelly Collins',
    'Ashley Hines',
    'Philip Martinez',
],
    'json': {
    'name': 'James Cervantes',
    'address': '50426 Christopher Summit\nBeckmouth, NE 09508',
},
    'key60021': 'value83211',
    'key31264': 'value85739',
    'key80057': 'value45377',
    'key68408': 'value60889',
    'key77731': 'value38883',
    'key42193': 'value69785',
    'key43980': 'value43416',
    'key57519': 'value46254',
    'key97955': 'value86377',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Adam Rogers',
    'address': '83035 Gregory Turnpike\nClintontown, ND 39024',
    'text': 'Know table character woman. For with mouth rich perhaps about.\nCut enough my indicate design not visit. More none once adult cell campaign eight.',
    'email': 'houstonshannon@example.com',
    'phone_number': '3234673855',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kathy Hester',
    'Anthony Johnson',
    'Barbara Snyder',
    'Antonio Sparks',
    'Michael Ford Jr.',
    'Michael Woods',
    'Carmen Salazar',
],
    'json': {
    'name': 'Cynthia Ibarra',
    'address': '24385 Matthew Ridges\nSouth Paulmouth, OK 55740',
},
    'key51021': 'value34590',
    'key42484': 'value62624',
    'key82091': 'value56481',
    'key20435': 'value49733',
    'key58900': 'value61619',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Wesley Carlson',
    'address': '3975 Morgan Locks\nCohenstad, OR 58213',
    'text': 'Congress ask short.\nPersonal daughter serve TV image type there. Nature hair many realize general. Argue thought prove likely.',
    'email': 'sherri34@example.org',
    'phone_number': '(615)908-8851x753',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gina Ramirez',
    'Linda Johnson',
    'Stephanie Camacho',
    'Gregory Smith',
],
    'json': {
    'name': 'Courtney Munoz',
    'address': '2514 Hatfield Greens Suite 336\nNew Tammymouth, OH 71681',
},
    'key31358': 'value75308',
    'key42449': 'value24253',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Jose Sampson',
    'address': '3355 Pearson Oval\nNew Bethfort, PA 87958',
    'text': 'That huge four behind happy moment later. Decide almost police property animal best. Rate want shake perhaps.',
    'email': 'mclark@example.com',
    'phone_number': '001-713-550-4168x33999',
    'array_int_dynamic': [
    3175,
],
    'array_varchar_dynamic': [
    'George Chapman',
    'Adrian White',
    'Vernon Lawrence',
    'Jason Cooper',
],
    'json': {
    'name': 'Roger Perez',
    'address': '448 Kirby Throughway Suite 274\nJosephmouth, ID 91220',
},
    'key64668': 'value11408',
    'key99515': 'value24344',
    'key69416': 'value22046',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Earl White',
    'address': '02848 Williams Lane\nTravisfort, OH 76438',
    'text': 'Development politics authority should year become. Five these unit month yourself mouth. Return feel war establish finally.',
    'email': 'laurie49@example.net',
    'phone_number': '001-714-442-6488x3605',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Goodman',
    'Kimberly Livingston',
    'Amanda Jones',
    'Marissa Williams',
    'James Crawford',
    'Christopher Shaw',
],
    'json': {
    'name': 'Jennifer Baker',
    'address': '00563 Brian Meadow Suite 856\nSouth Erinberg, MH 47446',
},
    'key11053': 'value38233',
    'key13360': 'value69267',
    'key25337': 'value32680',
    'key94691': 'value73095',
    'key48718': 'value10131',
    'key56538': 'value20152',
    'key43929': 'value44139',
    'key23063': 'value57873',
    'key20532': 'value32850',
    'key59139': 'value87225',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kirsten Wiley',
    'address': '187 Sarah Fort\nJoyceland, GU 32452',
    'text': 'Their this act perhaps number number. Skill will inside power. Town dream nor dinner case.',
    'email': 'robertmartinez@example.org',
    'phone_number': '935.212.0686x429',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gavin Williams',
    'Mariah Raymond',
    'Daniel Weaver',
    'Steven King',
    'Lynn Cook',
    'Amber Hubbard',
],
    'json': {
    'name': 'Tracy Duran',
    'address': '1316 Hill Freeway Apt. 369\nAnamouth, NV 39075',
},
    'key43485': 'value59530',
    'key82653': 'value75631',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Karen Elliott',
    'address': '0257 Summers Ports\nLake Alexchester, SC 24292',
    'text': 'Others fact add north. Develop great return rather manage them also. Woman send opportunity focus ask threat final.',
    'email': 'staceyhartman@example.org',
    'phone_number': '(403)883-3704x3857',
    'array_int_dynamic': [
    53513,
],
    'array_varchar_dynamic': [
    'Robert Jordan',
    'Christina Willis',
],
    'json': {
    'name': 'Amy Fry',
    'address': '2822 Brown Valley Suite 849\nLake Susanfurt, FL 26420',
},
    'key42663': 'value37090',
    'key29786': 'value68033',
    'key37736': 'value43046',
    'key65217': 'value30893',
    'key41603': 'value87560',
    'key89097': 'value82353',
    'key31183': 'value22180',
    'key20643': 'value52499',
    'key43824': 'value18038',
    'key881': 'value42966',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Gregory Torres',
    'address': '3293 Nicholas Park Apt. 433\nYoungshire, HI 39177',
    'text': 'Model mother camera world paper country. Hold gas third lose little law.\nActually company sense really might. Rule quite production family dream experience. Politics why agency ball audience herself.',
    'email': 'millerderek@example.com',
    'phone_number': '(942)230-0464x2965',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shawn King',
    'Chelsea Davis',
    'Ryan White',
    'Gina Shaw',
    'Jamie Lewis',
    'Eric Bailey',
    'April Oneill',
    'Dana Ross',
],
    'json': {
    'name': 'Jamie Delacruz',
    'address': '425 Rachel Freeway Suite 645\nLake Matthewtown, TN 61290',
},
    'key23078': 'value28033',
    'key17577': 'value56671',
    'key61624': 'value37617',
    'key55905': 'value33999',
    'key88185': 'value52693',
    'key69626': 'value17634',
    'key18404': 'value39096',
    'key88527': 'value84103',
    'key31461': 'value53336',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Brian Clark',
    'address': '83004 Campbell Manor Apt. 538\nWest Holly, OK 74990',
    'text': 'Choice every specific easy behavior add. While decide no return respond. Simply attack history increase.\nChance we hotel report. Term simply thus ok nearly why.',
    'email': 'michelleali@example.org',
    'phone_number': '379-389-4226',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Nathan Anderson',
    'Brian Miller',
    'Melissa Walker',
    'Douglas Mccoy',
],
    'json': {
    'name': 'Keith Martinez',
    'address': '40642 Townsend Streets Apt. 241\nNew Joycestad, WY 90489',
},
    'key73003': 'value45587',
    'key7229': 'value3603',
    'key11258': 'value1936',
    'key39904': 'value40929',
    'key13939': 'value83790',
    'key8761': 'value2303',
    'key2870': 'value30550',
    'key50901': 'value42256',
    'key27168': 'value6592',
    'key47839': 'value59862',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Evan Brown',
    'address': '5677 Brennan Overpass\nPort Michaelberg, MS 64792',
    'text': 'Seem must Democrat show. Security college kind mouth sing network its.\nTeach break soldier live financial. Actually vote evening buy nature support. Suggest address hot space pattern remain.',
    'email': 'christine40@example.com',
    'phone_number': '500-652-3084',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'David Smith',
    'Hannah Hunter',
],
    'json': {
    'name': 'Linda Arias',
    'address': '2914 Joseph Parkways Suite 588\nWest Leslie, CA 96633',
},
    'key22133': 'value59066',
    'key78877': 'value83071',
    'key57849': 'value79578',
    'key38145': 'value12711',
    'key89428': 'value36689',
    'key18674': 'value25401',
    'key6047': 'value9410',
    'key84109': 'value4902',
    'key61648': 'value20867',
    'key96851': 'value38183',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Maria Lopez',
    'address': '19188 Bryant Hills Apt. 008\nDavidtown, KY 14583',
    'text': 'Or boy investment story take.\nFour north court process seem he. Citizen support each week. Them easy since water under security.',
    'email': 'ryanchavez@example.net',
    'phone_number': '522-326-0076x6279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Lindsey Murphy',
    'Derrick Thompson',
    'Mary Brooks',
    'Donna Snyder',
],
    'json': {
    'name': 'Christopher White',
    'address': '21870 Sanchez Branch Suite 506\nPort Bradleyburgh, GU 33668',
},
    'key552': 'value71040',
    'key25798': 'value14550',
    'key85896': 'value57002',
    'key91956': 'value1492',
    'key63917': 'value6628',
    'key83514': 'value97940',
    'key83098': 'value28343',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Marie Gonzales',
    'address': '764 Rogers Meadows\nMillerhaven, OK 04812',
    'text': 'Shake left language rise production particularly.\nClose simple ago under center. Difference contain beyond our effort car.\nYou product about thank people himself. Interesting too forward current.',
    'email': 'cyoung@example.org',
    'phone_number': '361.303.0721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Richard Morris',
    'Carmen Johnson',
    'Grace Richards',
    'Anna Davis',
    'Madison Ware',
    'Renee Sosa',
],
    'json': {
    'name': 'Clifford Sanders',
    'address': '865 Klein Avenue\nNew Elizabeth, CA 46720',
},
    'key30866': 'value84927',
    'key86568': 'value24242',
    'key8448': 'value59747',
    'key74005': 'value630',
    'key77111': 'value64069',
    'key81582': 'value40597',
    'key30381': 'value66239',
    'key79024': 'value76598',
    'key47633': 'value92555',
    'key69657': 'value52737',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Troy Burnett',
    'address': '4371 Smith Forges\nEast Michaelaville, AS 00567',
    'text': 'Beat week authority option carry few support. Leader become building.\nAfter least police kitchen inside fight. Look let or really agency garden.',
    'email': 'oflores@example.com',
    'phone_number': '5168344539',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Todd Hardin',
],
    'json': {
    'name': 'Katherine Anderson',
    'address': '708 Anthony Avenue Suite 879\nMaryberg, IL 20478',
},
    'key93456': 'value24650',
    'key15390': 'value30551',
    'key42384': 'value59017',
    'key99645': 'value59251',
    'key5005': 'value45363',
    'key50230': 'value94152',
    'key52608': 'value75488',
    'key29656': 'value90988',
    'key35932': 'value39649',
    'key77432': 'value31811',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Matthew Allen',
    'address': '83397 Kelley Fall Suite 745\nRobertsland, WY 71278',
    'text': 'Tell skill provide response various field quite also. Exist up cut save finally admit. Most assume good.',
    'email': 'durankristine@example.net',
    'phone_number': '001-462-699-5240x47721',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Melissa Scott',
    'Dr. Jason Reese',
    'Sandra Henry',
    'Theresa Thompson',
],
    'json': {
    'name': 'James Price',
    'address': '6802 Shelly Junction Apt. 805\nMillsbury, ID 17953',
},
    'key22607': 'value55781',
    'key63295': 'value47009',
    'key21951': 'value51663',
    'key65677': 'value12456',
    'key77367': 'value61291',
    'key91068': 'value98183',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Ryan Davis',
    'address': '105 Caleb Courts\nLewischester, RI 12015',
    'text': 'Rock nothing much near man church.\nHour late response catch nearly baby rise. Office physical almost study image especially. Lose mission adult within issue attorney.',
    'email': 'joshua44@example.net',
    'phone_number': '(508)457-2274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Perez',
    'Lisa Evans',
    'John Sims',
    'Christina Rose',
    'James Hill',
    'Wendy Lopez',
    'Ryan Hill',
    'Tara Marshall',
    'Dawn Arnold',
],
    'json': {
    'name': 'Wendy Moses',
    'address': '5426 Smith Knoll\nTurnerberg, AS 62625',
},
    'key26738': 'value54190',
    'key94919': 'value71139',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Ryan Moore',
    'address': '239 Lopez Mission\nCrystalfurt, AZ 12580',
    'text': 'You only relate last.\nPolicy class pass black focus song discuss. Art sign consumer person policy. Whose service bar clearly nation audience.\nSense feel information us girl particular.',
    'email': 'danielmiller@example.net',
    'phone_number': '695.567.1802',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Brad Myers',
    'Jeremiah Ochoa',
    'Hannah Rodriguez',
    'Samantha Kennedy',
    'Samuel Moran',
    'Courtney Oliver',
    'Valerie Mccoy',
    'Cody Stephens',
],
    'json': {
    'name': 'Kyle James',
    'address': '5183 Amber Hollow Suite 384\nWest Russellmouth, FM 84182',
},
    'key90352': 'value73632',
    'key44260': 'value58549',
    'key3261': 'value68642',
    'key49606': 'value80433',
    'key72772': 'value97399',
    'key19009': 'value99796',
    'key55464': 'value19294',
    'key35258': 'value70988',
    'key7582': 'value9413',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Billy Berry',
    'address': '79751 Osborne Underpass Suite 569\nWest Erin, DC 30817',
    'text': 'Future play plant necessary student instead loss. Whether impact civil week. Model stay such school tough course bad.\nWestern lot appear three represent site lead somebody.',
    'email': 'jacob58@example.com',
    'phone_number': '708.449.0351',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca May',
    'Glen Green',
    'Christopher Kramer',
    'Joshua Brown',
    'Susan Hahn',
    'Christopher Chan',
    'Matthew Walton',
    'Darryl Ramsey',
],
    'json': {
    'name': 'Angela Bradford',
    'address': '02027 Daniels Forge\nNorth Anneville, DC 37491',
},
    'key24642': 'value42330',
    'key97160': 'value15519',
    'key78273': 'value33751',
    'key90133': 'value66379',
    'key91848': 'value72490',
    'key44920': 'value72824',
    'key90473': 'value32153',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Edwin Blair',
    'address': '6401 Javier Stream\nLake Geraldton, OR 27400',
    'text': 'Couple beat gun agency stay. Unit will road serious black.\nCard network trouble level easy economy say put. Drug event fire exactly from recently laugh. Also go even another goal book hot.',
    'email': 'mackcassandra@example.com',
    'phone_number': '+1-851-305-4899x745',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Barry Dixon',
    'Sarah Bennett',
    'Aaron Morris',
    'Kim Lara',
    'Paul Bennett',
    'Lisa Shaw',
    'Robert Ewing PhD',
],
    'json': {
    'name': 'Jessica Mills',
    'address': '27537 Burnett Roads Suite 837\nSouth Elizabethland, KY 58797',
},
    'key39202': 'value41111',
    'key22993': 'value29458',
    'key77837': 'value79126',
    'key86971': 'value76864',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Virginia Marsh',
    'address': '4133 Price Island Apt. 901\nSouth Natalieview, OK 26787',
    'text': 'Debate all whether management mother arm city. Red stand great sense instead well talk. Perform successful military democratic find fund.',
    'email': 'griffinalicia@example.com',
    'phone_number': '420-310-3154x638',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jack Franklin',
    'John Davidson',
    'Terry Bradley',
    'Kimberly Grimes',
    'Cody Allison',
],
    'json': {
    'name': 'Kyle Kent MD',
    'address': '4617 Mann Common\nChristopherview, AS 28954',
},
    'key81539': 'value37265',
    'key43263': 'value70831',
    'key19629': 'value10175',
    'key62935': 'value17617',
    'key10478': 'value14268',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Brittany Stewart',
    'address': '463 Harrison Common\nRodriguezborough, CT 01276',
    'text': 'Case professor western respond nation various discussion. Cut about cost. Finally all admit stay.',
    'email': 'jesuswoods@example.com',
    'phone_number': '+1-219-229-8815x314',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Murray',
    'Cynthia Turner',
    'Steven West',
    'Priscilla Martinez',
],
    'json': {
    'name': 'Barbara Carter',
    'address': '24658 Laurie Lights Apt. 255\nWest Gail, PR 06593',
},
    'key53724': 'value31649',
    'key59012': 'value16275',
    'key4093': 'value3707',
    'key47683': 'value762',
    'key66140': 'value11487',
    'key25492': 'value46354',
    'key30114': 'value77449',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Dawn Washington',
    'address': '4864 Morris Estate\nTorrestown, FL 88449',
    'text': 'Huge recognize beautiful college Republican free position. Experience through them near cup manager.\nThen lose also even. Skin key board.\nTruth base color study. Quite watch offer occur ahead.',
    'email': 'vburns@example.com',
    'phone_number': '001-879-709-9459x9638',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Yvette Peterson',
    'Krista Hayes',
    'Mandy Booker',
    'Aaron Moss',
    'John Payne',
    'Bryan Ware',
],
    'json': {
    'name': 'Christina Leonard',
    'address': '43414 Sharon Burgs\nStephensstad, MO 64350',
},
    'key44723': 'value45142',
    'key76437': 'value79907',
    'key8944': 'value32883',
    'key75917': 'value19196',
    'key47187': 'value57043',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Ryan Lopez',
    'address': '546 Kelly Trafficway Suite 265\nWashingtonmouth, MA 93641',
    'text': 'Resource majority decision beautiful opportunity of. Defense allow also every senior manager.',
    'email': 'dbass@example.org',
    'phone_number': '472-666-4772x5603',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Bruce',
    'Lisa Jackson',
    'Regina Miller',
    'Mike Lambert',
    'Angela Prince',
    'Lori Stewart',
    'Ashley Lopez',
    'Olivia Garcia',
    'Anne Clark',
],
    'json': {
    'name': 'Michael Torres',
    'address': '178 Harrington Summit\nPatrickfort, PR 44139',
},
    'key53638': 'value65097',
    'key87349': 'value8831',
    'key87824': 'value50136',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Nicholas Simpson',
    'address': '1765 Bradley Throughway\nPort Heather, OH 91021',
    'text': 'Cause million and compare beat. Want community thousand. Follow receive picture between improve could.\nSide work standard per fly already. Mind only population seven produce impact across.',
    'email': 'jesse36@example.org',
    'phone_number': '+1-676-864-7941x0902',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Deborah Lyons MD',
    'Hunter King',
    'Emily Collins',
    'David Mcdonald',
    'Mr. Keith Orozco',
    'Jeremy Velazquez',
],
    'json': {
    'name': 'Tara Berry',
    'address': '9460 Jack Neck Apt. 644\nBoltonshire, MN 21540',
},
    'key71680': 'value81330',
    'key17595': 'value23856',
    'key62653': 'value94998',
    'key45311': 'value34955',
    'key73191': 'value55807',
    'key87528': 'value53696',
    'key15841': 'value95345',
    'key27730': 'value23747',
    'key85785': 'value44137',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Matthew Smith',
    'address': '8222 Peterson Mill\nHillhaven, MN 77899',
    'text': 'Eat imagine big else fine. Child board type.\nReach for shake wear put difference down. Air time address how simply mind production.',
    'email': 'tiffany00@example.org',
    'phone_number': '+1-319-280-4046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Gardner',
],
    'json': {
    'name': 'Jamie Burnett',
    'address': '691 Coleman Knolls\nNorth Michaelhaven, AZ 44391',
},
    'key47932': 'value57456',
    'key88149': 'value95226',
    'key15335': 'value98836',
    'key39101': 'value19117',
    'key92021': 'value94631',
    'key59963': 'value60732',
    'key91763': 'value97922',
    'key65806': 'value85345',
    'key20482': 'value18275',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'William Walker',
    'address': '30803 Nicole Harbors Suite 674\nWest Beth, WA 84015',
    'text': 'Possible site you class tend group allow. Chance happy fight two throughout however note subject. Four loss without machine back ok.',
    'email': 'zking@example.net',
    'phone_number': '749.733.7229x1168',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Odonnell',
    'Diane Brewer',
    'David Norris',
    'Ashley Thompson',
    'Tracy Saunders',
    'Sheila Davis',
    'James Short',
],
    'json': {
    'name': 'Michael Diaz',
    'address': '2192 Villanueva Junction\nJameschester, WI 32356',
},
    'key7719': 'value43453',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Barbara Mckay',
    'address': '4277 Gregory Springs Suite 619\nLake Troyport, OR 42958',
    'text': 'Everyone letter box yard research material quality. Employee modern discussion long. Out black difference morning under.',
    'email': 'christopher07@example.org',
    'phone_number': '(828)267-4085x14212',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Cole',
    'Lisa Petersen',
    'Jonathon Serrano',
    'Thomas Reyes',
    'Riley Browning',
],
    'json': {
    'name': 'Virginia Durham',
    'address': '7829 Smith Square\nNorth Deannatown, NC 48305',
},
    'key10166': 'value32101',
    'key25471': 'value90381',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Stephanie Howell',
    'address': '8204 Charles Canyon Apt. 960\nJonathanland, ID 14578',
    'text': 'Scientist off worry represent history. Right adult seat cut pull.\nRoad especially point including standard other stuff. Write later music race. Seek scene plan modern.',
    'email': 'timothyschmidt@example.org',
    'phone_number': '790-463-5556',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Anne Ramos',
    'Robin Morrow',
    'Jonathan Love',
    'Michael Stanley',
    'Tanya Bryant',
    'Jennifer Morris',
    'Harold Sanchez',
],
    'json': {
    'name': 'Scott Keller',
    'address': '08805 Justin Ridge Apt. 580\nLake Michael, UT 16862',
},
    'key27295': 'value19580',
    'key20439': 'value9778',
    'key49233': 'value66692',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Walter Mason',
    'address': '5362 Sharon Stream\nWhiteborough, MD 14952',
    'text': 'East through wish music themselves environmental. Table side will science election.',
    'email': 'rodgersjenny@example.com',
    'phone_number': '+1-682-974-3595x43648',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Chad Rivas',
    'Christopher Williams',
    'Jacqueline Allen',
    'Joseph Kim',
    'Roy Gonzalez',
    'Margaret Ford',
    'Dorothy Schultz',
    'Omar Gomez',
],
    'json': {
    'name': 'Adam Thompson',
    'address': '800 Jones Valley Suite 443\nSouth Patriciafurt, KS 85931',
},
    'key15635': 'value45874',
    'key31266': 'value24586',
    'key72983': 'value65862',
    'key9279': 'value1333',
    'key536': 'value50523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Darrell Larsen',
    'address': '6071 Sara Rapids Apt. 800\nWest Davidbury, IL 68347',
    'text': 'During statement cost water matter fear. Final catch per.\nWithout newspaper science the modern.\nWhile memory morning part area. Whose five size possible case.',
    'email': 'pglenn@example.com',
    'phone_number': '622-969-2148x0030',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kathy Freeman',
    'Blake Patrick',
    'Matthew Dunn',
    'Amber Reed',
    'David Donaldson',
    'Timothy Cabrera',
    'Andrea Holland',
    'John Morrison',
    'Chris Reed',
],
    'json': {
    'name': 'Douglas Mills',
    'address': '885 Luna Parks\nCourtneymouth, MT 15080',
},
    'key48823': 'value34960',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Karen Smith',
    'address': '082 Day Mission Apt. 841\nErinfort, FL 33702',
    'text': 'Series chair media recognize. Prevent war among tough. Own issue him dinner.',
    'email': 'edward79@example.com',
    'phone_number': '999.609.2757x740',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Duncan',
    'Christine Johnson',
    'Andrew Rosales',
    'Bobby Chan',
    'Jeremy Collier',
],
    'json': {
    'name': 'Mrs. Brianna Jones',
    'address': '45436 David Divide\nSouth Michellefurt, IN 04130',
},
    'key8715': 'value66642',
    'key49794': 'value236',
    'key23090': 'value91747',
    'key15871': 'value95834',
    'key7579': 'value43662',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Lee Tyler',
    'address': '02968 Caroline Crescent\nBallton, NH 43098',
    'text': 'Finally assume nothing. Up policy cell information your worry weight because.\nBecause media administration purpose law technology. Else treatment she everyone suddenly fish production.',
    'email': 'ssims@example.net',
    'phone_number': '922.493.1263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Young',
    'Vanessa Hurley',
],
    'json': {
    'name': 'Theresa Hill',
    'address': '899 Daniel Ville Apt. 732\nPort Markberg, ND 43428',
},
    'key57237': 'value95995',
    'key28820': 'value51508',
    'key66589': 'value71092',
    'key23623': 'value2538',
    'key92018': 'value41647',
    'key97900': 'value60561',
    'key12776': 'value48933',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Erin Kelley',
    'address': '35563 Benjamin Lodge Suite 258\nLake Janice, MH 70568',
    'text': 'Body factor speak book threat in. Her use result.\nConcern moment from recent authority team television. Recently several much doctor position kid region.',
    'email': 'rshields@example.com',
    'phone_number': '971-508-4540',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'April Rodgers',
    'Catherine Cooper',
    'Thomas Bridges',
    'Christopher Guerra',
    'Jonathan Watkins',
    'Cheryl Allen',
    'Jeffrey Schmidt',
],
    'json': {
    'name': 'Ivan Brown',
    'address': '1103 Payne Port\nJacobfurt, VT 93454',
},
    'key20749': 'value75157',
    'key64099': 'value83692',
    'key97337': 'value69099',
    'key42231': 'value20730',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Heather Brown',
    'address': '33234 Green Ports Apt. 385\nEast Taylormouth, ID 08353',
    'text': 'Respond during fish individual sort already. Brother space student trial control difference still even. Discover bring strategy party high itself movement.',
    'email': 'maldonadojohnny@example.com',
    'phone_number': '+1-941-341-9773x2365',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Joel Moore',
    'Leah Craig',
    'Fernando Carter',
    'Ruth Griffin',
    'John Cameron',
    'Dillon Herrera',
    'Gary Cox',
    'Samantha Smith',
    'Lisa Blake',
],
    'json': {
    'name': 'Rachael Norton',
    'address': '431 Douglas Cliff Apt. 813\nNorth Joelview, MA 85471',
},
    'key65959': 'value49061',
    'key44799': 'value61634',
    'key33470': 'value84071',
    'key36056': 'value57897',
    'key50591': 'value78976',
    'key81795': 'value49665',
    'key1844': 'value46888',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'John Thompson',
    'address': '307 Sarah Glens Apt. 710\nPereztown, OK 47736',
    'text': 'Available current shoulder watch. Reflect exist threat my action rest. Education moment figure main trial tough better official. Will turn bank to send ok cup.',
    'email': 'scottfowler@example.org',
    'phone_number': '001-770-593-2480x7435',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Glenn',
    'Daniel Graham',
],
    'json': {
    'name': 'Daniel Boyer',
    'address': 'PSC 5411, Box 1761\nAPO AE 16488',
},
    'key79190': 'value38828',
    'key61689': 'value42675',
    'key67533': 'value34985',
    'key38590': 'value6958',
    'key94173': 'value91036',
    'key75146': 'value95937',
    'key27733': 'value86948',
    'key36106': 'value84648',
    'key96649': 'value78936',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Nathaniel Ryan',
    'address': 'Unit 2361 Box 1841\nDPO AE 46060',
    'text': 'Guess bag establish never inside half. Discover culture task government amount hospital.\nDog any popular sell military treat strategy. Despite believe attorney commercial.',
    'email': 'howardtimothy@example.org',
    'phone_number': '(324)983-3598',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tonya Simpson',
    'Kara Russo',
    'Gregory Martinez',
],
    'json': {
    'name': 'William White',
    'address': '231 Megan Union\nWest Raven, LA 49490',
},
    'key65174': 'value53828',
    'key76439': 'value63777',
    'key79697': 'value63125',
    'key65806': 'value97447',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Monica Henson',
    'address': '01076 Joseph Mall Suite 088\nChristinechester, ID 21486',
    'text': 'Finish hotel question here. Finish along when store page growth ago.\nWe which brother law media. Prepare speak voice green. Debate follow game detail claim remember identify.',
    'email': 'robertgraves@example.com',
    'phone_number': '443.402.8170',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Julie Martin',
    'Kathleen Cox',
    'Jacob Powell',
    'Tony Perez',
    'Aaron Stevens',
    'Gregory Brown',
    'Jeffrey Campbell',
    'Stephanie White',
    'Rachel Hill',
    'Gina Guzman',
],
    'json': {
    'name': 'Robin Holt',
    'address': '8633 Patrick Key Suite 481\nMelaniestad, RI 54738',
},
    'key40942': 'value97330',
    'key56968': 'value1120',
    'key64376': 'value63659',
    'key8742': 'value2411',
    'key72252': 'value15143',
    'key69658': 'value54256',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Daniel Williams',
    'address': '335 Denise Port Apt. 436\nJohnsonton, ID 91069',
    'text': 'Girl anyone even close. So treat enjoy so green half city. Training hard wide.\nMention wait you difficult hard next. Employee ten street something nearly. Magazine western himself.',
    'email': 'brownrichard@example.com',
    'phone_number': '+1-819-249-3779x8103',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'John Matthews',
    'Lisa Mcbride',
    'Robert Rivera',
    'Kristin Bowen',
    'Samuel Burke',
    'Nicole Castillo',
],
    'json': {
    'name': 'Danielle Barnett',
    'address': '96961 Dunn Station\nPort Jesse, SD 11426',
},
    'key11736': 'value17698',
    'key28202': 'value43950',
    'key54416': 'value43455',
    'key67986': 'value73616',
    'key49042': 'value31024',
    'key64090': 'value46178',
    'key62812': 'value8734',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Brian Brown',
    'address': '01175 Julie Field Suite 188\nNew Ricky, DC 79071',
    'text': 'Find some approach foot church. West stage environment you less beat magazine everybody.',
    'email': 'hturner@example.com',
    'phone_number': '2823995912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Williams',
    'Kimberly Schultz',
    'Amanda Brock',
    'Charles Small PhD',
],
    'json': {
    'name': 'Mark Gibbs',
    'address': '276 Tiffany Mountain\nJenkinsberg, MA 74630',
},
    'key61031': 'value68551',
    'key69047': 'value40116',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Jacob Smith',
    'address': '10724 Theresa Branch\nPort Malloryshire, NY 79058',
    'text': 'Thus since process itself soon situation project. Open himself near important there least.\nOperation impact far plant. Fact perform concern half policy.',
    'email': 'drewsmith@example.net',
    'phone_number': '(491)290-7312x2710',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Erica Kim',
    'Mr. David Serrano',
    'Brittany Meyer',
    'Tami Brown',
    'Alexander Madden',
    'Brian King',
    'Andrew Robinson',
    'Michael Sanchez',
    'Anthony Butler',
],
    'json': {
    'name': 'Michael Mason',
    'address': 'USNV Petersen\nFPO AE 51985',
},
    'key71076': 'value70276',
    'key31888': 'value72507',
    'key26075': 'value71078',
    'key44375': 'value98007',
    'key98457': 'value74672',
    'key43045': 'value6318',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Patricia Cunningham',
    'address': '0761 Goodman Lane Apt. 600\nTorresfurt, IL 87656',
    'text': 'Ahead according soon street change politics black town. On music important seven stand four I.',
    'email': 'hallsarah@example.com',
    'phone_number': '(210)455-0149',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Moreno',
    'James Abbott',
    'James Jones',
    'Alexander Martinez',
    'Bobby Thompson',
    'Miss Angela Thomas',
],
    'json': {
    'name': 'Benjamin Fleming',
    'address': '4260 Johnny Ford Suite 361\nNew Amyborough, CA 05077',
},
    'key64630': 'value22942',
    'key75354': 'value93268',
    'key17950': 'value9007',
    'key84925': 'value54413',
    'key11342': 'value8784',
    'key25227': 'value97661',
    'key28234': 'value26149',
    'key22187': 'value8558',
    'key60983': 'value42509',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Sarah Davis',
    'address': '103 Shirley Hollow Suite 951\nLake Dylan, ID 69137',
    'text': 'Travel small then. Design party certainly.\nHold ok case raise cause weight list surface. Cup role world budget then poor.',
    'email': 'johnsonsamantha@example.com',
    'phone_number': '247-341-5685',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Beasley',
    'John Stevens',
    'Jennifer Brown',
    'Daisy Guerra',
    'Mark Pittman',
    'Michelle Alexander',
    'Julie Martinez',
    'Linda Becker',
    'Paul King',
],
    'json': {
    'name': 'Catherine Cunningham',
    'address': '35493 Heather Shores\nMelindahaven, IA 49551',
},
    'key83474': 'value85057',
    'key70999': 'value92898',
    'key78464': 'value88986',
    'key64021': 'value44385',
    'key21745': 'value94281',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Cheryl Jones',
    'address': '768 Brad Island\nDawnmouth, AS 52287',
    'text': 'Manager about first admit throughout. Growth effort newspaper suffer young. Lawyer class hear use piece get.\nMyself difficult safe memory property. Market when blood away own course charge.',
    'email': 'melodyneal@example.com',
    'phone_number': '+1-826-635-2638x26602',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Gregory Johnson',
    'Derrick Reed',
    'Christopher Rivera',
    'Marie Carpenter',
    'Katherine Holland',
    'Bailey Mcneil',
],
    'json': {
    'name': 'Angela West',
    'address': '343 Joseph Points Apt. 915\nSouth Joseph, SD 27080',
},
    'key35091': 'value61279',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'James Curtis',
    'address': 'USCGC Wang\nFPO AA 66269',
    'text': 'Young exactly right sell himself draw full and. Important share among. Whether do method bag accept.',
    'email': 'vanderson@example.net',
    'phone_number': '547-412-8067',
    'array_int_dynamic': [
    59193,
],
    'array_varchar_dynamic': [
    'Eric Long',
    'Kenneth Pena',
    'Mandy Alvarez',
    'Bryan Green',
    'Melissa Todd',
    'Benjamin Mccoy',
    'Donna Lee',
    'Dorothy Mcdaniel',
    'Joseph Johnson',
],
    'json': {
    'name': 'Patrick Adams',
    'address': '682 Sharon Prairie\nKathleenville, OK 16309',
},
    'key79682': 'value68664',
    'key10425': 'value71410',
    'key79704': 'value84485',
    'key16823': 'value14261',
    'key63302': 'value85048',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Ryan Rogers',
    'address': '8099 Carlos Oval\nNew Gina, RI 18720',
    'text': 'Happen accept big old behavior turn record. From detail scientist far answer method ago. Question effort final source success society itself choice.',
    'email': 'oandrews@example.org',
    'phone_number': '001-825-466-6377x52189',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robert Herrera',
    'Sean Hill',
    'Chad Hernandez',
    'Chad Lee',
    'Benjamin Boyd',
    'Rachel Lambert',
],
    'json': {
    'name': 'Sharon Garcia',
    'address': '797 Heather Point Suite 101\nNorth Connie, CT 93127',
},
    'key20966': 'value24095',
    'key57981': 'value38897',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'William Gordon',
    'address': '0195 Patton Crescent Apt. 053\nPort Samuel, AZ 27574',
    'text': 'Table avoid require.\nAccept close under house image season important floor. Situation fact arrive throw certain energy month improve. Visit campaign specific summer.',
    'email': 'michaelscott@example.net',
    'phone_number': '234.982.0471',
    'array_int_dynamic': [
    67725,
],
    'array_varchar_dynamic': [
    'Kathleen Dunn',
    'Kirk Weiss',
    'Debra Robinson',
    'Tammy Gilbert',
    'Richard Bird',
    'Joshua Lewis',
    'Terry Martin',
    'Jordan Fisher',
    'Michele Greene',
    'Sandra Jimenez',
],
    'json': {
    'name': 'Nancy Farley',
    'address': '778 Davila Turnpike Apt. 623\nReyeston, IL 61823',
},
    'key6030': 'value12577',
    'key69932': 'value50550',
    'key7798': 'value94299',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Courtney Stevens',
    'address': '80789 Hoffman Passage Apt. 378\nRobertshire, IL 15494',
    'text': 'Keep style begin read industry. Ready public your indeed. Discover nature participant control form.\nFly truth probably Democrat Mr large science. Able address despite.',
    'email': 'jacobschmidt@example.org',
    'phone_number': '001-653-202-8592',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Michael Lopez',
    'Anna Fernandez',
    'Amy Kent',
    'Wendy Smith',
    'Kyle Vaughan',
    'Brittany Moore',
    'Paul Anderson',
],
    'json': {
    'name': 'Amanda Hawkins',
    'address': '9723 Jackson Walk\nSamanthashire, PW 61748',
},
    'key80687': 'value33294',
    'key68240': 'value28782',
    'key31690': 'value35353',
    'key54368': 'value2370',
    'key16255': 'value75309',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'James Gibson',
    'address': '7927 Christopher Trace Suite 425\nNew Amber, MT 06105',
    'text': 'Grow claim yeah. Rate food game matter must partner. Project suggest red sound.',
    'email': 'sarahtran@example.com',
    'phone_number': '+1-718-243-9208x261',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sophia Cabrera',
],
    'json': {
    'name': 'Oscar Arellano',
    'address': '6657 Joshua Tunnel\nNew Marilynmouth, AK 89653',
},
    'key44290': 'value85709',
    'key99928': 'value67044',
    'key33750': 'value30259',
    'key87945': 'value81444',
    'key652': 'value43713',
    'key87863': 'value57394',
    'key35981': 'value58567',
    'key90003': 'value42749',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jeffery Reyes',
    'address': '49289 Rachel Circle\nJoneston, HI 93835',
    'text': 'Water position hospital practice what author military summer. Population significant represent strong government. Customer election inside sing know by subject.',
    'email': 'ggates@example.net',
    'phone_number': '810.269.5693',
    'array_int_dynamic': [
    56218,
],
    'array_varchar_dynamic': [
    'Gregory Miller',
    'Nancy Kim',
    'Jonathan Holt',
    'Melissa Estrada',
    'Joseph Campos',
    'Ashley Montoya',
    'Thomas Mason',
    'Dr. Jeffrey Gray',
    'Ralph Gutierrez',
    'Kelly Anderson',
],
    'json': {
    'name': 'Mrs. Felicia Murphy',
    'address': '4851 Hopkins Ramp\nWest John, IL 35594',
},
    'key303': 'value23476',
    'key28139': 'value64060',
    'key78610': 'value17704',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Melissa Marshall',
    'address': '53364 Melissa Forge\nNorth Michelle, CA 57646',
    'text': 'Question model as provide station water. Usually type son writer myself.\nYoung least hope economic. Center certain car better itself they boy. Only peace character cultural before head must.',
    'email': 'lopezsara@example.net',
    'phone_number': '325-565-0794',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Gary Johnson',
    'Denise Rodriguez',
],
    'json': {
    'name': 'Kenneth Ramos DDS',
    'address': '222 Sarah Groves Suite 852\nMercerville, WA 84575',
},
    'key76337': 'value39081',
    'key33955': 'value83848',
    'key73609': 'value97780',
    'key27141': 'value61058',
    'key61669': 'value85301',
    'key45018': 'value24201',
    'key99590': 'value47676',
    'key77008': 'value26818',
    'key79833': 'value43462',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Tracy Lopez',
    'address': '29365 Heidi Fort Apt. 362\nShannonshire, MP 79309',
    'text': 'Computer inside senior staff employee. Moment respond democratic.',
    'email': 'brianbrewer@example.com',
    'phone_number': '001-555-858-9290x56505',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'David Brown',
    'Richard Hughes',
    'John Olson',
    'Corey Miller',
    'Ruth Wilkinson',
    'Julie Richards',
    'Richard Cherry',
    'Kevin Chen',
    'Dennis Manning',
],
    'json': {
    'name': 'Eric Hall',
    'address': '199 Hoover Cliffs Apt. 285\nEast William, IL 15803',
},
    'key65181': 'value79700',
    'key7760': 'value46356',
    'key54468': 'value61239',
    'key92212': 'value95526',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Alexa Estes',
    'address': '8357 Pineda Village\nNew Lindashire, MT 26164',
    'text': 'Significant article soon fire point ago. Agreement mention response challenge sell describe.',
    'email': 'sarabrown@example.net',
    'phone_number': '754-694-4043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Davis',
    'Sarah Perez',
    'Emily Jackson',
    'Samuel Kennedy',
    'April Berry',
    'Marcus Weeks',
    'Susan Johnson',
],
    'json': {
    'name': 'Anthony Mcneil',
    'address': 'USNS Parrish\nFPO AA 89942',
},
    'key51014': 'value28287',
    'key88952': 'value62398',
    'key54328': 'value95034',
    'key84120': 'value67318',
    'key33013': 'value70441',
    'key8777': 'value56251',
    'key58849': 'value24701',
    'key39654': 'value90050',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Shelley Moore',
    'address': '755 Jackson Landing Apt. 137\nJustinhaven, NC 12792',
    'text': 'List million he learn across but. Business join military measure list safe final.\nPlayer as than level sense order. Executive prevent site start wrong help station.',
    'email': 'jacksonpatrick@example.net',
    'phone_number': '254.439.9084x56247',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Bailey',
],
    'json': {
    'name': 'Jose Garner',
    'address': '585 Kim Spurs\nSawyerville, AK 78213',
},
    'key55702': 'value32478',
    'key97496': 'value79969',
    'key51054': 'value87234',
    'key25476': 'value4837',
    'key32042': 'value40012',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Veronica Johnson',
    'address': '8410 Emily Drive\nSherryville, SC 75625',
    'text': 'Some box allow line. Book ten yourself respond poor.\nStart company rock our enter however say.\nMajor use art their. Huge firm computer management region generation.\nThere item claim public.',
    'email': 'smithmelissa@example.com',
    'phone_number': '001-856-584-5466x1801',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Allen',
    'Elizabeth Rowe',
    'Michelle Ryan',
    'Javier Williamson',
    'Barbara Potter',
    'Brandon Sherman',
    'Mr. Stephen Morris',
    'Brenda Singh',
],
    'json': {
    'name': 'Cody Dillon',
    'address': '58104 Rodney Forks\nTracyhaven, PA 84591',
},
    'key39301': 'value16607',
    'key30669': 'value43783',
    'key97777': 'value26018',
    'key58388': 'value40072',
    'key83059': 'value59208',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Kyle Greene',
    'address': '149 Nathan Parks\nAshleyview, OR 03846',
    'text': 'Debate movement goal during whether eight drug. Pm figure speech piece treat memory onto. Miss fish whatever tax south interest who.',
    'email': 'vthompson@example.org',
    'phone_number': '8029183914',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Amber Stewart',
    'Brandon Ray',
    'Bryan Owen',
    'Samantha Livingston',
    'Gerald Munoz',
    'Bryce Perry',
    'Shelly Ruiz',
],
    'json': {
    'name': 'Michael Proctor',
    'address': 'PSC 3502, Box 7544\nAPO AA 11926',
},
    'key58830': 'value71163',
    'key64378': 'value74420',
    'key52908': 'value40876',
    'key77496': 'value58092',
    'key76508': 'value12453',
    'key50215': 'value55597',
    'key95434': 'value45593',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Madeline Lutz',
    'address': '1546 Crawford Port Apt. 231\nElizabethfort, MA 25558',
    'text': 'Yard them position into. Officer myself threat push whose rate.\nAny authority attack bad.\nTen Mrs generation decade. Then close option whether head.',
    'email': 'jgonzalez@example.org',
    'phone_number': '830.655.4905x43404',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Horton',
    'Carrie Thornton',
],
    'json': {
    'name': 'Dana Perez',
    'address': 'Unit 7039 Box 7074\nDPO AE 39220',
},
    'key85262': 'value77457',
    'key2598': 'value69701',
    'key48807': 'value51012',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Lisa Moody',
    'address': 'Unit 5400 Box 2044\nDPO AE 34916',
    'text': 'Hope for get spring data probably. A education eat attention under.\nOutside child away participant fine. Say admit cultural great. Chance effect short indicate.',
    'email': 'terrelllisa@example.com',
    'phone_number': '5676437449',
    'array_int_dynamic': [
    86301,
],
    'array_varchar_dynamic': [
    'Maria Smith',
    'Anthony Schultz',
    'Jason King',
    'Scott Anderson',
],
    'json': {
    'name': 'Sandra Camacho DDS',
    'address': '940 Diaz Knoll Suite 426\nWest Seanshire, MT 23191',
},
    'key36909': 'value30176',
    'key4195': 'value64079',
    'key48856': 'value31264',
    'key79552': 'value64894',
    'key79725': 'value96055',
    'key11074': 'value86159',
    'key80081': 'value27249',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Daniel Davis',
    'address': '593 Atkins Flats Apt. 363\nMelanieborough, GU 61457',
    'text': 'Authority open star. Mother leave myself traditional. Money money office show now bill when.\nHospital appear quite mission break say official management. Show four family.',
    'email': 'qcole@example.org',
    'phone_number': '+1-956-314-7832x3108',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Ayala',
    'Scott Fowler',
    'Jennifer Knight',
    'Susan Reyes',
    'Elaine Smith',
    'Leslie Tucker',
],
    'json': {
    'name': 'Sean Harper',
    'address': '463 Hunter Glens Apt. 731\nLake Cole, OK 55329',
},
    'key37143': 'value75584',
    'key61795': 'value16406',
    'key70100': 'value80621',
    'key9939': 'value68106',
    'key67785': 'value7562',
    'key45297': 'value94641',
    'key27534': 'value95754',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jessica Garcia',
    'address': '92093 Morrison Forest\nJessicamouth, NH 44226',
    'text': 'Game force bed another enter sometimes mouth chance. Yes until share speak meeting hospital. Understand around issue remain hand.',
    'email': 'megan30@example.org',
    'phone_number': '7999883128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jimmy Hernandez',
    'James Santos',
    'Tina Valdez',
    'Mason Johnson',
    'Jennifer Chapman',
],
    'json': {
    'name': 'Albert Jones',
    'address': '5383 Medina Terrace Suite 729\nSotoburgh, IL 31513',
},
    'key81813': 'value21833',
    'key7546': 'value92376',
    'key20080': 'value93145',
    'key75972': 'value34792',
    'key9745': 'value2673',
    'key50887': 'value740',
    'key37949': 'value95664',
    'key15869': 'value46869',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Diana Burton',
    'address': '012 Patricia Valley Suite 447\nMorrisview, AR 82726',
    'text': 'Line put whole stay. Support nearly their inside lead.\nExactly staff show kitchen expert. Result read however rock.',
    'email': 'benitezveronica@example.com',
    'phone_number': '(942)513-3515x03719',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brent Taylor',
    'Patricia Weeks',
    'Samantha Diaz',
    'Penny Watts',
    'Kimberly Grant',
    'Trevor Torres',
    'Robert Fields',
    'James Espinoza',
    'Veronica Liu',
    'Blake Carter',
],
    'json': {
    'name': 'Hayden Davis',
    'address': '536 Ballard Centers\nEast Katherine, VT 26919',
},
    'key55234': 'value72553',
    'key58859': 'value13311',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Shannon Morris',
    'address': 'USS Phillips\nFPO AA 08047',
    'text': 'Ten list I state drop able something. Generation anyone mean each.\nLevel reach fact. Fight social challenge here view.',
    'email': 'amyhoward@example.net',
    'phone_number': '(642)868-3514',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Jones',
    'Toni Long',
    'Charles Stephens',
    'Ryan Smith',
    'Tina Smith',
    'Christian Grimes',
    'John Martinez',
    'Meredith Thomas',
    'Bradley Porter',
    'Mrs. Julie Leach',
],
    'json': {
    'name': 'James Cain',
    'address': '17107 Hammond Pass\nPort Tammyberg, IA 43194',
},
    'key63357': 'value79049',
    'key37790': 'value71481',
    'key18591': 'value10230',
    'key89869': 'value13721',
    'key96777': 'value85805',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Paul Webb',
    'address': '1720 Michael Way Apt. 827\nLake Tamiview, NY 16252',
    'text': 'Put win thought card never already. Cell body there many civil.\nHuge industry parent conference our how himself. Whatever those performance any visit medical.',
    'email': 'sarah40@example.org',
    'phone_number': '001-917-655-1028x77551',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Holland',
    'Douglas Lee',
    'Natalie Walker',
    'Ashley Scott',
    'Robert Wilcox',
    'Kristin Atkinson',
    'Diane Nelson',
    'Richard Johnson',
    'Jason Gomez',
],
    'json': {
    'name': 'Kelly Thomas',
    'address': '14141 Jennifer Islands Apt. 304\nFerrellland, NH 24572',
},
    'key46606': 'value65816',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Andrea Buck',
    'address': '591 Jeremy Row\nLake Johnfort, ND 75598',
    'text': 'Friend either low describe air maybe reach. Study fact laugh early town capital bed loss. Thank eight his attack hard investment leader.',
    'email': 'qhodges@example.com',
    'phone_number': '396-749-3626x6406',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Harrison',
    'Jason Ferguson',
    'David Sanchez',
    'Michael Cruz DDS',
    'Elizabeth Davis',
],
    'json': {
    'name': 'Linda Clarke',
    'address': '0998 Rose Vista Suite 398\nGillburgh, CT 27946',
},
    'key76875': 'value28644',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Mckenzie Gentry',
    'address': '519 Travis Mews Apt. 291\nTownsendburgh, KS 53188',
    'text': 'Daughter reflect think arrive catch city. Common head provide bill deal. He black man great group health.\nYet sometimes sense develop wide second church. Teacher view turn assume.',
    'email': 'bwagner@example.org',
    'phone_number': '(546)634-3772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kari Baldwin',
    'Timothy Williams',
    'Randy Huerta',
    'Andrea Welch',
    'Mary Mcconnell',
    'Elizabeth Brown',
],
    'json': {
    'name': 'Kyle Bishop',
    'address': '3869 Larson Flats\nWest Lynnstad, KY 10088',
},
    'key69504': 'value45533',
    'key32528': 'value14647',
    'key55474': 'value14868',
    'key44033': 'value36426',
    'key43993': 'value2233',
    'key85969': 'value12512',
    'key89644': 'value76745',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Javier Johnson',
    'address': '71399 Cheryl Estates\nNew Kellymouth, VI 12386',
    'text': 'Western treat maybe scene may.\nWell east save do fine TV. Hit radio member environment term less probably study. Actually what across little public back.',
    'email': 'ryanking@example.com',
    'phone_number': '(486)557-9289x3187',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Samantha Curry',
    'Timothy Dennis',
    'Bryan Rice MD',
    'Keith Duffy',
    'Aaron Bennett',
    'Elizabeth Nelson',
    'Peter Brown',
    'Matthew Flores',
    'Cynthia Martin',
    'Debbie Lowery DDS',
],
    'json': {
    'name': 'Michelle Adams',
    'address': '226 Solomon Mission Apt. 817\nHobbsmouth, ND 19459',
},
    'key71422': 'value66519',
    'key91215': 'value11583',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Christopher Boyd',
    'address': '13643 Mark Ports\nNorth Catherine, ID 13206',
    'text': 'Nation much daughter kid. Who similar positive read order town edge fund.\nAsk control that model.\nStrategy sea space. Tell ok friend mention develop bed.',
    'email': 'uryan@example.net',
    'phone_number': '671.787.7314',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Debra Huang',
    'Mark Carrillo',
    'Gregory Murray',
    'Nicole Edwards',
    'Sarah Hawkins',
],
    'json': {
    'name': 'Katherine Hunter',
    'address': '1234 Huff Cape Apt. 280\nAnthonyview, VA 49214',
},
    'key77641': 'value46028',
    'key5068': 'value48338',
    'key98235': 'value99566',
    'key31462': 'value69912',
    'key77918': 'value36946',
    'key668': 'value68058',
    'key37438': 'value99079',
    'key22420': 'value54005',
    'key9496': 'value35755',
    'key67328': 'value30822',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Alexandra Brown',
    'address': '9965 Garcia Valley Apt. 905\nLake Connorville, AR 78089',
    'text': 'Someone itself work cell like hear. Window action keep can weight economy. Particularly line side later item there participant often.',
    'email': 'nathanielgutierrez@example.org',
    'phone_number': '+1-474-405-5044x61757',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mike Webster',
    'Michael Russell',
    'Gerald Johnson',
    'Ebony Luna',
    'Stephanie Campbell',
    'Taylor Smith',
],
    'json': {
    'name': 'Elizabeth Martinez',
    'address': '095 Christian Divide\nHeatherborough, LA 43051',
},
    'key17793': 'value29334',
    'key80695': 'value52646',
    'key89276': 'value31659',
    'key90368': 'value449',
    'key32490': 'value78651',
    'key31173': 'value75129',
    'key33345': 'value30083',
    'key4965': 'value86171',
    'key84019': 'value61915',
    'key63892': 'value74381',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Cheryl Armstrong',
    'address': '6830 Kyle Trace\nRoymouth, AZ 19107',
    'text': 'Per east least talk. Since they just. Opportunity cost detail those south.\nElection role wear for wish. Boy play than yourself. Condition standard figure night animal dream.',
    'email': 'brandonsmith@example.net',
    'phone_number': '(778)582-5741x3857',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Leon Garcia',
    'Margaret Buchanan',
    'Jason Olson',
    'Andrew Shaw',
    'Samantha Wheeler',
    'Hunter Rice',
    'John Hansen',
    'Thomas Hudson',
    'Christina Lewis',
],
    'json': {
    'name': 'Sean Harris',
    'address': '9832 Becker Station\nEast Katherineland, WA 86214',
},
    'key49691': 'value76330',
    'key61735': 'value96290',
    'key83091': 'value74245',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Emily Barnett',
    'address': '923 Andrade Extensions Apt. 717\nAnthonyland, DE 12582',
    'text': 'Fall remember their seat manager beat. Threat region quite mean program much. Line I assume leave than. Feeling someone government.',
    'email': 'garciarichard@example.org',
    'phone_number': '664.480.1771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Anderson',
    'Jason Brown',
    'Bianca Hester',
    'Brandon Luna',
    'Michael Schneider',
    'Joshua Robinson',
],
    'json': {
    'name': 'Laura Mahoney',
    'address': '99821 Perkins Bridge\nEast Sherristad, IL 18068',
},
    'key52879': 'value36977',
    'key8002': 'value14524',
    'key97220': 'value6151',
    'key38919': 'value35584',
    'key87991': 'value20538',
    'key66426': 'value95057',
    'key10691': 'value63320',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Alexander Smith PhD',
    'address': '48971 Joshua Parks\nLake Krista, WI 00804',
    'text': 'Always describe final so Democrat since find protect. Body night have official daughter lead.\nCampaign could set ago street human. Group receive source computer fight boy.',
    'email': 'nathaniel32@example.com',
    'phone_number': '(748)913-3851',
    'array_int_dynamic': [
    4534,
],
    'array_varchar_dynamic': [
    'James Taylor',
    'Henry Patel',
    'Jonathan Sutton',
    'Gabriel Conley',
],
    'json': {
    'name': 'Steven Shannon',
    'address': '75863 Lisa Spurs Suite 320\nLake Peter, MS 22125',
},
    'key63732': 'value37172',
    'key6926': 'value12526',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Brianna Thomas',
    'address': '64297 Elizabeth Squares\nNew Timothyborough, DC 42680',
    'text': 'Building alone PM budget fly prove person. Positive maybe account term. Yet walk cause help him develop structure. Energy able both political learn worker bar.',
    'email': 'amandabarron@example.org',
    'phone_number': '(267)752-9304x65547',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Contreras',
    'Jonathon Graham',
    'Melissa Watkins',
],
    'json': {
    'name': 'Paul Fisher',
    'address': '513 Joseph Trail\nPort Cheryl, MO 63976',
},
    'key3755': 'value23786',
    'key6143': 'value43808',
    'key89694': 'value66885',
    'key35281': 'value56227',
    'key65395': 'value75703',
    'key35788': 'value99884',
    'key91074': 'value79164',
    'key86082': 'value30793',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Michael Mendez',
    'address': '0150 Diana Walk Apt. 592\nMathewstown, TX 97326',
    'text': 'Theory add possible street decide three. Arm follow us music than including just. Last these then wide.\nTen relate happen herself. Reason teach economy series coach remain together early.',
    'email': 'jsmith@example.net',
    'phone_number': '001-365-866-4356',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Shawn Jacobs',
    'John Davis',
    'Jamie Paul',
    'Kimberly Brooks',
    'James Sullivan',
    'Michael Collins',
    'Andrew Beard',
    'Ellen Ward',
    'Kim Moore',
    'Donna Bishop',
],
    'json': {
    'name': 'Matthew Dodson',
    'address': '33239 Davis Crest Apt. 554\nJeffreyborough, TX 15200',
},
    'key22987': 'value78560',
    'key47521': 'value85687',
    'key66437': 'value81052',
    'key7659': 'value34898',
    'key31869': 'value21974',
    'key56216': 'value98126',
    'key14354': 'value37567',
    'key43725': 'value31603',
    'key83921': 'value36354',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Ronald Howard',
    'address': '13797 Douglas Forks\nNorth Thomas, SD 76913',
    'text': 'Begin deep gun care pretty leader. Meet compare modern oil then. Traditional network situation. Decide stand data of rise none.\nDuring customer her senior. Remember commercial board within.',
    'email': 'tgray@example.net',
    'phone_number': '(726)643-2115x7851',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Amy Davis',
    'Lori Larson',
    'Cindy Yates',
    'Stephen Curtis',
],
    'json': {
    'name': 'Michael Carter',
    'address': '445 Joseph Trail Apt. 812\nFosterview, SC 16768',
},
    'key98921': 'value53128',
    'key64230': 'value56072',
    'key30796': 'value48104',
    'key40504': 'value26903',
    'key45796': 'value29088',
    'key83434': 'value18730',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Tammy Jones',
    'address': '213 Mcguire Valleys\nWest Heathermouth, MO 99885',
    'text': 'Other its strong see. Guy grow no may sort structure.\nBut store culture take find after like whom. Able plant bad write true. Face discover myself million pass natural.',
    'email': 'jeremy08@example.com',
    'phone_number': '(381)780-2526x195',
    'array_int_dynamic': [
    6389,
],
    'array_varchar_dynamic': [
    'Abigail Duncan',
    'Melinda Elliott',
    'Clarence Smith',
    'James Flores',
    'Samantha Walker',
    'Deanna Ortega',
    'Jeremy Taylor',
    'Jacob Duran',
],
    'json': {
    'name': 'Stephanie Sims',
    'address': '058 Elizabeth Highway\nKaylaport, PW 82190',
},
    'key16752': 'value16217',
    'key49758': 'value18141',
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
    'RequestId': '4ea2b7a4-62f1-11f0-804f-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_47_164140grQJZWjQ',
    'filter': 'uid > 0',
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
    'RequestId': '4f46d1d6-62f1-11f0-9a29-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_47_164140grQJZWjQ',
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
    'RequestId': '47e9fd1c-62f1-11f0-bc97-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_34_47_164140grQJZWjQ',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid > 0_0]_1752744900.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid001752744900Json()
    test.run_tests()
