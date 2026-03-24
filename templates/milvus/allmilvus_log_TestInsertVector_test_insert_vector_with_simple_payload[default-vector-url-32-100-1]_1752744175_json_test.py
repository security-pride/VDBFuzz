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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-1]_1752744175_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-1]_1752744175.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl3210011752744175Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-1]_1752744175.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-1]_1752744175.json"
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
    'RequestId': '9f140af9-62ef-11f0-9c24-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_54_408088kLvnDbRx',
    'dimension': 32,
    'primaryField': 'url',
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
    'RequestId': '9f34e269-62ef-11f0-b472-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_54_408088kLvnDbRx',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Miguel Moreno',
    'address': '6201 Matthew Heights\nStephenside, VT 76390',
    'text': 'Onto thus sister beyond better body. Election degree five site factor nothing loss. Without party nation.',
    'email': 'bthornton@example.org',
    'phone_number': '9947174971',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Melanie Sparks',
    'Rachel Boone MD',
    'Jeremy Armstrong',
    'Jeffrey Cole',
    'Jason Green',
    'Jeffrey Norris',
    'William Burnett',
    'Caroline Kline',
    'Keith Phillips',
],
    'json': {
    'name': 'Colleen Ashley',
    'address': '366 Chelsea Greens Suite 365\nMartinhaven, CA 22098',
},
    'key9012': 'value90427',
    'key66995': 'value65008',
    'key7491': 'value78899',
    'key75335': 'value45821',
    'key78738': 'value20959',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Wendy Roy',
    'address': '012 Hill Pine\nMarthaborough, WY 52247',
    'text': 'Yeah option political movement next.\nBase election any single value fly perform. Range red mission news firm job.',
    'email': 'vgonzalez@example.net',
    'phone_number': '001-590-800-2104x868',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Richard Spears',
    'Melissa Martin',
    'Robert Buck',
    'Christopher Alvarez',
    'Kelly Abbott',
],
    'json': {
    'name': 'Janet Mooney',
    'address': '8456 Allen Circles\nSouth Cynthiachester, SD 64283',
},
    'key76150': 'value62959',
    'key75484': 'value87494',
    'key97880': 'value35630',
    'key80401': 'value79002',
    'key54978': 'value26777',
    'key75460': 'value30406',
    'key38217': 'value45728',
    'key2323': 'value32112',
    'key99976': 'value14855',
    'key98552': 'value10410',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Nicole Freeman',
    'address': 'PSC 9689, Box 5061\nAPO AE 82725',
    'text': 'Above eight within way lay kitchen name. Subject ok store again.',
    'email': 'carl00@example.org',
    'phone_number': '(736)977-3803',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Ryan Phillips',
    'Susan Morgan',
    'Melissa Aguilar',
    'Kelly Moore',
    'Mr. Hunter Garcia',
    'Amanda Chapman',
    'Ronald Schultz',
    'Michelle Chung',
    'Rebecca Sharp',
    'Joshua Erickson',
],
    'json': {
    'name': 'Sherry Dennis',
    'address': '1983 Melissa Springs\nPort Peterville, HI 07393',
},
    'key28531': 'value35150',
    'key47423': 'value32958',
    'key62423': 'value552',
    'key12451': 'value80334',
    'key75376': 'value72602',
    'key23165': 'value76289',
    'key98224': 'value71506',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Amber Riddle',
    'address': 'Unit 4940 Box 7484\nDPO AA 49812',
    'text': 'Western feel then yet somebody itself agent. Election half eye amount effort minute again maintain. Follow seek write fish. Be while fear wish red.',
    'email': 'ashleykelly@example.org',
    'phone_number': '410-539-5486x9391',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David Phelps',
    'Allen Hernandez',
    'Carrie Willis MD',
    'Dennis Henry',
],
    'json': {
    'name': 'Keith Douglas',
    'address': '92059 Parker Square Apt. 263\nStephensshire, MN 39693',
},
    'key17566': 'value9425',
    'key8023': 'value1549',
    'key39893': 'value31739',
    'key52327': 'value21907',
    'key30866': 'value68694',
    'key63587': 'value63593',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Tiffany Bass',
    'address': '971 Shields Hollow Apt. 670\nNelsonmouth, TX 89118',
    'text': 'Require course feel war pressure. Level likely item writer. Toward since shoulder personal rock page word.\nPerformance must simple fine issue. Join accept responsibility machine where.',
    'email': 'johnny29@example.net',
    'phone_number': '667-459-8608x4538',
    'array_int_dynamic': [
    57955,
],
    'array_varchar_dynamic': [
    'James Garcia',
    'Samuel Smith',
    'Cynthia Aguirre',
    'Kimberly Boyd',
],
    'json': {
    'name': 'Jason Bell',
    'address': '5055 Donald Dale\nSouth Christophermouth, ME 55524',
},
    'key66994': 'value48430',
    'key45500': 'value63075',
    'key2140': 'value49526',
    'key92828': 'value38764',
    'key23261': 'value16861',
    'key40440': 'value47654',
    'key3199': 'value4606',
    'key34810': 'value11557',
    'key22984': 'value32533',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'George Patel',
    'address': '091 Bush Ridges Suite 637\nBillystad, SC 33982',
    'text': 'Exist fund sit let economy. Point more simple protect.\nLong get improve security let environment can. Range draw clear its set herself activity.',
    'email': 'whitakersara@example.com',
    'phone_number': '253.671.3022x99024',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Ward',
],
    'json': {
    'name': 'Emily Perez',
    'address': '056 Robert Glens Apt. 983\nLake Briannamouth, AZ 95576',
},
    'key47595': 'value87530',
    'key18612': 'value33407',
    'key91311': 'value95900',
    'key33020': 'value66059',
    'key17592': 'value31196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Mr. Raymond Hunt MD',
    'address': '3970 Stanton Greens\nNorth Robert, RI 29671',
    'text': 'Institution amount church child too power particularly. Current teach create medical book.\nOther nothing case blood almost character apply sign. Pm she young see again.',
    'email': 'newtonnathaniel@example.com',
    'phone_number': '(797)584-0333',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Larry Hicks',
    'Robert Johnson',
    'Dillon Cardenas',
    'Robert Levy',
    'David Singh',
    'Kenneth Gardner',
    'Eduardo Gonzalez',
],
    'json': {
    'name': 'Antonio Carpenter',
    'address': '745 Burgess Fork Suite 324\nNorth Ginaview, LA 02251',
},
    'key46688': 'value34745',
    'key7985': 'value96599',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Spencer Pollard',
    'address': '72378 Destiny Walk\nCampbellshire, CO 66531',
    'text': 'Teacher lay find month site knowledge. Parent someone rock standard marriage her to choose.',
    'email': 'ali@example.com',
    'phone_number': '445-842-9488x52264',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christian Mccarty',
    'Mary Ramirez',
    'Jeffrey Allen',
],
    'json': {
    'name': 'Jennifer King',
    'address': 'USNS Collins\nFPO AE 93293',
},
    'key89038': 'value17372',
    'key71782': 'value5177',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Christopher Smith',
    'address': '262 Munoz Crest Apt. 657\nHoldenside, WI 57623',
    'text': 'Real expect offer PM always. Off southern writer mind find. Magazine will walk cell message. Coach during few soon unit boy customer.',
    'email': 'jennifer47@example.org',
    'phone_number': '333-202-1726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Holly Smith',
    'Elizabeth Whitney',
    'Colleen Arnold',
    'Justin Lopez DDS',
    'Valerie Lee',
    'Kyle Johnson',
    'Carl Taylor',
    'Johnathan Sullivan',
    'Beth Davis',
    'Melissa Robinson',
],
    'json': {
    'name': 'Gregory Franklin',
    'address': '86706 Brian Ford Suite 031\nSouth Bonnieside, NC 70750',
},
    'key9062': 'value2501',
    'key37733': 'value54473',
    'key56809': 'value32590',
    'key28094': 'value84742',
    'key80582': 'value1096',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Matthew Dyer',
    'address': '2789 Grant Forest\nSouth Reginaldside, MA 94037',
    'text': 'Shoulder image maybe situation. Me practice develop admit. Opportunity seat feeling.',
    'email': 'fshannon@example.org',
    'phone_number': '+1-385-863-9030x52647',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Leslie Frank',
    'David Douglas',
    'Colin Cross',
    'Brian Morales',
    'Glen Lane',
    'Katelyn Thompson',
    'Rodney Franklin',
    'Shelley Bennett',
],
    'json': {
    'name': 'Michelle Wagner',
    'address': '54306 Noble Mission\nJennifermouth, IA 63999',
},
    'key81666': 'value9706',
    'key67128': 'value4269',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Edward Bowen',
    'address': '422 Timothy Roads Suite 766\nMartinezmouth, CO 81556',
    'text': 'Talk agent everything result message together kind. Expect prove spring federal writer. Color wonder care wish several.\nExactly partner four tend. Politics hour view share.',
    'email': 'sfarley@example.net',
    'phone_number': '(641)524-9311',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Paul Crawford',
    'Craig Gregory',
    'Chad Rodriguez',
    'Susan Maynard',
],
    'json': {
    'name': 'Diane Black',
    'address': '39959 Michael Meadows Apt. 644\nPort Sheri, PA 45584',
},
    'key54887': 'value95958',
    'key39388': 'value98182',
    'key92848': 'value29445',
    'key752': 'value47436',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Michael Jones',
    'address': '2950 Snyder Radial Apt. 958\nThomasbury, AL 02844',
    'text': 'Front to eight manage baby.\nLearn interesting knowledge his believe professor. Him quality avoid network food section. Traditional generation main adult very direction.',
    'email': 'jamesmolina@example.org',
    'phone_number': '+1-644-412-5134x846',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alison Davis',
    'Brenda Snyder',
    'Mary Mckinney',
],
    'json': {
    'name': 'Mr. Jacob Lee',
    'address': 'USCGC Jackson\nFPO AA 69250',
},
    'key54480': 'value98145',
    'key87158': 'value48997',
    'key21425': 'value83616',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Douglas Murphy',
    'address': '3315 Payne Inlet\nNorth Jamieville, NV 42538',
    'text': 'The song for onto their. Night travel hard occur. Energy window father through husband just notice. Recognize either court.',
    'email': 'paigeweiss@example.org',
    'phone_number': '643.964.7262',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Penny Richards',
    'Caitlin Wright',
    'Ryan Durham',
    'Anthony Long',
    'Kimberly Riddle',
],
    'json': {
    'name': 'Mackenzie Shannon',
    'address': '631 Lance Center\nNew Paulborough, WY 71150',
},
    'key49964': 'value75983',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Taylor Thompson',
    'address': '726 Flores Mountain Suite 400\nNew Thomas, NM 35524',
    'text': 'Behind less trade. Would control receive. Bar staff right be agreement away rate.\nCut head seven building lead stop.',
    'email': 'thomasgerald@example.org',
    'phone_number': '+1-705-934-6764x5790',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Reilly',
],
    'json': {
    'name': 'Barbara Cross',
    'address': 'USS Love\nFPO AP 79378',
},
    'key49285': 'value16855',
    'key48272': 'value88568',
    'key42655': 'value54053',
    'key9421': 'value35301',
    'key84215': 'value39382',
    'key67804': 'value94655',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Anthony Dunn',
    'address': 'USNV Reid\nFPO AA 56292',
    'text': 'Any sometimes scientist authority evening message value. Someone simple your country writer southern. Cost skill ago reason north involve kid. Huge Congress become view station.',
    'email': 'grossluke@example.org',
    'phone_number': '+1-779-728-1075x10215',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Karen Smith',
],
    'json': {
    'name': 'Sandra Vargas',
    'address': '973 Julie Trail Suite 396\nAmyville, TX 84364',
},
    'key17439': 'value85472',
    'key75596': 'value87457',
    'key89464': 'value9962',
    'key12227': 'value98928',
    'key44497': 'value93920',
    'key21399': 'value40585',
    'key51758': 'value70124',
    'key29890': 'value63564',
    'key58278': 'value61944',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Anna Sosa',
    'address': '4942 Harris Course\nWest Geoffreystad, DC 62125',
    'text': 'Ask sea quite nation. Pass act best avoid. Society site section child.\nComputer three run case air. Call everybody lose sound. Argue late rich begin beautiful help.',
    'email': 'oramirez@example.net',
    'phone_number': '2204619309',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'David Greene',
    'Gregory Walker',
    'Michelle Ross',
    'Debbie Wright',
    'Brenda Adams',
    'Kathleen Johnson',
    'Doris Johnston',
    'Michael Cruz',
    'Anthony Simon',
],
    'json': {
    'name': 'Joseph Rodriguez',
    'address': '525 Hill Lock\nNorth Deanna, OH 04856',
},
    'key25740': 'value40535',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Brandi White',
    'address': 'USNV Humphrey\nFPO AA 47699',
    'text': 'Pull guess throw become check tell father it. Enter ground six cause town include good recently.',
    'email': 'joel15@example.org',
    'phone_number': '6343263003',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Miller',
    'Leon Parker',
    'Bruce Barrett',
],
    'json': {
    'name': 'Tanya Bradley',
    'address': '25618 Hernandez Extensions Suite 259\nSouth Chelseafort, IL 56171',
},
    'key78907': 'value55344',
    'key69397': 'value29686',
    'key17005': 'value58113',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Madison Martinez',
    'address': '2554 Escobar Springs\nPort Wendychester, AK 47540',
    'text': 'Husband seat candidate evidence throughout. Make black specific speech yard this short.\nRepublican scientist situation throughout safe hospital happy decide. Very up nothing pull which concern put.',
    'email': 'cooperjames@example.net',
    'phone_number': '946-673-7912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Marcus Hull',
    'Jennifer Guzman',
    'Kerry Gibbs',
    'Anthony Woodard',
    'Michele Lowe',
],
    'json': {
    'name': 'Debra Sellers',
    'address': '613 Odonnell Circle\nArmstrongville, MH 02404',
},
    'key37365': 'value83354',
    'key6630': 'value32523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Tony Campbell',
    'address': '704 Colleen Ridge\nEast James, NY 98139',
    'text': 'Glass poor drive movie. Fill scientist suddenly as.\nFive several leg do civil. Choice turn modern according feel west.\nDifficult want show contain goal significant strategy. Local accept send spring.',
    'email': 'iwilliams@example.com',
    'phone_number': '(568)231-8891x2394',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Chloe Williams',
    'Jasmine Phelps',
    'Katrina Hamilton',
    'Deanna Bernard',
    'Victoria Craig',
],
    'json': {
    'name': 'Erica Lewis',
    'address': '887 Moore Crescent Suite 839\nPort Kimberlyhaven, AZ 37323',
},
    'key86006': 'value62868',
    'key63333': 'value86645',
    'key36749': 'value95115',
    'key8133': 'value78975',
    'key96020': 'value1489',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Cody Green',
    'address': '137 Ross Glen Apt. 215\nWest Jamesport, NV 20764',
    'text': 'Life claim check.\nThen marriage American property such table resource. Different color sure develop. Performance leg Mr their event miss set.',
    'email': 'jeffrey00@example.net',
    'phone_number': '8656347164',
    'array_int_dynamic': [
    77133,
],
    'array_varchar_dynamic': [
    'Nicholas Cunningham',
    'Eric Maxwell',
    'Ricky Fowler',
    'Katherine Dawson',
    'Stephanie Walsh',
    'Joseph Guzman',
    'Courtney Griffith',
],
    'json': {
    'name': 'Michael Flores',
    'address': '73295 Christy Point\nSouth Emily, VI 71177',
},
    'key51009': 'value9890',
    'key53438': 'value2912',
    'key71810': 'value35683',
    'key76653': 'value91019',
    'key66744': 'value15554',
    'key27775': 'value95236',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Melissa Horton',
    'address': '9984 Howell Shoals\nJenniferborough, DC 15420',
    'text': 'Society what safe also. Feel various place skill effect. View ready soon. Too energy send father begin physical always.',
    'email': 'gardnerpatrick@example.org',
    'phone_number': '5332388363',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Cody Hardy',
    'Vanessa Silva',
    'Larry Coleman',
    'Steven Burton',
    'James Anderson',
    'Christopher James',
    'Curtis Gonzales',
    'Kelly Lynch',
],
    'json': {
    'name': 'Pamela Jones',
    'address': 'PSC 9266, Box 1336\nAPO AA 29074',
},
    'key24378': 'value54609',
    'key40743': 'value93170',
    'key7847': 'value75032',
    'key49900': 'value18732',
    'key53329': 'value57808',
    'key21077': 'value83591',
    'key183': 'value42221',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Michael Stewart',
    'address': '257 Cunningham Shore\nPort Markstad, CT 54775',
    'text': 'Parent ago year worry. Instead huge him another. Administration think easy pressure hot.\nPopulation policy catch home meeting interview. Can join free really war pass paper.',
    'email': 'veronica49@example.org',
    'phone_number': '+1-319-783-3212x5954',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Carolyn Williams',
    'Amber Taylor',
    'Kyle Cruz',
    'David Moore',
    'Susan Dudley',
    'Ms. Wanda Reid DDS',
    'Thomas Chaney',
    'Christine Smith',
    'Helen Robertson',
],
    'json': {
    'name': 'Juan Shields',
    'address': 'Unit 9016 Box 2609\nDPO AA 85817',
},
    'key30706': 'value70740',
    'key77042': 'value10012',
    'key49254': 'value83290',
    'key24288': 'value51884',
    'key54198': 'value43802',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Barbara Burton',
    'address': '88755 Clark Creek\nPort Kristenhaven, ND 08683',
    'text': 'Star eight financial your. Beyond medical least bag. Current decision pull choose camera about.',
    'email': 'corey25@example.com',
    'phone_number': '+1-558-318-6746x24558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Brett Paul',
    'Cassie Ellison',
    'Bradley Stephenson',
],
    'json': {
    'name': 'Stephanie Mccarthy',
    'address': '968 Atkins Bridge Apt. 301\nMorristown, ID 76246',
},
    'key37471': 'value11384',
    'key21723': 'value82222',
    'key77974': 'value34859',
    'key59767': 'value47167',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Yolanda Maddox',
    'address': '01027 Laura Forest Suite 744\nFloresbury, RI 64843',
    'text': 'Artist office mind court thus. Front range customer what.\nAlone employee point though. Marriage nor significant music exactly. Dream notice between sit.',
    'email': 'tracy24@example.org',
    'phone_number': '(598)588-8128',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Sanchez',
    'Kimberly Bailey',
    'Richard Schultz',
    'Joy Becker',
    'Nicholas Bowers',
    'Madison Keller',
    'Michael James',
],
    'json': {
    'name': 'Mr. Dennis Arias MD',
    'address': '5616 Emily Courts\nCarltown, PA 70182',
},
    'key51460': 'value23853',
    'key21908': 'value33619',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Christopher Jackson Jr.',
    'address': '63466 Lloyd Divide Suite 227\nGreenfort, NE 98136',
    'text': 'Explain minute trip film politics. Toward account gas maintain. Possible move result it kid happen week. Own technology rest question walk carry forward.',
    'email': 'conwayjeffery@example.com',
    'phone_number': '8935704536',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Amber Frederick',
    'Micheal Wright',
    'Shannon Green',
    'Andrew Hernandez',
    'Shannon Ballard',
    'Dr. John Jimenez',
    'Tracy Moss',
    'Michael Smith',
    'Joshua Anderson',
],
    'json': {
    'name': 'Erika Barrera',
    'address': '9215 Williams Motorway\nRobertstad, OH 75329',
},
    'key22153': 'value70196',
    'key90711': 'value78456',
    'key11047': 'value57565',
    'key91479': 'value99097',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'John Ellis',
    'address': '814 Gordon Parkways\nLake Daniel, GA 96912',
    'text': 'May red wait gas. Learn detail wall design institution long sometimes.',
    'email': 'epearson@example.com',
    'phone_number': '(911)925-4204x02644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Rodriguez',
    'Brandon Lam',
    'Sabrina Carr',
    'Ryan Miller',
    'Andrew Williams',
],
    'json': {
    'name': 'Jake Torres',
    'address': '53785 Jeremy Corners Suite 773\nEast Alexachester, LA 49994',
},
    'key2817': 'value13797',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'John Miller',
    'address': '0414 Jeffrey Ville Suite 586\nBrittanyside, MD 57618',
    'text': 'Lot one official ask. Human tough before above different raise. Would look under attack.\nBase build use can group well.',
    'email': 'mfoster@example.com',
    'phone_number': '239.328.8422',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Susan Nixon',
],
    'json': {
    'name': 'Raymond Lambert',
    'address': '62794 Goodwin Points\nSouth Ashleefort, TX 44534',
},
    'key51881': 'value18590',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Ryan Sandoval',
    'address': '1801 Torres Station\nWandachester, MN 90512',
    'text': 'Tend lawyer defense plan focus foreign religious.\nMention fast student growth. When we involve. A development while three.',
    'email': 'brandtsamantha@example.net',
    'phone_number': '786.944.8939',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'John Bowers',
    'Daniel Shepherd',
    'Charles Weeks',
    'Denise Jones',
    'Daniel Miller',
],
    'json': {
    'name': 'Kathleen Russo',
    'address': '835 Kristin Manor Suite 234\nNew Dylanport, MS 35081',
},
    'key61615': 'value42800',
    'key63129': 'value61810',
    'key54817': 'value20765',
    'key63062': 'value51805',
    'key31297': 'value62173',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Michael Carr',
    'address': '19257 Kyle Locks Suite 888\nRuizport, MN 84641',
    'text': 'Court audience but risk draw pretty recent. Every line part prevent drive.\nAudience step about building. Thus treatment campaign past of serious reality.',
    'email': 'blackmary@example.com',
    'phone_number': '666.466.2050',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Miss Anna Zuniga',
    'Kimberly Cobb',
    'Kelsey Walker',
    'Jessica Taylor',
    'Nathaniel Gonzales',
    'Steven Morris',
    'Wesley Arnold',
    'Sally Ryan',
    'Amy Johnson',
    'Douglas Hubbard',
],
    'json': {
    'name': 'Lynn Arellano',
    'address': '28828 Lindsay Island\nValenzuelaville, KY 66242',
},
    'key37933': 'value66937',
    'key4544': 'value25514',
    'key38015': 'value15642',
    'key3194': 'value27538',
    'key65906': 'value5679',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'April Fisher',
    'address': '240 Anderson Trace Suite 768\nNorth Veronica, KY 35364',
    'text': 'Daughter create forget structure difference design believe. Probably health surface.\nServe service bring four who early face. Return must nothing.',
    'email': 'zriley@example.com',
    'phone_number': '605-712-0631x435',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Watkins',
    'Michelle Murphy',
    'Sharon Cooper',
    'Tracy Walker',
    'Daniel Moore',
    'Kirk Vaughn',
    'April Davis',
],
    'json': {
    'name': 'Christopher Moore',
    'address': '105 Brian Spurs Apt. 720\nRobertmouth, OK 45564',
},
    'key47777': 'value31011',
    'key76398': 'value13284',
    'key68910': 'value48272',
    'key247': 'value45025',
    'key96995': 'value50432',
    'key95648': 'value22859',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Maria Cooper',
    'address': '369 Johnson Viaduct\nNorth Julia, FM 97628',
    'text': 'Several site ready. Scientist present shoulder. Let money fill shoulder speech security wall.\nFly trial suffer class. More generation sea bag growth attention.',
    'email': 'peter83@example.net',
    'phone_number': '338-423-0612x835',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Lamb',
    'Eric Mays',
],
    'json': {
    'name': 'Jared Mckenzie',
    'address': 'PSC 0815, Box 2695\nAPO AA 93106',
},
    'key44886': 'value27527',
    'key99486': 'value49575',
    'key56131': 'value40318',
    'key32493': 'value76967',
    'key42991': 'value29561',
    'key55879': 'value95696',
    'key74975': 'value84824',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Shawn Graham',
    'address': 'PSC 8886, Box 0130\nAPO AE 10494',
    'text': 'Grow any house performance. Animal area role data never series institution.\nOpen food central. Never economy traditional me.',
    'email': 'garrettmorris@example.net',
    'phone_number': '7468461312',
    'array_int_dynamic': [
    49951,
],
    'array_varchar_dynamic': [
    'John Dickson',
    'Kimberly Collins',
    'Catherine Edwards',
    'Jennifer Riley',
    'Renee Hogan',
    'Janice Black',
    'Cheryl Brooks',
    'Deborah Johnson',
],
    'json': {
    'name': 'Thomas Cole',
    'address': '80564 Zoe Ford\nJulieport, GA 61122',
},
    'key3650': 'value11056',
    'key74037': 'value35722',
    'key43906': 'value6858',
    'key85835': 'value70236',
    'key52034': 'value12691',
    'key82760': 'value75523',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Adrian Watkins MD',
    'address': '536 Reilly Brooks Suite 813\nSmithberg, ID 81431',
    'text': 'Take people shoulder leader. Visit present project according concern trial.\nStep better statement early enjoy have decade. Myself increase bag animal consumer. Billion source surface energy shake.',
    'email': 'hubbardsuzanne@example.net',
    'phone_number': '322-565-8654',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Adam Farrell',
    'Dr. John Hernandez',
    'Angela Russell',
    'Jason Bryant',
    'David Johnston',
],
    'json': {
    'name': 'Thomas Smith',
    'address': '333 Johnson Oval Apt. 307\nHamptontown, VI 36687',
},
    'key8342': 'value6099',
    'key33610': 'value46570',
    'key56952': 'value68852',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Ryan Mcguire',
    'address': 'USS Thompson\nFPO AA 60117',
    'text': 'Movement free use section. Recently his trip ability space seem firm.\nDream picture huge science kid. The age next where political anyone. Less effort some room.\nRate baby around nation.',
    'email': 'danieljohnson@example.net',
    'phone_number': '835-863-8917x20136',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Carlos Jordan',
    'Nathaniel Whitney',
    'Kayla Kelly',
    'Lori Harris',
    'Michael Murray',
    'Margaret Barron',
],
    'json': {
    'name': 'Kristen Hodge',
    'address': '596 Nolan Rapids\nAndrewmouth, TN 62254',
},
    'key9313': 'value28268',
    'key69173': 'value65933',
    'key89176': 'value36243',
    'key46798': 'value69471',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Douglas Garcia',
    'address': '0011 Bush Underpass Suite 475\nRiveraborough, LA 49771',
    'text': 'That opportunity local generation send wife radio. Never hospital article the able. Under effect add place. Experience conference news morning owner.\nIf financial our something at.',
    'email': 'billygonzales@example.org',
    'phone_number': '(883)629-3175x016',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sean Clark',
    'Brian Frazier',
    'Tina Arnold',
    'Brian Mcdonald',
    'Jamie Rivas',
    'Angela Walter',
    'Keith Romero',
],
    'json': {
    'name': 'Dr. Kimberly Pham',
    'address': '3298 Amy Station\nEast Ryan, MH 31854',
},
    'key43740': 'value15847',
    'key26393': 'value79256',
    'key23053': 'value27681',
    'key39856': 'value35423',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Martin Wilson',
    'address': '952 Andre Trail\nHendersonton, SD 21001',
    'text': 'Then his add well scientist. Plan in family resource picture apply.\nEver own fly bag true whole. Attention either store set about tonight between.',
    'email': 'smithaaron@example.org',
    'phone_number': '719-725-2785x62952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Valerie Jones',
    'Keith Morris',
    'Ashley Armstrong',
],
    'json': {
    'name': 'Lisa Reynolds',
    'address': '079 Sandra Spring\nWilsonville, OR 70866',
},
    'key99149': 'value4290',
    'key7625': 'value1875',
    'key32572': 'value20984',
    'key4568': 'value86444',
    'key67785': 'value89849',
    'key73907': 'value7465',
    'key8046': 'value5015',
    'key52992': 'value34824',
    'key23086': 'value49006',
    'key45121': 'value25187',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Manuel Shaw',
    'address': '80474 Troy Prairie Apt. 117\nTammyport, ND 56855',
    'text': 'Traditional whose them boy plan. Up those common. Base sell relationship.\nSystem bag those like perform eye born. Real we short week major change.',
    'email': 'hgibson@example.org',
    'phone_number': '+1-801-581-5610x0634',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jason Hunter',
    'Russell Booth',
    'Julie Salinas',
    'Jennifer Mathews',
    'Rebecca Evans',
    'Anthony Mullen',
    'Jerry Huffman',
    'Andrea Keller',
    'Latoya Ortega',
],
    'json': {
    'name': 'Marc Smith',
    'address': '021 Craig Locks Apt. 203\nSnyderfort, ME 21443',
},
    'key86832': 'value62032',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Stephanie Scott',
    'address': '1169 Mary Vista\nEast Daniellemouth, CA 31961',
    'text': 'Speak water trouble new policy. Garden statement recognize relationship blue.',
    'email': 'kenneththompson@example.net',
    'phone_number': '301.374.6058',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Tim Gallagher',
    'Jose Bradley',
    'Hannah Suarez',
    'Rhonda Norman',
    'Todd Walker',
    'Samantha Dalton',
    'Holly Caldwell',
    'Laura Smith',
    'Megan Hall',
],
    'json': {
    'name': 'Matthew Walker',
    'address': '40250 Parker Mission Apt. 462\nWest Davidburgh, WY 69012',
},
    'key46945': 'value73097',
    'key96942': 'value37839',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'John Nichols',
    'address': '51715 Williams Divide Apt. 670\nNew Shelby, GU 20437',
    'text': 'Carry necessary according only whole small design former. Everyone travel manage a almost hotel. Within management themselves wrong voice.',
    'email': 'sperry@example.org',
    'phone_number': '(714)622-3644',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Christina Clark',
    'Lauren Foster',
    'Richard Hawkins',
    'Corey Martinez',
    'Richard Sullivan',
    'Crystal Mitchell',
    'Michelle Mays',
    'Rachael Lewis',
    'Theresa Christensen',
    'Derek Rodriguez',
],
    'json': {
    'name': 'Robert Ingram',
    'address': '28680 Mills Viaduct\nLawsonborough, MT 49959',
},
    'key20180': 'value59854',
    'key83967': 'value21068',
    'key72353': 'value58996',
    'key13600': 'value40893',
    'key2550': 'value422',
    'key20676': 'value2964',
    'key51945': 'value72681',
    'key16527': 'value77231',
    'key19172': 'value74640',
    'key67650': 'value29677',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Jennifer Medina',
    'address': '282 Russell Lane Apt. 408\nMaryville, WY 79485',
    'text': 'East record strong campaign reason. Space down play at two. Hope reveal wonder tend decide need arm.\nSong wrong parent watch recently. Ball figure listen the PM along.',
    'email': 'robbinsgregory@example.com',
    'phone_number': '(624)611-8625x218',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Cathy Anderson',
    'Joseph Hall',
    'Gerald Tanner',
],
    'json': {
    'name': 'Sean Cabrera',
    'address': '8188 Warren Plains Apt. 833\nWest Andrewport, CA 74847',
},
    'key8477': 'value12898',
    'key98069': 'value12682',
    'key91646': 'value35037',
    'key38868': 'value77560',
    'key14890': 'value27992',
    'key27415': 'value39492',
    'key78910': 'value90335',
    'key6085': 'value31932',
    'key51744': 'value95491',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Norma Petty',
    'address': '65061 Flores Lodge\nNorth Neil, OK 57114',
    'text': 'Give worker too year itself meet should. Box somebody many professional born plant.\nDemocrat explain reason north soon where. Smile trouble understand reality enter want.',
    'email': 'zbrewer@example.org',
    'phone_number': '(827)780-1106x11612',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Steven Mayer',
    'Stephen Howard',
    'Lori Morales',
    'Allison Davis',
    'Dr. Michelle Wright',
    'Matthew Benson',
    'Craig Castro',
    'Kathleen Hughes',
    'Charles Clayton',
    'Madison Cowan',
],
    'json': {
    'name': 'Sarah Palmer',
    'address': '81581 Pamela Trafficway\nFreemanland, FM 05487',
},
    'key19267': 'value49500',
    'key21309': 'value18855',
    'key97851': 'value80941',
    'key25276': 'value45187',
    'key74893': 'value42224',
    'key94287': 'value8867',
    'key10024': 'value77157',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Elizabeth Taylor',
    'address': '6131 Chase Parks\nEllenside, WY 76075',
    'text': 'Whether pressure cut customer alone. Within north forget listen technology treatment.\nAmerican strong home material option.',
    'email': 'estuart@example.com',
    'phone_number': '(858)458-5206',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Stacey Glover',
],
    'json': {
    'name': 'Eric Richardson',
    'address': '99540 Gail Drive\nNew Luke, WI 29994',
},
    'key5677': 'value84300',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Christie Moyer',
    'address': '7548 Robles Mall Apt. 155\nWest Andrea, KS 84633',
    'text': 'Protect spend security street bar realize. Language first lose class lose. Finish street though walk.\nReduce apply place he main step. Civil speech billion chance. Poor very quickly.',
    'email': 'jennifer56@example.net',
    'phone_number': '001-756-738-0585x8306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brett Hubbard',
    'Elizabeth Young',
    'Jason Vaughan',
    'Daniel Parker',
    'Sean Kim',
    'Anthony Miller',
    'Michael Carlson',
    'Angela Williams',
    'James Brown',
],
    'json': {
    'name': 'Frank Perez',
    'address': '77130 Gallagher Square\nMejiabury, CO 32183',
},
    'key32889': 'value33965',
    'key12178': 'value71847',
    'key3834': 'value8219',
    'key82907': 'value62550',
    'key19509': 'value67128',
    'key98977': 'value97377',
    'key39116': 'value73308',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Cristina Kane',
    'address': '6836 Lori Forges\nLake Matthew, MD 20695',
    'text': 'Probably she speech offer card magazine. What she citizen learn realize everyone collection. While food in though else.',
    'email': 'ujohnson@example.com',
    'phone_number': '001-462-666-3860x71169',
    'array_int_dynamic': [
    30012,
],
    'array_varchar_dynamic': [
    'Erika Johnson',
    'Lisa Watson',
    'Kelly Brown',
    'Miranda Baker',
    'Ryan Tran',
    'Timothy Lopez DDS',
    'Amanda Smith',
    'Nicholas Cruz',
],
    'json': {
    'name': 'Karen Williams',
    'address': '01797 Courtney Lodge Apt. 331\nZacharymouth, PA 96062',
},
    'key47717': 'value96973',
    'key79720': 'value81623',
    'key28628': 'value24110',
    'key53405': 'value17255',
    'key44333': 'value90071',
    'key11293': 'value97190',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Marissa Adams',
    'address': '09045 Robert Keys\nWest James, NV 77806',
    'text': 'Dog prove so personal continue blood image. International history fly enter safe fine point.\nFind purpose enjoy both without value team son.',
    'email': 'ibanks@example.com',
    'phone_number': '001-468-749-2160x772',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Eric Pierce',
    'Cindy Castillo',
    'Brittany Phillips',
    'Derek Hopkins',
],
    'json': {
    'name': 'Mary Hill',
    'address': '75712 Jackson Knoll\nFritzview, MA 48049',
},
    'key52870': 'value16408',
    'key73954': 'value69251',
    'key15693': 'value10447',
    'key67232': 'value51921',
    'key8828': 'value50564',
    'key47992': 'value81022',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'Diane Forbes',
    'address': 'USNV Marshall\nFPO AA 14087',
    'text': 'More section camera too remember. Score without item how song. Down never section minute billion fund alone.\nWhich decide fly for miss garden choose. Well various claim travel seem sea feel possible.',
    'email': 'clarkmatthew@example.com',
    'phone_number': '001-957-434-3697x62148',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Robert Mack',
    'Ruth Simpson',
    'George Grant',
],
    'json': {
    'name': 'James Jackson',
    'address': '542 Rogers Lodge\nJennifertown, HI 46043',
},
    'key11702': 'value23815',
    'key20682': 'value93441',
    'key31727': 'value36776',
    'key4591': 'value2470',
    'key4681': 'value51874',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Mark Potts',
    'address': '0222 Woods Burg\nJasonstad, NV 56029',
    'text': 'Responsibility admit room toward find country trip. Federal pull ready report room. Major once other training.',
    'email': 'rfoster@example.net',
    'phone_number': '696-276-0113x11489',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Rodgers',
    'Kathy Mcknight',
    'Sherri Brown',
    'Benjamin Hale',
],
    'json': {
    'name': 'Rhonda Martinez',
    'address': '7404 Pitts Fall Apt. 663\nWilliamside, NH 06093',
},
    'key3266': 'value89399',
    'key48313': 'value2091',
    'key18181': 'value19885',
    'key11257': 'value68759',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Andrew Olsen',
    'address': '8133 Smith Islands\nRiverstown, KY 53619',
    'text': 'Great evening station main hit. Stuff indeed the federal. Leave similar cell take community member.',
    'email': 'xthomas@example.org',
    'phone_number': '621.862.2806x217',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jason Brooks',
    'Miss Rebecca Valencia',
    'Troy Carrillo',
    'Robert Schultz',
    'Connie Paul',
    'Melissa Anderson',
    'Joshua Davis',
],
    'json': {
    'name': 'Marcus Mcintyre',
    'address': '58676 Abbott Squares\nJessicachester, OH 01283',
},
    'key67668': 'value23675',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Christina Mahoney',
    'address': '559 Armstrong Courts Suite 812\nPort Jefferystad, MO 81604',
    'text': 'These network leave each front. Best though others operation.',
    'email': 'kathryn16@example.org',
    'phone_number': '+1-251-873-9843',
    'array_int_dynamic': [
    94025,
],
    'array_varchar_dynamic': [
    'David Mendez',
    'Elizabeth Montoya',
    'Teresa Richardson',
    'David Ochoa',
    'Timothy Larson',
    'Tiffany Gordon',
],
    'json': {
    'name': 'Allen Jones',
    'address': '84737 Watson Isle Apt. 894\nBrownview, NM 04634',
},
    'key79204': 'value35209',
    'key7925': 'value8858',
    'key99588': 'value19163',
    'key35506': 'value84680',
    'key32542': 'value31377',
    'key37412': 'value15069',
    'key89941': 'value43877',
    'key50329': 'value69141',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Ryan Grant',
    'address': '317 Brian Turnpike Suite 170\nLake Alexandrastad, RI 63219',
    'text': 'Wife discussion effect knowledge plant firm morning.\nInternational outside way east. National thousand own bad have second wait. Man us rather woman standard price series.',
    'email': 'vcooper@example.org',
    'phone_number': '+1-412-818-8141x2717',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jacob Ward',
    'Gary Clements PhD',
    'Jerry Hale',
    'Megan Camacho',
    'Joseph Fletcher',
    'Phyllis Butler',
    'Jay Franklin',
    'Angela Anderson',
    'Holly Webb',
],
    'json': {
    'name': 'Nicholas Haley',
    'address': '30445 Jonathan Place\nPort Angelaview, IA 55410',
},
    'key80211': 'value54382',
    'key75171': 'value35927',
    'key54276': 'value84793',
    'key86206': 'value17829',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Brandon Gill',
    'address': '6731 Alexis Mill Apt. 441\nPort Lanceview, IL 31107',
    'text': 'Unit outside office his yourself wall big cold. Prevent mind relate mind.\nHard purpose exist fire part plan. Full fund on carry.\nBetween past Democrat walk. Discussion imagine song rock pattern.',
    'email': 'steven45@example.net',
    'phone_number': '(439)669-1094',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Rivera',
    'Jenny Fox',
],
    'json': {
    'name': 'Gabrielle Wilson',
    'address': '56285 Obrien Islands Apt. 378\nSouth Michael, AK 32862',
},
    'key18223': 'value88959',
    'key33900': 'value18841',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Ashley Lester',
    'address': 'USNS Allen\nFPO AP 96549',
    'text': 'Show sport cause rest suddenly. Story cover school result picture box could. Allow imagine according low particular crime effect important.',
    'email': 'williamssusan@example.org',
    'phone_number': '(586)757-9582',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'David Gonzales',
    'Rhonda Ross',
],
    'json': {
    'name': 'John Parsons',
    'address': '7125 Ashley Throughway Apt. 081\nRileyberg, MD 41429',
},
    'key92147': 'value94883',
    'key80928': 'value28125',
    'key14326': 'value93703',
    'key50945': 'value4054',
    'key64821': 'value27194',
    'key21188': 'value90759',
    'key30212': 'value89084',
    'key59215': 'value81984',
    'key18130': 'value36558',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Luis Sherman',
    'address': '20542 David Garden Suite 404\nChristinaside, MI 33198',
    'text': 'Language successful move direction pay field base policy. Could difficult information ok half.',
    'email': 'phampton@example.com',
    'phone_number': '853.358.9855x953',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Brittany Brooks',
    'Courtney Richardson',
],
    'json': {
    'name': 'Andrea Cummings MD',
    'address': '05282 Gomez Circle Suite 964\nEast Michaelview, TN 52786',
},
    'key86332': 'value53005',
    'key70220': 'value1250',
    'key23882': 'value19437',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'David Rodriguez',
    'address': '5378 Jasmine Skyway Apt. 116\nNew Elizabeth, MP 97783',
    'text': 'Have on night world ago of your. Along real trip serve main listen. Economic mind thousand miss.',
    'email': 'vargasjames@example.org',
    'phone_number': '8493607821',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'John Smith',
    'Brandy Wang',
    'Jenna Romero',
    'Michael Waters',
    'Howard Johnson',
    'Elizabeth Nguyen',
    'Charles Stewart',
    'Ashley Wilson',
],
    'json': {
    'name': 'Jenny Mora',
    'address': '7682 Vaughan Underpass\nPort Scott, WY 26779',
},
    'key5711': 'value67393',
    'key55576': 'value46314',
    'key50288': 'value97402',
    'key52227': 'value51481',
    'key39471': 'value98116',
    'key84612': 'value18522',
    'key83451': 'value46988',
    'key42018': 'value4804',
    'key19489': 'value63967',
    'key94948': 'value89510',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Heather Farley',
    'address': '4151 Cameron Expressway\nJonbury, HI 96494',
    'text': 'Indeed one big fill. Sound program increase meet sport price.\nThing in event. Environment figure your subject participant ok only.\nSupport edge of parent movie manage. Little heavy for hundred.',
    'email': 'davisamber@example.com',
    'phone_number': '347-417-8660',
    'array_int_dynamic': [
    1128,
],
    'array_varchar_dynamic': [
    'Martha Brown',
    'Jonathan Short',
    'Kimberly Lopez',
    'Kimberly Brown',
    'Paula Pruitt',
    'Ryan Salazar',
    'Kathryn Hall',
    'James Armstrong',
],
    'json': {
    'name': 'Steven Mitchell',
    'address': 'USNV Savage\nFPO AP 91450',
},
    'key95045': 'value88114',
    'key99271': 'value987',
    'key12986': 'value44421',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Donald Smith',
    'address': '801 Conrad Drive\nNew Brianville, TN 46556',
    'text': 'Theory international simply strong watch real with. Visit give she specific. Some hear wonder PM also.',
    'email': 'tanyahenderson@example.com',
    'phone_number': '(480)692-4027',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Shane Campbell',
    'Andrea Johnson',
    'Tonya Norris',
    'Taylor Newton',
    'Jackson Smith',
    'Donald Allen',
    'Stacey Marshall',
    'Robert Williams',
    'Michael Harrington',
    'Kim Roy',
],
    'json': {
    'name': 'Tonya Mercer',
    'address': '61991 Fisher Vista Apt. 345\nDebraville, MS 80756',
},
    'key63082': 'value32019',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'James White',
    'address': '970 Mccullough Canyon Apt. 474\nSouth Ivanborough, VT 26459',
    'text': 'Walk while room face she itself. Grow population young forget arrive relationship. Until listen himself nearly dinner top matter.',
    'email': 'kristenaustin@example.com',
    'phone_number': '001-636-440-1672x8536',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Atkinson',
    'Bradley Maynard',
    'Mrs. Brandi Ray PhD',
    'Jessica Shields',
    'Amber Aguilar',
],
    'json': {
    'name': 'Pamela Bowen',
    'address': '32825 Johnson Forges Apt. 138\nRebeccaberg, RI 06556',
},
    'key96433': 'value82735',
    'key56335': 'value96821',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Mike Zuniga',
    'address': '98252 Alison Mission Suite 282\nRossberg, TX 49128',
    'text': 'Man black yourself produce. Theory pick foreign teacher market skin. Dinner attention game senior onto.',
    'email': 'montgomerymatthew@example.org',
    'phone_number': '8727416324',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jonathan Kennedy',
    'Chad Turner',
    'Linda Donaldson',
],
    'json': {
    'name': 'John Perez',
    'address': 'Unit 0078 Box 0782\nDPO AA 52923',
},
    'key14461': 'value93801',
    'key72879': 'value4873',
    'key36684': 'value43637',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Stephen Brown',
    'address': '17472 Daniel Lake\nBowmanville, NE 51323',
    'text': 'Enter indeed put read field outside. Remain American shoulder add treatment. Address interview form some.',
    'email': 'kimberlyshepard@example.org',
    'phone_number': '001-824-768-4462x3822',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Harris',
    'Michael Mills',
],
    'json': {
    'name': 'Stacy Cooper',
    'address': '25987 Meza Keys\nWest Brittanyfurt, GU 97786',
},
    'key62421': 'value61270',
    'key27438': 'value50603',
    'key99183': 'value88723',
    'key60555': 'value32712',
    'key47522': 'value43285',
    'key21578': 'value5634',
    'key78852': 'value18259',
    'key85530': 'value76928',
    'key67574': 'value89068',
    'key41652': 'value25110',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Joseph Gardner Jr.',
    'address': '99372 Sheri Locks\nJuliemouth, AK 50119',
    'text': 'Operation try system yourself take early.\nMan party traditional practice look attack growth. With nature may second left.',
    'email': 'heather80@example.com',
    'phone_number': '761.366.4225',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Ford',
    'Cynthia Baker',
    'Andrew Stone',
    'Dr. Matthew Boone',
    'Vanessa Walker',
],
    'json': {
    'name': 'Vincent Wilson',
    'address': '77815 Jessica Throughway\nWilliamfurt, OR 11221',
},
    'key36393': 'value80112',
    'key94001': 'value90216',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Jenna George',
    'address': 'Unit 2215 Box 5135\nDPO AP 32115',
    'text': 'Threat leg whatever around song water already. Stage thought hand common way ten. Campaign about quickly of.\nCurrent today strategy sport.',
    'email': 'ucummings@example.net',
    'phone_number': '856-955-7445x68557',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Carol Norton',
    'Nathan Wade',
    'Kristen Hernandez',
    'Glen Howard',
    'David Frost',
    'Blake Nichols',
    'Shawn Henry',
    'Stephanie Dickerson',
    'Rebecca Morris',
    'Rebecca Brown',
],
    'json': {
    'name': 'Mr. Samuel Austin Jr.',
    'address': '6784 Ashley Port Apt. 437\nRodriguezside, IA 29918',
},
    'key41685': 'value71883',
    'key14365': 'value82516',
    'key86940': 'value43773',
    'key61851': 'value54703',
    'key97888': 'value21115',
    'key40090': 'value86569',
    'key77351': 'value6782',
    'key22258': 'value96095',
    'key61694': 'value26908',
    'key59705': 'value31674',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Mark Crosby',
    'address': '1307 Christopher Key\nBrownburgh, TX 86429',
    'text': 'Teach indicate economy expert. Nation wind trip seat production.',
    'email': 'klucero@example.com',
    'phone_number': '(236)297-6278x8968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Tamara Franco',
    'Lorraine Powell',
    'Marissa Robbins',
    'Bradley Oconnor',
    'Amanda Blair',
    'Joshua Odonnell',
    'Anthony Davis',
    'Dr. Bradley Cook',
    'Lori Malone',
    'Joshua Ortiz',
],
    'json': {
    'name': 'Emily Mccullough',
    'address': '54365 John Valleys Apt. 302\nNorth Tinabury, CA 16583',
},
    'key94658': 'value90371',
    'key17180': 'value22012',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Emily Silva',
    'address': '885 Lopez Locks Apt. 583\nBrittanyfort, MT 08684',
    'text': 'Then far yes under son. Car tree as turn response.\nConsider agreement center season change. Cover same rate machine argue with similar. Indicate instead bar teacher spend them heart.',
    'email': 'sherrycarter@example.com',
    'phone_number': '717.982.1951',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mitchell Hansen',
    'Cheryl Barrett',
    'Nicholas Dixon',
    'Heather Rogers',
],
    'json': {
    'name': 'Michael Barnes',
    'address': '64158 Ashley Cliffs Suite 068\nEast Kristaborough, CT 38303',
},
    'key44960': 'value8444',
    'key51564': 'value26546',
    'key41258': 'value32741',
    'key8880': 'value92976',
    'key23795': 'value44680',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'John Ortega',
    'address': '4763 John Creek\nSmithside, MS 70779',
    'text': 'Force reason mother collection ever business floor. Stand half star. Away everything left cultural adult.\nRace affect generation after certainly executive. Item society position.',
    'email': 'haileyobrien@example.org',
    'phone_number': '570.832.9151',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Burgess',
    'Tina Day',
    'Russell Ware',
    'Matthew James',
    'Kayla Austin',
    'Carol Spears',
    'Tyler Stanley',
],
    'json': {
    'name': 'Matthew Daniels',
    'address': 'PSC 1957, Box 5906\nAPO AA 44947',
},
    'key73180': 'value44896',
    'key28337': 'value33475',
    'key93383': 'value85341',
    'key65290': 'value39511',
    'key4588': 'value87435',
    'key79457': 'value51629',
    'key90858': 'value50728',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Caitlyn Gilbert',
    'address': '807 Smith Meadows Suite 065\nGlendaborough, AL 69226',
    'text': 'Environmental himself family guy learn shoulder. Social standard international their father century simple down. Poor expect gas job.\nFind for surface window. Miss within follow ball benefit.',
    'email': 'nmontgomery@example.org',
    'phone_number': '001-913-936-0426x044',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Russell Taylor',
    'Aaron Day',
],
    'json': {
    'name': 'Christopher White',
    'address': '7352 Katie Meadow Suite 368\nEast Daniel, KY 93456',
},
    'key40107': 'value23219',
    'key91781': 'value38490',
    'key12121': 'value66145',
    'key48184': 'value35015',
    'key19017': 'value77348',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Laurie Webster MD',
    'address': '4423 John Meadow\nNorth Michelle, NC 19663',
    'text': 'Effect group nothing above somebody sense talk.\nIf record father leave main letter case present. Rest enough live first they. Role station check professional risk.',
    'email': 'ikirby@example.org',
    'phone_number': '299.469.8246',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Donald White',
    'Patty Warren',
    'Michelle Flores',
    'Dana Harvey',
    'Terri Crawford',
    'Robert Willis',
    'Kayla Guzman',
    'Benjamin Delgado',
    'Jeremy Brooks',
    'Lori Murray',
],
    'json': {
    'name': 'Mary Chan',
    'address': '67934 Williams Course Suite 291\nRonaldmouth, MD 05384',
},
    'key57635': 'value18744',
    'key78778': 'value76368',
    'key72907': 'value26361',
    'key84641': 'value54809',
    'key64800': 'value28912',
    'key29994': 'value64546',
    'key50949': 'value53822',
    'key25722': 'value97808',
    'key86603': 'value45231',
    'key35260': 'value70035',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Douglas Wilson',
    'address': 'Unit 8400 Box 0840\nDPO AA 26016',
    'text': 'From ago decade attack probably. To must respond all only happy less. Range carry near finally article.\nItself deep sea wind yet put concern property. Growth forward bring chair.',
    'email': 'robertbailey@example.org',
    'phone_number': '749-329-3501x39851',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brent Bartlett',
],
    'json': {
    'name': 'Jacqueline Ramirez',
    'address': '2435 Alicia Parkways Suite 617\nNorth Jared, ME 79968',
},
    'key57092': 'value69731',
    'key38471': 'value59948',
    'key94565': 'value73607',
    'key44079': 'value76841',
    'key24811': 'value1342',
    'key31361': 'value90004',
    'key23923': 'value23276',
    'key40514': 'value15022',
    'key26424': 'value2761',
    'key39668': 'value64173',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Grant Smith',
    'address': '150 Patrick Isle Apt. 031\nWest Tyler, MH 47251',
    'text': 'Impact should former certainly worry site still. Election person order candidate there under tax.',
    'email': 'bsmith@example.com',
    'phone_number': '+1-771-801-8763x68963',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dawn Burns',
],
    'json': {
    'name': 'Colleen Murray',
    'address': '040 Henderson Cove Apt. 936\nSouth Matthew, FL 06136',
},
    'key71227': 'value77033',
    'key46073': 'value46591',
    'key9665': 'value84306',
    'key45232': 'value69249',
    'key54074': 'value89530',
    'key68669': 'value53164',
    'key12806': 'value30867',
    'key26152': 'value76443',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'John Edwards',
    'address': '917 Alexander Mall\nEast Michealside, MP 73534',
    'text': 'Law bit standard enter safe. Skill executive far body pressure major important.\nForm lead example song voice will strategy. Side adult including benefit still talk. Give various fall loss.',
    'email': 'jamieneal@example.net',
    'phone_number': '6899736435',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Greer',
    'Megan Sexton',
    'Justin Sanchez',
    'Kathy Cameron',
    'Kristin Evans',
    'Mr. Jesse Barrett',
],
    'json': {
    'name': 'Mary Guzman',
    'address': '8044 Diana Plains Suite 395\nJamesfurt, SC 44685',
},
    'key64725': 'value62847',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Valerie Jones',
    'address': '0686 Matthew Land\nNorth Daniellehaven, AL 51916',
    'text': 'Behind employee human movement young hot enjoy. Note girl go yard.\nHer see ok player technology hope. Body above range benefit room important ahead.',
    'email': 'joshua56@example.net',
    'phone_number': '6553848820',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Marissa Chan',
    'Joseph Raymond',
    'Diane King',
    'Matthew Mccarthy',
    'Darren Spence',
    'Jennifer Knox',
    'Tiffany Williams',
    'Debra Long',
    'Connie Ortiz',
    'Brian Shields',
],
    'json': {
    'name': 'Daniel Griffin',
    'address': '4528 Williams Circles Apt. 579\nNew Ashley, PA 27889',
},
    'key33432': 'value88923',
    'key81587': 'value65173',
    'key47052': 'value56612',
    'key43306': 'value34052',
    'key12289': 'value79198',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Pamela Hodge',
    'address': 'USCGC Ferguson\nFPO AP 84384',
    'text': 'Store able mention. Lawyer bring these what someone how time.\nRepresent debate together hour. Establish hotel forget tough. With body create really rule so dog.',
    'email': 'lowerymark@example.com',
    'phone_number': '(236)729-6917x2820',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mark Dawson',
    'Michael Rogers',
    'Tamara Simon',
    'Thomas Evans',
],
    'json': {
    'name': 'Emily Holder MD',
    'address': '42197 Sandra Path Suite 545\nBrettstad, AL 98954',
},
    'key88643': 'value54092',
    'key58559': 'value15782',
    'key67656': 'value49475',
    'key93408': 'value11629',
    'key57600': 'value36076',
    'key1602': 'value64470',
    'key85827': 'value57535',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Joshua Bauer',
    'address': '865 Martinez Squares Suite 320\nLisafurt, CO 35775',
    'text': 'What order among PM scientist arrive natural recently. Enter start eat glass though. Another drive sign join each pull.',
    'email': 'christophernichols@example.com',
    'phone_number': '267.710.1308x5408',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Harold Davis',
    'Eric Collins',
    'Raymond Warren',
    'Mark Jackson',
    'Douglas Powers',
    'Nicole Clark',
],
    'json': {
    'name': 'Melissa Nelson',
    'address': '71265 Morgan Port Apt. 902\nPort Derek, NH 84227',
},
    'key21446': 'value59447',
    'key37211': 'value38879',
    'key70610': 'value66616',
    'key55571': 'value8417',
    'key17752': 'value24553',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Jasmine Thomas',
    'address': '0087 Carrie Spurs\nLake Katie, VA 69831',
    'text': 'Law kind interest run teacher magazine. Section cultural lawyer rich true national.\nRecently operation pass. Bring time almost thus key best. Loss weight cut.',
    'email': 'meganmorales@example.net',
    'phone_number': '001-422-497-6370x0886',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Keith Kim',
],
    'json': {
    'name': 'Jody Robinson',
    'address': '32371 George Square\nAngelberg, FL 99326',
},
    'key97774': 'value9479',
    'key99684': 'value17546',
    'key35590': 'value46042',
    'key94159': 'value22081',
    'key15644': 'value14115',
    'key4882': 'value41016',
    'key36115': 'value73370',
    'key94329': 'value21909',
    'key71118': 'value53797',
    'key32398': 'value79565',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Nancy Lewis',
    'address': '9890 Lyons Lodge Apt. 636\nLeechester, CA 92135',
    'text': 'Minute surface notice. Fire their wrong right ground election cost.\nThrow view second. Yourself glass home production group imagine serious.',
    'email': 'dmelendez@example.net',
    'phone_number': '721.701.2124x458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Olsen',
    'Sarah Brown',
    'James Levy',
    'David Williams',
    'Peter Franklin',
    'Heather Lewis',
],
    'json': {
    'name': 'Jennifer Larson',
    'address': '102 Kristin Via Apt. 136\nMichelleborough, MN 11274',
},
    'key62080': 'value24957',
    'key40663': 'value71076',
    'key34385': 'value54941',
    'key4915': 'value18794',
    'key46356': 'value7974',
    'key8980': 'value23284',
    'key98502': 'value77487',
    'key98618': 'value46890',
    'key2817': 'value24967',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Sarah Berry',
    'address': '8261 Jo Walk\nSmithview, DC 64093',
    'text': 'Garden head wind early natural Congress hospital. Mouth always could remember peace. Son audience beautiful probably behind.\nMedia door role action. Worry give be they community prevent.',
    'email': 'ramosjoseph@example.com',
    'phone_number': '814.376.2290',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jody Peterson',
    'Robin Jones',
    'Thomas Ellis',
    'Miguel Perez',
    'Danielle Mosley',
],
    'json': {
    'name': 'Cheryl Mitchell',
    'address': '2586 Edwards Pass\nBrandonmouth, TX 21654',
},
    'key10364': 'value86487',
    'key7289': 'value16756',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Danielle Stewart',
    'address': '2829 Jackson Keys Apt. 290\nYangfort, AL 66636',
    'text': 'Prevent else majority enjoy day catch again.\nCompany personal despite even. Pay stock state our serious education yeah.\nAdult common choose. Up affect Mr. Stage north really together nothing.',
    'email': 'adam68@example.com',
    'phone_number': '521.995.2784x6264',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Antonio Rich',
],
    'json': {
    'name': 'Ryan Edwards',
    'address': '5823 Young Harbors\nLake Melissachester, NH 94452',
},
    'key42472': 'value22016',
    'key30980': 'value93973',
    'key31388': 'value86313',
    'key37574': 'value6428',
    'key29012': 'value3781',
    'key76067': 'value92260',
    'key77305': 'value64365',
    'key33223': 'value84199',
    'key75839': 'value28705',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Erika Shaw',
    'address': '65107 Jones Station Apt. 360\nSouth Andrewfurt, MH 64669',
    'text': 'Similar matter get meeting when might. Own company medical cell join care brother. Night phone rule lot ground red.\nBack religious conference fish. Recent heart issue full police happen not.',
    'email': 'perezamy@example.org',
    'phone_number': '757.275.8267x05921',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Dylan Navarro',
    'Amber Hunter',
    'Brian Robinson',
    'Lisa Barron',
    'Thomas Johnson',
    'Richard Andrews',
],
    'json': {
    'name': 'Michael Graham',
    'address': 'USCGC Johnson\nFPO AE 97278',
},
    'key44231': 'value70033',
    'key73810': 'value51164',
    'key66894': 'value14541',
    'key97172': 'value2400',
    'key21902': 'value7466',
    'key36925': 'value38892',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Tina Branch',
    'address': 'PSC 3623, Box 0113\nAPO AA 25120',
    'text': 'Hot sign event nor tend administration best. Big voice door them relate nation fast. Economy within course.',
    'email': 'afrey@example.org',
    'phone_number': '+1-834-767-1391x714',
    'array_int_dynamic': [
    85323,
],
    'array_varchar_dynamic': [
    'Richard Murray',
    'April Wright',
    'Michael Oliver',
    'Courtney Leonard',
],
    'json': {
    'name': 'Donald Moran',
    'address': '1957 Small Mills\nDennisberg, TN 86497',
},
    'key34360': 'value47295',
    'key27154': 'value30366',
    'key27659': 'value2616',
    'key28540': 'value49300',
    'key80770': 'value41860',
    'key17648': 'value80087',
    'key43453': 'value25782',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Michael Grant',
    'address': '51919 Perry Harbor Suite 542\nKennethmouth, MD 26989',
    'text': 'South drop activity police history simply past. Gas million international eight. Blue like but country pay whatever.',
    'email': 'casey72@example.net',
    'phone_number': '710.745.4379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Destiny Wagner',
    'Lisa Vance',
    'Kenneth Miller',
],
    'json': {
    'name': 'Daniel Willis',
    'address': '98044 Jacob Plaza\nJordanfurt, MN 06252',
},
    'key34002': 'value78083',
    'key67008': 'value65056',
    'key40845': 'value3702',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Mrs. Lisa Conner',
    'address': '2725 Matthew Hill\nRhondaside, VA 38695',
    'text': 'Candidate project region seven national work sometimes. Concern page friend trial others team simply. Congress enter room lead turn. World student table onto bag pretty.',
    'email': 'kristinaodonnell@example.net',
    'phone_number': '998.451.2463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jeanette Brown',
    'Phillip Mccarthy',
    'Kristi Reynolds',
    'Michael Hill',
],
    'json': {
    'name': 'Jennifer Ford',
    'address': '92225 Odonnell Creek\nEast Nathaniel, GA 55942',
},
    'key42629': 'value95497',
    'key34274': 'value63254',
    'key99571': 'value26122',
    'key61471': 'value21956',
    'key87392': 'value40319',
    'key47614': 'value49968',
    'key77690': 'value93427',
    'key2337': 'value39004',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Anna Wright',
    'address': '1579 Ashley Common Apt. 164\nSouth Joshuachester, NC 11789',
    'text': 'Yard scientist with although field open city money. Six newspaper continue individual.\nPressure office sit consumer truth wear set human. Production different bar figure say wind turn forward.',
    'email': 'hoodmisty@example.com',
    'phone_number': '348.835.5790x9450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julie Erickson',
    'Shelley Kelly',
    'Anita Terry',
    'Kara Thomas',
    'Daniel Greene',
    'Cathy Price',
    'Larry Howell',
],
    'json': {
    'name': 'Ashlee Cole',
    'address': '3641 Alexandria Squares\nSmithside, IL 11642',
},
    'key31457': 'value69495',
    'key45472': 'value98525',
    'key2284': 'value58588',
    'key5293': 'value22691',
    'key90365': 'value58172',
    'key8016': 'value30542',
    'key60206': 'value77965',
    'key60216': 'value88077',
    'key42996': 'value34421',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Anthony Norton',
    'address': '173 Lynn Mountain Suite 425\nEast Deanborough, MH 92522',
    'text': 'Yard fine life available. Field himself there follow prove. Officer close name stop environment can. Remain single lot couple expect real body.',
    'email': 'fsilva@example.org',
    'phone_number': '564.670.1348x01533',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Fred Buchanan',
    'Alyssa Parker',
    'Dr. Jonathan Murphy Jr.',
    'Jillian Hall DVM',
    'Theresa Martin',
    'Cassandra Meyer',
],
    'json': {
    'name': 'Michael Carter',
    'address': '3385 Lowe Forge\nEast Markshire, LA 53024',
},
    'key85203': 'value57188',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Steven Green',
    'address': 'Unit 7689 Box 2509\nDPO AP 42303',
    'text': 'Idea campaign indeed international late.\nFront billion fight woman tell future ever. Phone significant dream thus table. Live perform fear opportunity agree believe themselves.',
    'email': 'lthompson@example.net',
    'phone_number': '001-376-858-3621',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Gregg Simpson',
    'Mr. Walter Berry MD',
],
    'json': {
    'name': 'Carrie Newman',
    'address': 'Unit 6435 Box 9038\nDPO AA 61718',
},
    'key38699': 'value25809',
    'key9483': 'value67476',
    'key54649': 'value66066',
    'key94379': 'value17192',
    'key27662': 'value30020',
    'key88657': 'value54509',
    'key1970': 'value91821',
    'key84058': 'value66626',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Cathy Villanueva',
    'address': '51939 Chase Union Suite 158\nWest Fernando, MP 31857',
    'text': 'Shoulder responsibility Congress north past. Around water dream anything receive heavy.\nWorld too exist product past. Tell agreement any maybe. Water drop defense respond.',
    'email': 'matthewbryant@example.com',
    'phone_number': '384-458-7600',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Grant',
],
    'json': {
    'name': 'Randall Reilly',
    'address': '42340 Harper Lock Apt. 788\nMcknightville, UT 94073',
},
    'key91193': 'value11762',
    'key17872': 'value59167',
    'key35351': 'value6945',
    'key28405': 'value27378',
    'key57954': 'value14182',
    'key93770': 'value71123',
    'key40405': 'value2863',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Samantha Potts',
    'address': '398 Jeremy Flats Apt. 590\nLisaport, KS 08514',
    'text': 'Drop under analysis notice foreign. Tough common discuss letter level among start get. Worry left end issue building operation. Necessary within usually eye sell understand.',
    'email': 'melissa92@example.org',
    'phone_number': '411-371-9352',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Edwards',
    'Jeffrey Smith',
    'Deborah Delgado',
    'Kim Lindsey',
    'Bradley Bass',
    'Dr. Jose Rivera',
    'Robert Love',
    'Scott Hernandez',
    'Karen Mendoza',
],
    'json': {
    'name': 'Mary Freeman',
    'address': '98099 Lane Plains\nRogerville, VA 11117',
},
    'key97103': 'value38080',
    'key21221': 'value89899',
    'key78710': 'value89959',
    'key74686': 'value34189',
    'key16903': 'value87494',
    'key26525': 'value47861',
    'key15237': 'value67642',
    'key9863': 'value46922',
    'key87163': 'value22843',
    'key28019': 'value45684',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Thomas Boyer',
    'address': '071 Lawson Green Suite 605\nWest Danny, MI 44796',
    'text': 'Head fund able much training ahead mother. Future so performance good ten raise. Board like Democrat from. Feeling particularly protect raise.',
    'email': 'tjones@example.com',
    'phone_number': '993-425-1046x509',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Zachary Nunez',
    'Jacob Miller',
],
    'json': {
    'name': 'Christopher Dixon',
    'address': '92704 Douglas Drive\nRobertville, NM 74735',
},
    'key55853': 'value44035',
    'key35273': 'value42006',
    'key74809': 'value23437',
    'key35332': 'value83560',
    'key91448': 'value65142',
    'key9233': 'value18444',
    'key80947': 'value17107',
    'key58872': 'value6989',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Jennifer Flowers',
    'address': '8841 Lori Pass Suite 556\nEast Zacharystad, GA 55403',
    'text': 'Night player land station career right letter. Surface rock coach meet. Charge way safe war necessary woman hair.\nAt mother perform sound mention instead.',
    'email': 'eho@example.com',
    'phone_number': '8818350134',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Anne Wilson',
    'Roy Haley',
    'Kimberly Jones',
    'Sarah Cruz',
    'Michael Hensley',
    'Stephanie Middleton',
    'Julia Anderson',
],
    'json': {
    'name': 'Erin Bowers',
    'address': '44717 Brian Parkways\nCharlesport, NH 05494',
},
    'key10285': 'value10117',
    'key52706': 'value14105',
    'key51298': 'value30535',
    'key3964': 'value62246',
    'key33106': 'value7717',
    'key10413': 'value64923',
    'key80667': 'value29339',
    'key95721': 'value72541',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Susan Valdez',
    'address': '20913 Kelly Freeway Suite 839\nWest Vincent, LA 52094',
    'text': 'Factor successful include institution use must. Hundred sound instead beat.',
    'email': 'thomaspennington@example.org',
    'phone_number': '293.513.9403',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Laura Gardner',
    'Justin Price',
    'Kayla Jacobs',
    'Yesenia Nichols',
    'Mark Barton',
    'Joshua Evans',
    'Tracy Johnson',
],
    'json': {
    'name': 'Miss Tammy West DVM',
    'address': 'PSC 7361, Box 8316\nAPO AE 71205',
},
    'key79927': 'value68515',
    'key22000': 'value71039',
    'key69742': 'value36602',
    'key73077': 'value3592',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Laura Harrison',
    'address': '7082 Taylor Common Apt. 543\nNorth Victoriaburgh, MA 09008',
    'text': 'Keep once impact.\nMonth you where beat. Reach they expect number floor threat.\nReally miss through law star scene. Down feeling close front yet wind.',
    'email': 'hshepherd@example.org',
    'phone_number': '001-530-375-6204x3340',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Tonya Scott',
    'Desiree Williams',
    'Daniel Benjamin',
    'Mary Beck',
    'Jeanette Kim',
    'Jordan Patton',
    'Lisa Boyer',
    'Nicholas Mccoy',
    'Jeffrey Terry',
],
    'json': {
    'name': 'Jeremy Suarez',
    'address': '355 Troy Prairie Apt. 881\nRodriguezland, KY 75585',
},
    'key34694': 'value23065',
    'key77648': 'value30092',
    'key21547': 'value48324',
    'key6659': 'value16229',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Brandon Kelly',
    'address': '7347 Benjamin Trail\nAdamsfurt, IA 16467',
    'text': 'Economic close source word. One build lawyer something report concern. Partner business evidence however case.',
    'email': 'reedjessica@example.com',
    'phone_number': '(762)995-1411',
    'array_int_dynamic': [
    11539,
],
    'array_varchar_dynamic': [
    'Sonia Lopez',
    'Peter Johnson',
],
    'json': {
    'name': 'Holly Lowe',
    'address': '769 Vargas Port Suite 845\nLake Jeremyside, KY 41628',
},
    'key90394': 'value6475',
    'key99627': 'value9068',
    'key14596': 'value55908',
    'key48403': 'value58078',
    'key89775': 'value93918',
    'key7555': 'value18100',
    'key62216': 'value26503',
    'key37519': 'value44659',
    'key96885': 'value35504',
    'key87957': 'value93097',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Allen Mullins',
    'address': '5645 Lyons Junctions\nNorth Carolfurt, NJ 32474',
    'text': 'Degree lead decide organization environment marriage. Have record again enter across mission show.',
    'email': 'james87@example.com',
    'phone_number': '757-218-8468x342',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Lewis',
    'Brenda Green',
    'Margaret Acosta',
    'Madison Larson',
    'Nicole Grimes',
    'Christina Roberts',
],
    'json': {
    'name': 'Cory Howard',
    'address': '7073 Rachel Locks\nSteventon, MI 52463',
},
    'key63241': 'value56182',
    'key67652': 'value92',
    'key75002': 'value38350',
    'key56916': 'value95989',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Nicole Salinas',
    'address': '94437 Dana Track\nAmandafort, NE 29083',
    'text': 'Catch treat why line training war present. Stage structure fill weight enjoy.\nEverything factor score field serious. Physical eye they year fear economic. Action professor southern current its.',
    'email': 'amy10@example.net',
    'phone_number': '+1-554-957-1119x867',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Breanna Thomas',
    'Martha Goodwin',
    'James Patterson',
    'Robin Hamilton',
    'Mitchell Thompson',
    'Andrea Mcintyre',
    'Cory Mcbride',
    'Jessica Simmons',
    'Gregory Leblanc',
],
    'json': {
    'name': 'Courtney Thomas',
    'address': '76153 Andrews Loaf Suite 645\nAndretown, KY 91225',
},
    'key202': 'value98324',
    'key54040': 'value33151',
    'key47404': 'value13584',
    'key97069': 'value85952',
    'key52993': 'value55372',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Amy Lee',
    'address': '5836 Decker Drive Suite 553\nDeleonfurt, ME 56496',
    'text': 'Debate both public fire view talk country. Black side whose season.\nWithin forward chance visit. Character remember opportunity bit know.',
    'email': 'wrightmegan@example.com',
    'phone_number': '001-959-793-9716x952',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Johnston',
],
    'json': {
    'name': 'Ashley Yu',
    'address': '50238 Lori Center\nMartinezville, ID 05576',
},
    'key81872': 'value62491',
    'key39922': 'value53947',
    'key91666': 'value55778',
    'key20538': 'value54431',
    'key62403': 'value39944',
    'key33385': 'value58981',
    'key32763': 'value47431',
    'key30816': 'value39948',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Stephanie Williams',
    'address': '1808 Matthew Road\nNew Stephenstad, NE 35225',
    'text': 'Lose it door idea. Only join off way million. On author single behavior individual lead power indicate.\nImprove draw task white rock. Personal wind ever edge.',
    'email': 'chanrobin@example.com',
    'phone_number': '624-829-0587',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mary Smith',
    'Ryan Price',
    'Tina Gregory',
    'Erica Rich',
    'Stacy Ruiz',
],
    'json': {
    'name': 'Chad Gomez',
    'address': '7968 Julie Springs\nAprilstad, FL 25845',
},
    'key74020': 'value75396',
    'key99436': 'value16109',
    'key2798': 'value66331',
    'key71083': 'value17175',
    'key59413': 'value53044',
    'key25230': 'value11967',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Wesley Rodriguez',
    'address': '01607 Carr Ranch Suite 222\nEast Justinmouth, MH 84760',
    'text': 'Throughout only hundred treat.\nTend teacher condition. Like newspaper black rich star.',
    'email': 'qriley@example.net',
    'phone_number': '001-283-643-4462x658',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Lopez',
    'Andrew Combs',
    'Kari Kirk',
    'Stephen Serrano',
    'Luke Collins',
    'Anthony Johnson',
    'Heather Brown',
],
    'json': {
    'name': 'Aaron Weiss',
    'address': '8682 Lee Crescent Suite 292\nRamirezside, IA 07564',
},
    'key66110': 'value5798',
    'key55776': 'value45013',
    'key33224': 'value57481',
    'key68657': 'value59781',
    'key44283': 'value71528',
    'key61691': 'value80304',
    'key83880': 'value90210',
    'key51316': 'value4985',
    'key78703': 'value98352',
    'key17098': 'value9297',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Christian Snyder',
    'address': '0915 Luke Corners\nJaredton, IN 06197',
    'text': 'American dinner exist as figure letter. Discover information former food place.\nSay none send PM. Peace your in role federal air visit small. Science six hand least within local recently.',
    'email': 'ohill@example.com',
    'phone_number': '884.513.9198x55731',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'William Miller',
    'Brandon Flores',
    'Brian Dillon',
],
    'json': {
    'name': 'Jessica Duffy',
    'address': 'PSC 3722, Box 4770\nAPO AA 14697',
},
    'key20500': 'value33889',
    'key12874': 'value52179',
    'key17829': 'value90975',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Jake Alvarez PhD',
    'address': '487 Corey Meadows\nOliviamouth, ND 91661',
    'text': 'Different process specific like eye put television finish. Consider billion with recently I head government.\nDifferent peace among him mind. Eight poor teach than record.',
    'email': 'robin93@example.org',
    'phone_number': '(973)382-2305',
    'array_int_dynamic': [
    96346,
],
    'array_varchar_dynamic': [
    'Nathan Boyer',
    'Linda Hancock',
    'Nathan Peterson',
    'Ronnie Castillo',
    'Gordon Hunt Jr.',
],
    'json': {
    'name': 'Robert Clark',
    'address': '5526 Reynolds Vista Suite 714\nNorth Oscarstad, MT 38815',
},
    'key8992': 'value16708',
    'key78105': 'value65380',
    'key47168': 'value2476',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Kathryn Ali',
    'address': '6698 Davis Ports\nWest Pamela, MO 61187',
    'text': 'Direction technology lot he. Place answer mouth claim book. Chance during play perform talk though.',
    'email': 'smithrobert@example.com',
    'phone_number': '+1-791-353-9371x0701',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Beltran',
    'Laurie Jackson',
    'Anthony Stephens',
    'Rebekah Barrera',
    'Alexandria Elliott',
    'Patricia Ramirez',
    'Marcus Christian',
],
    'json': {
    'name': 'Erin Hanna',
    'address': '887 Nancy Ranch Apt. 582\nRamirezbury, IA 33478',
},
    'key36279': 'value8120',
    'key56421': 'value44732',
    'key24699': 'value60428',
    'key93204': 'value94077',
    'key15268': 'value50667',
    'key24127': 'value17681',
    'key80280': 'value73271',
    'key97419': 'value78430',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Jessica Hopkins',
    'address': '53179 Simmons Motorway\nNorth Nathan, HI 70004',
    'text': 'Despite around scientist build herself.\nStaff future order despite again. Scene attention group past between foreign might. National contain look term.',
    'email': 'kellie59@example.net',
    'phone_number': '(970)734-4086x0344',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Mcknight',
],
    'json': {
    'name': 'Beth Stevens',
    'address': '738 Vasquez Burgs\nWest Danielleberg, AL 83034',
},
    'key74730': 'value55640',
    'key84739': 'value12075',
    'key65494': 'value95006',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Katelyn Richards',
    'address': '9585 Le Landing Suite 215\nMichaelfurt, NH 86602',
    'text': 'Audience stand short. Coach cold value believe down seek. Leader agree price attorney mean star.',
    'email': 'christopherbutler@example.org',
    'phone_number': '(840)622-5785x65669',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Susan Oliver',
    'Gina Harris',
    'Diana Brewer',
    'Kristina Ellison',
    'David White',
    'Kristie Sullivan',
    'Donna Fox',
    'Allison Mcbride',
    'Melissa Hoffman',
    'Lori Lee',
],
    'json': {
    'name': 'Lance Parks',
    'address': '12409 Christopher Brooks Suite 536\nSavannahport, LA 15953',
},
    'key52257': 'value74844',
    'key95577': 'value56689',
    'key62528': 'value28143',
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
    'RequestId': '9f140af9-62ef-11f0-9c24-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_54_408088kLvnDbRx',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-32-100-1]_1752744175.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl3210011752744175Json()
    test.run_tests()
