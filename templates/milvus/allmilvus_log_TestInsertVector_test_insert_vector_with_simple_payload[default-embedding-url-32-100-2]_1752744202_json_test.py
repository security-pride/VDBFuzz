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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-100-2]_1752744202_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-100-2]_1752744202.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl3210021752744202Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-100-2]_1752744202.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-100-2]_1752744202.json"
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
    'RequestId': 'af2c0b52-62ef-11f0-a02a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_21_408923oxaiNDYg',
    'dimension': 32,
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
    'RequestId': 'af4e4fd1-62ef-11f0-80bf-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_21_408923oxaiNDYg',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Jenna Farley',
    'address': '51548 Jennifer Creek Apt. 003\nAngiefurt, MH 84730',
    'text': 'Page speak which opportunity share south business. Water catch manager skill. Without so almost game.\nThen guess develop western community. Past side many radio idea century room body.',
    'email': 'gainestheresa@example.org',
    'phone_number': '906.616.0182',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Dennis Barron',
    'John Jackson',
],
    'json': {
    'name': 'Jeffrey Holmes',
    'address': '0718 Christian Springs\nAngelaland, WV 60814',
},
    'key80289': 'value63515',
    'key63637': 'value106',
    'key65088': 'value52018',
    'key20543': 'value73464',
    'key38389': 'value11106',
    'key55270': 'value72406',
    'key13795': 'value98534',
    'key74509': 'value50321',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Ralph Espinoza',
    'address': 'Unit 4936 Box 7469\nDPO AP 53268',
    'text': 'Take best arrive half TV. Would every scientist capital common strategy organization. What cell off.',
    'email': 'ambergarza@example.org',
    'phone_number': '456.788.1465x81411',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Campbell',
    'Brian Macdonald',
    'Brenda Stephens',
    'Dana Kim',
    'Becky Taylor',
    'Julie Rivera',
    'Janet Lee',
    'Andrea Carter',
],
    'json': {
    'name': 'April Jones',
    'address': 'PSC 8895, Box 2399\nAPO AA 85547',
},
    'key19447': 'value59674',
    'key91468': 'value98439',
    'key45489': 'value57651',
    'key91406': 'value31696',
    'key72070': 'value39595',
    'key26627': 'value63680',
    'key70959': 'value96078',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'David Thompson',
    'address': '078 Kelly Drive\nWest Racheltown, OK 76066',
    'text': 'Rest shoulder rule. Feel leg owner. Something again people least same suggest.\nYard left serve. Manager more consider.',
    'email': 'randyscott@example.net',
    'phone_number': '246-539-9173x03016',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Frank Juarez',
    'Gabriel Johnson',
],
    'json': {
    'name': 'Jack Brown',
    'address': '6346 Allen Plains Apt. 915\nAaronmouth, VI 06866',
},
    'key62179': 'value18756',
    'key61749': 'value86840',
    'key63587': 'value73185',
    'key12516': 'value40364',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Christopher Miller',
    'address': '3517 Lloyd Spurs Suite 387\nMichelefurt, SD 84820',
    'text': 'Bag direction understand some eye popular three. Meet computer choose character police.\nAcross school right bill ready within chair.',
    'email': 'butlerjames@example.net',
    'phone_number': '842.548.2689x8557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Bethany Miller',
    'Rebecca Henry',
    'Miranda Holden',
    'Cheryl Barton',
    'Casey Clark',
    'David Hines',
    'Matthew Sullivan',
    'Sharon Smith',
    'Elizabeth Smith',
],
    'json': {
    'name': 'Kari Kim',
    'address': 'USS Singh\nFPO AE 40957',
},
    'key37625': 'value69411',
    'key41686': 'value97479',
    'key34561': 'value21018',
    'key85032': 'value93672',
    'key75825': 'value9822',
    'key69472': 'value69431',
    'key30816': 'value27172',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Sarah Brown',
    'address': '0195 Colon Fords Apt. 730\nGriffinfurt, NC 82419',
    'text': 'Total some million hit position as. Training board use population company. Participant sure start field.',
    'email': 'riggsandre@example.com',
    'phone_number': '365-320-6921x015',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Autumn Cline',
    'Lisa Salazar',
    'Tanner Rodriguez',
    'James Newman',
    'Jessica Howell',
],
    'json': {
    'name': 'Stephanie Woodward',
    'address': '865 Crystal Spur Apt. 316\nNorth Brianbury, TN 47850',
},
    'key12451': 'value18111',
    'key34088': 'value80112',
    'key55037': 'value54054',
    'key37362': 'value68354',
    'key19891': 'value9249',
    'key45128': 'value17924',
    'key9062': 'value44330',
    'key3352': 'value68914',
    'key39796': 'value55864',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Brett Villarreal',
    'address': '207 Joseph Neck\nRyanbury, MI 52776',
    'text': 'Phone scientist general less no unit. Experience training fly she guess. Answer week during actually detail which we success. And stay adult style lawyer plant decide.',
    'email': 'larry07@example.net',
    'phone_number': '(658)546-2506x23789',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ruth Contreras',
    'Kristy Dean',
],
    'json': {
    'name': 'Shawn Miller',
    'address': '4271 Steve Way\nDenisechester, KY 53514',
},
    'key18050': 'value16989',
    'key99166': 'value79461',
    'key53445': 'value75956',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Victoria Gilbert',
    'address': '205 Kimberly Mill\nLindaville, ME 71548',
    'text': 'Help store total not bank high. Some issue idea story create star. Model industry mean data morning. Necessary theory year space growth.',
    'email': 'tiffanygomez@example.com',
    'phone_number': '856-912-1078x90778',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michael Graham',
    'Adam Mcgrath',
    'Shari Golden',
    'Louis Swanson',
    'Philip Carter',
    'Nathan Sanchez',
],
    'json': {
    'name': 'Michael Hurst',
    'address': '54128 Mercer Isle\nNew Kathy, SD 09278',
},
    'key13089': 'value40675',
    'key29478': 'value57510',
    'key90129': 'value48800',
    'key60482': 'value25770',
    'key41352': 'value77081',
    'key50177': 'value2419',
    'key29954': 'value50510',
    'key27628': 'value44102',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Angel Sims',
    'address': '519 Edward Extension\nRobersonburgh, KS 60980',
    'text': 'Say whether meet baby thank behind field. Work administration amount interesting economic like first trial. Work station speak work article.\nRealize most ten thought let.',
    'email': 'jacquelineroberts@example.org',
    'phone_number': '+1-475-275-2705x13823',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jason Lane',
    'Victor Williams',
    'Patricia Green',
    'Christie Cummings',
],
    'json': {
    'name': 'Jordan Anderson',
    'address': '9173 Williams Cape Suite 766\nAlyssaville, SC 09736',
},
    'key42923': 'value96503',
    'key43185': 'value9716',
    'key53913': 'value2323',
    'key25864': 'value89123',
    'key11131': 'value23622',
    'key2575': 'value90695',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Robert Sweeney',
    'address': '528 Antonio Expressway\nLake Steven, VT 39569',
    'text': 'Authority behavior every direction high laugh believe. Same argue now these. Them happen pay professor church very five two.',
    'email': 'kathrynbarry@example.net',
    'phone_number': '3907290674',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Benjamin Morris',
    'Melissa Morris',
    'Joseph Hobbs',
    'Chris Huber',
    'Robert Nelson',
],
    'json': {
    'name': 'Brittney Weber',
    'address': 'USCGC Garner\nFPO AP 08181',
},
    'key5552': 'value1034',
    'key11529': 'value93428',
    'key50912': 'value23236',
    'key70400': 'value67484',
    'key67106': 'value47358',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Christian Webster',
    'address': '093 Sandy Street\nNorth Julianbury, AK 72164',
    'text': 'Person society general head throughout maintain. Leave run toward dark central.\nScore feeling meeting. Itself similar series step week together situation seat. Financial nature also trial.',
    'email': 'michaelallen@example.org',
    'phone_number': '(582)398-8741',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Preston Morgan',
    'Nicholas Luna',
    'Mrs. Carolyn Porter',
    'Miss Nicole Smith',
    'Rodney Clayton',
    'Heidi Ward',
    'Amy Williamson',
    'Keith Gardner',
],
    'json': {
    'name': 'Jeff Rodgers DVM',
    'address': '6389 Kelly Valleys\nOlsonchester, MO 37637',
},
    'key29160': 'value18994',
    'key54521': 'value4019',
    'key94694': 'value51533',
    'key95214': 'value31623',
    'key97661': 'value41224',
    'key64862': 'value40448',
    'key37974': 'value41915',
    'key35415': 'value62079',
    'key64759': 'value51236',
    'key50616': 'value59005',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Rachel Andrews',
    'address': '86281 Sophia Highway Suite 867\nLake Michelle, ME 40094',
    'text': 'Culture center pull shake small image later she. Something environmental some area. Finish wall effect add section.\nSummer arm physical coach. Agent everything woman identify make.',
    'email': 'travisgrimes@example.net',
    'phone_number': '(481)228-8084x731',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Montes',
    'Jane Ross',
],
    'json': {
    'name': 'Travis Logan',
    'address': '2859 Lindsay Shoals\nMaryfurt, MT 39819',
},
    'key89409': 'value22816',
    'key90570': 'value18710',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Shannon Newman',
    'address': '2845 Pugh Pines Apt. 611\nEast Charlesbury, NE 88320',
    'text': 'Expert head eat someone fund still eight activity. Wear against challenge final environmental present.\nBeat computer attorney yet yeah. Trial he interview magazine on. Everyone treatment woman store.',
    'email': 'ryanjackson@example.org',
    'phone_number': '(892)715-3741x88874',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Reyes',
    'Katelyn Valencia',
    'Christina Morris',
    'Anthony Prince',
],
    'json': {
    'name': 'Daniel Fields',
    'address': '091 Linda Run\nEast Mckenzie, DE 86034',
},
    'key69806': 'value396',
    'key24590': 'value49960',
    'key87920': 'value49552',
    'key98737': 'value1063',
    'key13013': 'value56994',
    'key59865': 'value72159',
    'key48718': 'value24190',
    'key72457': 'value92042',
    'key99299': 'value23478',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Jason Smith',
    'address': 'USNS Jones\nFPO AP 71883',
    'text': 'Operation effect traditional live worry go. Leg hand center herself rate second. Own indicate finally sure enough end. Continue close class marriage organization.',
    'email': 'shelly02@example.org',
    'phone_number': '001-929-969-4313x33403',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Megan Freeman',
],
    'json': {
    'name': 'Brian Potts',
    'address': '4239 Stevens Cape Apt. 516\nLisastad, UT 54452',
},
    'key62211': 'value26293',
    'key48049': 'value11980',
    'key29742': 'value85226',
    'key58418': 'value9492',
    'key88780': 'value96350',
    'key52539': 'value48446',
    'key43271': 'value27258',
    'key41688': 'value50394',
    'key36424': 'value61208',
    'key32893': 'value65044',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Benjamin Roy',
    'address': '95842 Erika Brook Suite 233\nPort Adrianborough, UT 17767',
    'text': 'Family mean interesting win range performance. Talk guy bag chair add actually.\nMy here you clear work student truth. Paper beautiful or thank film. Human participant everything realize traditional.',
    'email': 'srivera@example.org',
    'phone_number': '775-622-9218',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Ray',
    'Alejandro Thomas',
    'Katie Campbell MD',
    'Heidi Mcintyre',
    'Steven Estrada',
    'George Brown',
    'Kyle Hudson',
],
    'json': {
    'name': 'Lynn Green',
    'address': '561 Shaw Brooks Apt. 818\nEast Deannamouth, GU 05339',
},
    'key39976': 'value98140',
    'key95053': 'value94534',
    'key46206': 'value75883',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Lucas Garcia',
    'address': '53265 Pedro Course Suite 942\nNorth Tiffanyshire, PA 58385',
    'text': 'Performance alone small accept manage now contain image. Everybody name training word property effort leave. Tonight nothing write local.',
    'email': 'kathleen49@example.net',
    'phone_number': '001-830-321-2361x82483',
    'array_int_dynamic': [
    93045,
],
    'array_varchar_dynamic': [
    'Laura Strickland',
],
    'json': {
    'name': 'Caitlin Hale',
    'address': 'USNV Sweeney\nFPO AE 86360',
},
    'key88336': 'value43609',
    'key95535': 'value67902',
    'key33842': 'value9247',
    'key36229': 'value25114',
    'key18738': 'value15077',
    'key80386': 'value97215',
    'key54998': 'value6690',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Casey Johnson',
    'address': '719 Kimberly Walk Apt. 381\nGarymouth, IN 24891',
    'text': 'Heavy experience animal whose service quickly hair. Raise Mr start unit. Me sign lot idea not suffer toward.',
    'email': 'torresmaria@example.org',
    'phone_number': '+1-202-322-7945x885',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robert Ruiz',
    'Julia Sawyer',
    'Matthew Johnson',
    'Andrew Flores',
    'Chelsea Ruiz',
],
    'json': {
    'name': 'Mrs. Julia Williams PhD',
    'address': '77645 Hester Mountain\nEast Nicoleberg, ND 37747',
},
    'key8999': 'value82869',
    'key28323': 'value70630',
    'key44647': 'value39040',
    'key57407': 'value84242',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Ronnie Lee',
    'address': '9231 Moss Light Suite 813\nAlyssabury, CT 31839',
    'text': 'Difference build media player sure. Next without high run. Test yeah it baby everyone than. Prevent focus certain probably.',
    'email': 'catherinepennington@example.net',
    'phone_number': '696.860.5902x855',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Brennan',
    'Amber King',
    'Laura Houston',
    'Andrea Ochoa',
    'Darryl Dalton',
    'Annette Gibson',
    'Raven Williams',
    'Gregory Wright',
    'Ashley Kelly',
],
    'json': {
    'name': 'Kathleen West',
    'address': '530 Ross Harbor Suite 942\nScottshire, CA 69230',
},
    'key97088': 'value99404',
    'key87460': 'value47460',
    'key14330': 'value91641',
    'key79672': 'value6712',
    'key97527': 'value51743',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Nicholas Small',
    'address': '47388 Martinez Courts\nSouth Mark, SD 57386',
    'text': 'Money individual police husband how because. Market economic through home him every particularly bar. Offer suggest sense another.',
    'email': 'aroy@example.org',
    'phone_number': '(242)615-0355',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Cox',
    'Molly Harris',
    'Mr. Andres Golden',
    'Misty King',
    'Michele Griffin',
    'Rebecca Norton',
    'Ian Price',
    'Scott Pennington',
    'Colleen Santiago',
    'Katherine Young',
],
    'json': {
    'name': 'Andrew Hall',
    'address': '5807 Patricia Divide\nWest Andreastad, TN 04687',
},
    'key90319': 'value9595',
    'key14485': 'value85278',
    'key77341': 'value9451',
    'key14762': 'value91478',
    'key82457': 'value8338',
    'key91780': 'value96212',
    'key338': 'value32468',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Ebony Glover',
    'address': '96874 Kyle Ranch\nNorth Johnton, ID 06547',
    'text': 'Capital include western add. Reason laugh candidate small during.\nSkin company population such. Air half today assume behavior view. Between threat another.',
    'email': 'jonathanjohnson@example.com',
    'phone_number': '+1-509-458-7027x8576',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Mathis',
    'Brandon Baldwin',
    'Sandra Dean',
    'James Salazar',
    'Michelle Chavez',
    'Kyle Simon',
    'Robin Torres',
    'Samantha Gutierrez',
],
    'json': {
    'name': 'Lori Webster',
    'address': '7220 Danny Mission Apt. 635\nTraceyberg, MT 58756',
},
    'key93957': 'value64714',
    'key80595': 'value88022',
    'key75261': 'value59526',
    'key39649': 'value71635',
    'key2773': 'value89447',
    'key86639': 'value82625',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Kelly Ayers',
    'address': '71062 Owens Turnpike\nLestertown, ME 65339',
    'text': 'Authority today leg let treat standard. Reflect trip nature manager ten first human. Perhaps more keep keep here word wide. Brother commercial training professional.',
    'email': 'christophersmith@example.org',
    'phone_number': '+1-921-752-7177',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Harding',
    'Sharon Coffey',
    'Michael Mccormick',
    'Alice Meadows',
],
    'json': {
    'name': 'David Wilkinson',
    'address': '621 Holmes Mount Apt. 869\nNew Shaneside, WI 97673',
},
    'key54210': 'value99256',
    'key84256': 'value36947',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'William Logan',
    'address': '92468 Morris Ramp Suite 514\nHoffmanside, VT 28128',
    'text': 'Company great most future ahead test record. Institution avoid little among reveal military. Amount doctor daughter consider stand individual.',
    'email': 'xclements@example.org',
    'phone_number': '956-648-6948',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Garcia',
    'Jeremy Ramsey',
    'Sean Jones',
    'Leonard Lynn',
    'Richard Garcia',
    'Beth Mcneil',
    'Andre Douglas',
    'Steven Allen',
],
    'json': {
    'name': 'Alan Garza',
    'address': '071 Angela Falls\nColefurt, KS 87679',
},
    'key81827': 'value11900',
    'key74230': 'value94465',
    'key48976': 'value13776',
    'key16684': 'value94917',
    'key89559': 'value21284',
    'key65736': 'value14864',
    'key78986': 'value95458',
    'key1895': 'value87829',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Tracey Spencer',
    'address': '1723 John Turnpike Suite 150\nLake Patrick, TN 85690',
    'text': 'Ok person property star table TV plan forward. Loss training Mr amount its something their. Improve there cultural series ten child Republican.',
    'email': 'barnesheather@example.org',
    'phone_number': '(373)927-4445',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jodi Martin',
    'Mark Combs',
    'Jennifer Gibson',
    'Ashley Clay',
    'Sherry Taylor',
    'Amber Howell',
],
    'json': {
    'name': 'Donald Fischer',
    'address': '3396 Russell Circle\nRobertsstad, MP 69155',
},
    'key98000': 'value70279',
    'key78072': 'value1275',
    'key62818': 'value14846',
    'key33391': 'value34529',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Deborah Dean',
    'address': '748 Vance Forges Apt. 933\nNew Timothyton, IN 71763',
    'text': 'Onto spring head people. Wear surface interview admit. Decision still yard star modern scene option.\nTeacher watch into different. So cold night.',
    'email': 'gail89@example.com',
    'phone_number': '001-982-204-0363x3708',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christian Walker',
    'Donald Montgomery',
    'Nicole Parker',
    'Jonathan Anderson',
    'Angel Sims',
    'Barbara Smith',
    'Heather Reyes',
    'Rebecca Roach',
    'Michael Thompson',
    'James Mitchell',
],
    'json': {
    'name': 'Tina Blair',
    'address': '74735 Victoria Club Suite 040\nMcclainton, TX 55524',
},
    'key90650': 'value57552',
    'key4592': 'value41810',
    'key85411': 'value2387',
    'key9134': 'value20176',
    'key65305': 'value77502',
    'key95097': 'value14545',
    'key74497': 'value50988',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Samuel Downs',
    'address': '87075 Trevino Villages Apt. 341\nJerryport, NJ 25921',
    'text': 'Me person for attack teach accept.\nFine miss company employee work. Capital old reveal sense government discover. Five hear finally here peace.',
    'email': 'danielsmith@example.com',
    'phone_number': '654-379-1418x6102',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Larry Owens',
    'Miguel Jones',
],
    'json': {
    'name': 'Michelle Walter',
    'address': '27913 Linda Underpass Suite 151\nPort Crystalchester, MO 31044',
},
    'key59000': 'value68686',
    'key72137': 'value88664',
    'key9828': 'value69397',
    'key15090': 'value61364',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Kevin Hughes',
    'address': '047 John Forges\nEast Corybury, MN 54999',
    'text': 'Character environmental professional easy success record strong. Try card election meet stuff.',
    'email': 'jeffersondenise@example.org',
    'phone_number': '684.469.7345',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'David Hester',
    'Daniel Baker',
    'Kathy Lewis',
],
    'json': {
    'name': 'Jesse Davis',
    'address': '052 Robert Lights Suite 118\nWest Joshuaton, MA 32423',
},
    'key53010': 'value95980',
    'key99398': 'value56901',
    'key32496': 'value36826',
    'key80190': 'value98965',
    'key78626': 'value63784',
    'key65222': 'value41920',
    'key7832': 'value92543',
    'key79054': 'value17503',
    'key62129': 'value21213',
    'key21149': 'value26648',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Eric Richards',
    'address': '08842 Paula Coves Apt. 227\nLake Stacy, LA 17578',
    'text': 'List radio area one tend action somebody. Everyone class check defense. Face team radio those become.\nData seem professional language. Evening manage central season her.',
    'email': 'matthew08@example.com',
    'phone_number': '001-776-764-2450x9466',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Lane',
    'Gabriel Hill',
    'Alyssa George',
    'Gabrielle Small',
    'Robert Graham',
    'Sarah Elliott',
    'Lauren Castillo',
    'Angelica Huffman',
    'Ryan Austin',
],
    'json': {
    'name': 'Isaac Bailey',
    'address': '723 Garcia Mills\nHarristown, FL 49696',
},
    'key47598': 'value71035',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Melissa Miller',
    'address': '67959 Sanchez Overpass\nDeborahstad, MA 11134',
    'text': 'Father book brother mission cut. Myself under authority fine away. Everyone election water throw raise artist support.\nThing against see guess identify wish. Product build successful look.',
    'email': 'brittney37@example.com',
    'phone_number': '717-746-2313',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Luis Sloan',
    'John Goodman',
    'Logan Collins',
    'Jimmy Dunn',
],
    'json': {
    'name': 'Jeremy Holt',
    'address': '7474 Kari Shoals Apt. 970\nChristophermouth, UT 09862',
},
    'key6286': 'value92793',
    'key34027': 'value71678',
    'key71342': 'value66211',
    'key89185': 'value74036',
    'key57954': 'value76361',
    'key55040': 'value21910',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Rachel Hahn',
    'address': '5229 Collins Row Suite 068\nMooreport, MT 84896',
    'text': 'Employee should walk store might court.\nAlone computer office piece military reduce today. Daughter today guess hotel yes.\nFuture employee senior hard top.',
    'email': 'ismith@example.com',
    'phone_number': '896.374.7851x3829',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Mckinney',
    'Jonathan Smith',
    'Justin Hayes',
    'Cathy Black',
],
    'json': {
    'name': 'Helen Schmidt',
    'address': '01885 Carrillo Orchard\nEast Joshua, RI 99404',
},
    'key39742': 'value37557',
    'key32424': 'value1140',
    'key50442': 'value89032',
    'key82348': 'value15998',
    'key51898': 'value53520',
    'key86575': 'value9833',
    'key86035': 'value51144',
    'key66806': 'value62627',
    'key4053': 'value55388',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Pamela Durham',
    'address': '8193 Glass Court Apt. 735\nSouth Michellestad, MS 16011',
    'text': 'Dog level discuss beat employee realize decade. Discussion work international while way start none.\nSenior guy win artist. Prevent region less scientist.',
    'email': 'gutierrezandrew@example.org',
    'phone_number': '+1-571-798-2969',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Adam Pearson',
    'William Taylor',
    'Rebecca Hernandez',
    'Anna Morris',
    'Bridget Davis',
    'Peggy Bush',
    'Jonathan Richards',
    'Christopher Salazar',
    'Crystal Gregory',
],
    'json': {
    'name': 'Amber Barker',
    'address': '534 Timothy Rue Apt. 568\nElizabethborough, OR 04589',
},
    'key46986': 'value5585',
    'key16821': 'value97989',
    'key84497': 'value17945',
    'key59380': 'value73062',
    'key92305': 'value28557',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Stephen Nelson',
    'address': '37523 Contreras Fork Apt. 466\nConnieview, VT 90047',
    'text': 'Simply reflect true miss system wear. Case PM trade even risk. Order threat center itself scene level.',
    'email': 'loretta54@example.org',
    'phone_number': '+1-462-323-4669',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'April Avila',
    'Lisa Morgan',
    'Ronald Farley',
],
    'json': {
    'name': 'Henry Henderson',
    'address': 'USNS Herman\nFPO AP 58931',
},
    'key61931': 'value65808',
    'key83209': 'value1927',
    'key62255': 'value36702',
    'key57107': 'value48030',
    'key27173': 'value89799',
    'key50366': 'value88566',
    'key80349': 'value32084',
    'key23764': 'value38901',
    'key80477': 'value93076',
    'key49551': 'value6573',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Carrie Hicks',
    'address': '2338 Anderson Club\nSamueltown, PR 71913',
    'text': 'Knowledge establish light art early. Guy notice wrong. Drop call light.\nBudget property southern very behavior scene raise. Affect me century.',
    'email': 'georgejames@example.net',
    'phone_number': '608-876-9963',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Fowler',
    'Michael Young',
    'Philip Jenkins',
    'Bryan Mcdonald',
    'Nathan Garcia',
    'Donna Anderson',
    'Michael Kim',
],
    'json': {
    'name': 'Kathleen Johnston PhD',
    'address': '8723 Garcia Crossroad\nEast Eric, NE 84275',
},
    'key95578': 'value13595',
    'key53092': 'value65600',
    'key98485': 'value32987',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Alexis Christensen',
    'address': '219 Hoffman Street\nNorth Matthewside, CT 52318',
    'text': 'Pay find year lead hair. Choice hope factor consider. Cause national can mention.\nSure receive ball TV young financial then believe. Second pass unit case college all community.',
    'email': 'nathanrhodes@example.org',
    'phone_number': '001-453-651-7429x03309',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kelli Fernandez',
    'Tina Lee',
    'Julia Hernandez',
],
    'json': {
    'name': 'Erika Lopez',
    'address': '508 Anne Harbors\nNew Oliviaberg, FM 25663',
},
    'key78251': 'value26178',
    'key40810': 'value98517',
    'key24013': 'value75238',
    'key89853': 'value80623',
    'key42007': 'value2851',
    'key93433': 'value7611',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Marie Wagner',
    'address': '56001 Kim Heights\nSouth Kenneth, NE 45424',
    'text': 'Market along answer their current fight. Style myself Congress clearly.\nOfficial rock role structure plan. Future cover easy worker audience if theory. Difficult hundred training want whose work.',
    'email': 'renee41@example.net',
    'phone_number': '492.380.9099x62330',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Green',
    'Matthew Davis',
    'Angelica Vargas',
    'Gregory Powell',
    'Brendan Allen',
    'Donald Aguilar',
    'Brian Patterson',
    'Courtney Smith',
],
    'json': {
    'name': 'Robert Martin',
    'address': '515 Wright Viaduct\nStephanieside, IN 23081',
},
    'key78148': 'value5275',
    'key12906': 'value67029',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Tracy Bond',
    'address': '642 Doyle Circle Apt. 091\nWilliamston, CT 88176',
    'text': 'Society industry rich special. Movie red activity simple person control southern suffer.\nBut discover send either letter.\nThemselves none process dinner. Late yes art off upon nature professor.',
    'email': 'jamesbush@example.net',
    'phone_number': '+1-430-524-4143x600',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Mcdonald',
    'Trevor Johnson',
    'Lindsay Shepherd',
    'Jessica Esparza',
    'Carlos Kidd',
    'Ashley Hammond',
],
    'json': {
    'name': 'Kimberly Bennett',
    'address': 'USNV Davis\nFPO AE 29659',
},
    'key96726': 'value96253',
    'key48267': 'value3025',
    'key51962': 'value66793',
    'key21052': 'value58797',
    'key7767': 'value61773',
    'key71696': 'value1905',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Susan Hill',
    'address': '86298 Mclaughlin Pike Apt. 919\nCynthiahaven, MO 25587',
    'text': 'Side goal around different forget outside. Value learn artist success then those capital.',
    'email': 'yevans@example.com',
    'phone_number': '620.450.1162x673',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Matthews',
    'Amanda Brady',
    'Gabriel Allen DVM',
    'Kevin Long',
    'Robert Mathews',
    'Dr. Scott Rodriguez',
    'John Spencer',
    'Allen Gutierrez',
    'Steven Neal',
    'Sherry Schwartz',
],
    'json': {
    'name': 'Ana Estes',
    'address': '59407 Brown Grove Apt. 722\nKevinborough, FL 13604',
},
    'key39856': 'value8042',
    'key76436': 'value56024',
    'key61885': 'value87230',
    'key78604': 'value49911',
    'key52258': 'value92534',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Krystal Chan',
    'address': '2305 Ross Shores\nChristopherton, IN 80385',
    'text': 'Like low treatment page again. Speech put offer continue Mrs edge. Beat through set college.',
    'email': 'gilljose@example.com',
    'phone_number': '601-526-6101',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jason Harris',
    'Beth Sellers MD',
    'Kathleen Waters',
    'Melissa Thomas',
    'Tyler Patton',
    'Cathy Smith',
],
    'json': {
    'name': 'Natasha Anderson',
    'address': '1910 Arthur Rue\nJohnchester, PA 87781',
},
    'key78449': 'value98627',
    'key21868': 'value91198',
    'key71977': 'value2471',
    'key27761': 'value6927',
    'key86425': 'value37313',
    'key71226': 'value81751',
    'key82480': 'value65574',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Michele Willis',
    'address': '465 Gonzalez Orchard\nNorth Jeffburgh, AK 85721',
    'text': 'Woman window positive serious speech table. Each yes wear about social. New because natural money sometimes character painting cost. That near once best husband even event.',
    'email': 'frederickjennifer@example.com',
    'phone_number': '652-931-3648x918',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Leonard',
    'Ryan Thompson',
    'Denise Patton',
    'Robert Barry',
    'Lindsey Phillips',
    'James Lynch',
    'Karen Ali',
    'Russell Nichols',
    'Maria Case',
],
    'json': {
    'name': 'Joshua Smith',
    'address': '500 Brian Ranch\nNew Kimberlyton, DE 06003',
},
    'key99746': 'value1503',
    'key48803': 'value14653',
    'key21195': 'value9515',
    'key93272': 'value51089',
    'key60066': 'value19450',
    'key31635': 'value22736',
    'key73778': 'value16030',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Michaela Ruiz',
    'address': '9302 Dustin Extensions Apt. 904\nWest Carolyn, RI 93925',
    'text': 'She us camera during event. Hot hope television sure property. Already book today.\nCamera bring two perhaps major. Which step respond long future home.',
    'email': 'tcarroll@example.org',
    'phone_number': '001-867-825-4455x3394',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'William Thomas',
    'Derrick Rodriguez',
    'William Rush',
    'Ronnie Coleman',
    'Kimberly Kelly',
    'Melissa Davis',
    'Charles Armstrong',
    'Jonathan Lee',
    'Crystal Lopez',
    'Kimberly Cunningham',
],
    'json': {
    'name': 'Christopher Neal II',
    'address': '3627 Soto Knoll\nWest Matthewfurt, CA 45660',
},
    'key14952': 'value8276',
    'key24050': 'value11225',
    'key55362': 'value53267',
    'key59185': 'value30182',
    'key33196': 'value42004',
    'key5106': 'value1414',
    'key35363': 'value76725',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Ryan Smith',
    'address': 'Unit 4582 Box 2814\nDPO AP 33417',
    'text': 'Free hope term and happy. Lot enough talk main natural.\nDoor both medical get party. Red lose yeah seat. Meeting region brother lose you can many.',
    'email': 'jeffrey87@example.net',
    'phone_number': '+1-807-791-6925',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Adam Sweeney',
    'Brian Berger',
    'Heather Wade',
    'Bethany Mueller',
    'Thomas Smith',
    'Tammy Fleming',
    'Patricia West',
    'Laura Rogers',
    'Kristopher Garcia',
],
    'json': {
    'name': 'Jesse Mitchell',
    'address': '292 Tanner Fork\nPort Kathleenfurt, SC 25458',
},
    'key32832': 'value19148',
    'key21988': 'value92576',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'William Nguyen',
    'address': 'PSC 4084, Box 6240\nAPO AA 10707',
    'text': 'Involve certain store itself point. Which pretty economy during every dinner fact.',
    'email': 'rebecca02@example.net',
    'phone_number': '838.322.9487x294',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Paula Sawyer',
],
    'json': {
    'name': 'Austin Lindsey',
    'address': '703 Richardson Islands Apt. 982\nPort Haleyside, MO 00560',
},
    'key34569': 'value90269',
    'key31152': 'value70602',
    'key80861': 'value80559',
    'key1445': 'value88685',
    'key98935': 'value67266',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Matthew Carpenter',
    'address': '860 Reed Branch Suite 553\nAlvarezfort, CT 36898',
    'text': 'Upon ready this general think stock. Senior such push trial occur white. Southern other ask himself voice dinner throw. Ago loss wonder.',
    'email': 'joelhanson@example.net',
    'phone_number': '+1-904-549-3855x6512',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Brent Warner',
    'Paul Guerra',
    'Alexis Greer',
    'Emily Prince',
    'Jason Powers',
    'Laura Barnett',
    'Jody Snow',
    'Daniel Salazar',
],
    'json': {
    'name': 'Kenneth Harmon',
    'address': '0296 Rivera Dale Suite 544\nNorth Stephanie, DE 96789',
},
    'key51254': 'value25129',
    'key86342': 'value39409',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'David Wilson',
    'address': '26807 White Via Apt. 084\nDavidshire, AS 83556',
    'text': 'Despite old gun behind hold owner. Note no word high. Already ten couple.\nPeace dog why fish action west foreign information. Meeting under together message. Factor travel practice today.',
    'email': 'davidorr@example.com',
    'phone_number': '001-291-641-0820',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ellen Bailey',
],
    'json': {
    'name': 'Robert Dickerson',
    'address': '30098 Turner Field Apt. 337\nLake Mark, ID 80912',
},
    'key93889': 'value75434',
    'key65740': 'value48449',
    'key634': 'value29960',
    'key6231': 'value27419',
    'key5015': 'value58160',
    'key76159': 'value80120',
    'key3106': 'value23257',
    'key30738': 'value13776',
    'key26075': 'value42879',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Patricia Myers',
    'address': '0750 Roberta Plains Suite 060\nWest Joshua, TN 82566',
    'text': 'Really red ago sea consider lose. Organization do month lead gun various.\nEat any food truth cause sea. Modern wrong same. Realize mission yeah talk Congress.',
    'email': 'qmorgan@example.net',
    'phone_number': '(686)545-3538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Marco Daniels',
    'Brenda Jones',
    'Darren Thomas',
    'Claudia Rodgers',
    'Scott Jackson',
    'Denise Murillo',
    'Ronald Stout',
    'Joseph Rogers',
    'Tammy Allen',
    'Alexa Gentry',
],
    'json': {
    'name': 'Kenneth Weber',
    'address': 'Unit 0246 Box 2013\nDPO AE 97599',
},
    'key87074': 'value20563',
    'key30462': 'value54456',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Heidi Bailey',
    'address': '81536 Patricia Isle\nJudychester, IL 93416',
    'text': 'Stage society mind type director debate throughout. Player sure finish statement word. Plant central instead full.\nClearly citizen indicate head wish whose. Scene item free analysis work sometimes.',
    'email': 'benderabigail@example.com',
    'phone_number': '789.538.8565x2474',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Bruce Garrison',
    'Lori Miller',
],
    'json': {
    'name': 'John Rosario',
    'address': '08087 Gill Point Apt. 172\nLarashire, UT 51651',
},
    'key36875': 'value736',
    'key67275': 'value49346',
    'key34479': 'value78452',
    'key87971': 'value32916',
    'key54575': 'value27352',
    'key96143': 'value37232',
    'key18863': 'value34419',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Maria Warner',
    'address': '21379 Joseph Pine Suite 614\nWest Kellyhaven, RI 13719',
    'text': 'Since husband television down cell none most. Doctor term remain bill. Forward treat us.',
    'email': 'carlos98@example.com',
    'phone_number': '+1-586-257-2662x70764',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Johnson',
    'Robert Fisher',
    'Leslie Romero',
    'Manuel Torres',
    'Sara Saunders',
    'Mark Long',
    'Daniel Vasquez',
    'Felicia Vazquez',
    'Adam Jenkins',
    'Micheal Villa',
],
    'json': {
    'name': 'Karen Williams',
    'address': '856 Johnson Pine Suite 446\nEast Dianafurt, DE 68744',
},
    'key77951': 'value90374',
    'key3547': 'value18456',
    'key64053': 'value61198',
    'key11696': 'value55263',
    'key45682': 'value43559',
    'key51742': 'value79820',
    'key38217': 'value86182',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Kimberly Edwards',
    'address': '753 Daniels Coves Apt. 052\nDebramouth, ME 51577',
    'text': 'Hour good stop head hard stage catch feel. Girl fear be green garden middle.',
    'email': 'rcrosby@example.com',
    'phone_number': '(964)338-0044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kim Jones',
    'Daniel Mitchell',
    'Jason Young',
    'Bryan Schmidt',
    'John Byrd',
    'Robert Norton',
    'Stephen Downs',
],
    'json': {
    'name': 'Erin Gilbert',
    'address': '74203 Ashley Square Suite 921\nSmithmouth, IN 01969',
},
    'key51781': 'value70896',
    'key27609': 'value86542',
    'key57489': 'value21629',
    'key8077': 'value55108',
    'key92648': 'value47746',
    'key82231': 'value71574',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Michael Brown',
    'address': '362 Price Highway Apt. 710\nLake Daniel, MN 32066',
    'text': 'Easy write lot truth process.\nSurface heavy as around. Quickly own rule others. Difference center moment call feel.',
    'email': 'jonesjason@example.org',
    'phone_number': '7364448601',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rhonda Hart',
    'Jacob Vega',
    'Diana Rush',
    'Christina Ball',
    'Amanda Wright',
],
    'json': {
    'name': 'Michelle Fischer',
    'address': '9066 Jeff Circles Apt. 916\nSouth Jessicamouth, MH 85044',
},
    'key41816': 'value51103',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Diane Price',
    'address': 'USNS Fowler\nFPO AE 22921',
    'text': 'Father out quickly election us some. Sort manager may site Democrat common line. Age long all seat agreement.',
    'email': 'vrobinson@example.org',
    'phone_number': '+1-235-276-0462',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Carlson',
    'Laura Knight',
    'Russell Palmer',
    'Amanda Brown',
    'Jose Sampson',
    'Jennifer Martin',
],
    'json': {
    'name': 'Mariah Hansen',
    'address': '6359 Snyder Squares\nEast Barry, IL 10031',
},
    'key12739': 'value92670',
    'key32404': 'value7765',
    'key17347': 'value59090',
    'key99770': 'value82051',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Troy Brooks',
    'address': '847 Bobby Trail\nHernandezport, WV 79146',
    'text': 'Cause stop professional consider little husband offer. Executive share state present relate out. Job to candidate save.\nThen book sing head usually media. All reason economic visit technology.',
    'email': 'meyermarcus@example.net',
    'phone_number': '3688761656',
    'array_int_dynamic': [
    63387,
],
    'array_varchar_dynamic': [
    'Mark James',
    'Keith Landry',
    'Jennifer Middleton',
    'Jasmine Caldwell',
    'Crystal Miller',
    'Gregory Abbott',
    'Lauren Donovan',
],
    'json': {
    'name': 'Amber Daniels',
    'address': '1642 Michael Common\nAshleyland, AS 63495',
},
    'key84928': 'value927',
    'key68229': 'value84482',
    'key88875': 'value12386',
    'key76462': 'value62640',
    'key36238': 'value80015',
    'key39028': 'value91313',
    'key36085': 'value97575',
    'key37298': 'value29159',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Curtis Harris',
    'address': '1766 Gonzalez Junction Apt. 246\nLoribury, OK 33903',
    'text': 'Unit career know area field something life. Various base decade would. Investment effect trouble piece family.\nSister up both water. Camera president traditional door ask. Special could affect.',
    'email': 'anthonyramsey@example.net',
    'phone_number': '(617)698-9162',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Laurie Williams',
    'Lisa Hodges',
    'Marisa Patel',
    'Victor Mason',
    'Shelia Prince',
    'Ronald Alvarado',
    'Lucas Andrews',
    'Richard Harris',
    'Adam Lopez',
    'Wayne Armstrong',
],
    'json': {
    'name': 'Gloria Torres',
    'address': '34048 Carlson Station Suite 635\nSchultzview, MI 13780',
},
    'key88297': 'value75871',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Melinda Walker',
    'address': '0885 Angela Street\nMaldonadoborough, NH 72077',
    'text': 'Bed adult paper increase situation research. Arm poor newspaper.\nRoom Democrat economy she scientist church head hair. Boy conference also save full energy.',
    'email': 'keithbarber@example.com',
    'phone_number': '813.985.8385x405',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Camacho',
    'Kaitlyn Hughes',
    'Terri Henderson',
    'Sheri Li',
    'Billy Davis',
    'Joan Romero',
    'Andrea Parker',
    'Amber Brown',
    'Jennifer Zamora',
],
    'json': {
    'name': 'Warren Mccoy',
    'address': '40804 Bradshaw Isle Apt. 699\nPort Thomas, HI 17252',
},
    'key7282': 'value3330',
    'key6102': 'value51413',
    'key3530': 'value85978',
    'key43384': 'value99386',
    'key11900': 'value47754',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Heather Hayes',
    'address': '249 Alan Junction\nDanielleland, OH 83459',
    'text': 'While never benefit off attack else.\nCitizen general bed I whatever lot be. Money instead who focus.\nAlthough either media prevent house true discuss. Best marriage raise case weight floor radio.',
    'email': 'christyduke@example.com',
    'phone_number': '536-937-4031x275',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Frank Moreno',
    'Rachel Smith',
    'John Patton',
    'Krystal Campbell',
],
    'json': {
    'name': 'Thomas Barron',
    'address': '415 Lisa Mill\nEast Christopherfort, IA 81186',
},
    'key18554': 'value41080',
    'key25563': 'value41004',
    'key59522': 'value98402',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Jenny Collins',
    'address': '0470 Roy Road Suite 793\nPort Monica, NJ 12074',
    'text': 'Sense energy true town window remember. Boy evening available sometimes deal husband at. Leave cup newspaper turn bill.\nSell mission expert better.',
    'email': 'chad38@example.com',
    'phone_number': '(563)875-4162x8023',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Colleen Mitchell',
    'Tina Kirk',
    'Cynthia Nelson',
    'Catherine Anderson',
    'Alyssa Brooks',
    'Justin Flowers',
    'Thomas Garcia',
    'Jason Scott',
    'Tara Cohen',
    'Kelly Andrews',
],
    'json': {
    'name': 'David Stanley',
    'address': '63026 Scott Junction Apt. 815\nEast Jessica, IN 03507',
},
    'key2862': 'value11420',
    'key9345': 'value17904',
    'key18894': 'value92510',
    'key95627': 'value75703',
    'key89688': 'value85157',
    'key78525': 'value58050',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Dale Smith',
    'address': '276 Jennifer Neck Suite 444\nAnnettefurt, UT 20902',
    'text': 'Challenge foot whole serve professor reality attack. Wish product by skill type life commercial.\nLook discussion our can appear special nature. Take head father wife.',
    'email': 'herreraashley@example.com',
    'phone_number': '6132470163',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Christina Stephens',
    'Ashley Vasquez',
    'Matthew Reilly',
],
    'json': {
    'name': 'David Munoz',
    'address': '1582 Howell Canyon Suite 345\nEast Josephton, FL 02435',
},
    'key53157': 'value40713',
    'key94248': 'value21664',
    'key29288': 'value26203',
    'key8647': 'value94868',
    'key62272': 'value11841',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'John Wilson',
    'address': '01601 Wiggins Field Suite 988\nNancyport, MT 76460',
    'text': 'Us under whose who. Toward then avoid fight bad energy speech.\nPositive represent he vote sign. Campaign change against approach.',
    'email': 'andersonmelissa@example.org',
    'phone_number': '(494)858-2012x2215',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Fuentes',
    'Christopher Freeman',
    'Jose Howard',
    'Laurie Mcbride',
    'Malik Shaw',
],
    'json': {
    'name': 'Matthew Pearson',
    'address': '46952 Ramirez Circle\nPort Susanfort, GU 54444',
},
    'key3795': 'value33537',
    'key77760': 'value54662',
    'key78521': 'value38778',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Terry Ruiz',
    'address': '966 Jonathan Passage\nNorth Jessica, MS 13449',
    'text': 'War around benefit in even tell. Tonight management series until able shake. Safe south blood later list thought.\nTen add audience think. Push where whatever test. Not poor left hope require year.',
    'email': 'gvaldez@example.net',
    'phone_number': '723-959-4404x6274',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Diane Rice',
    'Wanda Gonzalez',
],
    'json': {
    'name': 'Sean Martin',
    'address': '72045 Lee Cliff Suite 131\nJonathanbury, GU 35103',
},
    'key9108': 'value82949',
    'key60259': 'value17744',
    'key15583': 'value59273',
    'key10709': 'value99919',
    'key69361': 'value59767',
    'key33684': 'value33527',
    'key42050': 'value90278',
    'key17863': 'value26936',
    'key8170': 'value87612',
    'key95386': 'value80408',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Mrs. Sandra Mcintosh',
    'address': '1566 Martinez Roads Suite 163\nJessemouth, FM 06801',
    'text': 'Little her why actually few third. Their management follow kitchen coach product visit. As not everybody education.\nCultural crime support some.',
    'email': 'reynoldsjason@example.net',
    'phone_number': '(570)581-0043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lee Payne',
    'Ryan Rodriguez',
    'Thomas Coleman',
    'Alexander Lawrence',
    'Ms. Andrea Rivera',
],
    'json': {
    'name': 'Danielle Davis',
    'address': '25848 Jackson Throughway\nLake Meghanland, DC 33033',
},
    'key29920': 'value77286',
    'key51167': 'value82943',
    'key30828': 'value71738',
    'key51229': 'value84047',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'John Ortiz',
    'address': '2682 Carroll Junctions Suite 267\nLake Ashleyport, NJ 64726',
    'text': 'Agreement itself woman color guess. Late add some anyone continue writer.\nSing practice couple move. Success win trial everyone another class white. Everything woman PM word final.',
    'email': 'xwillis@example.net',
    'phone_number': '2819525747',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Vazquez',
    'Michael Lewis',
    'Sarah Lowery',
    'Pamela Willis',
    'Bruce Murphy',
    'David White',
    'Amanda Russo',
    'William Crawford',
],
    'json': {
    'name': 'Wesley Brown',
    'address': '223 Willis Gardens Apt. 076\nBryanshire, SD 04743',
},
    'key20752': 'value13939',
    'key16342': 'value82198',
    'key12113': 'value65591',
    'key51218': 'value80398',
    'key92590': 'value35724',
    'key45198': 'value63881',
    'key25410': 'value14073',
    'key38711': 'value4310',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Phillip Khan',
    'address': '6506 James Highway\nDouglasville, IN 57767',
    'text': 'Speak thousand million receive do protect huge cost. Play receive social across.\nNew executive relationship. Really win east road.',
    'email': 'williamsashley@example.org',
    'phone_number': '+1-916-889-5128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Beard',
    'Sarah Arellano',
    'Robert Escobar',
    'Julie Cooke',
    'Cynthia Guzman',
    'Heather Sullivan',
],
    'json': {
    'name': 'David Vega',
    'address': 'Unit 8103 Box 0438\nDPO AP 55331',
},
    'key16998': 'value392',
    'key23272': 'value22635',
    'key63238': 'value81068',
    'key88155': 'value14070',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Paula Nelson',
    'address': '27893 Rodriguez Alley\nRosemouth, PA 87501',
    'text': 'Serious main magazine scientist. Very music low put level trip hold.\nYeah every remain improve. Better whether political trade often.',
    'email': 'sanchezmartha@example.org',
    'phone_number': '782.475.3276x58199',
    'array_int_dynamic': [
    83072,
],
    'array_varchar_dynamic': [
    'Heather Jackson',
    'Suzanne Wise',
    'Karen Kaiser',
    'Richard Jones',
    'Jeremy Schneider',
    'Mrs. Elizabeth Miller DDS',
    'Russell Martinez',
    'Angela Wilson',
    'Alicia Salas',
    'Steve Stewart',
],
    'json': {
    'name': 'Linda Day',
    'address': '5919 Hopkins Garden Suite 135\nSouth Douglasborough, UT 14873',
},
    'key94005': 'value14736',
    'key90652': 'value12491',
    'key2988': 'value22282',
    'key25790': 'value35518',
    'key36991': 'value60891',
    'key16296': 'value91752',
    'key5182': 'value77254',
    'key12539': 'value51526',
    'key6900': 'value32733',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Connor Combs',
    'address': '16433 Sara Fields Apt. 986\nAllisontown, CA 91267',
    'text': 'Ago Mr memory civil whatever career. Necessary development like tell.',
    'email': 'carternicole@example.net',
    'phone_number': '898.319.2061x028',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Walton',
    'Holly Torres',
    'Jonathan Gonzalez',
    'Brian Baker',
    'Kelli Smith',
    'Jason Wilson',
    'Samantha Yates',
    'Alicia Silva',
    'Amanda Barnes',
    'Amanda Lambert',
],
    'json': {
    'name': 'Richard Graves',
    'address': '6242 Ryan Circle\nLarryfurt, MI 51351',
},
    'key85713': 'value44405',
    'key65596': 'value41795',
    'key3980': 'value2494',
    'key78548': 'value57606',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Jennifer Wilson',
    'address': '10432 Johnson Shores\nZacharystad, AR 94683',
    'text': 'Recognize dog short. Both important happen true plan. Heart husband bar modern. Weight work law side.\nPlace wall decide some ever finally project.',
    'email': 'huertakaren@example.org',
    'phone_number': '+1-203-651-6062x4891',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Sullivan',
    'Ashley Sutton',
],
    'json': {
    'name': 'Phillip Parks',
    'address': '280 Schmidt Keys Apt. 456\nAmandaport, UT 91130',
},
    'key24204': 'value81577',
    'key18652': 'value41334',
    'key53080': 'value31948',
    'key93790': 'value55282',
    'key84442': 'value91481',
    'key77460': 'value84789',
    'key6344': 'value75263',
    'key47375': 'value77650',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Joel Peters',
    'address': '0436 Erin Spur\nNew Kyle, ID 13518',
    'text': 'Road president war or successful. Customer happy travel popular manage society recently. Within tree two too. Other dinner long enter.',
    'email': 'lrodgers@example.org',
    'phone_number': '280.924.1199',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Bryan Gonzalez',
    'Theresa Thompson',
    'Mark Cooper',
    'Cristian Murphy',
    'Jennifer Knight',
    'Douglas Hall',
    'Jessica Robinson',
],
    'json': {
    'name': 'Mary Burns',
    'address': 'PSC 8392, Box 2010\nAPO AA 69749',
},
    'key24728': 'value80213',
    'key78366': 'value98310',
    'key57684': 'value56668',
    'key54429': 'value96997',
    'key79641': 'value94814',
    'key72916': 'value67021',
    'key76664': 'value30682',
    'key77796': 'value53081',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Kelli Pace',
    'address': '61288 Mathews Walks Suite 679\nWest Tracyside, VA 47163',
    'text': 'Parent student less mission have.\nDecision throw free position while manage send most. Rather century born life story still. Mention us wind career blood drive.',
    'email': 'awashington@example.org',
    'phone_number': '(656)536-8520x79743',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Brenda Brown',
    'Lori Phillips',
    'Sara Yang',
    'Stephanie Mccarty',
    'Ryan Harris',
    'Vanessa Cox',
    'Jonathan Martinez',
    'Nicholas Walsh',
],
    'json': {
    'name': 'Logan Leon',
    'address': '6124 Keith Pine Apt. 731\nJameshaven, KY 80340',
},
    'key58530': 'value21168',
    'key93937': 'value76957',
    'key4631': 'value73398',
    'key69400': 'value15375',
    'key2082': 'value10937',
    'key31227': 'value67847',
    'key63200': 'value23054',
    'key15831': 'value42728',
    'key72077': 'value37265',
    'key3526': 'value44100',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Matthew Ballard',
    'address': '326 Serrano Trafficway Apt. 404\nEast Loganport, MT 09040',
    'text': 'Like read modern quality other consumer. On social simple book national.',
    'email': 'pcarter@example.org',
    'phone_number': '(552)961-9842',
    'array_int_dynamic': [
    88326,
],
    'array_varchar_dynamic': [
    'Barbara Parsons',
    'Robert Mcintosh',
    'Nathan Lawson',
    'James Gomez',
],
    'json': {
    'name': 'Thomas Hall',
    'address': '2984 Odonnell Station Apt. 727\nLopezburgh, NY 50871',
},
    'key81112': 'value11410',
    'key81545': 'value98736',
    'key89225': 'value26119',
    'key78204': 'value81608',
    'key22276': 'value90807',
    'key117': 'value51831',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Jeffrey Whitaker',
    'address': '702 Donna Coves\nAnnafurt, DE 83787',
    'text': 'Everything message place study. Some accept stop style manager last may. Already specific main even here.',
    'email': 'ihendricks@example.net',
    'phone_number': '+1-982-258-8450x43781',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Gomez',
    'Matthew Thomas',
    'Brandon Smith',
    'Christy Ramsey',
    'Ian Bentley',
    'Joseph Knapp',
],
    'json': {
    'name': 'Patricia White',
    'address': '035 Rodriguez Lock Apt. 181\nEast Denise, TN 45798',
},
    'key93925': 'value96620',
    'key8796': 'value34748',
    'key12134': 'value10279',
    'key51035': 'value500',
    'key32038': 'value31948',
    'key81115': 'value73831',
    'key7385': 'value76489',
    'key86094': 'value89240',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Ana Holland',
    'address': '3631 Osborn Via\nCoreyborough, WY 70628',
    'text': 'Throw often seem college hear. Community according most while.\nSpeech thank thought fine win care bring cause. Newspaper good herself form small young. Which unit open least material especially.',
    'email': 'jasondeleon@example.com',
    'phone_number': '+1-539-904-3748x172',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Michele Jackson',
    'Vanessa Gonzalez',
    'Heather Fletcher',
    'Victor Green',
    'Sara Solomon',
    'Adam Lawrence',
    'Nicole Thomas',
    'Jorge Robinson',
    'Thomas Williams',
    'Kendra Spencer',
],
    'json': {
    'name': 'Nathan Burns',
    'address': '91834 Tran Fort\nBrownfort, CT 10206',
},
    'key66452': 'value28081',
    'key40517': 'value1478',
    'key63756': 'value70317',
    'key80172': 'value98315',
    'key91754': 'value21383',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Paula Barber',
    'address': '76181 Robinson Plains\nNorth Keith, DE 54152',
    'text': 'Feel start himself source north pull. When knowledge parent before husband. Mission two can road phone law meeting mind.',
    'email': 'muellererin@example.org',
    'phone_number': '(690)407-3341x500',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michael Mathis',
    'Christopher Riggs',
    'Jesus Webster',
    'William Alvarado',
    'Andrea Taylor',
    'Joshua Smith',
    'Sarah Stanton',
],
    'json': {
    'name': 'Christina Hogan',
    'address': '0448 Moore Estates\nYolandaport, ME 22363',
},
    'key89160': 'value25680',
    'key18157': 'value39782',
    'key96135': 'value86771',
    'key41133': 'value10614',
    'key72051': 'value77488',
    'key28606': 'value35577',
    'key9949': 'value84578',
    'key57644': 'value51426',
    'key53624': 'value44193',
    'key77391': 'value15463',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Johnny Cortez DVM',
    'address': '2829 Adam Throughway Suite 703\nWest Caitlynbury, SD 11968',
    'text': 'Organization entire prevent rich fall Mrs attack west. Use five start why trip message do.\nHistory share name involve would too energy. Spring year coach suffer protect. Range television give card.',
    'email': 'alyssa02@example.net',
    'phone_number': '371-817-3359',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amber Stone',
],
    'json': {
    'name': 'Kelly Lambert',
    'address': '92668 Ryan Forges Suite 225\nAmbershire, AZ 50578',
},
    'key26131': 'value68082',
    'key152': 'value85711',
    'key65009': 'value14758',
    'key39549': 'value7303',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Douglas Figueroa',
    'address': '0976 Freeman Island\nLake Lindsayside, VI 70609',
    'text': 'Cup figure six information.\nChance dream class field myself check small. Most should environment imagine fight.',
    'email': 'dawsonrhonda@example.net',
    'phone_number': '8983628197',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Ward',
    'Katherine Henderson',
    'Whitney Kelly',
    'Destiny Harris',
    'Joshua Osborne',
    'Jeremy Navarro',
    'Kyle Duke',
    'Carol Hardy',
],
    'json': {
    'name': 'Emily Vargas',
    'address': '7749 Suzanne Course\nNorth Jameshaven, HI 25691',
},
    'key12224': 'value2685',
    'key17131': 'value34638',
    'key33815': 'value78671',
    'key98396': 'value38434',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Dawn Simmons',
    'address': '09029 Chang Mews Suite 344\nNorth Juliehaven, FL 45043',
    'text': 'Statement his interest director tax without room. Today course coach would.\nEverything hold would well threat bad owner she. Gun return floor happen. Really crime address another.',
    'email': 'brenda63@example.net',
    'phone_number': '+1-483-699-6883x08678',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Caitlin Henderson',
    'Lydia Johnson',
    'Laura Brooks',
    'James Jefferson',
],
    'json': {
    'name': 'Alicia Davis',
    'address': '472 Laurie Trail Apt. 238\nEast Jenniferstad, SC 94882',
},
    'key68250': 'value35880',
    'key35911': 'value91565',
    'key10610': 'value31866',
    'key17436': 'value75448',
    'key94915': 'value92367',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Sara Murphy',
    'address': '51761 Sarah Trace Apt. 802\nJessicatown, GU 73044',
    'text': 'Heart try right public arrive wind play. Story protect scene threat white.\nInterview best live late life. When war within treat resource tell. Act agreement minute purpose throughout.',
    'email': 'yjones@example.org',
    'phone_number': '(478)273-4914x86126',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Terri Allen',
    'Ashley Green',
    'Sarah Decker',
    'Brent Graves',
    'Kim Manning',
    'Kristin Lee',
],
    'json': {
    'name': 'Lindsey Carter',
    'address': '5127 Kenneth Walk\nNew Alexandra, GU 37905',
},
    'key48782': 'value550',
    'key31828': 'value19057',
    'key4072': 'value52406',
    'key19188': 'value62909',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Taylor Mcgee',
    'address': '379 Carson Lake Apt. 189\nRonaldside, PA 06166',
    'text': 'Move wear economic few travel process. Look offer purpose bad but.\nShort our understand enter. Make who hold the child however.',
    'email': 'robert75@example.net',
    'phone_number': '(981)401-1089',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Turner',
    'Mrs. Sara Archer MD',
],
    'json': {
    'name': 'George Ellis',
    'address': '28100 Larsen Forest Suite 144\nNormanport, SC 07551',
},
    'key40169': 'value27469',
    'key81046': 'value76207',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Joyce Torres',
    'address': '5317 Valdez Knolls Suite 303\nNew Oscar, MA 98469',
    'text': 'To young sea. Current modern forward while we herself.\nClearly early bad hear enter possible player beyond. Visit blue street while discuss heavy.',
    'email': 'higginsalyssa@example.com',
    'phone_number': '001-282-287-1468x6218',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Smith',
    'Timothy Thompson',
    'Stephen Taylor',
    'Hannah Hall',
    'Eric Scott',
    'Walter Nelson',
],
    'json': {
    'name': 'Julie Johns',
    'address': '2062 Mathis Inlet\nNew Gabrielleside, MT 89170',
},
    'key31698': 'value2316',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Justin Hahn',
    'address': '02887 Ramirez Gardens Apt. 523\nPaulafort, MT 12484',
    'text': 'Economy across pretty camera western eat. Do speech section. Close business good power than entire result.',
    'email': 'john77@example.org',
    'phone_number': '306-364-5682',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Donna Anderson',
    'Jamie Mata',
    'Bruce Ramirez',
    'Daniel Oneill',
    'Adrienne Osborn',
    'Derek Kelly',
],
    'json': {
    'name': 'Zachary Patterson',
    'address': '505 Miranda Mills Apt. 602\nSchwartzland, WY 54035',
},
    'key80783': 'value20227',
    'key69437': 'value58447',
    'key65004': 'value80115',
    'key91773': 'value82737',
    'key28958': 'value77045',
    'key33639': 'value82526',
    'key68029': 'value99332',
    'key56179': 'value86105',
    'key51003': 'value94865',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Debbie Burns',
    'address': '606 Patrick Coves\nYoungborough, NE 73249',
    'text': 'Field just song authority. Decision model begin build exactly.\nPractice stay yeah strategy go professor. Town character reduce collection buy.',
    'email': 'rfuller@example.com',
    'phone_number': '204.709.5900x2875',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Eric Mason',
    'Jesse Gibson',
    'Sarah Grimes',
    'Valerie Zavala',
    'Brianna Smith',
    'Mr. Joseph Berry',
    'Kaitlyn Bates',
],
    'json': {
    'name': 'Elizabeth Hale',
    'address': 'PSC 0951, Box 4119\nAPO AP 76093',
},
    'key24361': 'value53915',
    'key87607': 'value47070',
    'key97987': 'value7614',
    'key39349': 'value30365',
    'key89318': 'value65457',
    'key98091': 'value33752',
    'key6669': 'value41270',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Marcus Smith',
    'address': '8855 Tiffany Viaduct Apt. 607\nWest Joshuaville, DC 06730',
    'text': 'Laugh house work effort term leave his. Senior rule federal soon.\nAnimal size people mouth five. Then child article need idea street provide.',
    'email': 'chadlucas@example.com',
    'phone_number': '+1-433-841-6068x341',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Robert Richards',
],
    'json': {
    'name': 'Tiffany Bishop',
    'address': '40124 Soto Drive\nTurnermouth, DE 39206',
},
    'key96808': 'value19154',
    'key85192': 'value23870',
    'key49287': 'value23498',
    'key52704': 'value26869',
    'key95195': 'value30312',
    'key38006': 'value14021',
    'key89260': 'value28936',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Derek Griffin',
    'address': 'Unit 6257 Box 2742\nDPO AE 95544',
    'text': 'At rate once develop. Management kitchen hit day. Friend bit stop movie rich. Material character wrong research bring plant.',
    'email': 'austinsmith@example.net',
    'phone_number': '2269382316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jose Anderson',
    'Mr. Steven Smith',
    'Lacey Thomas',
    'David Villarreal',
    'Susan Robertson',
    'Christian Terry',
    'John Hammond',
],
    'json': {
    'name': 'Michele Long',
    'address': '028 Miranda Inlet Suite 064\nNew Megan, OR 85339',
},
    'key3759': 'value19366',
    'key24062': 'value66315',
    'key22855': 'value48188',
    'key93837': 'value25078',
    'key1427': 'value14988',
    'key87882': 'value93483',
    'key89461': 'value44607',
    'key56340': 'value70550',
    'key49070': 'value50489',
    'key63898': 'value61859',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Michael Sandoval',
    'address': '34159 Snyder Stravenue Suite 055\nAndersonbury, VA 88159',
    'text': 'Sell they forget last sister industry. Exactly between different.\nMethod lead nearly stuff individual very experience. Bring tend be.',
    'email': 'bianca81@example.net',
    'phone_number': '(860)289-2707x77279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Baker',
    'Kimberly Navarro',
    'Madison Torres',
    'Jim Meyer',
    'Shawn Hill',
    'Mary Blackburn',
    'Travis Rodriguez',
    'Andre Hudson',
    'Courtney Lynn',
    'James Douglas',
],
    'json': {
    'name': 'Sheila Johnston',
    'address': '0626 Mary Corner Apt. 282\nStephaniechester, PW 27379',
},
    'key78627': 'value79857',
    'key11422': 'value29820',
    'key48975': 'value74265',
    'key67576': 'value95683',
    'key1161': 'value26558',
    'key77560': 'value14678',
    'key75862': 'value37543',
    'key46022': 'value47130',
    'key46878': 'value28968',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Meghan Crawford',
    'address': '211 Yang Place Apt. 055\nJarvisshire, NY 04652',
    'text': 'Professor whole claim. Nearly result half easy. Way need probably project kind vote safe security.\nBeyond red public use. Close computer usually cup land hundred.',
    'email': 'matthewsmichelle@example.net',
    'phone_number': '476-271-8100x626',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Herrera',
],
    'json': {
    'name': 'Tony Reeves',
    'address': '559 Smith Streets\nNew Michelleport, ND 75159',
},
    'key45853': 'value9259',
    'key30609': 'value4143',
    'key63813': 'value88206',
    'key19388': 'value4518',
    'key43714': 'value98036',
    'key38152': 'value14666',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Taylor Patel',
    'address': '0738 Miranda Ville\nNew Mark, OK 68284',
    'text': 'Doctor often whose similar carry. City project use only scene sport.\nParty commercial line. Safe will general public. Window security investment these.',
    'email': 'zcurry@example.com',
    'phone_number': '001-565-601-2317',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Sandra Perry',
    'Samantha Taylor',
    'Drew Mclaughlin',
    'Mr. Michael Morrison',
    'Antonio Graham',
    'Brent Martinez DDS',
    'Kyle Alvarez',
    'Lisa Ramos',
    'Travis Johnson',
],
    'json': {
    'name': 'Julie Sullivan',
    'address': '2717 Barber Flat\nMartinbury, CA 96099',
},
    'key17576': 'value80576',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'David Bush',
    'address': '02263 Todd Turnpike\nMatthewmouth, WA 21218',
    'text': 'Scientist agree gun forget piece include their. Short resource person party happen. Food challenge unit color political feel side.',
    'email': 'johnsonbriana@example.net',
    'phone_number': '001-385-338-1025',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Lewis',
    'Casey Rivera',
],
    'json': {
    'name': 'Gloria Mccoy',
    'address': 'PSC 1610, Box 2516\nAPO AA 31843',
},
    'key78427': 'value27412',
    'key64778': 'value38938',
    'key18300': 'value86304',
    'key71385': 'value76538',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Mr. Kurt Robinson Jr.',
    'address': '9444 Ryan Common Suite 732\nReynoldsshire, KY 60212',
    'text': 'Skill visit speech want anyone ball outside although. Else morning real live store debate edge necessary.\nTotal side machine thank. Four although score us positive he. Sometimes safe few each likely.',
    'email': 'mjohnson@example.org',
    'phone_number': '201.254.9544',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jenna Castillo',
    'William Roth',
    'Justin Juarez',
    'Joseph Rivera',
    'Julie Campbell',
    'Melissa Young',
],
    'json': {
    'name': 'Jason Bradshaw',
    'address': 'PSC 3104, Box 3643\nAPO AA 37357',
},
    'key54729': 'value15291',
    'key11943': 'value40206',
    'key59498': 'value46606',
    'key40354': 'value70589',
    'key39555': 'value36913',
    'key22314': 'value50044',
    'key3401': 'value79460',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Richard Galvan',
    'address': '4525 Tina Motorway\nLake Michael, VT 67609',
    'text': 'Girl baby region young mouth but. Run resource far believe build reach.',
    'email': 'linda10@example.org',
    'phone_number': '871-923-7515',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Miss Kathy Kim',
],
    'json': {
    'name': 'Andrew Thomas',
    'address': '67009 Campos Manors\nJosephburgh, MA 01108',
},
    'key68595': 'value99473',
    'key55948': 'value35304',
    'key87349': 'value8354',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Deborah Roy',
    'address': '14872 Mitchell Trace\nAdrianland, NY 38147',
    'text': 'Perform research collection many home senior cost.\nGet road return positive last meet child. Risk information suddenly hope. Above various marriage commercial effect unit onto himself.',
    'email': 'qtodd@example.org',
    'phone_number': '(711)274-7694x646',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'James Griffith',
],
    'json': {
    'name': 'Ian Carroll',
    'address': '16450 Sharon Causeway\nNorth Henry, WA 87932',
},
    'key93346': 'value40835',
    'key56144': 'value68278',
    'key18111': 'value17652',
    'key88171': 'value49518',
    'key47199': 'value46300',
    'key18270': 'value12618',
    'key66514': 'value95092',
    'key98866': 'value26567',
    'key75725': 'value90678',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Theresa Cunningham',
    'address': '476 Adams Gateway\nSouth Kellyport, WA 99895',
    'text': 'Here involve call political war TV mind. Teacher simple back hundred. Job go price hair these power image friend.',
    'email': 'xgregory@example.net',
    'phone_number': '+1-910-315-0207',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rodney Rodriguez',
],
    'json': {
    'name': 'Christopher Taylor',
    'address': '019 Carolyn Springs\nWest Alexaton, PR 19950',
},
    'key46715': 'value78761',
    'key81554': 'value74388',
    'key68145': 'value49607',
    'key75205': 'value13098',
    'key76538': 'value28926',
    'key28068': 'value42221',
    'key21490': 'value14147',
    'key24076': 'value16716',
    'key18792': 'value75083',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Julie Carr',
    'address': 'Unit 6096 Box 8575\nDPO AP 16082',
    'text': 'Training for cut hand card rest make memory. Itself so industry affect. Wonder bag as yes young goal.',
    'email': 'serranojose@example.net',
    'phone_number': '687-644-2213x071',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nichole Lee',
    'Kimberly Henderson',
    'Tracy Spencer',
    'Holly Johnson',
],
    'json': {
    'name': 'Natasha Smith',
    'address': '821 Turner Meadows\nNew Jacqueline, MH 08395',
},
    'key16103': 'value10787',
    'key96317': 'value31094',
    'key57876': 'value76605',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Rachel Conway',
    'address': '132 Ramos Ford\nTurnerland, CO 63916',
    'text': 'Fact rise north police garden language save.\nPossible feel program with star both wish. Suggest federal television first natural today.',
    'email': 'sjones@example.com',
    'phone_number': '+1-449-783-2608',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Susan Copeland',
    'Gabrielle Jefferson',
    'David Mullen',
    'James Cole',
    'Donald Gonzalez',
    'Sarah Williams',
],
    'json': {
    'name': 'Patrick Wood',
    'address': '9591 Jonathan Groves\nMurphyshire, VI 02175',
},
    'key82134': 'value1709',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Jonathon Orr',
    'address': 'PSC 7490, Box 4637\nAPO AA 09423',
    'text': 'Hold have model floor. Father eight region because poor. White four maintain gun design.\nMain information next quickly. Box indicate market talk away.',
    'email': 'forddavid@example.com',
    'phone_number': '(217)979-5976x935',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Porter',
    'Peter Cunningham',
    'Lisa Cowan',
    'Todd Velasquez',
    'Cassidy Robles',
    'Nicole Jackson',
    'Erika Garcia',
    'Alison Smith',
],
    'json': {
    'name': 'Alfred Ball',
    'address': '795 Jenna Rue\nMolinaborough, NH 33752',
},
    'key73829': 'value52456',
    'key29841': 'value48346',
    'key31834': 'value36202',
    'key47665': 'value22626',
    'key2730': 'value63474',
    'key3792': 'value96929',
    'key46246': 'value79009',
    'key43276': 'value45853',
    'key62144': 'value56431',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Christina Sims',
    'address': '503 Geoffrey Brooks\nPort Janet, KY 29827',
    'text': 'Remain feeling when will check win. Begin indeed mention pick challenge pass.\nChair fire bar respond scene than matter. Whatever table who way according.',
    'email': 'dgonzalez@example.org',
    'phone_number': '275-258-1158x1148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Smith',
],
    'json': {
    'name': 'Joseph Ford',
    'address': '805 Kennedy Underpass Suite 384\nWest Samanthabury, AR 99469',
},
    'key11908': 'value11425',
    'key1655': 'value43255',
    'key98640': 'value21148',
    'key22447': 'value27633',
    'key77873': 'value3462',
    'key10054': 'value87681',
    'key94239': 'value27896',
    'key87099': 'value18549',
    'key53042': 'value66200',
    'key40951': 'value48346',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Margaret Lynch',
    'address': '848 Sean Centers\nParkland, NJ 55720',
    'text': 'Recent second move reality material. Country team example short recent then view.\nResponsibility visit soldier can. Political wind field a. Strategy heavy but certain bill into.',
    'email': 'alison60@example.org',
    'phone_number': '313-504-7956x30545',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Nichole Chavez',
    'Maria Stephens',
],
    'json': {
    'name': 'Edward Ryan',
    'address': '92279 Acevedo River\nLake Brentmouth, CO 74546',
},
    'key1183': 'value15461',
    'key92066': 'value38394',
    'key73805': 'value76405',
    'key1160': 'value97186',
    'key47799': 'value69652',
    'key337': 'value9189',
    'key22529': 'value80551',
    'key39860': 'value62973',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Brian Robbins',
    'address': '984 Jorge Square\nSouth Sandra, NH 11193',
    'text': 'Become design list join anyone street. Ready maybe blood leave. Represent individual into tree style section community yard. Green both smile look clear again difference.',
    'email': 'sierraortega@example.com',
    'phone_number': '(620)866-9940x20697',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Luis Ford',
    'Edward Roach',
    'Tracy Gregory',
    'Adam Patel',
    'Ashley Hubbard',
    'David Turner',
    'Leah Murphy',
    'Teresa Lyons',
    'Michelle Campbell',
    'Amy White',
],
    'json': {
    'name': 'Catherine Roberts',
    'address': 'USNV Rivera\nFPO AA 25194',
},
    'key63269': 'value50540',
    'key84054': 'value94383',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Christopher Medina',
    'address': '2991 Brendan Manor Apt. 930\nBrownfort, TN 63831',
    'text': 'Per clear enjoy Congress. Possible left grow human tough. Mention here strategy offer fill area.',
    'email': 'westamanda@example.net',
    'phone_number': '001-693-366-4233x20941',
    'array_int_dynamic': [
    95753,
],
    'array_varchar_dynamic': [
    'Andre Hall',
    'Gina Clark',
    'Timothy Williams',
    'John Washington',
    'Tina Sanchez',
    'Johnny Hutchinson',
    'Mark Campbell',
    'Cynthia Stephens',
],
    'json': {
    'name': 'Kenneth Arnold',
    'address': 'Unit 6997 Box 2103\nDPO AA 44027',
},
    'key7547': 'value36995',
    'key61819': 'value74864',
    'key99733': 'value34117',
    'key43303': 'value17813',
    'key54260': 'value62559',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'James Byrd',
    'address': 'PSC 6244, Box 2746\nAPO AE 60116',
    'text': 'Place herself public work sound trip traditional question. Beyond now stage them huge air. Serve strong discover carry window list.',
    'email': 'pamelasanders@example.net',
    'phone_number': '858-505-9730x4616',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Anna Ball',
    'Brittany Robertson',
    'Danielle Bryant DDS',
],
    'json': {
    'name': 'Daniel Jones',
    'address': '21724 Malone Flats\nTimothyberg, PR 56909',
},
    'key19420': 'value1812',
    'key13012': 'value6465',
    'key81697': 'value54870',
    'key56258': 'value97201',
    'key93148': 'value30800',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Alexis Miller',
    'address': '950 Collier Spring Apt. 048\nPort Janebury, SC 19493',
    'text': 'Mouth example and western blue everybody. Thing training instead. Make help senior door.\nMove organization budget nice. Why pattern money never month administration different.',
    'email': 'lawrence96@example.com',
    'phone_number': '352.916.3183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Joseph Hall',
    'Tonya Austin',
    'James Velasquez',
    'Jonathan Brooks',
    'Jennifer Ellis',
    'Krystal Dixon',
    'Amber Kennedy',
    'Angela Kelley',
    'Patricia Lawson',
    'Vanessa Baker',
],
    'json': {
    'name': 'Matthew Young',
    'address': '795 Thornton Crest\nPort Hollyport, AK 16692',
},
    'key1292': 'value89492',
    'key92658': 'value46818',
    'key40892': 'value11729',
    'key35322': 'value68892',
    'key406': 'value28934',
    'key99629': 'value27353',
    'key36810': 'value9266',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Melanie Silva',
    'address': '1078 Joseph Corner\nLake Molly, RI 24068',
    'text': 'Difficult sure help population. Read type material.\nCivil better mother role great either note. Pattern couple under. Commercial director high produce watch yourself wife.',
    'email': 'blackvickie@example.org',
    'phone_number': '001-695-572-1036x250',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Mary Jones',
    'Mark Quinn',
    'Steven Chapman',
    'Collin Glover',
    'Haley Fitzpatrick',
    'Raven Rice',
],
    'json': {
    'name': 'Ian Dawson',
    'address': '4063 Shelley Canyon\nHowellside, MN 90897',
},
    'key69046': 'value46091',
    'key81959': 'value93643',
    'key62980': 'value22617',
    'key71640': 'value24714',
    'key36577': 'value63177',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Angela West',
    'address': '433 Spence Drives\nNorth Leonardhaven, IL 50616',
    'text': 'Fill glass national traditional join movement. Maybe though these former still watch discussion. Shake model short attorney need medical let firm.',
    'email': 'bobby94@example.net',
    'phone_number': '248.970.0462x7494',
    'array_int_dynamic': [
    15626,
],
    'array_varchar_dynamic': [
    'Daniel Cline',
    'Dawn Garcia',
],
    'json': {
    'name': 'Maria Ruiz',
    'address': '25264 Tapia Street\nEast Angela, NC 82698',
},
    'key52850': 'value915',
    'key62135': 'value57046',
    'key95837': 'value69732',
    'key73930': 'value89101',
    'key62554': 'value21785',
    'key77614': 'value56021',
    'key82': 'value42849',
    'key33859': 'value91582',
    'key8320': 'value63632',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Cassandra Schultz',
    'address': '67159 Reginald Ville Suite 805\nNew Zachary, PA 38945',
    'text': 'Answer race action morning. Form seek impact difference marriage into class.\nWord opportunity white remain. Pressure include sister result media store.',
    'email': 'wayne42@example.org',
    'phone_number': '944-671-5430x20941',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Brown',
    'Jessica Stewart',
    'Lee Martinez',
    'Ashley Phillips',
    'Jacqueline Jones',
    'Nancy Lambert',
    'Patricia Johnson',
    'Tracy Hunter',
    'Joseph Hughes',
],
    'json': {
    'name': 'Catherine Green MD',
    'address': '3366 Harris Court\nPort Kathrynstad, PA 85727',
},
    'key95635': 'value77177',
    'key77135': 'value92937',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Sean Luna',
    'address': '3277 Wheeler Ford\nWest Teresa, MA 88218',
    'text': 'Receive suggest officer data two pick similar. Southern manage itself century large more enter car. Large number east two should will network.',
    'email': 'rachelbennett@example.com',
    'phone_number': '(413)835-9463x026',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Diane Ford',
    'Jacob Garcia',
    'Mark Gill',
    'Amy Lane',
    'Dawn Allison',
    'Alexandra Carter',
    'Sierra Gonzalez',
    'Justin Wong',
    'Robin Mckinney MD',
],
    'json': {
    'name': 'Angela Gutierrez',
    'address': '102 Shelley Trace\nWatersmouth, OR 50225',
},
    'key25129': 'value34083',
    'key8552': 'value46447',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Robert Hatfield',
    'address': '8836 Sanders Turnpike Suite 577\nJohntown, NM 14759',
    'text': 'Activity recent where financial. Control voice vote news career include peace.',
    'email': 'xsanchez@example.com',
    'phone_number': '649-534-5885x9734',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Ellis',
    'Tanner Zavala',
    'Dean Johnson',
    'Mary Pineda',
    'Howard Johnson',
    'Brian Rhodes',
    'Tamara Hanson',
    'Amy Peterson',
    'Caitlin Gonzalez',
    'Kelly Garcia',
],
    'json': {
    'name': 'Lisa Snyder',
    'address': '9929 David Knoll\nLake William, CT 76012',
},
    'key20147': 'value61711',
    'key70415': 'value24484',
    'key26309': 'value34960',
    'key35704': 'value18828',
    'key53993': 'value86145',
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
    'RequestId': 'af2c0b52-62ef-11f0-a02a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_21_408923oxaiNDYg',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-100-2]_1752744202.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl3210021752744202Json()
    test.run_tests()
